from __future__ import annotations

import json
from pathlib import Path

from sentientos.orchestrator import OrchestratorConfig, tick


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

    trace_path = tmp_path / "glow/forge/traces" / f"{result.trace_id}.json"
    trace_payload = json.loads(trace_path.read_text(encoding="utf-8"))
    clamps = trace_payload.get("clamps_applied", [])
    assert any(isinstance(item, dict) and item.get("name") == "strategic_adaptation_proposal" for item in clamps)
