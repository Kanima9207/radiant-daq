"""Mirrored digital-state integrity protection for FDIR-004.

This is a software protection model for SEU-like experiments. It provides
redundant copies and deterministic CRC-32 fingerprints for scalar configuration
state; it is not a radiation-hard hardware implementation or certification.
"""
from dataclasses import dataclass
import math
import struct
import zlib


@dataclass(frozen=True)
class StateFinding:
    kind: str
    register: str
    detail: str = ""


@dataclass(frozen=True)
class StateIntegrityReport:
    healthy: bool
    findings: tuple[StateFinding, ...]

    @property
    def detected(self):
        return bool(self.findings)


def _validate_name(name):
    if not isinstance(name, str) or not name:
        raise ValueError("register name must be a nonempty string")


def _validate_value(value):
    if type(value) is int:
        if not -(1 << 63) <= value <= (1 << 63) - 1:
            raise ValueError("integer register must fit signed 64-bit range")
        return value
    if isinstance(value, float) and math.isfinite(value):
        return float(value)
    raise ValueError("register value must be a finite int or float scalar")


def _canonical_value_bytes(value):
    value = _validate_value(value)
    if type(value) is int:
        return b"i" + struct.pack(">q", value)
    return b"f" + struct.pack(">d", value)


def state_crc32(name, value):
    """Return deterministic CRC-32 over register identity, type and value."""
    _validate_name(name)
    payload = name.encode("utf-8") + b"\0" + _canonical_value_bytes(value)
    return zlib.crc32(payload) & 0xFFFFFFFF


class MirroredStateBank:
    """Maintain primary/shadow scalar state with independent CRC fingerprints.

    Normal ``write`` updates both copies and their fingerprints. ``inspect``
    reports divergence or checksum failure but performs no automatic repair in
    FDIR-004. The ``replace_*_for_test`` methods are explicit fault-injection
    hooks used by deterministic SEU experiments; production code should not use
    them as ordinary writes.
    """

    def __init__(self, registers):
        if not isinstance(registers, dict) or not registers:
            raise ValueError("registers must be a nonempty dict")
        self._primary = {}
        self._shadow = {}
        self._primary_crc = {}
        self._shadow_crc = {}
        for name, value in registers.items():
            _validate_name(name)
            value = _validate_value(value)
            self._primary[name] = value
            self._shadow[name] = value
            crc = state_crc32(name, value)
            self._primary_crc[name] = crc
            self._shadow_crc[name] = crc

    @property
    def names(self):
        return tuple(self._primary)

    def read(self, name):
        if name not in self._primary:
            raise KeyError(name)
        return self._primary[name]

    def read_shadow(self, name):
        if name not in self._shadow:
            raise KeyError(name)
        return self._shadow[name]

    def write(self, name, value):
        if name not in self._primary:
            raise KeyError(name)
        value = _validate_value(value)
        self._primary[name] = value
        self._shadow[name] = value
        crc = state_crc32(name, value)
        self._primary_crc[name] = crc
        self._shadow_crc[name] = crc

    def inspect(self, name=None):
        names = self.names if name is None else (name,)
        findings = []
        for register in names:
            if register not in self._primary:
                raise KeyError(register)
            primary = self._primary[register]
            shadow = self._shadow[register]
            primary_ok = state_crc32(register, primary) == self._primary_crc[register]
            shadow_ok = state_crc32(register, shadow) == self._shadow_crc[register]
            if not primary_ok:
                findings.append(StateFinding(
                    "primary_crc_failure", register,
                    "primary value does not match its stored fingerprint",
                ))
            if not shadow_ok:
                findings.append(StateFinding(
                    "shadow_crc_failure", register,
                    "shadow value does not match its stored fingerprint",
                ))
            if type(primary) is not type(shadow) or primary != shadow:
                findings.append(StateFinding(
                    "mirror_mismatch", register,
                    "primary and shadow values disagree",
                ))
        return StateIntegrityReport(not findings, tuple(findings))

    def replace_primary_for_test(self, name, value):
        """Inject an unprotected primary-copy value without updating its CRC."""
        if name not in self._primary:
            raise KeyError(name)
        self._primary[name] = _validate_value(value)

    def replace_shadow_for_test(self, name, value):
        """Inject an unprotected shadow-copy value without updating its CRC."""
        if name not in self._shadow:
            raise KeyError(name)
        self._shadow[name] = _validate_value(value)

    def corrupt_primary_crc_for_test(self, name, mask=1):
        """Flip selected bits in the stored primary CRC for fault injection."""
        if name not in self._primary_crc:
            raise KeyError(name)
        if type(mask) is not int or not 0 < mask <= 0xFFFFFFFF:
            raise ValueError("mask must be a nonzero 32-bit integer")
        self._primary_crc[name] ^= mask
