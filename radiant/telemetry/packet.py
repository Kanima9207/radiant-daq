from dataclasses import dataclass
import numpy as np
from radiant.acquisition import AcquisitionPacket


@dataclass(frozen=True)
class ProcessedPacket:
    """Output at the source sample rate, with uncompensated source timestamps.

    valid is false during FIR startup and while a clipped input remains in
    the filter window. Arrays are caller-owned, not made immutable by frozen.
    """

    source: AcquisitionPacket
    volts: np.ndarray
    valid: np.ndarray
    group_delay_samples: int
