# RADIANT-DAQ

**A software-first scientific data acquisition platform, developing toward distributed timing and fault tolerance.**

RADIANT-DAQ investigates how an instrumentation node can identify unreliable measurements and preserve useful diagnostic evidence. This independent student project is not affiliated with CERN.

## Current status: DAQ-CORE-001

Implemented and tested:
- Configurable ideal ADC (16-bit, ±10 V by default), quantisation and per-sample clipping flags.
- Eight-channel chunk acquisition with channel IDs and packet sequence numbers.
- Continuous sample indices and integer nanosecond timestamps derived from a simulated sample clock.
- Reproducible command-line demonstration and automated requirement tests.

Timing synchronisation, DSP, fault recovery, CRC, dashboard, RTL and physical hardware validation are **planned**, not demonstrated by this version. Simulated timestamps do not prove real-time host execution or clock synchronisation. No radiation tolerance or safety certification is claimed.

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

The demonstration acquires two 5,000-sample chunks across eight channels at 50 ksample/s per channel. The second packet starts at sample 5,000 (100,000,000 ns). Default ADC resolution is 0.30517578 mV/LSB. These are configuration-derived values, not hardware measurements.

## Measurement conventions

Input shape is `(samples, channels)`, with zero-based channel IDs. All channels are modelled as sampled simultaneously. The ideal ADC uses `2**bits` bins over `[v_min, v_max)`, floor coding and midpoint voltage reconstruction. Upper-full-scale input is flagged as clipped; in-range reconstruction error is bounded by half an LSB. The default mid-rise model reconstructs zero input as +0.5 LSB.

Timestamps start at zero and use `floor(sample_index * 1e9 / sample_rate_hz)`. They represent nominal acquisition time, not UTC or packet arrival time. Invalid chunks raise an exception without advancing acquisition state. Packet arrays are caller-owned snapshots; frozen dataclasses do not make NumPy arrays immutable.

## Roadmap

1. Acquisition core: ADC and packet metadata implemented; DSP integration, triggering, buffering and logging next.
2. Distributed timing: oscillator offset/drift, delay models and estimator validation.
3. Fault injection: sensor, ADC, packet, clock and register corruption.
4. Diagnostics and recovery: detection, isolation and explicitly bounded recovery policies.
5. Supervisor: event records, flight recorder and visualisation.
6. Hardware validation: analog front end, ADC and MCU/FPGA integration.

See [requirements and verification mapping](docs/requirements/DAQ-CORE-001.md) and [architecture](docs/architecture/overview.md). Earlier DAQ/DSP work lives separately in [cern-signal-acquisition](https://github.com/Kanima9207/cern-signal-acquisition); results from that project are not claimed as results of this implementation.
