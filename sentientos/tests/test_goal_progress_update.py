from __future__ import annotations

from pathlib import Path

from sentientos.artifact_catalog import append_catalog_entry
from sentientos.goal_executor import update_goal_state_from_run
from sentientos.goal_graph import Goal, GoalGraph
from sentientos.work_plan import TaskRun, WorkPlanRun


def _mk_run(status: str, reason: str | None = None) -> WorkPlanRun:
    return WorkPlanRun(
        schema_version=1,
        run_id="r1",
        plan_id="p1",
        created_at="2026-01-01T00:00:00Z",
        status=status,
        operating_mode="normal",
        quarantine_active=False,
        task_runs=(TaskRun("t1", "g1", "verify", status, reason, "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z", 1, (), False),),
        reason_stack=(),
    )


def test_progress_and_completion(tmp_path: Path) -> None:
    (tmp_path / "glow/forge/work_runs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/work_runs/run.json").write_text('{"status":"ok"}\n', encoding="utf-8")
    append_catalog_entry(tmp_path, kind="work_run", artifact_id="r1", relative_path="glow/forge/work_runs/run.json", schema_name="work_run", schema_version=1, links={"goal_id": "g1"}, summary={"status": "ok"})
    graph = GoalGraph(schema_version=1, goals=(Goal("g1", "d", 1.0, 1, (), "check_forge_last_run_ok", 1, 1, ("integrity",), True),))
    out = update_goal_state_from_run(graph, {}, _mk_run("success"), repo_root=tmp_path, operating_mode="normal", pressure_level=0, posture="balanced", quarantine_active=False, risk_budget_summary={})
    assert out["g1"].status == "completed"


def test_repeated_failure_blocks(tmp_path: Path) -> None:
    graph = GoalGraph(schema_version=1, goals=(Goal("g1", "d", 1.0, 1, (), "check_federation_ok", 1, 1, ("federation",), True),))
    first = update_goal_state_from_run(graph, {}, _mk_run("failed", "x"), repo_root=tmp_path, operating_mode="normal", pressure_level=0, posture="balanced", quarantine_active=False, risk_budget_summary={})
    second = update_goal_state_from_run(graph, first, _mk_run("failed", "x"), repo_root=tmp_path, operating_mode="normal", pressure_level=0, posture="balanced", quarantine_active=False, risk_budget_summary={})
    assert second["g1"].status == "blocked"
