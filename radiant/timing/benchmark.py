from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from .clock import LocalClock
from .network import NetworkDelayModel, exchange_observation, simulate_exchange
from .synchronization import estimate_synchronization, synchronization_error


DEFAULT_NODES = (
    {"name": "node_a", "offset_ns": 120_000, "frequency_error_ppm": 25.0, "clock_jitter_std_ns": 250.0, "seed": 101},
    {"name": "node_b", "offset_ns": -85_000, "frequency_error_ppm": -18.0, "clock_jitter_std_ns": 250.0, "seed": 202},
)


def _error_metrics(error_ns):
    error = np.asarray(error_ns, dtype=np.float64)
    return {
        "rms_ns": float(np.sqrt(np.mean(error * error))),
        "peak_abs_ns": float(np.max(np.abs(error))),
        "mean_ns": float(np.mean(error)),
    }


def run_timing_benchmark(
    duration_s=120,
    sync_interval_s=1,
    validation_interval_ms=100,
    network_delay_ns=50_000,
    network_jitter_std_ns=800.0,
    node_processing_ns=20_000,
    nodes=DEFAULT_NODES,
):
    """Run a seeded two-node timing experiment and return metrics plus traces.

    Synchronization observations are produced by four-timestamp exchanges over
    symmetric but jittered network paths. A separate validation timeline is
    used to quantify raw and corrected clock error. Returned values are fully
    deterministic for the default seeds.
    """
    for name, value in (("duration_s", duration_s), ("sync_interval_s", sync_interval_s),
                        ("validation_interval_ms", validation_interval_ms)):
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if duration_s < 2 * sync_interval_s:
        raise ValueError("duration_s must contain at least two synchronization exchanges")
    if type(network_delay_ns) is not int or network_delay_ns < 0:
        raise ValueError("network_delay_ns must be a nonnegative integer")
    if type(node_processing_ns) is not int or node_processing_ns < 0:
        raise ValueError("node_processing_ns must be a nonnegative integer")
    if not isinstance(network_jitter_std_ns, (int, float)) or network_jitter_std_ns < 0:
        raise ValueError("network_jitter_std_ns must be nonnegative")

    sync_times = np.arange(0, duration_s * 10**9, sync_interval_s * 10**9, dtype=np.int64)
    validation_step = validation_interval_ms * 10**6
    validation_times = np.arange(0, duration_s * 10**9, validation_step, dtype=np.int64)
    if validation_times.size < 2:
        raise ValueError("validation timeline must contain at least two samples")

    metrics = {
        "schema": "radiant-timing-benchmark-v1",
        "duration_s": duration_s,
        "sync_interval_s": sync_interval_s,
        "validation_interval_ms": validation_interval_ms,
        "network_delay_ns": network_delay_ns,
        "network_jitter_std_ns": float(network_jitter_std_ns),
        "node_processing_ns": node_processing_ns,
        "nodes": {},
    }
    traces = {"reference_ns": validation_times.copy(), "nodes": {}}

    for index, cfg in enumerate(nodes):
        required = {"name", "offset_ns", "frequency_error_ppm", "clock_jitter_std_ns", "seed"}
        if not isinstance(cfg, dict) or not required.issubset(cfg):
            raise ValueError("each node configuration must provide name, offset_ns, frequency_error_ppm, clock_jitter_std_ns and seed")
        clock = LocalClock(
            offset_ns=int(cfg["offset_ns"]),
            frequency_error_ppm=float(cfg["frequency_error_ppm"]),
            jitter_std_ns=float(cfg["clock_jitter_std_ns"]),
            seed=int(cfg["seed"]),
        )
        network = NetworkDelayModel(
            forward_delay_ns=network_delay_ns,
            reverse_delay_ns=network_delay_ns,
            jitter_std_ns=network_jitter_std_ns,
            seed=10_000 + index,
        )

        master_obs, local_obs = [], []
        for send_ns in sync_times:
            exchange = simulate_exchange(int(send_ns), clock, network, node_processing_ns)
            master_mid, node_mid = exchange_observation(exchange)
            master_obs.append(master_mid)
            local_obs.append(node_mid)
        master_obs = np.asarray(master_obs, dtype=np.int64)
        local_obs = np.asarray(local_obs, dtype=np.int64)
        estimate = estimate_synchronization(master_obs, local_obs)

        local_validation = clock.read(validation_times)
        corrected = estimate.correct(local_validation)
        before_error = local_validation.astype(np.int64) - validation_times
        after_error = synchronization_error(validation_times, corrected)
        before = _error_metrics(before_error)
        after = _error_metrics(after_error)

        node_metrics = {
            "configured_offset_ns": int(cfg["offset_ns"]),
            "configured_frequency_error_ppm": float(cfg["frequency_error_ppm"]),
            "clock_jitter_std_ns": float(cfg["clock_jitter_std_ns"]),
            "estimated_offset_ns": estimate.offset_ns,
            "estimated_frequency_error_ppm": estimate.frequency_error_ppm,
            "fit_rms_error_ns": estimate.rms_error_ns,
            "fit_peak_error_ns": estimate.peak_error_ns,
            "before_sync": before,
            "after_sync": after,
            "rms_improvement_factor": before["rms_ns"] / after["rms_ns"] if after["rms_ns"] else float("inf"),
        }
        metrics["nodes"][cfg["name"]] = node_metrics
        traces["nodes"][cfg["name"]] = {
            "local_ns": local_validation,
            "corrected_ns": corrected,
            "before_error_ns": before_error,
            "after_error_ns": after_error,
        }

    return metrics, traces


def write_benchmark_results(output_dir, metrics, traces, make_plots=True):
    """Persist benchmark metrics, traces and optional plots."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    metrics_path = root / "timing_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")

    csv_path = root / "timing_trace.csv"
    names = tuple(metrics["nodes"].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        header = ["reference_ns"]
        for name in names:
            header.extend([f"{name}_local_ns", f"{name}_corrected_ns", f"{name}_before_error_ns", f"{name}_after_error_ns"])
        writer.writerow(header)
        reference = traces["reference_ns"]
        for i in range(len(reference)):
            row = [int(reference[i])]
            for name in names:
                node = traces["nodes"][name]
                row.extend(int(node[field][i]) for field in ("local_ns", "corrected_ns", "before_error_ns", "after_error_ns"))
            writer.writerow(row)

    plot_paths = []
    if make_plots:
        try:
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise RuntimeError("matplotlib is required for timing benchmark plots; install .[benchmark]") from exc
        seconds = traces["reference_ns"].astype(np.float64) / 1e9
        for field, title, filename in (
            ("before_error_ns", "Clock error before synchronization", "timing_error_before.png"),
            ("after_error_ns", "Residual error after synchronization", "timing_error_after.png"),
        ):
            fig, ax = plt.subplots()
            for name in names:
                ax.plot(seconds, traces["nodes"][name][field], label=name)
            ax.set_xlabel("Reference time (s)")
            ax.set_ylabel("Timing error (ns)")
            ax.set_title(title)
            ax.grid(True, alpha=0.25)
            ax.legend()
            fig.tight_layout()
            path = root / filename
            fig.savefig(path, dpi=160)
            plt.close(fig)
            plot_paths.append(path)
    return {"metrics": metrics_path, "trace": csv_path, "plots": tuple(plot_paths)}


def _print_summary(metrics):
    print("RADIANT-DAQ DISTRIBUTED TIMING BENCHMARK")
    print("=" * 56)
    for name, node in metrics["nodes"].items():
        print(f"{name}: configured={node['configured_frequency_error_ppm']:+.3f} ppm | "
              f"estimated={node['estimated_frequency_error_ppm']:+.3f} ppm")
        print(f"  before RMS={node['before_sync']['rms_ns']:.1f} ns | peak={node['before_sync']['peak_abs_ns']:.1f} ns")
        print(f"  after  RMS={node['after_sync']['rms_ns']:.1f} ns | peak={node['after_sync']['peak_abs_ns']:.1f} ns")
        print(f"  RMS improvement={node['rms_improvement_factor']:.1f}x")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the RADIANT-DAQ timing benchmark")
    parser.add_argument("--output", default="results/timing", help="output directory")
    parser.add_argument("--no-plots", action="store_true", help="skip matplotlib plots")
    args = parser.parse_args(argv)
    metrics, traces = run_timing_benchmark()
    paths = write_benchmark_results(args.output, metrics, traces, make_plots=not args.no_plots)
    _print_summary(metrics)
    print(f"metrics: {paths['metrics']}")
    print(f"trace:   {paths['trace']}")
    for path in paths["plots"]:
        print(f"plot:    {path}")


if __name__ == "__main__":
    main()
