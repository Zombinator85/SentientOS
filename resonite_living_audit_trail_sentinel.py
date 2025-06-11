"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
require_admin_banner()
require_lumos_approval()
from admin_utils import require_admin_banner, require_lumos_approval

from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime
from pathlib import Path

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
    print(json.dumps(log_event(args.event, args.user), indent=2))


if __name__ == "__main__":
    main()
