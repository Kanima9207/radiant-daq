"""Hardware-validation adapters for RADIANT-DAQ.

These interfaces support external/hardware-emulated acquisition. They do not
imply validated hardware performance until measurements are performed.
"""
from .bridge import (
    ExternalAcquisitionFrame,
    ExternalAcquisitionBridge,
    encode_external_frame,
    decode_external_frame,
)
from .emulator import HardwareEmulatorConfig, SerialHardwareEmulator

__all__ = [
    "ExternalAcquisitionFrame",
    "ExternalAcquisitionBridge",
    "encode_external_frame",
    "decode_external_frame",
    "HardwareEmulatorConfig",
    "SerialHardwareEmulator",
]
