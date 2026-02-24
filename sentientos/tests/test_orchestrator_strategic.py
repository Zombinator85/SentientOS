from __future__ import annotations

import json
from pathlib import Path

from sentientos.orchestrator import OrchestratorConfig, tick
from sentientos.signed_strategic import sign_object


def _seed_repo(root: Path) -> None:
    (root / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (root / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")


def test_orchestrator_propose_only_with_cooldown(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _seed_repo(tmp_path)
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_AUTO_PROPOSE", "1")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_AUTO_APPLY", "0")

    tick(tmp_path, config=OrchestratorConfig(True, 300, False, False, False, False, False))
    proposals_path = tmp_path / "pulse/strategic_proposals.jsonl"
    assert proposals_path.exists()
    first_rows = proposals_path.read_text(encoding="utf-8").splitlines()
    assert len(first_rows) == 1

    tick(tmp_path, config=OrchestratorConfig(True, 300, False, False, False, False, False))
    second_rows = proposals_path.read_text(encoding="utf-8").splitlines()
    assert len(second_rows) == 1


def test_orchestrator_links_strategic_in_index_and_trace(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _seed_repo(tmp_path)
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_AUTO_PROPOSE", "1")

    result = tick(tmp_path, config=OrchestratorConfig(True, 300, False, False, False, False, False))

    index_payload = json.loads((tmp_path / "glow/forge/index.json").read_text(encoding="utf-8"))
    assert index_payload["strategic_last_proposal_id"]
    assert index_payload["strategic_last_proposal_status"] in {"proposed", "approved", "applied", "none"}
    assert isinstance(index_payload.get("strategic_last_proposal_added_goals"), list)
    assert isinstance(index_payload.get("strategic_last_proposal_removed_goals"), list)

    trace_path = tmp_path / "glow/forge/traces" / f"{result.trace_id}.json"
    trace_payload = json.loads(trace_path.read_text(encoding="utf-8"))
    clamps = trace_payload.get("clamps_applied", [])
    strategic = next((item for item in clamps if isinstance(item, dict) and item.get("name") == "strategic_adaptation_proposal"), None)
    assert strategic is not None
    after = strategic.get("after") if isinstance(strategic, dict) else {}
    assert isinstance(after, dict) and isinstance(after.get("strategic_counterfactual_summary"), dict)


def test_orchestrator_runtime_signature_verify_ok(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _seed_repo(tmp_path)
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_HMAC_SECRET", "test-secret")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_SIG_VERIFY", "1")
    proposal = {"schema_version": 2, "proposal_id": "p1", "created_at": "2099-01-01T00:00:00Z"}
    proposal_path = tmp_path / "glow/forge/strategic/proposals/proposal_1.json"
    proposal_path.parent.mkdir(parents=True, exist_ok=True)
    proposal_path.write_text(json.dumps(proposal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _ = sign_object(tmp_path, kind="proposal", object_id="p1", object_rel_path=str(proposal_path.relative_to(tmp_path)), object_payload=proposal, created_at="2099-01-01T00:00:00Z")

    _ = tick(tmp_path, config=OrchestratorConfig(True, 300, False, False, False, False, False))
    report = json.loads(sorted((tmp_path / "glow/forge/orchestrator/ticks").glob("tick_*.json"))[-1].read_text(encoding="utf-8"))
    assert report["strategic_sig_verify_status"] == "ok"
    assert report["strategic_sig_verify_checked_n"] == 1


def test_orchestrator_runtime_signature_verify_warn_and_enforce(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _seed_repo(tmp_path)
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_HMAC_SECRET", "test-secret")
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_SIG_VERIFY", "1")
    proposal = {"schema_version": 2, "proposal_id": "p1", "created_at": "2099-01-01T00:00:00Z"}
    proposal_path = tmp_path / "glow/forge/strategic/proposals/proposal_1.json"
    proposal_path.parent.mkdir(parents=True, exist_ok=True)
    proposal_path.write_text(json.dumps(proposal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _ = sign_object(tmp_path, kind="proposal", object_id="p1", object_rel_path=str(proposal_path.relative_to(tmp_path)), object_payload=proposal, created_at="2099-01-01T00:00:00Z")
    proposal["tampered"] = True
    proposal_path.write_text(json.dumps(proposal, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    monkeypatch.setenv("SENTIENTOS_STRATEGIC_SIG_WARN", "1")
    _ = tick(tmp_path, config=OrchestratorConfig(True, 300, False, False, False, False, False))
    warn_report = json.loads(sorted((tmp_path / "glow/forge/orchestrator/ticks").glob("tick_*.json"))[-1].read_text(encoding="utf-8"))
    assert warn_report["strategic_sig_verify_status"] == "warn"

    monkeypatch.delenv("SENTIENTOS_STRATEGIC_SIG_WARN", raising=False)
    monkeypatch.setenv("SENTIENTOS_STRATEGIC_SIG_ENFORCE", "1")
    _ = tick(tmp_path, config=OrchestratorConfig(True, 300, False, False, False, False, False))
    enforce_report = json.loads(sorted((tmp_path / "glow/forge/orchestrator/ticks").glob("tick_*.json"))[-1].read_text(encoding="utf-8"))
    assert enforce_report["strategic_sig_verify_status"] == "fail"
    assert enforce_report["mutation_allowed"] is False
