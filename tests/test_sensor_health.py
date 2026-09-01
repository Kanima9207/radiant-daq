import numpy as np
import pytest

from radiant.fdir import SensorHealthConfig, SensorHealthMonitor


def cfg():
    return SensorHealthConfig(
        expected_mean_v=0.0,
        bias_threshold_v=0.25,
        drift_threshold_v_per_sample=1e-3,
        stuck_std_threshold_v=5e-3,
        noise_std_threshold_v=0.15,
        min_samples=32,
    )


def test_healthy_sine_window_is_not_flagged():
    x = np.arange(128)
    samples = (0.1 * np.sin(2 * np.pi * x / 16))[:, None]
    report = SensorHealthMonitor(cfg()).inspect(samples)
    assert not report.detected
    assert report.findings == ()


def test_bias_fault_is_detected():
    x = np.arange(128)
    samples = (0.75 + 0.05 * np.sin(2 * np.pi * x / 16))[:, None]
    report = SensorHealthMonitor(cfg()).inspect(samples)
    assert any(f.kind == "bias" for f in report.findings)


def test_drift_fault_is_detected():
    x = np.arange(128, dtype=float)
    samples = (0.002 * x + 0.05 * np.sin(2 * np.pi * x / 16))[:, None]
    report = SensorHealthMonitor(cfg()).inspect(samples)
    assert any(f.kind == "drift" for f in report.findings)


def test_stuck_fault_is_detected_and_not_double_classified_as_bias():
    samples = np.full((128, 1), 1.2)
    report = SensorHealthMonitor(cfg()).inspect(samples)
    kinds = {f.kind for f in report.findings}
    assert kinds == {"stuck"}


def test_excess_noise_is_detected_after_detrending():
    rng = np.random.default_rng(7)
    samples = rng.normal(0.0, 0.25, size=(256, 1))
    report = SensorHealthMonitor(cfg()).inspect(samples)
    assert any(f.kind == "noise" for f in report.findings)


def test_custom_channel_ids_and_per_channel_configuration():
    x = np.arange(128)
    samples = np.column_stack([
        0.1 * np.sin(2 * np.pi * x / 16),
        0.4 + 0.1 * np.sin(2 * np.pi * x / 16),
    ])
    strict = cfg()
    relaxed = SensorHealthConfig(bias_threshold_v=0.5, min_samples=32)
    monitor = SensorHealthMonitor(strict, per_channel={7: relaxed})
    report = monitor.inspect(samples, channel_ids=(3, 7))
    assert [c.channel_id for c in report.channels] == [3, 7]
    assert all(c.healthy for c in report.channels)


def test_short_window_is_rejected():
    with pytest.raises(ValueError, match="requires at least"):
        SensorHealthMonitor(cfg()).inspect(np.zeros((16, 1)))


def test_nonfinite_samples_are_rejected():
    samples = np.zeros((64, 1))
    samples[10, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        SensorHealthMonitor(cfg()).inspect(samples)


def test_duplicate_channel_ids_are_rejected():
    with pytest.raises(ValueError, match="uniquely"):
        SensorHealthMonitor(cfg()).inspect(np.zeros((64, 2)), channel_ids=(1, 1))


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValueError):
        SensorHealthConfig(noise_std_threshold_v=-1.0)
