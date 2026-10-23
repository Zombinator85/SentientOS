"""Bound the ingress and projection of authenticated peer Health assertions.

The caller supplies one signed wire envelope from an operator-provisioned
transport. Trust, signature, freshness, sequence, and immutable local replay
custody are verified before the peer assertion is projected. The output is
explicitly a peer-reported claim; this module does not publish the local
Federation Health document or grant admission, planning, execution, or decision
authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Mapping, cast

from .peer_authentication import (
    FederationPeerEventVerificationError,
    FederationPeerSignatureVerifier,
    VerifiedFederationPeerEvent,
    federation_peer_event_digest,
    verify_federation_peer_event,
)
from .peer_replay_owner import (
    FederationPeerReplayOwner,
    FederationPeerReplayOwnerError,
)
from .peer_trust_catalog import (
    FederationPeerTrustCatalogError,
    ReadOnlyFederationPeerTrustCatalog,
)

PEER_HEALTH_EVENT_SCHEMA = "sentientos.federation.peer_health_observation:v1"
_MAX_PEER_HEALTH_AGE_SECONDS = 3_600
_PEER_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}\Z")
_KEY_ID = re.compile(r"ed25519-sha256:[0-9a-f]{64}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ALLOWED_STATUS = frozenset({"healthy", "degraded", "unavailable", "unknown"})
_EVENT_FIELDS = frozenset({"schema", "status"})


class FederationPeerHealthBridgeError(ValueError):
    """A bounded, fail-closed peer Health assertion ingress or projection error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class FederationPeerHealthObservation:
    """Fresh, authenticated peer-reported status with explicit authority denials."""

    peer_id: str
    signing_key_id: str
    endpoint: str
    sequence: int
    issued_at: str
    peer_reported_status: str
    event_digest: str
    replay_record_digest: str
    catalog_version: int
    catalog_digest: str
    max_age_seconds: int
    source: str = "operator_provisioned_authenticated_peer_assertion"
    freshness_state: str = "within_bound"
    claim_truth_established: bool = False
    local_health_publication_permitted: bool = False
    work_admission_permitted: bool = False
    planning_permitted: bool = False
    execution_permitted: bool = False
    decision_power: bool = False


def _utc_time(value: object) -> datetime:
    if (not isinstance(value, datetime) or value.tzinfo is None
            or value.utcoffset() != timedelta(0)):
        raise FederationPeerHealthBridgeError("peer_health_clock_invalid")
    return value


def _parse_issued_at(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise FederationPeerHealthBridgeError("peer_health_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FederationPeerHealthBridgeError("peer_health_timestamp_invalid") from exc
    if (parsed.utcoffset() != timezone.utc.utcoffset(parsed)
            or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value):
        raise FederationPeerHealthBridgeError("peer_health_timestamp_invalid")
    return parsed


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise FederationPeerHealthBridgeError("peer_health_event_content_invalid")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or type(value) in {str, int, float, bool}:
        return value
    raise FederationPeerHealthBridgeError("peer_health_event_content_invalid")


def _validate_event_shape(event: Mapping[str, object]) -> str:
    try:
        value = _json_value(event)
    except FederationPeerHealthBridgeError:
        raise
    if not isinstance(value, dict) or set(value) != _EVENT_FIELDS:
        raise FederationPeerHealthBridgeError("peer_health_event_fields_invalid")
    if value.get("schema") != PEER_HEALTH_EVENT_SCHEMA:
        raise FederationPeerHealthBridgeError("peer_health_event_schema_invalid")
    status = value.get("status")
    if not isinstance(status, str) or status not in _ALLOWED_STATUS:
        raise FederationPeerHealthBridgeError("peer_health_status_invalid")
    return status


def _project(
    replay: object,
    *,
    now: datetime,
    max_age_seconds: int,
) -> FederationPeerHealthObservation:
    from .peer_replay_owner import FederationPeerReplayAcceptance

    if not isinstance(replay, FederationPeerReplayAcceptance):
        raise FederationPeerHealthBridgeError("peer_health_replay_acceptance_required")
    event = replay.verified_event
    if not isinstance(event, VerifiedFederationPeerEvent):
        raise FederationPeerHealthBridgeError("peer_health_verified_event_required")
    if (type(replay.sequence) is not int or replay.sequence < 1
            or replay.sequence != event.sequence or replay.created is not True
            or not isinstance(replay.record_digest, str)
            or _DIGEST.fullmatch(replay.record_digest) is None
            or not isinstance(event.peer_id, str) or _PEER_ID.fullmatch(event.peer_id) is None
            or not isinstance(event.signing_key_id, str) or _KEY_ID.fullmatch(event.signing_key_id) is None
            or not isinstance(event.endpoint, str) or not event.endpoint
            or len(event.endpoint) > 2_048
            or type(event.catalog_version) is not int or event.catalog_version < 1
            or not isinstance(event.catalog_digest, str) or _DIGEST.fullmatch(event.catalog_digest) is None
            or not isinstance(event.event_digest, str) or _DIGEST.fullmatch(event.event_digest) is None
            or not isinstance(event.event, Mapping)):
        raise FederationPeerHealthBridgeError("peer_health_replay_provenance_invalid")
    issued_at = _parse_issued_at(event.issued_at)
    age_seconds = (now - issued_at).total_seconds()
    if age_seconds < 0:
        raise FederationPeerHealthBridgeError("peer_health_event_from_future")
    if age_seconds > max_age_seconds:
        raise FederationPeerHealthBridgeError("peer_health_event_stale")
    status = _validate_event_shape(event.event)
    try:
        event_value = cast(Mapping[str, object], _json_value(event.event))
        computed_digest = federation_peer_event_digest(event_value)
    except (TypeError, ValueError, RecursionError) as exc:
        raise FederationPeerHealthBridgeError("peer_health_event_content_invalid") from exc
    if computed_digest != event.event_digest:
        raise FederationPeerHealthBridgeError("peer_health_event_digest_mismatch")
    return FederationPeerHealthObservation(
        peer_id=event.peer_id,
        signing_key_id=event.signing_key_id,
        endpoint=event.endpoint,
        sequence=event.sequence,
        issued_at=event.issued_at,
        peer_reported_status=status,
        event_digest=event.event_digest,
        replay_record_digest=replay.record_digest,
        catalog_version=event.catalog_version,
        catalog_digest=event.catalog_digest,
        max_age_seconds=max_age_seconds,
    )


def accept_peer_health_event(
    raw: bytes,
    *,
    owner: FederationPeerReplayOwner,
    catalog: ReadOnlyFederationPeerTrustCatalog,
    signature_verifier: FederationPeerSignatureVerifier,
    now: datetime,
    max_age_seconds: int = 300,
) -> FederationPeerHealthObservation:
    """Authenticate, freshness-bound, durably sequence, then project one peer status.

    The preflight verifies the supported Health event shape before persistence.
    The replay owner then repeats signature/sequence/freshness verification under
    its own acceptance path before immutable publication. A race with another
    event therefore fails closed at durable acceptance.
    """
    clock = _utc_time(now)
    if (type(max_age_seconds) is not int
            or not 1 <= max_age_seconds <= _MAX_PEER_HEALTH_AGE_SECONDS):
        raise FederationPeerHealthBridgeError("peer_health_freshness_policy_invalid")
    if not isinstance(owner, FederationPeerReplayOwner):
        raise FederationPeerHealthBridgeError("peer_health_replay_owner_required")
    if not isinstance(catalog, ReadOnlyFederationPeerTrustCatalog):
        raise FederationPeerHealthBridgeError("peer_health_trust_catalog_required")
    if not callable(getattr(signature_verifier, "verify", None)):
        raise FederationPeerHealthBridgeError("peer_health_signature_verifier_required")
    try:
        prior_sequence = owner.last_accepted_sequence
        verified = verify_federation_peer_event(
            raw,
            catalog=catalog,
            signature_verifier=signature_verifier,
            now=clock,
            last_accepted_sequence=prior_sequence,
            max_age_seconds=max_age_seconds,
            future_skew_seconds=0,
        )
    except FederationPeerEventVerificationError as exc:
        raise FederationPeerHealthBridgeError(exc.args[0]) from exc
    except FederationPeerReplayOwnerError as exc:
        raise FederationPeerHealthBridgeError(exc.code) from exc
    _validate_event_shape(verified.event)
    try:
        replay = owner.accept(
            raw,
            catalog=catalog,
            signature_verifier=signature_verifier,
            now=clock,
            max_age_seconds=max_age_seconds,
            future_skew_seconds=0,
        )
    except FederationPeerEventVerificationError as exc:
        raise FederationPeerHealthBridgeError(exc.args[0]) from exc
    except FederationPeerReplayOwnerError as exc:
        raise FederationPeerHealthBridgeError(exc.code) from exc
    except FederationPeerTrustCatalogError as exc:
        raise FederationPeerHealthBridgeError("peer_health_trust_catalog_invalid") from exc
    return _project(replay, now=clock, max_age_seconds=max_age_seconds)


__all__ = [
    "FederationPeerHealthBridgeError",
    "FederationPeerHealthObservation",
    "PEER_HEALTH_EVENT_SCHEMA",
    "accept_peer_health_event",
]
