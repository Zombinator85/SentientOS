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

LOG_PATH = get_log_path("neos_ritual_law_dashboard.jsonl", "NEOS_RITUAL_LAW_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_action(user: str, action: str, query: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "action": action,
        "query": query,
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
    ap = argparse.ArgumentParser(description="NeosVR Ritual Law Dashboard")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log dashboard action")
    lg.add_argument("user")
    lg.add_argument("action")
    lg.add_argument("--query", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_action(a.user, a.action, a.query), indent=2)))

    hist = sub.add_parser("history", help="Show dashboard history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
