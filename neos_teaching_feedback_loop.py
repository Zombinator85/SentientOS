from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_teaching_feedback.jsonl", "NEOS_TEACHING_FEEDBACK_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_feedback(session: str, user: str, score: float, comment: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "session": session,
        "user": user,
        "score": score,
        "comment": comment,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
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
    ap = argparse.ArgumentParser(description="NeosVR Teaching Performance Feedback Loop")
    sub = ap.add_subparsers(dest="cmd")

    fb = sub.add_parser("log", help="Log feedback")
    fb.add_argument("session")
    fb.add_argument("user")
    fb.add_argument("score", type=float)
    fb.add_argument("--comment", default="")
    fb.set_defaults(func=lambda a: print(json.dumps(log_feedback(a.session, a.user, a.score, a.comment), indent=2)))

    hist = sub.add_parser("history", help="Show feedback history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
