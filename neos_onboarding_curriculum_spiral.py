from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_curriculum_spiral.jsonl", "NEOS_CURRICULUM_SPIRAL_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_lesson(user: str, lesson: str, note: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "lesson": lesson,
        "note": note,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_lessons(user: str = "") -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if user and rec.get("user") != user:
            continue
        out.append(rec)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Onboarding Curriculum Spiral")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log lesson completion")
    lg.add_argument("user")
    lg.add_argument("lesson")
    lg.add_argument("--note", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_lesson(a.user, a.lesson, a.note), indent=2)))

    ls = sub.add_parser("list", help="List lessons")
    ls.add_argument("--user", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_lessons(a.user), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
