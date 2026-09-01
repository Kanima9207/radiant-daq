from dataclasses import dataclass
import numpy as np
from radiant.stream import StreamCursor, validate_processed


@dataclass(frozen=True)
class BufferSnapshot:
    first_sample: int | None
    sample_rate_hz: int | None
    channel_ids: tuple[int, ...]
    group_delay_samples: int | None
    timestamps_ns: np.ndarray
    codes: np.ndarray
    raw_volts: np.ndarray
    filtered_volts: np.ndarray
    clipped: np.ndarray
    valid: np.ndarray


class SampleRingBuffer:
    """Preallocated sample storage; overwrite oldest and count evicted samples.

    Single producer/consumer, no thread-safety guarantee. Append copies arrays;
    snapshots also copy, so subsequent caller mutations cannot alter storage.
    """

    def __init__(self, capacity_samples, channels=8):
        if type(capacity_samples) is not int or capacity_samples < 1:
            raise ValueError("capacity_samples must be a positive integer")
        if type(channels) is not int or channels < 1:
            raise ValueError("channels must be a positive integer")
        self.capacity_samples = capacity_samples
        self.channels = channels
        shape = (capacity_samples, channels)
        self._arrays = {
            "timestamps_ns": np.empty(capacity_samples, dtype=np.int64),
            "codes": np.empty(shape, dtype=np.uint64),
            "raw_volts": np.empty(shape), "filtered_volts": np.empty(shape),
            "clipped": np.empty(shape, dtype=bool), "valid": np.empty(shape, dtype=bool),
        }
        self.clear()

    def clear(self):
        self._cursor = StreamCursor()
        self._write = self._count = self.overwritten_samples = 0
        self._delay = None

    def __len__(self):
        return self._count

    def append(self, packet):
        validate_processed(packet)
        source = packet.source
        self._cursor.check(source)
        if len(source.channel_ids) != self.channels:
            raise ValueError("channel count differs from buffer configuration")
        if self._delay is not None and packet.group_delay_samples != self._delay:
            raise ValueError("filter delay changed; clear the buffer")
        n = len(packet.volts)
        keep = min(n, self.capacity_samples)
        # Skip excess input, including its logical advancement around the ring.
        start = (self._write + n - keep) % self.capacity_samples
        first = min(keep, self.capacity_samples - start)
        incoming = {"timestamps_ns": source.timestamps_ns, "codes": source.data.codes,
                    "raw_volts": source.data.volts, "filtered_volts": packet.volts,
                    "clipped": source.data.clipped, "valid": packet.valid}
        for key, values in incoming.items():
            tail = values[-keep:]
            self._arrays[key][start:start + first] = tail[:first]
            self._arrays[key][:keep - first] = tail[first:]
        self.overwritten_samples += max(0, self._count + n - self.capacity_samples)
        self._write = (self._write + n) % self.capacity_samples
        self._count = min(self._count + n, self.capacity_samples)
        self._delay = packet.group_delay_samples
        self._cursor.commit(source)

    def snapshot(self):
        positions = (self._write - self._count + np.arange(self._count)) % self.capacity_samples
        data = {key: values[positions].copy() for key, values in self._arrays.items()}
        signature = self._cursor.signature
        return BufferSnapshot(
            None if signature is None else self._cursor.next_sample - self._count,
            None if signature is None else signature[0],
            () if signature is None else signature[1], self._delay, **data)
