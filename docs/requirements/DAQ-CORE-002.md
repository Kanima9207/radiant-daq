# DAQ-CORE-002 — Streaming DSP, trigger and bounded buffer

Scope: causal filtering at the acquisition sample rate, digital threshold events, recent sample retention. The APIs consume `AcquisitionPacket` / `ProcessedPacket` objects; no network wire format, file format or hard real-time scheduler is included.

All listed tests are in `tests/test_streaming.py`.

| ID | Requirement | Verification |
|---|---|---|
| DSP-001 | Preserve independent channel FIR state across arbitrary nonempty chunk lengths; match full-signal convolution | test_fir_matches_independent_convolution_across_unequal_chunks; test_fir_channel_independence_and_identity |
| DSP-002 | Default 63-tap design: DC gain 1, 1 kHz gain within 1%, 10 kHz magnitude below 0.01 at 50 ksample/s | test_filter_response_and_impulse_delay |
| DSP-003 | Preserve source sample rate/timestamps and report 31-sample group delay for the default design | test_filter_response_and_impulse_delay; test_integrated_pipeline_is_independent_of_chunk_partition |
| DSP-004 | Mark unavailable startup and every output whose input window contains clipping invalid | test_clipping_invalidates_full_filter_window_across_chunks; test_fir_matches_independent_convolution_across_unequal_chunks |
| DSP-005 | Reject invalid filter parameters and preserve history on rejected packets; support explicit reset | test_bad_filter_coefficients; test_bad_filter_design; test_rejected_packet_leaves_fir_history_unchanged |
| TRG-001 | Arm on valid value <= low, fire on >= high; require low < high and preserve state across chunks | test_trigger_boundary_hysteresis_and_holdoff; test_trigger_threshold_equality_and_channel_ids; test_bad_trigger_configuration |
| TRG-002 | Enforce per-channel sample holdoff; consume suppressed crossings; report channel, index and timestamp | test_trigger_boundary_hysteresis_and_holdoff; test_trigger_threshold_equality_and_channel_ids |
| TRG-003 | Clear arming on invalid data, requiring a fresh valid low sample | test_invalid_sample_clears_trigger_arming |
| BUF-001 | Retain newest capacity samples in chronological order through wraparound and oversized appends | test_ring_wrap_oversized_append_and_snapshot_ownership |
| BUF-002 | Store raw/filtered data and quality flags together with timing/delay metadata | test_buffer_preserves_quality_and_delay; test_ring_wrap_oversized_append_and_snapshot_ownership |
| BUF-003 | Count overwritten samples; copy inputs/snapshots; clear retained state explicitly | test_ring_wrap_oversized_append_and_snapshot_ownership |
| STR-001 | Reject gaps, duplicate/reordered sequence, changed rate/channels or inconsistent timestamps before advancing state | test_stream_consumers_reject_discontinuity_without_advancing |
| SYS-001 | Filtering, event sample/timestamp and retained history shall be independent of chunk partitioning | test_integrated_pipeline_is_independent_of_chunk_partition |

## Defined boundaries

- The first accepted packet may start in the middle of a stream. FIR history is initially unknown and outputs are invalid for M-1 samples; subsequent packets must be contiguous.
- The FIR cutoff parameter defines the ideal sinc transition centre. No general stopband/transition-width requirement is implied by the two frequency checks in DSP-002.
- Output timestamps are uncompensated nominal sample times. Group delay is filter metadata; threshold crossing delay also depends on waveform shape and thresholds.
- `valid` covers missing FIR history and clipping provenance. It is not an all-fault health indicator or a safety interlock.
- Resetting downstream modules after a gap is an explicit application decision. The application must coordinate them; a rejected packet is not automatically repaired.
- The buffer capacity is samples per channel, not packet count. A snapshot exposes the retained interval; automated pre/post-event persistence is not included.
