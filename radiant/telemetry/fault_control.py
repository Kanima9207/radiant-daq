"""Dashboard-facing fault injection controls for SUPERVISORY-005.

The control layer reuses the verified protected FDIR scenario evaluations and
translates one selected simulated fault into operator-facing telemetry. It does
not alter physical hardware or claim real-time fault injection.
"""
from dataclasses import dataclass

from radiant.fdir.benchmark import ProtectedBenchmarkRow, evaluate_protected_faults
from radiant.fdir.system import HealthState

from .supervisory import AlarmRecord, RecoveryTelemetry, SupervisorySnapshot


FAULT_OPTIONS = (
    "bias",
    "drift",
    "stuck",
    "noise",
    "saturation",
    "payload_bit_flip",
    "timestamp_corruption",
    "packet_drop",
    "packet_duplicate",
    "packet_reorder",
    "register_bit_flip",
    "float_config_bit_flip",
    "clock_jump",
    "drift_change",
    "timestamp_freeze",
)


@dataclass(frozen=True)
class FaultControlResult:
    fault: str
    domain: str
    detected: bool
    contained: bool
    recovered: bool
    detector: str
    recovery_action: str
    metric_name: str
    metric_value: float

    @classmethod
    def from_benchmark_row(cls, row):
        if not isinstance(row, ProtectedBenchmarkRow):
            raise TypeError("row must be ProtectedBenchmarkRow")
        return cls(
            row.fault,
            row.domain,
            row.detected,
            row.contained,
            row.recovered,
            row.detector,
            row.recovery_action,
            row.metric_name,
            row.metric_value,
        )


class FaultInjectionController:
    """Resolve simulated fault choices through the protected FDIR matrix."""

    def __init__(self):
        rows = evaluate_protected_faults()
        self._rows = {row.fault: row for row in rows}
        if tuple(self._rows) != FAULT_OPTIONS:
            raise RuntimeError("protected benchmark fault set does not match dashboard controls")

    @property
    def faults(self):
        return FAULT_OPTIONS

    def evaluate(self, fault):
        if not isinstance(fault, str):
            raise TypeError("fault must be a string")
        try:
            row = self._rows[fault]
        except KeyError as exc:
            raise ValueError(f"unknown fault: {fault}") from exc
        return FaultControlResult.from_benchmark_row(row)

    def snapshot(self, fault, sequence, timestamp_ns, node_id="node-0"):
        result = self.evaluate(fault)
        severity = self._severity(result)
        state = HealthState.DEGRADED if severity >= 2 else HealthState.WARNING
        detail = (
            f"simulated {result.fault}; detector={result.detector}; "
            f"{result.metric_name}={result.metric_value:.6g}"
        )
        alarms = (
            AlarmRecord(result.domain, result.fault, severity, detail),
        ) if result.detected else ()

        recoveries = ()
        if result.recovery_action != "none":
            recoveries = (
                RecoveryTelemetry(
                    result.domain,
                    result.recovery_action,
                    result.contained or result.recovered,
                    self._recovery_detail(result),
                ),
            )

        metrics = {
            "sample_rate_hz": 50_000.0,
            "active_channels": 8.0,
            "buffer_fill_pct": 42.0,
            "timing_rms_ns": 260.0,
            "processing_utilization_pct": 28.0,
            "fault_metric_value": result.metric_value,
            "fault_detected": float(result.detected),
            "fault_contained": float(result.contained),
            "fault_recovered": float(result.recovered),
        }
        if result.domain == "timing":
            metrics["timing_rms_ns"] = max(260.0, result.metric_value)
        if result.domain == "digital_state":
            metrics["processing_utilization_pct"] = 55.0

        return SupervisorySnapshot(
            sequence=sequence,
            timestamp_ns=timestamp_ns,
            health_state=state,
            node_id=node_id,
            metrics=metrics,
            alarms=alarms,
            recoveries=recoveries,
        )

    @staticmethod
    def _severity(result):
        if result.domain == "digital_state":
            return 3
        if result.domain in {"timing", "transport", "adc"}:
            return 2
        return 1

    @staticmethod
    def _recovery_detail(result):
        if result.recovered:
            return "fault detected and protected state restored"
        if result.contained:
            return "fault detected and corrupted data contained; original data not reconstructed"
        return "detector finding recorded; no automatic recovery implemented"
