import pytest

from radiant.faults.seu import flip_float64_bit, flip_integer_bit
from radiant.fdir import MirroredStateBank, state_crc32


def test_healthy_bank_has_no_findings():
    bank = MirroredStateBank({"mode": 3, "gain": 1.25})
    report = bank.inspect()
    assert report.healthy
    assert not report.detected
    assert report.findings == ()


def test_integer_primary_bit_flip_is_detected_and_isolated():
    bank = MirroredStateBank({"mode": 5})
    corrupted = flip_integer_bit(bank.read("mode"), 2, width=32)
    bank.replace_primary_for_test("mode", corrupted)
    report = bank.inspect("mode")
    kinds = {finding.kind for finding in report.findings}
    assert not report.healthy
    assert "primary_crc_failure" in kinds
    assert "mirror_mismatch" in kinds
    assert "shadow_crc_failure" not in kinds


def test_float_primary_bit_flip_is_detected_and_isolated():
    bank = MirroredStateBank({"gain": 1.0})
    corrupted = flip_float64_bit(bank.read("gain"), 0)
    bank.replace_primary_for_test("gain", corrupted)
    kinds = {finding.kind for finding in bank.inspect("gain").findings}
    assert "primary_crc_failure" in kinds
    assert "mirror_mismatch" in kinds


def test_shadow_corruption_is_distinguished_from_primary_corruption():
    bank = MirroredStateBank({"threshold": 10})
    bank.replace_shadow_for_test("threshold", 11)
    kinds = {finding.kind for finding in bank.inspect("threshold").findings}
    assert "shadow_crc_failure" in kinds
    assert "mirror_mismatch" in kinds
    assert "primary_crc_failure" not in kinds


def test_crc_storage_corruption_is_detected_without_value_mismatch():
    bank = MirroredStateBank({"mode": 7})
    bank.corrupt_primary_crc_for_test("mode")
    report = bank.inspect("mode")
    assert [finding.kind for finding in report.findings] == ["primary_crc_failure"]
    assert bank.read("mode") == bank.read_shadow("mode")


def test_normal_write_refreshes_both_copies_and_crc():
    bank = MirroredStateBank({"gain": 1.0})
    bank.write("gain", 2.5)
    assert bank.read("gain") == 2.5
    assert bank.read_shadow("gain") == 2.5
    assert bank.inspect("gain").healthy


def test_crc_is_type_sensitive():
    assert state_crc32("value", 1) != state_crc32("value", 1.0)


def test_crc_is_register_name_sensitive():
    assert state_crc32("a", 1) != state_crc32("b", 1)


def test_unknown_register_raises_key_error():
    bank = MirroredStateBank({"mode": 1})
    with pytest.raises(KeyError):
        bank.inspect("missing")
    with pytest.raises(KeyError):
        bank.write("missing", 2)


def test_invalid_state_definitions_are_rejected():
    with pytest.raises(ValueError):
        MirroredStateBank({})
    with pytest.raises(ValueError):
        MirroredStateBank({"": 1})
    with pytest.raises(ValueError):
        MirroredStateBank({"bad": float("nan")})
    with pytest.raises(ValueError):
        MirroredStateBank({"too_large": 1 << 63})
