import numpy as np
import pytest

from radiant.recording import EventRecord


def make_record(**overrides):
    first, n, channels = 100, 5, 2
    timestamps = np.arange(first, first + n, dtype=np.int64) * 20_000
    values = np.arange(n * channels, dtype=float).reshape(n, channels)
    data = dict(
        event_id=0,
        channel_id=0,
        trigger_sample=102,
        trigger_timestamp_ns=int(timestamps[2]),
        trigger_value_volts=1.25,
        packet_sequence=4,
        sample_rate_hz=50_000,
        channel_ids=(0, 1),
        group_delay_samples=31,
        first_sample=first,
        requested_pretrigger_samples=2,
        requested_posttrigger_samples=2,
        pretrigger_complete=True,
        posttrigger_complete=True,
        timestamps_ns=timestamps,
        codes=np.arange(n * channels, dtype=np.uint16).reshape(n, channels),
        raw_volts=values,
        filtered_volts=values / 2,
        clipped=np.zeros((n, channels), dtype=bool),
        valid=np.ones((n, channels), dtype=bool),
    )
    data.update(overrides)
    return EventRecord(**data)


def test_complete_record_exposes_window_bounds():
    record = make_record()
    assert record.sample_count == 5
    assert record.first_sample == 100
    assert record.last_sample == 104
    assert record.complete


def test_record_copies_input_arrays():
    raw = np.zeros((5, 2))
    record = make_record(raw_volts=raw)
    raw[0, 0] = 99.0
    assert record.raw_volts[0, 0] == 0.0


def test_incomplete_startup_history_is_explicit():
    record = make_record(
        first_sample=101,
        requested_pretrigger_samples=2,
        pretrigger_complete=False,
        timestamps_ns=np.arange(101, 106, dtype=np.int64) * 20_000,
        trigger_timestamp_ns=102 * 20_000,
        requested_posttrigger_samples=3,
        posttrigger_complete=True,
    )
    assert not record.pretrigger_complete
    assert not record.complete


def test_rejects_trigger_outside_window():
    with pytest.raises(ValueError, match="trigger_sample"):
        make_record(trigger_sample=99)


def test_rejects_trigger_timestamp_mismatch():
    with pytest.raises(ValueError, match="trigger timestamp"):
        make_record(trigger_timestamp_ns=123)


def test_rejects_wrong_array_shape():
    with pytest.raises(ValueError, match="filtered_volts"):
        make_record(filtered_volts=np.zeros((5, 3)))


def test_rejects_nonmonotonic_timestamps():
    timestamps = np.array([2_000_000, 2_020_000, 2_010_000, 2_060_000, 2_080_000], dtype=np.int64)
    with pytest.raises(ValueError, match="strictly increasing"):
        make_record(timestamps_ns=timestamps, trigger_timestamp_ns=2_010_000)


def test_rejects_false_completeness_claim():
    with pytest.raises(ValueError, match="pretrigger_complete"):
        make_record(requested_pretrigger_samples=3, pretrigger_complete=True)
