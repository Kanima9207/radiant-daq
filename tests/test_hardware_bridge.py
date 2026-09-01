import json

import numpy as np
import pytest

from radiant.hardware import (
    ExternalAcquisitionBridge,
    ExternalAcquisitionFrame,
    decode_external_frame,
    encode_external_frame,
)


def _frame(sequence=0, first_sample=0, channels=(0, 1)):
    timestamps = np.array([0, 20_000, 40_000, 60_000], dtype=np.int64) + first_sample * 20_000
    codes = np.array([
        [0, 32768],
        [16384, 49152],
        [32768, 65535],
        [65535, 0],
    ], dtype=np.uint32)
    clipped = np.zeros_like(codes, dtype=bool)
    return ExternalAcquisitionFrame(
        sequence=sequence,
        first_sample=first_sample,
        sample_rate_hz=50_000,
        channel_ids=channels,
        adc_bits=16,
        v_min=-10.0,
        v_max=10.0,
        timestamps_ns=timestamps,
        codes=codes,
        clipped=clipped,
    )


def test_frame_round_trip_preserves_data():
    frame = _frame()
    decoded = decode_external_frame(encode_external_frame(frame))
    assert decoded.sequence == frame.sequence
    assert decoded.channel_ids == frame.channel_ids
    assert np.array_equal(decoded.timestamps_ns, frame.timestamps_ns)
    assert np.array_equal(decoded.codes, frame.codes)
    assert np.array_equal(decoded.clipped, frame.clipped)


def test_crc_corruption_is_rejected():
    encoded = json.loads(encode_external_frame(_frame()))
    encoded["payload"]["codes"][0][0] = 1
    with pytest.raises(ValueError, match="CRC"):
        decode_external_frame(json.dumps(encoded))


def test_bridge_builds_native_acquisition_packet():
    packet = ExternalAcquisitionBridge().ingest_frame(_frame())
    assert packet.sequence == 0
    assert packet.first_sample == 0
    assert packet.sample_rate_hz == 50_000
    assert packet.channel_ids == (0, 1)
    assert np.array_equal(packet.data.codes, _frame().codes)
    assert np.array_equal(packet.timestamps_ns, _frame().timestamps_ns)


def test_bridge_reconstructs_midpoint_voltage():
    packet = ExternalAcquisitionBridge().ingest_frame(_frame())
    lsb = 20.0 / 65536
    assert packet.data.volts[0, 0] == pytest.approx(-10.0 + 0.5 * lsb)
    assert packet.data.volts[0, 1] == pytest.approx(-10.0 + (32768.5 * lsb))


def test_clip_flags_are_preserved():
    frame = _frame()
    clipped = frame.clipped.copy()
    clipped[2, 1] = True
    frame = ExternalAcquisitionFrame(
        frame.sequence, frame.first_sample, frame.sample_rate_hz, frame.channel_ids,
        frame.adc_bits, frame.v_min, frame.v_max, frame.timestamps_ns, frame.codes, clipped,
    )
    packet = ExternalAcquisitionBridge().ingest_frame(frame)
    assert packet.data.clipped[2, 1]


def test_strict_bridge_rejects_sequence_gap():
    bridge = ExternalAcquisitionBridge()
    bridge.ingest_frame(_frame(sequence=0, first_sample=0))
    with pytest.raises(ValueError, match="sequence discontinuity"):
        bridge.ingest_frame(_frame(sequence=2, first_sample=4))


def test_strict_bridge_rejects_sample_gap():
    bridge = ExternalAcquisitionBridge()
    bridge.ingest_frame(_frame(sequence=0, first_sample=0))
    with pytest.raises(ValueError, match="sample discontinuity"):
        bridge.ingest_frame(_frame(sequence=1, first_sample=8))


def test_bridge_rejects_stream_configuration_change():
    bridge = ExternalAcquisitionBridge()
    bridge.ingest_frame(_frame(sequence=0, first_sample=0))
    changed = _frame(sequence=1, first_sample=4, channels=(1, 2))
    with pytest.raises(ValueError, match="channel mapping"):
        bridge.ingest_frame(changed)


def test_non_strict_bridge_allows_sequence_and_sample_discontinuity():
    bridge = ExternalAcquisitionBridge(strict_continuity=False)
    bridge.ingest_frame(_frame(sequence=0, first_sample=0))
    packet = bridge.ingest_frame(_frame(sequence=7, first_sample=40))
    assert packet.sequence == 7
    assert packet.first_sample == 40


def test_reset_starts_a_new_external_stream():
    bridge = ExternalAcquisitionBridge()
    bridge.ingest_frame(_frame(sequence=0, first_sample=0))
    bridge.reset()
    packet = bridge.ingest_frame(_frame(sequence=10, first_sample=100))
    assert packet.sequence == 10
    assert packet.first_sample == 100
