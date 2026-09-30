"""Bounded principal-specific currentness verification for authenticated roots.

The operator-selected snapshot is loaded once and is read-only.  Currentness is
evidence about one instant and one snapshot; it grants no allocation, entitlement,
admission, or effect and is not a live revocation distribution mechanism.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping

from sentientos.causal_resource_principal import CausalResourcePrincipal, CausalResourcePrincipalError, CausalResourcePrincipalVerifier
from sentientos.causal_resource_principal_authentication import AuthenticatedRootPrincipalEvidence

REGISTRY_SCHEMA = "sentientos.causal_resource_principal.revocation_registry:v1"
_REGISTRY_FIELDS = frozenset({"schema", "registry_version", "generated_at", "valid_until", "revoked_principals", "registry_digest"})
_ENTRY_FIELDS = frozenset({"principal_id", "principal_binding_digest", "issuer_id", "epoch", "revoked_at"})
_PRINCIPAL_ID = re.compile(r"crp-sha256:[0-9a-f]{64}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_ISSUER_ID = re.compile(r"[a-z0-9][a-z0-9._:/-]{0,127}")


class PrincipalCurrentnessError(ValueError):
    """A bounded, non-leaking registry or verification failure."""


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def registry_digest_for(value: Mapping[str, object]) -> str:
    """Seal every snapshot/currentness-bearing field except the digest itself."""
    body = dict(value)
    body.pop("registry_digest", None)
    return "sha256:" + hashlib.sha256(_canonical_bytes(body)).hexdigest()


def _time(value: object, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PrincipalCurrentnessError(code)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PrincipalCurrentnessError(code) from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed) or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value:
        raise PrincipalCurrentnessError(code)
    return parsed


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PrincipalCurrentnessError("registry_json_invalid")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class RevokedPrincipalEntry:
    principal_id: str
    principal_binding_digest: str
    issuer_id: str
    epoch: int
    revoked_at: str


@dataclass(frozen=True, slots=True)
class ReadOnlyPrincipalRevocationRegistry:
    """One immutable operator-bound principal-revocation snapshot."""

    registry_version: int
    registry_digest: str
    generated_at: str
    valid_until: str
    revoked_principals: tuple[RevokedPrincipalEntry, ...]

    @classmethod
    def load(cls, path: str | Path, *, expected_registry_version: int, expected_registry_digest: str) -> ReadOnlyPrincipalRevocationRegistry:
        if type(expected_registry_version) is not int or expected_registry_version < 1:
            raise PrincipalCurrentnessError("expected_registry_version_invalid")
        if not isinstance(expected_registry_digest, str) or _DIGEST.fullmatch(expected_registry_digest) is None:
            raise PrincipalCurrentnessError("expected_registry_digest_invalid")
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
        except PrincipalCurrentnessError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise PrincipalCurrentnessError("registry_load_failed") from exc
        if not isinstance(value, dict) or set(value) != _REGISTRY_FIELDS:
            raise PrincipalCurrentnessError("registry_fields_not_exact")
        if value.get("schema") != REGISTRY_SCHEMA:
            raise PrincipalCurrentnessError("unsupported_registry_schema")
        version = value.get("registry_version")
        if type(version) is not int or version < 1:
            raise PrincipalCurrentnessError("invalid_registry_version")
        generated_at_value, valid_until_value = value.get("generated_at"), value.get("valid_until")
        generated_at = _time(generated_at_value, "invalid_registry_generated_at")
        valid_until = _time(valid_until_value, "invalid_registry_valid_until")
        if generated_at >= valid_until:
            raise PrincipalCurrentnessError("invalid_registry_validity_window")
        digest = value.get("registry_digest")
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            raise PrincipalCurrentnessError("invalid_registry_digest")
        if digest != registry_digest_for(value):
            raise PrincipalCurrentnessError("registry_digest_mismatch")
        if version != expected_registry_version:
            raise PrincipalCurrentnessError("unexpected_registry_version")
        if digest != expected_registry_digest:
            raise PrincipalCurrentnessError("unexpected_registry_digest")
        raw_entries = value.get("revoked_principals")
        if not isinstance(raw_entries, list):
            raise PrincipalCurrentnessError("revoked_principals_invalid")
        entries: list[RevokedPrincipalEntry] = []
        identities: set[tuple[str, str, str, int]] = set()
        for raw_entry in raw_entries:
            entry = _entry(raw_entry)
            identity = (entry.principal_id, entry.principal_binding_digest, entry.issuer_id, entry.epoch)
            if identity in identities:
                raise PrincipalCurrentnessError("duplicate_principal_revocation")
            identities.add(identity)
            entries.append(entry)
        assert isinstance(generated_at_value, str) and isinstance(valid_until_value, str)
        return cls(version, digest, generated_at_value, valid_until_value, tuple(entries))


def _entry(value: object) -> RevokedPrincipalEntry:
    if not isinstance(value, dict) or set(value) != _ENTRY_FIELDS:
        raise PrincipalCurrentnessError("revocation_entry_fields_not_exact")
    principal_id = value.get("principal_id")
    if not isinstance(principal_id, str) or _PRINCIPAL_ID.fullmatch(principal_id) is None:
        raise PrincipalCurrentnessError("invalid_revoked_principal_id")
    binding = value.get("principal_binding_digest")
    if not isinstance(binding, str) or _DIGEST.fullmatch(binding) is None:
        raise PrincipalCurrentnessError("invalid_revoked_principal_binding_digest")
    issuer = value.get("issuer_id")
    if not isinstance(issuer, str) or _ISSUER_ID.fullmatch(issuer) is None or issuer in {"all", "any"}:
        raise PrincipalCurrentnessError("invalid_revoked_issuer_id")
    epoch = value.get("epoch")
    if type(epoch) is not int or epoch < 1:
        raise PrincipalCurrentnessError("invalid_revoked_epoch")
    revoked_at = value.get("revoked_at")
    _time(revoked_at, "invalid_revoked_at")
    assert isinstance(binding, str) and isinstance(issuer, str) and isinstance(revoked_at, str)
    return RevokedPrincipalEntry(principal_id, binding, issuer, epoch, revoked_at)


_EVIDENCE_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False)
class CurrentAuthenticatedRootPrincipalEvidence:
    """Process-local proof of a bounded check; never a serialized authority claim."""

    principal_id: str
    principal_binding_digest: str
    issuer_id: str
    epoch: int
    provenance_digest: str
    revocation_registry_version: int
    revocation_registry_digest: str
    registry_generated_at: str
    registry_valid_until: str
    checked_at: str

    def __init__(self, *, _token: object, principal_id: str, principal_binding_digest: str, issuer_id: str, epoch: int,
                 provenance_digest: str, revocation_registry_version: int, revocation_registry_digest: str,
                 registry_generated_at: str, registry_valid_until: str, checked_at: str) -> None:
        if _token is not _EVIDENCE_TOKEN:
            raise PrincipalCurrentnessError("currentness_evidence_verifier_required")
        for name, value in locals().items():
            if name not in {"self", "_token"}:
                object.__setattr__(self, name, value)


class PrincipalCurrentnessVerifier:
    """Establish bounded currentness for one exact authenticated canonical root."""

    def verify(self, principal: CausalResourcePrincipal, authenticated: AuthenticatedRootPrincipalEvidence,
               registry: ReadOnlyPrincipalRevocationRegistry, *, current_time: str) -> CurrentAuthenticatedRootPrincipalEvidence:
        if type(principal) is not CausalResourcePrincipal:
            raise PrincipalCurrentnessError("canonical_principal_required")
        if type(authenticated) is not AuthenticatedRootPrincipalEvidence:
            raise PrincipalCurrentnessError("authenticated_evidence_required")
        if type(registry) is not ReadOnlyPrincipalRevocationRegistry:
            raise PrincipalCurrentnessError("revocation_registry_required")
        if authenticated.principal_id != principal.principal_id:
            raise PrincipalCurrentnessError("authenticated_principal_id_mismatch")
        if authenticated.principal_binding_digest != principal.binding_digest:
            raise PrincipalCurrentnessError("authenticated_principal_binding_mismatch")
        if authenticated.issuer_id != principal.issuer_id:
            raise PrincipalCurrentnessError("authenticated_issuer_mismatch")
        try:
            verified = CausalResourcePrincipalVerifier().verify(principal, current_time=current_time)
        except CausalResourcePrincipalError as exc:
            raise PrincipalCurrentnessError(str(exc)) from exc
        now = _time(current_time, "invalid_current_time")
        if now < _time(registry.generated_at, "invalid_registry_generated_at"):
            raise PrincipalCurrentnessError("registry_not_yet_valid")
        if now >= _time(registry.valid_until, "invalid_registry_valid_until"):
            raise PrincipalCurrentnessError("registry_stale")
        for entry in registry.revoked_principals:
            if entry.principal_id != verified.principal_id:
                continue
            if entry.principal_binding_digest != verified.binding_digest:
                raise PrincipalCurrentnessError("revocation_principal_binding_mismatch")
            if entry.issuer_id != verified.issuer_id:
                raise PrincipalCurrentnessError("revocation_issuer_mismatch")
            if entry.epoch != verified.epoch:
                raise PrincipalCurrentnessError("revocation_epoch_mismatch")
            if now >= _time(entry.revoked_at, "invalid_revoked_at"):
                raise PrincipalCurrentnessError("principal_revoked")
        return CurrentAuthenticatedRootPrincipalEvidence(
            _token=_EVIDENCE_TOKEN, principal_id=verified.principal_id, principal_binding_digest=verified.binding_digest,
            issuer_id=verified.issuer_id, epoch=verified.epoch, provenance_digest=authenticated.provenance_digest,
            revocation_registry_version=registry.registry_version, revocation_registry_digest=registry.registry_digest,
            registry_generated_at=registry.generated_at, registry_valid_until=registry.valid_until, checked_at=current_time,
        )


__all__ = ["REGISTRY_SCHEMA", "CurrentAuthenticatedRootPrincipalEvidence", "PrincipalCurrentnessError",
           "PrincipalCurrentnessVerifier", "ReadOnlyPrincipalRevocationRegistry", "RevokedPrincipalEntry",
           "registry_digest_for"]
