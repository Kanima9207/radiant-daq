# DAQ-CORE-002 — Local verification record

Verified environment: Python 3.12.13, NumPy 2.3.5, pytest 9.1.1 on Linux.

## Reproduce

```sh
python -m pip install -r requirements.txt
python -m pytest -q
python run_radiant.py
```

Local result: **58 tests passed** (20 acquisition tests and 38 streaming cases). This is a local test result, not evidence of a completed GitHub Actions run. The workflow is configured for Python 3.10 and 3.12.

## Demonstration observations

Four consecutive chunks, 5,000 samples per channel per chunk, eight channels at 50 ksample/s per channel. Input contains 1 kHz sinusoidal signals, 10 kHz interference and three CH0 rectangular pulses beginning at samples 5,000, 10,000 and 15,000. No ADC samples clipped in this demonstration; clipping is exercised separately in the tests.

| Output | Observed value |
|---|---|
| Triggered CH0 sample indices | 5,030; 10,030; 15,030 |
| Event timestamps (ns) | 100,600,000; 200,600,000; 300,600,000 |
| Events on other channels | 0 |
| Retained sample interval (inclusive) | 12,500–19,999 |
| Samples retained per channel | 7,500 |
| Samples overwritten/skipped per channel | 12,500 |
| Filter group delay | 31 samples / 620 µs |

The observed pulse-threshold delay is 30 samples in this particular demonstration. It need not equal the FIR group delay: the crossing time depends on pulse shape and threshold. Event timestamps are not backdated.

## Filter checks

The default design is a 63-tap Hamming-windowed sinc, ideal cutoff 4 kHz and DC-normalised gain, evaluated at 50 ksample/s. Direct evaluation of the FIR frequency response gives:

| Frequency | Magnitude | Gain (dB) |
|---|---:|---:|
| 1 kHz | 0.99574338 | -0.03705 |
| 10 kHz | 0.0000234325 | -92.60363 |

These are calculated transfer-function values at two frequencies, not measured hardware performance, end-to-end SNR improvement, or a bound across the whole stopband. The regression gate deliberately requires only 1% passband magnitude accuracy at 1 kHz and at least 40 dB attenuation at 10 kHz.

## Coverage and limits

- Independent full-signal convolution is compared against variable chunks including one-sample chunks.
- The integrated two-channel experiment verifies identical event indices/timestamps and retained sample history for whole-signal and chunked processing.
- Startup and clipping contamination propagate through filter validity and suppress trigger arming.
- Gap, duplicate, clock, channel-map and timestamp errors are rejected without advancing each consumer's state.
- Buffer tests cover wraparound, oversized appends, output ordering, quality metadata and mutation isolation.

Host execution deadlines, network behaviour, distributed synchronisation, fault recovery and hardware timing have not been benchmarked in this increment. Data is retained in memory; no persistent flight recorder is claimed.
