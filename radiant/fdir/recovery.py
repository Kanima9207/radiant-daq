"""Targeted recovery and watchdog primitives for FDIR-006.

These helpers act only on already-detected software faults. They provide
explicit recovery records and fail closed when redundant state is ambiguous.
They do not represent a physical safety interlock or hardware watchdog.
"""
from dataclasses import dataclass

from .state import MirroredStateBank
from .transport import IntegrityReport


@dataclass(frozen=True)
class RecoveryRecord:
    source: str
    action: str
    success: bool
    detail: str = ""


class ProcessingWatchdog:
    """Deterministic software watchdog driven by monotonic integer nanoseconds."""

    def __init__(self, timeout_ns, reset_callback):
        if type(timeout_ns) is not int or timeout_ns <= 0:
            raise ValueError("timeout_ns must be a positive integer")
        if not callable(reset_callback):
            raise TypeError("reset_callback must be callable")
        self.timeout_ns = timeout_ns
        self.reset_callback = reset_callback
        self.reset()

    def reset(self):
        self.last_pet_ns = None
        self.trip_count = 0

    def pet(self, now_ns):
        self._validate_time(now_ns)
        if self.last_pet_ns is not None and now_ns < self.last_pet_ns:
            raise ValueError("watchdog time must be nondecreasing")
        self.last_pet_ns = now_ns

    def expired(self, now_ns):
        self._validate_time(now_ns)
        if self.last_pet_ns is None:
            return False
        if now_ns < self.last_pet_ns:
            raise ValueError("watchdog time must be nondecreasing")
        return now_ns - self.last_pet_ns > self.timeout_ns

    def service(self, now_ns):
        if not self.expired(now_ns):
            return RecoveryRecord("watchdog", "none", True, "watchdog healthy")
        self.reset_callback()
        self.trip_count += 1
        self.last_pet_ns = now_ns
        return RecoveryRecord(
            "watchdog", "reset_processing", True,
            f"processing reset after timeout; trip_count={self.trip_count}",
        )

    @staticmethod
    def _validate_time(value):
        if type(value) is not int or value < 0:
            raise ValueError("time must be a nonnegative integer nanosecond value")


class RecoveryManager:
    """Apply bounded recovery actions after detector findings.

    Transport recovery in FDIR-006 means rejecting anomalous packets, not
    reconstructing missing data. Mirrored-state repair trusts a copy only when
    its own CRC is valid; when neither side is trustworthy the repair fails.
    """

    def handle_transport(self, report):
        if not isinstance(report, IntegrityReport):
            raise TypeError("report must be an IntegrityReport")
        if report.detected or not report.accepted:
            kinds = ",".join(f.kind for f in report.findings) or "rejected"
            return RecoveryRecord(
                "transport", "reject_packet", True,
                f"packet excluded from downstream processing: {kinds}",
            )
        return RecoveryRecord("transport", "accept_packet", True, "packet accepted")

    def recover_state(self, bank, name):
        if not isinstance(bank, MirroredStateBank):
            raise TypeError("bank must be a MirroredStateBank")
        report = bank.inspect(name)
        if report.healthy:
            return RecoveryRecord("digital_state", "none", True, f"{name} healthy")

        kinds = {finding.kind for finding in report.findings}
        primary_bad = "primary_crc_failure" in kinds
        shadow_bad = "shadow_crc_failure" in kinds
        mismatch = "mirror_mismatch" in kinds

        if primary_bad and shadow_bad:
            return RecoveryRecord(
                "digital_state", "fail_closed", False,
                f"{name}: both copies fail integrity checks",
            )

        primary = bank.read(name)
        shadow = bank.read_shadow(name)

        if primary_bad and not shadow_bad:
            bank.write(name, shadow)
            return RecoveryRecord(
                "digital_state", "restore_from_shadow", bank.inspect(name).healthy,
                f"{name}: restored primary state from CRC-valid shadow copy",
            )

        if shadow_bad and not primary_bad:
            bank.write(name, primary)
            return RecoveryRecord(
                "digital_state", "restore_from_primary", bank.inspect(name).healthy,
                f"{name}: restored shadow state from CRC-valid primary copy",
            )

        # Both CRCs validate yet values disagree. This should be extremely rare
        # in this software model; there is no authoritative copy, so do not guess.
        if mismatch:
            return RecoveryRecord(
                "digital_state", "fail_closed", False,
                f"{name}: copies disagree but both fingerprints validate",
            )

        return RecoveryRecord(
            "digital_state", "fail_closed", False,
            f"{name}: integrity finding cannot be safely resolved",
        )
