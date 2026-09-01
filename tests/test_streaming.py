from dataclasses import replace
import numpy as np
import pytest

from radiant.acquisition import AcquisitionEngine
from radiant.buffer import SampleRingBuffer
from radiant.dsp import FIRPipeline, lowpass_taps
from radiant.telemetry import ProcessedPacket
from radiant.trigger import ThresholdTrigger


def processed(engine, values):
    source = engine.acquire(values)
    return ProcessedPacket(source, source.data.volts.copy(),
                           np.ones(source.data.volts.shape, dtype=bool), 0)


def test_fir_matches_independent_convolution_across_unequal_chunks():
    taps = lowpass_taps(50_000)
    values = np.random.default_rng(7).uniform(-4, 4, (311, 8))
    engine = AcquisitionEngine()
    pipeline = FIRPipeline(taps)
    raw, outputs = [], []
    for part in np.split(values, [1, 8, 62, 64, 201]):
        packet = engine.acquire(part)
        raw.append(packet.data.volts)
        outputs.append(pipeline.process(packet))
    expected = np.column_stack([np.convolve(np.concatenate(raw)[:, ch], taps)[:311]
                                for ch in range(8)])
    np.testing.assert_allclose(np.concatenate([p.volts for p in outputs]), expected,
                               rtol=1e-12, atol=1e-12)
    valid = np.concatenate([p.valid for p in outputs])
    assert not valid[:62].any()
    assert valid[62:].all()
    assert outputs[0].group_delay_samples == 31
    assert outputs[1].source.first_sample == 1


def test_filter_response_and_impulse_delay():
    taps = lowpass_taps(50_000)
    n = np.arange(len(taps))
    gain = lambda hz: abs(np.sum(taps * np.exp(-2j * np.pi * hz * n / 50_000)))
    assert abs(taps.sum() - 1) < 1e-12
    assert 0.99 < gain(1000) < 1.01
    assert gain(10_000) < 0.01  # At least 40 dB rejection at this test frequency.
    impulse = np.zeros((130, 1))
    impulse[0] = 1
    source = AcquisitionEngine(channels=1).acquire(impulse)
    result = FIRPipeline(taps).process(source)
    assert np.argmax(result.volts[:, 0]) == result.group_delay_samples == 31


def test_clipping_invalidates_full_filter_window_across_chunks():
    engine = AcquisitionEngine(channels=1)
    pipeline = FIRPipeline([0.25, 0.5, 0.25])
    a = pipeline.process(engine.acquire(np.array([[0], [0], [0], [12]])))
    b = pipeline.process(engine.acquire(np.zeros((4, 1))))
    np.testing.assert_array_equal(a.valid[:, 0], [False, False, True, False])
    np.testing.assert_array_equal(b.valid[:, 0], [False, False, True, True])


def test_fir_channel_independence_and_identity():
    engine = AcquisitionEngine(channels=2)
    source = engine.acquire(np.array([[0, 2], [0, 3], [0, 12]]))
    result = FIRPipeline([1]).process(source)
    np.testing.assert_array_equal(result.volts, source.data.volts)
    np.testing.assert_array_equal(result.valid, ~source.data.clipped)


def test_rejected_packet_leaves_fir_history_unchanged():
    engine = AcquisitionEngine(channels=1)
    pipeline, control = FIRPipeline([.25, .5, .25]), FIRPipeline([.25, .5, .25])
    a, b = engine.acquire([[1], [2]]), engine.acquire([[3], [4]])
    pipeline.process(a)
    control.process(a)
    with pytest.raises(ValueError, match="discontinuity"):
        pipeline.process(replace(b, sequence=99))
    np.testing.assert_array_equal(pipeline.process(b).volts, control.process(b).volts)
    pipeline.reset()
    np.testing.assert_array_equal(pipeline.process(a).volts,
                                  FIRPipeline([.25, .5, .25]).process(a).volts)


@pytest.mark.parametrize("taps", [[], [1, 1], [1, 2, 3], [0, np.nan, 0]])
def test_bad_filter_coefficients(taps):
    with pytest.raises(ValueError):
        FIRPipeline(taps)


@pytest.mark.parametrize("kwargs", [{"cutoff_hz": 25_000}, {"cutoff_hz": 0},
                                     {"num_taps": 2}, {"sample_rate_hz": 0}])
def test_bad_filter_design(kwargs):
    args = {"sample_rate_hz": 50_000, **kwargs}
    with pytest.raises(ValueError):
        lowpass_taps(**args)


def test_trigger_boundary_hysteresis_and_holdoff():
    engine = AcquisitionEngine(sample_rate_hz=1000, channels=1)
    trigger = ThresholdTrigger(high=1, low=.5, holdoff_samples=5)
    # Starts high: cannot fire until a valid low sample has been seen.
    a = processed(engine, [[2], [0]])
    assert trigger.process(a) == []
    b = processed(engine, [[2], [.8], [1.2], [0], [2], [2], [0], [2]])
    events = trigger.process(b)
    assert [e.sample_index for e in events] == [2, 9]
    assert [e.timestamp_ns for e in events] == [2_000_000, 9_000_000]
    assert all(e.channel_id == 0 and e.packet_sequence == 1 for e in events)


def test_trigger_threshold_equality_and_channel_ids():
    engine = AcquisitionEngine(channels=2)
    block = processed(engine, [[0, 0], [0, 0]])
    block = replace(block, source=replace(block.source, channel_ids=(4, 9)),
                    volts=np.array([[.5, .5], [1., 1.]]))
    events = ThresholdTrigger(high=1, low=.5).process(block)
    assert [e.channel_id for e in events] == [4, 9]
    assert [e.sample_index for e in events] == [1, 1]


def test_invalid_sample_clears_trigger_arming():
    engine = AcquisitionEngine(channels=1)
    block = processed(engine, [[0], [2], [2], [0], [2]])
    block.valid[1] = False
    events = ThresholdTrigger().process(block)
    assert [e.sample_index for e in events] == [4]


@pytest.mark.parametrize("kwargs", [{"high": .5, "low": .5}, {"high": np.inf},
                                     {"holdoff_samples": -1}, {"holdoff_samples": True}])
def test_bad_trigger_configuration(kwargs):
    with pytest.raises(ValueError):
        ThresholdTrigger(**kwargs)


def test_ring_wrap_oversized_append_and_snapshot_ownership():
    engine = AcquisitionEngine(channels=2)
    ring = SampleRingBuffer(5, channels=2)
    blocks = []
    for n in [3, 4, 12, 1]:
        first = sum(len(b.volts) for b in blocks)
        values = np.repeat((np.arange(first, first + n) / 10)[:, None], 2, axis=1)
        block = processed(engine, values)
        blocks.append(block)
        ring.append(block)
        snapshot = ring.snapshot()
        expected = np.concatenate([b.volts for b in blocks])[-5:]
        np.testing.assert_array_equal(snapshot.filtered_volts, expected)
        np.testing.assert_array_equal(snapshot.raw_volts, expected)
        np.testing.assert_array_equal(snapshot.codes,
                                      np.concatenate([b.source.data.codes for b in blocks])[-5:])
        np.testing.assert_array_equal(snapshot.timestamps_ns,
                                      np.concatenate([b.source.timestamps_ns for b in blocks])[-5:])
        assert snapshot.first_sample == max(0, first + n - 5)
    assert len(ring) == 5 and ring.overwritten_samples == 15
    expected = ring.snapshot().filtered_volts.copy()
    blocks[-1].volts[:] = -999
    snapshot.filtered_volts[:] = 999
    np.testing.assert_array_equal(ring.snapshot().filtered_volts, expected)
    ring.clear()
    assert len(ring) == 0 and ring.overwritten_samples == 0
    assert ring.snapshot().first_sample is None
    assert ring.snapshot().raw_volts.shape == (0, 2)


def test_buffer_preserves_quality_and_delay():
    source = AcquisitionEngine(channels=1).acquire([[0], [0], [0], [12], [0]])
    block = FIRPipeline([.25, .5, .25]).process(source)
    ring = SampleRingBuffer(3, channels=1)
    ring.append(block)
    snapshot = ring.snapshot()
    np.testing.assert_array_equal(snapshot.valid, block.valid[-3:])
    np.testing.assert_array_equal(snapshot.clipped, source.data.clipped[-3:])
    assert snapshot.group_delay_samples == 1


@pytest.mark.parametrize("consumer", ["filter", "trigger", "buffer"])
@pytest.mark.parametrize("corruption", ["gap", "duplicate", "clock", "channels", "timestamps"])
def test_stream_consumers_reject_discontinuity_without_advancing(consumer, corruption):
    engine = AcquisitionEngine(channels=1)
    a, b = processed(engine, [[0], [2]]), processed(engine, [[0], [2]])
    bad = {
        "gap": replace(b.source, sequence=3),
        "duplicate": a.source,
        "clock": replace(b.source, sample_rate_hz=1000),
        "channels": replace(b.source, channel_ids=(9,)),
        "timestamps": replace(b.source, timestamps_ns=b.source.timestamps_ns + 1),
    }[corruption]
    if consumer == "filter":
        obj = FIRPipeline([1])
        obj.process(a.source)
        with pytest.raises(ValueError):
            obj.process(bad)
        np.testing.assert_array_equal(obj.process(b.source).volts, b.volts)
    elif consumer == "trigger":
        obj = ThresholdTrigger()
        obj.process(a)
        with pytest.raises(ValueError):
            obj.process(replace(b, source=bad))
        assert [e.sample_index for e in obj.process(b)] == [3]
    else:
        obj = SampleRingBuffer(4, channels=1)
        obj.append(a)
        with pytest.raises(ValueError):
            obj.append(replace(b, source=bad))
        obj.append(b)
        assert len(obj) == 4


def test_integrated_pipeline_is_independent_of_chunk_partition():
    values = np.zeros((300, 2))
    values[50:90, 0] = 3
    values[160:180, 1] = 3
    values[220:230, 0] = 12  # Clipping metadata must survive into the recorder.

    def run(parts):
        engine = AcquisitionEngine(channels=2)
        pipeline = FIRPipeline(lowpass_taps(50_000, num_taps=15))
        trigger = ThresholdTrigger()
        ring = SampleRingBuffer(127, channels=2)
        events, outputs = [], []
        for part in parts:
            block = pipeline.process(engine.acquire(part))
            outputs.append(block.volts)
            events.extend(trigger.process(block))
            ring.append(block)
        return np.concatenate(outputs), events, ring.snapshot()

    whole, events_a, buffer_a = run([values])
    chunked, events_b, buffer_b = run(np.split(values, [1, 50, 53, 120, 161, 225]))
    np.testing.assert_allclose(chunked, whole, atol=1e-12, rtol=1e-12)
    assert [(e.channel_id, e.sample_index) for e in events_a] == [(0, 56), (1, 166)]
    assert [(e.channel_id, e.sample_index, e.timestamp_ns) for e in events_b] == [
        (e.channel_id, e.sample_index, e.timestamp_ns) for e in events_a]
    np.testing.assert_allclose(buffer_a.filtered_volts, buffer_b.filtered_volts)
    np.testing.assert_array_equal(buffer_a.valid, buffer_b.valid)
    assert buffer_a.first_sample == buffer_b.first_sample == 173
