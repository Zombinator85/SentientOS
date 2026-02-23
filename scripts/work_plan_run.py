from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.goal_executor import ExecutorState, GoalExecutor
from sentientos.integrity_quarantine import load_state as load_quarantine_state
from sentientos.risk_budget import compute_risk_budget
from sentientos.strategic_posture import resolve_posture
from sentientos.throughput_policy import derive_throughput_policy
from sentientos.work_plan import load_work_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute work plan file")
    parser.add_argument("plan_path")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    plan = load_work_plan(Path(args.plan_path).resolve())
    quarantine = load_quarantine_state(root)
    throughput = derive_throughput_policy(integrity_pressure_level=0, quarantine=quarantine)
    posture = resolve_posture()
    budget = compute_risk_budget(repo_root=root, posture=posture.posture, pressure_level=0, operating_mode=throughput.mode, quarantine_active=quarantine.active)
    state = ExecutorState(
        repo_root=root,
        created_at=plan.created_at,
        context=plan.context,
        operating_mode=throughput.mode,
        quarantine_active=quarantine.active,
        allow_mutation=(not quarantine.active) and budget.forge_max_files_changed > 0,
        goal_graph_hash="manual",
        allocation_id="manual",
        risk_budget=budget,
    )
    run = GoalExecutor(repo_root=root).execute_plan(plan, state)
    print(json.dumps(run.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
