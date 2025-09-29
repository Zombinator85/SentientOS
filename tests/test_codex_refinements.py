from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codex.implementations import Implementor
from codex.refinements import Refiner
from codex.specs import SpecProposal
from implementations_dashboard import implementations_panel_state


class ManualClock:
    def __init__(self) -> None:
        self.moment = datetime(2025, 3, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        current = self.moment
        self.moment += timedelta(seconds=1)
        return current


def _proposal(spec_id: str) -> SpecProposal:
    return SpecProposal(
        spec_id=spec_id,
        title="Codex refinement loop",
        objective="Exercise refiner iterations",
        directives=["Draft initial daemon"],
        testing_requirements=["Ensure refiner can iterate"],
        trigger_key="anomaly::refiner",
        trigger_context={"source": "test"},
        status="queued",
    )


def _bootstrap(
    tmp_path: Path, spec_id: str
) -> tuple[ManualClock, Implementor, Refiner, SpecProposal]:
    clock = ManualClock()
    implementor = Implementor(
        repo_root=tmp_path,
        integration_root=tmp_path / "integration",
        now=clock.now,
    )
    refiner = Refiner(
        repo_root=tmp_path,
        integration_root=tmp_path / "integration",
        implementor=implementor,
        now=clock.now,
    )
    proposal = _proposal(spec_id)
    implementor.draft_from_scaffold(
        proposal,
        {
            "paths": {
                "daemon": "codex/daemon_module.py",
                "test": "tests/test_daemon_module.py",
            }
        },
    )
    return clock, implementor, refiner, proposal


def _read_log(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_refiner_generates_versions_and_dashboard(tmp_path: Path) -> None:
    _, implementor, refiner, proposal = _bootstrap(tmp_path, "spec-refiner-1")

    v1_path = tmp_path / "integration" / "implementations" / proposal.spec_id / "versions" / "v1.json"
    assert v1_path.exists(), "Initial draft should persist as version v1"

    refiner.refine(
        proposal.spec_id,
        failure="pytest failure",
        change_summary="Adjust error handling",
        operator="aurora",
        transform=lambda block: block.draft + "\n    # refined iteration",
    )

    record = implementor.load_record(proposal.spec_id)
    assert record.pending_version == "v2"
    assert record.versions and record.versions[-1]["parent_id"] == "v1"
    assert record.versions[-1]["change_summary"] == "Adjust error handling"

    version_record = implementor.load_version(proposal.spec_id, "v2")
    assert version_record.parent_id == "v1"
    assert any(entry.get("action") == "refined" for entry in version_record.history or [])

    log_path = tmp_path / "integration" / "refinement_log.jsonl"
    entries = _read_log(log_path)
    assert any(entry["action"] == "refined" for entry in entries)

    dashboard = implementations_panel_state(implementor, include_history=True)
    pending = next(item for item in dashboard["pending"] if item["spec_id"] == proposal.spec_id)
    assert pending["pending_version"] == "v2"
    latest_version = pending["versions"][-1]
    assert "diff" in latest_version
    assert "refined iteration" in latest_version["diff"]


def test_refiner_gating_and_rollbacks(tmp_path: Path) -> None:
    _clock, implementor, refiner, proposal = _bootstrap(tmp_path, "spec-refiner-2")

    implementor.commit_ledger_entry(proposal.spec_id, "ledger://refiner/001")
    implementor.approve(proposal.spec_id, operator="aurora")
    implementor.assert_ready(proposal.spec_id)

    refiner.refine(
        proposal.spec_id,
        failure="integration failure",
        change_summary="Tighten validation",
        operator="aurora",
        transform=lambda block: block.draft + "\n    # tightened",
    )

    record = implementor.load_record(proposal.spec_id)
    assert record.status == "pending_review"
    with pytest.raises(RuntimeError):
        implementor.assert_ready(proposal.spec_id)

    implementor.approve(proposal.spec_id, operator="aurora", version_id="v2")
    implementor.assert_ready(proposal.spec_id)
    updated = implementor.load_record(proposal.spec_id)
    assert updated.active_version == "v2"

    refiner.rollback(proposal.spec_id, "v1", operator="aurora", reason="Regression")
    rolled = implementor.load_record(proposal.spec_id)
    assert rolled.active_version == "v1"
    assert rolled.pending_version is None
    implementor.assert_ready(proposal.spec_id)

    log_entries = _read_log(tmp_path / "integration" / "refinement_log.jsonl")
    actions = {entry["action"] for entry in log_entries}
    assert {"refined", "rolled_back"}.issubset(actions)
