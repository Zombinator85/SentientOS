"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""  # plint: disable=banner-order
require_admin_banner()
require_lumos_approval()
from __future__ import annotations
#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|    |_\__,_|\__, |_|_| |_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/ 
from __future__ import annotations
"""Privilege Banner: requires admin & Lumos approval."""
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.

from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import daily_theme
from admin_utils import require_admin_banner, require_lumos_approval

LITURGY_LOG = get_log_path("cathedral_liturgy.jsonl", "CATHEDRAL_LITURGY_LOG")
LITURGY_LOG.parent.mkdir(parents=True, exist_ok=True)


def _append(entry: dict) -> None:
    with LITURGY_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def boot_command(args: argparse.Namespace) -> None:
    theme = daily_theme.generate()
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": "boot",
        "theme": theme,
    }
    _append(entry)
    print(f"Cathedral opens • theme: {theme}")


def shutdown_command(args: argparse.Namespace) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": "shutdown",
    }
    _append(entry)
    print("Cathedral closes • see blessing ledger for recap")


def history_command(args: argparse.Namespace) -> None:
    if not LITURGY_LOG.exists():
        print("[]")
        return
    lines = LITURGY_LOG.read_text(encoding="utf-8").splitlines()[-args.limit:]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    print(json.dumps(out, indent=2))


def main() -> None:
    require_admin_banner()
    parser = argparse.ArgumentParser(description="Cathedral boot/shutdown liturgy")
    sub = parser.add_subparsers(dest="cmd")

    b = sub.add_parser("boot")
    b.set_defaults(func=boot_command)

    s = sub.add_parser("shutdown")
    s.set_defaults(func=shutdown_command)

    h = sub.add_parser("history")
    h.add_argument("--limit", type=int, default=10)
    h.set_defaults(func=history_command)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
