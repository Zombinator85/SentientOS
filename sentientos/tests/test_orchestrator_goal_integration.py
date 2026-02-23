from __future__ import annotations

import json
from pathlib import Path

from sentientos.orchestrator import OrchestratorConfig, tick


def _seed_repo(root: Path) -> None:
    (root / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (root / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    (root / "glow/forge/goals").mkdir(parents=True, exist_ok=True)
    (root / "glow/forge/goals/goal_graph.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "goals": [
                    {
                        "goal_id": "integrity_repair",
                        "description": "repair",
                        "weight": 1.0,
                        "priority": 2,
                        "dependencies": [],
                        "completion_check": "rule:repair",
                        "risk_cost_estimate": 1,
                        "throughput_cost_estimate": 1,
                        "tags": ["integrity"],
                        "enabled": True,
                    },
                    {
                        "goal_id": "feature_ship",
                        "description": "ship",
                        "weight": 5.0,
                        "priority": 5,
                        "dependencies": [],
                        "completion_check": "rule:ship",
                        "risk_cost_estimate": 5,
                        "throughput_cost_estimate": 1,
                        "tags": ["feature"],
                        "enabled": True,
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_tick_emits_goal_allocation_artifact_and_trace(tmp_path: Path) -> None:
    _seed_repo(tmp_path)

    result = tick(tmp_path, config=OrchestratorConfig(True, 300, False, False, False, False, False))
    report = json.loads((tmp_path / result.tick_report_path).read_text(encoding="utf-8"))
    allocation = report.get("goal_allocation")
    assert isinstance(allocation, dict)
    allocation_path = allocation.get("artifact_path")
    assert isinstance(allocation_path, str)
    assert (tmp_path / allocation_path).exists()

    rows = [json.loads(line) for line in (tmp_path / "pulse/goal_allocations.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows
    assert rows[-1]["allocation_path"] == allocation_path

    trace_id = report["trace"]["trace_id"]
    assert isinstance(trace_id, str)
    trace_payload = json.loads((tmp_path / f"glow/forge/traces/{trace_id}.json").read_text(encoding="utf-8"))
    clamps = trace_payload.get("clamps_applied")
    assert isinstance(clamps, list)
    assert any(item.get("name") == "goal_allocation" for item in clamps if isinstance(item, dict))

    index_payload = json.loads((tmp_path / "glow/forge/index.json").read_text(encoding="utf-8"))
    assert index_payload["goal_allocation_status"] == "ok"
    assert index_payload["last_goal_allocation_id"] == allocation_path
    assert isinstance(index_payload["last_selected_goals"], list)
    assert isinstance(index_payload["last_deferred_goal_count"], int)
    assert isinstance(index_payload["goal_graph_hash"], str)
