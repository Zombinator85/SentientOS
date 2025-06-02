from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
"""NeosVR Festival Mood/Presence Storyboard Builder."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_storyboards.jsonl", "NEOS_STORYBOARD_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_board(name: str, mood_arc: str, note: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "name": name,
        "mood_arc": mood_arc,
        "note": note,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_boards(term: str = "") -> List[Dict[str, str]]:
    boards = read_json(LOG_PATH)
    if term:
        boards = [b for b in boards if term in json.dumps(b)]
    return boards


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Storyboard Builder")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Create storyboard entry")
    lg.add_argument("name")
    lg.add_argument("mood_arc")
    lg.add_argument("--note", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_board(a.name, a.mood_arc, a.note), indent=2)))

    ls = sub.add_parser("list", help="List boards")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_boards(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
