import numpy as np
import pytest

from radiant.timing import LocalClock, estimate_synchronization, synchronization_error


def test_exact_affine_clock_is_recovered():
    reference = np.arange(0, 10_000_000_001, 1_000_000_000, dtype=np.int64)
    clock = LocalClock(offset_ns=250_000, frequency_error_ppm=25.0)
    local = clock.read(reference)
    estimate = estimate_synchronization(reference, local)
    assert abs(estimate.offset_ns - 250_000) < 1.0
    assert abs(estimate.frequency_error_ppm - 25.0) < 1e-6
    assert estimate.rms_error_ns < 1.0
    corrected = estimate.correct(local)
    np.testing.assert_array_equal(corrected, reference)


def test_negative_frequency_error_is_recovered():
    reference = np.arange(0, 8_000_000_001, 500_000_000, dtype=np.int64)
    local = LocalClock(offset_ns=-90_000, frequency_error_ppm=-18.0).read(reference)
    estimate = estimate_synchronization(reference, local)
    assert abs(estimate.offset_ns + 90_000) < 1.0
    assert abs(estimate.frequency_error_ppm + 18.0) < 1e-6


def test_jittered_clock_correction_reduces_rms_error():
    reference = np.arange(0, 20_000_000_001, 100_000_000, dtype=np.int64)
    local = LocalClock(offset_ns=700_000, frequency_error_ppm=32.0,
                       jitter_std_ns=800.0, seed=4).read(reference)
    before = local - reference
    estimate = estimate_synchronization(reference, local)
    after = synchronization_error(reference, estimate.correct(local))
    assert np.sqrt(np.mean(after.astype(float) ** 2)) < np.sqrt(np.mean(before.astype(float) ** 2)) / 100
    assert abs(estimate.frequency_error_ppm - 32.0) < 0.1
    assert estimate.rms_error_ns < 2_000


def test_two_nodes_correct_back_to_same_reference():
    reference = np.arange(0, 12_000_000_001, 250_000_000, dtype=np.int64)
    a = LocalClock(offset_ns=150_000, frequency_error_ppm=25.0).read(reference)
    b = LocalClock(offset_ns=-220_000, frequency_error_ppm=-18.0).read(reference)
    a_fit = estimate_synchronization(reference, a)
    b_fit = estimate_synchronization(reference, b)
    np.testing.assert_array_equal(a_fit.correct(a), reference)
    np.testing.assert_array_equal(b_fit.correct(b), reference)
    np.testing.assert_array_equal(a_fit.correct(a), b_fit.correct(b))


def test_scalar_correction_is_supported():
    reference = np.array([0, 1_000_000_000, 2_000_000_000], dtype=np.int64)
    local = LocalClock(offset_ns=1234, frequency_error_ppm=10).read(reference)
    estimate = estimate_synchronization(reference, local)
    assert estimate.correct(int(local[1])) == int(reference[1])


@pytest.mark.parametrize("reference, local", [
    ([0], [0]),
    ([0, 1], [0]),
    ([[0, 1]], [0, 1]),
    ([0.0, 1.0], [0, 1]),
    ([0, 1], [0.0, 1.0]),
    ([0, 0], [0, 1]),
    ([0, 1], [1, 1]),
])
def test_bad_estimator_inputs(reference, local):
    with pytest.raises(ValueError):
        estimate_synchronization(np.asarray(reference), np.asarray(local))


def test_synchronization_error_reports_signed_residual():
    reference = np.array([10, 20, 30], dtype=np.int64)
    corrected = np.array([12, 19, 30], dtype=np.int64)
    np.testing.assert_array_equal(synchronization_error(reference, corrected), [2, -1, 0])


def test_synchronization_error_rejects_mismatched_shape():
    with pytest.raises(ValueError):
        synchronization_error(np.array([1, 2], dtype=np.int64),
                              np.array([1], dtype=np.int64))
