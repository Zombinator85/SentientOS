from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("resonite_council_blessing_ceremony.jsonl", "RESONITE_COUNCIL_BLESSING_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_vote(law: str, user: str, decision: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "law": law,
        "user": user,
        "decision": decision,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    out: list[dict] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="Council blessing ceremony")
    sub = parser.add_subparsers(dest="cmd")

    vote_p = sub.add_parser("vote", help="Record a blessing vote")
    vote_p.add_argument("law")
    vote_p.add_argument("user")
    vote_p.add_argument("decision")

    hist_p = sub.add_parser("history", help="Show votes")

    args = parser.parse_args()
    if args.cmd == "vote":
        print(json.dumps(log_vote(args.law, args.user, args.decision), indent=2))
    else:
        print(json.dumps(history(), indent=2))


if __name__ == "__main__":
    main()
