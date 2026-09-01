import math
import numpy as np


class LocalClock:
    """Deterministic simulated node clock referenced to ideal nanosecond time.

    The model applies a fixed initial offset, constant fractional frequency
    error in parts per million, and optional zero-mean Gaussian timestamp
    jitter generated from a seeded RNG. It models simulated clock readings;
    it does not use or measure the host wall clock.
    """

    def __init__(self, offset_ns=0, frequency_error_ppm=0.0, jitter_std_ns=0.0, seed=0):
        if type(offset_ns) is not int:
            raise ValueError("offset_ns must be an integer")
        if not isinstance(frequency_error_ppm, (int, float)) or not math.isfinite(frequency_error_ppm):
            raise ValueError("frequency_error_ppm must be finite")
        if 1.0 + float(frequency_error_ppm) * 1e-6 <= 0:
            raise ValueError("frequency_error_ppm must keep clock rate positive")
        if not isinstance(jitter_std_ns, (int, float)) or not math.isfinite(jitter_std_ns) or jitter_std_ns < 0:
            raise ValueError("jitter_std_ns must be finite and nonnegative")
        if seed is not None and type(seed) is not int:
            raise ValueError("seed must be an integer or None")
        self.offset_ns = offset_ns
        self.frequency_error_ppm = float(frequency_error_ppm)
        self.jitter_std_ns = float(jitter_std_ns)
        self.seed = seed
        self._rng = np.random.default_rng(seed)

    @property
    def rate_scale(self):
        return 1.0 + self.frequency_error_ppm * 1e-6

    def reset(self):
        """Reset jitter generation to the original seeded state."""
        self._rng = np.random.default_rng(self.seed)

    def read(self, reference_ns):
        """Return local clock readings for scalar or 1-D ideal reference time."""
        scalar = np.isscalar(reference_ns)
        refs = np.asarray([reference_ns] if scalar else reference_ns)
        if refs.ndim != 1 or refs.size == 0 or not np.issubdtype(refs.dtype, np.integer):
            raise ValueError("reference_ns must be an integer scalar or nonempty 1-D integer array")
        refs = refs.astype(np.int64, copy=False)
        if np.any(refs < 0):
            raise ValueError("reference_ns must be nonnegative")
        if refs.size > 1 and np.any(np.diff(refs) < 0):
            raise ValueError("reference_ns must be nondecreasing")

        # Long-double arithmetic keeps the ppm model stable for long simulated runs.
        nominal = refs.astype(np.longdouble) * np.longdouble(self.rate_scale)
        local = np.rint(nominal).astype(object)
        local = np.array([int(v) + self.offset_ns for v in local], dtype=object)
        if self.jitter_std_ns:
            jitter = np.rint(self._rng.normal(0.0, self.jitter_std_ns, refs.size)).astype(np.int64)
            local = np.array([int(v) + int(j) for v, j in zip(local, jitter)], dtype=object)

        limit = np.iinfo(np.int64)
        if any(v < limit.min or v > limit.max for v in local):
            raise OverflowError("local clock reading exceeds signed 64-bit nanoseconds")
        result = np.asarray(local, dtype=np.int64)
        return int(result[0]) if scalar else result

    def sample_timestamps(self, first_sample, sample_count, sample_rate_hz):
        """Generate local timestamps using Stage-1 sample-index convention."""
        if type(first_sample) is not int or first_sample < 0:
            raise ValueError("first_sample must be a nonnegative integer")
        if type(sample_count) is not int or sample_count < 1:
            raise ValueError("sample_count must be a positive integer")
        if type(sample_rate_hz) is not int or not 1 <= sample_rate_hz <= 10**9:
            raise ValueError("sample_rate_hz must be an integer in [1, 1e9]")
        end = first_sample + sample_count
        refs = np.fromiter((i * 10**9 // sample_rate_hz for i in range(first_sample, end)),
                           dtype=np.int64)
        return self.read(refs)
