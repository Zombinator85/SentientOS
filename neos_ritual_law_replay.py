from __future__ import annotations
from logging_config import get_log_path

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""NeosVR Ritual Law Replay/Teaching Engine."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_ritual_law_replay.jsonl", "NEOS_RITUAL_LAW_REPLAY_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_replay(topic: str, note: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "topic": topic,
        "note": note,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_replays(term: str = "") -> List[Dict[str, str]]:
    rp = read_json(LOG_PATH)
    if term:
        rp = [r for r in rp if term in json.dumps(r)]
    return rp


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Ritual Law Replay")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log replay topic")
    lg.add_argument("topic")
    lg.add_argument("--note", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_replay(a.topic, a.note), indent=2)))

    ls = sub.add_parser("list", help="List replays")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_replays(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
