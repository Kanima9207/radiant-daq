"""Pure presentation helpers for the Streamlit supervisory dashboard.

These functions translate validated telemetry models into simple dictionaries
for UI rendering. They contain no detector, recovery, or interlock logic.
"""
from radiant.fdir.system import HealthState
from .supervisory import SupervisorySnapshot
from .journal import JournalEvent


_STATE_LABELS = {
    HealthState.NORMAL: "NORMAL",
    HealthState.WARNING: "WARNING",
    HealthState.DEGRADED: "DEGRADED",
    HealthState.SAFE: "SAFE",
}


def state_label(state):
    if not isinstance(state, HealthState):
        raise TypeError("state must be HealthState")
    return _STATE_LABELS[state]


def metric_rows(snapshot):
    if not isinstance(snapshot, SupervisorySnapshot):
        raise TypeError("snapshot must be SupervisorySnapshot")
    return tuple(
        {"metric": name, "value": float(value)}
        for name, value in sorted(snapshot.metrics.items())
    )


def alarm_rows(snapshot):
    if not isinstance(snapshot, SupervisorySnapshot):
        raise TypeError("snapshot must be SupervisorySnapshot")
    return tuple({
        "source": item.source,
        "alarm": item.kind,
        "severity": item.severity,
        "detail": item.detail,
    } for item in snapshot.alarms)


def recovery_rows(snapshot):
    if not isinstance(snapshot, SupervisorySnapshot):
        raise TypeError("snapshot must be SupervisorySnapshot")
    return tuple({
        "source": item.source,
        "action": item.action,
        "success": item.success,
        "detail": item.detail,
    } for item in snapshot.recoveries)


def history_rows(history):
    rows = []
    for snapshot in history:
        if not isinstance(snapshot, SupervisorySnapshot):
            raise TypeError("history must contain SupervisorySnapshot values")
        row = {
            "sequence": snapshot.sequence,
            "time_ms": snapshot.timestamp_ns / 1_000_000.0,
            "state": snapshot.health_state.value,
            "alarms": snapshot.alarm_count,
            "failed_recoveries": snapshot.failed_recovery_count,
        }
        row.update({name: float(value) for name, value in snapshot.metrics.items()})
        rows.append(row)
    return tuple(rows)


def journal_rows(events):
    rows = []
    for event in events:
        if not isinstance(event, JournalEvent):
            raise TypeError("events must contain JournalEvent values")
        rows.append({
            "sequence": event.sequence,
            "time_ms": event.timestamp_ns / 1_000_000.0,
            "node": event.node_id,
            "kind": event.kind,
            "source": event.source,
            "name": event.name,
            "severity": event.severity,
            "success": event.success,
            "detail": event.detail,
        })
    return tuple(rows)
