# TIMING-001 — Distributed timing model and synchronization

## Purpose

Model independent DAQ-node clocks and quantify correction of offset and frequency drift using simulated timing exchanges.

## Requirements

- **TIM-REQ-001:** A local node clock shall support configurable initial offset and constant frequency error in ppm.
- **TIM-REQ-002:** Optional timestamp jitter shall be reproducible from a configured random seed.
- **TIM-REQ-003:** The synchronization estimator shall estimate a positive affine mapping between paired reference and local timestamps and expose offset, rate error and residual-fit metrics.
- **TIM-REQ-004:** Corrected timestamps shall be expressible back in the reference clock domain.
- **TIM-REQ-005:** The network timing model shall support independently configured forward/reverse delays and seeded delay jitter.
- **TIM-REQ-006:** A four-timestamp exchange shall expose round-trip delay and path asymmetry, and the estimator shall document its symmetric-path assumption.
- **TIM-REQ-007:** A reproducible benchmark shall report configured/estimated ppm, RMS and peak error before correction, RMS and peak error after correction, and machine-readable traces/metrics.

## Boundaries

This is a student-scale simulated synchronization architecture. It is not an implementation of CERN White Rabbit, IEEE 1588/PTP hardware timestamping, UTC traceability or a hardware timing measurement. Network asymmetry is a known accuracy limit under the symmetric-delay assumption.
