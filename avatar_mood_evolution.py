from __future__ import annotations
from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
"""Avatar Mood Evolution Visualizer

Graph the mood tags of an avatar across its history.
This implementation prints a simple time ordered list.
"""
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict

LOG_PATH = get_log_path("avatar_memory_link.jsonl", "AVATAR_MEMORY_LINK_LOG")


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


def mood_stats(avatar: str) -> Dict[str, int]:
    """Aggregate mood occurrences for the avatar."""
    stats: Dict[str, int] = {}
    for entry in mood_history(avatar):
        mood = entry.get("mood")
        if isinstance(mood, dict):
            for m in mood.keys():
                stats[m] = stats.get(m, 0) + 1
        elif isinstance(mood, str):
            stats[mood] = stats.get(mood, 0) + 1
    return stats


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Avatar mood evolution")
    ap.add_argument("avatar")
    args = ap.parse_args()
    for e in mood_history(args.avatar):
        print(e.get("timestamp"), e.get("mood"))
    stats = mood_stats(args.avatar)
    if stats:
        print(json.dumps({"stats": stats}, indent=2))


if __name__ == "__main__":
    main()
