from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class SynchronizationEstimate:
    """Affine mapping from local clock time back to reference time."""

    offset_ns: float
    rate_scale: float
    frequency_error_ppm: float
    rms_error_ns: float
    peak_error_ns: float
    sample_count: int

    def correct(self, local_timestamps_ns):
        values = np.asarray(local_timestamps_ns)
        scalar = np.isscalar(local_timestamps_ns)
        if scalar:
            values = np.asarray([local_timestamps_ns])
        if values.ndim != 1 or values.size == 0 or not np.issubdtype(values.dtype, np.integer):
            raise ValueError("local_timestamps_ns must be an integer scalar or nonempty 1-D integer array")
        corrected = (values.astype(np.longdouble) - np.longdouble(self.offset_ns)) / np.longdouble(self.rate_scale)
        rounded = np.rint(corrected)
        limit = np.iinfo(np.int64)
        if np.any(rounded < limit.min) or np.any(rounded > limit.max):
            raise OverflowError("corrected timestamp exceeds signed 64-bit nanoseconds")
        result = rounded.astype(np.int64)
        return int(result[0]) if scalar else result


def estimate_synchronization(reference_timestamps_ns, local_timestamps_ns):
    """Estimate local = offset + rate_scale * reference by least squares.

    Inputs are paired observations of the same physical instants expressed in
    the reference and local clock domains. At least two distinct reference
    timestamps are required. Network delay is intentionally outside TIMING-002.
    """
    reference = np.asarray(reference_timestamps_ns)
    local = np.asarray(local_timestamps_ns)
    if reference.ndim != 1 or local.ndim != 1 or reference.size < 2 or reference.size != local.size:
        raise ValueError("reference and local timestamps must be equal-length 1-D arrays with at least two samples")
    if not np.issubdtype(reference.dtype, np.integer) or not np.issubdtype(local.dtype, np.integer):
        raise ValueError("timestamps must contain integers")
    reference = reference.astype(np.int64, copy=False)
    local = local.astype(np.int64, copy=False)
    if np.any(np.diff(reference) <= 0):
        raise ValueError("reference timestamps must be strictly increasing")
    if np.any(np.diff(local) <= 0):
        raise ValueError("local timestamps must be strictly increasing")

    # Center the regression to avoid loss of precision for large nanosecond values.
    x = reference.astype(np.longdouble)
    y = local.astype(np.longdouble)
    x0 = np.mean(x)
    y0 = np.mean(y)
    dx = x - x0
    denominator = np.sum(dx * dx)
    if denominator == 0:
        raise ValueError("reference timestamps must span more than one instant")
    rate_scale = np.sum(dx * (y - y0)) / denominator
    if not math.isfinite(float(rate_scale)) or rate_scale <= 0:
        raise ValueError("estimated clock rate must be positive and finite")
    offset = y0 - rate_scale * x0

    predicted = offset + rate_scale * x
    residual = y - predicted
    rms = np.sqrt(np.mean(residual * residual))
    peak = np.max(np.abs(residual))
    ppm = (rate_scale - 1) * 1e6

    return SynchronizationEstimate(
        offset_ns=float(offset),
        rate_scale=float(rate_scale),
        frequency_error_ppm=float(ppm),
        rms_error_ns=float(rms),
        peak_error_ns=float(peak),
        sample_count=int(reference.size),
    )


def synchronization_error(reference_timestamps_ns, corrected_timestamps_ns):
    """Return signed nanosecond error after correction."""
    reference = np.asarray(reference_timestamps_ns)
    corrected = np.asarray(corrected_timestamps_ns)
    if reference.ndim != 1 or corrected.ndim != 1 or reference.shape != corrected.shape or reference.size == 0:
        raise ValueError("reference and corrected timestamps must be nonempty equal-length 1-D arrays")
    if not np.issubdtype(reference.dtype, np.integer) or not np.issubdtype(corrected.dtype, np.integer):
        raise ValueError("timestamps must contain integers")
    return corrected.astype(np.int64) - reference.astype(np.int64)
