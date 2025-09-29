from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codex.implementations import Implementor
from codex.scaffolds import ScaffoldEngine
from codex.specs import SpecProposal
from implementations_dashboard import implementations_panel_state


class ManualClock:
    def __init__(self) -> None:
        self.moment = datetime(2025, 2, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        current = self.moment
        self.moment += timedelta(seconds=1)
        return current


def _proposal(spec_id: str = "spec-implementor-1") -> SpecProposal:
    return SpecProposal(
        spec_id=spec_id,
        title="Codex Implementor draft",
        objective="Generate first pass implementations",
        directives=[
            "Create daemon flow for spec enforcement",
            "Add test coverage for ledger gating",
        ],
        testing_requirements=["Ensure pending review gating"],
        trigger_key="anomaly::implementor",
        trigger_context={"source": "test"},
        status="queued",
    )


def _read_log(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_implementor_drafts_from_scaffold(tmp_path: Path) -> None:
    clock = ManualClock()
    implementor = Implementor(repo_root=tmp_path, integration_root=tmp_path / "integration", now=clock.now)
    engine = ScaffoldEngine(
        repo_root=tmp_path,
        integration_root=tmp_path / "integration",
        now=clock.now,
        implementor=implementor,
    )
    proposal = _proposal()

    record = engine.generate(proposal)

    implementation_path = tmp_path / "integration" / "implementations" / f"{proposal.spec_id}.json"
    log_path = tmp_path / "integration" / "implementation_log.jsonl"

    assert implementation_path.exists(), "Implementor should persist draft metadata"
    assert log_path.exists(), "Implementor should append draft logs"

    payload = json.loads(implementation_path.read_text(encoding="utf-8"))
    assert payload["status"] == "pending_review"
    assert payload["spec_id"] == proposal.spec_id
    assert payload["blocks"], "Draft blocks should be recorded"

    draft = payload["blocks"][0]["draft"]
    assert f"Spec Link:" in draft
    assert f"Confidence:" in draft
    assert f"Rollback: integration/implementations/{proposal.spec_id}.json" in draft
    assert "# CODEX_IMPLEMENTATION START" in draft
    assert "# CODEX_IMPLEMENTATION END" in draft
    assert proposal.spec_id in draft

    log_entries = _read_log(log_path)
    assert any(entry["action"] == "drafted" for entry in log_entries)


def test_dashboard_surfaces_pending_implementations(tmp_path: Path) -> None:
    clock = ManualClock()
    implementor = Implementor(repo_root=tmp_path, integration_root=tmp_path / "integration", now=clock.now)
    engine = ScaffoldEngine(
        repo_root=tmp_path,
        integration_root=tmp_path / "integration",
        now=clock.now,
        implementor=implementor,
    )
    proposal = _proposal("spec-implementor-2")
    engine.generate(proposal)

    state = implementations_panel_state(implementor, include_history=True)

    assert state["panel"] == "Implementations"
    assert state["pending"], "Pending implementations should be listed"
    entry = state["pending"][0]
    assert entry["spec_id"] == proposal.spec_id
    assert entry["blocks"], "Blocks should be surfaced for review"


def test_implementations_gated_by_ledger(tmp_path: Path) -> None:
    clock = ManualClock()
    implementor = Implementor(repo_root=tmp_path, integration_root=tmp_path / "integration", now=clock.now)
    engine = ScaffoldEngine(
        repo_root=tmp_path,
        integration_root=tmp_path / "integration",
        now=clock.now,
        implementor=implementor,
    )
    proposal = _proposal("spec-implementor-3")
    engine.generate(proposal)

    with pytest.raises(RuntimeError):
        implementor.assert_ready(proposal.spec_id)

    engine.enable(proposal.spec_id, operator="aurora", ledger_entry="ledger://impl/123")

    with pytest.raises(RuntimeError):
        implementor.assert_ready(proposal.spec_id)

    implementor.approve(proposal.spec_id, operator="aurora")

    implementor.assert_ready(proposal.spec_id)

    log_path = tmp_path / "integration" / "implementation_log.jsonl"
    log_entries = _read_log(log_path)
    assert any(entry["action"] == "approved" for entry in log_entries)

