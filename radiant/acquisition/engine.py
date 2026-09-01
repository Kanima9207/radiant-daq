"""Sample-index-based simulated acquisition, independent of host wall clock."""
from dataclasses import dataclass
import numpy as np
from .adc import ADC, ADCResult


@dataclass(frozen=True)
class AcquisitionPacket:
    sequence: int
    first_sample: int
    sample_rate_hz: int
    channel_ids: tuple[int, ...]
    timestamps_ns: np.ndarray
    data: ADCResult


class AcquisitionEngine:
    def __init__(self, sample_rate_hz=50_000, channels=8, adc=None):
        if type(sample_rate_hz) is not int or not 1 <= sample_rate_hz <= 10**9:
            raise ValueError("sample_rate_hz must be an integer in [1, 1e9]")
        if type(channels) is not int or channels < 1:
            raise ValueError("channels must be a positive integer")
        self.sample_rate_hz = sample_rate_hz
        self.channel_ids = tuple(range(channels))
        self.adc = ADC() if adc is None else adc
        self._sequence = 0
        self._sample = 0

    def acquire(self, samples):
        """Consume (samples, channels); rejected chunks do not advance state."""
        values = np.asarray(samples, dtype=np.float64)
        if values.ndim != 2 or values.shape[1] != len(self.channel_ids) or not len(values):
            raise ValueError("expected nonempty (samples, channels) array")
        data = self.adc.convert(values)
        end = self._sample + len(values)
        # Python integer arithmetic avoids intermediate multiplication overflow.
        last_ns = (end - 1) * 10**9 // self.sample_rate_hz
        if last_ns > np.iinfo(np.int64).max:
            raise OverflowError("timestamp exceeds signed 64-bit nanoseconds")
        stamps = np.fromiter((i * 10**9 // self.sample_rate_hz
                              for i in range(self._sample, end)), dtype=np.int64)
        packet = AcquisitionPacket(self._sequence, self._sample, self.sample_rate_hz,
                                   self.channel_ids, stamps, data)
        self._sample = end
        self._sequence += 1
        return packet
