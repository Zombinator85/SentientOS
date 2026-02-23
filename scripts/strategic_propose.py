from __future__ import annotations

import argparse
from pathlib import Path

from sentientos.strategic_adaptation import create_adjustment_proposal


def main() -> int:
    parser = argparse.ArgumentParser(description="Create deterministic strategic adaptation proposal")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--window", default="last_24h", choices=["last_24h", "last_7d"])
    args = parser.parse_args()

    proposal, path = create_adjustment_proposal(Path(args.repo_root), window_name=args.window)
    print(f"proposal_path={path}")
    print(f"proposal_id={proposal.proposal_id}")
    if not proposal.adjustments:
        print("adjustments=none")
        return 0
    for item in proposal.adjustments:
        print(f"{item.goal_id}: {item.field} {item.old} -> {item.new} ({item.reason})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
