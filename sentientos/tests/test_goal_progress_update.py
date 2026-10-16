from __future__ import annotations

import json
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
    # A successful task run cannot complete a goal without a matching
    # persisted run and canonical plan evidence digest.
    assert out["g1"].status == "active"
    assert out["g1"].progress < 1.0
    assert "run_evidence_binding_missing" in (out["g1"].blocked_reason or "")


def test_repeated_failure_blocks(tmp_path: Path) -> None:
    graph = GoalGraph(schema_version=1, goals=(Goal("g1", "d", 1.0, 1, (), "check_federation_ok", 1, 1, ("federation",), True),))
    first = update_goal_state_from_run(graph, {}, _mk_run("failed", "x"), repo_root=tmp_path, operating_mode="normal", pressure_level=0, posture="balanced", quarantine_active=False, risk_budget_summary={})
    second = update_goal_state_from_run(graph, first, _mk_run("failed", "x"), repo_root=tmp_path, operating_mode="normal", pressure_level=0, posture="balanced", quarantine_active=False, risk_budget_summary={})
    assert second["g1"].status == "blocked"


def test_persisted_evidence_bound_run_completes_goal(tmp_path: Path) -> None:
    from sentientos.artifact_catalog import append_catalog_entry

    plan_digest = "b" * 64
    evidence_digest = "a" * 64
    run_id = f"run_{plan_digest}"
    run = WorkPlanRun(
        schema_version=3, run_id=run_id, plan_id="p-bound",
        created_at="2026-10-16T00:00:00Z", status="ok",
        operating_mode="normal", quarantine_active=False,
        task_runs=(TaskRun("t1", "g1", "verify", "success", None,
            "2026-10-16T00:00:00Z", "2026-10-16T00:00:01Z", 1, (), False),),
        reason_stack=(), plan_digest=plan_digest,
        evidence_digest=evidence_digest,
    )
    rel = f"glow/forge/work_runs/{run_id}.json"
    path = tmp_path / rel
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(run.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_catalog_entry(tmp_path, kind="work_run", artifact_id=run_id,
        relative_path=rel, schema_name="", schema_version=3,
        links={"work_run_id": run_id, "goal_ids": ["g1"]},
        summary={"status": "ok"})
    graph = GoalGraph(schema_version=1, goals=(Goal("g1", "d", 1.0, 1, (),
        "check_forge_last_run_ok", 1, 1, ("integrity",), True),))

    out = update_goal_state_from_run(graph, {}, run, repo_root=tmp_path,
        operating_mode="normal", pressure_level=0, posture="balanced",
        quarantine_active=False, risk_budget_summary={})

    assert out["g1"].status == "completed"
    completion_path = next((tmp_path / "glow/forge/completion_checks").glob("*.json"))
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    assert completion["schema_version"] == 2
    assert completion["evidence_digest"] == evidence_digest
