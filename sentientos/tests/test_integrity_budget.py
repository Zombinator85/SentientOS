from __future__ import annotations

from pathlib import Path

from sentientos.integrity_controller import evaluate_integrity
from sentientos.policy_fingerprint import emit_policy_fingerprint


def _seed_repo(root: Path) -> None:
    (root / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (root / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")


def test_budget_exhaustion_skips_snapshot_verify_not_strategic(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _seed_repo(tmp_path)
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY", "1")
    monkeypatch.setenv("SENTIENTOS_ROLLUP_SIG_VERIFY", "1")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_SIG_VERIFY", "1")
    monkeypatch.setenv("SENTIENTOS_INTEGRITY_MAX_VERIFY_STREAMS", "2")

    fp = emit_policy_fingerprint(tmp_path, ts="2099-01-01T00:00:00Z")
    status = evaluate_integrity(tmp_path, policy_hash=fp.policy_hash)

    gate_map = {gate.name: gate for gate in status.gate_results}
    assert gate_map["attestation_snapshot_signatures"].reason == "skipped_budget_exhausted"
    assert gate_map["strategic_signatures"].reason != "skipped_budget_exhausted"
    assert status.budget_exhausted is True


def test_integrity_status_excludes_recursive_snapshot_fields(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    fp = emit_policy_fingerprint(tmp_path, ts="2099-01-01T00:00:00Z")
    status = evaluate_integrity(tmp_path, policy_hash=fp.policy_hash)
    payload = status.to_dict()

    assert "attestation_snapshot_tip" not in payload
    assert "snapshot_signature_hash" not in payload
