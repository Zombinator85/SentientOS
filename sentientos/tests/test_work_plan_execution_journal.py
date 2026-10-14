from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.work_plan import Task, WorkPlan
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
