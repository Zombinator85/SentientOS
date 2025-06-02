from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
"""Avatar Emotion-Adaptive Animation Engine."""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict

LOG_PATH = get_log_path("avatar_animation.jsonl", "AVATAR_ANIMATION_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def record_change(avatar: str, mood: str, reaction: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "mood": mood,
        "reaction": reaction,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def run_daemon(avatar: str, mood: str, interval: float) -> None:
    while True:
        record_change(avatar, mood, "adaptive update")
        time.sleep(interval)


def main() -> None:
    ap = argparse.ArgumentParser(description="Emotion-Adaptive Animation Engine")
    sub = ap.add_subparsers(dest="cmd")

    rc = sub.add_parser("record", help="Record an animation change")
    rc.add_argument("avatar")
    rc.add_argument("mood")
    rc.add_argument("reaction")
    rc.set_defaults(func=lambda a: print(json.dumps(record_change(a.avatar, a.mood, a.reaction), indent=2)))

    dn = sub.add_parser("daemon", help="Run adaptive daemon")
    dn.add_argument("avatar")
    dn.add_argument("mood")
    dn.add_argument("--interval", type=float, default=60.0)
    dn.set_defaults(func=lambda a: run_daemon(a.avatar, a.mood, a.interval))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
