import numpy as np
import pytest

from radiant.acquisition import AcquisitionEngine
from radiant.faults import (
    corrupt_sequence,
    corrupt_timestamp,
    drop_packet,
    duplicate_packet,
    envelope_packet,
    flip_code_bit,
    packet_crc32,
    reorder_adjacent,
    verify_envelope,
)


def make_packets(count=4, rows=8, channels=2):
    engine = AcquisitionEngine(sample_rate_hz=1_000, channels=channels)
    packets = []
    for i in range(count):
        x = np.full((rows, channels), 0.1 * (i + 1), dtype=np.float64)
        packets.append(engine.acquire(x))
    return packets


def test_crc_is_deterministic_for_same_packet():
    packet = make_packets(1)[0]
    assert packet_crc32(packet) == packet_crc32(packet)


def test_envelope_verifies_before_corruption():
    envelope = envelope_packet(make_packets(1)[0])
    assert verify_envelope(envelope)


def test_payload_bit_flip_changes_code_and_breaks_crc():
    envelope = envelope_packet(make_packets(1)[0])
    original = int(envelope.packet.data.codes[2, 1])
    corrupted, truth = flip_code_bit(envelope, 2, 1, 3)
    assert int(corrupted.packet.data.codes[2, 1]) == (original ^ (1 << 3))
    assert truth.kind == "payload_bit_flip"
    assert not verify_envelope(corrupted)
    assert verify_envelope(envelope)


def test_bit_flip_is_detached_from_original_packet():
    envelope = envelope_packet(make_packets(1)[0])
    corrupted, _ = flip_code_bit(envelope, 0, 0, 0)
    corrupted.packet.data.codes[0, 0] ^= np.uint32(2)
    assert verify_envelope(envelope)


def test_timestamp_corruption_breaks_crc_and_preserves_truth():
    envelope = envelope_packet(make_packets(1)[0])
    original = int(envelope.packet.timestamps_ns[3])
    corrupted, truth = corrupt_timestamp(envelope, 3, 250)
    assert int(corrupted.packet.timestamps_ns[3]) == original + 250
    assert truth.kind == "timestamp_corruption"
    assert not verify_envelope(corrupted)


def test_timestamp_overflow_rejected():
    envelope = envelope_packet(make_packets(1)[0])
    envelope.packet.timestamps_ns[-1] = np.iinfo(np.int64).max
    with pytest.raises(OverflowError):
        corrupt_timestamp(envelope, envelope.packet.timestamps_ns.size - 1, 1)


def test_sequence_corruption_breaks_crc():
    envelope = envelope_packet(make_packets(1)[0])
    corrupted, truth = corrupt_sequence(envelope, 99)
    assert corrupted.packet.sequence == 99
    assert truth.original_sequence == 0
    assert truth.kind == "sequence_corruption"
    assert not verify_envelope(corrupted)


def test_drop_packet_records_removed_sequence():
    envelopes = [envelope_packet(p) for p in make_packets()]
    output, truth = drop_packet(envelopes, 1)
    assert [e.packet.sequence for e in output] == [0, 2, 3]
    assert truth.kind == "packet_drop"
    assert truth.original_sequence == 1
    assert truth.output_position == 1


def test_duplicate_packet_inserts_detached_copy():
    envelopes = [envelope_packet(p) for p in make_packets()]
    output, truth = duplicate_packet(envelopes, 1)
    assert [e.packet.sequence for e in output] == [0, 1, 1, 2, 3]
    assert truth.kind == "packet_duplicate"
    assert truth.output_position == 2
    output[2].packet.data.codes[0, 0] ^= np.uint32(1)
    assert verify_envelope(output[1])


def test_reorder_adjacent_swaps_only_selected_pair():
    envelopes = [envelope_packet(p) for p in make_packets()]
    output, truth = reorder_adjacent(envelopes, 1)
    assert [e.packet.sequence for e in output] == [0, 2, 1, 3]
    assert truth.kind == "packet_reorder"
    assert "1 and 2" in truth.detail


def test_stream_fault_operations_do_not_change_crc_of_intact_packets():
    envelopes = [envelope_packet(p) for p in make_packets()]
    dropped, _ = drop_packet(envelopes, 2)
    assert all(verify_envelope(e) for e in dropped)
    duplicated, _ = duplicate_packet(envelopes, 0)
    assert all(verify_envelope(e) for e in duplicated)
    reordered, _ = reorder_adjacent(envelopes, 1)
    assert all(verify_envelope(e) for e in reordered)


@pytest.mark.parametrize(
    "func,args",
    [
        (flip_code_bit, (-1, 0, 0)),
        (flip_code_bit, (0, -1, 0)),
        (flip_code_bit, (0, 0, 32)),
        (corrupt_timestamp, (-1, 1)),
        (corrupt_timestamp, (0, 0)),
        (corrupt_sequence, (-1,)),
    ],
)
def test_invalid_corruption_arguments_rejected(func, args):
    envelope = envelope_packet(make_packets(1)[0])
    with pytest.raises(ValueError):
        func(envelope, *args)


def test_invalid_stream_positions_rejected():
    envelopes = [envelope_packet(p) for p in make_packets(2)]
    with pytest.raises(ValueError):
        drop_packet(envelopes, 2)
    with pytest.raises(ValueError):
        duplicate_packet(envelopes, -1)
    with pytest.raises(ValueError):
        reorder_adjacent(envelopes, 1)
