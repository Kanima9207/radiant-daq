"""Read RADIANT-DAQ external acquisition frames from a physical serial port.

Example:
    python run_serial_hardware.py COM5 --baud 115200 --frames 100

The connected device must emit the HW-001 CRC-protected JSON-line protocol.
"""
import argparse

from radiant.hardware import LiveSerialConsumer, PhysicalSerialSource, SerialPortConfig


def parse_args():
    parser = argparse.ArgumentParser(description="RADIANT-DAQ physical serial acquisition reader")
    parser.add_argument("port", help="serial port, e.g. COM5 or /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200, help="serial baud rate")
    parser.add_argument("--frames", type=int, default=100, help="frames to read")
    parser.add_argument("--timeout", type=float, default=1.0, help="serial read timeout in seconds")
    return parser.parse_args()


def main():
    args = parse_args()
    config = SerialPortConfig(args.port, baudrate=args.baud, timeout_s=args.timeout)
    with PhysicalSerialSource(config) as source:
        consumer = LiveSerialConsumer(source)
        packets = consumer.run(args.frames, stop_on_error=False)
    stats = consumer.stats

    print("RADIANT-DAQ HW-004 PHYSICAL SERIAL INGEST")
    print("=" * 60)
    print(f"Port                  : {args.port}")
    print(f"Baud rate             : {args.baud}")
    print(f"Frames received       : {stats.frames_received}")
    print(f"Frames accepted       : {stats.frames_accepted}")
    print(f"Frames rejected       : {stats.frames_rejected}")
    print(f"Samples accepted      : {stats.samples_accepted}")
    print(f"Frame acceptance      : {stats.frame_acceptance_pct:.2f}%")
    print(f"Host ingest throughput: {stats.samples_per_second:,.0f} samples/s")
    if packets:
        print(f"Sequence range        : {packets[0].sequence} .. {packets[-1].sequence}")
    if consumer.last_error:
        print(f"Last error            : {consumer.last_error}")


if __name__ == "__main__":
    main()
