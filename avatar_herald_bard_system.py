from __future__ import annotations
from logging_config import get_log_path

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Autonomous Avatar Herald/Bard System.

Logs ritual announcements, omens, and celebration poems.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_herald_events.jsonl", "AVATAR_HERALD_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_event(event_type: str, content: str, mood: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "type": event_type,
        "content": content,
        "mood": mood,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_events() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Herald/Bard System")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log a herald event")
    lg.add_argument("type")
    lg.add_argument("content")
    lg.add_argument("--mood", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_event(a.type, a.content, a.mood), indent=2)))

    ls = sub.add_parser("list", help="List events")
    ls.set_defaults(func=lambda a: print(json.dumps(list_events(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
