"""Avatar Federation Blessing Ritual

Import an avatar from another node and record a local blessing.
Presence pulse is captured to color the ritual log.

Example:
    python avatar_federation_blessing.py import avatar.tar.gz ./avatars alice
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import avatar_federation as af
from presence_pulse_api import pulse

LOG_PATH = Path(os.getenv("AVATAR_FED_BLESSING_LOG", "logs/avatar_federation_blessing.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def import_with_blessing(tar: Path, dest: Path, officiant: str) -> dict:
    dest_path = af.import_avatar(tar, dest, reason="federation")
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": dest_path.name,
        "officiant": officiant,
        "pulse": pulse(),
        "blessing": f"Avatar from {tar} accepted and crowned",
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar federation blessing")
    ap.add_argument("tar")
    ap.add_argument("dest")
    ap.add_argument("--officiant", default="")
    args = ap.parse_args()
    entry = import_with_blessing(Path(args.tar), Path(args.dest), args.officiant)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
