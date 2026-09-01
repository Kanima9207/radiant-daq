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
from .seu import (
    SEUFaultRecord,
    DigitalStateBank,
    flip_integer_bit,
    flip_float64_bit,
    flip_array_element_bit,
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
    "SEUFaultRecord",
    "DigitalStateBank",
    "flip_integer_bit",
    "flip_float64_bit",
    "flip_array_element_bit",
]
