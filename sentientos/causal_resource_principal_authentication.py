"""Issuer-authentication claims for inert causal resource principals.

This module supplies only verification boundaries.  Authentication performed here
grants nothing, admits nothing, allocates nothing, and executes nothing.  In
particular, no production signer, cryptographic backend, or trust-store mutation
surface is provided.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import base64
import hashlib
import json
import re
from typing import Any, Mapping, Protocol

from sentientos.causal_resource_principal import (
    CausalResourcePrincipal,
    CausalResourcePrincipalVerifier,
)

PROVENANCE_SCHEMA = "sentientos.causal_resource_principal.issuer_provenance:v1"
SIGNING_DOMAIN = "sentientos.causal_resource_principal.issuer_provenance:v1"
ED25519_ALGORITHM = "ed25519"

_FIELDS = frozenset(
    {
        "schema",
        "principal_id",
        "principal_binding_digest",
        "issuer_id",
        "signing_key_id",
        "algorithm",
        "signed_at",
        "signature",
        "provenance_digest",
    }
)
_PRINCIPAL_ID = re.compile(r"crp-sha256:[0-9a-f]{64}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_ISSUER_ID = re.compile(r"[a-z0-9][a-z0-9._:/-]{0,127}")
_KEY_ID = re.compile(r"ed25519-sha256:[0-9a-f]{64}")


class RootIssuerProvenanceError(ValueError):
    """A fail-closed, bounded provenance verification failure."""


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _parse_time(value: object, error: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise RootIssuerProvenanceError(error)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RootIssuerProvenanceError(error) from exc
    canonical = parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed) or canonical != value:
        raise RootIssuerProvenanceError(error)
    return parsed


def _decode_base64url(value: object, length: int, error: str) -> bytes:
    if not isinstance(value, str) or not value or "=" in value:
        raise RootIssuerProvenanceError(error)
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise RootIssuerProvenanceError(error) from exc
    if len(decoded) != length or base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != value:
        raise RootIssuerProvenanceError(error)
    return decoded


def canonical_root_provenance_payload(
    *,
    principal_id: str,
    principal_binding_digest: str,
    issuer_id: str,
    signing_key_id: str,
    algorithm: str,
    signed_at: str,
) -> bytes:
    """Build the exact domain-separated bytes signed by an issuer backend."""
    return _canonical_bytes(
        {
            "schema": PROVENANCE_SCHEMA,
            "domain": SIGNING_DOMAIN,
            "principal_id": principal_id,
            "principal_binding_digest": principal_binding_digest,
            "issuer_id": issuer_id,
            "signing_key_id": signing_key_id,
            "algorithm": algorithm,
            "signed_at": signed_at,
        }
    )


def provenance_digest_for(value: Mapping[str, object]) -> str:
    """Return the envelope integrity digest, which is not authentication."""
    body = dict(value)
    body.pop("provenance_digest", None)
    return "sha256:" + hashlib.sha256(_canonical_bytes(body)).hexdigest()


@dataclass(frozen=True)
class RootPrincipalIssuerProvenance:
    """Serialized issuer-provenance claim; its presence does not establish trust."""

    schema: str
    principal_id: str
    principal_binding_digest: str
    issuer_id: str
    signing_key_id: str
    algorithm: str
    signed_at: str
    signature: str
    provenance_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def create(
        cls,
        *,
        principal_id: str,
        principal_binding_digest: str,
        issuer_id: str,
        signing_key_id: str,
        algorithm: str,
        signed_at: str,
        signature: str,
    ) -> RootPrincipalIssuerProvenance:
        body: dict[str, object] = {
            "schema": PROVENANCE_SCHEMA,
            "principal_id": principal_id,
            "principal_binding_digest": principal_binding_digest,
            "issuer_id": issuer_id,
            "signing_key_id": signing_key_id,
            "algorithm": algorithm,
            "signed_at": signed_at,
            "signature": signature,
        }
        return cls.from_mapping({**body, "provenance_digest": provenance_digest_for(body)})

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> RootPrincipalIssuerProvenance:
        if set(value) != _FIELDS:
            raise RootIssuerProvenanceError("provenance_fields_not_exact")
        if value.get("schema") != PROVENANCE_SCHEMA:
            raise RootIssuerProvenanceError("unsupported_schema")
        principal_id = value.get("principal_id")
        if not isinstance(principal_id, str) or _PRINCIPAL_ID.fullmatch(principal_id) is None:
            raise RootIssuerProvenanceError("invalid_principal_id")
        binding = value.get("principal_binding_digest")
        if not isinstance(binding, str) or _DIGEST.fullmatch(binding) is None:
            raise RootIssuerProvenanceError("invalid_principal_binding_digest")
        issuer = value.get("issuer_id")
        if not isinstance(issuer, str) or _ISSUER_ID.fullmatch(issuer) is None or issuer in {"all", "any"}:
            raise RootIssuerProvenanceError("invalid_issuer_id")
        key_id = value.get("signing_key_id")
        if not isinstance(key_id, str) or _KEY_ID.fullmatch(key_id) is None or key_id == issuer:
            raise RootIssuerProvenanceError("invalid_signing_key_id")
        if value.get("algorithm") != ED25519_ALGORITHM:
            raise RootIssuerProvenanceError("unsupported_algorithm")
        _parse_time(value.get("signed_at"), "invalid_signed_at")
        _decode_base64url(value.get("signature"), 64, "invalid_signature_encoding")
        digest = value.get("provenance_digest")
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None or digest != provenance_digest_for(value):
            raise RootIssuerProvenanceError("invalid_provenance_digest")
        try:
            return cls(**dict(value))  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise RootIssuerProvenanceError("provenance_fields_not_exact") from exc


@dataclass(frozen=True)
class TrustedRootIssuerKey:
    """One immutable, public, lookup result supplied by trusted configuration."""

    issuer_id: str
    signing_key_id: str
    algorithm: str
    public_key: str
    valid_from: str
    valid_until: str
    revocation_status: str


class RootIssuerTrustStore(Protocol):
    """Lookup-only trust boundary; mutation is deliberately absent."""

    def lookup(self, *, issuer_id: str, signing_key_id: str, algorithm: str) -> TrustedRootIssuerKey | None: ...


class RootIssuerSignatureVerifier(Protocol):
    """Injected verification-only backend."""

    def verify(self, *, algorithm: str, public_key: str, payload: bytes, signature: str) -> bool: ...


class RootIssuerProvenanceSigner(Protocol):
    """Future purpose-scoped signer boundary; not implemented in production here."""

    def authenticate_root_provenance(
        self, principal: CausalResourcePrincipal, *, signed_at: str
    ) -> RootPrincipalIssuerProvenance: ...


@dataclass(frozen=True)
class AuthenticatedRootPrincipalEvidence:
    """Process-local verifier result carrying no authority or allocation."""

    principal_id: str
    principal_binding_digest: str
    provenance_digest: str
    issuer_id: str
    signing_key_id: str
    algorithm: str
    signed_at: str


class RootIssuerProvenanceVerifier:
    """Authenticate an exact canonical principal against injected public trust."""

    def __init__(self, *, trust_store: RootIssuerTrustStore, signature_verifier: RootIssuerSignatureVerifier) -> None:
        self._trust_store = trust_store
        self._signature_verifier = signature_verifier

    def verify(
        self,
        principal: CausalResourcePrincipal | Mapping[str, object],
        provenance: RootPrincipalIssuerProvenance | Mapping[str, object],
        *,
        current_time: str,
    ) -> AuthenticatedRootPrincipalEvidence:
        # Principal canonicality and current validity are intentionally checked first.
        verified_principal = CausalResourcePrincipalVerifier().verify(principal, current_time=current_time)
        claim_mapping = provenance.to_dict() if isinstance(provenance, RootPrincipalIssuerProvenance) else provenance
        claim = RootPrincipalIssuerProvenance.from_mapping(claim_mapping)
        if claim.principal_id != verified_principal.principal_id or claim.principal_binding_digest != verified_principal.binding_digest:
            raise RootIssuerProvenanceError("principal_binding_mismatch")
        if claim.issuer_id != verified_principal.issuer_id:
            raise RootIssuerProvenanceError("issuer_mismatch")
        signed_at = _parse_time(claim.signed_at, "invalid_signed_at")
        issued_at = _parse_time(verified_principal.issued_at, "invalid_signed_at")
        expires_at = _parse_time(verified_principal.expires_at, "invalid_signed_at")
        if signed_at < issued_at or signed_at >= expires_at:
            raise RootIssuerProvenanceError("invalid_signed_at")
        try:
            trusted = self._trust_store.lookup(
                issuer_id=claim.issuer_id,
                signing_key_id=claim.signing_key_id,
                algorithm=claim.algorithm,
            )
        except Exception as exc:
            raise RootIssuerProvenanceError("trusted_key_not_found") from exc
        if trusted is None:
            raise RootIssuerProvenanceError("trusted_key_not_found")
        if (trusted.issuer_id, trusted.signing_key_id, trusted.algorithm) != (
            claim.issuer_id,
            claim.signing_key_id,
            claim.algorithm,
        ):
            raise RootIssuerProvenanceError("trusted_key_binding_mismatch")
        try:
            raw_public_key = _decode_base64url(trusted.public_key, 32, "trusted_key_binding_mismatch")
        except RootIssuerProvenanceError as exc:
            raise RootIssuerProvenanceError("trusted_key_binding_mismatch") from exc
        derived_key_id = "ed25519-sha256:" + hashlib.sha256(raw_public_key).hexdigest()
        if derived_key_id != claim.signing_key_id:
            raise RootIssuerProvenanceError("trusted_key_binding_mismatch")
        try:
            valid_from = _parse_time(trusted.valid_from, "trusted_key_binding_mismatch")
            valid_until = _parse_time(trusted.valid_until, "trusted_key_binding_mismatch")
        except RootIssuerProvenanceError as exc:
            raise RootIssuerProvenanceError("trusted_key_binding_mismatch") from exc
        if signed_at < valid_from:
            raise RootIssuerProvenanceError("trusted_key_not_yet_valid")
        if signed_at >= valid_until:
            raise RootIssuerProvenanceError("trusted_key_expired")
        if trusted.revocation_status == "revoked":
            raise RootIssuerProvenanceError("trusted_key_revoked")
        if trusted.revocation_status != "active":
            raise RootIssuerProvenanceError("trusted_key_binding_mismatch")
        payload = canonical_root_provenance_payload(
            principal_id=claim.principal_id,
            principal_binding_digest=claim.principal_binding_digest,
            issuer_id=claim.issuer_id,
            signing_key_id=claim.signing_key_id,
            algorithm=claim.algorithm,
            signed_at=claim.signed_at,
        )
        try:
            valid_signature = self._signature_verifier.verify(
                algorithm=claim.algorithm,
                public_key=trusted.public_key,
                payload=payload,
                signature=claim.signature,
            )
        except Exception as exc:
            raise RootIssuerProvenanceError("signature_backend_unavailable") from exc
        if valid_signature is not True:
            raise RootIssuerProvenanceError("signature_verification_failed")
        return AuthenticatedRootPrincipalEvidence(
            principal_id=claim.principal_id,
            principal_binding_digest=claim.principal_binding_digest,
            provenance_digest=claim.provenance_digest,
            issuer_id=claim.issuer_id,
            signing_key_id=claim.signing_key_id,
            algorithm=claim.algorithm,
            signed_at=claim.signed_at,
        )
