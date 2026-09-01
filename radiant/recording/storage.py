import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import numpy as np

from .event_record import EventRecord


FORMAT_NAME = "radiant-event"
FORMAT_VERSION = 1


class EventStore:
    """Persist and reload EventRecord objects with SHA-256 integrity checking."""

    def __init__(self, root):
        self.root = Path(root)

    def event_path(self, event_id):
        if type(event_id) is not int or event_id < 0:
            raise ValueError("event_id must be a nonnegative integer")
        return self.root / f"event_{event_id:06d}"

    def save(self, record):
        if not isinstance(record, EventRecord):
            raise TypeError("record must be an EventRecord")
        destination = self.event_path(record.event_id)
        if destination.exists():
            raise FileExistsError(f"event already exists: {destination}")
        self.root.mkdir(parents=True, exist_ok=True)

        temp = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=self.root))
        try:
            metadata = self._metadata(record)
            metadata_bytes = self._canonical_json(metadata)
            (temp / "metadata.json").write_bytes(metadata_bytes)
            np.savez_compressed(
                temp / "samples.npz",
                timestamps_ns=record.timestamps_ns,
                codes=record.codes,
                raw_volts=record.raw_volts,
                filtered_volts=record.filtered_volts,
                clipped=record.clipped,
                valid=record.valid,
            )
            payload_bytes = (temp / "samples.npz").read_bytes()
            digest = self._digest(metadata_bytes, payload_bytes)
            (temp / "checksum.sha256").write_text(digest + "\n", encoding="ascii")
            temp.replace(destination)
        except Exception:
            shutil.rmtree(temp, ignore_errors=True)
            raise
        return destination

    def load(self, event):
        path = self.event_path(event) if type(event) is int else Path(event)
        metadata_path = path / "metadata.json"
        payload_path = path / "samples.npz"
        checksum_path = path / "checksum.sha256"
        for required in (metadata_path, payload_path, checksum_path):
            if not required.is_file():
                raise FileNotFoundError(f"missing event file: {required.name}")

        metadata_bytes = metadata_path.read_bytes()
        payload_bytes = payload_path.read_bytes()
        expected = checksum_path.read_text(encoding="ascii").strip().lower()
        actual = self._digest(metadata_bytes, payload_bytes)
        if expected != actual:
            raise ValueError("event integrity check failed")

        try:
            metadata = json.loads(metadata_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid event metadata") from exc
        self._validate_metadata(metadata)

        try:
            with np.load(payload_path, allow_pickle=False) as arrays:
                required = ("timestamps_ns", "codes", "raw_volts", "filtered_volts", "clipped", "valid")
                if set(arrays.files) != set(required):
                    raise ValueError("event payload fields are invalid")
                payload = {name: arrays[name].copy() for name in required}
        except (OSError, ValueError) as exc:
            if isinstance(exc, ValueError) and str(exc) == "event payload fields are invalid":
                raise
            raise ValueError("invalid event payload") from exc

        fields = metadata["event"]
        return EventRecord(
            event_id=fields["event_id"],
            channel_id=fields["channel_id"],
            trigger_sample=fields["trigger_sample"],
            trigger_timestamp_ns=fields["trigger_timestamp_ns"],
            trigger_value_volts=fields["trigger_value_volts"],
            packet_sequence=fields["packet_sequence"],
            sample_rate_hz=fields["sample_rate_hz"],
            channel_ids=tuple(fields["channel_ids"]),
            group_delay_samples=fields["group_delay_samples"],
            first_sample=fields["first_sample"],
            requested_pretrigger_samples=fields["requested_pretrigger_samples"],
            requested_posttrigger_samples=fields["requested_posttrigger_samples"],
            pretrigger_complete=fields["pretrigger_complete"],
            posttrigger_complete=fields["posttrigger_complete"],
            **payload,
        )

    @staticmethod
    def _metadata(record):
        return {
            "format": FORMAT_NAME,
            "version": FORMAT_VERSION,
            "event": {
                "event_id": record.event_id,
                "channel_id": record.channel_id,
                "trigger_sample": record.trigger_sample,
                "trigger_timestamp_ns": record.trigger_timestamp_ns,
                "trigger_value_volts": record.trigger_value_volts,
                "packet_sequence": record.packet_sequence,
                "sample_rate_hz": record.sample_rate_hz,
                "channel_ids": list(record.channel_ids),
                "group_delay_samples": record.group_delay_samples,
                "first_sample": record.first_sample,
                "requested_pretrigger_samples": record.requested_pretrigger_samples,
                "requested_posttrigger_samples": record.requested_posttrigger_samples,
                "pretrigger_complete": record.pretrigger_complete,
                "posttrigger_complete": record.posttrigger_complete,
            },
        }

    @staticmethod
    def _canonical_json(metadata):
        return (json.dumps(metadata, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")

    @staticmethod
    def _digest(metadata_bytes, payload_bytes):
        digest = hashlib.sha256()
        digest.update(b"RADIANT-EVENT-V1\0")
        digest.update(metadata_bytes)
        digest.update(b"\0")
        digest.update(payload_bytes)
        return digest.hexdigest()

    @staticmethod
    def _validate_metadata(metadata):
        if not isinstance(metadata, dict) or metadata.get("format") != FORMAT_NAME:
            raise ValueError("unsupported event format")
        if metadata.get("version") != FORMAT_VERSION:
            raise ValueError("unsupported event format version")
        if not isinstance(metadata.get("event"), dict):
            raise ValueError("invalid event metadata")
