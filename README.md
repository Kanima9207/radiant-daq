# RADIANT-DAQ

**A software-first scientific data acquisition platform, developing toward distributed timing and fault tolerance.**

RADIANT-DAQ investigates how an instrumentation node can identify unreliable measurements and preserve useful diagnostic evidence. This independent student project is not affiliated with CERN.

## Current status: DAQ-CORE-002 (v0.2.0)

Implemented and tested:
- Configurable ideal ADC (16-bit, ±10 V by default), quantisation and per-sample clipping flags.
- Eight-channel chunk acquisition with channel IDs and packet sequence numbers.
- Continuous sample indices and integer nanosecond timestamps derived from a simulated sample clock.
- Causal FIR low-pass filtering with state preserved across unequal chunks and explicit group delay.
- Per-channel threshold triggers with hysteresis, sample-based holdoff and event timestamps.
- A bounded ring buffer retaining raw ADC codes/volts, filtered volts, timestamps and quality flags.
- Rejection of missing, duplicate, reordered or incompatible stream packets before state advances.
- Reproducible command-line demonstration and automated requirement tests.

Timing synchronisation, adaptive filtering, decimation, persistent event logging, fault recovery, CRC, dashboard, RTL and physical hardware validation are **planned**, not demonstrated by this version. Simulated timestamps do not prove real-time host execution or clock synchronisation. No radiation tolerance or safety certification is claimed.

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

The demonstration acquires four 5,000-sample chunks across eight channels at 50 ksample/s per channel, filters a 1 kHz signal plus 10 kHz interference, and detects three CH0 pulses whose onsets fall on chunk boundaries. A 7,500-sample ring retains indices 12,500–19,999 and counts 12,500 overwritten samples. The filter has 63 taps and a group delay of 31 samples (620 µs). The Hamming-windowed sinc design uses a 4 kHz ideal cutoff; this is not a Butterworth -3 dB corner specification. Default ADC resolution is 0.30517578 mV/LSB. These are simulation and configuration values, not hardware measurements.

Tests compare streamed filtering against independent full-signal convolution, check event timing across chunk boundaries and exercise buffer wraparound, oversized writes, clipping and discontinuity handling. See [verification evidence](docs/verification/DAQ-CORE-002.md).

## Measurement conventions

Input shape is `(samples, channels)`, with zero-based channel IDs. All channels are modelled as sampled simultaneously. The ideal ADC uses `2**bits` bins over `[v_min, v_max)`, floor coding and midpoint voltage reconstruction. Upper-full-scale input is flagged as clipped; in-range reconstruction error is bounded by half an LSB. The default mid-rise model reconstructs zero input as +0.5 LSB.

Timestamps start at zero and use `floor(sample_index * 1e9 / sample_rate_hz)`. They represent nominal acquisition time, not UTC or packet arrival time. Invalid chunks raise an exception without advancing acquisition state. Packet arrays are caller-owned snapshots; frozen dataclasses do not make NumPy arrays immutable.

Filtering preserves source timestamps. Trigger timestamps identify the filtered threshold crossing and include filter-delay metadata; they do not claim the physical pulse-onset time. The first 62 outputs and any output whose 63-sample input window contains clipping are marked invalid. Triggers require a valid sample at or below the low threshold before a high crossing can fire. Invalid data clears that armed state. These quality flags cover startup and observed ADC clipping only.

Each processing module is a single-consumer stream: no thread-safety guarantee. On a gap or metadata change, it raises `ValueError`; the caller must investigate and explicitly reset the modules (and clear the buffer) before resuming as a new stream. The ring buffer supplies recent history, but automated pre/post-event capture and disk persistence are still future work.

## Roadmap

1. Acquisition core: ADC, packet metadata, streaming FIR, triggering and buffering implemented; persistent event recording next.
2. Distributed timing: oscillator offset/drift, delay models and estimator validation.
3. Fault injection: sensor, ADC, packet, clock and register corruption.
4. Diagnostics and recovery: detection, isolation and explicitly bounded recovery policies.
5. Supervisor: event records, flight recorder and visualisation.
6. Hardware validation: analog front end, ADC and MCU/FPGA integration.

See requirements for [ADC/acquisition](docs/requirements/DAQ-CORE-001.md), [stream processing](docs/requirements/DAQ-CORE-002.md), and the [architecture](docs/architecture/overview.md). Earlier DAQ/DSP work lives separately in [cern-signal-acquisition](https://github.com/Kanima9207/cern-signal-acquisition); results from that project are not claimed as results of this implementation.
