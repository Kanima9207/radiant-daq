"""Deterministic serial-compatible acquisition-node emulator for HW-002.

The emulator emits the CRC-protected JSON-line frames defined by HW-001 and
provides both iterator and ``readline()`` interfaces. It models device-side
sampling and framing only; it is not a claim of physical ADC, UART, USB or
real-time timing performance.
"""
from dataclasses import dataclass
import math

import numpy as np

from .bridge import ExternalAcquisitionFrame, encode_external_frame


@dataclass(frozen=True)
class HardwareEmulatorConfig:
    sample_rate_hz: int = 50_000
    channels: int = 8
    frame_samples: int = 256
    adc_bits: int = 16
    v_min: float = -10.0
    v_max: float = 10.0
    signal_frequency_hz: float = 1_000.0
    signal_amplitude_v: float = 1.0
    dc_offset_v: float = 0.0

    def __post_init__(self):
        if type(self.sample_rate_hz) is not int or not 1 <= self.sample_rate_hz <= 10**9:
            raise ValueError("sample_rate_hz must be an integer in [1, 1e9]")
        if type(self.channels) is not int or self.channels < 1:
            raise ValueError("channels must be a positive integer")
        if type(self.frame_samples) is not int or self.frame_samples < 1:
            raise ValueError("frame_samples must be a positive integer")
        if type(self.adc_bits) is not int or not 1 <= self.adc_bits <= 24:
            raise ValueError("adc_bits must be an integer from 1 to 24")
        for name in ("v_min", "v_max", "signal_frequency_hz", "signal_amplitude_v", "dc_offset_v"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
        if self.v_min >= self.v_max:
            raise ValueError("v_min must be less than v_max")
        if self.signal_frequency_hz < 0:
            raise ValueError("signal_frequency_hz must be nonnegative")
        if self.signal_amplitude_v < 0:
            raise ValueError("signal_amplitude_v must be nonnegative")


class SerialHardwareEmulator:
    """Emit continuous external acquisition frames through a serial-like API."""

    def __init__(self, config=None):
        self.config = HardwareEmulatorConfig() if config is None else config
        if not isinstance(self.config, HardwareEmulatorConfig):
            raise TypeError("config must be HardwareEmulatorConfig")
        self.reset()

    def reset(self):
        self._sequence = 0
        self._sample = 0

    @property
    def sequence(self):
        return self._sequence

    @property
    def first_sample(self):
        return self._sample

    def __iter__(self):
        return self

    def __next__(self):
        return self.next_line()

    def next_frame(self):
        cfg = self.config
        start = self._sample
        stop = start + cfg.frame_samples
        indices = np.arange(start, stop, dtype=np.int64)
        timestamps = np.fromiter(
            (int(i) * 10**9 // cfg.sample_rate_hz for i in indices),
            dtype=np.int64,
            count=cfg.frame_samples,
        )

        t = indices.astype(np.float64) / float(cfg.sample_rate_hz)
        samples = np.empty((cfg.frame_samples, cfg.channels), dtype=np.float64)
        for channel in range(cfg.channels):
            phase = 2.0 * math.pi * channel / cfg.channels
            samples[:, channel] = (
                cfg.dc_offset_v
                + cfg.signal_amplitude_v
                * np.sin(2.0 * math.pi * cfg.signal_frequency_hz * t + phase)
            )

        clipped = (samples < cfg.v_min) | (samples >= cfg.v_max)
        bounded = np.clip(samples, cfg.v_min, cfg.v_max)
        lsb = (cfg.v_max - cfg.v_min) / (1 << cfg.adc_bits)
        max_code = (1 << cfg.adc_bits) - 1
        codes = np.clip(
            np.floor((bounded - cfg.v_min) / lsb), 0, max_code
        ).astype(np.uint32)

        frame = ExternalAcquisitionFrame(
            sequence=self._sequence,
            first_sample=start,
            sample_rate_hz=cfg.sample_rate_hz,
            channel_ids=tuple(range(cfg.channels)),
            adc_bits=cfg.adc_bits,
            v_min=cfg.v_min,
            v_max=cfg.v_max,
            timestamps_ns=timestamps,
            codes=codes,
            clipped=clipped.astype(bool),
        )
        self._sequence += 1
        self._sample = stop
        return frame

    def next_line(self):
        """Return one UTF-8 JSON line as text, terminated with newline."""
        return encode_external_frame(self.next_frame()) + "\n"

    def readline(self):
        """Serial-compatible byte-oriented read of one complete frame."""
        return self.next_line().encode("utf-8")

    def lines(self, count):
        if type(count) is not int or count < 1:
            raise ValueError("count must be a positive integer")
        return tuple(self.next_line() for _ in range(count))
