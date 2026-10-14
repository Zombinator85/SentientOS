from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from sentientos.work_plan import Task, TaskRun, WorkPlan
from sentientos.work_plan_execution_journal import (
    WorkPlanExecutionJournal, WorkPlanJournalError,
)


def _plan() -> WorkPlan:
    return WorkPlan(1, "journal-plan", "2026-01-01T00:00:00Z", "manual", ("g1",), (
        Task(1, "g1:propose", "g1", "forge_propose", (), None, 0, 0, {}, (), False),))


def test_journal_binds_task_events_to_exact_plan_identity(tmp_path: Path) -> None:
    plan = _plan()
    journal = WorkPlanExecutionJournal(tmp_path, plan)
    journal.start("g1:propose")

    changed = WorkPlan(1, plan.plan_id, plan.created_at, plan.context, plan.selected_goals,
        (Task(1, "g1:other", "g1", "forge_propose", (), None, 0, 0, {}, (), False),))
    with pytest.raises(WorkPlanJournalError, match="work_plan_journal_record_invalid"):
        WorkPlanExecutionJournal(tmp_path, changed)


def test_corrupted_journal_digest_fails_closed(tmp_path: Path) -> None:
    journal = WorkPlanExecutionJournal(tmp_path, _plan())
    journal.start("g1:propose")
    row = json.loads(journal.path.read_text(encoding="utf-8"))
    row["recorded_at"] = "2026-01-02T00:00:00Z"
    journal.path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(WorkPlanJournalError, match="work_plan_journal_digest_mismatch"):
        WorkPlanExecutionJournal(tmp_path, _plan())


def test_terminal_task_result_is_recovered_with_original_artifacts_and_times(tmp_path: Path) -> None:
    plan = _plan()
    result = TaskRun("g1:propose", "g1", "forge_propose", "success", None,
        "2026-01-01T00:00:01Z", "2026-01-01T00:00:02Z", 1000,
        ("glow/forge/plan.json",), False)
    journal = WorkPlanExecutionJournal(tmp_path, plan)
    journal.start("g1:propose")
    journal.finish("g1:propose", status="success", reason=None, result=result)

    recovered = WorkPlanExecutionJournal(tmp_path, plan)

    assert recovered.state("g1:propose") == "success"
    assert recovered.result("g1:propose") == result
    rows = [json.loads(line) for line in journal.path.read_text().splitlines()]
    assert all(row["schema_version"] == 2 for row in rows)
    assert rows[-1]["task_result"]["artifacts"] == ["glow/forge/plan.json"]


def test_legacy_v1_started_journal_remains_explicitly_unknown(tmp_path: Path) -> None:
    plan = _plan()
    journal = WorkPlanExecutionJournal(tmp_path, plan)
    semantic = {"schema_version": 1, "sequence": 1, "plan_id": plan.plan_id,
        "plan_digest": journal.plan_digest, "task_id": "g1:propose", "event": "started",
        "status": None, "reason": None, "recorded_at": "2026-01-01T00:00:01Z",
        "previous_digest": "0" * 64}
    digest = hashlib.sha256(json.dumps(semantic, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    journal.path.parent.mkdir(parents=True, exist_ok=True)
    journal.path.write_text(json.dumps({**semantic, "digest": digest}, sort_keys=True,
        separators=(",", ":")) + "\n")

    recovered = WorkPlanExecutionJournal(tmp_path, plan)

    assert recovered.state("g1:propose") == "interrupted"
    assert recovered.result("g1:propose") is None
