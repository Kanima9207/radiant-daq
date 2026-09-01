"""Persistent supervisory alarm and event journal for Stage 5.

The journal records operator-facing state transitions, alarms and recovery
results as append-only JSON Lines. It is diagnostic persistence only; it does
not command interlocks or alter acquisition state.
"""
from dataclasses import dataclass, asdict
import json
from pathlib import Path

from radiant.fdir.system import HealthState
from .supervisory import SupervisorySnapshot


_EVENT_KINDS = {"state_transition", "alarm", "recovery"}


@dataclass(frozen=True)
class JournalEvent:
    sequence: int
    timestamp_ns: int
    node_id: str
    kind: str
    source: str
    name: str
    severity: int = 0
    success: bool | None = None
    detail: str = ""

    def __post_init__(self):
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence must be a nonnegative integer")
        if type(self.timestamp_ns) is not int or self.timestamp_ns < 0:
            raise ValueError("timestamp_ns must be a nonnegative integer")
        if not isinstance(self.node_id, str) or not self.node_id:
            raise ValueError("node_id must be a nonempty string")
        if self.kind not in _EVENT_KINDS:
            raise ValueError(f"kind must be one of {sorted(_EVENT_KINDS)}")
        if not isinstance(self.source, str) or not self.source:
            raise ValueError("source must be a nonempty string")
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("name must be a nonempty string")
        if type(self.severity) is not int or not 0 <= self.severity <= 3:
            raise ValueError("severity must be an integer in [0, 3]")
        if self.success is not None and type(self.success) is not bool:
            raise TypeError("success must be bool or None")
        if not isinstance(self.detail, str):
            raise TypeError("detail must be a string")
        if self.kind == "alarm" and self.severity == 0:
            raise ValueError("alarm severity must be in [1, 3]")
        if self.kind == "recovery" and self.success is None:
            raise ValueError("recovery events require success")
        if self.kind != "recovery" and self.success is not None:
            raise ValueError("success is only valid for recovery events")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, payload):
        if not isinstance(payload, dict):
            raise ValueError("journal payload must be an object")
        required = {
            "sequence", "timestamp_ns", "node_id", "kind", "source", "name",
            "severity", "success", "detail",
        }
        if set(payload) != required:
            raise ValueError("journal payload has unexpected or missing fields")
        return cls(**payload)


class EventJournal:
    """Append-only event journal with replay validation."""

    def __init__(self, path=None):
        self.path = None if path is None else Path(path)
        self._events = []
        self._next_sequence = 0
        self._last_snapshot_state = {}

    @property
    def events(self):
        return tuple(self._events)

    def append(self, event):
        if not isinstance(event, JournalEvent):
            raise TypeError("event must be JournalEvent")
        if event.sequence != self._next_sequence:
            raise ValueError("event sequence must be contiguous")
        if self._events and event.timestamp_ns < self._events[-1].timestamp_ns:
            raise ValueError("event timestamp must be nondecreasing")
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")))
                handle.write("\n")
        self._events.append(event)
        self._next_sequence += 1
        return event

    def record_snapshot(self, snapshot):
        if not isinstance(snapshot, SupervisorySnapshot):
            raise TypeError("snapshot must be SupervisorySnapshot")
        emitted = []
        previous = self._last_snapshot_state.get(snapshot.node_id)
        if previous is None:
            self._last_snapshot_state[snapshot.node_id] = snapshot.health_state
        elif previous != snapshot.health_state:
            emitted.append(self.append(JournalEvent(
                self._next_sequence,
                snapshot.timestamp_ns,
                snapshot.node_id,
                "state_transition",
                "system",
                f"{previous.value}->{snapshot.health_state.value}",
                detail="supervisory health-state transition",
            )))
            self._last_snapshot_state[snapshot.node_id] = snapshot.health_state

        for alarm in snapshot.alarms:
            emitted.append(self.append(JournalEvent(
                self._next_sequence,
                snapshot.timestamp_ns,
                snapshot.node_id,
                "alarm",
                alarm.source,
                alarm.kind,
                severity=alarm.severity,
                detail=alarm.detail,
            )))

        for recovery in snapshot.recoveries:
            emitted.append(self.append(JournalEvent(
                self._next_sequence,
                snapshot.timestamp_ns,
                snapshot.node_id,
                "recovery",
                recovery.source,
                recovery.action,
                success=recovery.success,
                detail=recovery.detail,
            )))
        return tuple(emitted)

    @classmethod
    def load(cls, path):
        path = Path(path)
        journal = cls(path)
        if not path.exists():
            return journal
        events = []
        last_timestamp = None
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise ValueError(f"blank journal line at {line_number}")
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSON at journal line {line_number}") from exc
                event = JournalEvent.from_dict(payload)
                expected = len(events)
                if event.sequence != expected:
                    raise ValueError(f"noncontiguous sequence at journal line {line_number}")
                if last_timestamp is not None and event.timestamp_ns < last_timestamp:
                    raise ValueError(f"timestamp regression at journal line {line_number}")
                events.append(event)
                last_timestamp = event.timestamp_ns
        journal._events = events
        journal._next_sequence = len(events)
        return journal
