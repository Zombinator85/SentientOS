from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.goal_completion import CompletionContext, eval_check
from sentientos.goal_graph import load_goal_graph, load_goal_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Show goal state + completion check status")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    graph = load_goal_graph(root)
    state = load_goal_state(root)
    out: dict[str, object] = {"goals": []}
    for goal in graph.goals:
        record = state.get(goal.goal_id)
        ctx = CompletionContext(root, goal.goal_id, "normal", 0, "balanced", False, {})
        check = eval_check(goal.completion_check_name, ctx)
        out["goals"].append(
            {
                "goal_id": goal.goal_id,
                "state": record.to_dict() if record is not None else None,
                "completion_check": goal.completion_check_name,
                "completion": check.to_dict(),
            }
        )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
