import numpy as np
import pytest

from radiant.fdir import TimingHealthConfig, TimingHealthMonitor
from radiant.timing.synchronization import SynchronizationEstimate


def _sync(offset=0.0, scale=1.0):
    return SynchronizationEstimate(
        offset_ns=offset,
        rate_scale=scale,
        frequency_error_ppm=(scale - 1.0) * 1e6,
        rms_error_ns=0.0,
        peak_error_ns=0.0,
        sample_count=10,
    )


def test_healthy_timing_window_passes():
    ref = np.arange(0, 10_000_000, 1_000_000, dtype=np.int64)
    monitor = TimingHealthMonitor(_sync(), TimingHealthConfig(1000, 500, 10))
    report = monitor.inspect(ref, ref.copy())
    assert report.healthy
    assert not report.detected
    assert report.peak_residual_ns == 0


def test_clock_jump_is_detected_by_residuals():
    ref = np.arange(0, 10_000_000, 1_000_000, dtype=np.int64)
    local = ref.copy()
    local[5:] += 250_000
    report = TimingHealthMonitor(_sync(), TimingHealthConfig(50_000, 20_000, 100_000)).inspect(ref, local)
    kinds = {f.kind for f in report.findings}
    assert "peak_residual" in kinds
    assert "rms_residual" in kinds


def test_drift_excursion_is_detected():
    ref = np.arange(0, 20_000_000, 1_000_000, dtype=np.int64)
    local = np.rint(ref.astype(np.longdouble) * np.longdouble(1.0005)).astype(np.int64)
    report = TimingHealthMonitor(_sync(), TimingHealthConfig(1_000_000, 1_000_000, 100)).inspect(ref, local)
    assert any(f.kind == "drift_excursion" for f in report.findings)
    assert report.observed_drift_ppm == pytest.approx(500.0, abs=0.1)


def test_timestamp_freeze_is_detected_as_nonprogressing():
    ref = np.arange(0, 8_000_000, 1_000_000, dtype=np.int64)
    local = ref.copy()
    local[3:5] = local[3]
    report = TimingHealthMonitor(_sync(), TimingHealthConfig(2_000_000, 2_000_000, 1_000_000)).inspect(ref, local)
    assert any(f.kind == "nonprogressing_timestamp" for f in report.findings)


def test_baseline_offset_and_scale_are_corrected():
    ref = np.arange(0, 10_000_000, 1_000_000, dtype=np.int64)
    scale = 1.000025
    offset = 2500
    local = np.rint(offset + ref.astype(np.longdouble) * np.longdouble(scale)).astype(np.int64)
    report = TimingHealthMonitor(_sync(offset, scale), TimingHealthConfig(10, 10, 1)).inspect(ref, local)
    assert report.healthy
    assert report.peak_residual_ns <= 1


def test_config_rejects_invalid_thresholds():
    with pytest.raises(ValueError):
        TimingHealthConfig(max_abs_residual_ns=-1)
    with pytest.raises(ValueError):
        TimingHealthConfig(max_rms_residual_ns=float("inf"))
    with pytest.raises(ValueError):
        TimingHealthConfig(max_drift_ppm=-0.1)


def test_monitor_requires_synchronization_estimate():
    with pytest.raises(TypeError):
        TimingHealthMonitor(object())


def test_monitor_requires_valid_config():
    with pytest.raises(TypeError):
        TimingHealthMonitor(_sync(), object())


def test_inspect_rejects_bad_shapes_and_types():
    monitor = TimingHealthMonitor(_sync())
    with pytest.raises(ValueError):
        monitor.inspect([0], [0])
    with pytest.raises(ValueError):
        monitor.inspect(np.array([0, 1]), np.array([0]))
    with pytest.raises(ValueError):
        monitor.inspect(np.array([0.0, 1.0]), np.array([0, 1]))


def test_reference_must_strictly_increase():
    monitor = TimingHealthMonitor(_sync())
    with pytest.raises(ValueError):
        monitor.inspect(np.array([0, 1, 1], dtype=np.int64), np.array([0, 1, 2], dtype=np.int64))
