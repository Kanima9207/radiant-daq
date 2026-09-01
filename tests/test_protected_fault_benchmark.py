import json

from radiant.fdir.benchmark import run_protected_fault_benchmark


EXPECTED = {
    "bias", "drift", "stuck", "noise", "saturation",
    "payload_bit_flip", "timestamp_corruption", "packet_drop",
    "packet_duplicate", "packet_reorder", "register_bit_flip",
    "float_config_bit_flip", "clock_jump", "drift_change",
    "timestamp_freeze",
}


def test_protected_benchmark_returns_original_15_scenarios(tmp_path):
    rows, summary = run_protected_fault_benchmark(tmp_path)
    assert len(rows) == 15
    assert summary["fault_count"] == 15
    assert {row.fault for row in rows} == EXPECTED


def test_protected_benchmark_detects_all_scenarios(tmp_path):
    rows, summary = run_protected_fault_benchmark(tmp_path)
    assert all(row.detected for row in rows)
    assert summary["detected_count"] == 15
    assert summary["detection_coverage_pct"] == 100.0


def test_protected_benchmark_eliminates_silent_corruption_in_matrix(tmp_path):
    rows, summary = run_protected_fault_benchmark(tmp_path)
    assert not any(row.silent_corruption for row in rows)
    assert summary["silent_corruption_count"] == 0
    assert summary["silent_corruption_pct"] == 0.0


def test_transport_faults_are_contained_but_not_claimed_recovered(tmp_path):
    rows, _ = run_protected_fault_benchmark(tmp_path)
    transport = [row for row in rows if row.domain == "transport"]
    assert len(transport) == 5
    assert all(row.contained for row in transport)
    assert not any(row.recovered for row in transport)
    assert all(row.recovery_action == "reject_packet" for row in transport)


def test_digital_state_faults_are_detected_and_recovered(tmp_path):
    rows, summary = run_protected_fault_benchmark(tmp_path)
    state = [row for row in rows if row.domain == "digital_state"]
    assert len(state) == 2
    assert all(row.detected and row.contained and row.recovered for row in state)
    assert {row.recovery_action for row in state} == {"restore_from_shadow"}
    assert summary["recovered_count"] == 2


def test_sensor_and_timing_faults_detected_without_recovery_claim(tmp_path):
    rows, _ = run_protected_fault_benchmark(tmp_path)
    selected = [row for row in rows if row.domain in {"sensor", "timing"}]
    assert selected
    assert all(row.detected for row in selected)
    assert not any(row.recovered for row in selected)


def test_protected_benchmark_writes_structured_json(tmp_path):
    rows, summary = run_protected_fault_benchmark(tmp_path)
    path = tmp_path / "fault_protected.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["mode"] == "protected_fdir"
    assert data["summary"] == summary
    assert len(data["rows"]) == len(rows)


def test_protected_benchmark_metrics_nonnegative(tmp_path):
    rows, _ = run_protected_fault_benchmark(tmp_path)
    assert all(row.metric_value >= 0 for row in rows)


def test_protected_benchmark_is_reproducible(tmp_path):
    rows_a, summary_a = run_protected_fault_benchmark(tmp_path / "a")
    rows_b, summary_b = run_protected_fault_benchmark(tmp_path / "b")
    assert rows_a == rows_b
    assert summary_a == summary_b


def test_containment_summary_counts_transport_adc_and_state(tmp_path):
    rows, summary = run_protected_fault_benchmark(tmp_path)
    assert summary["contained_count"] == sum(row.contained for row in rows)
    assert summary["contained_count"] == 8
