"""Fault detection, isolation and recovery primitives for RADIANT-DAQ."""

from .transport import IntegrityFinding, IntegrityReport, TransportIntegrityMonitor
from .sensor import (
    SensorHealthConfig,
    SensorFinding,
    ChannelHealth,
    SensorHealthReport,
    SensorHealthMonitor,
)
from .timing import (
    TimingHealthConfig,
    TimingFinding,
    TimingHealthReport,
    TimingHealthMonitor,
)
from .state import (
    StateFinding,
    StateIntegrityReport,
    MirroredStateBank,
    state_crc32,
)
from .system import (
    HealthState,
    HealthSignal,
    HealthTransition,
    SystemHealthConfig,
    SystemHealthStateMachine,
)

__all__ = [
    "IntegrityFinding",
    "IntegrityReport",
    "TransportIntegrityMonitor",
    "SensorHealthConfig",
    "SensorFinding",
    "ChannelHealth",
    "SensorHealthReport",
    "SensorHealthMonitor",
    "TimingHealthConfig",
    "TimingFinding",
    "TimingHealthReport",
    "TimingHealthMonitor",
    "StateFinding",
    "StateIntegrityReport",
    "MirroredStateBank",
    "state_crc32",
    "HealthState",
    "HealthSignal",
    "HealthTransition",
    "SystemHealthConfig",
    "SystemHealthStateMachine",
]
