# DAQ-CORE-003 — Verification record

## Scope

This record covers the `EventRecord` contract, in-memory `FlightRecorder`, persistent event storage, SHA-256 integrity checking and replay.

## Verified behaviour

Automated tests exercise:

- complete trigger-centred event bounds;
- explicit incomplete pre-trigger history at startup;
- array-copy/mutation isolation;
- trigger/timestamp/window-shape consistency checks;
- cross-chunk post-trigger completion;
- multiple simultaneous pending events;
- zero-post-trigger immediate completion;
- recorder reset and invalid configuration;
- persistent metadata/sample storage;
- checksum verification and corruption rejection;
- missing persistent-file rejection;
- duplicate event-ID protection; and
- replay into detached validated event records.

DAQ-CORE-003 was developed incrementally on top of the verified DAQ-CORE-002 baseline. The full repository regression suite subsequently continued through the distributed-timing work and reached **114 passing tests** before the TIMING-004 benchmark increment. This number is evidence supplied from the local project run, not a claim about a GitHub Actions execution.

## Limits

The recorder currently uses local filesystem persistence. It does not provide redundant storage, authenticated signatures, remote replication, database indexing or crash-consistent multi-device transactions. Event completeness is bounded by retained ring-buffer history; unavailable samples are never fabricated.
