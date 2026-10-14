from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from sentientos.work_plan import (
    Task, TaskOmission, TaskRun, WorkPlan, WorkPlanError, WorkPlanRun, load_work_plan,
    load_work_run, persist_work_plan, persist_work_run,
)


def _plan() -> WorkPlan:
    return WorkPlan(1, "plan-1", "2026-01-01T00:00:00Z", "manual", ("goal-1",), (
        Task(1, "goal-1:diagnostic", "goal-1", "diagnostic",
            ("python -m scripts.contract_drift",), None, 1, 1, {}, (), False),
        Task(1, "goal-1:forge_apply", "goal-1", "forge_apply", (), None,
            1, 1, {"requires_mutation": True}, ("glow/forge",), True,
            ("goal-1:diagnostic",)),
    ))


def test_version_one_plan_round_trips_without_coercion(tmp_path: Path) -> None:
    plan = _plan()
    path = tmp_path / persist_work_plan(tmp_path, plan)

    assert load_work_plan(path) == plan


def test_legacy_version_one_plan_without_omissions_remains_readable(tmp_path: Path) -> None:
    payload = _plan().to_dict()
    payload.pop("omissions")
    for task in payload["tasks"]:
        task.pop("depends_on")
    path = tmp_path / "legacy-v1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    expected = replace(_plan(), tasks=tuple(replace(task, depends_on=())
        for task in _plan().tasks))

    assert load_work_plan(path) == expected


def test_planning_omissions_round_trip_as_non_executable_evidence(tmp_path: Path) -> None:
    plan = replace(_plan(), omissions=(
        TaskOmission("goal-1", "fetch", "task_kind_not_implemented"),))
    path = tmp_path / persist_work_plan(tmp_path, plan)

    assert load_work_plan(path) == plan


def test_malformed_planning_omission_rejects_plan(tmp_path: Path) -> None:
    payload = _plan().to_dict()
    payload["omissions"] = [{"goal_id": "goal-1", "kind": [],
        "reason": "task_kind_not_implemented"}]
    path = tmp_path / "malformed-omission.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorkPlanError, match="work_plan_omissions_invalid"):
        load_work_plan(path)


def test_missing_task_dependency_rejects_plan(tmp_path: Path) -> None:
    payload = _plan().to_dict()
    payload["tasks"][1]["depends_on"] = ["missing-task"]
    path = tmp_path / "missing-dependency.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorkPlanError, match="work_plan_task_dependencies_invalid"):
        load_work_plan(path)


def test_persisted_plan_identity_is_write_once(tmp_path: Path) -> None:
    plan = _plan()
    relative = persist_work_plan(tmp_path, plan)
    path = tmp_path / relative
    original = path.read_bytes()

    assert persist_work_plan(tmp_path, plan) == relative
    assert len((tmp_path / "pulse/work_plans.jsonl").read_text().splitlines()) == 1
    with pytest.raises(WorkPlanError, match="work_plan_artifact_identity_conflict"):
        persist_work_plan(tmp_path, replace(plan, context="changed"))
    assert path.read_bytes() == original


def test_persisted_run_identity_is_write_once(tmp_path: Path) -> None:
    run = WorkPlanRun(1, "run-1", "plan-1", "2026-01-01T00:00:00Z", "ok",
        "normal", False,
        (TaskRun("task-1", "goal-1", "diagnostic", "success", None,
            "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z", 1, (), False),), ())
    relative = persist_work_run(tmp_path, run)
    path = tmp_path / relative
    original = path.read_bytes()

    assert persist_work_run(tmp_path, run) == relative
    assert len((tmp_path / "pulse/work_runs.jsonl").read_text().splitlines()) == 1
    with pytest.raises(WorkPlanError, match="work_plan_artifact_identity_conflict"):
        persist_work_run(tmp_path, replace(run, status="failed"))
    assert path.read_bytes() == original


def test_existing_run_artifact_recovers_against_exact_plan(tmp_path: Path) -> None:
    plan = _plan()
    run = WorkPlanRun(1, "run_2026-01-01T00-00-00Z_plan-1", plan.plan_id,
        plan.created_at, "partial", "normal", False,
        (TaskRun("goal-1:diagnostic", "goal-1", "diagnostic", "success", None,
            "2026-01-01T00:00:01Z", "2026-01-01T00:00:02Z", 1000,
            ("glow/contracts/contract_status.json",), False),
         TaskRun("goal-1:forge_apply", "goal-1", "forge_apply", "skipped",
            "mutation_disallowed", "2026-01-01T00:00:02Z", "2026-01-01T00:00:02Z",
            0, (), True)), ("mutation_disallowed",))
    persist_work_run(tmp_path, run)

    assert load_work_run(tmp_path, plan, created_at=plan.created_at) == run


def test_existing_run_artifact_rejects_substituted_task_identity(tmp_path: Path) -> None:
    plan = _plan()
    run = WorkPlanRun(1, "run_2026-01-01T00-00-00Z_plan-1", plan.plan_id,
        plan.created_at, "partial", "normal", False,
        (TaskRun("goal-1:diagnostic", "goal-1", "diagnostic", "success", None,
            "2026-01-01T00:00:01Z", "2026-01-01T00:00:02Z", 1000, (), False),
         TaskRun("goal-1:forge_apply", "goal-1", "forge_apply", "skipped",
            "mutation_disallowed", "2026-01-01T00:00:02Z", "2026-01-01T00:00:02Z",
            0, (), True)), ("mutation_disallowed",))
    relative = persist_work_run(tmp_path, run)
    path = tmp_path / relative
    payload = json.loads(path.read_text())
    payload["task_runs"][0]["task_id"] = "substituted"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    with pytest.raises(WorkPlanError, match="work_run_task_identity_invalid"):
        load_work_run(tmp_path, plan, created_at=plan.created_at)


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
