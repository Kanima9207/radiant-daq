import numpy as np
import pytest

from radiant.acquisition import ADC
from radiant.faults import FaultEvent, SensorFaultInjector


def test_bias_fault_applies_only_inside_interval_and_channel():
    samples = np.zeros((10, 2))
    event = FaultEvent(1, "bias", 1, 3, 7, magnitude_volts=1.25)
    result = SensorFaultInjector([event]).apply(samples)
    np.testing.assert_allclose(result.samples[3:7, 1], 1.25)
    np.testing.assert_allclose(result.samples[:3, 1], 0.0)
    np.testing.assert_allclose(result.samples[7:, 1], 0.0)
    assert np.all(result.fault_ids[3:7, 1] == 1)
    assert not np.any(result.active[:, 0])


def test_drift_uses_absolute_fault_elapsed_samples():
    samples = np.zeros((5, 1))
    event = FaultEvent(2, "drift", 0, 100, 110, slope_volts_per_sample=0.1)
    result = SensorFaultInjector([event]).apply(samples, first_sample=103)
    np.testing.assert_allclose(result.samples[:, 0], [0.3, 0.4, 0.5, 0.6, 0.7])


def test_stuck_fault_overwrites_signal():
    samples = np.arange(8, dtype=float).reshape(4, 2)
    event = FaultEvent(3, "stuck", 0, 1, 4, stuck_value_volts=-2.5)
    result = SensorFaultInjector([event]).apply(samples)
    np.testing.assert_allclose(result.samples[1:4, 0], -2.5)
    np.testing.assert_allclose(result.samples[:, 1], samples[:, 1])


def test_noise_is_reproducible_and_chunk_invariant():
    event = FaultEvent(4, "noise", 0, 2, 18, noise_std_volts=0.5)
    injector = SensorFaultInjector([event], seed=17)
    whole = injector.apply(np.zeros((20, 1)), first_sample=0)
    a = injector.apply(np.zeros((7, 1)), first_sample=0)
    b = injector.apply(np.zeros((13, 1)), first_sample=7)
    combined = np.concatenate([a.samples, b.samples], axis=0)
    np.testing.assert_array_equal(combined, whole.samples)
    assert np.std(whole.samples[2:18, 0]) > 0


def test_saturation_fault_drives_real_adc_clipping_path():
    samples = np.zeros((6, 1))
    event = FaultEvent(5, "saturation", 0, 2, 5, saturation_value_volts=12.0)
    injected = SensorFaultInjector([event]).apply(samples)
    adc_result = ADC(bits=16, v_min=-10.0, v_max=10.0).convert(injected.samples)
    np.testing.assert_array_equal(adc_result.clipped[:, 0], [False, False, True, True, True, False])
    assert np.all(injected.fault_ids[2:5, 0] == 5)


def test_custom_channel_ids_are_respected():
    samples = np.zeros((4, 2))
    event = FaultEvent(6, "bias", 7, 0, 4, magnitude_volts=3.0)
    result = SensorFaultInjector([event]).apply(samples, channel_ids=(4, 7))
    np.testing.assert_allclose(result.samples[:, 0], 0.0)
    np.testing.assert_allclose(result.samples[:, 1], 3.0)


def test_events_for_absent_channels_do_not_modify_chunk():
    samples = np.ones((3, 1))
    event = FaultEvent(7, "bias", 9, 0, 3, magnitude_volts=10.0)
    result = SensorFaultInjector([event]).apply(samples, channel_ids=(0,))
    np.testing.assert_array_equal(result.samples, samples)
    assert not np.any(result.active)


def test_result_copies_input_and_ground_truth_arrays():
    samples = np.zeros((3, 1))
    result = SensorFaultInjector().apply(samples)
    samples[:] = 9.0
    np.testing.assert_allclose(result.samples, 0.0)
    active = result.active
    active[:] = True
    assert not np.any(result.active)


def test_rejects_overlapping_faults_on_same_channel():
    a = FaultEvent(1, "bias", 0, 0, 5, magnitude_volts=1.0)
    b = FaultEvent(2, "stuck", 0, 4, 8, stuck_value_volts=0.0)
    with pytest.raises(ValueError):
        SensorFaultInjector([a, b])


def test_allows_overlapping_faults_on_different_channels():
    a = FaultEvent(1, "bias", 0, 0, 5, magnitude_volts=1.0)
    b = FaultEvent(2, "stuck", 1, 2, 4, stuck_value_volts=0.0)
    SensorFaultInjector([a, b])


def test_rejects_duplicate_fault_ids():
    a = FaultEvent(1, "bias", 0, 0, 2, magnitude_volts=1.0)
    b = FaultEvent(1, "bias", 1, 0, 2, magnitude_volts=1.0)
    with pytest.raises(ValueError):
        SensorFaultInjector([a, b])


def test_rejects_invalid_fault_configuration():
    bad_kwargs = (
        {"fault_id": 0, "kind": "bias", "channel_id": 0, "start_sample": 0, "stop_sample": 1},
        {"fault_id": 1, "kind": "unknown", "channel_id": 0, "start_sample": 0, "stop_sample": 1},
        {"fault_id": 1, "kind": "bias", "channel_id": -1, "start_sample": 0, "stop_sample": 1},
        {"fault_id": 1, "kind": "bias", "channel_id": 0, "start_sample": 2, "stop_sample": 2},
        {"fault_id": 1, "kind": "noise", "channel_id": 0, "start_sample": 0, "stop_sample": 1,
         "noise_std_volts": -1.0},
    )
    for kwargs in bad_kwargs:
        with pytest.raises(ValueError):
            FaultEvent(**kwargs)


def test_rejects_invalid_apply_inputs():
    injector = SensorFaultInjector()
    for bad in (np.zeros(3), np.zeros((0, 1)), np.array([[np.nan]])):
        with pytest.raises(ValueError):
            injector.apply(bad)
    with pytest.raises(ValueError):
        injector.apply(np.zeros((2, 1)), first_sample=-1)
    with pytest.raises(ValueError):
        injector.apply(np.zeros((2, 2)), channel_ids=(0, 0))
