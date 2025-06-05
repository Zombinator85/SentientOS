from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""NeosVR Cross-World Avatar Provenance Dashboard."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_avatar_provenance.jsonl", "NEOS_AVATAR_PROVENANCE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_query(avatar: str, note: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "note": note,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_queries(term: str = "") -> List[Dict[str, str]]:
    q = read_json(LOG_PATH)
    if term:
        q = [e for e in q if term in json.dumps(e)]
    return q


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Avatar Provenance Dashboard")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log provenance query")
    lg.add_argument("avatar")
    lg.add_argument("--note", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_query(a.avatar, a.note), indent=2)))

    ls = sub.add_parser("list", help="List queries")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_queries(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
