import numpy as np

from radiant.acquisition import AcquisitionEngine
from radiant.buffer import SampleRingBuffer
from radiant.recording import FlightRecorder
from radiant.telemetry import ProcessedPacket
from radiant.trigger import ThresholdTrigger


def processed(engine, values):
    source = engine.acquire(values)
    return ProcessedPacket(source, source.data.volts.copy(),
                           np.ones(source.data.volts.shape, dtype=bool), 0)


def test_cross_chunk_event_capture_completes_after_future_samples():
    engine = AcquisitionEngine(sample_rate_hz=1000, channels=1)
    trigger = ThresholdTrigger(high=1.0, low=0.5)
    ring = SampleRingBuffer(16, channels=1)
    recorder = FlightRecorder(pretrigger_samples=3, posttrigger_samples=4)

    a = processed(engine, [[0], [0], [0], [0], [0], [0]])
    ring.append(a)
    assert recorder.process(trigger.process(a), ring) == []

    b = processed(engine, [[0], [2]])
    ring.append(b)
    events = trigger.process(b)
    assert [e.sample_index for e in events] == [7]
    assert recorder.process(events, ring) == []
    assert recorder.pending_count == 1

    c = processed(engine, [[2], [2], [2], [2], [0]])
    ring.append(c)
    records = recorder.process(trigger.process(c), ring)
    assert len(records) == 1
    record = records[0]
    assert record.first_sample == 4
    assert record.last_sample == 11
    assert record.trigger_sample == 7
    assert record.sample_count == 8
    assert record.complete
    np.testing.assert_array_equal(record.timestamps_ns,
                                  np.arange(4, 12, dtype=np.int64) * 1_000_000)


def test_startup_event_marks_missing_pretrigger_history():
    engine = AcquisitionEngine(sample_rate_hz=1000, channels=1)
    trigger = ThresholdTrigger(high=1.0, low=0.5)
    ring = SampleRingBuffer(8, channels=1)
    recorder = FlightRecorder(pretrigger_samples=3, posttrigger_samples=2)

    a = processed(engine, [[0], [2]])
    ring.append(a)
    events = trigger.process(a)
    assert [e.sample_index for e in events] == [1]
    assert recorder.process(events, ring) == []

    b = processed(engine, [[2], [2]])
    ring.append(b)
    records = recorder.process(trigger.process(b), ring)
    assert len(records) == 1
    record = records[0]
    assert record.first_sample == 0
    assert record.last_sample == 3
    assert not record.pretrigger_complete
    assert record.posttrigger_complete
    assert not record.complete


def test_multiple_pending_events_complete_in_order():
    engine = AcquisitionEngine(sample_rate_hz=1000, channels=1)
    trigger = ThresholdTrigger(high=1.0, low=0.5)
    ring = SampleRingBuffer(20, channels=1)
    recorder = FlightRecorder(pretrigger_samples=1, posttrigger_samples=3)

    block = processed(engine, [[0], [2], [0], [2]])
    ring.append(block)
    events = trigger.process(block)
    assert [e.sample_index for e in events] == [1, 3]
    assert recorder.process(events, ring) == []
    assert recorder.pending_count == 2

    tail = processed(engine, [[0], [0], [0], [0]])
    ring.append(tail)
    records = recorder.process(trigger.process(tail), ring)
    assert [r.event_id for r in records] == [0, 1]
    assert [r.trigger_sample for r in records] == [1, 3]
    assert recorder.pending_count == 0


def test_zero_posttrigger_can_complete_immediately():
    engine = AcquisitionEngine(sample_rate_hz=1000, channels=1)
    trigger = ThresholdTrigger(high=1.0, low=0.5)
    ring = SampleRingBuffer(8, channels=1)
    recorder = FlightRecorder(pretrigger_samples=1, posttrigger_samples=0)

    block = processed(engine, [[0], [2]])
    ring.append(block)
    records = recorder.process(trigger.process(block), ring)
    assert len(records) == 1
    assert records[0].trigger_sample == records[0].last_sample == 1


def test_recorder_reset_discards_pending_and_restarts_ids():
    engine = AcquisitionEngine(sample_rate_hz=1000, channels=1)
    trigger = ThresholdTrigger(high=1.0, low=0.5)
    ring = SampleRingBuffer(8, channels=1)
    recorder = FlightRecorder(pretrigger_samples=1, posttrigger_samples=2)

    block = processed(engine, [[0], [2]])
    ring.append(block)
    assert recorder.process(trigger.process(block), ring) == []
    assert recorder.pending_count == 1
    recorder.reset()
    assert recorder.pending_count == 0


def test_bad_recorder_configuration_rejected():
    for kwargs in ({"pretrigger_samples": -1}, {"posttrigger_samples": -1},
                   {"pretrigger_samples": True}, {"posttrigger_samples": 1.5}):
        try:
            FlightRecorder(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid recorder configuration was accepted")
