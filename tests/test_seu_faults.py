import math
import numpy as np
import pytest

from radiant.faults import (
    DigitalStateBank,
    flip_array_element_bit,
    flip_float64_bit,
    flip_integer_bit,
)


def test_integer_bit_flip_unsigned():
    assert flip_integer_bit(0b0010, 0, width=4) == 0b0011


def test_integer_bit_flip_signed_sign_bit():
    assert flip_integer_bit(1, 3, width=4, signed=True) == -7


def test_integer_bit_flip_rejects_out_of_range():
    with pytest.raises(ValueError):
        flip_integer_bit(16, 0, width=4)


def test_float64_bit_flip_is_deterministic_and_reversible():
    original = 1.0
    corrupted = flip_float64_bit(original, 0)
    restored = flip_float64_bit(corrupted, 0)
    assert corrupted != original
    assert restored == original


def test_float64_rejects_nonfinite_input():
    with pytest.raises(ValueError):
        flip_float64_bit(float("inf"), 1)


def test_array_bit_flip_copies_input_and_reports_truth():
    values = np.array([[10, 20], [30, 40]], dtype=np.uint16)
    corrupted, before, after = flip_array_element_bit(values, (1, 0), 0)
    assert before == 30
    assert after == 31
    assert values[1, 0] == 30
    assert corrupted[1, 0] == 31


def test_array_bit_flip_supports_float64_coefficients():
    taps = np.array([0.25, 0.5, 0.25], dtype=np.float64)
    corrupted, before, after = flip_array_element_bit(taps, 1, 0)
    assert before == 0.5
    assert after != before
    assert corrupted.shape == taps.shape
    assert np.array_equal(taps, np.array([0.25, 0.5, 0.25]))


def test_array_bit_flip_rejects_slice_target():
    values = np.arange(4, dtype=np.uint16)
    with pytest.raises(ValueError):
        flip_array_element_bit(values, slice(0, 2), 0)


def test_persistent_integer_upset_changes_stored_register():
    bank = DigitalStateBank({"mode": 2})
    after = bank.inject_integer("mode", 0, width=8, persistent=True)
    assert after == 3
    assert bank.read("mode") == 3
    assert bank.records[-1].persistent is True


def test_transient_integer_upset_preserves_stored_register():
    bank = DigitalStateBank({"timestamp_counter": 100})
    after = bank.inject_integer("timestamp_counter", 2, width=32, persistent=False)
    assert after == 96
    assert bank.read("timestamp_counter") == 100
    assert bank.records[-1].persistent is False


def test_persistent_float_upset_changes_configuration_state():
    bank = DigitalStateBank({"gain": 1.0})
    after = bank.inject_float64("gain", 0, persistent=True)
    assert after != 1.0
    assert bank.read("gain") == after


def test_transient_float_upset_preserves_configuration_state():
    bank = DigitalStateBank({"threshold": 0.75})
    after = bank.inject_float64("threshold", 0, persistent=False)
    assert after != 0.75
    assert bank.read("threshold") == 0.75


def test_fault_records_capture_before_after_and_target():
    bank = DigitalStateBank({"register_a": 8})
    bank.inject_integer("register_a", 1, width=8, persistent=True)
    record = bank.records[-1]
    assert record.target == "register_a"
    assert record.bit_index == 1
    assert record.before == 8
    assert record.after == 10


def test_bank_rejects_invalid_register_values():
    with pytest.raises(ValueError):
        DigitalStateBank({"bad": math.nan})


def test_wrong_register_type_is_rejected():
    bank = DigitalStateBank({"int_reg": 1, "float_reg": 1.0})
    with pytest.raises(TypeError):
        bank.inject_float64("int_reg", 0)
    with pytest.raises(TypeError):
        bank.inject_integer("float_reg", 0)
