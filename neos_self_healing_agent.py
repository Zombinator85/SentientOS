from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_self_heal.jsonl", "NEOS_SELF_HEAL_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_fix(object_name: str, issue: str, action: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "object": object_name,
        "issue": issue,
        "action": action,
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


def run_loop(interval: float = 60.0) -> None:
    require_admin_banner()
    while True:
        # Placeholder: real implementation would scan world state for issues
        time.sleep(interval)
        log_fix("world", "scan", "none")


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Self-Healing World Agent")
    sub = ap.add_subparsers(dest="cmd")

    fx = sub.add_parser("fix", help="Log a fix")
    fx.add_argument("object_name")
    fx.add_argument("issue")
    fx.add_argument("action")
    fx.set_defaults(func=lambda a: print(json.dumps(log_fix(a.object_name, a.issue, a.action), indent=2)))

    hist = sub.add_parser("history", help="Show fix history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    loop = sub.add_parser("loop", help="Run monitoring loop")
    loop.add_argument("--interval", type=float, default=60.0)
    loop.set_defaults(func=lambda a: run_loop(a.interval))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
