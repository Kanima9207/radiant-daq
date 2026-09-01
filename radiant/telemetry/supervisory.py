"""Unified supervisory telemetry snapshots for Stage 5.

These models expose operator-facing health and recovery evidence without
changing raw acquisition packets. They are software telemetry structures only;
they do not command physical interlocks or hardware.
"""
from dataclasses import dataclass, field
from typing import Mapping

from radiant.fdir.system import HealthState


@dataclass(frozen=True)
class AlarmRecord:
    source: str
    kind: str
    severity: int
    detail: str = ""

    def __post_init__(self):
        if not isinstance(self.source, str) or not self.source:
            raise ValueError("source must be a nonempty string")
        if not isinstance(self.kind, str) or not self.kind:
            raise ValueError("kind must be a nonempty string")
        if type(self.severity) is not int or not 1 <= self.severity <= 3:
            raise ValueError("severity must be an integer in [1, 3]")
        if not isinstance(self.detail, str):
            raise TypeError("detail must be a string")


@dataclass(frozen=True)
class RecoveryTelemetry:
    source: str
    action: str
    success: bool
    detail: str = ""

    def __post_init__(self):
        if not isinstance(self.source, str) or not self.source:
            raise ValueError("source must be a nonempty string")
        if not isinstance(self.action, str) or not self.action:
            raise ValueError("action must be a nonempty string")
        if type(self.success) is not bool:
            raise TypeError("success must be bool")
        if not isinstance(self.detail, str):
            raise TypeError("detail must be a string")


@dataclass(frozen=True)
class SupervisorySnapshot:
    """Single immutable health snapshot suitable for dashboard/API transport."""

    sequence: int
    timestamp_ns: int
    health_state: HealthState
    node_id: str = "node-0"
    metrics: Mapping[str, float] = field(default_factory=dict)
    alarms: tuple[AlarmRecord, ...] = ()
    recoveries: tuple[RecoveryTelemetry, ...] = ()

    def __post_init__(self):
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence must be a nonnegative integer")
        if type(self.timestamp_ns) is not int or self.timestamp_ns < 0:
            raise ValueError("timestamp_ns must be a nonnegative integer")
        if not isinstance(self.health_state, HealthState):
            raise TypeError("health_state must be HealthState")
        if not isinstance(self.node_id, str) or not self.node_id:
            raise ValueError("node_id must be a nonempty string")
        metrics = dict(self.metrics)
        for key, value in metrics.items():
            if not isinstance(key, str) or not key:
                raise ValueError("metric names must be nonempty strings")
            if not isinstance(value, (int, float)):
                raise TypeError("metric values must be numeric")
        if any(not isinstance(item, AlarmRecord) for item in self.alarms):
            raise TypeError("alarms must contain AlarmRecord values")
        if any(not isinstance(item, RecoveryTelemetry) for item in self.recoveries):
            raise TypeError("recoveries must contain RecoveryTelemetry values")
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(self, "alarms", tuple(self.alarms))
        object.__setattr__(self, "recoveries", tuple(self.recoveries))

    @property
    def alarm_count(self):
        return len(self.alarms)

    @property
    def failed_recovery_count(self):
        return sum(not item.success for item in self.recoveries)

    def to_dict(self):
        return {
            "sequence": self.sequence,
            "timestamp_ns": self.timestamp_ns,
            "health_state": self.health_state.value,
            "node_id": self.node_id,
            "metrics": dict(self.metrics),
            "alarms": [
                {
                    "source": item.source,
                    "kind": item.kind,
                    "severity": item.severity,
                    "detail": item.detail,
                }
                for item in self.alarms
            ],
            "recoveries": [
                {
                    "source": item.source,
                    "action": item.action,
                    "success": item.success,
                    "detail": item.detail,
                }
                for item in self.recoveries
            ],
        }


class SupervisoryBuffer:
    """Bounded in-memory snapshot history for dashboards and tests."""

    def __init__(self, capacity=256):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        self.capacity = capacity
        self._items = []

    def append(self, snapshot):
        if not isinstance(snapshot, SupervisorySnapshot):
            raise TypeError("snapshot must be SupervisorySnapshot")
        if self._items and snapshot.sequence <= self._items[-1].sequence:
            raise ValueError("snapshot sequence must increase strictly")
        if self._items and snapshot.timestamp_ns < self._items[-1].timestamp_ns:
            raise ValueError("snapshot timestamp must be nondecreasing")
        self._items.append(snapshot)
        if len(self._items) > self.capacity:
            del self._items[:len(self._items) - self.capacity]

    @property
    def latest(self):
        return self._items[-1] if self._items else None

    def snapshot(self):
        return tuple(self._items)

    def clear(self):
        self._items.clear()
