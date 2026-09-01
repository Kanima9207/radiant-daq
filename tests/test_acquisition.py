import numpy as np
import pytest
from radiant.acquisition import ADC, AcquisitionEngine


def test_adc_transfer_and_clipping():
    result = ADC(bits=2, v_min=-2, v_max=2).convert([-3, -2, -1, 0, 1, 2, 3])
    np.testing.assert_array_equal(result.codes, [0, 0, 1, 2, 3, 3, 3])
    np.testing.assert_array_equal(result.volts, [-1.5, -1.5, -.5, .5, 1.5, 1.5, 1.5])
    np.testing.assert_array_equal(result.clipped, [True, False, False, False, False, True, True])


def test_quantisation_error():
    adc = ADC()
    values = np.random.default_rng(42).uniform(-10, 10, (5000, 8))
    result = adc.convert(values)
    assert np.max(np.abs(values - result.volts)) <= adc.lsb / 2 + 1e-14
    assert not result.clipped.any()
    assert adc.lsb == 20 / 65536


@pytest.mark.parametrize("kwargs", [{"bits": 0}, {"bits": True}, {"bits": 25},
                                     {"v_min": 10}, {"v_max": float("inf")}])
def test_invalid_adc_config(kwargs):
    with pytest.raises(ValueError):
        ADC(**kwargs)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_rejected(value):
    with pytest.raises(ValueError):
        ADC().convert([value])


def test_eight_channels_and_packet_continuity():
    engine = AcquisitionEngine()
    a = engine.acquire(np.zeros((5000, 8)))
    b = engine.acquire(np.zeros((13, 8)))
    assert a.channel_ids == tuple(range(8))
    assert a.data.codes.shape == (5000, 8)
    assert (a.sequence, b.sequence, b.first_sample) == (0, 1, 5000)
    assert b.timestamps_ns[0] == 100_000_000
    assert b.timestamps_ns[0] - a.timestamps_ns[-1] == 20_000


def test_fractional_period_does_not_accumulate_rounding():
    engine = AcquisitionEngine(sample_rate_hz=3, channels=1)
    a = engine.acquire(np.zeros((2, 1)))
    b = engine.acquire(np.zeros((2, 1)))
    np.testing.assert_array_equal(np.concatenate([a.timestamps_ns, b.timestamps_ns]),
                                  [0, 333333333, 666666666, 1000000000])


@pytest.mark.parametrize("bad", [np.zeros((2, 7)), np.zeros((0, 8)),
                                  np.zeros(8), np.full((2, 8), np.nan)])
def test_rejection_preserves_state(bad):
    engine = AcquisitionEngine()
    with pytest.raises(ValueError):
        engine.acquire(bad)
    packet = engine.acquire(np.zeros((1, 8)))
    assert (packet.sequence, packet.first_sample, packet.timestamps_ns[0]) == (0, 0, 0)


@pytest.mark.parametrize("kwargs", [{"sample_rate_hz": 0}, {"sample_rate_hz": 1.5},
                                     {"channels": 0}, {"channels": True}])
def test_invalid_engine_config(kwargs):
    with pytest.raises(ValueError):
        AcquisitionEngine(**kwargs)
