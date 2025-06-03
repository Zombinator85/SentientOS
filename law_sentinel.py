from admin_utils import require_admin_banner
"""Law Sentinel & Automated Doctrine Watchdog

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path


LOG_PATH = get_log_path("law_sentinel.jsonl", "LAW_SENTINEL_LOG")
WATCH_PATH = get_log_path("agents.log", "LAW_WATCH_FILE")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def scan() -> None:
    if not WATCH_PATH.exists():
        return
    for line in WATCH_PATH.read_text(encoding="utf-8").splitlines():
        if "violation" in line.lower():
            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "event": "violation",
                "line": line,
            }
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")


def watch(interval: float) -> None:  # pragma: no cover - runtime loop
    while True:
        scan()
        time.sleep(interval)


def cli() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Law sentinel")
    ap.add_argument("--watch", type=float, help="Watch interval")
    args = ap.parse_args()
    if args.watch:
        watch(args.watch)
    else:
        scan()


if __name__ == "__main__":  # pragma: no cover
    cli()
