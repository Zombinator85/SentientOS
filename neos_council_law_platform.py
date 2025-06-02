from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
"""NeosVR Council Law Review & Voting Platform."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_council_law.jsonl", "NEOS_COUNCIL_LAW_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_action(action: str, law: str, user: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "law": law,
        "user": user,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_actions(term: str = "") -> List[Dict[str, str]]:
    acts = read_json(LOG_PATH)
    if term:
        acts = [a for a in acts if term in json.dumps(a)]
    return acts


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Council Law Platform")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log council action")
    lg.add_argument("action")
    lg.add_argument("law")
    lg.add_argument("--user", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_action(a.action, a.law, a.user), indent=2)))

    ls = sub.add_parser("list", help="List actions")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_actions(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
