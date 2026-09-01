"""Deterministic clock/timestamp fault injection for simulated timing studies.

This module perturbs readings from an existing reference clock model. It does
not represent a physical oscillator implementation or measured hardware timing.
"""
from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class ClockFaultEvent:
    fault_id: int
    kind: str
    start_reference_ns: int
    end_reference_ns: int | None = None
    magnitude: float = 0.0

    def __post_init__(self):
        if type(self.fault_id) is not int or self.fault_id <= 0:
            raise ValueError("fault_id must be a positive integer")
        if self.kind not in {"jump", "drift_change", "freeze"}:
            raise ValueError("unsupported clock fault kind")
        if type(self.start_reference_ns) is not int or self.start_reference_ns < 0:
            raise ValueError("start_reference_ns must be a nonnegative integer")
        if self.end_reference_ns is not None:
            if type(self.end_reference_ns) is not int or self.end_reference_ns <= self.start_reference_ns:
                raise ValueError("end_reference_ns must be greater than start_reference_ns")
        if not isinstance(self.magnitude, (int, float)) or not math.isfinite(float(self.magnitude)):
            raise ValueError("magnitude must be finite")
        if self.kind == "freeze" and self.end_reference_ns is None:
            raise ValueError("freeze faults require a finite end_reference_ns")


@dataclass(frozen=True)
class ClockFaultResult:
    timestamps_ns: np.ndarray
    fault_ids: np.ndarray


class FaultedClock:
    """Wrap a simulated clock and inject explicit timestamp-domain faults.

    ``jump`` adds a constant nanosecond offset after the event start (or only
    inside a finite interval when end_reference_ns is supplied).

    ``drift_change`` adds an additional slope expressed in ppm, beginning at
    the event start. For finite intervals the accumulated extra phase is held
    after the interval so timestamps remain continuous.

    ``freeze`` holds the timestamp at its value at the fault start for the
    specified reference-time interval, then resumes with the corresponding
    lost elapsed time still visible as an offset.
    """
    def __init__(self, base_clock, events=()):
        if not hasattr(base_clock, "read"):
            raise TypeError("base_clock must provide read(reference_ns)")
        self.base_clock = base_clock
        self.events = tuple(sorted(events, key=lambda e: (e.start_reference_ns, e.fault_id)))
        for event in self.events:
            if not isinstance(event, ClockFaultEvent):
                raise TypeError("events must contain ClockFaultEvent instances")
        for first, second in zip(self.events, self.events[1:]):
            first_end = first.end_reference_ns
            if first_end is None or first_end > second.start_reference_ns:
                raise ValueError("clock fault intervals must not overlap")

    def reset(self):
        if hasattr(self.base_clock, "reset"):
            self.base_clock.reset()

    def read_with_truth(self, reference_ns):
        scalar = np.isscalar(reference_ns)
        refs = np.asarray([reference_ns] if scalar else reference_ns)
        if refs.ndim != 1 or refs.size == 0 or not np.issubdtype(refs.dtype, np.integer):
            raise ValueError("reference_ns must be an integer scalar or nonempty 1-D integer array")
        refs = refs.astype(np.int64, copy=False)
        if np.any(refs < 0):
            raise ValueError("reference_ns must be nonnegative")
        if refs.size > 1 and np.any(np.diff(refs) < 0):
            raise ValueError("reference_ns must be nondecreasing")

        base = np.asarray(self.base_clock.read(refs), dtype=np.int64)
        result = base.astype(object)
        truth = np.zeros(refs.size, dtype=np.int32)

        for event in self.events:
            start = event.start_reference_ns
            end = event.end_reference_ns
            active = refs >= start
            if end is not None:
                active &= refs < end

            if event.kind == "jump":
                delta = int(round(event.magnitude))
                for idx in np.flatnonzero(active):
                    result[idx] = int(result[idx]) + delta
                truth[active] = event.fault_id

            elif event.kind == "drift_change":
                ppm = float(event.magnitude)
                elapsed = np.maximum(refs.astype(object) - start, 0)
                if end is not None:
                    elapsed = np.minimum(elapsed, end - start)
                extra = np.rint(np.asarray(elapsed, dtype=np.longdouble) * np.longdouble(ppm) * np.longdouble(1e-6)).astype(object)
                affected = refs >= start
                for idx in np.flatnonzero(affected):
                    result[idx] = int(result[idx]) + int(extra[idx])
                truth[active] = event.fault_id

            elif event.kind == "freeze":
                freeze_value = int(np.asarray(self.base_clock.read(start), dtype=np.int64).item())
                for idx in np.flatnonzero(active):
                    result[idx] = freeze_value
                after = refs >= end
                lost = end - start
                for idx in np.flatnonzero(after):
                    result[idx] = int(result[idx]) - lost
                truth[active] = event.fault_id

        limit = np.iinfo(np.int64)
        if any(v < limit.min or v > limit.max for v in result):
            raise OverflowError("faulted timestamp exceeds signed 64-bit nanoseconds")
        timestamps = np.asarray(result, dtype=np.int64)
        payload = ClockFaultResult(timestamps, truth)
        if scalar:
            return int(timestamps[0]), int(truth[0])
        return payload

    def read(self, reference_ns):
        result = self.read_with_truth(reference_ns)
        if isinstance(result, tuple):
            return result[0]
        return result.timestamps_ns
