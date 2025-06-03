from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

LOG_PATH = get_log_path("resonite_creative_council.jsonl", "RESONITE_CREATIVE_COUNCIL_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_proposal(user: str, proposal: str, vote: str | None = None) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "proposal": proposal,
        "vote": vote,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def submit_proposal(user: str, text: str) -> None:
    require_admin_banner()
    entry = log_proposal(user, text)
    print(json.dumps(entry, indent=2))


def vote(user: str, proposal: str, decision: str) -> None:
    require_admin_banner()
    entry = log_proposal(user, proposal, decision)
    print(json.dumps(entry, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Creative council engine")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_submit = sub.add_parser("submit")
    p_submit.add_argument("user")
    p_submit.add_argument("text")
    p_vote = sub.add_parser("vote")
    p_vote.add_argument("user")
    p_vote.add_argument("proposal")
    p_vote.add_argument("decision", choices=["yes", "no", "abstain"])
    args = parser.parse_args()
    if args.cmd == "submit":
        submit_proposal(args.user, args.text)
    else:
        vote(args.user, args.proposal, args.decision)


if __name__ == "__main__":
    main()
