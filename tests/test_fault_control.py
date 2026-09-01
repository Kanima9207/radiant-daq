import pytest

from radiant.fdir.system import HealthState
from radiant.telemetry import (
    FAULT_OPTIONS,
    FaultInjectionController,
    SupervisoryDemoBackend,
)


def test_fault_options_cover_all_protected_scenarios():
    controller = FaultInjectionController()
    assert controller.faults == FAULT_OPTIONS
    assert len(controller.faults) == 15
    assert len(set(controller.faults)) == 15


def test_bias_is_detected_but_not_automatically_contained():
    result = FaultInjectionController().evaluate("bias")
    assert result.detected
    assert not result.contained
    assert not result.recovered
    assert result.detector == "sensor_health"


def test_packet_drop_is_contained_but_not_recovered():
    result = FaultInjectionController().evaluate("packet_drop")
    assert result.detected
    assert result.contained
    assert not result.recovered
    assert result.recovery_action == "reject_packet"


def test_register_bit_flip_is_recovered_from_redundant_state():
    result = FaultInjectionController().evaluate("register_bit_flip")
    assert result.detected
    assert result.contained
    assert result.recovered
    assert result.recovery_action == "restore_from_shadow"


def test_clock_jump_is_detected_without_automatic_recovery():
    result = FaultInjectionController().evaluate("clock_jump")
    assert result.detected
    assert not result.contained
    assert not result.recovered
    assert result.domain == "timing"


def test_unknown_fault_is_rejected():
    controller = FaultInjectionController()
    with pytest.raises(ValueError):
        controller.evaluate("not_a_fault")
    with pytest.raises(TypeError):
        controller.evaluate(123)


def test_sensor_snapshot_has_warning_alarm():
    snapshot = FaultInjectionController().snapshot("bias", 7, 900, "node-a")
    assert snapshot.sequence == 7
    assert snapshot.timestamp_ns == 900
    assert snapshot.node_id == "node-a"
    assert snapshot.health_state is HealthState.WARNING
    assert snapshot.alarms[0].kind == "bias"
    assert snapshot.metrics["fault_detected"] == 1.0


def test_digital_state_snapshot_reports_true_recovery():
    snapshot = FaultInjectionController().snapshot("register_bit_flip", 0, 0)
    assert snapshot.health_state is HealthState.DEGRADED
    assert snapshot.metrics["fault_contained"] == 1.0
    assert snapshot.metrics["fault_recovered"] == 1.0
    assert snapshot.recoveries[0].success
    assert snapshot.recoveries[0].action == "restore_from_shadow"


def test_backend_injected_fault_advances_history_and_journal():
    backend = SupervisoryDemoBackend()
    backend.next_frame()
    frame = backend.inject_fault("packet_drop")
    assert frame.snapshot.sequence == 1
    assert len(backend.history) == 2
    assert frame.snapshot.alarms[0].kind == "packet_drop"
    assert frame.snapshot.recoveries[0].action == "reject_packet"
    assert any(event.kind == "alarm" for event in frame.journal_events)
    assert any(event.kind == "recovery" for event in frame.journal_events)


def test_backend_can_return_to_nominal_stream_after_injection():
    backend = SupervisoryDemoBackend()
    injected = backend.inject_fault("register_bit_flip")
    following = backend.next_frame()
    assert injected.snapshot.health_state is HealthState.DEGRADED
    assert following.snapshot.sequence == 1
    assert following.snapshot.timestamp_ns > injected.snapshot.timestamp_ns
    assert following.snapshot.health_state is HealthState.NORMAL
