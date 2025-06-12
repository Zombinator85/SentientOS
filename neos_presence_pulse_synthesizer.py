"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from logging_config import get_log_path


"""NeosVR Autonomous Presence Pulse Synthesizer."""

import argparse
import json
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_presence_pulse.jsonl", "NEOS_PULSE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_pulse(value: float) -> Dict[str, float]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "value": value}
    append_json(LOG_PATH, entry)
    return entry


def list_pulses() -> List[Dict[str, float]]:
    return read_json(LOG_PATH)


def run_daemon(interval: float) -> None:
    while True:
        val = random.random()
        log_pulse(val)
        time.sleep(interval)


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Presence Pulse Synthesizer")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log pulse value")
    lg.add_argument("value", type=float)
    lg.set_defaults(func=lambda a: print(json.dumps(log_pulse(a.value), indent=2)))

    ls = sub.add_parser("list", help="List pulses")
    ls.set_defaults(func=lambda a: print(json.dumps(list_pulses(), indent=2)))

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
