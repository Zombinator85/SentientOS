from __future__ import annotations

import argparse
from pathlib import Path

from sentientos.goal_graph import load_goal_graph
from sentientos.strategic_adaptation import _allocation_diff, _allocation_summary, _compute_allocation_for_snapshot, _load_proposal, apply_adjustments_to_goal_graph


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay strategic proposal counterfactual allocation deterministically")
    parser.add_argument("proposal_path")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    proposal = _load_proposal(Path(args.proposal_path))
    graph = load_goal_graph(root)
    current = _compute_allocation_for_snapshot(graph=graph, snapshot=proposal.allocator_inputs_snapshot)
    proposed_graph = apply_adjustments_to_goal_graph(graph, proposal.adjustments)
    proposed = _compute_allocation_for_snapshot(graph=proposed_graph, snapshot=proposal.allocator_inputs_snapshot)

    print(f"proposal_id={proposal.proposal_id}")
    print(f"current={_allocation_summary(current)}")
    print(f"proposed={_allocation_summary(proposed)}")
    print(f"allocation_diff={_allocation_diff(current, proposed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
