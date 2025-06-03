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

LOG_PATH = get_log_path("neos_cross_world_blessing.jsonl", "NEOS_CROSS_WORLD_BLESSING_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def record_blessing(world: str, avatar: str, artifact: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "world": world,
        "avatar": avatar,
        "artifact": artifact,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_blessings(filter_world: str = "") -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if filter_world and rec.get("world") != filter_world:
            continue
        out.append(rec)
    return out


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Cross-World Artifact/Avatar Blessing Tracker")
    sub = ap.add_subparsers(dest="cmd")

    rec = sub.add_parser("record", help="Record blessing")
    rec.add_argument("world")
    rec.add_argument("avatar")
    rec.add_argument("artifact")
    rec.set_defaults(func=lambda a: print(json.dumps(record_blessing(a.world, a.avatar, a.artifact), indent=2)))

    ls = sub.add_parser("list", help="List blessings")
    ls.add_argument("--world", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_blessings(a.world), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
