from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.work_plan import (
    Task, WorkPlan, WorkPlanError, load_work_plan, persist_work_plan,
)


def _plan() -> WorkPlan:
    return WorkPlan(1, "plan-1", "2026-01-01T00:00:00Z", "manual", ("goal-1",), (
        Task(1, "goal-1:diagnostic", "goal-1", "diagnostic",
            ("python -m scripts.contract_drift",), None, 1, 1, {}, (), False),
        Task(1, "goal-1:forge_apply", "goal-1", "forge_apply", (), None,
            1, 1, {"requires_mutation": True}, ("glow/forge",), True),
    ))


def test_version_one_plan_round_trips_without_coercion(tmp_path: Path) -> None:
    plan = _plan()
    path = tmp_path / persist_work_plan(tmp_path, plan)

    assert load_work_plan(path) == plan


def test_malformed_task_row_rejects_whole_plan(tmp_path: Path) -> None:
    payload = _plan().to_dict()
    payload["tasks"].append("not-a-task")
    path = tmp_path / "malformed.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorkPlanError, match="work_plan_task_invalid"):
        load_work_plan(path)


def test_destructive_task_identity_cannot_be_reclassified(tmp_path: Path) -> None:
    payload = _plan().to_dict()
    payload["tasks"][1]["destructive"] = False
    path = tmp_path / "reclassified.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorkPlanError, match="work_plan_destructive_classification_mismatch"):
        load_work_plan(path)


@pytest.mark.parametrize("bad_value", [True, "1", 2])
def test_plan_version_is_not_coerced(tmp_path: Path, bad_value: object) -> None:
    payload = _plan().to_dict()
    payload["schema_version"] = bad_value
    path = tmp_path / "invalid-version.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorkPlanError, match="work_plan_shape_invalid"):
        load_work_plan(path)
