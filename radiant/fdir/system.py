"""System-level health state machine for FDIR-005.

This module combines detector outcomes into a deterministic supervisory health
state. It does not itself repair faults or command physical interlocks.
"""
from dataclasses import dataclass
from enum import Enum


class HealthState(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    DEGRADED = "DEGRADED"
    SAFE = "SAFE"


@dataclass(frozen=True)
class HealthSignal:
    """Normalized health evidence from any subsystem detector."""

    source: str
    kind: str
    severity: int = 1
    critical: bool = False

    def __post_init__(self):
        if not isinstance(self.source, str) or not self.source:
            raise ValueError("source must be a nonempty string")
        if not isinstance(self.kind, str) or not self.kind:
            raise ValueError("kind must be a nonempty string")
        if type(self.severity) is not int or not 1 <= self.severity <= 3:
            raise ValueError("severity must be an integer in [1, 3]")
        if type(self.critical) is not bool:
            raise TypeError("critical must be bool")


@dataclass(frozen=True)
class HealthTransition:
    previous: HealthState
    current: HealthState
    reason: str
    fault_streak: int
    clean_streak: int


@dataclass(frozen=True)
class SystemHealthConfig:
    warning_after: int = 1
    degraded_after: int = 2
    safe_after: int = 4
    recover_after: int = 3

    def __post_init__(self):
        for name in ("warning_after", "degraded_after", "safe_after", "recover_after"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not self.warning_after <= self.degraded_after <= self.safe_after:
            raise ValueError("escalation thresholds must be nondecreasing")


class SystemHealthStateMachine:
    """Aggregate detector evidence into NORMAL/WARNING/DEGRADED/SAFE.

    Persistent noncritical evidence escalates according to configured streak
    thresholds. Severity 3 accelerates escalation to at least DEGRADED. A
    critical signal forces SAFE immediately. Clean observations recover only
    after ``recover_after`` consecutive healthy evaluations, one state at a
    time, preventing rapid state flapping.
    """

    def __init__(self, config=None):
        self.config = config or SystemHealthConfig()
        if not isinstance(self.config, SystemHealthConfig):
            raise TypeError("config must be SystemHealthConfig")
        self.reset()

    def reset(self):
        self.state = HealthState.NORMAL
        self.fault_streak = 0
        self.clean_streak = 0
        self.history = []

    def evaluate(self, signals=()):
        signals = tuple(signals)
        if any(not isinstance(signal, HealthSignal) for signal in signals):
            raise TypeError("signals must contain HealthSignal instances")

        previous = self.state
        if signals:
            self.clean_streak = 0
            self.fault_streak += 1
            max_severity = max(signal.severity for signal in signals)
            critical = any(signal.critical for signal in signals)

            if critical or self.fault_streak >= self.config.safe_after:
                target = HealthState.SAFE
                reason = "critical finding" if critical else "persistent faults reached SAFE threshold"
            elif max_severity >= 3 or self.fault_streak >= self.config.degraded_after:
                target = HealthState.DEGRADED
                reason = "high-severity finding" if max_severity >= 3 else "persistent faults reached DEGRADED threshold"
            elif self.fault_streak >= self.config.warning_after:
                target = HealthState.WARNING
                reason = "fault evidence present"
            else:
                target = self.state
                reason = "fault evidence below escalation threshold"

            if _rank(target) > _rank(self.state):
                self.state = target
        else:
            self.fault_streak = 0
            self.clean_streak += 1
            reason = "healthy evidence"
            if self.clean_streak >= self.config.recover_after:
                self.state = _step_down(self.state)
                self.clean_streak = 0
                reason = "sustained healthy evidence"

        transition = HealthTransition(previous, self.state, reason,
                                      self.fault_streak, self.clean_streak)
        self.history.append(transition)
        return transition


def _rank(state):
    return {
        HealthState.NORMAL: 0,
        HealthState.WARNING: 1,
        HealthState.DEGRADED: 2,
        HealthState.SAFE: 3,
    }[state]


def _step_down(state):
    return {
        HealthState.SAFE: HealthState.DEGRADED,
        HealthState.DEGRADED: HealthState.WARNING,
        HealthState.WARNING: HealthState.NORMAL,
        HealthState.NORMAL: HealthState.NORMAL,
    }[state]
