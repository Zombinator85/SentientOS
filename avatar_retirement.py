"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()



# Avatar Retirement & Archive Ritual
#
# Retire an avatar with reflection and preserve it in an archive.
# The act is logged in a ritual ledger.
#
# Example usage:
#     python avatar_retirement.py retire avatar1.blend retired/ --mood nostalgia --reason "story closed"

from logging_config import get_log_path

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

LOG_PATH = get_log_path("avatar_retirement.jsonl", "AVATAR_RETIRE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def retire_avatar(path: Path, archive: Path, mood: str = "", reason: str = "") -> dict:
    archive.mkdir(parents=True, exist_ok=True)
    dest = archive / path.name
    if path.exists():
        shutil.copy2(path, dest)
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": path.name,
        "mood": mood,
        "reason": reason,
        "archive": str(dest),
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    ap = argparse.ArgumentParser(description="Retire avatar")
    ap.add_argument("avatar")
    ap.add_argument("archive")
    ap.add_argument("--mood", default="")
    ap.add_argument("--reason", default="")
    args = ap.parse_args()
    entry = retire_avatar(Path(args.avatar), Path(args.archive), args.mood, args.reason)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
