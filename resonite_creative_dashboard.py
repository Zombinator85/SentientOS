from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

LOG_PATH = get_log_path("resonite_creative_dashboard.jsonl", "RESONITE_CREATIVE_DASHBOARD_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_action(user: str, action: str, mood: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "action": action,
        "mood": mood,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Resonite creative dashboard")
    parser.add_argument("user")
    parser.add_argument("action")
    parser.add_argument("mood")
    args = parser.parse_args()
    require_admin_banner()
    print(json.dumps(log_action(args.user, args.action, args.mood), indent=2))


if __name__ == "__main__":
    main()
