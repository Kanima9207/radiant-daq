"""HW-003 serial-compatible hardware-in-the-loop demonstration.

Uses the software hardware emulator by default. The measured throughput is
host-side Python ingestion performance, not a physical serial-link guarantee.
"""
from radiant.hardware import (
    HardwareEmulatorConfig,
    LiveSerialConsumer,
    SerialHardwareEmulator,
)


def main():
    config = HardwareEmulatorConfig(sample_rate_hz=50_000, channels=8, frame_samples=256)
    source = SerialHardwareEmulator(config)
    consumer = LiveSerialConsumer(source)
    packets = consumer.run(100, stop_on_error=True)
    stats = consumer.stats

    print("RADIANT-DAQ HW-003 HIL EMULATOR DEMO")
    print("=" * 60)
    print(f"Frames received       : {stats.frames_received}")
    print(f"Frames accepted       : {stats.frames_accepted}")
    print(f"Frames rejected       : {stats.frames_rejected}")
    print(f"Samples accepted      : {stats.samples_accepted}")
    print(f"Frame acceptance      : {stats.frame_acceptance_pct:.2f}%")
    print(f"Host ingest throughput: {stats.samples_per_second:,.0f} samples/s")
    if packets:
        first, last = packets[0], packets[-1]
        print(f"Sequence range        : {first.sequence} .. {last.sequence}")
        print(f"Sample range          : {first.first_sample} .. {last.first_sample + len(last.timestamps_ns) - 1}")
    print("Mode                  : software hardware-emulator source")


if __name__ == "__main__":
    main()
