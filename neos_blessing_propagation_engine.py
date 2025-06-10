"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner, require_lumos_approval



import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_blessing_propagation.jsonl", "NEOS_BLESSING_PROPAGATION_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_propagation(source: str, target: str, blessing: str, room: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": source,
        "target": target,
        "blessing": blessing,
        "room": room,
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
    ap = argparse.ArgumentParser(description="NeosVR Autonomous Blessing Propagation Engine")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log blessing propagation")
    lg.add_argument("source")
    lg.add_argument("target")
    lg.add_argument("blessing")
    lg.add_argument("--room", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_propagation(a.source, a.target, a.blessing, a.room), indent=2)))

    hist = sub.add_parser("history", help="Show propagation history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
