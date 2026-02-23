from __future__ import annotations

import json
from pathlib import Path

from sentientos.goal_graph import Goal, GoalGraph, persist_goal_graph
from sentientos.orchestrator import OrchestratorConfig, tick


def test_tick_emits_completion_artifacts_and_index(tmp_path: Path) -> None:
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    persist_goal_graph(tmp_path, GoalGraph(schema_version=1, goals=(Goal("g1", "d", 1.0, 5, (), "check_forge_last_run_ok", 1, 1, ("integrity",), True),)))
    tick(tmp_path, config=OrchestratorConfig(True, 300, False, False, False, False, False))
    checks = list((tmp_path / "glow/forge/completion_checks").glob("check_*.json"))
    assert checks
    index = json.loads((tmp_path / "glow/forge/index.json").read_text(encoding="utf-8"))
    assert "last_completion_check_at" in index
    assert "goal_completion_summary" in index
