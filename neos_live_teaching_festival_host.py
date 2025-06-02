from __future__ import annotations
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_live_festival_host.jsonl", "NEOS_LIVE_FESTIVAL_HOST_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_feedback(user: str, mood: str, note: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "mood": mood,
        "note": note,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def feedback_history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Live Teaching Festival Host")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log attendee feedback")
    lg.add_argument("user")
    lg.add_argument("mood")
    lg.add_argument("--note", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_feedback(a.user, a.mood, a.note), indent=2)))

    hist = sub.add_parser("history", help="Show feedback history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(feedback_history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
