"""Verify operator provenance for resident transition requests.

Verification is deliberately separate from signing and admission.  This module
accepts only public trust supplied by the installation owner and authenticates
the exact immutable request claims; it grants no authority and performs no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import json
import re
from typing import Mapping, Protocol

OPERATOR_PROVENANCE_SCHEMA = "sentientos.resident_cognitive_transition_operator_provenance:v1"
SIGNING_DOMAIN = "sentientos.resident_cognitive_transition_operator_request:v1"
ED25519_ALGORITHM = "ed25519"
_PROVENANCE_FIELDS = frozenset({
    "schema", "operator_identity", "signing_key_id", "algorithm", "signed_at",
    "request_claims_digest", "signature", "provenance_digest",
})
_IDENTITY = re.compile(r"[a-z0-9][a-z0-9._:/-]{0,127}")
_KEY_ID = re.compile(r"ed25519-sha256:[0-9a-f]{64}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+")


class TransitionOperatorProvenanceError(ValueError):
    """A bounded, fail-closed operator provenance verification failure."""


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _parse_time(value: object, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise TransitionOperatorProvenanceError(code)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise TransitionOperatorProvenanceError(code) from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed) or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value:
        raise TransitionOperatorProvenanceError(code)
    return parsed


def _decode(value: object, length: int, code: str) -> bytes:
    if not isinstance(value, str) or _BASE64URL.fullmatch(value) is None:
        raise TransitionOperatorProvenanceError(code)
    try:
        raw = base64.b64decode((value + "=" * (-len(value) % 4)).encode("ascii"), altchars=b"-_", validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise TransitionOperatorProvenanceError(code) from exc
    if len(raw) != length or base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value:
        raise TransitionOperatorProvenanceError(code)
    return raw


def operator_request_claims_digest(request: Mapping[str, object]) -> str:
    """Hash every request claim except its detached provenance and derived IDs."""
    claims = dict(request)
    for field in ("operator_provenance", "request_id", "request_digest"):
        claims.pop(field, None)
    return "sha256:" + hashlib.sha256(_canonical(claims)).hexdigest()


def canonical_operator_request_payload(*, operator_identity: str, signing_key_id: str,
                                      signed_at: str, request_claims_digest: str) -> bytes:
    """Return exact domain-separated bytes for an offline operator signer."""
    return _canonical({
        "schema": OPERATOR_PROVENANCE_SCHEMA,
        "domain": SIGNING_DOMAIN,
        "operator_identity": operator_identity,
        "signing_key_id": signing_key_id,
        "algorithm": ED25519_ALGORITHM,
        "signed_at": signed_at,
        "request_claims_digest": request_claims_digest,
    })


def provenance_digest_for(value: Mapping[str, object]) -> str:
    body = dict(value)
    body.pop("provenance_digest", None)
    return "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()


def seal_request_with_operator_provenance(request: Mapping[str, object],
                                          provenance: Mapping[str, object]) -> dict[str, object]:
    """Attach an already signed claim and recompute the request's integrity IDs."""
    body = dict(request)
    body.pop("request_id", None)
    body.pop("request_digest", None)
    body["operator_provenance"] = dict(provenance)
    request_digest = hashlib.sha256(_canonical(body)).hexdigest()
    return {**body, "request_id": "resident-transition-request-" + request_digest[:24],
            "request_digest": request_digest}


@dataclass(frozen=True, slots=True)
class TrustedTransitionOperatorKey:
    operator_identity: str
    signing_key_id: str
    algorithm: str
    public_key: str
    valid_from: str
    valid_until: str
    revocation_status: str


class TransitionOperatorTrustStore(Protocol):
    """Lookup-only trust interface; there is no enrollment or mutation method."""

    def lookup(self, *, operator_identity: str, signing_key_id: str,
               algorithm: str) -> TrustedTransitionOperatorKey | None: ...


class TransitionOperatorSignatureVerifier(Protocol):
    """Injected signature verification backend; signing is intentionally absent."""

    def verify(self, *, algorithm: str, public_key: str, payload: bytes, signature: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class AuthenticatedTransitionOperatorRequest:
    operator_identity: str
    signing_key_id: str
    request_claims_digest: str
    provenance_digest: str
    signed_at: str


class TransitionOperatorProvenanceVerifier:
    """Authenticate one exact request against operator-selected public trust."""

    def __init__(self, *, trust_store: TransitionOperatorTrustStore,
                 signature_verifier: TransitionOperatorSignatureVerifier) -> None:
        self._trust_store = trust_store
        self._signature_verifier = signature_verifier

    def verify(self, request: Mapping[str, object], *, current_time: datetime) -> AuthenticatedTransitionOperatorRequest:
        provenance = request.get("operator_provenance")
        if not isinstance(provenance, Mapping) or set(provenance) != _PROVENANCE_FIELDS:
            raise TransitionOperatorProvenanceError("operator_provenance_fields_invalid")
        operator_identity = request.get("operator_identity")
        if (not isinstance(operator_identity, str) or _IDENTITY.fullmatch(operator_identity) is None
                or provenance.get("schema") != OPERATOR_PROVENANCE_SCHEMA
                or provenance.get("operator_identity") != operator_identity):
            raise TransitionOperatorProvenanceError("operator_provenance_identity_invalid")
        signing_key_id = provenance.get("signing_key_id")
        if not isinstance(signing_key_id, str) or _KEY_ID.fullmatch(signing_key_id) is None:
            raise TransitionOperatorProvenanceError("operator_provenance_key_invalid")
        if provenance.get("algorithm") != ED25519_ALGORITHM:
            raise TransitionOperatorProvenanceError("operator_provenance_algorithm_invalid")
        signed_at = provenance.get("signed_at")
        signed_time = _parse_time(signed_at, "operator_provenance_time_invalid")
        try:
            if current_time.tzinfo is None or current_time.utcoffset() is None:
                raise TransitionOperatorProvenanceError("operator_provenance_time_invalid")
            now = current_time.astimezone(timezone.utc)
        except TransitionOperatorProvenanceError:
            raise
        except (OverflowError, TypeError, ValueError) as exc:
            raise TransitionOperatorProvenanceError("operator_provenance_time_invalid") from exc
        claims_digest = operator_request_claims_digest(request)
        if provenance.get("request_claims_digest") != claims_digest:
            raise TransitionOperatorProvenanceError("operator_provenance_request_mismatch")
        claimed_digest = provenance.get("provenance_digest")
        if (not isinstance(claimed_digest, str) or _DIGEST.fullmatch(claimed_digest) is None
                or claimed_digest != provenance_digest_for(provenance)):
            raise TransitionOperatorProvenanceError("operator_provenance_digest_invalid")
        _decode(provenance.get("signature"), 64, "operator_provenance_signature_invalid")
        try:
            trusted = self._trust_store.lookup(operator_identity=operator_identity,
                signing_key_id=signing_key_id, algorithm=ED25519_ALGORITHM)
        except Exception as exc:
            raise TransitionOperatorProvenanceError("operator_provenance_trust_unavailable") from exc
        if trusted is None:
            raise TransitionOperatorProvenanceError("operator_provenance_untrusted")
        if (trusted.operator_identity != operator_identity or trusted.signing_key_id != signing_key_id
                or trusted.algorithm != ED25519_ALGORITHM or trusted.revocation_status != "active"):
            raise TransitionOperatorProvenanceError("operator_provenance_key_not_active")
        key_start = _parse_time(trusted.valid_from, "operator_provenance_key_validity_invalid")
        key_end = _parse_time(trusted.valid_until, "operator_provenance_key_validity_invalid")
        if key_start >= key_end or not key_start <= signed_time < key_end or not key_start <= now < key_end:
            raise TransitionOperatorProvenanceError("operator_provenance_key_outside_validity")
        # Request creation and expiry are signature-bound claims, but admission
        # owns their live validity check. Journal recovery may need to reconcile
        # a genuinely signed, previously admitted request after its window closes.
        if signed_time > now:
            raise TransitionOperatorProvenanceError("operator_provenance_time_invalid")
        payload = canonical_operator_request_payload(operator_identity=operator_identity,
            signing_key_id=signing_key_id, signed_at=str(signed_at), request_claims_digest=claims_digest)
        try:
            valid = self._signature_verifier.verify(algorithm=ED25519_ALGORITHM,
                public_key=trusted.public_key, payload=payload, signature=str(provenance.get("signature")))
        except Exception as exc:
            raise TransitionOperatorProvenanceError("operator_provenance_verifier_unavailable") from exc
        if valid is not True:
            raise TransitionOperatorProvenanceError("operator_provenance_signature_invalid")
        return AuthenticatedTransitionOperatorRequest(operator_identity, signing_key_id,
            claims_digest, claimed_digest, str(signed_at))


__all__ = [
    "AuthenticatedTransitionOperatorRequest", "OPERATOR_PROVENANCE_SCHEMA",
    "TrustedTransitionOperatorKey", "TransitionOperatorProvenanceError",
    "TransitionOperatorProvenanceVerifier", "TransitionOperatorSignatureVerifier",
    "TransitionOperatorTrustStore", "canonical_operator_request_payload",
    "operator_request_claims_digest", "provenance_digest_for",
    "seal_request_with_operator_provenance",
]
