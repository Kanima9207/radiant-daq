"""Deterministic supervisory dashboard backend for Stage 5.

The backend emits validated supervisory snapshots and journal events without
binding the project to a particular UI framework. Streamlit or another client
can render this feed without owning detector or state-machine logic.
"""
from dataclasses import dataclass

from radiant.fdir.system import HealthState
from .journal import EventJournal
from .supervisory import (
    AlarmRecord,
    RecoveryTelemetry,
    SupervisoryBuffer,
    SupervisorySnapshot,
)


@dataclass(frozen=True)
class DashboardFrame:
    snapshot: SupervisorySnapshot
    journal_events: tuple

    @property
    def health_state(self):
        return self.snapshot.health_state


class SupervisoryDemoBackend:
    """Generate a reproducible operator-facing demo stream.

    The default scenario intentionally progresses through nominal operation,
    warning, degraded operation, a recovery action, and return toward nominal
    state. Values are deterministic simulation telemetry, not hardware data.
    """

    def __init__(self, node_id="node-0", capacity=256, journal_path=None):
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("node_id must be a nonempty string")
        self.node_id = node_id
        self.buffer = SupervisoryBuffer(capacity)
        self.journal = EventJournal(journal_path)
        self._sequence = 0
        self._step = 0

    @property
    def latest(self):
        return self.buffer.latest

    @property
    def history(self):
        return self.buffer.snapshot()

    def reset(self):
        self.buffer.clear()
        self.journal = EventJournal(self.journal.path)
        self._sequence = 0
        self._step = 0

    def next_frame(self):
        state, metrics, alarms, recoveries = self._scenario(self._step)
        timestamp_ns = self._step * 100_000_000
        snapshot = SupervisorySnapshot(
            sequence=self._sequence,
            timestamp_ns=timestamp_ns,
            health_state=state,
            node_id=self.node_id,
            metrics=metrics,
            alarms=alarms,
            recoveries=recoveries,
        )
        self.buffer.append(snapshot)
        events = self.journal.record_snapshot(snapshot)
        frame = DashboardFrame(snapshot, events)
        self._sequence += 1
        self._step += 1
        return frame

    def run(self, frames):
        if type(frames) is not int or frames < 1:
            raise ValueError("frames must be a positive integer")
        return tuple(self.next_frame() for _ in range(frames))

    @staticmethod
    def _scenario(step):
        phase = step % 8
        base_metrics = {
            "sample_rate_hz": 50_000.0,
            "active_channels": 8.0,
            "buffer_fill_pct": 30.0 + 2.0 * phase,
            "timing_rms_ns": 260.0,
            "processing_utilization_pct": 20.0 + phase,
        }

        if phase in (0, 1):
            return HealthState.NORMAL, base_metrics, (), ()

        if phase == 2:
            alarms = (
                AlarmRecord("sensor", "bias", 1, "channel mean exceeded nominal threshold"),
            )
            return HealthState.WARNING, base_metrics, alarms, ()

        if phase == 3:
            metrics = dict(base_metrics)
            metrics["timing_rms_ns"] = 18_000.0
            alarms = (
                AlarmRecord("sensor", "bias", 1, "sensor anomaly persists"),
                AlarmRecord("timing", "rms_residual", 2, "timing residual approaching limit"),
            )
            return HealthState.DEGRADED, metrics, alarms, ()

        if phase == 4:
            metrics = dict(base_metrics)
            metrics["processing_utilization_pct"] = 85.0
            alarms = (
                AlarmRecord("digital_state", "primary_crc_failure", 3,
                            "configuration copy failed integrity check"),
            )
            recoveries = (
                RecoveryTelemetry("digital_state", "restore_from_shadow", True,
                                  "restored CRC-valid shadow state"),
            )
            return HealthState.DEGRADED, metrics, alarms, recoveries

        if phase == 5:
            recoveries = (
                RecoveryTelemetry("digital_state", "integrity_recheck", True,
                                  "mirrored configuration state healthy"),
            )
            return HealthState.WARNING, base_metrics, (), recoveries

        return HealthState.NORMAL, base_metrics, (), ()
