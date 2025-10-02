from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codex.amendments import (
    AmendmentReviewBoard,
    IntegrityViolation,
    PrivilegeViolation,
    SpecAmender,
)
from privilege_lint.reporting import PrivilegeReport


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


def _make_report(status: str, issues: list[str]) -> PrivilegeReport:
    return PrivilegeReport(
        status=status,
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        issues=issues,
        metrics={"files": 0, "cache_hits": 0, "runtime": 0, "rules": {}},
        checked_files=[],
    )


class StubHook:
    def __init__(self, report: PrivilegeReport) -> None:
        self.report = report
        self.calls: list[tuple[str, str]] = []

    def enforce(
        self,
        *,
        spec_id: str,
        proposal_id: str,
        requested_format: str | None = None,
        paths: list[str] | None = None,
    ) -> PrivilegeReport:
        self.calls.append((spec_id, proposal_id))
        return self.report


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
    hook = StubHook(_make_report("clean", []))
    board = AmendmentReviewBoard(engine, hook=hook)

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
    assert hook.calls, "Privilege hook should be invoked during approval"
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


def test_integrity_daemon_quarantines_malicious_amendment(
    tmp_path: Path, base_spec: dict
) -> None:
    clock = ManualClock()
    root = tmp_path / "integration"
    engine = SpecAmender(root=root, now=clock.now)

    hostile_spec = dict(base_spec)
    hostile_spec.pop("directives")
    hostile_spec["status"] = "reboot"
    hostile_spec["lineage"] = None

    with pytest.raises(IntegrityViolation) as excinfo:
        engine.propose_manual(
            base_spec["spec_id"],
            summary="",
            deltas={"directives": {"before": base_spec["directives"], "after": []}},
            context={"origin": "rogue-operator"},
            original_spec={**base_spec, "lineage": {"seed": "v0"}},
            proposed_spec=hostile_spec,
        )

    violation = excinfo.value
    assert "tamper" in violation.reason_codes
    assert "violation_of_vow" in violation.reason_codes

    quarantine_dir = root / "daemon" / "integrity" / "quarantine"
    entries = list(quarantine_dir.glob("*.json"))
    assert entries, "IntegrityDaemon should quarantine hostile amendments"
    record = _load_json(entries[0])
    assert record["violations"], "Quarantine record should list violations"
    assert record["proposal"]["spec_id"] == base_spec["spec_id"]


def test_privilege_violation_blocks_approval(tmp_path: Path, base_spec: dict) -> None:
    clock = ManualClock()
    root = tmp_path / "integration"
    engine = SpecAmender(root=root, now=clock.now)
    hook = StubHook(_make_report("violation", ["spec.py:1: missing banner"]))
    board = AmendmentReviewBoard(engine, hook=hook)

    proposal = engine.record_signal(
        base_spec["spec_id"],
        "coverage_gap",
        {"detail": "unverified branch"},
        current_spec=base_spec,
    )
    for _ in range(2):
        proposal = engine.record_signal(
            base_spec["spec_id"],
            "coverage_gap",
            {"detail": "unverified branch"},
            current_spec=base_spec,
        )
    assert proposal is not None

    with pytest.raises(PrivilegeViolation) as excinfo:
        board.approve(
            proposal.proposal_id,
            operator="aurora",
            ledger_entry="ledger://amend/002",
        )
    violation = excinfo.value
    assert violation.report.issues

    stored = engine.load_proposal(proposal.proposal_id)
    assert stored is not None
    assert stored.status == "quarantined"
    amendment_log = _read_log(root / "amendment_log.jsonl")
    assert any(entry["event"] == "privilege-blocked" for entry in amendment_log)

def test_integrity_endpoint_reports_health(tmp_path: Path, base_spec: dict) -> None:
    clock = ManualClock()
    root = tmp_path / "integration"
    engine = SpecAmender(root=root, now=clock.now)

    # Trigger a standard proposal to mark a healthy pass
    for _ in range(3):
        engine.record_signal(
            base_spec["spec_id"],
            "coverage_gap",
            {"detail": "missing-case"},
            current_spec=base_spec,
        )

    status = engine.integrity_endpoint()
    assert status["daemon"] == "IntegrityDaemon"
    assert status["passed"] >= 1
    assert status["status"] in {"stable", "watch"}
