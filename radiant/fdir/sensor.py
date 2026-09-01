"""Explainable sensor-health monitoring for FDIR-002.

This module detects simple sensor faults from finite sample windows using
transparent statistical features. Detection only: it does not repair samples,
replace channels, or alter acquisition state.
"""
from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class SensorHealthConfig:
    expected_mean_v: float = 0.0
    bias_threshold_v: float = 0.25
    drift_threshold_v_per_sample: float = 1e-3
    stuck_std_threshold_v: float = 5e-3
    noise_std_threshold_v: float = 0.15
    min_samples: int = 32

    def __post_init__(self):
        for name in (
            "expected_mean_v", "bias_threshold_v", "drift_threshold_v_per_sample",
            "stuck_std_threshold_v", "noise_std_threshold_v",
        ):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
        if self.bias_threshold_v < 0 or self.drift_threshold_v_per_sample < 0:
            raise ValueError("bias and drift thresholds must be nonnegative")
        if self.stuck_std_threshold_v < 0 or self.noise_std_threshold_v < 0:
            raise ValueError("stuck and noise thresholds must be nonnegative")
        if type(self.min_samples) is not int or self.min_samples < 3:
            raise ValueError("min_samples must be an integer >= 3")


@dataclass(frozen=True)
class SensorFinding:
    kind: str
    channel_id: int
    value: float
    threshold: float
    detail: str = ""


@dataclass(frozen=True)
class ChannelHealth:
    channel_id: int
    mean_v: float
    std_v: float
    drift_v_per_sample: float
    residual_std_v: float
    findings: tuple[SensorFinding, ...]

    @property
    def healthy(self):
        return not self.findings


@dataclass(frozen=True)
class SensorHealthReport:
    channels: tuple[ChannelHealth, ...]

    @property
    def detected(self):
        return any(not channel.healthy for channel in self.channels)

    @property
    def findings(self):
        return tuple(finding for channel in self.channels for finding in channel.findings)


class SensorHealthMonitor:
    """Window-based detector for bias, drift, stuck and excess-noise faults."""

    def __init__(self, config=None, per_channel=None):
        self.config = SensorHealthConfig() if config is None else config
        if not isinstance(self.config, SensorHealthConfig):
            raise TypeError("config must be a SensorHealthConfig")
        self.per_channel = {} if per_channel is None else dict(per_channel)
        if any(type(channel_id) is not int or channel_id < 0 for channel_id in self.per_channel):
            raise ValueError("per_channel keys must be nonnegative integers")
        if any(not isinstance(cfg, SensorHealthConfig) for cfg in self.per_channel.values()):
            raise TypeError("per_channel values must be SensorHealthConfig objects")

    def inspect(self, samples, channel_ids=None):
        values = np.asarray(samples, dtype=np.float64)
        if values.ndim != 2 or values.shape[0] == 0 or values.shape[1] == 0:
            raise ValueError("samples must be a nonempty 2-D array")
        if not np.all(np.isfinite(values)):
            raise ValueError("samples must be finite")
        if channel_ids is None:
            channel_ids = tuple(range(values.shape[1]))
        else:
            channel_ids = tuple(channel_ids)
        if len(channel_ids) != values.shape[1] or len(set(channel_ids)) != len(channel_ids):
            raise ValueError("channel_ids must uniquely match sample columns")
        if any(type(channel_id) is not int or channel_id < 0 for channel_id in channel_ids):
            raise ValueError("channel_ids must contain nonnegative integers")

        reports = []
        x = np.arange(values.shape[0], dtype=np.float64)
        x_centered = x - x.mean()
        denominator = float(np.dot(x_centered, x_centered))

        for column, channel_id in enumerate(channel_ids):
            cfg = self.per_channel.get(channel_id, self.config)
            if values.shape[0] < cfg.min_samples:
                raise ValueError(
                    f"channel window has {values.shape[0]} samples; requires at least {cfg.min_samples}"
                )
            y = values[:, column]
            mean_v = float(np.mean(y))
            std_v = float(np.std(y))
            slope = float(np.dot(x_centered, y - mean_v) / denominator)
            fitted = mean_v + slope * x_centered
            residual_std = float(np.std(y - fitted))
            findings = []

            # Stuck is evaluated first because a constant biased channel is more
            # specifically described as stuck than as a simple mean-offset fault.
            if std_v <= cfg.stuck_std_threshold_v:
                findings.append(SensorFinding(
                    "stuck", channel_id, std_v, cfg.stuck_std_threshold_v,
                    "window variance is at or below the stuck-sensor threshold",
                ))
            else:
                if abs(slope) >= cfg.drift_threshold_v_per_sample:
                    findings.append(SensorFinding(
                        "drift", channel_id, slope, cfg.drift_threshold_v_per_sample,
                        "absolute linear trend exceeds the configured drift threshold",
                    ))
                if abs(mean_v - cfg.expected_mean_v) >= cfg.bias_threshold_v:
                    findings.append(SensorFinding(
                        "bias", channel_id, mean_v - cfg.expected_mean_v,
                        cfg.bias_threshold_v,
                        "window mean differs from the configured nominal mean",
                    ))
                if residual_std >= cfg.noise_std_threshold_v:
                    findings.append(SensorFinding(
                        "noise", channel_id, residual_std, cfg.noise_std_threshold_v,
                        "detrended residual standard deviation exceeds the noise threshold",
                    ))

            reports.append(ChannelHealth(
                channel_id, mean_v, std_v, slope, residual_std, tuple(findings)
            ))

        return SensorHealthReport(tuple(reports))
