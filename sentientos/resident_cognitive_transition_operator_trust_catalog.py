"""Immutable installation-provisioned public keys for transition operators."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping

from .resident_cognitive_transition_operator_authentication import (
    ED25519_ALGORITHM, TrustedTransitionOperatorKey,
)
from .windows_handle_custody import WindowsHandleCustodyError, read_explicit_file

CATALOG_SCHEMA = "sentientos.resident_cognitive_transition_operator_trust_catalog:v1"
_CATALOG_FIELDS = frozenset({"schema", "catalog_version", "entries", "catalog_digest"})
_ENTRY_FIELDS = frozenset({"operator_identity", "signing_key_id", "algorithm", "public_key",
                           "valid_from", "valid_until", "revocation_status"})
_IDENTITY = re.compile(r"[a-z0-9][a-z0-9._:/-]{0,127}")
_KEY_ID = re.compile(r"ed25519-sha256:[0-9a-f]{64}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class TransitionOperatorTrustCatalogError(ValueError):
    """A bounded catalog load or validation failure."""


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise TransitionOperatorTrustCatalogError("catalog_json_duplicate_key")
        result[key] = value
    return result


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise TransitionOperatorTrustCatalogError("catalog_validity_invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise TransitionOperatorTrustCatalogError("catalog_validity_invalid") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed) or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value:
        raise TransitionOperatorTrustCatalogError("catalog_validity_invalid")
    return parsed


def catalog_digest_for(value: Mapping[str, object]) -> str:
    body = dict(value)
    body.pop("catalog_digest", None)
    return "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()


@dataclass(frozen=True, slots=True)
class ReadOnlyTransitionOperatorTrustCatalog:
    catalog_version: int
    catalog_digest: str
    _entries: Mapping[tuple[str, str, str], TrustedTransitionOperatorKey]

    @classmethod
    def load(cls, path: str | Path, *, expected_catalog_version: int,
             expected_catalog_digest: str) -> ReadOnlyTransitionOperatorTrustCatalog:
        try:
            raw = read_explicit_file(Path(path), max_bytes=1_048_576)
        except (WindowsHandleCustodyError, OSError) as exc:
            raise TransitionOperatorTrustCatalogError("catalog_load_failed") from exc
        return cls.from_bytes(raw, expected_catalog_version=expected_catalog_version,
                              expected_catalog_digest=expected_catalog_digest)

    @classmethod
    def from_bytes(cls, raw: bytes, *, expected_catalog_version: int,
                   expected_catalog_digest: str) -> ReadOnlyTransitionOperatorTrustCatalog:
        if type(expected_catalog_version) is not int or expected_catalog_version < 1:
            raise TransitionOperatorTrustCatalogError("expected_catalog_version_invalid")
        if not isinstance(expected_catalog_digest, str) or _DIGEST.fullmatch(expected_catalog_digest) is None:
            raise TransitionOperatorTrustCatalogError("expected_catalog_digest_invalid")
        try:
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
        except TransitionOperatorTrustCatalogError:
            raise
        except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise TransitionOperatorTrustCatalogError("catalog_load_failed") from exc
        if not isinstance(value, dict) or set(value) != _CATALOG_FIELDS:
            raise TransitionOperatorTrustCatalogError("catalog_fields_not_exact")
        if value.get("schema") != CATALOG_SCHEMA:
            raise TransitionOperatorTrustCatalogError("catalog_schema_invalid")
        version = value.get("catalog_version")
        if type(version) is not int or version != expected_catalog_version:
            raise TransitionOperatorTrustCatalogError("catalog_version_mismatch")
        claimed_digest = value.get("catalog_digest")
        if (not isinstance(claimed_digest, str) or claimed_digest != catalog_digest_for(value)
                or claimed_digest != expected_catalog_digest):
            raise TransitionOperatorTrustCatalogError("catalog_digest_mismatch")
        if _canonical(value) != raw:
            raise TransitionOperatorTrustCatalogError("catalog_not_canonical")
        raw_entries = value.get("entries")
        if not isinstance(raw_entries, list):
            raise TransitionOperatorTrustCatalogError("catalog_entries_invalid")
        entries: dict[tuple[str, str, str], TrustedTransitionOperatorKey] = {}
        for raw_entry in raw_entries:
            entry = _validate_entry(raw_entry)
            key = (entry.operator_identity, entry.signing_key_id, entry.algorithm)
            if key in entries:
                raise TransitionOperatorTrustCatalogError("catalog_trust_tuple_duplicate")
            entries[key] = entry
        return cls(version, claimed_digest, MappingProxyType(entries))

    def lookup(self, *, operator_identity: str, signing_key_id: str,
               algorithm: str) -> TrustedTransitionOperatorKey | None:
        return self._entries.get((operator_identity, signing_key_id, algorithm))


def _validate_entry(value: object) -> TrustedTransitionOperatorKey:
    if not isinstance(value, dict) or set(value) != _ENTRY_FIELDS:
        raise TransitionOperatorTrustCatalogError("catalog_entry_fields_invalid")
    identity = value.get("operator_identity")
    if not isinstance(identity, str) or _IDENTITY.fullmatch(identity) is None:
        raise TransitionOperatorTrustCatalogError("catalog_operator_identity_invalid")
    algorithm = value.get("algorithm")
    if algorithm != ED25519_ALGORITHM:
        raise TransitionOperatorTrustCatalogError("catalog_algorithm_invalid")
    public_key = value.get("public_key")
    if not isinstance(public_key, str):
        raise TransitionOperatorTrustCatalogError("catalog_public_key_invalid")
    try:
        decoded = base64.b64decode((public_key + "=" * (-len(public_key) % 4)).encode("ascii"),
                                   altchars=b"-_", validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise TransitionOperatorTrustCatalogError("catalog_public_key_invalid") from exc
    if (len(decoded) != 32 or base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != public_key):
        raise TransitionOperatorTrustCatalogError("catalog_public_key_invalid")
    key_id = value.get("signing_key_id")
    expected_key_id = "ed25519-sha256:" + hashlib.sha256(decoded).hexdigest()
    if not isinstance(key_id, str) or _KEY_ID.fullmatch(key_id) is None or key_id != expected_key_id:
        raise TransitionOperatorTrustCatalogError("catalog_signing_key_id_invalid")
    valid_from, valid_until = value.get("valid_from"), value.get("valid_until")
    if _parse_time(valid_from) >= _parse_time(valid_until):
        raise TransitionOperatorTrustCatalogError("catalog_validity_invalid")
    revocation = value.get("revocation_status")
    if revocation not in {"active", "revoked"}:
        raise TransitionOperatorTrustCatalogError("catalog_revocation_status_invalid")
    assert isinstance(public_key, str) and isinstance(valid_from, str) and isinstance(valid_until, str)
    return TrustedTransitionOperatorKey(identity, key_id, algorithm, public_key,
                                        valid_from, valid_until, revocation)


__all__ = ["CATALOG_SCHEMA", "ReadOnlyTransitionOperatorTrustCatalog",
           "TransitionOperatorTrustCatalogError", "catalog_digest_for"]
