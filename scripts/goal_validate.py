from __future__ import annotations

import argparse
from pathlib import Path

from sentientos.goal_graph import detect_dependency_cycles, load_goal_graph, order_goals_deterministic


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate goal graph determinism and dependency structure")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    graph = load_goal_graph(Path(args.repo_root))
    cycles = detect_dependency_cycles(graph)
    if cycles:
        print(f"cycles_detected={cycles}")
        return 1

    ordered_ids = [goal.goal_id for goal in order_goals_deterministic(graph.goals)]
    print(f"ok goals={len(graph.goals)} ordered_goal_ids={ordered_ids}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
