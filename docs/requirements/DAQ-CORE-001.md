# DAQ-CORE-001 — ADC and acquisition engine

Scope: ideal simultaneous multichannel simulation. No acquisition scheduling, physical ADC interface or distributed clock estimation yet.

| ID | Requirement | Verification in tests/test_acquisition.py |
|---|---|---|
| ADC-001 | Map finite voltages to unsigned codes across configurable full scale; clamp and flag values outside the half-open input range | test_adc_transfer_and_clipping |
| ADC-002 | Bound in-range midpoint reconstruction error by 0.5 LSB, allowing floating-point roundoff | test_quantisation_error |
| ADC-003 | Reject invalid configuration and nonfinite samples | test_invalid_adc_config; test_nonfinite_rejected |
| DAQ-001 | Acquire eight channels by default and include zero-based channel IDs | test_eight_channels_and_packet_continuity |
| DAQ-002 | Increment sequence once per accepted chunk and preserve sample continuity across unequal chunk lengths | test_eight_channels_and_packet_continuity |
| TIM-001 | Derive nanosecond timestamps from absolute sample indices without cumulative period rounding | test_fractional_period_does_not_accumulate_rounding |
| DAQ-003 | Reject empty, malformed or nonfinite chunks without changing state | test_rejection_preserves_state |
| DAQ-004 | Reject invalid sample rate and channel count | test_invalid_engine_config |

Run `python -m pytest -q` from the repository root. Randomised quantisation validation uses seed 42 and 40,000 sample values. This samples the transfer characteristic; it is not exhaustive verification of every floating-point input.

Limitations: ideal bins; no INL/DNL, jitter, input bandwidth, aperture skew, analog noise or temperature dependence. Signed 64-bit timestamps are bounded and overflow raises an exception. Independent channel metadata and data-integrity checks will be extended in later requirements.
