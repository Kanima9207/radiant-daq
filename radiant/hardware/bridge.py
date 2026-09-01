"""CRC-protected external acquisition bridge for HW-001.

This module defines a compact JSON-line protocol for bringing hardware or
hardware-emulated ADC frames into the existing RADIANT-DAQ AcquisitionPacket
pipeline. It is a validation/prototyping transport, not a high-throughput link
or a claim of hardware timing performance.
"""
from dataclasses import dataclass
import json
import math
import zlib

import numpy as np

from radiant.acquisition import AcquisitionPacket
from radiant.acquisition.adc import ADCResult


_PROTOCOL_VERSION = 1


def _canonical_bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class ExternalAcquisitionFrame:
    sequence: int
    first_sample: int
    sample_rate_hz: int
    channel_ids: tuple[int, ...]
    adc_bits: int
    v_min: float
    v_max: float
    timestamps_ns: np.ndarray
    codes: np.ndarray
    clipped: np.ndarray

    def __post_init__(self):
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence must be a nonnegative integer")
        if type(self.first_sample) is not int or self.first_sample < 0:
            raise ValueError("first_sample must be a nonnegative integer")
        if type(self.sample_rate_hz) is not int or not 1 <= self.sample_rate_hz <= 10**9:
            raise ValueError("sample_rate_hz must be an integer in [1, 1e9]")
        channel_ids = tuple(self.channel_ids)
        if not channel_ids or any(type(item) is not int or item < 0 for item in channel_ids):
            raise ValueError("channel_ids must contain nonnegative integers")
        if len(set(channel_ids)) != len(channel_ids):
            raise ValueError("channel_ids must be unique")
        if type(self.adc_bits) is not int or not 1 <= self.adc_bits <= 24:
            raise ValueError("adc_bits must be an integer from 1 to 24")
        if not (isinstance(self.v_min, (int, float)) and isinstance(self.v_max, (int, float))):
            raise TypeError("ADC limits must be numeric")
        v_min = float(self.v_min)
        v_max = float(self.v_max)
        if not (math.isfinite(v_min) and math.isfinite(v_max) and v_min < v_max):
            raise ValueError("ADC limits must be finite with v_min < v_max")

        timestamps = np.asarray(self.timestamps_ns)
        codes = np.asarray(self.codes)
        clipped = np.asarray(self.clipped)
        if timestamps.ndim != 1 or timestamps.size == 0 or not np.issubdtype(timestamps.dtype, np.integer):
            raise ValueError("timestamps_ns must be a nonempty 1-D integer array")
        if np.any(timestamps < 0) or np.any(np.diff(timestamps.astype(np.int64)) <= 0):
            raise ValueError("timestamps_ns must be nonnegative and strictly increasing")
        if codes.ndim != 2 or codes.shape != (timestamps.size, len(channel_ids)):
            raise ValueError("codes must have shape (samples, channels)")
        if not np.issubdtype(codes.dtype, np.integer):
            raise ValueError("codes must contain integers")
        max_code = (1 << self.adc_bits) - 1
        if np.any(codes < 0) or np.any(codes > max_code):
            raise ValueError("codes exceed configured ADC range")
        if clipped.shape != codes.shape or clipped.dtype != np.bool_:
            raise ValueError("clipped must be a boolean array matching codes")

        object.__setattr__(self, "channel_ids", channel_ids)
        object.__setattr__(self, "v_min", v_min)
        object.__setattr__(self, "v_max", v_max)
        object.__setattr__(self, "timestamps_ns", timestamps.astype(np.int64, copy=True))
        object.__setattr__(self, "codes", codes.astype(np.uint32, copy=True))
        object.__setattr__(self, "clipped", clipped.astype(bool, copy=True))

    @property
    def sample_count(self):
        return int(self.codes.shape[0])

    def to_payload(self):
        return {
            "version": _PROTOCOL_VERSION,
            "sequence": self.sequence,
            "first_sample": self.first_sample,
            "sample_rate_hz": self.sample_rate_hz,
            "channel_ids": list(self.channel_ids),
            "adc_bits": self.adc_bits,
            "v_min": self.v_min,
            "v_max": self.v_max,
            "timestamps_ns": self.timestamps_ns.tolist(),
            "codes": self.codes.tolist(),
            "clipped": self.clipped.tolist(),
        }


def encode_external_frame(frame):
    if not isinstance(frame, ExternalAcquisitionFrame):
        raise TypeError("frame must be ExternalAcquisitionFrame")
    payload = frame.to_payload()
    crc32 = zlib.crc32(_canonical_bytes(payload)) & 0xFFFFFFFF
    return json.dumps(
        {"payload": payload, "crc32": crc32},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def decode_external_frame(line):
    if not isinstance(line, str) or not line.strip():
        raise ValueError("line must be a nonempty string")
    try:
        envelope = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid external-frame JSON") from exc
    if not isinstance(envelope, dict) or set(envelope) != {"payload", "crc32"}:
        raise ValueError("external frame envelope must contain payload and crc32")
    payload = envelope["payload"]
    crc32 = envelope["crc32"]
    if type(crc32) is not int or not 0 <= crc32 <= 0xFFFFFFFF:
        raise ValueError("crc32 must be an unsigned 32-bit integer")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    actual = zlib.crc32(_canonical_bytes(payload)) & 0xFFFFFFFF
    if actual != crc32:
        raise ValueError("external frame CRC mismatch")
    required = {
        "version", "sequence", "first_sample", "sample_rate_hz", "channel_ids",
        "adc_bits", "v_min", "v_max", "timestamps_ns", "codes", "clipped",
    }
    if set(payload) != required:
        raise ValueError("external frame payload has unexpected or missing fields")
    if payload["version"] != _PROTOCOL_VERSION:
        raise ValueError("unsupported external frame protocol version")
    return ExternalAcquisitionFrame(
        sequence=payload["sequence"],
        first_sample=payload["first_sample"],
        sample_rate_hz=payload["sample_rate_hz"],
        channel_ids=tuple(payload["channel_ids"]),
        adc_bits=payload["adc_bits"],
        v_min=payload["v_min"],
        v_max=payload["v_max"],
        timestamps_ns=np.asarray(payload["timestamps_ns"], dtype=np.int64),
        codes=np.asarray(payload["codes"], dtype=np.int64),
        clipped=np.asarray(payload["clipped"], dtype=bool),
    )


class ExternalAcquisitionBridge:
    """Convert validated external frames into native AcquisitionPacket values."""

    def __init__(self, strict_continuity=True):
        if type(strict_continuity) is not bool:
            raise TypeError("strict_continuity must be bool")
        self.strict_continuity = strict_continuity
        self.reset()

    def reset(self):
        self._next_sequence = None
        self._next_sample = None
        self._sample_rate_hz = None
        self._channel_ids = None

    def ingest_line(self, line):
        return self.ingest_frame(decode_external_frame(line))

    def ingest_frame(self, frame):
        if not isinstance(frame, ExternalAcquisitionFrame):
            raise TypeError("frame must be ExternalAcquisitionFrame")
        self._validate_stream(frame)
        lsb = (frame.v_max - frame.v_min) / (1 << frame.adc_bits)
        volts = frame.v_min + (frame.codes.astype(np.float64) + 0.5) * lsb
        packet = AcquisitionPacket(
            frame.sequence,
            frame.first_sample,
            frame.sample_rate_hz,
            frame.channel_ids,
            frame.timestamps_ns.copy(),
            ADCResult(frame.codes.copy(), volts, frame.clipped.copy()),
        )
        self._next_sequence = frame.sequence + 1
        self._next_sample = frame.first_sample + frame.sample_count
        self._sample_rate_hz = frame.sample_rate_hz
        self._channel_ids = frame.channel_ids
        return packet

    def _validate_stream(self, frame):
        if self._next_sequence is None:
            return
        if frame.sample_rate_hz != self._sample_rate_hz:
            raise ValueError("sample rate changed within external acquisition stream")
        if frame.channel_ids != self._channel_ids:
            raise ValueError("channel mapping changed within external acquisition stream")
        if self.strict_continuity:
            if frame.sequence != self._next_sequence:
                raise ValueError("external frame sequence discontinuity")
            if frame.first_sample != self._next_sample:
                raise ValueError("external frame sample discontinuity")
