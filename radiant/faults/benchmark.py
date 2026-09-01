"""Quantitative unprotected fault benchmark for RADIANT-DAQ.

This benchmark measures observable consequences of injected faults before FDIR
or recovery logic is enabled. It is simulation evidence only.
"""
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import numpy as np

from radiant.acquisition import ADC, AcquisitionEngine
from radiant.faults.injection import FaultEvent, SensorFaultInjector
from radiant.faults.packet import (
    envelope_packet,
    verify_envelope,
    flip_code_bit,
    corrupt_timestamp,
    drop_packet,
    duplicate_packet,
    reorder_adjacent,
)
from radiant.faults.seu import DigitalStateBank
from radiant.faults.clock import ClockFaultEvent, FaultedClock
from radiant.timing.clock import LocalClock


@dataclass(frozen=True)
class FaultBenchmarkRow:
    fault: str
    domain: str
    injected: bool
    observable: bool
    detected_by_existing_integrity_check: bool
    silent_corruption: bool
    impact: str
    metric_name: str
    metric_value: float


def _sensor_rows():
    rows = []
    base = np.zeros((1000, 2), dtype=np.float64)
    adc = ADC()
    events = [
        FaultEvent(1, "bias", 0, 100, 200, magnitude_volts=0.75),
        FaultEvent(2, "drift", 0, 300, 400, slope_volts_per_sample=0.002),
        FaultEvent(3, "stuck", 1, 500, 600, stuck_value_volts=1.25),
        FaultEvent(4, "noise", 1, 700, 800, noise_std_volts=0.2),
        FaultEvent(5, "saturation", 0, 850, 900, saturation_value_volts=12.0),
    ]
    result = SensorFaultInjector(events, seed=7).apply(base)
    converted = adc.convert(result.samples)

    bias_mean = float(np.mean(result.samples[100:200, 0]))
    rows.append(FaultBenchmarkRow("bias", "sensor", True, bias_mean != 0.0, False, True,
                                  "measurement offset", "mean_offset_v", bias_mean))
    drift_peak = float(np.max(np.abs(result.samples[300:400, 0])))
    rows.append(FaultBenchmarkRow("drift", "sensor", True, drift_peak > 0.0, False, True,
                                  "progressive measurement error", "peak_error_v", drift_peak))
    stuck_std = float(np.std(result.samples[500:600, 1]))
    rows.append(FaultBenchmarkRow("stuck", "sensor", True, True, False, True,
                                  "loss of sensor variability", "std_v", stuck_std))
    noise_rms = float(np.sqrt(np.mean(result.samples[700:800, 1] ** 2)))
    rows.append(FaultBenchmarkRow("noise", "sensor", True, noise_rms > 0.0, False, True,
                                  "increased measurement variance", "rms_v", noise_rms))
    clip_fraction = float(np.mean(converted.clipped[850:900, 0]))
    rows.append(FaultBenchmarkRow("saturation", "adc", True, clip_fraction > 0.0, True, False,
                                  "ADC clipping", "clipped_fraction", clip_fraction))
    return rows


def _packet_rows():
    engine = AcquisitionEngine(sample_rate_hz=50_000, channels=2)
    packets = [engine.acquire(np.zeros((32, 2))) for _ in range(4)]
    envs = [envelope_packet(packet) for packet in packets]
    rows = []

    corrupted, _ = flip_code_bit(envs[0], 0, 0, 3)
    crc_fail = not verify_envelope(corrupted)
    rows.append(FaultBenchmarkRow("payload_bit_flip", "transport", True, True, crc_fail, not crc_fail,
                                  "payload corruption", "crc_failure", float(crc_fail)))

    corrupted_ts, _ = corrupt_timestamp(envs[1], 0, 5000)
    crc_ts = not verify_envelope(corrupted_ts)
    rows.append(FaultBenchmarkRow("timestamp_corruption", "transport", True, True, crc_ts, not crc_ts,
                                  "timestamp error", "crc_failure", float(crc_ts)))

    dropped, _ = drop_packet(envs, 1)
    missing = len(envs) - len(dropped)
    rows.append(FaultBenchmarkRow("packet_drop", "transport", True, missing == 1, False, True,
                                  "missing acquisition data", "packets_missing", float(missing)))

    duplicated, _ = duplicate_packet(envs, 1)
    extra = len(duplicated) - len(envs)
    rows.append(FaultBenchmarkRow("packet_duplicate", "transport", True, extra == 1, False, True,
                                  "duplicate acquisition data", "extra_packets", float(extra)))

    reordered, _ = reorder_adjacent(envs, 1)
    seq = [item.packet.sequence for item in reordered]
    inversion = float(seq != sorted(seq))
    rows.append(FaultBenchmarkRow("packet_reorder", "transport", True, bool(inversion), False, True,
                                  "out-of-order stream", "sequence_inversion", inversion))
    return rows


def _seu_rows():
    bank = DigitalStateBank({"mode": 3, "gain": 1.0})
    mode_after = bank.inject_integer("mode", 2, width=8, persistent=True)
    mode_delta = float(abs(mode_after - 3))
    gain_after = bank.inject_float64("gain", 0, persistent=True)
    gain_delta = float(abs(gain_after - 1.0))
    return [
        FaultBenchmarkRow("register_bit_flip", "digital_state", True, mode_delta != 0.0, False, True,
                          "configuration register corruption", "absolute_delta", mode_delta),
        FaultBenchmarkRow("float_config_bit_flip", "digital_state", True, gain_delta != 0.0, False, True,
                          "floating-point configuration corruption", "absolute_delta", gain_delta),
    ]


def _clock_rows():
    refs = np.arange(0, 10_000_000, 100_000, dtype=np.int64)
    base = LocalClock(offset_ns=0, frequency_error_ppm=0.0, jitter_std_ns=0.0)
    events = [ClockFaultEvent(1, "jump", 2_000_000, magnitude=250_000.0)]
    faulted = FaultedClock(base, events)
    jump = faulted.read(refs)
    jump_peak = float(np.max(np.abs(jump - refs)))

    drift = FaultedClock(LocalClock(), [ClockFaultEvent(2, "drift_change", 1_000_000, 6_000_000, 100.0)])
    drift_values = drift.read(refs)
    drift_peak = float(np.max(np.abs(drift_values - refs)))

    freeze = FaultedClock(LocalClock(), [ClockFaultEvent(3, "freeze", 3_000_000, 4_000_000)])
    freeze_values = freeze.read(refs)
    freeze_peak = float(np.max(np.abs(freeze_values - refs)))

    return [
        FaultBenchmarkRow("clock_jump", "timing", True, jump_peak > 0.0, False, True,
                          "timestamp discontinuity", "peak_timestamp_error_ns", jump_peak),
        FaultBenchmarkRow("drift_change", "timing", True, drift_peak > 0.0, False, True,
                          "accumulating timing error", "peak_timestamp_error_ns", drift_peak),
        FaultBenchmarkRow("timestamp_freeze", "timing", True, freeze_peak > 0.0, False, True,
                          "lost elapsed time", "peak_timestamp_error_ns", freeze_peak),
    ]


def run_fault_benchmark(output_dir="results/faults"):
    rows = _sensor_rows() + _packet_rows() + _seu_rows() + _clock_rows()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payload = [asdict(row) for row in rows]
    with (output / "fault_baseline.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    silent = sum(row.silent_corruption for row in rows)
    detected = sum(row.detected_by_existing_integrity_check for row in rows)
    return rows, {"fault_count": len(rows), "silent_corruption_count": silent,
                  "existing_integrity_detection_count": detected}


def main():
    rows, summary = run_fault_benchmark()
    print("RADIANT-DAQ UNPROTECTED FAULT BENCHMARK")
    print("=" * 60)
    for row in rows:
        print(f"{row.fault:24s} | domain={row.domain:13s} | "
              f"detected={str(row.detected_by_existing_integrity_check):5s} | "
              f"silent={str(row.silent_corruption):5s} | "
              f"{row.metric_name}={row.metric_value:.6g}")
    print("-" * 60)
    print(f"fault scenarios: {summary['fault_count']}")
    print(f"existing integrity detections: {summary['existing_integrity_detection_count']}")
    print(f"silent corruptions without FDIR: {summary['silent_corruption_count']}")
    print("metrics: results/faults/fault_baseline.json")


if __name__ == "__main__":
    main()
