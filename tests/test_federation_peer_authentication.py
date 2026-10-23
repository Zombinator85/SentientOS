from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from sentientos.federation.peer_authentication import (
    PEER_EVENT_SCHEMA,
    FederationPeerEventVerificationError,
    canonical_federation_peer_event_signing_payload,
    federation_peer_event_digest,
    verify_federation_peer_event,
)
from sentientos.federation.peer_trust_catalog import (
    CATALOG_SCHEMA,
    FederationPeerTrustCatalogError,
    ReadOnlyFederationPeerTrustCatalog,
    catalog_digest_for,
)
from sentientos.federation.peer_replay_owner import (
    FederationPeerReplayOwner,
    FederationPeerReplayOwnerError,
)
from sentientos.federation import peer_replay_owner as peer_replay_owner_module

pytestmark = pytest.mark.no_legacy_skip

NOW = datetime(2026, 10, 23, 10, 0, 0, tzinfo=timezone.utc)
NOW_TEXT = "2026-10-23T10:00:00Z"
ENDPOINT = "https://peer.example.test/presence"


class Ed25519Verifier:
    def verify(self, *, algorithm: str, public_key: str, payload: bytes, signature: str) -> bool:
        assert algorithm == "ed25519"
        raw_public = base64.urlsafe_b64decode(public_key + "=" * (-len(public_key) % 4))
        raw_signature = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        try:
            Ed25519PublicKey.from_public_bytes(raw_public).verify(raw_signature, payload)
        except InvalidSignature:
            return False
        return True


class AcceptingVerifier:
    def verify(self, **_kwargs) -> bool:
        return True


class TruthyVerifier:
    def verify(self, **_kwargs):
        return 1


class RejectingVerifier:
    def verify(self, **_kwargs) -> bool:
        return False


def _make_catalog(*, revoked: str = "active", valid_from: str = "2026-01-01T00:00:00Z",
                  valid_until: str = "2027-01-01T00:00:00Z"):
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_text = base64.urlsafe_b64encode(public).decode("ascii").rstrip("=")
    key_id = "ed25519-sha256:" + hashlib.sha256(public).hexdigest()
    body = {
        "schema": CATALOG_SCHEMA,
        "catalog_version": 4,
        "entries": [{
            "peer_id": "peer-one",
            "signing_key_id": key_id,
            "endpoint": ENDPOINT,
            "algorithm": "ed25519",
            "public_key": public_text,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "revocation_status": revoked,
        }],
    }
    value = {**body, "catalog_digest": catalog_digest_for(body)}
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    catalog = ReadOnlyFederationPeerTrustCatalog.from_bytes(
        raw, expected_catalog_version=4, expected_catalog_digest=value["catalog_digest"])
    return private, public_text, key_id, value["catalog_digest"], raw, catalog, value


def _signed_event(private, key_id: str, *, peer_id: str = "peer-one",
                  endpoint: str = ENDPOINT, sequence: int = 1,
                  issued_at: str = NOW_TEXT, event=None, signature_from=None):
    payload_event = {"kind": "heartbeat", "metrics": {"load": 0.25}} if event is None else event
    digest = federation_peer_event_digest(payload_event)
    signing_payload = canonical_federation_peer_event_signing_payload(
        peer_id=peer_id, signing_key_id=key_id, endpoint=endpoint, sequence=sequence,
        issued_at=issued_at, event_digest=digest)
    signer = private if signature_from is None else signature_from
    signature = base64.urlsafe_b64encode(signer.sign(signing_payload)).decode("ascii").rstrip("=")
    envelope = {
        "schema": PEER_EVENT_SCHEMA,
        "peer_id": peer_id,
        "signing_key_id": key_id,
        "endpoint": endpoint,
        "sequence": sequence,
        "issued_at": issued_at,
        "event": payload_event,
        "event_digest": digest,
        "signature": signature,
    }
    raw = (json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    return raw, envelope


def _verify(raw, catalog, *, now=NOW, last=0, verifier=None):
    return verify_federation_peer_event(
        raw,
        catalog=catalog,
        signature_verifier=verifier or Ed25519Verifier(),
        now=now,
        last_accepted_sequence=last,
    )


def test_catalog_is_operator_pinned_lookup_only_and_exact_tuple_bound():
    _, public, key_id, digest, _, catalog, _ = _make_catalog()
    entry = catalog.lookup(peer_id="peer-one", signing_key_id=key_id, endpoint=ENDPOINT)
    assert entry is not None
    assert entry.public_key == public
    assert entry.revocation_status == "active"
    assert catalog.catalog_digest == digest
    assert catalog.lookup(peer_id="peer-two", signing_key_id=key_id, endpoint=ENDPOINT) is None
    assert catalog.lookup(peer_id="peer-one", signing_key_id=key_id, endpoint=ENDPOINT + "/stream") is None
    assert not hasattr(catalog, "enroll")
    assert not hasattr(catalog, "revoke")
    with pytest.raises(TypeError, match="pinned canonical bytes"):
        ReadOnlyFederationPeerTrustCatalog(4, digest, {})


def test_catalog_load_uses_explicit_file_and_digest_pin(tmp_path):
    _, _, _, digest, raw, _, _ = _make_catalog()
    path = tmp_path / "peer-trust.json"
    path.write_bytes(raw)
    catalog = ReadOnlyFederationPeerTrustCatalog.load(
        path, expected_catalog_version=4, expected_catalog_digest=digest)
    assert catalog.catalog_digest == digest


@pytest.mark.parametrize("kwargs,code", [
    ({"expected_catalog_version": True}, "expected_catalog_version_invalid"),
    ({"expected_catalog_version": 5}, "catalog_version_mismatch"),
    ({"expected_catalog_digest": "sha256:" + "0" * 64}, "catalog_digest_mismatch"),
    ({"expected_catalog_digest": "not-a-digest"}, "expected_catalog_digest_invalid"),
])
def test_catalog_rejects_version_and_digest_mismatch(kwargs, code):
    _, _, _, digest, raw, _, _ = _make_catalog()
    args = {"expected_catalog_version": 4, "expected_catalog_digest": digest}
    args.update(kwargs)
    with pytest.raises(FederationPeerTrustCatalogError, match=code):
        ReadOnlyFederationPeerTrustCatalog.from_bytes(raw, **args)


def test_catalog_rejects_duplicate_json_keys_noncanonical_bytes_and_oversize():
    _, _, _, digest, raw, _, _ = _make_catalog()
    with pytest.raises(FederationPeerTrustCatalogError, match="catalog_json_duplicate_key"):
        ReadOnlyFederationPeerTrustCatalog.from_bytes(
            b'{"schema":"a","schema":"b"}',
            expected_catalog_version=4, expected_catalog_digest=digest)
    with pytest.raises(FederationPeerTrustCatalogError, match="catalog_not_canonical"):
        ReadOnlyFederationPeerTrustCatalog.from_bytes(
            raw + b" ",
            expected_catalog_version=4, expected_catalog_digest=digest)
    with pytest.raises(FederationPeerTrustCatalogError, match="catalog_size_invalid"):
        ReadOnlyFederationPeerTrustCatalog.from_bytes(
            b"x" * 1_048_577,
            expected_catalog_version=4, expected_catalog_digest=digest)


@pytest.mark.parametrize("change,code", [
    (lambda row: row.update(peer_id="../peer"), "catalog_peer_id_invalid"),
    (lambda row: row.update(endpoint="https://user:secret@peer.example.test/presence"),
     "catalog_endpoint_invalid"),
    (lambda row: row.update(endpoint="https://peer.example.test/presence?token=x"),
     "catalog_endpoint_invalid"),
    (lambda row: row.update(endpoint="https://peer.example.test:0/presence"),
     "catalog_endpoint_invalid"),
    (lambda row: row.update(revocation_status=[]), "catalog_revocation_status_invalid"),
    (lambda row: row.update(valid_until="2025-01-01T00:00:00Z"), "catalog_validity_invalid"),
    (lambda row: row.update(algorithm="rsa"), "catalog_algorithm_invalid"),
    (lambda row: row.update(public_key="***"), "catalog_public_key_invalid"),
    (lambda row: row.update(signing_key_id="ed25519-sha256:" + "0" * 64),
     "catalog_key_id_mismatch"),
])
def test_catalog_rejects_invalid_trust_fields(change, code):
    _, _, _, _, _, _, value = _make_catalog()
    mutated = json.loads(json.dumps(value))
    change(mutated["entries"][0])
    body = dict(mutated)
    body.pop("catalog_digest")
    mutated["catalog_digest"] = catalog_digest_for(body)
    raw = (json.dumps(mutated, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    with pytest.raises(FederationPeerTrustCatalogError, match=code):
        ReadOnlyFederationPeerTrustCatalog.from_bytes(
            raw, expected_catalog_version=4, expected_catalog_digest=mutated["catalog_digest"])


def test_catalog_rejects_duplicate_peer_key_endpoint_tuple():
    _, _, _, _, _, _, value = _make_catalog()
    value["entries"].append(dict(value["entries"][0]))
    body = dict(value)
    body.pop("catalog_digest")
    value["catalog_digest"] = catalog_digest_for(body)
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with pytest.raises(FederationPeerTrustCatalogError, match="catalog_trust_tuple_duplicate"):
        ReadOnlyFederationPeerTrustCatalog.from_bytes(
            raw, expected_catalog_version=4, expected_catalog_digest=value["catalog_digest"])


def test_signed_event_verifies_and_returns_deeply_immutable_provenance():
    private, _, key_id, digest, _, catalog, _ = _make_catalog()
    raw, _ = _signed_event(private, key_id)
    verified = _verify(raw, catalog)
    assert verified.peer_id == "peer-one"
    assert verified.sequence == 1
    assert verified.catalog_digest == digest
    assert verified.event["kind"] == "heartbeat"
    with pytest.raises(TypeError):
        verified.event["kind"] = "changed"
    with pytest.raises(TypeError):
        verified.event["metrics"]["load"] = 0.75
    assert not hasattr(verified, "accept")
    assert not hasattr(verified, "persist")


def test_signed_event_requires_exact_next_replay_sequence():
    private, _, key_id, _, _, catalog, _ = _make_catalog()
    raw, _ = _signed_event(private, key_id, sequence=3)
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_sequence_not_next"):
        _verify(raw, catalog, last=1)


def test_signed_event_rejects_peer_or_endpoint_substitution():
    private, _, key_id, _, _, catalog, _ = _make_catalog()
    for raw, _ in (
        _signed_event(private, key_id, peer_id="peer-two"),
        _signed_event(private, key_id, endpoint=ENDPOINT + "/stream"),
    ):
        with pytest.raises(FederationPeerEventVerificationError, match="peer_event_trust_not_found"):
            _verify(raw, catalog)


def test_signed_event_rejects_mutated_event_digest_and_bad_signature():
    private, _, key_id, _, _, catalog, _ = _make_catalog()
    raw, envelope = _signed_event(private, key_id)
    changed = dict(envelope)
    changed["event"] = {"kind": "forged"}
    changed_raw = (json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_digest_mismatch"):
        _verify(changed_raw, catalog)
    forged_private = Ed25519PrivateKey.from_private_bytes(bytes(reversed(range(32))))
    bad_signature, _ = _signed_event(private, key_id, signature_from=forged_private)
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_signature_invalid"):
        _verify(bad_signature, catalog)
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_signature_invalid"):
        _verify(raw, catalog, verifier=RejectingVerifier())


def test_signed_event_rejects_the_exact_key_expiry_instant():
    private, _, key_id, _, _, catalog, _ = _make_catalog()
    issued_at = "2027-01-01T00:00:00Z"
    raw, _ = _signed_event(private, key_id, issued_at=issued_at)
    boundary = datetime(2027, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_key_outside_validity"):
        _verify(raw, catalog, now=boundary)


def test_signed_event_rejects_revoked_key_and_currently_expired_key():
    private, _, key_id, _, _, _, _ = _make_catalog()
    revoked = _make_catalog(revoked="revoked")[5]
    raw, _ = _signed_event(private, key_id)
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_key_revoked"):
        _verify(raw, revoked)
    expired = _make_catalog(valid_until="2026-10-22T00:00:00Z")[5]
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_key_outside_validity"):
        _verify(raw, expired)


@pytest.mark.parametrize("issued_at,now,code", [
    ("2026-10-23T09:54:59Z", NOW, "peer_event_stale"),
    ("2026-10-23T10:00:31Z", NOW, "peer_event_from_future"),
    (NOW_TEXT, datetime.max.replace(tzinfo=timezone.utc), "peer_event_stale"),
    ("2026-10-23T10:00:00+00:00", NOW, "peer_event_timestamp_invalid"),
    ("2026-10-23T10:00:00.000Z", NOW, "peer_event_timestamp_invalid"),
])
def test_signed_event_enforces_canonical_freshness_window(issued_at, now, code):
    private, _, key_id, _, _, catalog, _ = _make_catalog()
    raw, _ = _signed_event(private, key_id, issued_at=issued_at)
    with pytest.raises(FederationPeerEventVerificationError, match=code):
        _verify(raw, catalog, now=now)


def test_signed_event_rejects_noncanonical_duplicate_and_extra_fields():
    private, _, key_id, _, _, catalog, _ = _make_catalog()
    raw, envelope = _signed_event(private, key_id)
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_not_canonical"):
        _verify(raw.rstrip(b"\n"), catalog)
    duplicate = raw[:-1].replace(b'"schema":', b'"schema":"sentientos.federation.peer_event:v1","schema":', 1) + b"\n"
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_json_duplicate_key"):
        _verify(duplicate, catalog)
    extra = dict(envelope)
    extra["authority"] = "execute"
    extra_raw = (json.dumps(extra, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_fields_not_exact"):
        _verify(extra_raw, catalog)


def test_signed_event_rejects_bad_sequence_types_and_json_constants():
    private, _, key_id, _, _, catalog, _ = _make_catalog()
    raw, envelope = _signed_event(private, key_id)
    bad_sequence = dict(envelope)
    bad_sequence["sequence"] = True
    encoded = (json.dumps(bad_sequence, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_claim_invalid"):
        _verify(encoded, catalog)
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_json_nonfinite_number"):
        _verify(b'{"x":NaN}', catalog)


def test_verifier_requires_real_true_boolean_and_bounded_policy_inputs():
    private, _, key_id, _, _, catalog, _ = _make_catalog()
    raw, _ = _signed_event(private, key_id)
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_signature_invalid"):
        _verify(raw, catalog, verifier=TruthyVerifier())
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_replay_state_invalid"):
        _verify(raw, catalog, last=True)
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_freshness_policy_invalid"):
        verify_federation_peer_event(
            raw, catalog=catalog, signature_verifier=AcceptingVerifier(),
            now=NOW, last_accepted_sequence=0, max_age_seconds=True)
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_clock_invalid"):
        verify_federation_peer_event(
            raw, catalog=catalog, signature_verifier=AcceptingVerifier(),
            now=datetime(2026, 10, 23), last_accepted_sequence=0)


def test_signed_event_size_is_bounded():
    _, _, _, _, _, catalog, _ = _make_catalog()
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_size_invalid"):
        _verify(b"x" * 65_537, catalog)

from sentientos.federation import peer_replay_owner as peer_replay_owner_module
from sentientos.federation.peer_replay_owner import (
    FederationPeerReplayOwner,
    FederationPeerReplayOwnerError,
)


def test_replay_owner_derives_sequence_recovers_and_preserves_outcomes(tmp_path):
    private, _, key_id, _, _, catalog, _ = _make_catalog()
    root = tmp_path / "peer-one"
    owner = FederationPeerReplayOwner(root, peer_id="peer-one")
    adverse_raw, _ = _signed_event(
        private, key_id, sequence=1,
        event={"kind": "trial_outcome", "outcome": "adverse", "reason": "timeout"},
    )
    first = owner.accept(
        adverse_raw, catalog=catalog, signature_verifier=Ed25519Verifier(), now=NOW,
    )
    assert first.sequence == 1
    assert first.created is True
    assert first.verified_event.event["outcome"] == "adverse"
    stored_first = json.loads((root / "event-00000000000000000001.json").read_text())
    assert stored_first["signed_envelope"] == adverse_raw.decode("utf-8")
    recovered = FederationPeerReplayOwner(root, peer_id="peer-one")
    assert recovered.last_accepted_sequence == 1

    positive_raw, _ = _signed_event(
        private, key_id, sequence=2,
        event={"kind": "trial_outcome", "outcome": "positive", "reason": "completed"},
    )
    second = recovered.accept(
        positive_raw, catalog=catalog, signature_verifier=Ed25519Verifier(), now=NOW,
    )
    assert second.sequence == 2
    assert second.verified_event.event["outcome"] == "positive"

    expanded_raw, _ = _signed_event(
        private, key_id, sequence=3,
        event={"kind": "bounded_payload", "value": '"' * 30_000},
    )
    assert len(expanded_raw) < 65_536
    third = recovered.accept(
        expanded_raw, catalog=catalog, signature_verifier=Ed25519Verifier(), now=NOW,
    )
    assert third.sequence == 3
    assert (root / "event-00000000000000000003.json").stat().st_size > 70_000
    assert FederationPeerReplayOwner(root, peer_id="peer-one").last_accepted_sequence == 3


def test_replay_owner_rejects_gap_replay_and_tampered_history(tmp_path):
    private, _, key_id, _, _, catalog, _ = _make_catalog()
    root = tmp_path / "peer-one"
    owner = FederationPeerReplayOwner(root, peer_id="peer-one")
    gap_raw, _ = _signed_event(private, key_id, sequence=2)
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_sequence_not_next"):
        owner.accept(gap_raw, catalog=catalog, signature_verifier=Ed25519Verifier(), now=NOW)
    assert owner.last_accepted_sequence == 0

    first_raw, _ = _signed_event(private, key_id, sequence=1)
    owner.accept(first_raw, catalog=catalog, signature_verifier=Ed25519Verifier(), now=NOW)
    with pytest.raises(FederationPeerEventVerificationError, match="peer_event_sequence_not_next"):
        owner.accept(first_raw, catalog=catalog, signature_verifier=Ed25519Verifier(), now=NOW)
    record_path = root / "event-00000000000000000001.json"
    original = record_path.read_bytes()
    record_path.write_bytes(b"{}\n")
    with pytest.raises(FederationPeerReplayOwnerError, match="replay_record_fields_invalid"):
        _ = owner.last_accepted_sequence

    record_path.write_bytes(original)
    second_raw, _ = _signed_event(private, key_id, sequence=2)
    owner.accept(second_raw, catalog=catalog, signature_verifier=Ed25519Verifier(), now=NOW)
    rewritten = json.loads(original)
    rewritten["recorded_at"] = "2026-10-23T10:00:01Z"
    rewritten["record_digest"] = peer_replay_owner_module._record_digest({
        key: value for key, value in rewritten.items() if key != "record_digest"
    })
    record_path.write_bytes(peer_replay_owner_module._canonical(rewritten))
    with pytest.raises(FederationPeerReplayOwnerError, match="replay_record_identity_invalid"):
        _ = owner.last_accepted_sequence


def test_replay_owner_bounds_history_and_fails_closed_without_posix_custody(tmp_path, monkeypatch):
    private, _, key_id, _, _, catalog, _ = _make_catalog()
    root = tmp_path / "peer-one"
    bounded = FederationPeerReplayOwner(root, peer_id="peer-one", max_history_bytes=140_000)
    assert bounded.max_history_bytes == 140_000
    for invalid_limit in (139_999, 67_108_865, True):
        with pytest.raises(FederationPeerReplayOwnerError, match="replay_owner_byte_limit_invalid"):
            FederationPeerReplayOwner(root, peer_id="peer-one", max_history_bytes=invalid_limit)

    byte_root = tmp_path / "byte-limited"
    byte_owner = FederationPeerReplayOwner(
        byte_root, peer_id="peer-one", max_history_bytes=140_000,
    )
    large_outcome = {"kind": "bounded_payload", "value": '"' * 30_000}
    large_first, _ = _signed_event(private, key_id, sequence=1, event=large_outcome)
    large_second, _ = _signed_event(private, key_id, sequence=2, event=large_outcome)
    assert len(large_first) < 65_536 and len(large_second) < 65_536
    byte_owner.accept(
        large_first, catalog=catalog, signature_verifier=Ed25519Verifier(), now=NOW,
    )
    with pytest.raises(FederationPeerReplayOwnerError, match="replay_owner_byte_limit_exceeded"):
        byte_owner.accept(
            large_second, catalog=catalog, signature_verifier=Ed25519Verifier(), now=NOW,
        )
    assert byte_owner.last_accepted_sequence == 1
    owner = FederationPeerReplayOwner(root, peer_id="peer-one", max_records=1)
    first_raw, _ = _signed_event(private, key_id, sequence=1)
    owner.accept(first_raw, catalog=catalog, signature_verifier=Ed25519Verifier(), now=NOW)
    second_raw, _ = _signed_event(private, key_id, sequence=2)
    with pytest.raises(FederationPeerReplayOwnerError, match="replay_owner_record_limit_exceeded"):
        owner.accept(second_raw, catalog=catalog, signature_verifier=Ed25519Verifier(), now=NOW)

    unsupported_root = tmp_path / "unsupported"
    unsupported = FederationPeerReplayOwner(unsupported_root, peer_id="peer-one")
    def unsupported_directory(*_args, **_kwargs):
        raise peer_replay_owner_module.PrivateFileCustodyError("directory_custody_unsupported")
    monkeypatch.setattr(peer_replay_owner_module, "open_private_directory", unsupported_directory)
    with pytest.raises(FederationPeerReplayOwnerError, match="replay_owner_custody_unavailable"):
        unsupported.accept(first_raw, catalog=catalog, signature_verifier=Ed25519Verifier(), now=NOW)
    assert not unsupported_root.exists()



from sentientos.federation.peer_semantic_acceptance import (
    CLAIM_EVIDENCE_SCHEMA,
    TRIAL_OUTCOME_SCHEMA,
    FederationPeerSemanticAcceptanceError,
    FederationPeerSemanticAcceptancePolicy,
    accept_peer_event_for_local_review,
    semantic_policy_digest_for,
)


def _local_semantic_policy(peer_rules):
    body = {
        "schema": "sentientos.federation.peer_semantic_policy:v1",
        "policy_version": 1,
        "peers": peer_rules,
    }
    value = {**body, "policy_digest": semantic_policy_digest_for(body)}
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    policy = FederationPeerSemanticAcceptancePolicy.from_bytes(
        raw, expected_policy_version=1, expected_policy_digest=value["policy_digest"])
    return raw, value["policy_digest"], policy


def _semantic_replay(tmp_path, event):
    private, _, key_id, _, _, catalog, _ = _make_catalog()
    raw, _ = _signed_event(private, key_id, event=event)
    owner = FederationPeerReplayOwner(tmp_path / "peer-one", peer_id="peer-one")
    return owner.accept(
        raw, catalog=catalog, signature_verifier=Ed25519Verifier(), now=NOW,
    )


def test_peer_claim_semantics_require_local_policy_and_only_enable_review(tmp_path):
    _, policy_digest, policy = _local_semantic_policy([{
        "peer_id": "peer-one",
        "accepted_event_schemas": [CLAIM_EVIDENCE_SCHEMA],
    }])
    replay = _semantic_replay(tmp_path, {
        "schema": CLAIM_EVIDENCE_SCHEMA,
        "claim": "The bounded trial preserved adverse outcomes.",
        "epistemic_status": "uncertain",
        "evidence_refs": ["trial:record-4"],
    })

    receipt = accept_peer_event_for_local_review(replay, policy=policy)

    assert receipt.decision == "accepted_for_local_review"
    assert receipt.semantic_kind == "claim_evidence"
    assert receipt.submitted_claim == "The bounded trial preserved adverse outcomes."
    assert receipt.submitted_epistemic_status == "uncertain"
    assert receipt.remote_evidence_refs == ("trial:record-4",)
    assert receipt.remote_evidence_resolved_locally is False
    assert receipt.claim_truth_established is False
    assert receipt.canonical_evidence_admitted is False
    assert receipt.health_publication_permitted is False
    assert receipt.work_admission_permitted is False
    assert receipt.planning_permitted is False
    assert receipt.execution_permitted is False
    assert receipt.decision_power == "none"
    assert receipt.policy_digest == policy_digest
    assert receipt.replay_record_digest == replay.record_digest
    assert receipt.event_digest == replay.verified_event.event_digest
    with pytest.raises(TypeError, match="locally pinned canonical bytes"):
        FederationPeerSemanticAcceptancePolicy(1, policy_digest, {})


@pytest.mark.parametrize("outcome", ["positive", "adverse", "mixed", "inconclusive"])
def test_peer_trial_outcomes_preserve_positive_and_adverse_labels(tmp_path, outcome):
    _, _, policy = _local_semantic_policy([{
        "peer_id": "peer-one",
        "accepted_event_schemas": [TRIAL_OUTCOME_SCHEMA],
    }])
    replay = _semantic_replay(tmp_path, {
        "schema": TRIAL_OUTCOME_SCHEMA,
        "experiment_id": "experiment-17",
        "outcome": outcome,
        "summary": "Outcome submitted by the authenticated peer.",
        "evidence_refs": ["trial:run-17"],
    })

    receipt = accept_peer_event_for_local_review(replay, policy=policy)

    assert receipt.decision == "accepted_for_local_review"
    assert receipt.semantic_kind == "trial_outcome"
    assert receipt.experiment_id == "experiment-17"
    assert receipt.submitted_outcome == outcome
    assert receipt.submitted_summary == "Outcome submitted by the authenticated peer."
    assert receipt.remote_evidence_refs == ("trial:run-17",)
    assert receipt.remote_evidence_resolved_locally is False
    assert receipt.canonical_evidence_admitted is False
    assert receipt.execution_permitted is False


def test_peer_event_schema_and_peer_must_be_explicitly_permitted(tmp_path):
    _, _, policy = _local_semantic_policy([])
    replay = _semantic_replay(tmp_path, {
        "schema": CLAIM_EVIDENCE_SCHEMA,
        "claim": "A peer claim.",
        "epistemic_status": "unknown",
        "evidence_refs": [],
    })

    receipt = accept_peer_event_for_local_review(replay, policy=policy)

    assert receipt.decision == "rejected"
    assert receipt.reason_code == "semantic_peer_or_schema_not_permitted"
    assert receipt.semantic_kind is None
    assert receipt.submitted_claim is None


@pytest.mark.parametrize("event", [
    {
        "schema": CLAIM_EVIDENCE_SCHEMA,
        "claim": "A peer claim.",
        "epistemic_status": "supported",
        "evidence_refs": ["../../outside"],
    },
    {
        "schema": CLAIM_EVIDENCE_SCHEMA,
        "claim": "A peer claim.",
        "epistemic_status": "supported",
        "evidence_refs": [],
        "execute": True,
    },
])
def test_peer_claim_shape_rejects_unresolved_paths_and_extra_authority_fields(tmp_path, event):
    _, _, policy = _local_semantic_policy([{
        "peer_id": "peer-one",
        "accepted_event_schemas": [CLAIM_EVIDENCE_SCHEMA],
    }])
    replay = _semantic_replay(tmp_path, event)

    receipt = accept_peer_event_for_local_review(replay, policy=policy)

    assert receipt.decision == "rejected"
    assert receipt.semantic_kind is None
    assert receipt.canonical_evidence_admitted is False
    assert receipt.execution_permitted is False


def test_local_semantic_policy_requires_exact_canonical_pinned_bytes():
    raw, digest, _ = _local_semantic_policy([{
        "peer_id": "peer-one",
        "accepted_event_schemas": [CLAIM_EVIDENCE_SCHEMA],
    }])
    with pytest.raises(FederationPeerSemanticAcceptanceError, match="semantic_policy_digest_mismatch"):
        FederationPeerSemanticAcceptancePolicy.from_bytes(
            raw, expected_policy_version=1, expected_policy_digest="sha256:" + "0" * 64,
        )
    with pytest.raises(FederationPeerSemanticAcceptanceError, match="semantic_policy_not_canonical"):
        FederationPeerSemanticAcceptancePolicy.from_bytes(
            raw + b" ", expected_policy_version=1, expected_policy_digest=digest,
        )
    with pytest.raises(FederationPeerSemanticAcceptanceError, match="semantic_policy_schemas_invalid"):
        _local_semantic_policy([{
            "peer_id": "peer-one",
            "accepted_event_schemas": ["sentientos.federation.remote_command:v1"],
        }])
