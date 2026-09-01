import json

from radiant.faults.benchmark import run_fault_benchmark


def test_fault_benchmark_returns_expected_scenarios(tmp_path):
    rows, summary = run_fault_benchmark(tmp_path)
    names = {row.fault for row in rows}
    assert len(rows) == 15
    assert summary["fault_count"] == 15
    assert {
        "bias", "drift", "stuck", "noise", "saturation",
        "payload_bit_flip", "timestamp_corruption", "packet_drop",
        "packet_duplicate", "packet_reorder", "register_bit_flip",
        "float_config_bit_flip", "clock_jump", "drift_change",
        "timestamp_freeze",
    } == names


def test_fault_benchmark_classifies_existing_integrity_detection(tmp_path):
    rows, summary = run_fault_benchmark(tmp_path)
    detected = {row.fault for row in rows if row.detected_by_existing_integrity_check}
    assert detected == {"saturation", "payload_bit_flip", "timestamp_corruption"}
    assert summary["existing_integrity_detection_count"] == 3


def test_fault_benchmark_marks_unprotected_silent_corruption(tmp_path):
    rows, summary = run_fault_benchmark(tmp_path)
    silent = {row.fault for row in rows if row.silent_corruption}
    assert "bias" in silent
    assert "packet_drop" in silent
    assert "register_bit_flip" in silent
    assert "clock_jump" in silent
    assert "saturation" not in silent
    assert "payload_bit_flip" not in silent
    assert summary["silent_corruption_count"] == 12


def test_fault_benchmark_writes_json_artifact(tmp_path):
    rows, _ = run_fault_benchmark(tmp_path)
    path = tmp_path / "fault_baseline.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data) == len(rows)
    assert data[0]["fault"] == rows[0].fault


def test_fault_benchmark_metrics_are_nonnegative(tmp_path):
    rows, _ = run_fault_benchmark(tmp_path)
    assert all(row.metric_value >= 0 for row in rows)


def test_fault_benchmark_reproducible(tmp_path):
    rows_a, summary_a = run_fault_benchmark(tmp_path / "a")
    rows_b, summary_b = run_fault_benchmark(tmp_path / "b")
    assert rows_a == rows_b
    assert summary_a == summary_b
