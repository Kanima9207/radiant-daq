import numpy as np

from .event_record import EventRecord


def replay_event(record):
    """Return detached arrays for deterministic offline processing/replay.

    Replay preserves the exact stored sample order and metadata. The returned
    arrays are copies so offline analysis cannot mutate the EventRecord.
    """
    if not isinstance(record, EventRecord):
        raise TypeError("record must be an EventRecord")
    return {
        "first_sample": record.first_sample,
        "last_sample": record.last_sample,
        "sample_rate_hz": record.sample_rate_hz,
        "channel_ids": record.channel_ids,
        "trigger_sample": record.trigger_sample,
        "trigger_timestamp_ns": record.trigger_timestamp_ns,
        "timestamps_ns": record.timestamps_ns.copy(),
        "codes": record.codes.copy(),
        "raw_volts": record.raw_volts.copy(),
        "filtered_volts": record.filtered_volts.copy(),
        "clipped": record.clipped.copy(),
        "valid": record.valid.copy(),
    }
