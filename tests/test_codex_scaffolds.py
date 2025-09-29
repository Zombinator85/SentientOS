from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codex.scaffolds import ScaffoldEngine
from codex.specs import SpecProposal
from scaffolds_dashboard import scaffolds_panel_state


class ManualClock:
    def __init__(self) -> None:
        self.moment = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        current = self.moment
        self.moment += timedelta(seconds=1)
        return current


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_log(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _proposal(spec_id: str = "spec-ledger-1") -> SpecProposal:
    return SpecProposal(
        spec_id=spec_id,
        title="Ledger gated scaffold",
        objective="Bootstrap scaffold generation",
        directives=["Generate scaffolds for approved specs."],
        testing_requirements=["Confirm ledger gating"],
        trigger_key="anomaly::ledger-gate",
        trigger_context={"source": "test"},
        status="queued",
    )


def test_scaffold_engine_generates_stubs(tmp_path: Path) -> None:
    clock = ManualClock()
    engine = ScaffoldEngine(repo_root=tmp_path, integration_root=tmp_path / "integration", now=clock.now)
    proposal = _proposal()

    record = engine.generate(proposal)

    daemon_path = tmp_path / Path(record.paths["daemon"])
    test_path = tmp_path / Path(record.paths["test"])
    metadata_path = tmp_path / "integration" / "scaffolds" / f"{proposal.spec_id}.json"
    log_path = tmp_path / "integration" / "scaffold_log.jsonl"

    assert daemon_path.exists()
    assert test_path.exists()
    assert metadata_path.exists()

    daemon_text = daemon_path.read_text(encoding="utf-8")
    test_text = test_path.read_text(encoding="utf-8")

    assert f"Spec ID: {proposal.spec_id}" in daemon_text
    assert "Status: INACTIVE" in daemon_text
    assert f"Rollback: integration/scaffolds/{proposal.spec_id}.json" in daemon_text
    assert f"Spec ID: {proposal.spec_id}" in test_text

    metadata = _load_json(metadata_path)
    assert metadata["status"] == "inactive"
    assert metadata["paths"]["daemon"] == record.paths["daemon"]

    log_entries = _read_log(log_path)
    assert log_entries and log_entries[0]["action"] == "generated"


def test_ledger_gating_requires_entry(tmp_path: Path) -> None:
    clock = ManualClock()
    engine = ScaffoldEngine(repo_root=tmp_path, integration_root=tmp_path / "integration", now=clock.now)
    proposal = _proposal("spec-ledger-2")
    engine.generate(proposal)

    with pytest.raises(ValueError):
        engine.enable(proposal.spec_id, operator="aurora", ledger_entry=None)

    metadata_before = _load_json(tmp_path / "integration" / "scaffolds" / f"{proposal.spec_id}.json")
    assert metadata_before["status"] == "inactive"

    record = engine.enable(proposal.spec_id, operator="aurora", ledger_entry="ledger://approval/123")
    metadata_after = _load_json(tmp_path / "integration" / "scaffolds" / f"{proposal.spec_id}.json")

    assert record.status == "enabled"
    assert metadata_after["status"] == "enabled"
    assert metadata_after["ledger_entry"] == "ledger://approval/123"

    log_entries = _read_log(tmp_path / "integration" / "scaffold_log.jsonl")
    assert any(entry["action"] == "enabled" for entry in log_entries)


def test_dashboard_lists_scaffolds(tmp_path: Path) -> None:
    clock = ManualClock()
    engine = ScaffoldEngine(repo_root=tmp_path, integration_root=tmp_path / "integration", now=clock.now)
    proposal = _proposal("spec-ledger-3")
    engine.generate(proposal)

    state = scaffolds_panel_state(engine, include_history=True)

    assert state["panel"] == "Scaffolds"
    assert state["scaffolds"], "Dashboard should list scaffolds"
    entry = state["scaffolds"][0]
    assert entry["spec_id"] == proposal.spec_id
    assert entry["status"] == "inactive"
    assert entry["paths"]["daemon"].endswith("spec_ledger_3_daemon.py")
