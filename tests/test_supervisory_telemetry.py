import pytest

from radiant.fdir.system import HealthState
from radiant.telemetry import (
    AlarmRecord,
    RecoveryTelemetry,
    SupervisoryBuffer,
    SupervisorySnapshot,
)


def make_snapshot(sequence=0, timestamp_ns=0, state=HealthState.NORMAL, **kwargs):
    return SupervisorySnapshot(sequence, timestamp_ns, state, **kwargs)


def test_snapshot_serializes_operator_facing_fields():
    snapshot = make_snapshot(
        3, 5000, HealthState.DEGRADED,
        node_id="daq-a",
        metrics={"timing_rms_ns": 250.5},
        alarms=(AlarmRecord("timing", "peak_residual", 2, "threshold exceeded"),),
        recoveries=(RecoveryTelemetry("digital_state", "restore_from_shadow", True),),
    )
    payload = snapshot.to_dict()
    assert payload["sequence"] == 3
    assert payload["health_state"] == "DEGRADED"
    assert payload["node_id"] == "daq-a"
    assert payload["metrics"]["timing_rms_ns"] == 250.5
    assert payload["alarms"][0]["kind"] == "peak_residual"
    assert payload["recoveries"][0]["success"] is True


def test_snapshot_counts_alarms_and_failed_recoveries():
    snapshot = make_snapshot(
        alarms=(AlarmRecord("sensor", "bias", 1), AlarmRecord("transport", "gap", 2)),
        recoveries=(RecoveryTelemetry("transport", "reject_packet", True),
                    RecoveryTelemetry("digital_state", "fail_closed", False)),
    )
    assert snapshot.alarm_count == 2
    assert snapshot.failed_recovery_count == 1


def test_snapshot_validates_sequence_timestamp_and_state():
    with pytest.raises(ValueError):
        make_snapshot(sequence=-1)
    with pytest.raises(ValueError):
        make_snapshot(timestamp_ns=-1)
    with pytest.raises(TypeError):
        SupervisorySnapshot(0, 0, "NORMAL")


def test_snapshot_validates_metric_schema():
    with pytest.raises(ValueError):
        make_snapshot(metrics={"": 1.0})
    with pytest.raises(TypeError):
        make_snapshot(metrics={"bad": "value"})


def test_alarm_and_recovery_validation():
    with pytest.raises(ValueError):
        AlarmRecord("", "bias", 1)
    with pytest.raises(ValueError):
        AlarmRecord("sensor", "bias", 4)
    with pytest.raises(TypeError):
        RecoveryTelemetry("state", "restore", 1)


def test_buffer_preserves_order_and_latest():
    buffer = SupervisoryBuffer(capacity=3)
    first = make_snapshot(0, 10)
    second = make_snapshot(1, 20, HealthState.WARNING)
    buffer.append(first)
    buffer.append(second)
    assert buffer.latest == second
    assert buffer.snapshot() == (first, second)


def test_buffer_is_bounded():
    buffer = SupervisoryBuffer(capacity=2)
    buffer.append(make_snapshot(0, 10))
    buffer.append(make_snapshot(1, 20))
    buffer.append(make_snapshot(2, 30))
    assert [item.sequence for item in buffer.snapshot()] == [1, 2]


def test_buffer_rejects_nonincreasing_sequence():
    buffer = SupervisoryBuffer()
    buffer.append(make_snapshot(2, 10))
    with pytest.raises(ValueError):
        buffer.append(make_snapshot(2, 20))
    with pytest.raises(ValueError):
        buffer.append(make_snapshot(1, 30))


def test_buffer_rejects_backward_timestamp():
    buffer = SupervisoryBuffer()
    buffer.append(make_snapshot(0, 100))
    with pytest.raises(ValueError):
        buffer.append(make_snapshot(1, 99))


def test_buffer_clear_and_capacity_validation():
    with pytest.raises(ValueError):
        SupervisoryBuffer(0)
    buffer = SupervisoryBuffer()
    buffer.append(make_snapshot())
    buffer.clear()
    assert buffer.latest is None
    assert buffer.snapshot() == ()
