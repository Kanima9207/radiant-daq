# TIMING-001 — Distributed timing verification record

## Verified local regression

After TIMING-003, the local full repository suite reported **114 passing tests** with no reported regression failures. TIMING-004 then added the reproducible benchmark and its own tests; the benchmark output below was run locally by the project author. This document does not claim a completed GitHub Actions run.

## Benchmark configuration

Two independently drifting simulated nodes are synchronized against a reference/master timeline. The benchmark uses fixed random seeds and the timing-network model, then saves machine-readable metrics, a trace and before/after plots under `results/timing/`.

## Observed TIMING-004 results

| Metric | Node A | Node B |
|---|---:|---:|
| Configured frequency error | +25.000 ppm | -18.000 ppm |
| Estimated frequency error | +25.000 ppm | -18.000 ppm |
| RMS error before correction | 1,835,847.9 ns | 1,320,579.5 ns |
| Peak error before correction | 3,117,637.0 ns | 2,243,289.0 ns |
| RMS error after correction | 256.7 ns | 259.7 ns |
| Peak error after correction | 820.0 ns | 896.0 ns |
| RMS improvement | 7151.5× | 5084.2× |

Generated benchmark paths reported by the run:

- `results/timing/timing_metrics.json`
- `results/timing/timing_trace.csv`
- `results/timing/timing_error_before.png`
- `results/timing/timing_error_after.png`

## Interpretation

Under this deterministic simulated benchmark, affine clock correction reduced RMS timestamp error from approximately 1.3–1.8 ms to approximately 257–260 ns for the two configured nodes. These are simulation results. They do not establish sub-microsecond physical synchronization, hardware timestamp accuracy, White Rabbit performance, or performance on a real Ethernet network.

The network model separately demonstrates the expected limitation of the symmetric-delay assumption: forward/reverse path asymmetry biases the inferred offset by half the path asymmetry. This limitation is retained explicitly rather than hidden by the benchmark.
