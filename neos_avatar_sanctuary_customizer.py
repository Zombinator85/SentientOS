from __future__ import annotations
from admin_utils import require_admin_banner
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_sanctuary_custom.jsonl", "NEOS_SANCTUARY_CUSTOM_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_change(room: str, setting: str, value: str) -> Dict[str, str]:
    """Record a sanctuary customization change."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "room": room,
        "setting": setting,
        "value": value,
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
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Avatar Sanctuary Customizer")
    sub = ap.add_subparsers(dest="cmd")

    ch = sub.add_parser("change", help="Record customization change")
    ch.add_argument("room")
    ch.add_argument("setting")
    ch.add_argument("value")
    ch.set_defaults(func=lambda a: print(json.dumps(log_change(a.room, a.setting, a.value), indent=2)))

    hist = sub.add_parser("history", help="Show change history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
