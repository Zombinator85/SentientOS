from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

LOG_PATH = get_log_path("resonite_teaching_ritual_spiral.jsonl", "RESONITE_TEACHING_RITUAL_SPIRAL_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_session(teacher: str, learner: str, lesson: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "teacher": teacher,
        "learner": learner,
        "lesson": lesson,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_sessions(term: str | None = None) -> list[dict]:
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
    parser = argparse.ArgumentParser(description="Resonite teaching ritual spiral engine")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_log = sub.add_parser("log")
    p_log.add_argument("teacher")
    p_log.add_argument("learner")
    p_log.add_argument("lesson")

    p_list = sub.add_parser("list")
    p_list.add_argument("--term")

    args = parser.parse_args()
    if args.cmd == "log":
        require_admin_banner()
        print(json.dumps(log_session(args.teacher, args.learner, args.lesson), indent=2))
    else:
        require_admin_banner()
        print(json.dumps(list_sessions(args.term), indent=2))


if __name__ == "__main__":
    main()
