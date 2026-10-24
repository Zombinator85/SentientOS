"""Read-only operator trust and verification for signed federation peer events.

This module verifies provenance only. It performs no enrollment, signing, persistence,
network access, relay admission, Health publication, or remote command execution.
The caller supplies the last committed sequence from its own trusted replay ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping, Protocol
from urllib.parse import urlsplit

from sentientos.windows_handle_custody import WindowsHandleCustodyError, read_explicit_file

CATALOG_SCHEMA = "sentientos.federation_peer_trust_catalog:v1"
_CATALOG_FIELDS = frozenset({"schema", "catalog_version", "entries", "catalog_digest"})
_ENTRY_FIELDS = frozenset({
    "peer_id", "signing_key_id", "endpoint", "algorithm", "public_key",
    "valid_from", "valid_until", "revocation_status",
})
_PEER_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}\Z")
_KEY_ID = re.compile(r"ed25519-sha256:[0-9a-f]{64}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+\Z")
_MAX_CATALOG_BYTES = 1_048_576
_MAX_CATALOG_ENTRIES = 4096


class FederationPeerTrustCatalogError(ValueError):
    """A bounded, non-leaking trust catalog load or validation failure."""


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def catalog_digest_for(value: Mapping[str, object]) -> str:
    """Hash the canonical catalog body, excluding only its derived digest."""
    body = dict(value)
    body.pop("catalog_digest", None)
    return "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FederationPeerTrustCatalogError("catalog_json_duplicate_key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise FederationPeerTrustCatalogError("catalog_json_nonfinite_number")


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise FederationPeerTrustCatalogError("catalog_validity_invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FederationPeerTrustCatalogError("catalog_validity_invalid") from exc
    if (parsed.utcoffset() != timezone.utc.utcoffset(parsed)
            or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value):
        raise FederationPeerTrustCatalogError("catalog_validity_invalid")
    return parsed


def _decode_public_key(value: object) -> bytes:
    if not isinstance(value, str) or _BASE64URL.fullmatch(value) is None:
        raise FederationPeerTrustCatalogError("catalog_public_key_invalid")
    try:
        decoded = base64.b64decode(
            (value + "=" * (-len(value) % 4)).encode("ascii"),
            altchars=b"-_", validate=True,
        )
    except (UnicodeEncodeError, ValueError) as exc:
        raise FederationPeerTrustCatalogError("catalog_public_key_invalid") from exc
    if (len(decoded) != 32
            or base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != value):
        raise FederationPeerTrustCatalogError("catalog_public_key_invalid")
    return decoded


def _validate_endpoint(value: object) -> str:
    if (not isinstance(value, str) or not value or len(value) > 2048
            or any(ord(char) <= 0x20 or ord(char) == 0x7f for char in value)):
        raise FederationPeerTrustCatalogError("catalog_endpoint_invalid")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise FederationPeerTrustCatalogError("catalog_endpoint_invalid") from exc
    if (parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment or "?" in value or "#" in value
            or (port is not None and not 1 <= port <= 65535)):
        raise FederationPeerTrustCatalogError("catalog_endpoint_invalid")
    return value


@dataclass(frozen=True, slots=True)
class TrustedFederationPeerKey:
    """One operator-provisioned public key bound to a peer and configured endpoint."""

    peer_id: str
    signing_key_id: str
    endpoint: str
    algorithm: str
    public_key: str
    valid_from: str
    valid_until: str
    revocation_status: str


@dataclass(frozen=True, slots=True, init=False)
class ReadOnlyFederationPeerTrustCatalog:
    """Immutable lookup-only peer trust, pinned by installation-owned version and digest."""

    catalog_version: int
    catalog_digest: str
    _entries: Mapping[tuple[str, str, str], TrustedFederationPeerKey]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("trust catalogs must be created from pinned canonical bytes")

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        expected_catalog_version: int,
        expected_catalog_digest: str,
    ) -> ReadOnlyFederationPeerTrustCatalog:
        try:
            raw = read_explicit_file(Path(path), max_bytes=_MAX_CATALOG_BYTES)
        except (WindowsHandleCustodyError, OSError) as exc:
            raise FederationPeerTrustCatalogError("catalog_load_failed") from exc
        return cls.from_bytes(
            raw,
            expected_catalog_version=expected_catalog_version,
            expected_catalog_digest=expected_catalog_digest,
        )

    @classmethod
    def from_bytes(
        cls,
        raw: bytes,
        *,
        expected_catalog_version: int,
        expected_catalog_digest: str,
    ) -> ReadOnlyFederationPeerTrustCatalog:
        if type(expected_catalog_version) is not int or expected_catalog_version < 1:
            raise FederationPeerTrustCatalogError("expected_catalog_version_invalid")
        if not isinstance(expected_catalog_digest, str) or _DIGEST.fullmatch(expected_catalog_digest) is None:
            raise FederationPeerTrustCatalogError("expected_catalog_digest_invalid")
        if not isinstance(raw, bytes) or not raw or len(raw) > _MAX_CATALOG_BYTES:
            raise FederationPeerTrustCatalogError("catalog_size_invalid")
        try:
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_constant,
            )
        except FederationPeerTrustCatalogError:
            raise
        except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
            raise FederationPeerTrustCatalogError("catalog_load_failed") from exc
        if not isinstance(value, dict) or set(value) != _CATALOG_FIELDS:
            raise FederationPeerTrustCatalogError("catalog_fields_not_exact")
        if value.get("schema") != CATALOG_SCHEMA:
            raise FederationPeerTrustCatalogError("catalog_schema_invalid")
        version = value.get("catalog_version")
        if type(version) is not int or version != expected_catalog_version:
            raise FederationPeerTrustCatalogError("catalog_version_mismatch")
        claimed_digest = value.get("catalog_digest")
        try:
            computed_digest = catalog_digest_for(value)
        except (TypeError, ValueError, RecursionError) as exc:
            raise FederationPeerTrustCatalogError("catalog_content_invalid") from exc
        if (not isinstance(claimed_digest, str) or claimed_digest != computed_digest
                or claimed_digest != expected_catalog_digest):
            raise FederationPeerTrustCatalogError("catalog_digest_mismatch")
        try:
            canonical_catalog = _canonical(value)
        except (TypeError, ValueError, RecursionError) as exc:
            raise FederationPeerTrustCatalogError("catalog_content_invalid") from exc
        if canonical_catalog != raw:
            raise FederationPeerTrustCatalogError("catalog_not_canonical")
        raw_entries = value.get("entries")
        if (not isinstance(raw_entries, list) or len(raw_entries) > _MAX_CATALOG_ENTRIES):
            raise FederationPeerTrustCatalogError("catalog_entries_invalid")
        entries: dict[tuple[str, str, str], TrustedFederationPeerKey] = {}
        for row in raw_entries:
            if not isinstance(row, dict) or set(row) != _ENTRY_FIELDS:
                raise FederationPeerTrustCatalogError("catalog_entry_fields_not_exact")
            peer_id = row.get("peer_id")
            key_id = row.get("signing_key_id")
            endpoint = _validate_endpoint(row.get("endpoint"))
            if not isinstance(peer_id, str) or _PEER_ID.fullmatch(peer_id) is None:
                raise FederationPeerTrustCatalogError("catalog_peer_id_invalid")
            if not isinstance(key_id, str) or _KEY_ID.fullmatch(key_id) is None:
                raise FederationPeerTrustCatalogError("catalog_key_id_invalid")
            algorithm = row.get("algorithm")
            if algorithm != "ed25519":
                raise FederationPeerTrustCatalogError("catalog_algorithm_invalid")
            public_raw = _decode_public_key(row.get("public_key"))
            if key_id != "ed25519-sha256:" + hashlib.sha256(public_raw).hexdigest():
                raise FederationPeerTrustCatalogError("catalog_key_id_mismatch")
            start = _parse_time(row.get("valid_from"))
            end = _parse_time(row.get("valid_until"))
            if end <= start:
                raise FederationPeerTrustCatalogError("catalog_validity_invalid")
            revoked = row.get("revocation_status")
            if not isinstance(revoked, str) or revoked not in {"active", "revoked"}:
                raise FederationPeerTrustCatalogError("catalog_revocation_status_invalid")
            key = TrustedFederationPeerKey(
                peer_id=peer_id,
                signing_key_id=key_id,
                endpoint=endpoint,
                algorithm=algorithm,
                public_key=row["public_key"],
                valid_from=row["valid_from"],
                valid_until=row["valid_until"],
                revocation_status=revoked,
            )
            identity = (peer_id, key_id, endpoint)
            if identity in entries:
                raise FederationPeerTrustCatalogError("catalog_trust_tuple_duplicate")
            entries[identity] = key
        catalog = object.__new__(cls)
        object.__setattr__(catalog, "catalog_version", version)
        object.__setattr__(catalog, "catalog_digest", claimed_digest)
        object.__setattr__(catalog, "_entries", MappingProxyType(entries))
        return catalog

    def lookup(self, *, peer_id: str, signing_key_id: str, endpoint: str) -> TrustedFederationPeerKey | None:
        """Look up an exact configured identity tuple; this catalog cannot enroll or mutate."""
        return self._entries.get((peer_id, signing_key_id, endpoint))

    @property
    def peer_ids(self) -> frozenset[str]:
        """Return only peer identifiers present in this immutable catalog."""
        return frozenset(key.peer_id for key in self._entries.values())


__all__ = [
    "CATALOG_SCHEMA",
    "FederationPeerTrustCatalogError",
    "ReadOnlyFederationPeerTrustCatalog",
    "TrustedFederationPeerKey",
    "catalog_digest_for",
]
