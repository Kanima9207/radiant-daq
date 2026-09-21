# RADIANT-DAQ

**Fault-tolerant, software-first scientific data acquisition with distributed timing, FDIR, supervisory telemetry, HIL emulation, and synthesizable SystemVerilog.**

RADIANT-DAQ is an independent instrumentation project exploring how a multi-channel DAQ node can acquire and timestamp signals, preserve event evidence, detect corrupted data or state, and move into bounded recovery/safe-state behaviour. The project is not affiliated with CERN.

> **Validation boundary:** current evidence comes from deterministic software simulation, software hardware-emulation, RTL simulation, Yosys synthesis, and Xilinx 7-series logical mapping. Physical FPGA/ADC validation and post-route timing closure are **not** claimed.

## At a glance

| Area | Current evidence |
|---|---|
| Acquisition | 8-channel software DAQ at 50 ksample/s/channel; 16-bit ideal ADC; FIR filtering; hysteretic threshold trigger; ring buffer and event records |
| Distributed timing | +25 ppm and -18 ppm simulated nodes corrected from 1.836 ms / 1.321 ms RMS error to 256.7 ns / 259.7 ns |
| Fault tolerance | Protected 15-scenario benchmark detects all configured scenarios; 600-trial seeded RTL campaign reports 100% detection/containment and 0 false alarms within that campaign |
| HIL emulator | 100/100 frames accepted; 25,600 samples; ~189.8 ksample/s host-side ingest in the recorded run |
| RTL verification | 363 pytest tests passing in the current local regression; Icarus Verilog-backed RTL tests included |
| FPGA mapping | Xilinx 7-series logical mapping: 2,633 cells, ~639 LUTs, 474 FFs, 174 CARRY4, 101 MUXF |
| Timing intent | 100 MHz / 10 ns implementation target; physical P&R and static timing closure not yet demonstrated |
| Supervisor | Streamlit console with health state, alarms, recovery actions, trends, journal, and deterministic fault injection |

## System architecture

```text
Sensor / simulated source
        |
        v
+----------------------+     +----------------------+
| Acquisition + ADC    | --> | FIR + trigger        |
| channel/sample/time  |     | hysteresis/holdoff   |
+----------------------+     +----------------------+
        |                           |
        +------------+--------------+
                     v
             +---------------+
             | Event buffer  |
             | + packetizer  |
             +---------------+
                     |
                     v
             +---------------+
             | CRC / sequence|
             | link monitor  |
             +---------------+
                     |
                     v
             +---------------+
             | FDIR + health |
             | safe-state    |
             +---------------+
                     |
          +----------+----------+
          v                     v
+------------------+   +------------------+
| Telemetry/journal|   | RTL/FPGA evidence|
| Streamlit console|   | synth + mapping  |
+------------------+   +------------------+
```

The software path preserves source sample indices and timestamps through filtering and event capture. The RTL path implements acquisition timing, multi-channel triggering, buffering, packet transport/integrity monitoring, health scoring, and safe-state control.

## Key benchmark evidence

### Distributed timing

The TIMING-004 deterministic simulation uses two independently drifting local clocks.

| Metric | Node A | Node B |
|---|---:|---:|
| Configured drift | +25.000 ppm | -18.000 ppm |
| RMS error before correction | 1,835,847.9 ns | 1,320,579.5 ns |
| RMS error after correction | 256.7 ns | 259.7 ns |
| Peak error after correction | 820.0 ns | 896.0 ns |
| RMS improvement | 7151.5x | 5084.2x |

These are simulated synchronization results, not physical clock-distribution measurements. See [TIMING-001 verification](docs/verification/TIMING-001.md).

### Fault detection and containment

The fault framework covers sensor/ADC, transport, digital-state, and timing faults. The protected software benchmark retains the original 15-scenario matrix and verifies detection of all configured scenarios, while only claiming recovery where state is actually restored.

The RTL reliability campaign independently exercises CRC corruption, protocol corruption, packet drop/gap, duplicate, reorder, and silence/watchdog faults. The seeded randomized campaign runs **600 trials** and asserts **100% detection and containment for injected fault trials with zero false alarms for clean controls within that configured campaign**.

Relevant evidence:
- [Deterministic RTL fault campaign](rtl/tb/tb_fault_campaign.sv)
- [600-trial randomized RTL campaign](rtl/tb/tb_random_fault_campaign.sv)
- [Protected software benchmark tests](tests/test_protected_fault_benchmark.py)

### Software HIL

`run_hil_demo.py` drives the serial-compatible ingestion path from a software hardware emulator. The recorded HW-003 run accepted **100/100 frames**, **25,600 samples**, with approximately **189,779 samples/s host-side ingestion throughput**. This is host/emulator performance, not a physical serial-link guarantee.

### RTL and FPGA mapping

The synthesizable RTL is regression-tested with Icarus Verilog and mapped with Yosys to Xilinx 7-series primitives.

| RTL-016 readiness metric | Result |
|---|---:|
| Mapped cells | 2,633 |
| Estimated LUTs | 639 |
| Estimated flip-flops | 474 |
| CARRY4 | 174 |
| MUXF7 + MUXF8 | 101 |
| Clock target | 100 MHz |
| Clock period | 10.000 ns |
| Logical mapping | PASS |
| Physical place-and-route | Not performed |
| Static timing closure | Not claimed |
| Physical FPGA validation | Not performed |

Committed evidence: [RTL-016 JSON](results/rtl/rtl016_implementation_readiness.json) and [human-readable report](results/rtl/rtl016_implementation_readiness.txt).

The repository also contains an XC7A35T implementation wrapper, constraint, and optional nextpnr-Xilinx runner. Those files make the physical implementation boundary explicit; they do not turn the 100 MHz target into a measured Fmax.

## Six-stage roadmap

| Stage | Status | Evidence |
|---|---|---|
| 1. Acquisition core | **Complete** | ADC model, metadata, FIR, trigger, buffering, event persistence/replay |
| 2. Distributed timing | **Complete in simulation** | Offset/drift model, network asymmetry, quantitative correction benchmark |
| 3. Fault injection | **Complete in simulation** | Sensor, ADC, transport, timing and SEU-style state corruption |
| 4. FDIR / recovery | **Complete for configured campaigns** | Detection, containment, protected-state restore, health and safe-state logic |
| 5. Supervisor | **Complete as software demo** | Telemetry, alarm/recovery journal, trends and Streamlit fault controls |
| 6. FPGA / HIL validation | **Implementation-ready; physical validation pending** | Software HIL, RTL regression, synthesis, Xilinx-7 mapping, 100 MHz timing intent |

## Run locally

Requires Python 3.10+.

```sh
git clone https://github.com/Kanima9207/radiant-daq.git
cd radiant-daq
python -m venv .venv
```

Activate the environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```sh
source .venv/bin/activate
```

Install and run the regression:

```sh
python -m pip install -r requirements.txt
python -m pytest -q
python run_radiant.py
```

Optional benchmark/dashboard dependencies:

```sh
python -m pip install -e ".[dev,benchmark,dashboard]"
python -m radiant.timing.benchmark
python run_hil_demo.py
streamlit run streamlit_app.py
```

For Xilinx logical mapping, install Yosys and run:

```sh
python tools/run_rtl_xilinx_mapping.py
python tools/run_rtl_implementation_readiness.py
```

The optional physical P&R runner requires `nextpnr-xilinx` plus an XC7A35T chip database and is intentionally separate from the logical-mapping readiness benchmark.

## Repository map

```text
radiant/        Python acquisition, timing, faults, FDIR, hardware-emulation and telemetry
rtl/            Synthesizable SystemVerilog and RTL testbenches
tests/          Python + simulator-backed regression suite
tools/          Reproducible synthesis/mapping/implementation runners
constraints/    FPGA timing / implementation intent
docs/           Requirements, architecture and verification notes
results/rtl/    Committed RTL-016 evidence
run_radiant.py  End-to-end acquisition demonstration
run_hil_demo.py Software hardware-emulator ingestion demo
streamlit_app.py Supervisory dashboard
```

## Engineering conventions and claim discipline

- Input arrays use `(samples, channels)` with zero-based channel IDs and simultaneous sampling.
- The ideal ADC uses `2**bits` bins over `[v_min, v_max)`; the default 16-bit ±10 V configuration gives **0.30517578 mV/LSB**.
- The 63-tap FIR has a 31-sample group delay, **620 us at 50 ksample/s**.
- Trigger timestamps identify filtered threshold crossings and carry filter-delay metadata; they are not estimates of analog pulse onset.
- Persistent event records use SHA-256 integrity verification for corruption detection, not authentication.
- "100 MHz" means **declared implementation target** until a routed timing report demonstrates closure.
- "Fault coverage" refers only to the explicitly configured deterministic/randomized campaigns; no universal reliability or radiation-tolerance claim is made.

## Project scope

RADIANT-DAQ is a student engineering/research project intended to demonstrate disciplined instrumentation development: requirements, simulation, quantitative benchmarking, fault injection, FDIR, RTL verification, synthesis evidence, and explicit validation boundaries.

Earlier DSP/DAQ work is maintained separately in [cern-signal-acquisition](https://github.com/Kanima9207/cern-signal-acquisition); results from that repository are not claimed as RADIANT-DAQ results.
