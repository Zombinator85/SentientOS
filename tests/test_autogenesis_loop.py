from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

import json

import pytest

from codex.amendments import AmendmentReviewBoard, IntegrityViolation, SpecAmender
from codex.autogenesis import GapScanner, LineageWriter, ReviewSymmetry, SelfAmender


class ManualClock:
    def __init__(self) -> None:
        self.moment = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        current = self.moment
        self.moment += timedelta(seconds=1)
        return current


def _read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture()
def base_spec() -> dict:
    return {
        "spec_id": "spec-autogenesis",
        "title": "Autogenesis Coverage",
        "objective": "Ensure telemetry gaps are surfaced.",
        "directives": ["Keep telemetry watchers online."],
        "testing_requirements": ["Replay telemetry gaps until resolved."],
        "version": "v1",
        "status": "active",
    }


@pytest.fixture()
def autogenesis_components(tmp_path: Path, base_spec: dict):
    clock = ManualClock()
    root = tmp_path / "integration"
    engine = SpecAmender(root=root, now=clock.now)
    board = AmendmentReviewBoard(engine)
    lineage = LineageWriter(engine, now=clock.now)
    review = ReviewSymmetry(root=root, board=board, now=clock.now)
    specs: Dict[str, dict] = {base_spec["spec_id"]: base_spec}
    self_amender = SelfAmender(engine, lineage_writer=lineage, review_symmetry=review)
    scanner = GapScanner(
        self_amender,
        spec_loader=lambda spec_id: specs[spec_id],
        now=clock.now,
    )
    return {
        "clock": clock,
        "engine": engine,
        "board": board,
        "lineage": lineage,
        "review": review,
        "scanner": scanner,
        "specs": specs,
        "root": root,
        "self_amender": self_amender,
    }


def test_gap_scanner_triggers_autogenesis(autogenesis_components: dict, base_spec: dict) -> None:
    scanner: GapScanner = autogenesis_components["scanner"]
    board: AmendmentReviewBoard = autogenesis_components["board"]
    root: Path = autogenesis_components["root"]

    context = None
    for idx in range(3):
        context = scanner.observe_log_failure(
            base_spec["spec_id"],
            message="runtime gap",
            detail=f"telemetry-miss-{idx}",
        )

    assert context is not None, "Recurring log failures should trigger autogenesis"
    proposal = context.proposal
    assert proposal.lineage is not None
    assert proposal.lineage["author"] == "sentientos.autogenesis"
    assert proposal.context["autogenesis"]["signal"] == "log_failure"

    board.approve(
        proposal.proposal_id,
        operator="aurora",
        ledger_entry="ledger://autogenesis/001",
    )

    dashboard_log = root / "dashboard" / "autogenesis_log.jsonl"
    entries = _read_log(dashboard_log)
    stages = {entry["stage"] for entry in entries}
    assert {"proposed", "adopted"}.issubset(stages)


def test_self_authored_amendment_still_hits_integrity(autogenesis_components: dict, base_spec: dict) -> None:
    self_amender: SelfAmender = autogenesis_components["self_amender"]

    hostile_spec = dict(base_spec)
    hostile_spec.pop("directives")
    hostile_spec["status"] = "reboot"

    with pytest.raises(IntegrityViolation):
        self_amender.submit_manual(
            base_spec["spec_id"],
            summary="Strip safeguards",
            deltas={"status": {"before": base_spec["status"], "after": "reboot"}},
            context={"reason": "attempted bypass"},
            original_spec={**base_spec, "lineage": {"seed": "v0"}},
            proposed_spec=hostile_spec,
        )


def test_lineage_marks_self_origin(autogenesis_components: dict, base_spec: dict) -> None:
    engine: SpecAmender = autogenesis_components["engine"]
    scanner: GapScanner = autogenesis_components["scanner"]
    specs: Dict[str, dict] = autogenesis_components["specs"]

    manual = engine.propose_manual(
        base_spec["spec_id"],
        summary="Operator tune",
        deltas={"objective": {"before": base_spec["objective"], "after": "Manual tune"}},
        context={"origin": "operator"},
        original_spec=base_spec,
        proposed_spec={**base_spec, "objective": "Manual tune"},
    )
    assert manual.lineage is None

    auto_spec = {**base_spec, "spec_id": "spec-autogenesis-tests"}
    specs[auto_spec["spec_id"]] = auto_spec

    context = None
    for _ in range(3):
        context = scanner.observe_test_failure(
            auto_spec["spec_id"],
            test_name="integration::pulse",
            failure_reason="pulse gap persists",
        )

    assert context is not None
    proposal = context.proposal
    assert proposal.lineage is not None
    assert proposal.lineage["author"] == "sentientos.autogenesis"
    assert proposal.context["autogenesis"]["channel"] == "tests"

