"""Avatar Presence Pulse Animation

Animates avatar presence intensity in sync with the presence pulse API.
Currently outputs an ASCII bar to represent animation.
TODO: real GUI or dashboard integration.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from presence_pulse_api import pulse

LOG_PATH = Path("logs/avatar_animation.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def animate_once(avatar: str) -> dict:
    p = pulse()
    bar = "#" * int(p * 10)
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "pulse": p,
        "animation": bar,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar presence pulse animation")
    ap.add_argument("avatar")
    args = ap.parse_args()
    entry = animate_once(args.avatar)
    print(entry["animation"])


if __name__ == "__main__":
    main()
