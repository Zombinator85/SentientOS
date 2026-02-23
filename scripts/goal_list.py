from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.goal_graph import load_goal_graph


def main() -> int:
    parser = argparse.ArgumentParser(description="List goals from deterministic goal graph")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    graph = load_goal_graph(Path(args.repo_root))
    if args.as_json:
        print(json.dumps(graph.to_dict(), indent=2, sort_keys=True))
        return 0

    for goal in graph.goals:
        print(f"{goal.goal_id}\tpriority={goal.priority}\tweight={goal.weight}\tenabled={goal.enabled}\ttags={','.join(goal.tags)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
