from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from sentientos.federation.peer_authentication import (
    PEER_EVENT_SCHEMA,
    canonical_federation_peer_event_signing_payload,
    federation_peer_event_digest,
)
from sentientos.federation.peer_health_bridge import (
    PEER_HEALTH_EVENT_SCHEMA,
    FederationPeerHealthBridgeError,
    accept_peer_health_event,
)
from sentientos.federation.peer_replay_owner import FederationPeerReplayOwner
from sentientos.federation.peer_trust_catalog import (
    CATALOG_SCHEMA,
    ReadOnlyFederationPeerTrustCatalog,
    catalog_digest_for,
)

pytestmark = pytest.mark.no_legacy_skip

ENDPOINT = "https://peer.example.test/health"
NOW = datetime(2026, 10, 23, 16, 0, 0, tzinfo=timezone.utc)


class Ed25519Verifier:
    def verify(self, *, algorithm: str, public_key: str, payload: bytes, signature: str) -> bool:
        assert algorithm == "ed25519"
        key = base64.urlsafe_b64decode(public_key + "=" * (-len(public_key) % 4))
        sig = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        try:
            Ed25519PublicKey.from_public_bytes(key).verify(sig, payload)
        except InvalidSignature:
            return False
        return True


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _provisioned_catalog():
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_text = base64.urlsafe_b64encode(public).decode("ascii").rstrip("=")
    key_id = "ed25519-sha256:" + hashlib.sha256(public).hexdigest()
    body = {
        "schema": CATALOG_SCHEMA,
        "catalog_version": 1,
        "entries": [{
            "peer_id": "peer-one",
            "signing_key_id": key_id,
            "endpoint": ENDPOINT,
            "algorithm": "ed25519",
            "public_key": public_text,
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_until": "2027-01-01T00:00:00Z",
            "revocation_status": "active",
        }],
    }
    value = {**body, "catalog_digest": catalog_digest_for(body)}
    catalog = ReadOnlyFederationPeerTrustCatalog.from_bytes(
        _canonical(value),
        expected_catalog_version=1,
        expected_catalog_digest=value["catalog_digest"],
    )
    return private, key_id, catalog


def _signed_health_event(private, key_id: str, *, sequence: int, issued_at: datetime, status: str):
    issued = issued_at.isoformat(timespec="seconds").replace("+00:00", "Z")
    event = {"schema": PEER_HEALTH_EVENT_SCHEMA, "status": status}
    event_digest = federation_peer_event_digest(event)
    signing_payload = canonical_federation_peer_event_signing_payload(
        peer_id="peer-one",
        signing_key_id=key_id,
        endpoint=ENDPOINT,
        sequence=sequence,
        issued_at=issued,
        event_digest=event_digest,
    )
    signature = base64.urlsafe_b64encode(private.sign(signing_payload)).decode("ascii").rstrip("=")
    envelope = {
        "schema": PEER_EVENT_SCHEMA,
        "peer_id": "peer-one",
        "signing_key_id": key_id,
        "endpoint": ENDPOINT,
        "sequence": sequence,
        "issued_at": issued,
        "event": event,
        "event_digest": event_digest,
        "signature": signature,
    }
    return _canonical(envelope)


@pytest.mark.parametrize("status", ["healthy", "unavailable"])
def test_authenticated_fresh_peer_assertion_is_durable_and_authority_denied(
    tmp_path, status
):
    private, key_id, catalog = _provisioned_catalog()
    owner = FederationPeerReplayOwner(tmp_path / "peer-one", peer_id="peer-one")

    observation = accept_peer_health_event(
        _signed_health_event(private, key_id, sequence=1, issued_at=NOW, status=status),
        owner=owner,
        catalog=catalog,
        signature_verifier=Ed25519Verifier(),
        now=NOW,
    )

    assert observation.peer_id == "peer-one"
    assert observation.peer_reported_status == status
    assert observation.sequence == 1
    assert observation.issued_at == "2026-10-23T16:00:00Z"
    assert observation.source == "operator_provisioned_authenticated_peer_assertion"
    assert observation.freshness_state == "within_bound"
    assert owner.last_accepted_sequence == 1
    assert observation.claim_truth_established is False
    assert observation.local_health_publication_permitted is False
    assert observation.work_admission_permitted is False
    assert observation.planning_permitted is False
    assert observation.execution_permitted is False
    assert observation.decision_power is False


def test_stale_peer_health_event_is_rejected_without_consuming_sequence(tmp_path):
    private, key_id, catalog = _provisioned_catalog()
    owner = FederationPeerReplayOwner(tmp_path / "peer-one", peer_id="peer-one")
    raw = _signed_health_event(
        private, key_id, sequence=1, issued_at=NOW - timedelta(seconds=301), status="healthy"
    )

    with pytest.raises(FederationPeerHealthBridgeError) as caught:
        accept_peer_health_event(
            raw, owner=owner, catalog=catalog,
            signature_verifier=Ed25519Verifier(), now=NOW,
        )

    assert caught.value.code == "peer_event_stale"
    assert owner.last_accepted_sequence == 0


def test_future_peer_health_event_is_rejected_without_consuming_sequence(tmp_path):
    private, key_id, catalog = _provisioned_catalog()
    owner = FederationPeerReplayOwner(tmp_path / "peer-one", peer_id="peer-one")
    raw = _signed_health_event(
        private, key_id, sequence=1, issued_at=NOW + timedelta(seconds=1), status="healthy"
    )

    with pytest.raises(FederationPeerHealthBridgeError) as caught:
        accept_peer_health_event(
            raw, owner=owner, catalog=catalog,
            signature_verifier=Ed25519Verifier(), now=NOW,
        )

    assert caught.value.code == "peer_event_from_future"
    assert owner.last_accepted_sequence == 0


@pytest.mark.parametrize(
    "event,expected_code",
    [
        ({"schema": "sentientos.other:v1", "status": "healthy"}, "peer_health_event_schema_invalid"),
        ({"schema": PEER_HEALTH_EVENT_SCHEMA, "status": "healthy", "nodes": 1},
         "peer_health_event_fields_invalid"),
        ({"schema": PEER_HEALTH_EVENT_SCHEMA, "status": "unknown-ish"},
         "peer_health_status_invalid"),
    ],
    ids=("unsupported_schema", "additional_fields", "unknown_status"),
)
def test_non_health_or_ambiguous_assertions_are_not_persisted(
    tmp_path, event, expected_code
):
    private, key_id, catalog = _provisioned_catalog()
    owner = FederationPeerReplayOwner(tmp_path / "peer-one", peer_id="peer-one")
    issued = NOW.isoformat(timespec="seconds").replace("+00:00", "Z")
    digest = federation_peer_event_digest(event)
    payload = canonical_federation_peer_event_signing_payload(
        peer_id="peer-one", signing_key_id=key_id, endpoint=ENDPOINT,
        sequence=1, issued_at=issued, event_digest=digest,
    )
    signature = base64.urlsafe_b64encode(private.sign(payload)).decode("ascii").rstrip("=")
    raw = _canonical({
        "schema": PEER_EVENT_SCHEMA,
        "peer_id": "peer-one",
        "signing_key_id": key_id,
        "endpoint": ENDPOINT,
        "sequence": 1,
        "issued_at": issued,
        "event": event,
        "event_digest": digest,
        "signature": signature,
    })

    with pytest.raises(FederationPeerHealthBridgeError) as caught:
        accept_peer_health_event(
            raw, owner=owner, catalog=catalog,
            signature_verifier=Ed25519Verifier(), now=NOW,
        )

    assert caught.value.code == expected_code
    assert owner.last_accepted_sequence == 0


def test_freshness_policy_and_clock_are_strictly_typed(tmp_path):
    private, key_id, catalog = _provisioned_catalog()
    owner = FederationPeerReplayOwner(tmp_path / "peer-one", peer_id="peer-one")
    raw = _signed_health_event(private, key_id, sequence=1, issued_at=NOW, status="degraded")

    for kwargs, expected in [
        ({"max_age_seconds": True}, "peer_health_freshness_policy_invalid"),
        ({"max_age_seconds": 0}, "peer_health_freshness_policy_invalid"),
        ({"max_age_seconds": 3_601}, "peer_health_freshness_policy_invalid"),
        ({"now": NOW.replace(tzinfo=None)}, "peer_health_clock_invalid"),
    ]:
        with pytest.raises(FederationPeerHealthBridgeError) as caught:
            accept_peer_health_event(
                raw, owner=owner, catalog=catalog,
                signature_verifier=Ed25519Verifier(),
                now=kwargs.get("now", NOW),
                max_age_seconds=kwargs.get("max_age_seconds", 300),
            )
        assert caught.value.code == expected
    assert owner.last_accepted_sequence == 0
