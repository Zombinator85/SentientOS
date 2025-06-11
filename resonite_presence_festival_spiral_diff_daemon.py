"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

LOG_PATH = get_log_path("resonite_presence_festival_diff.jsonl", "RESONITE_PRESENCE_FESTIVAL_DIFF_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_diff(world_a: str, world_b: str, user: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "world_a": world_a,
        "world_b": world_b,
        "user": user,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Resonite presence/festival spiral diff daemon")
    parser.add_argument("world_a")
    parser.add_argument("world_b")
    parser.add_argument("user")
    args = parser.parse_args()
    print(json.dumps(log_diff(args.world_a, args.world_b, args.user), indent=2))


if __name__ == "__main__":
    main()
