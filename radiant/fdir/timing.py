"""Timing-health monitoring for FDIR-003.

Detection only: this module evaluates corrected timestamp residuals and local
clock progression. It does not retune, discipline, or recover a clock.
"""
from dataclasses import dataclass
import math
import numpy as np

from radiant.timing.synchronization import SynchronizationEstimate


@dataclass(frozen=True)
class TimingHealthConfig:
    max_abs_residual_ns: float = 50_000.0
    max_rms_residual_ns: float = 20_000.0
    max_drift_ppm: float = 100.0

    def __post_init__(self):
        for name in ("max_abs_residual_ns", "max_rms_residual_ns", "max_drift_ppm"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0:
                raise ValueError(f"{name} must be a finite nonnegative number")


@dataclass(frozen=True)
class TimingFinding:
    kind: str
    value: float
    threshold: float
    detail: str = ""


@dataclass(frozen=True)
class TimingHealthReport:
    healthy: bool
    rms_residual_ns: float
    peak_residual_ns: float
    observed_drift_ppm: float
    findings: tuple[TimingFinding, ...]

    @property
    def detected(self):
        return bool(self.findings)


class TimingHealthMonitor:
    """Monitor timing residuals against a previously estimated clock model."""

    def __init__(self, synchronization, config=TimingHealthConfig()):
        if not isinstance(synchronization, SynchronizationEstimate):
            raise TypeError("synchronization must be a SynchronizationEstimate")
        if not isinstance(config, TimingHealthConfig):
            raise TypeError("config must be a TimingHealthConfig")
        self.synchronization = synchronization
        self.config = config

    def inspect(self, reference_timestamps_ns, local_timestamps_ns):
        reference = np.asarray(reference_timestamps_ns)
        local = np.asarray(local_timestamps_ns)
        if (reference.ndim != 1 or local.ndim != 1 or reference.size < 2 or
                reference.shape != local.shape):
            raise ValueError("timestamps must be equal-length 1-D arrays with at least two samples")
        if not np.issubdtype(reference.dtype, np.integer) or not np.issubdtype(local.dtype, np.integer):
            raise ValueError("timestamps must contain integers")
        reference = reference.astype(np.int64, copy=False)
        local = local.astype(np.int64, copy=False)
        if np.any(np.diff(reference) <= 0):
            raise ValueError("reference timestamps must be strictly increasing")

        findings = []
        local_delta = np.diff(local)
        if np.any(local_delta <= 0):
            findings.append(TimingFinding(
                "nonprogressing_timestamp", float(np.min(local_delta)), 0.0,
                "local timestamps repeated or moved backwards",
            ))

        corrected = np.asarray(self.synchronization.correct(local), dtype=np.int64)
        residual = corrected.astype(np.longdouble) - reference.astype(np.longdouble)
        rms = float(np.sqrt(np.mean(residual * residual)))
        peak = float(np.max(np.abs(residual)))

        if peak > self.config.max_abs_residual_ns:
            findings.append(TimingFinding(
                "peak_residual", peak, float(self.config.max_abs_residual_ns),
                "corrected timestamp peak residual exceeds threshold",
            ))
        if rms > self.config.max_rms_residual_ns:
            findings.append(TimingFinding(
                "rms_residual", rms, float(self.config.max_rms_residual_ns),
                "corrected timestamp RMS residual exceeds threshold",
            ))

        # Estimate rate error over the observation window without fitting away
        # the anomaly. Compare observed local/reference span ratio with the
        # baseline rate scale from TIMING-002.
        ref_span = int(reference[-1]) - int(reference[0])
        local_span = int(local[-1]) - int(local[0])
        if ref_span <= 0:
            raise ValueError("reference timestamp span must be positive")
        observed_scale = np.longdouble(local_span) / np.longdouble(ref_span)
        baseline_scale = np.longdouble(self.synchronization.rate_scale)
        drift_ppm = float((observed_scale / baseline_scale - 1) * np.longdouble(1e6))
        if abs(drift_ppm) > self.config.max_drift_ppm:
            findings.append(TimingFinding(
                "drift_excursion", abs(drift_ppm), float(self.config.max_drift_ppm),
                f"observed rate differs from synchronized baseline by {drift_ppm:.6g} ppm",
            ))

        return TimingHealthReport(
            healthy=not findings,
            rms_residual_ns=rms,
            peak_residual_ns=peak,
            observed_drift_ppm=drift_ppm,
            findings=tuple(findings),
        )
