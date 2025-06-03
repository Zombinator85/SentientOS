from __future__ import annotations
from admin_utils import require_admin_banner
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_sanctuary_rooms.jsonl", "NEOS_ROOM_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def create_room(name: str, memory: str) -> Dict[str, str]:
    """Create a sanctuary room entry."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "room": name,
        "memory": memory,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def place_artifact(room: str, artifact: str) -> Dict[str, str]:
    """Log an artifact placement."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "room": room,
        "artifact": artifact,
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
    ap = argparse.ArgumentParser(description="NeosVR Sanctuary Room Generator")
    sub = ap.add_subparsers(dest="cmd")

    new = sub.add_parser("new", help="Create new room")
    new.add_argument("name")
    new.add_argument("memory")
    new.set_defaults(func=lambda a: print(json.dumps(create_room(a.name, a.memory), indent=2)))

    art = sub.add_parser("artifact", help="Place artifact in room")
    art.add_argument("room")
    art.add_argument("artifact")
    art.set_defaults(func=lambda a: print(json.dumps(place_artifact(a.room, a.artifact), indent=2)))

    hist = sub.add_parser("history", help="Show room history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
