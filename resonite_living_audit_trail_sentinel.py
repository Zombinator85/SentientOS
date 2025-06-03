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

LOG_PATH = get_log_path("resonite_living_audit.jsonl", "RESONITE_LIVING_AUDIT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_event(event: str, user: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event,
        "user": user,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Resonite living audit trail sentinel")
    parser.add_argument("event")
    parser.add_argument("user")
    args = parser.parse_args()
    require_admin_banner()
    print(json.dumps(log_event(args.event, args.user), indent=2))


if __name__ == "__main__":
    main()
