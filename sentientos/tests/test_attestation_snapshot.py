from __future__ import annotations

from sentientos.attestation_snapshot import AttestationSnapshot, emit_snapshot, maybe_sign_snapshot, verify_recent_snapshots
from sentientos.integrity_snapshot import compare_integrity_snapshots


def test_attestation_snapshot_sign_and_verify_hmac(monkeypatch, tmp_path):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_HMAC_SECRET", "secret")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY", "1")
    snapshot = AttestationSnapshot(
        schema_version=1,
        ts="2099-01-01T00:00:00Z",
        policy_hash="policy",
        integrity_status_hash="integrity",
        latest_rollup_sig_hash=None,
        latest_strategic_sig_hash=None,
        latest_goal_graph_hash="g1",
        latest_catalog_checkpoint_hash=None,
        doctrine_bundle_sha256="bundle",
        witness_summary={"rollup": {"status": "disabled"}, "strategic": {"status": "disabled"}},
    )
    rel = emit_snapshot(tmp_path, snapshot)
    envelope = maybe_sign_snapshot(tmp_path, snapshot_rel_path=rel, snapshot_payload=snapshot.to_dict())
    assert envelope is not None
    verify = verify_recent_snapshots(tmp_path, last=5)
    assert verify.status == "ok"


def test_compare_snapshot_detects_attestation_policy_mismatch() -> None:
    local = {
        "latest_attestation_snapshot_sig_hash": "a1",
        "latest_attestation_snapshot_hash": "h1",
        "integrity_status_hash": "i1",
        "policy_hash": "p1",
    }
    peer = {
        "latest_attestation_snapshot_sig_hash": "a2",
        "latest_attestation_snapshot_hash": "h2",
        "integrity_status_hash": "i2",
        "policy_hash": "p2",
    }
    comparison = compare_integrity_snapshots(local, peer)
    assert "attestation_snapshot_tip_mismatch" in comparison.divergence_reasons
    assert "policy_hash_mismatch" in comparison.divergence_reasons

