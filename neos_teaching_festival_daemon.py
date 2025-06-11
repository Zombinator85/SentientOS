"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from log_utils import append_json, read_json
"""NeosVR In-World Autonomous Teaching Festival.

"""



LOG_PATH = get_log_path("neos_teaching_festival.jsonl", "NEOS_TEACHING_FESTIVAL_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_lesson(topic: str, mood: str = "", participant: str = "", feedback: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "topic": topic,
        "mood": mood,
        "participant": participant,
        "feedback": feedback,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_lessons(term: str = "") -> List[Dict[str, str]]:
    lessons = read_json(LOG_PATH)
    if term:
        lessons = [l for l in lessons if term in json.dumps(l)]
    return lessons


def run_daemon(interval: float) -> None:
    while True:
        log_lesson("heartbeat")
        time.sleep(interval)


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Teaching Festival Daemon")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log lesson")
    lg.add_argument("topic")
    lg.add_argument("--mood", default="")
    lg.add_argument("--participant", default="")
    lg.add_argument("--feedback", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_lesson(a.topic, a.mood, a.participant, a.feedback), indent=2)))

    ls = sub.add_parser("list", help="List lessons")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_lessons(a.term), indent=2)))

    rn = sub.add_parser("run", help="Run daemon")
    rn.add_argument("--interval", type=float, default=60.0)
    rn.set_defaults(func=lambda a: run_daemon(a.interval))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
