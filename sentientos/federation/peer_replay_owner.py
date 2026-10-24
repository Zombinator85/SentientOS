"""Durable local ownership of authenticated federation peer replay sequence.

This owner derives replay state only from its own bounded immutable record chain.
It verifies each new exact signed envelope before publishing its record. It has
no network, enrollment, Health, admission, planning, or execution interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Iterable, Mapping

from sentientos.private_file_custody import (
    PrivateFileCustodyError,
    list_bounded_json_names_at,
    open_private_directory,
    publish_immutable_bytes,
    read_private_file_at,
)
from sentientos.windows_handle_custody import (
    WindowsHandleCustodyError,
    _valid_file_identity,
    read_regular_files,
)
from sentientos.windows_peer_replay_custody import (
    WindowsReplayCustodyError,
    publish_immutable_replay_bytes,
)
from .peer_authentication import (
    FederationPeerEventVerificationError,
    FederationPeerSignatureVerifier,
    VerifiedFederationPeerEvent,
    verify_federation_peer_event,
)
from .peer_trust_catalog import ReadOnlyFederationPeerTrustCatalog

REPLAY_RECORD_SCHEMA = "sentientos.federation.peer_replay_record:v1"
_MAX_SEQUENCE = 2**63 - 1
_MAX_RECORDS = 4096
_MAX_RECORD_BYTES = 140_000
_MAX_HISTORY_BYTES = 67_108_864
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PEER_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}\Z")
_RECORD_FIELDS = frozenset({
    "schema", "peer_id", "sequence", "previous_digest", "recorded_at",
    "signed_envelope", "signing_key_id", "event_digest", "catalog_version",
    "catalog_digest", "record_digest",
})


class FederationPeerReplayOwnerError(ValueError):
    """A bounded replay history, identity, or custody failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class FederationPeerReplayAcceptance:
    """One persisted signed peer envelope and the verification result it binds."""

    sequence: int
    record_digest: str
    created: bool
    verified_event: VerifiedFederationPeerEvent


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FederationPeerReplayOwnerError("replay_record_duplicate_key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise FederationPeerReplayOwnerError("replay_record_nonfinite_number")


def _load_json(raw: bytes) -> object:
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except FederationPeerReplayOwnerError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise FederationPeerReplayOwnerError("replay_record_load_failed") from exc


def _utc_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise FederationPeerReplayOwnerError("replay_record_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FederationPeerReplayOwnerError("replay_record_timestamp_invalid") from exc
    if (parsed.utcoffset() != timezone.utc.utcoffset(parsed)
            or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value):
        raise FederationPeerReplayOwnerError("replay_record_timestamp_invalid")
    return parsed


def _record_digest(body: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()


def _record_name(sequence: int) -> str:
    return f"event-{sequence:020d}.json"


def _validate_record(record: object, *, raw: bytes, peer_id: str,
                     sequence: int, previous_digest: str | None) -> str:
    if not isinstance(record, dict) or set(record) != _RECORD_FIELDS:
        raise FederationPeerReplayOwnerError("replay_record_fields_invalid")
    if (record.get("schema") != REPLAY_RECORD_SCHEMA
            or record.get("peer_id") != peer_id
            or type(record.get("sequence")) is not int
            or record.get("sequence") != sequence
            or record.get("previous_digest") != previous_digest):
        raise FederationPeerReplayOwnerError("replay_record_identity_invalid")
    recorded_at = record.get("recorded_at")
    _utc_timestamp(recorded_at)
    envelope_text = record.get("signed_envelope")
    if not isinstance(envelope_text, str):
        raise FederationPeerReplayOwnerError("replay_record_envelope_invalid")
    try:
        envelope_raw = envelope_text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise FederationPeerReplayOwnerError("replay_record_envelope_invalid") from exc
    envelope = _load_json(envelope_raw)
    if not isinstance(envelope, dict) or _canonical(envelope) != envelope_raw:
        raise FederationPeerReplayOwnerError("replay_record_envelope_invalid")
    if (envelope.get("peer_id") != peer_id
            or type(envelope.get("sequence")) is not int
            or envelope.get("sequence") != sequence
            or envelope.get("signing_key_id") != record.get("signing_key_id")
            or envelope.get("event_digest") != record.get("event_digest")):
        raise FederationPeerReplayOwnerError("replay_record_envelope_binding_invalid")
    catalog_version = record.get("catalog_version")
    catalog_digest = record.get("catalog_digest")
    if type(catalog_version) is not int or catalog_version < 1:
        raise FederationPeerReplayOwnerError("replay_record_catalog_invalid")
    if not isinstance(catalog_digest, str) or _DIGEST.fullmatch(catalog_digest) is None:
        raise FederationPeerReplayOwnerError("replay_record_catalog_invalid")
    digest = record.get("record_digest")
    if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
        raise FederationPeerReplayOwnerError("replay_record_digest_invalid")
    body = {key: value for key, value in record.items() if key != "record_digest"}
    if digest != _record_digest(body) or raw != _canonical(record):
        raise FederationPeerReplayOwnerError("replay_record_digest_mismatch")
    return digest


class FederationPeerReplayOwner:
    """Own one peer's next accepted sequence under explicit private local custody.

    The owner, rather than the caller, supplies the verifier's prior sequence.
    Records are immutable, canonical, bounded, and hash-linked. Windows requires
    an already provisioned private local root and never creates directories.
    Its publication uses held handles, no-replace rename, flush and readback.
    Windows operations require the operator-pinned filesystem identity on every read and write.
    """

    __slots__ = ("_root", "_peer_id", "_max_records", "_max_history_bytes",
                 "_expected_root_identity", "_lock")

    def __init__(self, root: str | Path, *, peer_id: str,
                 max_records: int = _MAX_RECORDS,
                 max_history_bytes: int = _MAX_HISTORY_BYTES,
                 expected_root_identity: tuple[int, bytes] | None = None) -> None:
        if not isinstance(root, (str, Path)) or not Path(root).is_absolute():
            raise FederationPeerReplayOwnerError("replay_owner_root_must_be_absolute")
        if not isinstance(peer_id, str) or _PEER_ID.fullmatch(peer_id) is None:
            raise FederationPeerReplayOwnerError("replay_owner_peer_id_invalid")
        if type(max_records) is not int or not 1 <= max_records <= _MAX_RECORDS:
            raise FederationPeerReplayOwnerError("replay_owner_record_limit_invalid")
        if (type(max_history_bytes) is not int
                or not (_MAX_RECORD_BYTES <= max_history_bytes <= _MAX_HISTORY_BYTES)):
            raise FederationPeerReplayOwnerError("replay_owner_byte_limit_invalid")
        if expected_root_identity is not None and not _valid_file_identity(expected_root_identity):
            raise FederationPeerReplayOwnerError("replay_owner_root_identity_invalid")
        if os.name == "nt" and expected_root_identity is None:
            raise FederationPeerReplayOwnerError("replay_owner_root_identity_required")
        self._root = Path(root)
        self._peer_id = peer_id
        self._max_records = max_records
        self._max_history_bytes = max_history_bytes
        self._expected_root_identity = expected_root_identity
        self._lock = threading.RLock()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def peer_id(self) -> str:
        return self._peer_id

    @property
    def max_records(self) -> int:
        return self._max_records

    @property
    def max_history_bytes(self) -> int:
        return self._max_history_bytes

    @property
    def expected_root_identity(self) -> tuple[int, bytes] | None:
        return self._expected_root_identity

    def _load_history(self, *, create: bool) -> tuple[list[dict[str, Any]], int]:
        if os.name == "nt":
            try:
                entries = read_regular_files(
                    self.root, max_entries=self.max_records + 1024,
                    max_file_bytes=_MAX_RECORD_BYTES,
                    max_total_bytes=self.max_history_bytes, require_private_acl=True,
                    expected_root_identity=self.expected_root_identity,
                )
            except WindowsHandleCustodyError as exc:
                raise FederationPeerReplayOwnerError("replay_owner_custody_unavailable") from exc
            return self._validate_history_entries(entries)
        try:
            directory_fd = open_private_directory(self.root, create=create)
        except PrivateFileCustodyError as exc:
            if not create and exc.code == "directory_root_missing":
                return [], 0
            raise FederationPeerReplayOwnerError("replay_owner_custody_unavailable") from exc
        try:
            names = list_bounded_json_names_at(
                directory_fd, max_entries=self.max_records,
                max_directory_entries=self.max_records + 1024,
            )
            def records() -> Iterable[tuple[str, bytes]]:
                for expected_sequence, name in enumerate(names, start=1):
                    if name != _record_name(expected_sequence):
                        raise FederationPeerReplayOwnerError("replay_history_sequence_gap")
                    try:
                        raw = read_private_file_at(
                            directory_fd, name, max_bytes=_MAX_RECORD_BYTES,
                            require_private_mode=True,
                        )
                    except PrivateFileCustodyError as exc:
                        raise FederationPeerReplayOwnerError("replay_history_record_unavailable") from exc
                    yield name, raw
            return self._validate_history_entries(records())
        except PrivateFileCustodyError as exc:
            raise FederationPeerReplayOwnerError("replay_history_unavailable") from exc
        finally:
            os.close(directory_fd)

    def _validate_history_entries(
        self, entries: Iterable[tuple[str, bytes]],
    ) -> tuple[list[dict[str, Any]], int]:
        history: list[dict[str, Any]] = []
        total_bytes = 0
        previous_digest: str | None = None
        for expected_sequence, (name, raw) in enumerate(entries, start=1):
            if expected_sequence > self.max_records:
                raise FederationPeerReplayOwnerError("replay_owner_record_limit_exceeded")
            if name != _record_name(expected_sequence):
                raise FederationPeerReplayOwnerError("replay_history_sequence_gap")
            total_bytes += len(raw)
            if total_bytes > self.max_history_bytes:
                raise FederationPeerReplayOwnerError("replay_history_byte_limit_exceeded")
            record = _load_json(raw)
            if not isinstance(record, dict):
                raise FederationPeerReplayOwnerError("replay_record_fields_invalid")
            previous_digest = _validate_record(
                record, raw=raw, peer_id=self.peer_id,
                sequence=expected_sequence, previous_digest=previous_digest,
            )
            history.append(record)
        return history, total_bytes

    @property
    def last_accepted_sequence(self) -> int:
        """Return the sequence reconstructed from the complete verified record chain."""
        with self._lock:
            history, _ = self._load_history(create=False)
            return len(history)

    def verified_history(
        self,
        *,
        catalog: ReadOnlyFederationPeerTrustCatalog,
        signature_verifier: FederationPeerSignatureVerifier,
    ) -> tuple[FederationPeerReplayAcceptance, ...]:
        """Reverify this immutable history against the exact pinned catalog.

        Replay verification uses each signed event's own issue time. Freshness of
        the latest assertion is applied later by the read-only projection layer.
        A changed catalog pin fails closed because this owner does not retain
        historical catalog snapshots.
        """
        if not isinstance(catalog, ReadOnlyFederationPeerTrustCatalog):
            raise FederationPeerReplayOwnerError("replay_history_catalog_required")
        if not callable(getattr(signature_verifier, "verify", None)):
            raise FederationPeerReplayOwnerError("replay_history_verifier_required")
        with self._lock:
            history, _ = self._load_history(create=False)
            verified_history: list[FederationPeerReplayAcceptance] = []
            for sequence, record in enumerate(history, start=1):
                if (
                    type(record.get("catalog_version")) is not int
                    or record.get("catalog_version") != catalog.catalog_version
                    or record.get("catalog_digest") != catalog.catalog_digest
                ):
                    raise FederationPeerReplayOwnerError(
                        "replay_history_catalog_binding_mismatch"
                    )
                envelope_text = record.get("signed_envelope")
                if not isinstance(envelope_text, str):
                    raise FederationPeerReplayOwnerError(
                        "replay_history_envelope_invalid"
                    )
                try:
                    raw = envelope_text.encode("utf-8")
                except UnicodeEncodeError as exc:
                    raise FederationPeerReplayOwnerError(
                        "replay_history_envelope_invalid"
                    ) from exc
                envelope = _load_json(raw)
                if not isinstance(envelope, dict) or _canonical(envelope) != raw:
                    raise FederationPeerReplayOwnerError(
                        "replay_history_envelope_invalid"
                    )
                issued_at = _utc_timestamp(envelope.get("issued_at"))
                try:
                    verified = verify_federation_peer_event(
                        raw,
                        catalog=catalog,
                        signature_verifier=signature_verifier,
                        now=issued_at,
                        last_accepted_sequence=sequence - 1,
                        max_age_seconds=1,
                        future_skew_seconds=0,
                    )
                except FederationPeerEventVerificationError as exc:
                    raise FederationPeerReplayOwnerError(
                        "replay_history_event_verification_failed"
                    ) from exc
                if (
                    verified.peer_id != self.peer_id
                    or verified.sequence != sequence
                    or verified.signing_key_id != record.get("signing_key_id")
                    or verified.event_digest != record.get("event_digest")
                    or verified.catalog_version != record.get("catalog_version")
                    or verified.catalog_digest != record.get("catalog_digest")
                ):
                    raise FederationPeerReplayOwnerError(
                        "replay_history_event_binding_mismatch"
                    )
                verified_history.append(
                    FederationPeerReplayAcceptance(
                        sequence=sequence,
                        record_digest=str(record["record_digest"]),
                        created=False,
                        verified_event=verified,
                    )
                )
            return tuple(verified_history)

    def accept(
        self,
        raw: bytes,
        *,
        catalog: ReadOnlyFederationPeerTrustCatalog,
        signature_verifier: FederationPeerSignatureVerifier,
        now: datetime,
        max_age_seconds: int = 300,
        future_skew_seconds: int = 30,
    ) -> FederationPeerReplayAcceptance:
        """Verify and immutably record one next peer event using owner-derived state."""
        with self._lock:
            history, total_bytes = self._load_history(create=True)
            prior_sequence = len(history)
            if prior_sequence >= self.max_records or prior_sequence >= _MAX_SEQUENCE:
                raise FederationPeerReplayOwnerError("replay_owner_record_limit_exceeded")
            verified = verify_federation_peer_event(
                raw, catalog=catalog, signature_verifier=signature_verifier, now=now,
                last_accepted_sequence=prior_sequence, max_age_seconds=max_age_seconds,
                future_skew_seconds=future_skew_seconds,
            )
            if verified.peer_id != self.peer_id:
                raise FederationPeerReplayOwnerError("replay_owner_peer_mismatch")
            previous_digest = history[-1]["record_digest"] if history else None
            try:
                envelope_text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise FederationPeerReplayOwnerError("replay_owner_envelope_encoding_invalid") from exc
            recorded_at = now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            body: dict[str, object] = {
                "schema": REPLAY_RECORD_SCHEMA,
                "peer_id": verified.peer_id,
                "sequence": verified.sequence,
                "previous_digest": previous_digest,
                "recorded_at": recorded_at,
                "signed_envelope": envelope_text,
                "signing_key_id": verified.signing_key_id,
                "event_digest": verified.event_digest,
                "catalog_version": verified.catalog_version,
                "catalog_digest": verified.catalog_digest,
            }
            digest = _record_digest(body)
            record = {**body, "record_digest": digest}
            record_bytes = _canonical(record)
            if len(record_bytes) > _MAX_RECORD_BYTES:
                raise FederationPeerReplayOwnerError("replay_owner_record_size_exceeded")
            if total_bytes + len(record_bytes) > self.max_history_bytes:
                raise FederationPeerReplayOwnerError("replay_owner_byte_limit_exceeded")
            try:
                if os.name == "nt":
                    created = publish_immutable_replay_bytes(
                        self.root / _record_name(verified.sequence), record_bytes,
                        max_bytes=_MAX_RECORD_BYTES, max_entries=self.max_records + 1024,
                        expected_root_identity=self.expected_root_identity,
                    )
                else:
                    created = publish_immutable_bytes(
                        self.root / _record_name(verified.sequence), record_bytes,
                        max_bytes=_MAX_RECORD_BYTES,
                        collision_code="replay_owner_record_conflict",
                    )
            except (PrivateFileCustodyError, WindowsReplayCustodyError) as exc:
                raise FederationPeerReplayOwnerError("replay_owner_publication_failed") from exc
            persisted, _ = self._load_history(create=False)
            if (len(persisted) != verified.sequence
                    or persisted[-1].get("record_digest") != digest):
                raise FederationPeerReplayOwnerError("replay_owner_persistence_unverified")
            return FederationPeerReplayAcceptance(
                sequence=verified.sequence, record_digest=digest,
                created=created, verified_event=verified,
            )


__all__ = [
    "FederationPeerReplayAcceptance",
    "FederationPeerReplayOwner",
    "FederationPeerReplayOwnerError",
    "REPLAY_RECORD_SCHEMA",
]
