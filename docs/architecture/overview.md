# Architecture and implementation boundary

The current executable path is a deterministic sinusoidal source in `run_radiant.py`, followed by `AcquisitionEngine.acquire`, ideal ADC conversion and an in-memory `AcquisitionPacket`.

The acquisition engine owns sequence and sample counters. ADC conversion is stateless. A packet contains codes, reconstructed volts, clipping flags, channel IDs, nominal sample rate, first sample index and one timestamp per simultaneous multichannel sample. It does not yet define a network wire format.

Future DSP must retain its filter state across chunks and explicitly account for latency and changed sample rates after decimation. Future timing correction must preserve the original local timestamp and distinguish estimated global time from raw acquisition time. Corruption injection should act on explicit state or serialized data, with ground truth recorded independently from detector output.

Hardware work will introduce an acquisition-source interface while preserving the packet's documented units and sample ordering. Physical timing, radiation response and protection functions require separate validation; simulation alone cannot establish these properties.
