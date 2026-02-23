from __future__ import annotations

import json
from pathlib import Path

from sentientos.goal_graph import Goal, GoalGraph, persist_goal_graph
from sentientos.orchestrator import OrchestratorConfig, tick


def test_tick_emits_work_plan_and_run_and_index_fields(tmp_path: Path) -> None:
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    persist_goal_graph(
        tmp_path,
        GoalGraph(schema_version=1, goals=(Goal("g1", "d", 1.0, 5, (), "task:forge_propose", 1, 1, ("integrity",), True),)),
    )

    tick(tmp_path, config=OrchestratorConfig(True, 300, False, False, False, False, False))

    plans = list((tmp_path / "glow/forge/work_plans").glob("plan_*.json"))
    runs = list((tmp_path / "glow/forge/work_runs").glob("run_*.json"))
    assert plans
    assert runs

    index = json.loads((tmp_path / "glow/forge/index.json").read_text(encoding="utf-8"))
    assert index.get("last_work_plan_id")
    assert index.get("last_work_run_id")
    assert index.get("last_work_run_status") in {"ok", "partial", "failed", "skipped", "unknown"}
    assert isinstance(index.get("goal_state_summary"), dict)
