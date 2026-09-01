"""Deterministic fault-injection primitives for RADIANT-DAQ."""

from .injection import FaultEvent, FaultInjectionResult, SensorFaultInjector
from .packet import (
    PacketEnvelope,
    PacketFaultRecord,
    packet_crc32,
    envelope_packet,
    verify_envelope,
    flip_code_bit,
    corrupt_timestamp,
    corrupt_sequence,
    drop_packet,
    duplicate_packet,
    reorder_adjacent,
)

__all__ = [
    "FaultEvent",
    "FaultInjectionResult",
    "SensorFaultInjector",
    "PacketEnvelope",
    "PacketFaultRecord",
    "packet_crc32",
    "envelope_packet",
    "verify_envelope",
    "flip_code_bit",
    "corrupt_timestamp",
    "corrupt_sequence",
    "drop_packet",
    "duplicate_packet",
    "reorder_adjacent",
]
