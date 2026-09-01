import math
import numpy as np
from radiant.stream import StreamCursor
from radiant.telemetry import ProcessedPacket


def lowpass_taps(sample_rate_hz, cutoff_hz=4000.0, num_taps=63):
    """Odd-length symmetric Hamming-windowed sinc, normalised for DC gain."""
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample rate must be positive and finite")
    if not math.isfinite(cutoff_hz) or not 0 < cutoff_hz < sample_rate_hz / 2:
        raise ValueError("cutoff must lie strictly between zero and Nyquist")
    if type(num_taps) is not int or num_taps < 3 or num_taps % 2 != 1:
        raise ValueError("num_taps must be an odd integer >= 3")
    n = np.arange(num_taps) - (num_taps - 1) / 2
    ratio = cutoff_hz / sample_rate_hz
    taps = 2 * ratio * np.sinc(2 * ratio * n) * np.hamming(num_taps)
    return taps / taps.sum()


class FIRPipeline:
    """Linear-phase FIR with per-channel state and clipping provenance.

    No decimation. Output sample indices/timestamps are unchanged. Group delay
    is metadata, not automatically subtracted from threshold event timestamps.
    """

    def __init__(self, taps, sample_rate_hz=50_000):
        taps = np.asarray(taps, dtype=np.float64)
        if (taps.ndim != 1 or not len(taps) or len(taps) % 2 != 1 or
                not np.all(np.isfinite(taps)) or
                not np.allclose(taps, taps[::-1], rtol=1e-12, atol=1e-15)):
            raise ValueError("taps must be a finite, odd-length, symmetric vector")
        if type(sample_rate_hz) is not int or not 1 <= sample_rate_hz <= 10**9:
            raise ValueError("sample rate must be an integer in [1, 1e9]")
        self._taps = taps.copy()
        self.sample_rate_hz = sample_rate_hz
        self.group_delay_samples = (len(taps) - 1) // 2
        self.reset()

    def reset(self):
        self._cursor = StreamCursor()
        self._history = None
        self._bad_history = None

    def process(self, packet):
        self._cursor.check(packet)
        if packet.sample_rate_hz != self.sample_rate_hz:
            raise ValueError("packet rate differs from filter design rate")
        size = len(self._taps) - 1
        channels = len(packet.channel_ids)
        history = np.zeros((size, channels)) if self._history is None else self._history
        bad_history = (np.ones((size, channels), dtype=bool) if self._bad_history is None
                       else self._bad_history)
        values = np.concatenate((history, packet.data.volts))
        bad = np.concatenate((bad_history, packet.data.clipped))
        volts = np.column_stack([np.convolve(values[:, ch], self._taps, mode="valid")
                                 for ch in range(channels)])
        valid = np.column_stack([np.convolve(bad[:, ch].astype(np.int64),
                                             np.ones(len(self._taps), dtype=np.int64),
                                             mode="valid") == 0 for ch in range(channels)])
        if not np.all(np.isfinite(volts)):
            raise ValueError("filter output overflow; state has not advanced")
        self._history = values[-size:].copy() if size else values[:0].copy()
        self._bad_history = bad[-size:].copy() if size else bad[:0].copy()
        self._cursor.commit(packet)
        return ProcessedPacket(packet, volts, valid, self.group_delay_samples)
