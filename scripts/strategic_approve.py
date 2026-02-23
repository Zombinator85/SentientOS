from __future__ import annotations

import argparse
from pathlib import Path

from sentientos.strategic_adaptation import approve_proposal, apply_requires_stable, can_auto_apply


def main() -> int:
    parser = argparse.ArgumentParser(description="Approve/reject strategic adaptation proposal")
    parser.add_argument("proposal_path")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reject", action="store_true")
    parser.add_argument("--approved-by", default="manual")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    apply_allowed = args.apply and (args.approved_by == "manual" or can_auto_apply())
    proposal, change_id = approve_proposal(
        Path(args.repo_root),
        proposal_path=Path(args.proposal_path),
        approve=not args.reject,
        approved_by=args.approved_by,
        decision_notes=args.notes,
        apply=apply_allowed,
        enforce_stable=apply_requires_stable(),
    )
    print(f"proposal_id={proposal.proposal_id}")
    print(f"status={proposal.approval.status}")
    print(f"approved_by={proposal.approval.approved_by}")
    if args.apply and not apply_allowed:
        print("apply=blocked_by_policy")
    if change_id:
        print(f"change_id={change_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
