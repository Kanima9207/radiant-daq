"""Deterministic packet/data-integrity fault injection for FAULT-002.

This module keeps corruption ground truth separate from integrity checking. CRC-32
is used as an error-detection experiment, not as authentication.
"""
from dataclasses import dataclass
import copy
import struct
import zlib
import numpy as np

from radiant.acquisition import ADCResult, AcquisitionPacket


@dataclass(frozen=True)
class PacketEnvelope:
    """Acquisition packet plus CRC computed before transport corruption."""

    packet: AcquisitionPacket
    crc32: int


@dataclass(frozen=True)
class PacketFaultRecord:
    """Independent ground truth for one injected transport fault."""

    kind: str
    original_sequence: int
    output_position: int | None = None
    detail: str = ""


def _canonical_bytes(packet):
    if not isinstance(packet, AcquisitionPacket):
        raise TypeError("packet must be an AcquisitionPacket")
    header = struct.pack(
        ">qqqI",
        int(packet.sequence),
        int(packet.first_sample),
        int(packet.sample_rate_hz),
        len(packet.channel_ids),
    )
    channels = np.asarray(packet.channel_ids, dtype=">i8").tobytes(order="C")
    stamps = np.asarray(packet.timestamps_ns, dtype=">i8").tobytes(order="C")
    codes = np.asarray(packet.data.codes, dtype=">u4").tobytes(order="C")
    volts = np.asarray(packet.data.volts, dtype=">f8").tobytes(order="C")
    clipped = np.asarray(packet.data.clipped, dtype=np.uint8).tobytes(order="C")
    shapes = struct.pack(
        ">IIII",
        packet.timestamps_ns.size,
        packet.data.codes.shape[0],
        packet.data.codes.shape[1],
        packet.data.volts.shape[1],
    )
    return header + shapes + channels + stamps + codes + volts + clipped


def packet_crc32(packet):
    """Return deterministic CRC-32 over packet metadata and payload."""
    return zlib.crc32(_canonical_bytes(packet)) & 0xFFFFFFFF


def envelope_packet(packet):
    """Snapshot a packet and attach its pre-transport CRC."""
    return PacketEnvelope(_copy_packet(packet), packet_crc32(packet))


def verify_envelope(envelope):
    if not isinstance(envelope, PacketEnvelope):
        raise TypeError("envelope must be a PacketEnvelope")
    return packet_crc32(envelope.packet) == envelope.crc32


def _copy_packet(packet):
    if not isinstance(packet, AcquisitionPacket):
        raise TypeError("packet must be an AcquisitionPacket")
    return AcquisitionPacket(
        sequence=int(packet.sequence),
        first_sample=int(packet.first_sample),
        sample_rate_hz=int(packet.sample_rate_hz),
        channel_ids=tuple(packet.channel_ids),
        timestamps_ns=np.array(packet.timestamps_ns, copy=True),
        data=ADCResult(
            codes=np.array(packet.data.codes, copy=True),
            volts=np.array(packet.data.volts, copy=True),
            clipped=np.array(packet.data.clipped, copy=True),
        ),
    )


def flip_code_bit(envelope, sample_index, channel_index, bit_index):
    """Flip one bit in one transmitted ADC code without changing stored CRC."""
    if not isinstance(envelope, PacketEnvelope):
        raise TypeError("envelope must be a PacketEnvelope")
    p = _copy_packet(envelope.packet)
    rows, cols = p.data.codes.shape
    if type(sample_index) is not int or not 0 <= sample_index < rows:
        raise ValueError("sample_index out of range")
    if type(channel_index) is not int or not 0 <= channel_index < cols:
        raise ValueError("channel_index out of range")
    if type(bit_index) is not int or not 0 <= bit_index < 32:
        raise ValueError("bit_index must be in [0, 31]")
    p.data.codes[sample_index, channel_index] ^= np.uint32(1 << bit_index)
    fault = PacketFaultRecord(
        "payload_bit_flip", p.sequence,
        detail=f"codes[{sample_index},{channel_index}] bit {bit_index}",
    )
    return PacketEnvelope(p, envelope.crc32), fault


def corrupt_timestamp(envelope, sample_index, delta_ns):
    """Add a deterministic error to one transmitted timestamp."""
    if not isinstance(envelope, PacketEnvelope):
        raise TypeError("envelope must be a PacketEnvelope")
    if type(delta_ns) is not int or delta_ns == 0:
        raise ValueError("delta_ns must be a nonzero integer")
    p = _copy_packet(envelope.packet)
    if type(sample_index) is not int or not 0 <= sample_index < p.timestamps_ns.size:
        raise ValueError("sample_index out of range")
    value = int(p.timestamps_ns[sample_index]) + delta_ns
    lim = np.iinfo(np.int64)
    if not lim.min <= value <= lim.max:
        raise OverflowError("corrupted timestamp exceeds signed 64-bit range")
    p.timestamps_ns[sample_index] = value
    fault = PacketFaultRecord(
        "timestamp_corruption", p.sequence,
        detail=f"timestamps_ns[{sample_index}] += {delta_ns}",
    )
    return PacketEnvelope(p, envelope.crc32), fault


def corrupt_sequence(envelope, new_sequence):
    """Replace transmitted sequence metadata without changing stored CRC."""
    if not isinstance(envelope, PacketEnvelope):
        raise TypeError("envelope must be a PacketEnvelope")
    if type(new_sequence) is not int or new_sequence < 0:
        raise ValueError("new_sequence must be a nonnegative integer")
    p = _copy_packet(envelope.packet)
    original = p.sequence
    p = AcquisitionPacket(
        new_sequence, p.first_sample, p.sample_rate_hz, p.channel_ids,
        p.timestamps_ns, p.data,
    )
    return PacketEnvelope(p, envelope.crc32), PacketFaultRecord(
        "sequence_corruption", original,
        detail=f"sequence {original} -> {new_sequence}",
    )


def drop_packet(envelopes, position):
    """Drop one packet from a stream and return independent ground truth."""
    items = list(envelopes)
    if type(position) is not int or not 0 <= position < len(items):
        raise ValueError("position out of range")
    removed = items.pop(position)
    if not isinstance(removed, PacketEnvelope):
        raise TypeError("stream must contain PacketEnvelope objects")
    fault = PacketFaultRecord("packet_drop", removed.packet.sequence, position)
    return items, fault


def duplicate_packet(envelopes, position):
    """Insert a detached duplicate immediately after the selected packet."""
    items = list(envelopes)
    if type(position) is not int or not 0 <= position < len(items):
        raise ValueError("position out of range")
    selected = items[position]
    if not isinstance(selected, PacketEnvelope):
        raise TypeError("stream must contain PacketEnvelope objects")
    duplicate = PacketEnvelope(_copy_packet(selected.packet), selected.crc32)
    items.insert(position + 1, duplicate)
    fault = PacketFaultRecord("packet_duplicate", selected.packet.sequence, position + 1)
    return items, fault


def reorder_adjacent(envelopes, position):
    """Swap packets at ``position`` and ``position + 1``."""
    items = list(envelopes)
    if type(position) is not int or not 0 <= position < len(items) - 1:
        raise ValueError("position must identify the first of two adjacent packets")
    if not all(isinstance(item, PacketEnvelope) for item in items):
        raise TypeError("stream must contain PacketEnvelope objects")
    first_sequence = items[position].packet.sequence
    second_sequence = items[position + 1].packet.sequence
    items[position], items[position + 1] = items[position + 1], items[position]
    fault = PacketFaultRecord(
        "packet_reorder", first_sequence, position,
        detail=f"swapped sequences {first_sequence} and {second_sequence}",
    )
    return items, fault
