from __future__ import annotations

import argparse
from pathlib import Path

from sentientos.strategic_adaptation import create_adjustment_proposal


def _string_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


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
    else:
        for item in proposal.adjustments:
            print(f"{item.goal_id}: {item.field} {item.old} -> {item.new} ({item.reason})")

    diff = proposal.allocation_diff
    added = [f"+{item}" for item in _string_items(diff.get("added_selected"))]
    removed = [f"-{item}" for item in _string_items(diff.get("removed_selected"))]
    print("allocation_diff:")
    print(f"  Would select: {' '.join(added) if added else 'none'} / drop: {' '.join(removed) if removed else 'none'}")

    raw_reordered = diff.get("reordered")
    reordered = raw_reordered if isinstance(raw_reordered, list) else []
    if not reordered:
        print("  Reorder: none")
    else:
        for entry in reordered[:5]:
            if not isinstance(entry, dict):
                continue
            goal_id = entry.get("goal_id")
            old_index = entry.get("old_index")
            new_index = entry.get("new_index")
            if (
                not isinstance(goal_id, str)
                or not isinstance(old_index, int)
                or isinstance(old_index, bool)
                or not isinstance(new_index, int)
                or isinstance(new_index, bool)
            ):
                continue
            print(f"  Reorder: {goal_id} {old_index}→{new_index}")

    budget_delta = diff.get("budget_delta") if isinstance(diff.get("budget_delta"), dict) else {}
    print(f"  Budget delta: {budget_delta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
