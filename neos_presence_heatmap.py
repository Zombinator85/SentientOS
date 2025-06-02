from __future__ import annotations
from logging_config import get_log_path

"""NeosVR Live Ritual Presence Heatmap."""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_presence_heatmap.jsonl", "NEOS_PRESENCE_HEATMAP_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_point(location: str, intensity: float) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "location": location,
        "intensity": intensity,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_points() -> List[Dict[str, str]]:
    return read_json(LOG_PATH)


def run_daemon(interval: float) -> None:
    i = 0.0
    while True:
        log_point("heartbeat", i)
        i += 1.0
        time.sleep(interval)


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Presence Heatmap")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log heatmap point")
    lg.add_argument("location")
    lg.add_argument("intensity", type=float)
    lg.set_defaults(func=lambda a: print(json.dumps(log_point(a.location, a.intensity), indent=2)))

    ls = sub.add_parser("list", help="List points")
    ls.set_defaults(func=lambda a: print(json.dumps(list_points(), indent=2)))

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
