from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
"""Ritual Avatar Conflict Drama Engine."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_conflict_drama.jsonl", "AVATAR_CONFLICT_DRAMA_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_conflict(parties: List[str], issue: str, resolution: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "parties": parties,
        "issue": issue,
        "resolution": resolution,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_conflicts() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def narrate(entry: Dict[str, str]) -> str:
    parties = " vs ".join(entry.get("parties", []))
    return (
        f"### Conflict: {parties}\n"
        f"**Issue:** {entry['issue']}\n\n"
        f"**Resolution:** {entry['resolution']}\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Conflict Drama Engine")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log a conflict")
    lg.add_argument("parties")
    lg.add_argument("issue")
    lg.add_argument("resolution")
    lg.set_defaults(func=lambda a: print(json.dumps(log_conflict([p.strip() for p in a.parties.split(',') if p.strip()], a.issue, a.resolution), indent=2)))

    ls = sub.add_parser("list", help="List conflicts")
    ls.set_defaults(func=lambda a: print(json.dumps(list_conflicts(), indent=2)))

    pl = sub.add_parser("play", help="Narrate latest conflict")
    pl.set_defaults(func=lambda a: print(narrate(list_conflicts()[-1])) if list_conflicts() else print("No conflicts logged"))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
