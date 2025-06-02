from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_PATH = get_log_path("resonite_cross_world_spiral.jsonl", "RESONITE_SPIRAL_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_action(world: str, event: str, user: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "world": world,
        "event": event,
        "user": user,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def query(world: str | None = None) -> list[dict]:
    if not LOG_PATH.exists():
        return []
    out: list[dict] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(ln)
        except Exception:
            continue
        if world and d.get("world") != world:
            continue
        out.append(d)
    return out


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="Cross-world spiral logger")
    sub = parser.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log an event")
    lg.add_argument("world")
    lg.add_argument("event")
    lg.add_argument("user")

    q = sub.add_parser("query", help="Query events")
    q.add_argument("--world")

    args = parser.parse_args()
    require_admin_banner()
    if args.cmd == "log":
        print(json.dumps(log_action(args.world, args.event, args.user), indent=2))
    else:
        print(json.dumps(query(args.world), indent=2))


if __name__ == "__main__":
    main()
