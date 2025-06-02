from __future__ import annotations
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_desire_reflection.jsonl", "NEOS_DESIRE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_desire(agent: str, desire: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "agent": agent,
        "desire": desire,
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
        # Placeholder: real implementation would scan VR state
        time.sleep(interval)
        log_desire("auto", "reflection scan")


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Desire Reflection Loop")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Record a desire")
    lg.add_argument("agent")
    lg.add_argument("desire")
    lg.set_defaults(func=lambda a: print(json.dumps(log_desire(a.agent, a.desire), indent=2)))

    hist = sub.add_parser("history", help="Show desire history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    loop = sub.add_parser("loop", help="Run reflection loop")
    loop.add_argument("--interval", type=float, default=60.0)
    loop.set_defaults(func=lambda a: run_loop(a.interval))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
