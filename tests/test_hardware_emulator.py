import numpy as np
import pytest

from radiant.hardware import (
    ExternalAcquisitionBridge,
    HardwareEmulatorConfig,
    SerialHardwareEmulator,
    decode_external_frame,
)


def test_default_emulator_emits_valid_external_frame():
    emulator = SerialHardwareEmulator()
    frame = decode_external_frame(emulator.next_line())
    assert frame.sequence == 0
    assert frame.first_sample == 0
    assert frame.sample_rate_hz == 50_000
    assert frame.codes.shape == (256, 8)


def test_bridge_accepts_multiple_emulator_frames_contiguously():
    emulator = SerialHardwareEmulator(HardwareEmulatorConfig(frame_samples=32, channels=2))
    bridge = ExternalAcquisitionBridge()
    packets = [bridge.ingest_line(emulator.next_line()) for _ in range(3)]
    assert [packet.sequence for packet in packets] == [0, 1, 2]
    assert [packet.first_sample for packet in packets] == [0, 32, 64]


def test_readline_is_serial_style_bytes():
    emulator = SerialHardwareEmulator(HardwareEmulatorConfig(frame_samples=8, channels=1))
    data = emulator.readline()
    assert isinstance(data, bytes)
    assert data.endswith(b"\n")
    frame = decode_external_frame(data.decode("utf-8"))
    assert frame.sample_count == 8


def test_device_timestamps_follow_integer_sample_index_convention():
    cfg = HardwareEmulatorConfig(sample_rate_hz=50_000, frame_samples=4, channels=1)
    frame = SerialHardwareEmulator(cfg).next_frame()
    assert frame.timestamps_ns.tolist() == [0, 20_000, 40_000, 60_000]


def test_reset_reproduces_initial_frame_exactly():
    emulator = SerialHardwareEmulator(HardwareEmulatorConfig(frame_samples=16, channels=2))
    first = emulator.next_line()
    emulator.next_line()
    emulator.reset()
    assert emulator.next_line() == first


def test_lines_advances_sequence_and_sample_index():
    cfg = HardwareEmulatorConfig(frame_samples=10, channels=1)
    emulator = SerialHardwareEmulator(cfg)
    frames = [decode_external_frame(line) for line in emulator.lines(3)]
    assert [frame.sequence for frame in frames] == [0, 1, 2]
    assert [frame.first_sample for frame in frames] == [0, 10, 20]
    assert emulator.sequence == 3
    assert emulator.first_sample == 30


def test_quantized_waveform_is_finite_and_within_adc_range():
    cfg = HardwareEmulatorConfig(frame_samples=100, channels=3, signal_amplitude_v=2.0)
    bridge = ExternalAcquisitionBridge()
    packet = bridge.ingest_line(SerialHardwareEmulator(cfg).next_line())
    assert np.all(np.isfinite(packet.data.volts))
    assert np.all(packet.data.volts >= cfg.v_min)
    assert np.all(packet.data.volts < cfg.v_max)
    assert not np.any(packet.data.clipped)


def test_phase_offset_produces_distinct_channels():
    cfg = HardwareEmulatorConfig(frame_samples=64, channels=2, signal_amplitude_v=1.0)
    frame = SerialHardwareEmulator(cfg).next_frame()
    assert not np.array_equal(frame.codes[:, 0], frame.codes[:, 1])


def test_overrange_waveform_sets_clip_flags():
    cfg = HardwareEmulatorConfig(
        frame_samples=128,
        channels=1,
        v_min=-1.0,
        v_max=1.0,
        signal_amplitude_v=2.0,
    )
    frame = SerialHardwareEmulator(cfg).next_frame()
    assert np.any(frame.clipped)


def test_invalid_config_and_line_count_are_rejected():
    with pytest.raises(ValueError):
        HardwareEmulatorConfig(frame_samples=0)
    with pytest.raises(ValueError):
        HardwareEmulatorConfig(channels=0)
    emulator = SerialHardwareEmulator()
    with pytest.raises(ValueError):
        emulator.lines(0)
