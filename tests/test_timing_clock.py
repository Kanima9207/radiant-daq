import numpy as np
import pytest

from radiant.timing import LocalClock


def test_ideal_clock_matches_stage1_sample_timestamp_convention():
    clock = LocalClock()
    stamps = clock.sample_timestamps(first_sample=3, sample_count=4, sample_rate_hz=50_000)
    expected = np.array([60_000, 80_000, 100_000, 120_000], dtype=np.int64)
    np.testing.assert_array_equal(stamps, expected)


def test_fixed_offset_is_applied_without_rate_error():
    clock = LocalClock(offset_ns=2_500)
    refs = np.array([0, 1_000_000, 2_000_000], dtype=np.int64)
    np.testing.assert_array_equal(clock.read(refs), refs + 2_500)


def test_positive_ppm_accumulates_expected_drift():
    clock = LocalClock(frequency_error_ppm=25.0)
    assert clock.read(1_000_000_000) == 1_000_025_000
    assert clock.read(10_000_000_000) == 10_000_250_000


def test_negative_ppm_accumulates_expected_drift():
    clock = LocalClock(frequency_error_ppm=-18.0)
    assert clock.read(1_000_000_000) == 999_982_000


def test_seeded_jitter_is_reproducible_and_resettable():
    refs = np.arange(20, dtype=np.int64) * 1_000_000
    a = LocalClock(jitter_std_ns=200.0, seed=7)
    b = LocalClock(jitter_std_ns=200.0, seed=7)
    first = a.read(refs)
    np.testing.assert_array_equal(first, b.read(refs))
    assert not np.array_equal(first, refs)
    a.reset()
    np.testing.assert_array_equal(a.read(refs), first)


def test_scalar_read_returns_python_integer():
    value = LocalClock(offset_ns=10).read(123)
    assert type(value) is int
    assert value == 133


def test_rejects_invalid_clock_configuration():
    for kwargs in (
        {"offset_ns": 1.5},
        {"frequency_error_ppm": np.inf},
        {"frequency_error_ppm": -1_000_000.0},
        {"jitter_std_ns": -1.0},
        {"seed": 2.5},
    ):
        with pytest.raises(ValueError):
            LocalClock(**kwargs)


def test_rejects_invalid_reference_and_sample_requests():
    clock = LocalClock()
    for bad in ([], [0.0, 1.0], [-1, 0], [2, 1]):
        with pytest.raises(ValueError):
            clock.read(bad)
    for args in ((-1, 1, 50_000), (0, 0, 50_000), (0, 1, 0)):
        with pytest.raises(ValueError):
            clock.sample_timestamps(*args)


def test_detects_signed_64_bit_overflow():
    clock = LocalClock(offset_ns=np.iinfo(np.int64).max)
    with pytest.raises(OverflowError):
        clock.read(1)
