from __future__ import annotations

import json
from pathlib import Path

from sentientos.federation_integrity import federation_integrity_gate
from sentientos.forge_merge_train import ForgeMergeTrain, TrainState
from sentientos.github_merge import MergeResult, RebaseResult
from sentientos.integrity_snapshot import compare_integrity_snapshots, emit_integrity_snapshot


class _Ops:
    checks = "success"

    def checks_for(self, entry):  # type: ignore[no-untyped-def]
        return (self.checks, None, None)

    def wait_for_checks(self, entry, timeout_seconds: int = 1800):  # type: ignore[no-untyped-def]
        _ = entry, timeout_seconds
        return ("success", False)

    def is_branch_behind_base(self, entry, base_branch: str) -> bool:  # type: ignore[no-untyped-def]
        _ = entry, base_branch
        return False

    def rebase_branch(self, entry, base_branch: str):  # type: ignore[no-untyped-def]
        _ = entry, base_branch
        return RebaseResult(ok=True, conflict=False, message="ok", new_head_sha="new", suspect_files=[])

    def merge_pull_request(self, entry, strategy: str):  # type: ignore[no-untyped-def]
        _ = entry, strategy
        return MergeResult(ok=True, conflict=False, message="ok")


def _entry():  # type: ignore[no-untyped-def]
    from sentientos.forge_merge_train import TrainEntry

    return TrainEntry(
        run_id="run-1",
        pr_url="https://github.com/o/r/pull/11",
        pr_number=11,
        head_sha="abc",
        branch="forge/1",
        goal_id="forge_smoke_noop",
        campaign_id=None,
        status="ready",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        check_overall="success",
    )


def test_integrity_snapshot_deterministic_fields(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_NODE_ID", "node-a")
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/contract_manifest.json").write_text(json.dumps({"bundle_sha256": "bundle-1"}) + "\n", encoding="utf-8")

    snap = emit_integrity_snapshot(tmp_path)

    payload = json.loads((tmp_path / "glow/federation/integrity_snapshot.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["node_id"] == "node-a"
    assert payload["doctrine_bundle_sha256"] == "bundle-1"
    assert snap.last_receipt_chain_tip_hash is None


def test_peer_divergence_detection() -> None:
    local = {
        "doctrine_bundle_sha256": "a",
        "last_receipt_chain_tip_hash": "r1",
        "last_anchor_tip_hash": "t1",
    }
    peer = {
        "doctrine_bundle_sha256": "b",
        "last_receipt_chain_tip_hash": "r2",
        "last_anchor_tip_hash": "t2",
    }
    result = compare_integrity_snapshots(local, peer)
    assert result.overall_status == "diverged"
    assert set(result.divergence_reasons) == {"doctrine_bundle_sha_mismatch", "receipt_tip_mismatch", "anchor_tip_mismatch"}


def test_warn_records_without_blocking(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FEDERATION_INTEGRITY_WARN", "1")
    (tmp_path / "glow/federation").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/federation/integrity_snapshot.json").write_text(
        json.dumps({"doctrine_bundle_sha256": "a", "last_receipt_chain_tip_hash": "r1", "last_anchor_tip_hash": "t1"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "glow/federation/peers/p1").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/federation/peers/p1/integrity_snapshot.json").write_text(
        json.dumps({"node_id": "p1", "doctrine_bundle_sha256": "b", "last_receipt_chain_tip_hash": "r1", "last_anchor_tip_hash": "t1"}) + "\n",
        encoding="utf-8",
    )
    gate = federation_integrity_gate(tmp_path, context="test")
    assert gate["status"] == "diverged"
    assert gate["blocked"] is False


def test_enforce_blocks_merge_train(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")
    monkeypatch.setenv("SENTIENTOS_FEDERATION_INTEGRITY_ENFORCE", "1")
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        json.dumps({"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "glow/federation").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/federation/integrity_snapshot.json").write_text(
        json.dumps({"doctrine_bundle_sha256": "a", "last_receipt_chain_tip_hash": "r1", "last_anchor_tip_hash": "t1"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "glow/federation/peers/p1").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/federation/peers/p1/integrity_snapshot.json").write_text(
        json.dumps({"node_id": "p1", "doctrine_bundle_sha256": "b", "last_receipt_chain_tip_hash": "r1", "last_anchor_tip_hash": "t1"}) + "\n",
        encoding="utf-8",
    )

    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    train.save_state(TrainState(entries=[_entry()]))
    result = train.tick()
    assert result["status"] == "held"
    assert result["reason"] == "federation_integrity_diverged"
