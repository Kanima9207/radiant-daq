# RADIANT-DAQ

**A software-first scientific data acquisition platform developing fault-tolerant acquisition, distributed timing and diagnostic evidence capture.**

RADIANT-DAQ investigates whether an instrumentation node can identify unreliable measurements, preserve useful diagnostic evidence and maintain a common simulated timebase under controlled faults. This independent student project is not affiliated with CERN.

## Current status: Stage 2 distributed timing verified

Implemented and tested:
- Configurable ideal ADC (16-bit, ±10 V by default), quantisation and per-sample clipping flags.
- Eight-channel chunk acquisition with channel IDs, packet sequence numbers and continuous sample indices.
- Causal FIR filtering with preserved state, explicit validity propagation and group-delay metadata.
- Per-channel threshold triggering with hysteresis and holdoff.
- Bounded raw/processed sample ring buffer.
- Trigger-centred flight recorder with explicit pre/post-window completeness.
- Persistent event records with metadata, compressed NumPy sample payloads, SHA-256 integrity checking and replay.
- Independent simulated node clocks with configurable offset, ppm error and seeded jitter.
- Affine offset/frequency-drift synchronization estimator and timestamp correction.
- Four-timestamp network exchanges with propagation delay, jitter and explicit forward/reverse asymmetry.
- Reproducible distributed-timing benchmark with JSON/CSV evidence and optional plots.

Fault injection, FDIR/recovery policies, CRC-protected transport, dashboard, RTL and physical hardware validation are **not yet demonstrated**. No radiation tolerance, safety certification, White Rabbit implementation or physical sub-microsecond synchronization is claimed.

## Distributed timing benchmark

The verified TIMING-004 simulation used two independently drifting nodes:

| Metric | Node A | Node B |
|---|---:|---:|
| Configured drift | +25.000 ppm | -18.000 ppm |
| Estimated drift | +25.000 ppm | -18.000 ppm |
| RMS timing error before correction | 1,835,847.9 ns | 1,320,579.5 ns |
| Peak timing error before correction | 3,117,637.0 ns | 2,243,289.0 ns |
| RMS timing error after correction | 256.7 ns | 259.7 ns |
| Peak timing error after correction | 820.0 ns | 896.0 ns |
| RMS improvement | 7151.5× | 5084.2× |

Under this deterministic simulated network benchmark, affine correction reduced RMS timestamp error from roughly 1.3–1.8 ms to roughly 257–260 ns. These are simulation results, not hardware timing measurements. The timing model also exposes the symmetric-path assumption: forward/reverse path asymmetry creates a corresponding offset bias rather than being hidden.

See [timing verification](docs/verification/TIMING-001.md).

## Run locally

Python 3.10 or newer:

```sh
git clone https://github.com/Kanima9207/radiant-daq.git
cd radiant-daq
python -m venv .venv
```

Activate on Windows PowerShell with `.venv\Scripts\Activate.ps1`, or on Linux/macOS with `source .venv/bin/activate`. Then:

```sh
python -m pip install -r requirements.txt
python -m pytest -q
python run_radiant.py
```

For the timing benchmark and plots:

```sh
python -m pip install -e ".[dev,benchmark]"
python -m radiant.timing.benchmark
```

The acquisition demonstration processes four 5,000-sample chunks across eight channels at 50 ksample/s per channel, filters a 1 kHz signal plus 10 kHz interference, and detects three CH0 pulses. A 7,500-sample ring retains indices 12,500–19,999. The 63-tap FIR has 31 samples / 620 µs group delay at 50 ksample/s. Default ADC resolution is 0.30517578 mV/LSB. These are simulation/configuration values, not hardware measurements.

## Measurement conventions

Input shape is `(samples, channels)`, with zero-based channel IDs and simultaneous sampling. The ideal ADC uses `2**bits` bins over `[v_min, v_max)`, floor coding and midpoint reconstruction. Upper-full-scale input is flagged as clipped; in-range reconstruction error is bounded by half an LSB.

Stage-1 nominal timestamps use `floor(sample_index * 1e9 / sample_rate_hz)`. They represent simulated acquisition time, not UTC or host packet-arrival time. Timing modules then model independent local clocks relative to that reference timeline. Timing correction does not establish traceability to a physical master clock.

Filtering preserves source timestamps. Trigger timestamps identify filtered threshold crossings and carry filter-delay metadata; they do not claim physical pulse-onset time. Startup/clipping validity propagates through the FIR and suppresses untrustworthy trigger arming.

Event records retain captured arrays and explicitly state whether requested pre/post-trigger history is complete. Persistent records use local filesystem storage and SHA-256 integrity verification; this is corruption detection, not cryptographic authentication or redundant archival storage.

Each streaming consumer validates packet ordering and metadata before state advances. Automatic stream recovery is intentionally deferred to the FDIR stage.

## Roadmap

1. **Acquisition core — complete:** ADC, packet metadata, streaming FIR, triggering, buffering, event recording, persistence and replay.
2. **Distributed timing — complete in simulation:** local clock models, offset/drift estimation, network delay/jitter/asymmetry and quantitative benchmark.
3. **Fault injection — next:** sensor, ADC, packet, clock and register/SEU-style corruption with independent ground truth.
4. **Diagnostics and recovery:** detection, isolation, trust state and explicitly bounded recovery policies.
5. **Supervisor:** alarms, event/health views, timing status and visualization.
6. **Hardware validation:** analog front end, ADC and MCU/FPGA integration.

Requirements and evidence: [DAQ-CORE-001](docs/requirements/DAQ-CORE-001.md), [DAQ-CORE-002](docs/requirements/DAQ-CORE-002.md), [DAQ-CORE-003](docs/requirements/DAQ-CORE-003.md), [TIMING-001](docs/requirements/TIMING-001.md), [DAQ verification](docs/verification/DAQ-CORE-002.md), [event-record verification](docs/verification/DAQ-CORE-003.md), [timing verification](docs/verification/TIMING-001.md), and [architecture](docs/architecture/overview.md).

Earlier DAQ/DSP work lives separately in [cern-signal-acquisition](https://github.com/Kanima9207/cern-signal-acquisition); results from that project are not claimed as results of this implementation.
