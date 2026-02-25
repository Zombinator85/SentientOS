from __future__ import annotations

import json
from pathlib import Path

from sentientos.integrity_controller import evaluate_integrity
from sentientos.orchestrator import OrchestratorConfig, tick
from sentientos.policy_fingerprint import emit_policy_fingerprint


def _seed_repo(root: Path) -> None:
    (root / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (root / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")


def test_integrity_status_deterministic_hash(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    fingerprint = emit_policy_fingerprint(tmp_path, ts="2099-01-01T00:00:00Z")
    first = evaluate_integrity(tmp_path, policy_hash=fingerprint.policy_hash)
    second = evaluate_integrity(tmp_path, policy_hash=fingerprint.policy_hash)
    assert first.to_dict() == second.to_dict()
    assert first.canonical_hash() == second.canonical_hash()


def test_orchestrator_writes_integrity_artifacts(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _seed_repo(tmp_path)
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_HMAC_SECRET", "secret")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY", "1")

    tick(tmp_path, config=OrchestratorConfig(True, 300, False, False, False, False, False))

    integrity_files = sorted((tmp_path / "glow/forge/integrity").glob("status_*.json"))
    assert integrity_files
    snapshots = sorted((tmp_path / "glow/forge/attestation/snapshots").glob("snapshot_*.json"))
    assert snapshots

    index_payload = json.loads((tmp_path / "glow/forge/index.json").read_text(encoding="utf-8"))
    assert index_payload["integrity_status"] in {"ok", "warn", "fail"}
    assert index_payload["last_integrity_status_path"]
    assert isinstance(index_payload["integrity_gate_summary"], dict)

