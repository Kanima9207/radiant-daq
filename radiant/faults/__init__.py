"""Deterministic fault-injection primitives for RADIANT-DAQ."""

from .injection import FaultEvent, FaultInjectionResult, SensorFaultInjector

__all__ = ["FaultEvent", "FaultInjectionResult", "SensorFaultInjector"]
