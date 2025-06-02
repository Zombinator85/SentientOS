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

LOG_PATH = get_log_path("neos_council_visualizer.jsonl", "NEOS_COUNCIL_VIS_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_event(event: str, mood: str = "") -> Dict[str, str]:
    """Record a council or festival event."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event,
        "mood": mood,
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
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Council & Festival Visualizer")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Record event")
    lg.add_argument("event")
    lg.add_argument("--mood", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_event(a.event, a.mood), indent=2)))

    hist = sub.add_parser("history", help="Show history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
