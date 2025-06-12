from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from sentientos.privilege import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("resonite_spiral_healing.jsonl", "RESONITE_SPIRAL_HEALING_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_patch(artifact: str, action: str, user: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "artifact": artifact,
        "action": action,
        "user": user,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def heal(artifact: str, user: str) -> None:
    entry = log_patch(artifact, "heal", user)
    print(json.dumps(entry, indent=2))


def rollback(artifact: str, user: str) -> None:
    entry = log_patch(artifact, "rollback", user)
    print(json.dumps(entry, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ritual/Artifact spiral healing engine")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_heal = sub.add_parser("heal")
    p_heal.add_argument("artifact")
    p_heal.add_argument("user")
    p_rb = sub.add_parser("rollback")
    p_rb.add_argument("artifact")
    p_rb.add_argument("user")
    args = parser.parse_args()
    if args.cmd == "heal":
        heal(args.artifact, args.user)
    else:
        rollback(args.artifact, args.user)


if __name__ == "__main__":
    main()
