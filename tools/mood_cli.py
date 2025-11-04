"""Inspect or reset mood persistence state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

STATE_PATH = Path("glow/state/mood.json")


def show() -> None:
    if not STATE_PATH.exists():
        print("mood:unset")
        return
    payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    mood = payload.get("mood", "unknown")
    baseline = payload.get("baseline", "unknown")
    print(f"mood:{mood} baseline:{baseline}")


def reset() -> None:
    if STATE_PATH.exists():
        STATE_PATH.unlink()
    print("mood:reset")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage persisted mood state")
    parser.add_argument("action", choices=["status", "reset"], help="Inspect or clear state")
    args = parser.parse_args()
    if args.action == "status":
        show()
    else:
        reset()


if __name__ == "__main__":
    main()

