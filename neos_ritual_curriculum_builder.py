from __future__ import annotations
from logging_config import get_log_path

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""NeosVR Autonomous Ritual Curriculum Builder."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_ritual_curriculum.jsonl", "NEOS_CURRICULUM_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_curriculum(title: str, adaptation: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "title": title,
        "adaptation": adaptation,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_curricula(term: str = "") -> List[Dict[str, str]]:
    cur = read_json(LOG_PATH)
    if term:
        cur = [c for c in cur if term in json.dumps(c)]
    return cur


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Ritual Curriculum Builder")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log curriculum entry")
    lg.add_argument("title")
    lg.add_argument("--adaptation", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_curriculum(a.title, a.adaptation), indent=2)))

    ls = sub.add_parser("list", help="List curricula")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_curricula(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
