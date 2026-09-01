import json

import numpy as np
import pytest

from radiant.recording import EventRecord, EventStore, replay_event


def make_record(event_id=7):
    first, n, channels = 100, 5, 2
    timestamps = np.arange(first, first + n, dtype=np.int64) * 20_000
    values = np.arange(n * channels, dtype=float).reshape(n, channels)
    return EventRecord(
        event_id=event_id,
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


def assert_same_record(a, b):
    scalar_fields = (
        "event_id", "channel_id", "trigger_sample", "trigger_timestamp_ns",
        "trigger_value_volts", "packet_sequence", "sample_rate_hz", "channel_ids",
        "group_delay_samples", "first_sample", "requested_pretrigger_samples",
        "requested_posttrigger_samples", "pretrigger_complete", "posttrigger_complete",
    )
    for name in scalar_fields:
        assert getattr(a, name) == getattr(b, name)
    for name in ("timestamps_ns", "codes", "raw_volts", "filtered_volts", "clipped", "valid"):
        np.testing.assert_array_equal(getattr(a, name), getattr(b, name))


def test_round_trip_preserves_record(tmp_path):
    store = EventStore(tmp_path)
    original = make_record()
    path = store.save(original)
    assert path.name == "event_000007"
    assert {p.name for p in path.iterdir()} == {"metadata.json", "samples.npz", "checksum.sha256"}
    restored = store.load(7)
    assert_same_record(original, restored)


def test_metadata_is_human_readable_and_versioned(tmp_path):
    path = EventStore(tmp_path).save(make_record())
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["format"] == "radiant-event"
    assert metadata["version"] == 1
    assert metadata["event"]["trigger_sample"] == 102


def test_payload_corruption_is_detected_before_load(tmp_path):
    store = EventStore(tmp_path)
    path = store.save(make_record())
    payload = path / "samples.npz"
    data = bytearray(payload.read_bytes())
    data[len(data) // 2] ^= 0x01
    payload.write_bytes(data)
    with pytest.raises(ValueError, match="integrity"):
        store.load(path)


def test_metadata_corruption_is_detected_before_replay(tmp_path):
    store = EventStore(tmp_path)
    path = store.save(make_record())
    metadata = path / "metadata.json"
    text = metadata.read_text(encoding="utf-8").replace('"trigger_sample":102', '"trigger_sample":103')
    metadata.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        store.load(path)


def test_duplicate_event_is_not_silently_overwritten(tmp_path):
    store = EventStore(tmp_path)
    store.save(make_record())
    with pytest.raises(FileExistsError):
        store.save(make_record())


def test_missing_component_is_rejected(tmp_path):
    store = EventStore(tmp_path)
    path = store.save(make_record())
    (path / "checksum.sha256").unlink()
    with pytest.raises(FileNotFoundError, match="checksum.sha256"):
        store.load(path)


def test_replay_is_deterministic_and_detached(tmp_path):
    store = EventStore(tmp_path)
    restored = store.load(store.save(make_record()))
    first = replay_event(restored)
    second = replay_event(restored)
    for name in ("timestamps_ns", "codes", "raw_volts", "filtered_volts", "clipped", "valid"):
        np.testing.assert_array_equal(first[name], second[name])
    first["raw_volts"][0, 0] = -999
    assert restored.raw_volts[0, 0] != -999
    assert second["raw_volts"][0, 0] != -999


def test_bad_event_id_and_wrong_save_type(tmp_path):
    store = EventStore(tmp_path)
    with pytest.raises(ValueError):
        store.event_path(-1)
    with pytest.raises(TypeError):
        store.save(object())
    with pytest.raises(TypeError):
        replay_event(object())
