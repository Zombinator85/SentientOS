from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.integrity_controller import (
    IntegrityBudget,
    IntegrityGateResult,
    evaluate_integrity,
)
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


def test_integrity_controller_fails_closed_on_corrupt_enabled_snapshot_index(
    monkeypatch, tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    from sentientos.attestation_snapshot import SIGNATURE_INDEX_PATH

    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY", "1")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_ENFORCE", "1")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_HMAC_SECRET", "secret")
    index = tmp_path / SIGNATURE_INDEX_PATH
    index.parent.mkdir(parents=True)
    index.write_text('{"sig_hash":"broken"}\nnot-json\n', encoding="utf-8")

    status = evaluate_integrity(tmp_path, policy_hash="test-policy")

    gate = next(item for item in status.gate_results
        if item.name == "attestation_snapshot_signatures")
    assert gate.status == "fail"
    assert gate.reason == "signature_custody_invalid"
    assert status.mutation_allowed is False
    assert status.publish_allowed is False
    assert status.automerge_allowed is False


@pytest.mark.no_legacy_skip
def test_verification_budget_does_not_execute_skipped_gates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    import sentientos.integrity_controller as controller

    calls: dict[str, list[bool]] = {
        "attestation_snapshot_signatures": [],
        "rollup_signatures": [],
        "strategic_signatures": [],
    }

    def gate_for(name: str):
        def gate(_root: Path, checked_at: str, _budget: IntegrityBudget,
                 *, dry_run: bool = False) -> IntegrityGateResult:
            calls[name].append(dry_run)
            return IntegrityGateResult(name, "ok", "planned" if dry_run else "verified", [], checked_at)
        return gate

    monkeypatch.setattr(controller, "_gate_snapshot_signatures",
        gate_for("attestation_snapshot_signatures"))
    monkeypatch.setattr(controller, "_gate_rollup_signatures",
        gate_for("rollup_signatures"))
    monkeypatch.setattr(controller, "_gate_strategic_signatures",
        gate_for("strategic_signatures"))

    results = controller._verification_budgeted_gates(
        tmp_path, "2026-10-12T00:00:00Z",
        IntegrityBudget(1, 10, 6, 6, 1),
    )

    by_name = {result.name: result for result in results}
    assert by_name["attestation_snapshot_signatures"].reason == "skipped_budget_exhausted"
    assert by_name["rollup_signatures"].reason == "skipped_budget_exhausted"
    assert by_name["strategic_signatures"].reason == "verified"
    assert calls == {
        "attestation_snapshot_signatures": [True],
        "rollup_signatures": [True],
        "strategic_signatures": [True, False],
    }


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

