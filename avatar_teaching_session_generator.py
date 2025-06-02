from __future__ import annotations
from logging_config import get_log_path

"""Avatar-Driven Teaching Session Generator."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_teaching_sessions.jsonl", "AVATAR_TEACHING_SESSION_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def plan_session(avatar: str, ritual: str, lesson: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "ritual": ritual,
        "lesson": lesson,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_sessions() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def latest_lesson() -> str:
    sessions = list_sessions()
    if not sessions:
        return "No sessions logged"
    s = sessions[-1]
    return f"Avatar {s['avatar']} teaches {s['ritual']}: {s['lesson']}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Teaching Session Generator")
    sub = ap.add_subparsers(dest="cmd")

    pl = sub.add_parser("plan", help="Plan a teaching session")
    pl.add_argument("avatar")
    pl.add_argument("ritual")
    pl.add_argument("lesson")
    pl.set_defaults(func=lambda a: print(json.dumps(plan_session(a.avatar, a.ritual, a.lesson), indent=2)))

    ls = sub.add_parser("list", help="List sessions")
    ls.set_defaults(func=lambda a: print(json.dumps(list_sessions(), indent=2)))

    tm = sub.add_parser("teachme", help="Show latest lesson")
    tm.set_defaults(func=lambda a: print(latest_lesson()))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
