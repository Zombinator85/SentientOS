from __future__ import annotations

import json
from pathlib import Path

from sentientos.integrity_snapshot import compare_integrity_snapshots, emit_integrity_snapshot
from sentientos.signed_strategic import maybe_publish_strategic_witness, sign_object, verify_latest


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_sign_and_verify_and_tamper(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_HMAC_SECRET", "test-secret")
    proposal = {"schema_version": 2, "proposal_id": "p1", "created_at": "2099-01-01T00:00:00Z", "approval": {"status": "proposed"}}
    proposal_path = tmp_path / "glow/forge/strategic/proposals/proposal_1.json"
    _write_json(proposal_path, proposal)

    _ = sign_object(tmp_path, kind="proposal", object_id="p1", object_rel_path=str(proposal_path.relative_to(tmp_path)), object_payload=proposal, created_at="2099-01-01T00:00:00Z")
    ok, reason = verify_latest(tmp_path, last=10)
    assert ok is True
    assert reason is None

    proposal["approval"] = {"status": "tampered"}
    _write_json(proposal_path, proposal)
    ok2, reason2 = verify_latest(tmp_path, last=10)
    assert ok2 is False
    assert reason2 is not None and "object_sha256_mismatch" in reason2


def test_chain_linkage_and_snapshot_divergence(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_HMAC_SECRET", "test-secret")
    p1 = {"schema_version": 2, "proposal_id": "p1", "created_at": "2099-01-01T00:00:00Z"}
    c1 = {"schema_version": 1, "change_id": "c1", "applied_at": "2099-01-01T00:05:00Z"}
    p1_path = tmp_path / "glow/forge/strategic/proposals/proposal_1.json"
    c1_path = tmp_path / "glow/forge/strategic/changes/change_1.json"
    _write_json(p1_path, p1)
    _write_json(c1_path, c1)
    sig1 = sign_object(tmp_path, kind="proposal", object_id="p1", object_rel_path=str(p1_path.relative_to(tmp_path)), object_payload=p1, created_at="2099-01-01T00:00:00Z")
    sig2 = sign_object(tmp_path, kind="change", object_id="c1", object_rel_path=str(c1_path.relative_to(tmp_path)), object_payload=c1, created_at="2099-01-01T00:05:00Z")
    assert sig2.prev_sig_hash == sig1.sig_hash

    local = {"latest_strategic_sig_hash": sig2.sig_hash[:16]}
    peer = {"latest_strategic_sig_hash": "deadbeefdeadbeef"}
    comparison = compare_integrity_snapshots(local, peer)
    assert comparison.overall_status == "diverged"
    assert "strategic_signature_tip_mismatch" in comparison.divergence_reasons


def test_witness_publish_file_backend(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_HMAC_SECRET", "test-secret")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_WITNESS_PUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_WITNESS_BACKEND", "file")
    proposal = {"schema_version": 2, "proposal_id": "p1", "created_at": "2099-01-01T00:00:00Z"}
    proposal_path = tmp_path / "glow/forge/strategic/proposals/proposal_1.json"
    _write_json(proposal_path, proposal)
    _ = sign_object(tmp_path, kind="proposal", object_id="p1", object_rel_path=str(proposal_path.relative_to(tmp_path)), object_payload=proposal, created_at="2099-01-01T00:00:00Z")

    first, err1 = maybe_publish_strategic_witness(tmp_path)
    second, err2 = maybe_publish_strategic_witness(tmp_path)
    assert err1 is None
    assert err2 is None
    assert first["status"] == "ok"
    assert second["status"] == "ok"
    rows = (tmp_path / "glow/federation/strategic_witness_tags.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1


def test_witness_publish_git_skips_when_mutation_disallowed(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_HMAC_SECRET", "test-secret")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_WITNESS_PUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_WITNESS_BACKEND", "git")
    proposal = {"schema_version": 2, "proposal_id": "p1", "created_at": "2099-01-01T00:00:00Z"}
    proposal_path = tmp_path / "glow/forge/strategic/proposals/proposal_1.json"
    _write_json(proposal_path, proposal)
    _ = sign_object(tmp_path, kind="proposal", object_id="p1", object_rel_path=str(proposal_path.relative_to(tmp_path)), object_payload=proposal, created_at="2099-01-01T00:00:00Z")

    status, err = maybe_publish_strategic_witness(tmp_path, allow_git_tag_publish=False)
    assert err is None
    assert status["status"] == "skipped_mutation_disallowed"
    assert status["failure"] == "mutation_disallowed"


def test_snapshot_includes_strategic_tip(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_HMAC_SECRET", "test-secret")
    proposal = {"schema_version": 2, "proposal_id": "p1", "created_at": "2099-01-01T00:00:00Z"}
    proposal_path = tmp_path / "glow/forge/strategic/proposals/proposal_1.json"
    _write_json(proposal_path, proposal)
    sig = sign_object(tmp_path, kind="proposal", object_id="p1", object_rel_path=str(proposal_path.relative_to(tmp_path)), object_payload=proposal, created_at="2099-01-01T00:00:00Z")

    snap = emit_integrity_snapshot(tmp_path)
    assert snap.latest_strategic_sig_hash == sig.sig_hash[:16]
