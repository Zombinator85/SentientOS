"""Utility CLI for toggling the persistent panic flag."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path("glow/state/panic.json")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_state(active: bool) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if active:
        payload = {"active": True, "timestamp": _timestamp()}
        STATE_PATH.write_text(json.dumps(payload), encoding="utf-8")
        print("panic:on")
    else:
        if STATE_PATH.exists():
            STATE_PATH.unlink()
        print("panic:off")


def status() -> None:
    if not STATE_PATH.exists():
        print("panic:off")
        return
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        active = bool(payload.get("active", False))
        ts = payload.get("timestamp", "unknown")
    except Exception:
        active = True
        ts = "corrupt"
    state = "on" if active else "off"
    print(f"panic:{state} timestamp={ts}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Toggle the SentientOS panic flag.")
    parser.add_argument("state", choices=["on", "off", "status"], help="Desired panic state")
    args = parser.parse_args()
    if args.state == "status":
        status()
    elif args.state == "on":
        set_state(True)
    else:
        set_state(False)


if __name__ == "__main__":
    main()

