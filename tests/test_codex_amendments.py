from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codex.amendments import AmendmentReviewBoard, SpecAmender


class ManualClock:
    def __init__(self) -> None:
        self.moment = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        current = self.moment
        self.moment += timedelta(seconds=1)
        return current


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture()
def base_spec() -> dict:
    return {
        "spec_id": "spec-recurring-gap",
        "title": "Recurring Coverage Spec",
        "objective": "Address baseline audit flow.",
        "directives": ["Keep the ledger open."],
        "testing_requirements": ["Ensure baseline audit flow replays."],
        "version": "v1",
        "status": "active",
    }


def test_amendment_proposals_include_deltas(tmp_path: Path, base_spec: dict) -> None:
    clock = ManualClock()
    root = tmp_path / "integration"
    engine = SpecAmender(root=root, now=clock.now)

    proposal = None
    for idx in range(3):
        proposal = engine.record_signal(
            base_spec["spec_id"],
            "coverage_gap",
            {"detail": f"missing_case_{idx}"},
            current_spec=base_spec,
        )
    assert proposal is not None, "Recurring signals should produce an amendment proposal"

    payload = _load_json(root / "specs" / "amendments" / "pending" / f"{proposal.proposal_id}.json")
    assert payload["context"]["counts"]["coverage_gap"] == 3
    assert payload["deltas"]["objective"]["after"].startswith("Tighten")
    assert payload["deltas"]["directives"]["added"], "Should add directives describing new coverage"
    assert payload["deltas"]["testing_requirements"]["added"], "Should add testing expectations"


def test_regeneration_links_lineage_and_archives(tmp_path: Path, base_spec: dict) -> None:
    clock = ManualClock()
    root = tmp_path / "integration"
    engine = SpecAmender(root=root, now=clock.now)

    proposal = engine.regenerate_spec(
        base_spec["spec_id"],
        operator="aurora",
        reason="structural-failure",
        current_spec=base_spec,
    )
    archive_path = root / "specs" / "amendments" / "archive" / "original_specs" / "spec-recurring-gap_v1.json"
    assert archive_path.exists(), "Original spec should be archived for rollback"

    spec_log_entries = _read_log(root / "spec_log.jsonl")
    regen_entry = next(entry for entry in spec_log_entries if entry["event"] == "regenerated")
    assert regen_entry["details"]["from_version"] == "v1"
    assert regen_entry["details"]["to_version"] == "v2"
    assert regen_entry["details"]["proposal_id"] == proposal.proposal_id


def test_dashboard_and_ledger_gating(tmp_path: Path, base_spec: dict) -> None:
    clock = ManualClock()
    root = tmp_path / "integration"
    engine = SpecAmender(root=root, now=clock.now)
    board = AmendmentReviewBoard(engine)

    proposal = engine.record_signal(
        base_spec["spec_id"],
        "coverage_gap",
        {"detail": "unverified branch"},
        current_spec=base_spec,
    )
    assert proposal is None, "Single signal should not trigger amendment"
    for _ in range(2):
        proposal = engine.record_signal(
            base_spec["spec_id"],
            "coverage_gap",
            {"detail": "unverified branch"},
            current_spec=base_spec,
        )
    assert proposal is not None

    dashboard = engine.dashboard_state()
    assert dashboard["panel"] == "Spec Amendments"
    diff = dashboard["pending"][0]["diff"]
    assert diff["objective"]["before"] == base_spec["objective"]
    assert "after" in diff["objective"]

    with pytest.raises(ValueError):
        board.approve(proposal.proposal_id, operator="aurora", ledger_entry=None)

    approved = board.approve(
        proposal.proposal_id,
        operator="aurora",
        ledger_entry="ledger://amend/001",
    )
    assert approved.status == "approved"
    assert engine.active_amendments(base_spec["spec_id"]), "Approved amendment should appear active"

    amendment_log = _read_log(root / "amendment_log.jsonl")
    assert any(entry["event"] == "approved" for entry in amendment_log)

    followup = engine.record_signal(
        "spec-followup",
        "coverage_gap",
        {"detail": "redundant"},
        current_spec=base_spec,
    )
    for _ in range(2):
        followup = engine.record_signal(
            "spec-followup",
            "coverage_gap",
            {"detail": "redundant"},
            current_spec=base_spec,
        )
    assert followup is not None

    rejected = board.reject(followup.proposal_id, operator="aurora", reason="not needed")
    rejected_path = root / "rejected_specs" / f"{rejected.proposal_id}.json"
    assert rejected_path.exists(), "Rejected proposals should be archived under rejected_specs"
    assert not engine.active_amendments("spec-followup")

    # Pending proposals must not be treated as active
    another = engine.record_signal(
        "spec-pending",
        "coverage_gap",
        {"detail": "pending branch"},
        current_spec=base_spec,
    )
    for _ in range(2):
        another = engine.record_signal(
            "spec-pending",
            "coverage_gap",
            {"detail": "pending branch"},
            current_spec=base_spec,
        )
    assert another is not None
    assert not engine.active_amendments("spec-pending"), "Ledger gating should block pending amendments"
