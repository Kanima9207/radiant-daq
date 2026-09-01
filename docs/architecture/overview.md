# Architecture and implementation boundary

The current executable path is a deterministic source in `run_radiant.py`, followed by `AcquisitionEngine.acquire`, ideal ADC conversion, `FIRPipeline.process`, `ThresholdTrigger.process` and `SampleRingBuffer.append`. No network transport or disk logging is implemented yet.

The acquisition engine owns sequence and sample counters. ADC conversion is stateless. A packet contains codes, reconstructed volts, clipping flags, channel IDs, nominal sample rate, first sample index and one timestamp per simultaneous multichannel sample. It does not yet define a network wire format.

`FIRPipeline` keeps M-1 samples of history per channel and M-1 clipping/availability flags. It uses causal convolution, with zero-padded startup samples marked invalid until the full window has arrived. A `ProcessedPacket` adds filtered volts, per-channel validity and integer group delay to the original acquisition packet. Symmetric odd-length taps provide integer linear-phase delay. The rate remains unchanged; there is no decimation.

`ThresholdTrigger` tracks armed state and last event sample per channel. A valid low sample arms it; a subsequent high sample fires unless holdoff suppresses that crossing. Events carry original sample index, timestamp, channel ID, value, source packet sequence and filter delay. They do not estimate analog event onset. Invalid outputs clear arming, preventing startup and clipping transients from being treated as trustworthy crossings.

`SampleRingBuffer` preallocates capacity in samples per channel, copies incoming data into circular arrays, and copies chronological snapshots out. It retains codes, ADC volts, filtered volts, timestamps, clipping and validity. Append work is bounded by retained capacity plus input validation. It counts all samples evicted or skipped by oversized appends. A snapshot records its first sample index, channel mapping, sample rate and filter delay. No claim of event-window completeness is made when data has been overwritten.

Each consumer independently validates packet shape, timestamps, stream order, sample rate and channel mapping before updating its state. Gaps are rejected; automatic recovery is deferred. These are single-consumer components, and an application must coordinate resets across them. No transaction across multiple modules or thread-safety is provided.

Future timing correction must preserve the original local timestamp and distinguish estimated global time from raw acquisition time. Corruption injection should act on explicit state or serialized data, with ground truth recorded independently from detector output.

Hardware work will introduce an acquisition-source interface while preserving the packet's documented units and sample ordering. Physical timing, radiation response and protection functions require separate validation; simulation alone cannot establish these properties.
