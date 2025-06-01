"""Simple CLI to view avatars and presence pulses."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

PRESENCE_LOG = Path(os.getenv("AVATAR_PRESENCE_LOG", "logs/avatar_presence.jsonl"))


def list_invocations(filter_reason: str = "") -> list[dict]:
    if not PRESENCE_LOG.exists():
        return []
    entries = []
    for line in PRESENCE_LOG.read_text(encoding="utf-8").splitlines():
        data = json.loads(line)
        if filter_reason and data.get("reason") != filter_reason:
            continue
        entries.append(data)
    return entries


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar gallery viewer")
    ap.add_argument("--reason", default="", help="Filter by invocation reason")
    args = ap.parse_args()
    for e in list_invocations(args.reason):
        print(json.dumps(e, indent=2))


if __name__ == "__main__":
    main()
