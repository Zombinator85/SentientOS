from __future__ import annotations

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

LOG_PATH = Path(os.getenv("AVATAR_MOOD_COUNCIL_LOG", "logs/avatar_mood_council.jsonl"))
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
