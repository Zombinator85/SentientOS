from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import neos_bridge as nb
import presence_ledger as pl

LOG_PATH = get_log_path("neos_avatar_teaching.jsonl", "NEOS_TEACH_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def teach(avatar: str, lesson: str) -> dict:
    nb.send_message("teaching", f"{avatar}: {lesson}")
    entry = {"timestamp": datetime.utcnow().isoformat(), "avatar": avatar, "lesson": lesson}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    pl.log(avatar, "teaching", lesson)
    return entry


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Avatar Teaching Mode")
    ap.add_argument("avatar")
    ap.add_argument("lesson")
    args = ap.parse_args()
    entry = teach(args.avatar, args.lesson)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
