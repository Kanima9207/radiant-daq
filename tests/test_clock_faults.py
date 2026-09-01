import numpy as np
import pytest

from radiant.faults import ClockFaultEvent, FaultedClock
from radiant.timing.clock import LocalClock


def test_jump_fault_adds_constant_offset_in_interval():
    clock = FaultedClock(LocalClock(), [ClockFaultEvent(1, "jump", 100, 300, 50)])
    refs = np.array([0, 100, 200, 300], dtype=np.int64)
    result = clock.read_with_truth(refs)
    assert np.array_equal(result.timestamps_ns, [0, 150, 250, 300])
    assert np.array_equal(result.fault_ids, [0, 1, 1, 0])


def test_persistent_jump_applies_after_start():
    clock = FaultedClock(LocalClock(), [ClockFaultEvent(2, "jump", 100, None, -25)])
    refs = np.array([99, 100, 200], dtype=np.int64)
    assert np.array_equal(clock.read(refs), [99, 75, 175])


def test_drift_change_accumulates_phase_error():
    clock = FaultedClock(LocalClock(), [ClockFaultEvent(3, "drift_change", 0, None, 1000.0)])
    refs = np.array([0, 1_000_000, 2_000_000], dtype=np.int64)
    assert np.array_equal(clock.read(refs), [0, 1_001_000, 2_002_000])


def test_finite_drift_change_holds_accumulated_phase_after_end():
    clock = FaultedClock(LocalClock(), [ClockFaultEvent(4, "drift_change", 0, 1_000_000, 1000.0)])
    refs = np.array([0, 500_000, 1_000_000, 2_000_000], dtype=np.int64)
    assert np.array_equal(clock.read(refs), [0, 500_500, 1_001_000, 2_001_000])


def test_freeze_holds_timestamp_then_resumes_with_lost_time():
    clock = FaultedClock(LocalClock(), [ClockFaultEvent(5, "freeze", 100, 300, 0)])
    refs = np.array([0, 100, 200, 299, 300, 400], dtype=np.int64)
    assert np.array_equal(clock.read(refs), [0, 100, 100, 100, 100, 200])


def test_scalar_read_returns_scalar_and_truth_id():
    clock = FaultedClock(LocalClock(), [ClockFaultEvent(6, "jump", 10, None, 5)])
    stamp, truth = clock.read_with_truth(20)
    assert stamp == 25
    assert truth == 6
    assert isinstance(stamp, int)
    assert isinstance(truth, int)


def test_base_clock_offset_and_drift_are_preserved():
    base = LocalClock(offset_ns=20, frequency_error_ppm=100.0)
    clock = FaultedClock(base, [ClockFaultEvent(7, "jump", 1_000_000, None, 30)])
    assert clock.read(2_000_000) == base.read(2_000_000) + 30


def test_faulted_clock_reset_replays_seeded_jitter():
    base = LocalClock(jitter_std_ns=5.0, seed=123)
    clock = FaultedClock(base, [ClockFaultEvent(8, "jump", 100, None, 10)])
    refs = np.arange(10, dtype=np.int64) * 100
    first = clock.read(refs)
    clock.reset()
    second = clock.read(refs)
    assert np.array_equal(first, second)


def test_overlapping_fault_intervals_are_rejected():
    events = [
        ClockFaultEvent(1, "jump", 100, 300, 10),
        ClockFaultEvent(2, "freeze", 200, 400, 0),
    ]
    with pytest.raises(ValueError, match="must not overlap"):
        FaultedClock(LocalClock(), events)


def test_invalid_clock_fault_definitions_are_rejected():
    with pytest.raises(ValueError):
        ClockFaultEvent(0, "jump", 0, None, 1)
    with pytest.raises(ValueError):
        ClockFaultEvent(1, "unknown", 0, None, 1)
    with pytest.raises(ValueError):
        ClockFaultEvent(1, "freeze", 0, None, 0)
    with pytest.raises(ValueError):
        ClockFaultEvent(1, "jump", -1, None, 1)


def test_invalid_reference_inputs_are_rejected():
    clock = FaultedClock(LocalClock())
    with pytest.raises(ValueError):
        clock.read(np.array([], dtype=np.int64))
    with pytest.raises(ValueError):
        clock.read(np.array([2, 1], dtype=np.int64))
    with pytest.raises(ValueError):
        clock.read(np.array([1.0, 2.0]))


def test_nonoverlapping_events_keep_independent_ground_truth():
    events = [
        ClockFaultEvent(11, "jump", 100, 200, 10),
        ClockFaultEvent(12, "jump", 300, 400, -10),
    ]
    clock = FaultedClock(LocalClock(), events)
    refs = np.array([50, 150, 250, 350, 450], dtype=np.int64)
    truth = clock.read_with_truth(refs).fault_ids
    assert np.array_equal(truth, [0, 11, 0, 12, 0])
