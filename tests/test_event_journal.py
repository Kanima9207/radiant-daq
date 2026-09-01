import json
import pytest

from radiant.fdir.system import HealthState
from radiant.telemetry import (
    AlarmRecord,
    RecoveryTelemetry,
    SupervisorySnapshot,
    JournalEvent,
    EventJournal,
)


def _snapshot(sequence, timestamp, state=HealthState.NORMAL, node_id="node-a",
              alarms=(), recoveries=()):
    return SupervisorySnapshot(
        sequence=sequence,
        timestamp_ns=timestamp,
        health_state=state,
        node_id=node_id,
        alarms=alarms,
        recoveries=recoveries,
    )


def test_journal_event_round_trip_dict():
    event = JournalEvent(0, 100, "node-a", "alarm", "sensor", "bias", 2, None, "offset")
    assert JournalEvent.from_dict(event.to_dict()) == event


def test_event_validation_rejects_invalid_combinations():
    with pytest.raises(ValueError):
        JournalEvent(0, 0, "node", "alarm", "sensor", "bias", 0)
    with pytest.raises(ValueError):
        JournalEvent(0, 0, "node", "recovery", "state", "restore")
    with pytest.raises(ValueError):
        JournalEvent(0, 0, "node", "alarm", "sensor", "bias", 1, True)


def test_record_snapshot_emits_alarm_and_recovery():
    journal = EventJournal()
    alarm = AlarmRecord("sensor", "drift", 2, "slope high")
    recovery = RecoveryTelemetry("digital_state", "restore_from_shadow", True, "restored")
    emitted = journal.record_snapshot(_snapshot(0, 100, alarms=(alarm,), recoveries=(recovery,)))
    assert [item.kind for item in emitted] == ["alarm", "recovery"]
    assert emitted[0].severity == 2
    assert emitted[1].success is True


def test_state_transition_emitted_only_when_state_changes():
    journal = EventJournal()
    assert journal.record_snapshot(_snapshot(0, 100, HealthState.NORMAL)) == ()
    assert journal.record_snapshot(_snapshot(1, 200, HealthState.NORMAL)) == ()
    emitted = journal.record_snapshot(_snapshot(2, 300, HealthState.WARNING))
    assert len(emitted) == 1
    assert emitted[0].kind == "state_transition"
    assert emitted[0].name == "NORMAL->WARNING"


def test_state_tracking_is_independent_per_node():
    journal = EventJournal()
    journal.record_snapshot(_snapshot(0, 100, HealthState.NORMAL, "node-a"))
    journal.record_snapshot(_snapshot(0, 100, HealthState.DEGRADED, "node-b"))
    emitted_a = journal.record_snapshot(_snapshot(1, 200, HealthState.WARNING, "node-a"))
    emitted_b = journal.record_snapshot(_snapshot(1, 200, HealthState.DEGRADED, "node-b"))
    assert len(emitted_a) == 1
    assert emitted_b == ()


def test_jsonl_persistence_and_load_round_trip(tmp_path):
    path = tmp_path / "events.jsonl"
    journal = EventJournal(path)
    journal.record_snapshot(_snapshot(
        0, 100, alarms=(AlarmRecord("timing", "peak_residual", 3),)
    ))
    journal.record_snapshot(_snapshot(
        1, 200, HealthState.DEGRADED,
        recoveries=(RecoveryTelemetry("watchdog", "reset_processing", True),),
    ))
    loaded = EventJournal.load(path)
    assert loaded.events == journal.events
    assert [event.sequence for event in loaded.events] == list(range(len(loaded.events)))


def test_append_requires_contiguous_sequence_and_monotonic_time():
    journal = EventJournal()
    journal.append(JournalEvent(0, 100, "node", "alarm", "sensor", "noise", 1))
    with pytest.raises(ValueError):
        journal.append(JournalEvent(2, 200, "node", "alarm", "sensor", "bias", 1))
    with pytest.raises(ValueError):
        journal.append(JournalEvent(1, 99, "node", "alarm", "sensor", "bias", 1))


def test_load_rejects_invalid_json_and_blank_lines(tmp_path):
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text("{bad json}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        EventJournal.load(malformed)
    blank = tmp_path / "blank.jsonl"
    blank.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError):
        EventJournal.load(blank)


def test_load_rejects_missing_fields_sequence_gap_and_time_regression(tmp_path):
    missing = tmp_path / "missing.jsonl"
    missing.write_text(json.dumps({"sequence": 0}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        EventJournal.load(missing)

    gap = tmp_path / "gap.jsonl"
    first = JournalEvent(0, 100, "node", "alarm", "sensor", "bias", 1).to_dict()
    second = JournalEvent(2, 200, "node", "alarm", "sensor", "noise", 1).to_dict()
    gap.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        EventJournal.load(gap)

    regression = tmp_path / "regression.jsonl"
    first = JournalEvent(0, 200, "node", "alarm", "sensor", "bias", 1).to_dict()
    second = JournalEvent(1, 100, "node", "alarm", "sensor", "noise", 1).to_dict()
    regression.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        EventJournal.load(regression)


def test_loading_missing_file_returns_empty_appendable_journal(tmp_path):
    path = tmp_path / "new.jsonl"
    journal = EventJournal.load(path)
    assert journal.events == ()
    journal.append(JournalEvent(0, 10, "node", "alarm", "sensor", "bias", 1))
    assert path.exists()
