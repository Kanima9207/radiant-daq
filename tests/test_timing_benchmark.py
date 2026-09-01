import json

import numpy as np
import pytest

from radiant.timing.benchmark import run_timing_benchmark, write_benchmark_results


def test_default_benchmark_is_deterministic():
    metrics_a, traces_a = run_timing_benchmark()
    metrics_b, traces_b = run_timing_benchmark()
    assert metrics_a == metrics_b
    np.testing.assert_array_equal(traces_a["reference_ns"], traces_b["reference_ns"])
    for name in metrics_a["nodes"]:
        for field in ("local_ns", "corrected_ns", "before_error_ns", "after_error_ns"):
            np.testing.assert_array_equal(traces_a["nodes"][name][field], traces_b["nodes"][name][field])


def test_default_benchmark_contains_two_expected_nodes():
    metrics, _ = run_timing_benchmark()
    assert set(metrics["nodes"]) == {"node_a", "node_b"}
    assert metrics["nodes"]["node_a"]["configured_frequency_error_ppm"] == 25.0
    assert metrics["nodes"]["node_b"]["configured_frequency_error_ppm"] == -18.0


def test_synchronization_reduces_rms_error_for_default_nodes():
    metrics, _ = run_timing_benchmark()
    for node in metrics["nodes"].values():
        assert node["after_sync"]["rms_ns"] < node["before_sync"]["rms_ns"]
        assert node["rms_improvement_factor"] > 1.0


def test_estimated_frequency_error_is_close_to_configured_value():
    metrics, _ = run_timing_benchmark()
    for node in metrics["nodes"].values():
        assert node["estimated_frequency_error_ppm"] == pytest.approx(
            node["configured_frequency_error_ppm"], abs=0.25
        )


def test_write_results_without_plots(tmp_path):
    metrics, traces = run_timing_benchmark(duration_s=10)
    paths = write_benchmark_results(tmp_path, metrics, traces, make_plots=False)
    assert paths["metrics"].is_file()
    assert paths["trace"].is_file()
    assert paths["plots"] == ()
    loaded = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    assert loaded == metrics
    lines = paths["trace"].read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("reference_ns,node_a_local_ns")
    assert len(lines) == len(traces["reference_ns"]) + 1


def test_invalid_duration_rejected():
    with pytest.raises(ValueError):
        run_timing_benchmark(duration_s=1, sync_interval_s=1)


def test_invalid_node_configuration_rejected():
    with pytest.raises(ValueError):
        run_timing_benchmark(nodes=({"name": "broken"},))
