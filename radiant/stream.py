"""Shared validation and continuity checks for single-consumer streams."""
import numpy as np


def validate_packet(packet):
    for value in (packet.sequence, packet.first_sample, packet.sample_rate_hz):
        if type(value) is not int or value < 0:
            raise ValueError("packet counters and sample rate must be nonnegative integers")
    if not 1 <= packet.sample_rate_hz <= 10**9:
        raise ValueError("sample rate must be in [1, 1e9]")
    ids = packet.channel_ids
    if (not isinstance(ids, tuple) or not ids or
            any(type(i) is not int or i < 0 for i in ids) or len(set(ids)) != len(ids)):
        raise ValueError("channel IDs must be a nonempty tuple of unique nonnegative integers")
    values = np.asarray(packet.data.volts)
    if values.ndim != 2 or values.shape[1] != len(ids) or len(values) == 0:
        raise ValueError("expected nonempty (samples, channels) volts")
    if not np.all(np.isfinite(values)):
        raise ValueError("volts must be finite")
    codes, clipped = np.asarray(packet.data.codes), np.asarray(packet.data.clipped)
    if codes.shape != values.shape or not np.issubdtype(codes.dtype, np.unsignedinteger):
        raise ValueError("codes must be an unsigned integer array matching volts")
    if clipped.shape != values.shape or clipped.dtype != np.bool_:
        raise ValueError("clipped must be a boolean array matching volts")
    stamps = np.asarray(packet.timestamps_ns)
    if stamps.shape != (len(values),) or stamps.dtype != np.int64:
        raise ValueError("timestamps must be an int64 vector matching sample count")
    last = (packet.first_sample + len(values) - 1) * 10**9 // packet.sample_rate_hz
    if last > np.iinfo(np.int64).max:
        raise ValueError("timestamps exceed int64 range")
    expected = np.fromiter((i * 10**9 // packet.sample_rate_hz for i in
                            range(packet.first_sample, packet.first_sample + len(values))),
                           dtype=np.int64, count=len(values))
    if not np.array_equal(stamps, expected):
        raise ValueError("timestamps do not match the nominal sample clock")


def validate_processed(packet):
    validate_packet(packet.source)
    if (packet.volts.shape != packet.source.data.volts.shape or
            not np.all(np.isfinite(packet.volts))):
        raise ValueError("processed volts must be finite and match source shape")
    if packet.valid.shape != packet.volts.shape or packet.valid.dtype != np.bool_:
        raise ValueError("valid must be a boolean array matching processed volts")
    if type(packet.group_delay_samples) is not int or packet.group_delay_samples < 0:
        raise ValueError("group delay must be a nonnegative integer")


class StreamCursor:
    """Check before processing; commit only after successful processing."""

    def __init__(self):
        self.next_sequence = None
        self.next_sample = None
        self.signature = None

    def check(self, packet):
        validate_packet(packet)
        signature = (packet.sample_rate_hz, packet.channel_ids)
        if self.signature is not None and (
                signature != self.signature or packet.sequence != self.next_sequence or
                packet.first_sample != self.next_sample):
            raise ValueError("stream discontinuity: reset explicitly before starting a new stream")

    def commit(self, packet):
        self.next_sequence = packet.sequence + 1
        self.next_sample = packet.first_sample + len(packet.data.volts)
        self.signature = (packet.sample_rate_hz, packet.channel_ids)
