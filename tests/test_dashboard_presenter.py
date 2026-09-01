import pytest

from radiant.fdir.system import HealthState
from radiant.telemetry import (
    AlarmRecord,
    RecoveryTelemetry,
    SupervisorySnapshot,
    SupervisoryDemoBackend,
    state_label,
    metric_rows,
    alarm_rows,
    recovery_rows,
    history_rows,
    journal_rows,
)


def _snapshot():
    return SupervisorySnapshot(
        sequence=3,
        timestamp_ns=250_000_000,
        health_state=HealthState.DEGRADED,
        node_id="node-a",
        metrics={"timing_rms_ns": 1200.0, "buffer_fill_pct": 42.0},
        alarms=(AlarmRecord("timing", "rms_residual", 2, "high residual"),),
        recoveries=(RecoveryTelemetry("state", "restore", True, "restored"),),
    )


def test_state_label_covers_health_state():
    assert state_label(HealthState.NORMAL) == "NORMAL"
    assert state_label(HealthState.SAFE) == "SAFE"


def test_state_label_rejects_wrong_type():
    with pytest.raises(TypeError):
        state_label("NORMAL")


def test_metric_rows_sorted_and_numeric():
    rows = metric_rows(_snapshot())
    assert [row["metric"] for row in rows] == ["buffer_fill_pct", "timing_rms_ns"]
    assert all(type(row["value"]) is float for row in rows)


def test_alarm_rows_preserve_details():
    row = alarm_rows(_snapshot())[0]
    assert row == {
        "source": "timing",
        "alarm": "rms_residual",
        "severity": 2,
        "detail": "high residual",
    }


def test_recovery_rows_preserve_success():
    row = recovery_rows(_snapshot())[0]
    assert row["action"] == "restore"
    assert row["success"] is True


def test_history_rows_include_metrics_and_state():
    row = history_rows((_snapshot(),))[0]
    assert row["sequence"] == 3
    assert row["time_ms"] == 250.0
    assert row["state"] == "DEGRADED"
    assert row["timing_rms_ns"] == 1200.0


def test_history_rows_reject_invalid_value():
    with pytest.raises(TypeError):
        history_rows((_snapshot(), object()))


def test_journal_rows_render_backend_events():
    backend = SupervisoryDemoBackend()
    backend.run(4)
    rows = journal_rows(backend.journal.events)
    assert rows
    assert {row["kind"] for row in rows} >= {"alarm", "state_transition"}


def test_journal_rows_reject_invalid_event():
    with pytest.raises(TypeError):
        journal_rows((object(),))


def test_demo_backend_data_is_dashboard_renderable():
    backend = SupervisoryDemoBackend()
    backend.run(8)
    assert history_rows(backend.history)
    assert journal_rows(backend.journal.events)
    assert state_label(backend.latest.health_state) in {"NORMAL", "WARNING", "DEGRADED", "SAFE"}
