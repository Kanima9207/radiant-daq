"""Ideal uniform ADC; no analog bandwidth or noise model is implied."""
from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class ADCResult:
    codes: np.ndarray
    volts: np.ndarray
    clipped: np.ndarray


@dataclass(frozen=True)
class ADC:
    bits: int = 16
    v_min: float = -10.0
    v_max: float = 10.0

    def __post_init__(self):
        if type(self.bits) is not int or not 1 <= self.bits <= 24:
            raise ValueError("bits must be an integer from 1 to 24")
        if not (math.isfinite(self.v_min) and math.isfinite(self.v_max)):
            raise ValueError("ADC limits must be finite")
        if self.v_min >= self.v_max or not math.isfinite(self.v_max - self.v_min):
            raise ValueError("ADC span must be positive and finite")

    @property
    def lsb(self):
        return (self.v_max - self.v_min) / (1 << self.bits)

    def convert(self, samples):
        """Floor-code quantiser, midpoint reconstruction, half-open input range.

        Values below v_min or >= v_max are flagged and clamped. Within the
        range, reconstruction error is at most half an LSB (roundoff aside).
        NaN and infinity are rejected rather than silently converted.
        """
        values = np.asarray(samples, dtype=np.float64)
        if not np.all(np.isfinite(values)):
            raise ValueError("samples must be finite")
        clipped = (values < self.v_min) | (values >= self.v_max)
        bounded = np.clip(values, self.v_min, self.v_max)
        codes = np.clip(np.floor((bounded - self.v_min) / self.lsb),
                        0, (1 << self.bits) - 1).astype(np.uint32)
        volts = self.v_min + (codes.astype(np.float64) + 0.5) * self.lsb
        return ADCResult(codes, volts, clipped)
