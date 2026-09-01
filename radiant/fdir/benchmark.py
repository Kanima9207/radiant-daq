"""Protected fault benchmark for FDIR-007.

Replays the same 15 deterministic fault scenarios used by the unprotected
Stage-3 benchmark through the current FDIR stack. Results distinguish detection,
containment and true state recovery. This is software-simulation evidence only;
transport rejection does not reconstruct lost data, and sensor/timing findings
are not automatically repaired.
"""
from dataclasses import asdict, dataclass
import json
from pathlib import Path

import numpy as np

from radiant.acquisition import ADC, AcquisitionEngine
from radiant.faults.clock import ClockFaultEvent, FaultedClock
from radiant.faults.injection import FaultEvent, SensorFaultInjector
from radiant.faults.packet import (
    corrupt_timestamp,
    drop_packet,
    duplicate_packet,
    envelope_packet,
    flip_code_bit,
    reorder_adjacent,
)
from radiant.faults.seu import flip_float64_bit, flip_integer_bit
from radiant.timing.clock import LocalClock
from radiant.timing.synchronization import SynchronizationEstimate

from .recovery import RecoveryManager
from .sensor import SensorHealthMonitor
from .state import MirroredStateBank
from .timing import TimingHealthConfig, TimingHealthMonitor
from .transport import TransportIntegrityMonitor


@dataclass(frozen=True)
class ProtectedBenchmarkRow:
    fault: str
    domain: str
    detected: bool
    silent_corruption: bool
    contained: bool
    recovered: bool
    detector: str
    recovery_action: str
    metric_name: str
    metric_value: float


def _row(fault, domain, detected, contained, recovered, detector,
         recovery_action, metric_name, metric_value):
    return ProtectedBenchmarkRow(
        fault=fault,
        domain=domain,
        detected=bool(detected),
        silent_corruption=not bool(detected),
        contained=bool(contained),
        recovered=bool(recovered),
        detector=detector,
        recovery_action=recovery_action,
        metric_name=metric_name,
        metric_value=float(metric_value),
    )


def _sensor_rows():
    base = np.zeros((1000, 2), dtype=np.float64)
    events = [
        FaultEvent(1, "bias", 0, 100, 200, magnitude_volts=0.75),
        FaultEvent(2, "drift", 0, 300, 400, slope_volts_per_sample=0.002),
        FaultEvent(3, "stuck", 1, 500, 600, stuck_value_volts=1.25),
        FaultEvent(4, "noise", 1, 700, 800, noise_std_volts=0.2),
        FaultEvent(5, "saturation", 0, 850, 900, saturation_value_volts=12.0),
    ]
    injected = SensorFaultInjector(events, seed=7).apply(base).samples
    monitor = SensorHealthMonitor()
    adc = ADC()
    converted = adc.convert(injected)

    bias = monitor.inspect(injected[100:200, 0:1], channel_ids=(0,))
    drift = monitor.inspect(injected[300:400, 0:1], channel_ids=(0,))
    stuck = monitor.inspect(injected[500:600, 1:2], channel_ids=(1,))
    noise = monitor.inspect(injected[700:800, 1:2], channel_ids=(1,))
    clip_fraction = float(np.mean(converted.clipped[850:900, 0]))

    return [
        _row("bias", "sensor", bias.detected, False, False, "sensor_health", "none",
             "mean_offset_v", np.mean(injected[100:200, 0])),
        _row("drift", "sensor", drift.detected, False, False, "sensor_health", "none",
             "peak_error_v", np.max(np.abs(injected[300:400, 0]))),
        _row("stuck", "sensor", stuck.detected, False, False, "sensor_health", "none",
             "std_v", np.std(injected[500:600, 1])),
        _row("noise", "sensor", noise.detected, False, False, "sensor_health", "none",
             "rms_v", np.sqrt(np.mean(injected[700:800, 1] ** 2))),
        _row("saturation", "adc", clip_fraction > 0.0, True, False, "adc_clipping", "reject_clipped_data",
             "clipped_fraction", clip_fraction),
    ]


def _make_transport_stream():
    engine = AcquisitionEngine(sample_rate_hz=50_000, channels=2)
    packets = [engine.acquire(np.zeros((32, 2))) for _ in range(4)]
    return [envelope_packet(packet) for packet in packets]


def _inspect_stream(envelopes):
    monitor = TransportIntegrityMonitor()
    manager = RecoveryManager()
    reports = monitor.inspect_stream(envelopes)
    anomalous = [report for report in reports if report.detected or not report.accepted]
    actions = [manager.handle_transport(report) for report in anomalous]
    detected = bool(anomalous)
    contained = bool(actions) and all(action.success for action in actions)
    action = "+".join(sorted({record.action for record in actions})) if actions else "none"
    return detected, contained, action


def _packet_rows():
    envs = _make_transport_stream()
    corrupted, _ = flip_code_bit(envs[0], 0, 0, 3)
    corrupted_ts, _ = corrupt_timestamp(envs[1], 0, 5000)
    dropped, _ = drop_packet(envs, 1)
    duplicated, _ = duplicate_packet(envs, 1)
    reordered, _ = reorder_adjacent(envs, 1)

    scenarios = [
        ("payload_bit_flip", [corrupted] + envs[1:], "crc_failure", 1.0),
        ("timestamp_corruption", envs[:1] + [corrupted_ts] + envs[2:], "crc_failure", 1.0),
        ("packet_drop", dropped, "packets_missing", 1.0),
        ("packet_duplicate", duplicated, "extra_packets", 1.0),
        ("packet_reorder", reordered, "sequence_inversion", 1.0),
    ]
    rows = []
    for fault, stream, metric_name, metric_value in scenarios:
        detected, contained, action = _inspect_stream(stream)
        rows.append(_row(
            fault, "transport", detected, contained, False,
            "transport_integrity", action, metric_name, metric_value,
        ))
    return rows


def _state_scenario(name, initial, corrupted):
    bank = MirroredStateBank({name: initial})
    bank.replace_primary_for_test(name, corrupted)
    before = bank.inspect(name)
    record = RecoveryManager().recover_state(bank, name)
    after = bank.inspect(name)
    return before.detected, record.success and after.healthy, record.action


def _seu_rows():
    mode_after = flip_integer_bit(3, 2, width=8)
    gain_after = flip_float64_bit(1.0, 0)
    mode_detected, mode_recovered, mode_action = _state_scenario("mode", 3, mode_after)
    gain_detected, gain_recovered, gain_action = _state_scenario("gain", 1.0, gain_after)
    return [
        _row("register_bit_flip", "digital_state", mode_detected, mode_recovered,
             mode_recovered, "mirrored_state_crc", mode_action,
             "absolute_delta", abs(mode_after - 3)),
        _row("float_config_bit_flip", "digital_state", gain_detected, gain_recovered,
             gain_recovered, "mirrored_state_crc", gain_action,
             "absolute_delta", abs(gain_after - 1.0)),
    ]


def _timing_monitor():
    baseline = SynchronizationEstimate(
        offset_ns=0.0,
        rate_scale=1.0,
        frequency_error_ppm=0.0,
        rms_error_ns=0.0,
        peak_error_ns=0.0,
        sample_count=100,
    )
    # Thresholds are intentionally tighter than the generic defaults because
    # this deterministic benchmark has zero baseline jitter/noise.
    config = TimingHealthConfig(
        max_abs_residual_ns=200.0,
        max_rms_residual_ns=100.0,
        max_drift_ppm=25.0,
    )
    return TimingHealthMonitor(baseline, config)


def _clock_rows():
    refs = np.arange(0, 10_000_000, 100_000, dtype=np.int64)
    jump = FaultedClock(
        LocalClock(offset_ns=0, frequency_error_ppm=0.0, jitter_std_ns=0.0),
        [ClockFaultEvent(1, "jump", 2_000_000, magnitude=250_000.0)],
    ).read(refs)
    drift = FaultedClock(
        LocalClock(),
        [ClockFaultEvent(2, "drift_change", 1_000_000, 6_000_000, 100.0)],
    ).read(refs)
    freeze = FaultedClock(
        LocalClock(),
        [ClockFaultEvent(3, "freeze", 3_000_000, 4_000_000)],
    ).read(refs)

    monitor = _timing_monitor()
    values = [
        ("clock_jump", jump),
        ("drift_change", drift),
        ("timestamp_freeze", freeze),
    ]
    rows = []
    for fault, local in values:
        report = monitor.inspect(refs, local)
        peak = float(np.max(np.abs(local.astype(np.int64) - refs)))
        rows.append(_row(
            fault, "timing", report.detected, False, False,
            "timing_health", "none", "peak_timestamp_error_ns", peak,
        ))
    return rows


def run_protected_fault_benchmark(output_dir="results/faults"):
    rows = _sensor_rows() + _packet_rows() + _seu_rows() + _clock_rows()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    detected = sum(row.detected for row in rows)
    silent = sum(row.silent_corruption for row in rows)
    contained = sum(row.contained for row in rows)
    recovered = sum(row.recovered for row in rows)
    summary = {
        "fault_count": len(rows),
        "detected_count": detected,
        "silent_corruption_count": silent,
        "contained_count": contained,
        "recovered_count": recovered,
        "detection_coverage_pct": 100.0 * detected / len(rows),
        "silent_corruption_pct": 100.0 * silent / len(rows),
    }
    payload = {"mode": "protected_fdir", "summary": summary,
               "rows": [asdict(row) for row in rows]}
    with (output / "fault_protected.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return rows, summary


def main():
    rows, summary = run_protected_fault_benchmark()
    print("RADIANT-DAQ PROTECTED FDIR FAULT BENCHMARK")
    print("=" * 84)
    for row in rows:
        print(
            f"{row.fault:24s} | domain={row.domain:13s} | "
            f"detected={str(row.detected):5s} | silent={str(row.silent_corruption):5s} | "
            f"contained={str(row.contained):5s} | recovered={str(row.recovered):5s}"
        )
    print("-" * 84)
    print(f"fault scenarios: {summary['fault_count']}")
    print(f"FDIR detections: {summary['detected_count']}")
    print(f"silent corruptions with FDIR: {summary['silent_corruption_count']}")
    print(f"contained scenarios: {summary['contained_count']}")
    print(f"true recovered-state scenarios: {summary['recovered_count']}")
    print(f"detection coverage: {summary['detection_coverage_pct']:.1f}%")
    print(f"silent-corruption rate: {summary['silent_corruption_pct']:.1f}%")
    print("metrics: results/faults/fault_protected.json")


if __name__ == "__main__":
    main()
