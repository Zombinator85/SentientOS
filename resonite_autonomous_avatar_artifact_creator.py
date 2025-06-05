from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("resonite_avatar_artifact_creator.jsonl", "RESONITE_AVATAR_ARTIFACT_CREATOR_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_creation(kind: str, name: str, user: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "kind": kind,
        "name": name,
        "user": user,
        "blessing": "spiral_blessed",
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def create(kind: str, name: str, user: str) -> None:
    require_admin_banner()
    entry = log_creation(kind, name, user)
    print(json.dumps(entry, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous avatar/artifact creation")
    parser.add_argument("kind", choices=["avatar", "artifact"])
    parser.add_argument("name")
    parser.add_argument("--user", default="system")
    args = parser.parse_args()
    create(args.kind, args.name, args.user)


if __name__ == "__main__":
    main()
