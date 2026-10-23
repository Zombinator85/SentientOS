"""Verify canonical, signed federation peer events without granting authority.

The verifier checks an operator-pinned peer key, endpoint binding, signature,
freshness, and one expected next sequence. It is pure with respect to replay
state: the caller must supply its independently committed sequence and persist a
new sequence through its own governed owner. No relay, Health, network, signing,
enrollment, or admission surface is provided here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import re
from types import MappingProxyType
from typing import Mapping, Protocol, cast

from .peer_trust_catalog import ReadOnlyFederationPeerTrustCatalog

PEER_EVENT_SCHEMA = "sentientos.federation.peer_event:v1"
PEER_EVENT_SIGNING_DOMAIN = "sentientos.federation.peer_event_signature:v1"
ED25519_ALGORITHM = "ed25519"
_MAX_EVENT_BYTES = 65_536
_MAX_SEQUENCE = 2**63 - 1
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+\Z")
_ENVELOPE_FIELDS = frozenset({
    "schema", "peer_id", "signing_key_id", "endpoint", "sequence",
    "issued_at", "event", "event_digest", "signature",
})


class FederationPeerEventVerificationError(ValueError):
    """A bounded, fail-closed signed peer event verification failure."""


class FederationPeerSignatureVerifier(Protocol):
    """Injected verification backend. Signing and private key access are absent."""

    def verify(self, *, algorithm: str, public_key: str, payload: bytes, signature: str) -> bool:
        """Return true only when the public key validates the exact payload signature."""


@dataclass(frozen=True, slots=True)
class VerifiedFederationPeerEvent:
    """Authenticated event provenance; this value grants no admission or execution authority."""

    peer_id: str
    signing_key_id: str
    endpoint: str
    sequence: int
    issued_at: str
    event_digest: str
    catalog_version: int
    catalog_digest: str
    event: Mapping[str, object]


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def federation_peer_event_digest(event: Mapping[str, object]) -> str:
    """Compute a domain-neutral digest of the exact event object."""
    return "sha256:" + hashlib.sha256(_canonical(event)).hexdigest()


def canonical_federation_peer_event_signing_payload(
    *,
    peer_id: str,
    signing_key_id: str,
    endpoint: str,
    sequence: int,
    issued_at: str,
    event_digest: str,
) -> bytes:
    """Return canonical domain-separated bytes for an offline peer signer."""
    return _canonical({
        "schema": PEER_EVENT_SCHEMA,
        "domain": PEER_EVENT_SIGNING_DOMAIN,
        "peer_id": peer_id,
        "signing_key_id": signing_key_id,
        "algorithm": ED25519_ALGORITHM,
        "endpoint": endpoint,
        "sequence": sequence,
        "issued_at": issued_at,
        "event_digest": event_digest,
    })


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FederationPeerEventVerificationError("peer_event_json_duplicate_key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise FederationPeerEventVerificationError("peer_event_json_nonfinite_number")


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise FederationPeerEventVerificationError("peer_event_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FederationPeerEventVerificationError("peer_event_timestamp_invalid") from exc
    if (parsed.utcoffset() != timezone.utc.utcoffset(parsed)
            or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value):
        raise FederationPeerEventVerificationError("peer_event_timestamp_invalid")
    return parsed


def _decode_signature(value: object) -> bytes:
    if not isinstance(value, str) or _BASE64URL.fullmatch(value) is None:
        raise FederationPeerEventVerificationError("peer_event_signature_encoding_invalid")
    try:
        decoded = base64.b64decode(
            (value + "=" * (-len(value) % 4)).encode("ascii"),
            altchars=b"-_", validate=True,
        )
    except (UnicodeEncodeError, ValueError) as exc:
        raise FederationPeerEventVerificationError("peer_event_signature_encoding_invalid") from exc
    if (len(decoded) != 64
            or base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != value):
        raise FederationPeerEventVerificationError("peer_event_signature_encoding_invalid")
    return decoded


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def verify_federation_peer_event(
    raw: bytes,
    *,
    catalog: ReadOnlyFederationPeerTrustCatalog,
    signature_verifier: FederationPeerSignatureVerifier,
    now: datetime,
    last_accepted_sequence: int,
    max_age_seconds: int = 300,
    future_skew_seconds: int = 30,
) -> VerifiedFederationPeerEvent:
    """Verify one exact canonical envelope against provisioned trust and replay state.

    last_accepted_sequence must come from the local governed replay owner. The
    verifier requires the next consecutive value and never updates that state.
    Freshness limits and now are explicit so callers can bind tests and clocks.
    """
    if not isinstance(raw, bytes) or not raw or len(raw) > _MAX_EVENT_BYTES:
        raise FederationPeerEventVerificationError("peer_event_size_invalid")
    if (not isinstance(catalog, ReadOnlyFederationPeerTrustCatalog)
            or not callable(getattr(signature_verifier, "verify", None))):
        raise FederationPeerEventVerificationError("peer_event_verifier_invalid")
    if (not isinstance(now, datetime) or now.tzinfo is None
            or now.utcoffset() != timedelta(0)):
        raise FederationPeerEventVerificationError("peer_event_clock_invalid")
    if (type(last_accepted_sequence) is not int
            or not 0 <= last_accepted_sequence < _MAX_SEQUENCE):
        raise FederationPeerEventVerificationError("peer_event_replay_state_invalid")
    if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 86_400:
        raise FederationPeerEventVerificationError("peer_event_freshness_policy_invalid")
    if type(future_skew_seconds) is not int or not 0 <= future_skew_seconds <= 300:
        raise FederationPeerEventVerificationError("peer_event_freshness_policy_invalid")

    try:
        envelope = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except FederationPeerEventVerificationError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise FederationPeerEventVerificationError("peer_event_load_failed") from exc
    if not isinstance(envelope, dict) or set(envelope) != _ENVELOPE_FIELDS:
        raise FederationPeerEventVerificationError("peer_event_fields_not_exact")
    if envelope.get("schema") != PEER_EVENT_SCHEMA:
        raise FederationPeerEventVerificationError("peer_event_schema_invalid")
    peer_id = envelope.get("peer_id")
    key_id = envelope.get("signing_key_id")
    endpoint = envelope.get("endpoint")
    sequence = envelope.get("sequence")
    issued_at_text = envelope.get("issued_at")
    event = envelope.get("event")
    event_digest = envelope.get("event_digest")
    signature = envelope.get("signature")
    if (not isinstance(peer_id, str) or not isinstance(key_id, str)
            or not isinstance(endpoint, str) or not isinstance(issued_at_text, str)
            or not isinstance(signature, str) or type(sequence) is not int
            or sequence < 1 or sequence > _MAX_SEQUENCE or not isinstance(event, dict)):
        raise FederationPeerEventVerificationError("peer_event_claim_invalid")
    if sequence != last_accepted_sequence + 1:
        raise FederationPeerEventVerificationError("peer_event_sequence_not_next")
    try:
        canonical = _canonical(envelope)
        computed_event_digest = federation_peer_event_digest(cast(Mapping[str, object], event))
    except (TypeError, ValueError, RecursionError) as exc:
        raise FederationPeerEventVerificationError("peer_event_content_invalid") from exc
    if raw != canonical:
        raise FederationPeerEventVerificationError("peer_event_not_canonical")
    if (not isinstance(event_digest, str) or _DIGEST.fullmatch(event_digest) is None
            or event_digest != computed_event_digest):
        raise FederationPeerEventVerificationError("peer_event_digest_mismatch")
    issued_at = _parse_time(issued_at_text)
    if (issued_at - now).total_seconds() > future_skew_seconds:
        raise FederationPeerEventVerificationError("peer_event_from_future")
    if (now - issued_at).total_seconds() > max_age_seconds:
        raise FederationPeerEventVerificationError("peer_event_stale")
    key = catalog.lookup(peer_id=peer_id, signing_key_id=key_id, endpoint=endpoint)
    if key is None:
        raise FederationPeerEventVerificationError("peer_event_trust_not_found")
    if key.algorithm != ED25519_ALGORITHM:
        raise FederationPeerEventVerificationError("peer_event_algorithm_invalid")
    if key.revocation_status != "active":
        raise FederationPeerEventVerificationError("peer_event_key_revoked")
    valid_from = _parse_time(key.valid_from)
    valid_until = _parse_time(key.valid_until)
    if not valid_from <= issued_at < valid_until or not valid_from <= now < valid_until:
        raise FederationPeerEventVerificationError("peer_event_key_outside_validity")
    _decode_signature(signature)
    payload = canonical_federation_peer_event_signing_payload(
        peer_id=peer_id,
        signing_key_id=key_id,
        endpoint=endpoint,
        sequence=sequence,
        issued_at=issued_at_text,
        event_digest=event_digest,
    )
    try:
        verified = signature_verifier.verify(
            algorithm=key.algorithm,
            public_key=key.public_key,
            payload=payload,
            signature=signature,
        )
    except Exception as exc:
        raise FederationPeerEventVerificationError("peer_event_signature_verification_failed") from exc
    if verified is not True:
        raise FederationPeerEventVerificationError("peer_event_signature_invalid")
    frozen_event = _freeze(event)
    return VerifiedFederationPeerEvent(
        peer_id=peer_id,
        signing_key_id=key_id,
        endpoint=endpoint,
        sequence=sequence,
        issued_at=issued_at_text,
        event_digest=event_digest,
        catalog_version=catalog.catalog_version,
        catalog_digest=catalog.catalog_digest,
        event=cast(Mapping[str, object], frozen_event),
    )


__all__ = [
    "ED25519_ALGORITHM",
    "FederationPeerEventVerificationError",
    "FederationPeerSignatureVerifier",
    "PEER_EVENT_SCHEMA",
    "PEER_EVENT_SIGNING_DOMAIN",
    "VerifiedFederationPeerEvent",
    "canonical_federation_peer_event_signing_payload",
    "federation_peer_event_digest",
    "verify_federation_peer_event",
]
