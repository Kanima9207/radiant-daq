# DAQ-CORE-003 — Event recording and replay

## Purpose

Preserve trigger-centred acquisition evidence without inventing unavailable history, and persist completed event records with integrity verification and deterministic replay.

## Requirements

- **DAQ-CORE-003-01:** The recorder shall capture configurable pre-trigger and post-trigger sample windows from the acquisition ring buffer.
- **DAQ-CORE-003-02:** Each event record shall retain trigger identity, sample/timestamp metadata, channel mapping, filter delay, raw ADC data, filtered data and quality flags.
- **DAQ-CORE-003-03:** Missing pre-trigger history at startup shall be reported explicitly rather than padded or fabricated.
- **DAQ-CORE-003-04:** An event shall remain pending until its requested post-trigger horizon is available.
- **DAQ-CORE-003-05:** Event records shall copy captured arrays so later caller mutation cannot alter the record.
- **DAQ-CORE-003-06:** Completed records shall support persistent storage of metadata and sample arrays.
- **DAQ-CORE-003-07:** Persistent records shall include a SHA-256 integrity value covering stored event content and shall reject corrupted or incomplete records on replay.
- **DAQ-CORE-003-08:** Persistent storage shall not silently overwrite an existing event identifier.
- **DAQ-CORE-003-09:** Replay shall reconstruct a detached `EventRecord` that is validated by the same record contract as live capture.

## Boundaries

This increment is an event evidence recorder, not a safety-certified black box. SHA-256 detects accidental or deliberate content changes when the checksum itself remains trustworthy; it is not authentication or a digital signature. Storage is local filesystem persistence, not a distributed database or redundant archival system.
