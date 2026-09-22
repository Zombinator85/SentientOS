"""Read-only operator-provisioned public trust for root-issuer verification.

The catalog digest self-binds catalog content; it does not authenticate an operator.
Trust comes from the operator-selected path, expected version, and expected digest passed
at process composition time.  This module loads once, owns public keys only, and offers
no enrollment, mutation, signing, discovery, admission, allocation, or effect surface.
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
from typing import Mapping

from sentientos.causal_resource_principal_authentication import TrustedRootIssuerKey

CATALOG_SCHEMA = "sentientos.causal_resource_principal.trusted_issuer_catalog:v1"

_CATALOG_FIELDS = frozenset({"schema", "catalog_version", "entries", "catalog_digest"})
_ENTRY_FIELDS = frozenset(
    {"issuer_id", "signing_key_id", "algorithm", "public_key", "valid_from", "valid_until", "revocation_status"}
)
_ISSUER_ID = re.compile(r"[a-z0-9][a-z0-9._:/-]{0,127}")
_KEY_ID = re.compile(r"ed25519-sha256:[0-9a-f]{64}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+")


class TrustedIssuerCatalogError(ValueError):
    """A bounded, non-leaking catalog load failure."""


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def catalog_digest_for(value: Mapping[str, object]) -> str:
    """Compute the integrity digest over every trust-bearing field except itself."""
    body = dict(value)
    body.pop("catalog_digest", None)
    return "sha256:" + hashlib.sha256(_canonical_bytes(body)).hexdigest()


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise TrustedIssuerCatalogError("invalid_entry_validity")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise TrustedIssuerCatalogError("invalid_entry_validity") from exc
    canonical = parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed) or canonical != value:
        raise TrustedIssuerCatalogError("invalid_entry_validity")
    return parsed


def _decode_public_key(value: object) -> bytes:
    if not isinstance(value, str) or _BASE64URL.fullmatch(value) is None:
        raise TrustedIssuerCatalogError("invalid_public_key")
    try:
        decoded = base64.b64decode((value + "=" * (-len(value) % 4)).encode("ascii"), altchars=b"-_", validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise TrustedIssuerCatalogError("invalid_public_key") from exc
    canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
    if len(decoded) != 32 or canonical != value:
        raise TrustedIssuerCatalogError("invalid_public_key")
    return decoded


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise TrustedIssuerCatalogError("catalog_json_invalid")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class ReadOnlyTrustedIssuerCatalog:
    """An immutable, exact-tuple implementation of ``RootIssuerTrustStore``."""

    catalog_version: int
    catalog_digest: str
    _entries: Mapping[tuple[str, str, str], TrustedRootIssuerKey]

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        expected_catalog_version: int,
        expected_catalog_digest: str,
    ) -> ReadOnlyTrustedIssuerCatalog:
        """Load once from operator-bound configuration and validate atomically."""
        if type(expected_catalog_version) is not int or expected_catalog_version < 1:
            raise TrustedIssuerCatalogError("expected_catalog_version_invalid")
        if not isinstance(expected_catalog_digest, str) or _DIGEST.fullmatch(expected_catalog_digest) is None:
            raise TrustedIssuerCatalogError("expected_catalog_digest_invalid")
        try:
            raw = Path(path).read_text(encoding="utf-8")
            value = json.loads(raw, object_pairs_hook=_reject_duplicate_json_keys)
        except TrustedIssuerCatalogError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise TrustedIssuerCatalogError("catalog_load_failed") from exc
        if not isinstance(value, dict) or set(value) != _CATALOG_FIELDS:
            raise TrustedIssuerCatalogError("catalog_fields_not_exact")
        if value.get("schema") != CATALOG_SCHEMA:
            raise TrustedIssuerCatalogError("unsupported_catalog_schema")
        version = value.get("catalog_version")
        if type(version) is not int or version < 1:
            raise TrustedIssuerCatalogError("unsupported_catalog_version")
        digest = value.get("catalog_digest")
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            raise TrustedIssuerCatalogError("invalid_catalog_digest")
        if digest != catalog_digest_for(value):
            raise TrustedIssuerCatalogError("catalog_digest_mismatch")
        if version != expected_catalog_version:
            raise TrustedIssuerCatalogError("unexpected_catalog_version")
        if digest != expected_catalog_digest:
            raise TrustedIssuerCatalogError("unexpected_catalog_digest")
        entries_value = value.get("entries")
        if not isinstance(entries_value, list):
            raise TrustedIssuerCatalogError("catalog_entries_invalid")
        entries: dict[tuple[str, str, str], TrustedRootIssuerKey] = {}
        for item in entries_value:
            entry = _validate_entry(item)
            key = (entry.issuer_id, entry.signing_key_id, entry.algorithm)
            if key in entries:
                raise TrustedIssuerCatalogError("duplicate_trust_tuple")
            entries[key] = entry
        return cls(version, digest, MappingProxyType(entries))

    def lookup(self, *, issuer_id: str, signing_key_id: str, algorithm: str) -> TrustedRootIssuerKey | None:
        """Return the sole exact trusted record, or no trust for an unknown tuple."""
        return self._entries.get((issuer_id, signing_key_id, algorithm))


def _validate_entry(value: object) -> TrustedRootIssuerKey:
    if not isinstance(value, dict) or set(value) != _ENTRY_FIELDS:
        raise TrustedIssuerCatalogError("entry_fields_not_exact")
    issuer = value.get("issuer_id")
    if not isinstance(issuer, str) or _ISSUER_ID.fullmatch(issuer) is None or issuer in {"all", "any"}:
        raise TrustedIssuerCatalogError("invalid_issuer_id")
    if value.get("algorithm") != "ed25519":
        raise TrustedIssuerCatalogError("unsupported_entry_algorithm")
    public_key = value.get("public_key")
    raw_public_key = _decode_public_key(public_key)
    key_id = value.get("signing_key_id")
    derived_key_id = "ed25519-sha256:" + hashlib.sha256(raw_public_key).hexdigest()
    if not isinstance(key_id, str) or _KEY_ID.fullmatch(key_id) is None or key_id != derived_key_id:
        raise TrustedIssuerCatalogError("invalid_signing_key_id")
    valid_from_value = value.get("valid_from")
    valid_until_value = value.get("valid_until")
    valid_from = _parse_time(valid_from_value)
    valid_until = _parse_time(valid_until_value)
    if valid_from >= valid_until:
        raise TrustedIssuerCatalogError("invalid_entry_validity")
    status = value.get("revocation_status")
    if status not in {"active", "revoked"}:
        raise TrustedIssuerCatalogError("invalid_revocation_status")
    assert isinstance(public_key, str) and isinstance(valid_from_value, str) and isinstance(valid_until_value, str)
    return TrustedRootIssuerKey(issuer, key_id, "ed25519", public_key, valid_from_value, valid_until_value, status)


__all__ = [
    "CATALOG_SCHEMA",
    "ReadOnlyTrustedIssuerCatalog",
    "TrustedIssuerCatalogError",
    "catalog_digest_for",
]
