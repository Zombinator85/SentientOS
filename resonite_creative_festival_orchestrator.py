from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_PATH = get_log_path("resonite_creative_festival.jsonl", "RESONITE_CREATIVE_FESTIVAL_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_event(name: str, mood: str, user: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": name,
        "mood": mood,
        "user": user,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_events(term: str | None = None) -> list[dict]:
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
    parser = argparse.ArgumentParser(description="Resonite creative festival orchestrator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sched = sub.add_parser("schedule")
    p_sched.add_argument("event")
    p_sched.add_argument("mood")
    p_sched.add_argument("user")

    p_list = sub.add_parser("list")
    p_list.add_argument("--term")

    args = parser.parse_args()
    if args.cmd == "schedule":
        require_admin_banner()
        print(json.dumps(log_event(args.event, args.mood, args.user), indent=2))
    else:
        require_admin_banner()
        print(json.dumps(list_events(args.term), indent=2))


if __name__ == "__main__":
    main()
