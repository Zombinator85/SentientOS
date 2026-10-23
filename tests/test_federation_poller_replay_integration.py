import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sentientos.federation.peer_authentication import (
    PEER_EVENT_SCHEMA,
    canonical_federation_peer_event_signing_payload,
    federation_peer_event_digest,
)
from sentientos.federation.peer_health_bridge import PEER_HEALTH_EVENT_SCHEMA
from sentientos.federation.peer_replay_owner import FederationPeerReplayOwner
from sentientos.federation.peer_trust_catalog import (
    CATALOG_SCHEMA,
    ReadOnlyFederationPeerTrustCatalog,
    catalog_digest_for,
)
from sentientos.federation.config import FederationConfig, PeerConfig
from sentientos.federation.identity import NodeId
from sentientos.federation.poller import FederationPoller, PeerHealthRecoverySource
from sentientos.federation.summary import (
    CathedralState,
    ConfigState,
    ExperimentState,
    FederationSummary,
)

pytestmark = pytest.mark.no_legacy_skip


class _RuntimeStub:
    def get_persona_snapshot(self):  # pragma: no cover - simple data
        return {"mood": "calm"}

    def get_dream_snapshot(self):  # pragma: no cover - simple data
        return {"last_focus": "alignment"}


def _summary(digest: str, total: int) -> FederationSummary:
    return FederationSummary(
        node_name="node",
        fingerprint="fp-node",
        ts=datetime.now(timezone.utc),
        cathedral=CathedralState(
            last_applied_id="amend-1",
            last_applied_digest=digest,
            ledger_height=2,
            rollback_count=0,
        ),
        experiments=ExperimentState(total=total, chains=0, dsl_version="1.0"),
        config=ConfigState(config_digest=f"cfg-{digest}"),
        meta={"runtime_root": "/tmp"},
    )


def test_poller_records_replay_delta(tmp_path, monkeypatch):
    events = []

    local_summary = _summary("dg-local", 2)
    peer_summary = _summary("dg-peer", 3)

    from sentientos.federation import poller as poller_module

    monkeypatch.setattr(poller_module, "publish_event", lambda event: events.append(event))
    monkeypatch.setattr(poller_module, "build_local_summary", lambda runtime: local_summary)
    monkeypatch.setattr(poller_module, "read_peer_summary", lambda path: peer_summary)

    state_file = tmp_path / "federation" / "state" / "local.json"
    peer_state = tmp_path / "federation" / "state" / "peer.json"
    peer_state.parent.mkdir(parents=True, exist_ok=True)
    peer_state.write_text("{}", encoding="utf-8")

    config = FederationConfig(
        enabled=True,
        node_id=NodeId(name="local", fingerprint="fp-local"),
        state_file=str(state_file),
        peers=[PeerConfig(node_name="peer", state_file=str(peer_state))],
        poll_interval_seconds=1,
        max_drift_peers=0,
        max_incompatible_peers=0,
        max_missing_peers=0,
    )

    poller = FederationPoller(config, runtime=_RuntimeStub(), log_cb=lambda *_: None)
    poller._poll_once()

    replay_state = poller.get_replay_state()
    assert "peer" in replay_state
    assert replay_state["peer"].severity in {"medium", "high"}

    replay_file = tmp_path / "federation" / "replay" / "peer.json"
    assert replay_file.exists()

    assert any(event.get("kind") == "federation_replay" for event in events)


def _peer_health_source(
    tmp_path: Path,
    *,
    status: str,
    now: datetime,
    accept_event: bool = True,
    owner_name: str = "authenticated-peer-one",
    history_statuses: tuple[str, ...] | None = None,
):
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_text = base64.urlsafe_b64encode(public).decode("ascii").rstrip("=")
    key_id = "ed25519-sha256:" + hashlib.sha256(public).hexdigest()
    endpoint = "https://peer.example.test/health"
    catalog_body = {
        "schema": CATALOG_SCHEMA,
        "catalog_version": 1,
        "entries": [{
            "peer_id": "peer-one",
            "signing_key_id": key_id,
            "endpoint": endpoint,
            "algorithm": "ed25519",
            "public_key": public_text,
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_until": "2027-01-01T00:00:00Z",
            "revocation_status": "active",
        }],
    }
    catalog_value = {
        **catalog_body,
        "catalog_digest": catalog_digest_for(catalog_body),
    }
    catalog = ReadOnlyFederationPeerTrustCatalog.from_bytes(
        (json.dumps(catalog_value, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        expected_catalog_version=1,
        expected_catalog_digest=catalog_value["catalog_digest"],
    )
    class Verifier:
        def verify(self, *, algorithm: str, public_key: str, payload: bytes, signature: str) -> bool:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            if algorithm != "ed25519":
                return False
            key = base64.urlsafe_b64decode(public_key + "=" * (-len(public_key) % 4))
            sig = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
            try:
                Ed25519PublicKey.from_public_bytes(key).verify(sig, payload)
            except InvalidSignature:
                return False
            return True

    owner = FederationPeerReplayOwner(tmp_path / owner_name, peer_id="peer-one")
    observed_history = history_statuses or (status,)
    if accept_event:
        for sequence, historical_status in enumerate(observed_history, start=1):
            issued = (
                now - (len(observed_history) - sequence) * timedelta(seconds=1)
            ).isoformat(timespec="seconds").replace("+00:00", "Z")
            event = {"schema": PEER_HEALTH_EVENT_SCHEMA, "status": historical_status}
            event_digest = federation_peer_event_digest(event)
            payload = canonical_federation_peer_event_signing_payload(
                peer_id="peer-one",
                signing_key_id=key_id,
                endpoint=endpoint,
                sequence=sequence,
                issued_at=issued,
                event_digest=event_digest,
            )
            envelope = {
                "schema": PEER_EVENT_SCHEMA,
                "peer_id": "peer-one",
                "signing_key_id": key_id,
                "endpoint": endpoint,
                "sequence": sequence,
                "issued_at": issued,
                "event": event,
                "event_digest": event_digest,
                "signature": base64.urlsafe_b64encode(private.sign(payload)).decode("ascii").rstrip("="),
            }
            raw = (json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n").encode()
            owner.accept(
                raw,
                catalog=catalog,
                signature_verifier=Verifier(),
                now=now,
            )
    # Recovery must use the durable history after the accepting owner is gone.
    return PeerHealthRecoverySource(
        owner=FederationPeerReplayOwner(tmp_path / owner_name, peer_id="peer-one"),
        catalog=catalog,
        signature_verifier=Verifier(),
    )


@pytest.mark.parametrize("status", ["healthy", "unavailable"])
def test_poller_exposes_restart_safe_authenticated_peer_health_projection(
    tmp_path, monkeypatch, status
):
    now = datetime(2026, 10, 23, 16, 0, 0, tzinfo=timezone.utc)
    local_summary = _summary("dg-local", 2)
    peer_summary = _summary("dg-peer", 3)
    from sentientos.federation import poller as poller_module

    monkeypatch.setattr(poller_module, "build_local_summary", lambda runtime: local_summary)
    monkeypatch.setattr(poller_module, "read_peer_summary", lambda path: peer_summary)
    state_file = tmp_path / "federation" / "state" / "local.json"
    peer_state = tmp_path / "federation" / "state" / "peer.json"
    peer_state.parent.mkdir(parents=True, exist_ok=True)
    peer_state.write_text("{}", encoding="utf-8")
    config = FederationConfig(
        enabled=True,
        node_id=NodeId(name="local", fingerprint="fp-local"),
        state_file=str(state_file),
        peers=[PeerConfig(node_name="peer-one", state_file=str(peer_state))],
        poll_interval_seconds=1,
        max_drift_peers=0,
        max_incompatible_peers=0,
        max_missing_peers=0,
    )
    previous_status = "unavailable" if status == "healthy" else "healthy"
    source = _peer_health_source(
        tmp_path,
        status=status,
        now=now,
        history_statuses=(previous_status, status),
    )
    poller = FederationPoller(
        config,
        runtime=_RuntimeStub(),
        log_cb=lambda *_: None,
        peer_health_sources={"peer-one": source},
    )
    monkeypatch.setattr(poller_module, "datetime", type("FixedDateTime", (), {"now": staticmethod(lambda *_args, **_kwargs: now)}))

    poller._poll_once()

    projection = poller.get_peer_health_projections()["peer-one"]
    assert projection.outcome == "recovered"
    assert projection.observation is not None
    assert projection.observation.peer_reported_status == status
    assert projection.observation.sequence == 2
    assert projection.observation.claim_truth_established is False
    assert projection.observation.local_health_publication_permitted is False
    assert projection.observation.work_admission_permitted is False
    assert projection.observation.planning_permitted is False
    assert projection.observation.execution_permitted is False
    assert projection.observation.decision_power is False
    assert poller.get_window() is not None


def test_poller_separates_empty_omitted_and_recovery_error_outcomes(tmp_path, monkeypatch):
    local_summary = _summary("dg-local", 2)
    peer_summary = _summary("dg-peer", 3)
    from sentientos.federation import poller as poller_module

    monkeypatch.setattr(poller_module, "build_local_summary", lambda runtime: local_summary)
    monkeypatch.setattr(poller_module, "read_peer_summary", lambda path: peer_summary)
    state_file = tmp_path / "federation" / "state" / "local.json"
    peer_states = [tmp_path / "federation" / "state" / f"peer-{i}.json" for i in range(4)]
    peer_states[0].parent.mkdir(parents=True, exist_ok=True)
    for path in peer_states:
        path.write_text("{}", encoding="utf-8")
    config = FederationConfig(
        enabled=True,
        node_id=NodeId(name="local", fingerprint="fp-local"),
        state_file=str(state_file),
        peers=[
            PeerConfig(node_name="peer-one" if i == 0 else f"peer-{i}", state_file=str(path))
            for i, path in enumerate(peer_states)
        ],
        poll_interval_seconds=1,
        max_drift_peers=0,
        max_incompatible_peers=0,
        max_missing_peers=0,
    )
    empty_source = _peer_health_source(
        tmp_path, status="healthy", now=datetime(2026, 10, 23, 16, 0, 0, tzinfo=timezone.utc),
        accept_event=False, owner_name="empty-peer-one",
    )
    error_source = PeerHealthRecoverySource(
        owner=object(),  # type: ignore[arg-type]
        catalog=object(),  # type: ignore[arg-type]
        signature_verifier=object(),  # type: ignore[arg-type]
    )
    mismatched_source = _peer_health_source(
        tmp_path, status="healthy", now=datetime(2026, 10, 23, 16, 0, 0, tzinfo=timezone.utc),
        owner_name="mismatched-peer-one",
    )
    poller = FederationPoller(
        config,
        runtime=_RuntimeStub(),
        log_cb=lambda *_: None,
        peer_health_sources={
            "peer-one": empty_source,
            "peer-1": error_source,
            "peer-3": mismatched_source,
        },
    )
    monkeypatch.setattr(
        poller_module,
        "datetime",
        type("FixedDateTime", (), {"now": staticmethod(lambda *_args, **_kwargs: datetime(2026, 10, 23, 16, 0, 0, tzinfo=timezone.utc))}),
    )

    poller._poll_once()

    projections = poller.get_peer_health_projections()
    assert projections["peer-one"].outcome == "empty"
    assert projections["peer-one"].observation is None
    assert projections["peer-1"].outcome == "error"
    assert projections["peer-1"].error_code == "peer_health_replay_owner_required"
    assert projections["peer-2"].outcome == "omitted"
    assert projections["peer-3"].outcome == "error"
    assert projections["peer-3"].error_code == "peer_health_peer_identity_mismatch"


def test_source_validation_binds_daemon_peer_health_projection_acceptance():
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
    source = workflow.read_text(encoding="utf-8")
    marker = "      - name: Verify daemon peer Health projection recovery\n"
    assert source.count(marker) == 1
    step = source.split(marker, 1)[1].split("      - name:", 1)[0]
    assert "test_poller_exposes_restart_safe_authenticated_peer_health_projection" in step
    assert "test_poller_separates_empty_omitted_and_recovery_error_outcomes" in step
    assert "test_source_validation_binds_daemon_peer_health_projection_acceptance" in step
    assert "federation_daemon_peer_health_projection_provenance.json" in step
    assert "federation_daemon_peer_health_projection_acceptance.json" in step
    assert "federation_daemon_peer_health_projection_acceptance_result.json" in step
