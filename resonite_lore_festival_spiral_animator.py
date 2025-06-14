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

LOG_PATH = get_log_path("resonite_lore_festival_animator.jsonl", "RESONITE_LORE_FESTIVAL_ANIMATOR_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_animation(name: str, artifact: str, user: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "name": name,
        "artifact": artifact,
        "user": user,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Resonite lore/festival spiral animator")
    parser.add_argument("name")
    parser.add_argument("artifact")
    parser.add_argument("user")
    args = parser.parse_args()
    print(json.dumps(log_animation(args.name, args.artifact, args.user), indent=2))


if __name__ == "__main__":
    main()
