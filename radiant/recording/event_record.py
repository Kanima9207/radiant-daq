from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class EventRecord:
    """Self-contained sample window associated with one trigger event.

    Arrays are copied on construction so later caller mutation cannot alter the
    captured event. A frozen dataclass does not make NumPy arrays immutable.
    """

    event_id: int
    channel_id: int
    trigger_sample: int
    trigger_timestamp_ns: int
    trigger_value_volts: float
    packet_sequence: int
    sample_rate_hz: int
    channel_ids: tuple[int, ...]
    group_delay_samples: int
    first_sample: int
    requested_pretrigger_samples: int
    requested_posttrigger_samples: int
    pretrigger_complete: bool
    posttrigger_complete: bool
    timestamps_ns: np.ndarray
    codes: np.ndarray
    raw_volts: np.ndarray
    filtered_volts: np.ndarray
    clipped: np.ndarray
    valid: np.ndarray

    def __post_init__(self):
        if type(self.event_id) is not int or self.event_id < 0:
            raise ValueError("event_id must be a nonnegative integer")
        if type(self.sample_rate_hz) is not int or self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be a positive integer")
        if not self.channel_ids:
            raise ValueError("channel_ids must not be empty")
        if len(set(self.channel_ids)) != len(self.channel_ids):
            raise ValueError("channel_ids must be unique")
        if self.channel_id not in self.channel_ids:
            raise ValueError("trigger channel is not present in channel_ids")
        if type(self.group_delay_samples) is not int or self.group_delay_samples < 0:
            raise ValueError("group_delay_samples must be nonnegative")
        if type(self.first_sample) is not int or self.first_sample < 0:
            raise ValueError("first_sample must be nonnegative")
        for name in ("requested_pretrigger_samples", "requested_posttrigger_samples"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")

        arrays = {
            "timestamps_ns": np.asarray(self.timestamps_ns),
            "codes": np.asarray(self.codes),
            "raw_volts": np.asarray(self.raw_volts),
            "filtered_volts": np.asarray(self.filtered_volts),
            "clipped": np.asarray(self.clipped),
            "valid": np.asarray(self.valid),
        }
        timestamps = arrays["timestamps_ns"]
        if timestamps.ndim != 1 or len(timestamps) == 0:
            raise ValueError("timestamps_ns must be a nonempty 1-D array")
        n, channels = len(timestamps), len(self.channel_ids)
        expected = (n, channels)
        for name in ("codes", "raw_volts", "filtered_volts", "clipped", "valid"):
            if arrays[name].shape != expected:
                raise ValueError(f"{name} must have shape {expected}")
        if not np.issubdtype(timestamps.dtype, np.integer):
            raise ValueError("timestamps_ns must contain integers")
        if n > 1 and np.any(np.diff(timestamps.astype(np.int64)) <= 0):
            raise ValueError("timestamps_ns must be strictly increasing")

        last_sample = self.first_sample + n - 1
        if not self.first_sample <= self.trigger_sample <= last_sample:
            raise ValueError("trigger_sample must lie inside the event window")
        trigger_row = self.trigger_sample - self.first_sample
        if int(timestamps[trigger_row]) != self.trigger_timestamp_ns:
            raise ValueError("trigger timestamp does not match captured sample")

        actual_pre = self.trigger_sample - self.first_sample
        actual_post = last_sample - self.trigger_sample
        if self.pretrigger_complete != (actual_pre >= self.requested_pretrigger_samples):
            raise ValueError("pretrigger_complete is inconsistent with captured history")
        if self.posttrigger_complete != (actual_post >= self.requested_posttrigger_samples):
            raise ValueError("posttrigger_complete is inconsistent with captured history")

        for name, array in arrays.items():
            object.__setattr__(self, name, array.copy())

    @property
    def sample_count(self):
        return len(self.timestamps_ns)

    @property
    def last_sample(self):
        return self.first_sample + self.sample_count - 1

    @property
    def complete(self):
        return self.pretrigger_complete and self.posttrigger_complete
