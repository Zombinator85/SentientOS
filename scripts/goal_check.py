from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.goal_completion import CompletionContext, eval_check
from sentientos.goal_graph import load_goal_graph


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic completion check for a goal")
    parser.add_argument("goal_id")
    parser.add_argument("--check", default=None)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    graph = load_goal_graph(root)
    goal = next((g for g in graph.goals if g.goal_id == args.goal_id), None)
    if goal is None:
        print(json.dumps({"error": "goal_not_found", "goal_id": args.goal_id}, sort_keys=True))
        return 2
    check_name = str(args.check or goal.completion_check_name)
    ctx = CompletionContext(
        repo_root=root,
        goal_id=goal.goal_id,
        operating_mode="normal",
        pressure_level=0,
        posture="balanced",
        quarantine_active=False,
        risk_budget_summary={},
    )
    result = eval_check(check_name, ctx)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
