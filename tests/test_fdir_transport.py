import numpy as np
import pytest

from radiant.acquisition import AcquisitionEngine
from radiant.faults import (
    envelope_packet,
    flip_code_bit,
    corrupt_timestamp,
    drop_packet,
    duplicate_packet,
    reorder_adjacent,
)
from radiant.fdir import TransportIntegrityMonitor


def make_envelopes(count=4):
    engine = AcquisitionEngine(sample_rate_hz=1000, channels=1)
    packets = []
    for _ in range(count):
        packets.append(envelope_packet(engine.acquire(np.zeros((4, 1)))))
    return packets


def test_healthy_stream_has_no_findings():
    monitor = TransportIntegrityMonitor()
    reports = monitor.inspect_stream(make_envelopes())
    assert all(report.accepted for report in reports)
    assert all(not report.detected for report in reports)
    assert monitor.next_sequence == 4


def test_payload_corruption_detected_by_crc_and_state_not_advanced():
    envelopes = make_envelopes(3)
    monitor = TransportIntegrityMonitor()
    assert monitor.inspect(envelopes[0]).accepted
    bad, _ = flip_code_bit(envelopes[1], 0, 0, 0)
    report = monitor.inspect(bad)
    assert not report.accepted
    assert report.findings[0].kind == "crc_failure"
    assert monitor.next_sequence == 1
    # The original sequence 1 can still be accepted afterward.
    assert monitor.inspect(envelopes[1]).accepted


def test_timestamp_corruption_detected_by_crc():
    envelope = make_envelopes(1)[0]
    bad, _ = corrupt_timestamp(envelope, 0, 100)
    report = TransportIntegrityMonitor().inspect(bad)
    assert report.detected
    assert report.findings[0].kind == "crc_failure"


def test_packet_drop_detected_as_gap_and_resynchronizes():
    envelopes, _ = drop_packet(make_envelopes(4), 1)
    monitor = TransportIntegrityMonitor()
    reports = monitor.inspect_stream(envelopes)
    assert reports[1].findings[0].kind == "gap"
    assert reports[1].findings[0].expected_sequence == 1
    assert reports[2].accepted
    assert monitor.next_sequence == 4


def test_duplicate_detected_without_advancing_state():
    envelopes, _ = duplicate_packet(make_envelopes(3), 1)
    monitor = TransportIntegrityMonitor()
    reports = monitor.inspect_stream(envelopes)
    assert reports[2].findings[0].kind == "duplicate"
    assert not reports[2].accepted
    assert reports[3].accepted
    assert monitor.next_sequence == 3


def test_reorder_detects_gap_then_old_packet():
    envelopes, _ = reorder_adjacent(make_envelopes(4), 1)
    reports = TransportIntegrityMonitor().inspect_stream(envelopes)
    assert reports[1].findings[0].kind == "gap"
    assert reports[2].findings[0].kind == "reorder"
    assert reports[3].accepted


def test_first_packet_establishes_baseline_even_if_sequence_nonzero():
    envelopes = make_envelopes(3)
    report = TransportIntegrityMonitor().inspect(envelopes[2])
    assert report.accepted
    assert not report.detected


def test_reset_allows_new_stream():
    monitor = TransportIntegrityMonitor()
    envelopes = make_envelopes(2)
    monitor.inspect_stream(envelopes)
    monitor.reset()
    assert monitor.next_sequence is None
    assert monitor.inspect(envelopes[0]).accepted


def test_invalid_input_rejected():
    with pytest.raises(TypeError):
        TransportIntegrityMonitor().inspect(object())


def test_gap_detail_counts_multiple_missing_sequences():
    envelopes = make_envelopes(5)
    monitor = TransportIntegrityMonitor()
    monitor.inspect(envelopes[0])
    report = monitor.inspect(envelopes[4])
    assert report.findings[0].kind == "gap"
    assert "missing 3" in report.findings[0].detail
