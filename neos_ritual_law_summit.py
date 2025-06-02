from __future__ import annotations
from logging_config import get_log_path

"""NeosVR Recurring Ritual Law Summit."""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_ritual_law_summit.jsonl", "NEOS_LAW_SUMMIT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_agenda(item: str, outcome: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "item": item,
        "outcome": outcome,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_agendas(term: str = "") -> List[Dict[str, str]]:
    ag = read_json(LOG_PATH)
    if term:
        ag = [a for a in ag if term in json.dumps(a)]
    return ag


def run_daemon(interval: float) -> None:
    while True:
        log_agenda("heartbeat")
        time.sleep(interval)


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Ritual Law Summit")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log agenda item")
    lg.add_argument("item")
    lg.add_argument("--outcome", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_agenda(a.item, a.outcome), indent=2)))

    ls = sub.add_parser("list", help="List agenda items")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_agendas(a.term), indent=2)))

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
