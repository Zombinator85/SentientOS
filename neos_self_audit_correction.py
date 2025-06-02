from __future__ import annotations
from logging_config import get_log_path

"""NeosVR Self-Audit & Memory Correction Ritual."""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_self_audit.jsonl", "NEOS_SELF_AUDIT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_correction(issue: str, fix: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "issue": issue,
        "fix": fix,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_corrections() -> List[Dict[str, str]]:
    return read_json(LOG_PATH)


def run_daemon(interval: float) -> None:
    while True:
        log_correction("heartbeat", "none")
        time.sleep(interval)


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Self Audit Correction")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log correction")
    lg.add_argument("issue")
    lg.add_argument("fix")
    lg.set_defaults(func=lambda a: print(json.dumps(log_correction(a.issue, a.fix), indent=2)))

    ls = sub.add_parser("list", help="List corrections")
    ls.set_defaults(func=lambda a: print(json.dumps(list_corrections(), indent=2)))

    rn = sub.add_parser("run", help="Run daemon")
    rn.add_argument("--interval", type=float, default=60.0)
    rn.set_defaults(func=lambda a: run_daemon(a.interval))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
