from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.goal_executor import ExecutorState, GoalExecutor
from sentientos.goal_graph import goal_graph_hash, load_goal_graph
from sentientos.integrity_quarantine import load_state as load_quarantine_state
from sentientos.risk_budget import compute_risk_budget
from sentientos.strategic_posture import resolve_posture
from sentientos.throughput_policy import derive_throughput_policy
from sentientos.work_allocator import allocate_goals


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic work plan from current goal allocation")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--context", default="manual")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    graph = load_goal_graph(root)
    graph_hash = goal_graph_hash(graph)
    quarantine = load_quarantine_state(root)
    throughput = derive_throughput_policy(integrity_pressure_level=0, quarantine=quarantine)
    posture = resolve_posture()
    budget = compute_risk_budget(repo_root=root, posture=posture.posture, pressure_level=0, operating_mode=throughput.mode, quarantine_active=quarantine.active)
    allocation = allocate_goals(graph=graph, budget=budget, operating_mode=throughput.mode, integrity_pressure_level=0, quarantine_active=quarantine.active, posture=posture.posture)

    state = ExecutorState(
        repo_root=root,
        created_at="1970-01-01T00:00:00Z",
        context=args.context,
        operating_mode=throughput.mode,
        quarantine_active=quarantine.active,
        allow_mutation=(not quarantine.active) and budget.forge_max_files_changed > 0,
        goal_graph_hash=graph_hash,
        allocation_id="manual_allocation",
        risk_budget=budget,
    )
    plan = GoalExecutor(repo_root=root).build_plan(allocation=allocation, state=state, graph=graph)
    print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
