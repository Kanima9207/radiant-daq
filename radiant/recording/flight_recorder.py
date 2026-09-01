from dataclasses import dataclass

from .event_record import EventRecord


@dataclass(frozen=True)
class _PendingEvent:
    event_id: int
    trigger: object


class FlightRecorder:
    """Build event windows from a continuously updated SampleRingBuffer.

    Call ``process(events, ring)`` after the current processed packet has been
    appended to ``ring``. Events remain pending until their requested
    post-trigger horizon is present. Missing pre-trigger history is reported
    explicitly by EventRecord rather than fabricated.
    """

    def __init__(self, pretrigger_samples=2000, posttrigger_samples=3000):
        for name, value in (("pretrigger_samples", pretrigger_samples),
                            ("posttrigger_samples", posttrigger_samples)):
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        self.pretrigger_samples = pretrigger_samples
        self.posttrigger_samples = posttrigger_samples
        self.reset()

    def reset(self):
        self._pending = []
        self._next_event_id = 0

    @property
    def pending_count(self):
        return len(self._pending)

    def process(self, events, ring):
        snapshot = ring.snapshot()
        for event in events:
            self._validate_trigger(event)
            self._pending.append(_PendingEvent(self._next_event_id, event))
            self._next_event_id += 1

        completed, remaining = [], []
        for pending in self._pending:
            event = pending.trigger
            if snapshot.first_sample is None:
                remaining.append(pending)
                continue
            snapshot_last = snapshot.first_sample + len(snapshot.timestamps_ns) - 1
            target_last = event.sample_index + self.posttrigger_samples
            if snapshot_last < target_last:
                remaining.append(pending)
                continue
            if event.sample_index < snapshot.first_sample or event.sample_index > snapshot_last:
                raise RuntimeError("trigger sample was lost before event capture completed")
            completed.append(self._build_record(pending, snapshot, snapshot_last))
        self._pending = remaining
        return completed

    @staticmethod
    def _validate_trigger(event):
        required = ("channel_id", "sample_index", "timestamp_ns", "value_volts",
                    "packet_sequence", "group_delay_samples")
        if any(not hasattr(event, name) for name in required):
            raise TypeError("events must provide TriggerEvent-compatible metadata")

    def _build_record(self, pending, snapshot, snapshot_last):
        event = pending.trigger
        desired_first = event.sample_index - self.pretrigger_samples
        first_sample = max(snapshot.first_sample, desired_first)
        last_sample = min(snapshot_last, event.sample_index + self.posttrigger_samples)
        start = first_sample - snapshot.first_sample
        stop = last_sample - snapshot.first_sample + 1
        fields = {
            "timestamps_ns": snapshot.timestamps_ns[start:stop],
            "codes": snapshot.codes[start:stop],
            "raw_volts": snapshot.raw_volts[start:stop],
            "filtered_volts": snapshot.filtered_volts[start:stop],
            "clipped": snapshot.clipped[start:stop],
            "valid": snapshot.valid[start:stop],
        }
        return EventRecord(
            event_id=pending.event_id,
            channel_id=event.channel_id,
            trigger_sample=event.sample_index,
            trigger_timestamp_ns=event.timestamp_ns,
            trigger_value_volts=event.value_volts,
            packet_sequence=event.packet_sequence,
            sample_rate_hz=snapshot.sample_rate_hz,
            channel_ids=snapshot.channel_ids,
            group_delay_samples=event.group_delay_samples,
            first_sample=first_sample,
            requested_pretrigger_samples=self.pretrigger_samples,
            requested_posttrigger_samples=self.posttrigger_samples,
            pretrigger_complete=first_sample <= desired_first,
            posttrigger_complete=last_sample >= event.sample_index + self.posttrigger_samples,
            **fields,
        )
