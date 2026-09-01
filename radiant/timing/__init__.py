"""Timing models and synchronization primitives for RADIANT-DAQ."""

from .clock import LocalClock
from .synchronization import (
    SynchronizationEstimate,
    estimate_synchronization,
    synchronization_error,
)

__all__ = [
    "LocalClock",
    "SynchronizationEstimate",
    "estimate_synchronization",
    "synchronization_error",
]
