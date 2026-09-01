import pytest

from radiant.fdir.system import HealthState
from radiant.telemetry import SupervisoryDemoBackend


def test_backend_starts_empty():
    backend = SupervisoryDemoBackend()
    assert backend.latest is None
    assert backend.history == ()


def test_first_frame_is_normal():
    frame = SupervisoryDemoBackend().next_frame()
    assert frame.health_state is HealthState.NORMAL
    assert frame.snapshot.sequence == 0
    assert frame.snapshot.timestamp_ns == 0


def test_scenario_reaches_warning_and_degraded():
    frames = SupervisoryDemoBackend().run(5)
    states = [frame.health_state for frame in frames]
    assert HealthState.WARNING in states
    assert HealthState.DEGRADED in states


def test_state_transitions_emit_journal_events():
    backend = SupervisoryDemoBackend()
    frames = backend.run(4)
    transition_names = [
        event.name
        for frame in frames
        for event in frame.journal_events
        if event.kind == "state_transition"
    ]
    assert "NORMAL->WARNING" in transition_names
    assert "WARNING->DEGRADED" in transition_names


def test_alarm_events_are_emitted():
    backend = SupervisoryDemoBackend()
    frames = backend.run(4)
    alarms = [event for frame in frames for event in frame.journal_events if event.kind == "alarm"]
    assert any(event.source == "sensor" and event.name == "bias" for event in alarms)
    assert any(event.source == "timing" for event in alarms)


def test_recovery_phase_records_success():
    backend = SupervisoryDemoBackend()
    frames = backend.run(5)
    recoveries = [event for frame in frames for event in frame.journal_events if event.kind == "recovery"]
    assert any(event.name == "restore_from_shadow" and event.success for event in recoveries)


def test_backend_is_deterministic():
    a = SupervisoryDemoBackend().run(8)
    b = SupervisoryDemoBackend().run(8)
    assert [frame.snapshot.to_dict() for frame in a] == [frame.snapshot.to_dict() for frame in b]


def test_buffer_capacity_is_enforced():
    backend = SupervisoryDemoBackend(capacity=3)
    backend.run(6)
    assert len(backend.history) == 3
    assert [item.sequence for item in backend.history] == [3, 4, 5]


def test_reset_restarts_demo_sequence():
    backend = SupervisoryDemoBackend()
    backend.run(4)
    backend.reset()
    frame = backend.next_frame()
    assert frame.snapshot.sequence == 0
    assert frame.snapshot.timestamp_ns == 0
    assert frame.health_state is HealthState.NORMAL


def test_run_rejects_invalid_frame_count():
    backend = SupervisoryDemoBackend()
    with pytest.raises(ValueError):
        backend.run(0)
    with pytest.raises(ValueError):
        backend.run(1.5)
