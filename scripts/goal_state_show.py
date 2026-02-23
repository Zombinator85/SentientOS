from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.goal_graph import load_goal_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Show goal state summary")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    state = load_goal_state(Path(args.repo_root).resolve())
    summary = {"active": 0, "blocked": 0, "completed": 0}
    for record in state.values():
        if record.status in summary:
            summary[record.status] += 1
    print(json.dumps({"summary": summary, "goals": {k: v.to_dict() for k, v in sorted(state.items())}}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
