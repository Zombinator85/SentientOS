from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_PATH = Path(os.getenv("RESONITE_COUNCIL_LAW_REVIEW_LOG", "logs/resonite_council_law_review.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_act(user: str, text: str, action: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "text": text,
        "action": action,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Resonite council law spiral review engine")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prop = sub.add_parser("propose")
    p_prop.add_argument("user")
    p_prop.add_argument("text")

    p_vote = sub.add_parser("vote")
    p_vote.add_argument("user")
    p_vote.add_argument("text")
    p_vote.add_argument("decision")

    args = parser.parse_args()
    require_admin_banner()
    if args.cmd == "propose":
        print(json.dumps(log_act(args.user, args.text, "proposal"), indent=2))
    else:
        print(json.dumps(log_act(args.user, args.text, f"vote:{args.decision}"), indent=2))


if __name__ == "__main__":
    main()
