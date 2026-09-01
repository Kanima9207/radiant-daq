"""Persistent event-recording primitives for RADIANT-DAQ."""

from .event_record import EventRecord
from .flight_recorder import FlightRecorder

__all__ = ["EventRecord", "FlightRecorder"]
