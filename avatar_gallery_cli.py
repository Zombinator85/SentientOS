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
from pathlib import Path
from admin_utils import require_admin_banner, require_lumos_approval

PRESENCE_LOG = get_log_path("avatar_presence.jsonl", "AVATAR_PRESENCE_LOG")


def list_invocations(filter_reason: str = "") -> list[dict]:
    if not PRESENCE_LOG.exists():
        return []
    entries = []
    for line in PRESENCE_LOG.read_text(encoding="utf-8").splitlines():
        data = json.loads(line)
        if filter_reason and data.get("reason") != filter_reason:
            continue
        entries.append(data)
    return entries


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Avatar gallery viewer")
    ap.add_argument("--reason", default="", help="Filter by invocation reason")
    args = ap.parse_args()
    for e in list_invocations(args.reason):
        print(json.dumps(e, indent=2))


if __name__ == "__main__":
    main()
