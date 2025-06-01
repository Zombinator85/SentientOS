"""Avatar Mood Evolution Visualizer

Graph the mood tags of an avatar across its history.
Currently prints a simple time ordered list. TODO: real graphs.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict

LOG_PATH = Path(os.getenv("AVATAR_MEMORY_LINK_LOG", "logs/avatar_memory_link.jsonl"))


def mood_history(avatar: str) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if f'"avatar": "{avatar}"' not in line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        out.append(entry)
    out.sort(key=lambda e: e.get("timestamp", ""))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar mood evolution")
    ap.add_argument("avatar")
    args = ap.parse_args()
    for e in mood_history(args.avatar):
        print(e.get("timestamp"), e.get("mood"))


if __name__ == "__main__":
    main()
