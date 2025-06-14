from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import presence_ledger as pl

LOG_PATH = get_log_path("neos_presence_dashboard.jsonl", "NEOS_PRESENCE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def record_event(event: str, note: str = "") -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "event": event, "note": note}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Presence Pulse Dashboard")
    sub = ap.add_subparsers(dest="cmd")

    rec = sub.add_parser("record", help="Record presence event")
    rec.add_argument("event")
    rec.add_argument("--note", default="")
    rec.set_defaults(func=lambda a: print(json.dumps(record_event(a.event, a.note), indent=2)))

    led = sub.add_parser("ledger", help="Show recent privilege attempts")
    led.add_argument("--limit", type=int, default=5)
    led.set_defaults(func=lambda a: print(json.dumps(pl.recent_privilege_attempts(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
