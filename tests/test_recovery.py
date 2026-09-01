import pytest

from radiant.fdir import (
    IntegrityFinding,
    IntegrityReport,
    MirroredStateBank,
    ProcessingWatchdog,
    RecoveryManager,
)


def test_healthy_transport_is_accepted():
    manager = RecoveryManager()
    report = IntegrityReport(True, True, True, ())
    record = manager.handle_transport(report)
    assert record.success
    assert record.action == "accept_packet"


def test_detected_transport_fault_is_rejected():
    manager = RecoveryManager()
    report = IntegrityReport(
        False, False, True,
        (IntegrityFinding("crc_failure", 5, 5, "bad crc"),),
    )
    record = manager.handle_transport(report)
    assert record.success
    assert record.action == "reject_packet"


def test_transport_requires_integrity_report():
    with pytest.raises(TypeError):
        RecoveryManager().handle_transport(object())


def test_restore_primary_from_shadow():
    bank = MirroredStateBank({"gain": 7})
    bank.replace_primary_for_test("gain", 3)
    record = RecoveryManager().recover_state(bank, "gain")
    assert record.success
    assert record.action == "restore_from_shadow"
    assert bank.read("gain") == 7
    assert bank.inspect("gain").healthy


def test_restore_shadow_from_primary():
    bank = MirroredStateBank({"threshold": 1.5})
    bank.replace_shadow_for_test("threshold", 2.0)
    record = RecoveryManager().recover_state(bank, "threshold")
    assert record.success
    assert record.action == "restore_from_primary"
    assert bank.read_shadow("threshold") == pytest.approx(1.5)
    assert bank.inspect("threshold").healthy


def test_healthy_state_needs_no_repair():
    bank = MirroredStateBank({"mode": 2})
    record = RecoveryManager().recover_state(bank, "mode")
    assert record.success
    assert record.action == "none"


def test_ambiguous_double_corruption_fails_closed():
    bank = MirroredStateBank({"gain": 10})
    bank.replace_primary_for_test("gain", 11)
    bank.replace_shadow_for_test("gain", 12)
    record = RecoveryManager().recover_state(bank, "gain")
    assert not record.success
    assert record.action == "fail_closed"
    assert not bank.inspect("gain").healthy


def test_watchdog_does_not_trip_at_timeout_boundary():
    calls = []
    watchdog = ProcessingWatchdog(100, lambda: calls.append("reset"))
    watchdog.pet(1000)
    record = watchdog.service(1100)
    assert record.action == "none"
    assert calls == []


def test_watchdog_trips_after_timeout_and_rearms():
    calls = []
    watchdog = ProcessingWatchdog(100, lambda: calls.append("reset"))
    watchdog.pet(1000)
    record = watchdog.service(1101)
    assert record.success
    assert record.action == "reset_processing"
    assert calls == ["reset"]
    assert watchdog.trip_count == 1
    assert watchdog.service(1150).action == "none"


def test_watchdog_rejects_invalid_or_backwards_time():
    watchdog = ProcessingWatchdog(100, lambda: None)
    with pytest.raises(ValueError):
        watchdog.pet(-1)
    watchdog.pet(1000)
    with pytest.raises(ValueError):
        watchdog.service(999)
