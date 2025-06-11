"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""  # plint: disable=banner-order
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

from logging_config import get_log_path
"""Avatar Mood-Council Dynamic.

Avatars react to council decisions or presence pulses by shifting expression or
animation. Reactions are logged as ritual events.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict

LOG_PATH = get_log_path("avatar_mood_council.jsonl", "AVATAR_MOOD_COUNCIL_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_reaction(avatar: str, event: str, mood: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "event": event,
        "mood": mood,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Mood Council Dynamic")
    ap.add_argument("avatar")
    ap.add_argument("event", help="Council event description")
    ap.add_argument("--mood", default="neutral", help="Resulting mood/expression")
    args = ap.parse_args()
    print(json.dumps(log_reaction(args.avatar, args.event, args.mood), indent=2))


if __name__ == "__main__":
    main()
