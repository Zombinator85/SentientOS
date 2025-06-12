"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Emergency Rites & Safe-State Protocol

"""
from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path


LOG_PATH = get_log_path("emergency_log.jsonl", "EMERGENCY_LOG")
STATE_FILE = Path(os.getenv("EMERGENCY_STATE", "state/emergency.lock"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def halt(reason: str) -> dict:
    STATE_FILE.write_text("halted")
    entry = {"timestamp": datetime.utcnow().isoformat(), "event": "halt", "reason": reason}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def restore() -> dict:
    STATE_FILE.unlink(missing_ok=True)
    entry = {"timestamp": datetime.utcnow().isoformat(), "event": "restore"}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def cli() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Emergency protocol")
    sub = ap.add_subparsers(dest="cmd")
    h = sub.add_parser("halt")
    h.add_argument("reason")
    sub.add_parser("restore")
    args = ap.parse_args()
    if args.cmd == "halt":
        print(json.dumps(halt(args.reason), indent=2))
    elif args.cmd == "restore":
        print(json.dumps(restore(), indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover
    cli()
