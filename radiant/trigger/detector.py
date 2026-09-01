from dataclasses import dataclass
import math
import numpy as np
from radiant.stream import StreamCursor, validate_processed


@dataclass(frozen=True)
class TriggerEvent:
    channel_id: int
    sample_index: int
    timestamp_ns: int
    value_volts: float
    packet_sequence: int
    group_delay_samples: int


class ThresholdTrigger:
    """Arm at <= low; fire at >= high. Invalid data clears the armed state.

    A crossing during holdoff is consumed. It requires a new low-to-high
    excursion to fire later. Holdoff is measured per channel in samples.
    """

    def __init__(self, high=1.0, low=0.5, holdoff_samples=0):
        if not (math.isfinite(high) and math.isfinite(low) and low < high):
            raise ValueError("thresholds must be finite with low < high")
        if type(holdoff_samples) is not int or holdoff_samples < 0:
            raise ValueError("holdoff_samples must be a nonnegative integer")
        self.high, self.low = high, low
        self.holdoff_samples = holdoff_samples
        self.reset()

    def reset(self):
        self._cursor = StreamCursor()
        self._armed = None
        self._last = None
        self._delay = None

    def process(self, packet):
        validate_processed(packet)
        source = packet.source
        self._cursor.check(source)
        if self._delay is not None and packet.group_delay_samples != self._delay:
            raise ValueError("filter delay changed; reset the trigger")
        channels = len(source.channel_ids)
        armed = np.zeros(channels, dtype=bool) if self._armed is None else self._armed.copy()
        last = [None] * channels if self._last is None else self._last.copy()
        events = []
        for row, values in enumerate(packet.volts):
            index = source.first_sample + row
            for ch, value in enumerate(values):
                if not packet.valid[row, ch]:
                    armed[ch] = False
                elif value <= self.low:
                    armed[ch] = True
                elif value >= self.high and armed[ch]:
                    armed[ch] = False
                    if last[ch] is None or index - last[ch] >= self.holdoff_samples:
                        events.append(TriggerEvent(source.channel_ids[ch], index,
                                                   int(source.timestamps_ns[row]), float(value),
                                                   source.sequence, packet.group_delay_samples))
                        last[ch] = index
        self._armed, self._last, self._delay = armed, last, packet.group_delay_samples
        self._cursor.commit(source)
        return events
