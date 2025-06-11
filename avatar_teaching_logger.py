from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Avatar Teaching Session Logger

Log ritual teaching sessions involving avatars.

Example:
    python avatar_teaching_logger.py log alice bob avatar1 "crown ritual" --mood joy
    python avatar_teaching_logger.py list
"""
from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_teaching.jsonl", "AVATAR_TEACH_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_session(teacher: str, learner: str, avatar: str, ritual: str, mood: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "teacher": teacher,
        "learner": learner,
        "avatar": avatar,
        "ritual": ritual,
        "mood": mood,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_sessions(term: str = "") -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if term and term not in line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar teaching logger")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Record a teaching session")
    lg.add_argument("teacher")
    lg.add_argument("learner")
    lg.add_argument("avatar")
    lg.add_argument("ritual")
    lg.add_argument("--mood", default="")
    lg.set_defaults(
        func=lambda a: print(
            json.dumps(
                log_session(a.teacher, a.learner, a.avatar, a.ritual, a.mood), indent=2
            )
        )
    )

    ls = sub.add_parser("list", help="List sessions")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_sessions(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
