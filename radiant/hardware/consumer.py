"""Serial-like live acquisition consumer for HW-003.

Reads newline-delimited external frames from any object exposing ``readline()``,
validates them through HW-001, and records host-side ingestion throughput and
failures. Host timing metrics describe this Python consumer only; they are not
hardware real-time or device timing guarantees.
"""
from dataclasses import dataclass
import time

from .bridge import ExternalAcquisitionBridge


@dataclass(frozen=True)
class ConsumerStats:
    frames_received: int
    frames_accepted: int
    frames_rejected: int
    samples_accepted: int
    elapsed_s: float

    @property
    def frame_acceptance_pct(self):
        return 100.0 if self.frames_received == 0 else 100.0 * self.frames_accepted / self.frames_received

    @property
    def samples_per_second(self):
        return 0.0 if self.elapsed_s <= 0.0 else self.samples_accepted / self.elapsed_s


class LiveSerialConsumer:
    """Consume a serial-compatible source into native acquisition packets."""

    def __init__(self, source, bridge=None, clock=None):
        if not hasattr(source, "readline") or not callable(source.readline):
            raise TypeError("source must provide callable readline()")
        self.source = source
        self.bridge = ExternalAcquisitionBridge() if bridge is None else bridge
        if not isinstance(self.bridge, ExternalAcquisitionBridge):
            raise TypeError("bridge must be ExternalAcquisitionBridge")
        self._clock = time.perf_counter if clock is None else clock
        if not callable(self._clock):
            raise TypeError("clock must be callable")
        self.reset_stats()

    def reset_stats(self):
        self._received = 0
        self._accepted = 0
        self._rejected = 0
        self._samples = 0
        self._elapsed = 0.0
        self.last_error = None

    @property
    def stats(self):
        return ConsumerStats(self._received, self._accepted, self._rejected,
                             self._samples, self._elapsed)

    def read_one(self):
        start = float(self._clock())
        raw = self.source.readline()
        self._received += 1
        try:
            if isinstance(raw, bytes):
                line = raw.decode("utf-8")
            elif isinstance(raw, str):
                line = raw
            else:
                raise TypeError("readline() must return bytes or str")
            if not line.strip():
                raise ValueError("source returned an empty frame")
            packet = self.bridge.ingest_line(line.strip())
        except (UnicodeDecodeError, TypeError, ValueError) as exc:
            self._rejected += 1
            self.last_error = str(exc)
            self._elapsed += max(0.0, float(self._clock()) - start)
            return None
        self._accepted += 1
        self._samples += len(packet.timestamps_ns)
        self.last_error = None
        self._elapsed += max(0.0, float(self._clock()) - start)
        return packet

    def run(self, frames, *, stop_on_error=False):
        if type(frames) is not int or frames < 1:
            raise ValueError("frames must be a positive integer")
        if type(stop_on_error) is not bool:
            raise TypeError("stop_on_error must be bool")
        packets = []
        for _ in range(frames):
            packet = self.read_one()
            if packet is None:
                if stop_on_error:
                    break
                continue
            packets.append(packet)
        return tuple(packets)
