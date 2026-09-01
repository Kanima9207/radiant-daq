import numpy as np
import pytest

from radiant.timing import (
    LocalClock,
    NetworkDelayModel,
    TimingExchange,
    estimate_exchange,
    estimate_synchronization,
    exchange_observation,
    simulate_exchange,
)


def test_symmetric_fixed_delay_recovers_offset():
    clock = LocalClock(offset_ns=12_000, frequency_error_ppm=0.0)
    network = NetworkDelayModel(forward_delay_ns=50_000, reverse_delay_ns=50_000)
    exchange = simulate_exchange(1_000_000, clock, network)
    estimate = estimate_exchange(exchange)
    assert estimate.offset_ns == pytest.approx(12_000.0)
    assert estimate.mean_path_delay_ns == pytest.approx(50_000.0)


def test_processing_residence_does_not_bias_symmetric_exchange():
    clock = LocalClock(offset_ns=-8_000, frequency_error_ppm=0.0)
    network = NetworkDelayModel(forward_delay_ns=20_000, reverse_delay_ns=20_000)
    exchange = simulate_exchange(2_000_000, clock, network, node_processing_ns=75_000)
    estimate = estimate_exchange(exchange)
    assert estimate.offset_ns == pytest.approx(-8_000.0)
    assert estimate.mean_path_delay_ns == pytest.approx(20_000.0)


def test_asymmetry_creates_half_asymmetry_offset_bias():
    clock = LocalClock(offset_ns=10_000, frequency_error_ppm=0.0)
    network = NetworkDelayModel(forward_delay_ns=70_000, reverse_delay_ns=30_000)
    exchange = simulate_exchange(5_000_000, clock, network)
    estimate = estimate_exchange(exchange)
    assert exchange.path_asymmetry_ns == 40_000
    assert estimate.offset_ns == pytest.approx(30_000.0)


def test_seeded_network_jitter_is_reproducible_after_reset():
    network = NetworkDelayModel(50_000, 50_000, jitter_std_ns=2_000, seed=123)
    first = [network.sample() for _ in range(8)]
    network.reset()
    second = [network.sample() for _ in range(8)]
    assert first == second


def test_network_delay_never_returns_negative_propagation():
    network = NetworkDelayModel(0, 0, jitter_std_ns=1_000_000, seed=4)
    for _ in range(20):
        fwd, rev = network.sample()
        assert fwd >= 0
        assert rev >= 0


def test_exchange_observations_support_affine_clock_fit():
    clock = LocalClock(offset_ns=25_000, frequency_error_ppm=25.0)
    network = NetworkDelayModel(40_000, 40_000)
    exchanges = [simulate_exchange(i * 1_000_000_000, clock, network)
                 for i in range(1, 11)]
    pairs = [exchange_observation(x) for x in exchanges]
    reference = np.array([p[0] for p in pairs], dtype=np.int64)
    local = np.array([p[1] for p in pairs], dtype=np.int64)
    estimate = estimate_synchronization(reference, local)
    assert estimate.frequency_error_ppm == pytest.approx(25.0, abs=0.01)
    assert estimate.offset_ns == pytest.approx(25_000.0, abs=2.0)


def test_jittered_exchanges_produce_bounded_fit_not_perfect_claim():
    clock = LocalClock(offset_ns=15_000, frequency_error_ppm=-18.0)
    network = NetworkDelayModel(50_000, 50_000, jitter_std_ns=3_000, seed=7)
    exchanges = [simulate_exchange(i * 500_000_000, clock, network)
                 for i in range(1, 41)]
    pairs = [exchange_observation(x) for x in exchanges]
    reference = np.array([p[0] for p in pairs], dtype=np.int64)
    local = np.array([p[1] for p in pairs], dtype=np.int64)
    estimate = estimate_synchronization(reference, local)
    assert estimate.frequency_error_ppm == pytest.approx(-18.0, abs=1.0)
    assert estimate.rms_error_ns > 0
    assert estimate.peak_error_ns > 0


def test_timing_exchange_properties():
    exchange = TimingExchange(100, 130, 150, 190, 30, 40)
    assert exchange.round_trip_ns == 90
    assert exchange.path_asymmetry_ns == -10


def test_invalid_network_configuration_rejected():
    with pytest.raises(ValueError):
        NetworkDelayModel(forward_delay_ns=-1)
    with pytest.raises(ValueError):
        NetworkDelayModel(jitter_std_ns=-1)
    with pytest.raises(ValueError):
        NetworkDelayModel(seed=1.5)


def test_invalid_exchange_arguments_rejected():
    clock = LocalClock()
    network = NetworkDelayModel()
    with pytest.raises(ValueError):
        simulate_exchange(-1, clock, network)
    with pytest.raises(ValueError):
        simulate_exchange(0, clock, network, node_processing_ns=-1)
    with pytest.raises(TypeError):
        simulate_exchange(0, object(), network)
    with pytest.raises(TypeError):
        simulate_exchange(0, clock, object())


def test_estimator_rejects_invalid_exchange_order():
    with pytest.raises(ValueError):
        estimate_exchange(TimingExchange(10, 20, 30, 5, 10, 10))
    with pytest.raises(ValueError):
        estimate_exchange(TimingExchange(10, 30, 20, 40, 10, 10))
    with pytest.raises(TypeError):
        estimate_exchange(object())
