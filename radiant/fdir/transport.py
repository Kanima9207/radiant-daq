"""Transport integrity and stream-continuity monitoring for FDIR-001.

Detection only: this module reports integrity/continuity anomalies but does not
repair, retransmit, reorder, or otherwise recover packets.
"""
from dataclasses import dataclass

from radiant.faults.packet import PacketEnvelope, verify_envelope


@dataclass(frozen=True)
class IntegrityFinding:
    kind: str
    sequence: int
    expected_sequence: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class IntegrityReport:
    accepted: bool
    crc_ok: bool
    continuity_ok: bool
    findings: tuple[IntegrityFinding, ...]

    @property
    def detected(self):
        return bool(self.findings)


class TransportIntegrityMonitor:
    """Stateful CRC and sequence-continuity monitor for packet envelopes.

    The first valid packet establishes the expected next sequence. CRC-invalid
    packets are reported but do not advance continuity state. Sequence gaps,
    duplicates and reordering are classified from the received sequence value.
    No recovery is attempted in FDIR-001.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.next_sequence = None
        self.last_sequence = None

    def inspect(self, envelope):
        if not isinstance(envelope, PacketEnvelope):
            raise TypeError("envelope must be a PacketEnvelope")

        sequence = envelope.packet.sequence
        if type(sequence) is not int or sequence < 0:
            raise ValueError("packet sequence must be a nonnegative integer")

        findings = []
        crc_ok = verify_envelope(envelope)
        if not crc_ok:
            findings.append(IntegrityFinding(
                "crc_failure", sequence, self.next_sequence,
                "stored CRC does not match received packet contents",
            ))
            return IntegrityReport(False, False, self.next_sequence is None,
                                   tuple(findings))

        continuity_ok = True
        if self.next_sequence is None:
            self.last_sequence = sequence
            self.next_sequence = sequence + 1
            return IntegrityReport(True, True, True, ())

        expected = self.next_sequence
        if sequence == expected:
            self.last_sequence = sequence
            self.next_sequence = sequence + 1
        elif self.last_sequence is not None and sequence == self.last_sequence:
            continuity_ok = False
            findings.append(IntegrityFinding(
                "duplicate", sequence, expected,
                "received the previous sequence again",
            ))
        elif sequence > expected:
            continuity_ok = False
            findings.append(IntegrityFinding(
                "gap", sequence, expected,
                f"missing {sequence - expected} sequence value(s)",
            ))
            # Resynchronise forward after reporting the gap so later healthy
            # packets are not all marked anomalous.
            self.last_sequence = sequence
            self.next_sequence = sequence + 1
        else:
            continuity_ok = False
            findings.append(IntegrityFinding(
                "reorder", sequence, expected,
                "received a sequence older than the expected value",
            ))

        return IntegrityReport(continuity_ok, True, continuity_ok,
                               tuple(findings))

    def inspect_stream(self, envelopes):
        reports = []
        for envelope in envelopes:
            reports.append(self.inspect(envelope))
        return tuple(reports)
