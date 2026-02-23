from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.goal_graph import load_goal_graph
from sentientos.integrity_pressure import compute_integrity_pressure
from sentientos.integrity_quarantine import load_state as load_quarantine_state
from sentientos.risk_budget import compute_risk_budget
from sentientos.strategic_posture import resolve_posture
from sentientos.throughput_policy import derive_throughput_policy
from sentientos.work_allocator import allocate_goals


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one-shot deterministic goal allocation")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    pressure = compute_integrity_pressure(root)
    quarantine = load_quarantine_state(root)
    posture = resolve_posture()
    throughput = derive_throughput_policy(integrity_pressure_level=pressure.level, quarantine=quarantine)
    budget = compute_risk_budget(
        repo_root=root,
        posture=posture.posture,
        pressure_level=pressure.level,
        operating_mode=throughput.mode,
        quarantine_active=quarantine.active,
    )
    graph = load_goal_graph(root)
    decision = allocate_goals(
        graph=graph,
        budget=budget,
        operating_mode=throughput.mode,
        integrity_pressure_level=pressure.level,
        quarantine_active=quarantine.active,
        posture=posture.posture,
    )
    print(
        json.dumps(
            {
                "selected_goals": list(decision.selected),
                "deferred_goals": [{"goal_id": item.goal_id, "reason": item.reason} for item in decision.deferred],
                "budget_summary": decision.budget_summary,
                "selection_reasons": list(decision.selected_reasons),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
