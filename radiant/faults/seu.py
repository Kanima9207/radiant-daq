"""Deterministic SEU-like digital-state fault injection.

These helpers model bit-level corruption in software state. They are fault-
injection abstractions only; they do not model particle energy, device cross
sections, FPGA technology, radiation dose, or physical upset probability.
"""
from dataclasses import dataclass
import math
import struct
import numpy as np


@dataclass(frozen=True)
class SEUFaultRecord:
    target: str
    bit_index: int
    before: object
    after: object
    persistent: bool


def flip_integer_bit(value, bit_index, width=32, signed=False):
    """Return an integer with one bit flipped in a fixed-width representation."""
    if type(value) is not int:
        raise TypeError("value must be an integer")
    if type(width) is not int or width < 1 or width > 64:
        raise ValueError("width must be an integer in [1, 64]")
    if type(bit_index) is not int or not 0 <= bit_index < width:
        raise ValueError("bit_index must lie within width")
    if type(signed) is not bool:
        raise TypeError("signed must be bool")
    lo = -(1 << (width - 1)) if signed else 0
    hi = (1 << (width - 1)) - 1 if signed else (1 << width) - 1
    if not lo <= value <= hi:
        raise ValueError("value does not fit requested representation")
    raw = value & ((1 << width) - 1)
    raw ^= 1 << bit_index
    if signed and raw >= (1 << (width - 1)):
        raw -= 1 << width
    return raw


def flip_float64_bit(value, bit_index):
    """Flip one IEEE-754 binary64 bit and return the resulting Python float."""
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError("value must be finite")
    if type(bit_index) is not int or not 0 <= bit_index < 64:
        raise ValueError("bit_index must be in [0, 63]")
    raw = struct.unpack("<Q", struct.pack("<d", float(value)))[0]
    raw ^= 1 << bit_index
    return struct.unpack("<d", struct.pack("<Q", raw))[0]


def flip_array_element_bit(array, index, bit_index):
    """Copy an integer/float array and flip one bit of one scalar element."""
    values = np.asarray(array)
    if values.ndim == 0:
        raise ValueError("array must have at least one dimension")
    if not (np.issubdtype(values.dtype, np.integer) or
            np.issubdtype(values.dtype, np.floating)):
        raise TypeError("array dtype must be integer or floating")
    try:
        before = values[index].item()
    except (IndexError, TypeError) as exc:
        raise ValueError("index must select exactly one array element") from exc
    if isinstance(values[index], np.ndarray):
        raise ValueError("index must select exactly one array element")
    width = values.dtype.itemsize * 8
    if type(bit_index) is not int or not 0 <= bit_index < width:
        raise ValueError("bit_index must lie within element width")
    result = values.copy()
    byte_view = result.view(np.uint8).reshape(result.shape + (values.dtype.itemsize,))
    byte_number, bit_number = divmod(bit_index, 8)
    byte_view[index + (byte_number,)] ^= np.uint8(1 << bit_number)
    return result, before, result[index].item()


class DigitalStateBank:
    """Small typed register bank with ground-truth upset bookkeeping.

    Persistent faults alter stored state. Transient faults return a corrupted
    read value while preserving the underlying register. No recovery or
    detection is performed here.
    """
    def __init__(self, registers):
        if not isinstance(registers, dict) or not registers:
            raise ValueError("registers must be a nonempty dict")
        self._registers = {}
        for name, value in registers.items():
            if not isinstance(name, str) or not name:
                raise ValueError("register names must be nonempty strings")
            if type(value) is int:
                self._registers[name] = value
            elif isinstance(value, (int, float)) and math.isfinite(float(value)):
                self._registers[name] = float(value)
            else:
                raise ValueError("register values must be finite int/float scalars")
        self.records = []

    def read(self, name):
        if name not in self._registers:
            raise KeyError(name)
        return self._registers[name]

    def inject_integer(self, name, bit_index, width=32, signed=False, persistent=True):
        before = self.read(name)
        if type(before) is not int:
            raise TypeError("target register is not integer-valued")
        after = flip_integer_bit(before, bit_index, width=width, signed=signed)
        if persistent:
            self._registers[name] = after
        record = SEUFaultRecord(name, bit_index, before, after, bool(persistent))
        self.records.append(record)
        return after

    def inject_float64(self, name, bit_index, persistent=True):
        before = self.read(name)
        if type(before) is int:
            raise TypeError("target register is not floating-point")
        after = flip_float64_bit(before, bit_index)
        if persistent:
            self._registers[name] = after
        record = SEUFaultRecord(name, bit_index, before, after, bool(persistent))
        self.records.append(record)
        return after
