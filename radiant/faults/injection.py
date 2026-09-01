from dataclasses import dataclass
import math
import numpy as np


_ALLOWED_KINDS = {"bias", "drift", "stuck", "noise", "saturation"}


@dataclass(frozen=True)
class FaultEvent:
    """Ground-truth description of one injected fault interval.

    ``start_sample`` is inclusive and ``stop_sample`` is exclusive. Parameters:
    bias -> magnitude_volts; drift -> slope_volts_per_sample;
    stuck -> stuck_value_volts; noise -> noise_std_volts;
    saturation -> saturation_value_volts.
    """

    fault_id: int
    kind: str
    channel_id: int
    start_sample: int
    stop_sample: int
    magnitude_volts: float = 0.0
    slope_volts_per_sample: float = 0.0
    stuck_value_volts: float = 0.0
    noise_std_volts: float = 0.0
    saturation_value_volts: float = 12.0

    def __post_init__(self):
        if type(self.fault_id) is not int or self.fault_id < 1:
            raise ValueError("fault_id must be a positive integer")
        if self.kind not in _ALLOWED_KINDS:
            raise ValueError(f"kind must be one of {sorted(_ALLOWED_KINDS)}")
        if type(self.channel_id) is not int or self.channel_id < 0:
            raise ValueError("channel_id must be a nonnegative integer")
        if type(self.start_sample) is not int or self.start_sample < 0:
            raise ValueError("start_sample must be a nonnegative integer")
        if type(self.stop_sample) is not int or self.stop_sample <= self.start_sample:
            raise ValueError("stop_sample must be greater than start_sample")
        for name in ("magnitude_volts", "slope_volts_per_sample", "stuck_value_volts",
                     "noise_std_volts", "saturation_value_volts"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.noise_std_volts < 0:
            raise ValueError("noise_std_volts must be nonnegative")


@dataclass(frozen=True)
class FaultInjectionResult:
    samples: np.ndarray
    fault_ids: np.ndarray

    def __post_init__(self):
        samples = np.asarray(self.samples, dtype=np.float64)
        ids = np.asarray(self.fault_ids)
        if samples.ndim != 2 or ids.shape != samples.shape:
            raise ValueError("samples and fault_ids must have identical 2-D shape")
        if not np.issubdtype(ids.dtype, np.integer):
            raise ValueError("fault_ids must contain integers")
        object.__setattr__(self, "samples", samples.copy())
        object.__setattr__(self, "fault_ids", ids.astype(np.int32, copy=True))

    @property
    def active(self):
        return self.fault_ids != 0


class SensorFaultInjector:
    """Apply scheduled pre-ADC sensor faults with independent ground truth."""

    def __init__(self, events=(), seed=0):
        if seed is not None and type(seed) is not int:
            raise ValueError("seed must be an integer or None")
        self.seed = seed
        self.events = tuple(events)
        ids = [event.fault_id for event in self.events]
        if len(ids) != len(set(ids)):
            raise ValueError("fault_id values must be unique")
        if any(not isinstance(event, FaultEvent) for event in self.events):
            raise TypeError("events must contain FaultEvent objects")
        self._reject_overlaps()

    def _reject_overlaps(self):
        by_channel = {}
        for event in self.events:
            by_channel.setdefault(event.channel_id, []).append(event)
        for channel_events in by_channel.values():
            ordered = sorted(channel_events, key=lambda event: event.start_sample)
            for previous, current in zip(ordered, ordered[1:]):
                if current.start_sample < previous.stop_sample:
                    raise ValueError("fault intervals on the same channel must not overlap")

    def apply(self, samples, first_sample=0, channel_ids=None):
        values = np.asarray(samples, dtype=np.float64)
        if values.ndim != 2 or values.shape[0] == 0 or values.shape[1] == 0:
            raise ValueError("samples must be a nonempty 2-D array")
        if not np.all(np.isfinite(values)):
            raise ValueError("samples must be finite")
        if type(first_sample) is not int or first_sample < 0:
            raise ValueError("first_sample must be a nonnegative integer")
        if channel_ids is None:
            channel_ids = tuple(range(values.shape[1]))
        else:
            channel_ids = tuple(channel_ids)
        if len(channel_ids) != values.shape[1] or len(set(channel_ids)) != len(channel_ids):
            raise ValueError("channel_ids must uniquely match sample columns")
        if any(type(channel_id) is not int or channel_id < 0 for channel_id in channel_ids):
            raise ValueError("channel_ids must contain nonnegative integers")

        output = values.copy()
        truth = np.zeros(values.shape, dtype=np.int32)
        chunk_stop = first_sample + values.shape[0]
        column_for = {channel_id: column for column, channel_id in enumerate(channel_ids)}

        for event in self.events:
            if event.channel_id not in column_for:
                continue
            overlap_start = max(first_sample, event.start_sample)
            overlap_stop = min(chunk_stop, event.stop_sample)
            if overlap_start >= overlap_stop:
                continue
            column = column_for[event.channel_id]
            row0 = overlap_start - first_sample
            row1 = overlap_stop - first_sample
            absolute = np.arange(overlap_start, overlap_stop, dtype=np.int64)

            if event.kind == "bias":
                output[row0:row1, column] += event.magnitude_volts
            elif event.kind == "drift":
                elapsed = absolute - event.start_sample
                output[row0:row1, column] += elapsed * event.slope_volts_per_sample
            elif event.kind == "stuck":
                output[row0:row1, column] = event.stuck_value_volts
            elif event.kind == "noise":
                output[row0:row1, column] += self._indexed_noise(event, absolute)
            elif event.kind == "saturation":
                output[row0:row1, column] = event.saturation_value_volts
            truth[row0:row1, column] = event.fault_id

        return FaultInjectionResult(output, truth)

    def _indexed_noise(self, event, absolute_samples):
        """Generate chunk-invariant Gaussian samples keyed by absolute index."""
        if event.noise_std_volts == 0:
            return np.zeros(len(absolute_samples), dtype=np.float64)
        base_seed = 0 if self.seed is None else self.seed
        result = np.empty(len(absolute_samples), dtype=np.float64)
        for i, sample_index in enumerate(absolute_samples):
            sequence = np.random.SeedSequence([base_seed, event.fault_id, int(sample_index)])
            result[i] = np.random.default_rng(sequence).normal(0.0, event.noise_std_volts)
        return result
