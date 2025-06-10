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

from admin_utils import require_admin_banner, require_lumos_approval

"""Record avatar invocation and presence blessing.

This CLI logs each time an avatar is invoked for a specific reason.
A presence affirmation is stored with a blessing message.
"""
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

LOG_PATH = get_log_path("avatar_presence.jsonl", "AVATAR_PRESENCE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_invocation(path: str, reason: str, mode: str = "visual") -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": path,
        "mode": mode,
        "reason": reason,
        "blessing": f"Avatar crowned for {reason}",
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Invoke avatar with blessing")
    ap.add_argument("avatar")
    ap.add_argument("reason")
    ap.add_argument("--mode", default="visual")
    args = ap.parse_args()
    entry = log_invocation(args.avatar, args.reason, args.mode)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
