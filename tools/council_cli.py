from __future__ import annotations

import argparse
from datetime import datetime
from textwrap import dedent

from sentientos.council.governance_council import GovernanceCouncil


def submit_command(args: argparse.Namespace) -> None:
    council = GovernanceCouncil()
    proposal_id = args.proposal_id or f"proposal-{int(datetime.utcnow().timestamp())}"
    vote = council.submit_proposal(
        proposal_id=proposal_id,
        proposal_type=args.proposal_type,
        origin=args.origin,
        summary=args.summary,
        proposed_by=args.proposed_by,
    )
    vote = council.conduct_vote(vote)
    print(f"Proposal {vote.proposal_id} status: {vote.status}")
    print(f"Votes: {vote.votes}")


def status_command(args: argparse.Namespace) -> None:
    council = GovernanceCouncil()
    vote = council.load_vote(args.proposal_id)
    if not vote:
        print(f"No vote found for proposal_id={args.proposal_id}")
        return
    print(
        dedent(
            f"""
            Proposal ID: {vote.proposal_id}
            Type: {vote.proposal_type}
            Origin: {vote.origin}
            Summary: {vote.summary}
            Proposed By: {vote.proposed_by}
            Status: {vote.status}
            Votes: {vote.votes}
            Quorum Required: {vote.quorum_required}
            Timestamp: {vote.timestamp}
            """
        ).strip()
    )


def test_vote_command(args: argparse.Namespace) -> None:
    council = GovernanceCouncil()
    proposal_id = f"test-merge-{int(datetime.utcnow().timestamp())}"
    summary = "Symbolic term merge: sentinel -> guardian"
    vote = council.submit_proposal(
        proposal_id=proposal_id,
        proposal_type="symbol_approval",
        origin="council_cli",
        summary=summary,
        proposed_by=args.proposed_by,
    )
    vote = council.conduct_vote(vote)
    print(f"Test vote {proposal_id} completed with status {vote.status}")
    print(f"Votes: {vote.votes}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Governance Council CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    submit_parser = subparsers.add_parser("submit", help="Submit a new proposal to the council")
    submit_parser.add_argument("proposal_type", choices=sorted(GovernanceCouncil.SUPPORTED_TYPES))
    submit_parser.add_argument("origin", help="Originating subsystem or process")
    submit_parser.add_argument("summary", help="Proposal summary")
    submit_parser.add_argument("proposed_by", help="Agent proposing the change")
    submit_parser.add_argument("--proposal-id", help="Optional proposal identifier")
    submit_parser.set_defaults(func=submit_command)

    status_parser = subparsers.add_parser("status", help="Query the status of a proposal")
    status_parser.add_argument("proposal_id", help="Proposal identifier to query")
    status_parser.set_defaults(func=status_command)

    test_parser = subparsers.add_parser(
        "test-vote",
        help="Trigger a symbolic test vote for sentinel -> guardian terminology merge",
    )
    test_parser.add_argument("--proposed-by", default="council_cli", help="Agent invoking the test")
    test_parser.set_defaults(func=test_vote_command)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
