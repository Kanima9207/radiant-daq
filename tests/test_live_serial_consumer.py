import pytest

from radiant.hardware import (
    HardwareEmulatorConfig,
    LiveSerialConsumer,
    SerialHardwareEmulator,
)


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        self.value += 0.001
        return self.value


class BadSource:
    def __init__(self, value):
        self.value = value

    def readline(self):
        return self.value


def test_consumer_accepts_emulator_bytes():
    consumer = LiveSerialConsumer(SerialHardwareEmulator(), clock=FakeClock())
    packet = consumer.read_one()
    assert packet.sequence == 0
    assert consumer.stats.frames_accepted == 1


def test_run_preserves_sequence_and_samples():
    cfg = HardwareEmulatorConfig(frame_samples=16, channels=2)
    consumer = LiveSerialConsumer(SerialHardwareEmulator(cfg), clock=FakeClock())
    packets = consumer.run(4)
    assert [p.sequence for p in packets] == [0, 1, 2, 3]
    assert [p.first_sample for p in packets] == [0, 16, 32, 48]


def test_stats_count_samples():
    cfg = HardwareEmulatorConfig(frame_samples=10, channels=2)
    consumer = LiveSerialConsumer(SerialHardwareEmulator(cfg), clock=FakeClock())
    consumer.run(3)
    assert consumer.stats.samples_accepted == 30


def test_stats_have_deterministic_throughput_with_fake_clock():
    cfg = HardwareEmulatorConfig(frame_samples=10)
    consumer = LiveSerialConsumer(SerialHardwareEmulator(cfg), clock=FakeClock())
    consumer.run(2)
    assert consumer.stats.elapsed_s == pytest.approx(0.002)
    assert consumer.stats.samples_per_second == pytest.approx(10_000.0)


def test_invalid_crc_is_rejected_without_exception():
    source = SerialHardwareEmulator()
    line = source.readline().decode("utf-8")
    damaged = line.replace('"crc32":', '"crc32":1, "old_crc":', 1)
    consumer = LiveSerialConsumer(BadSource(damaged), clock=FakeClock())
    assert consumer.read_one() is None
    assert consumer.stats.frames_rejected == 1
    assert consumer.last_error is not None


def test_empty_frame_is_rejected():
    consumer = LiveSerialConsumer(BadSource(b"\n"), clock=FakeClock())
    assert consumer.read_one() is None
    assert consumer.stats.frames_rejected == 1


def test_wrong_readline_type_is_rejected():
    consumer = LiveSerialConsumer(BadSource(123), clock=FakeClock())
    assert consumer.read_one() is None
    assert consumer.stats.frames_rejected == 1


def test_stop_on_error_stops_run():
    consumer = LiveSerialConsumer(BadSource(b"bad json\n"), clock=FakeClock())
    assert consumer.run(5, stop_on_error=True) == ()
    assert consumer.stats.frames_received == 1


def test_reset_stats_preserves_bridge_stream_but_clears_counters():
    source = SerialHardwareEmulator(HardwareEmulatorConfig(frame_samples=8))
    consumer = LiveSerialConsumer(source, clock=FakeClock())
    consumer.read_one()
    consumer.reset_stats()
    packet = consumer.read_one()
    assert packet.sequence == 1
    assert consumer.stats.frames_received == 1


def test_invalid_source_and_run_arguments_rejected():
    with pytest.raises(TypeError):
        LiveSerialConsumer(object())
    consumer = LiveSerialConsumer(SerialHardwareEmulator(), clock=FakeClock())
    with pytest.raises(ValueError):
        consumer.run(0)
    with pytest.raises(TypeError):
        consumer.run(1, stop_on_error=1)
