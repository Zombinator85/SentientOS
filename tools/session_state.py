"""Helper CLI for inspecting and clearing autonomy continuity state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.autonomy.state import ContinuityStateManager


STATE_PATH = Path("glow/state/session.json")
MOOD_PATH = Path("glow/state/mood.json")


def dump_state() -> int:
    manager = ContinuityStateManager(STATE_PATH)
    snapshot = manager.load()
    print(json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False))
    return 0


def clear_state() -> int:
    manager = ContinuityStateManager(STATE_PATH)
    manager.clear()
    MOOD_PATH.unlink(missing_ok=True)
    heartbeat = Path("pulse/heartbeat.snap")
    heartbeat.unlink(missing_ok=True)
    (Path("pulse") / "last_readiness.txt").unlink(missing_ok=True)
    print("continuity state cleared")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect SentientOS continuity state")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("dump", help="Print the current continuity snapshot")
    sub.add_parser("clear", help="Remove persisted continuity state")
    args = parser.parse_args(argv)
    if args.command == "dump":
        return dump_state()
    if args.command == "clear":
        return clear_state()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

