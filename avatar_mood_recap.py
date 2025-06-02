"""Ritual Avatar Mood Recap

Summarize moods and blessing lines of avatar events over a period.
Outputs markdown by default.

Example:
    python avatar_mood_recap.py --days 1 --out recap.md
"""
from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_memory_link.jsonl", "AVATAR_MEMORY_LINK_LOG")


def load_entries(days: int = 1) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    start = datetime.utcnow() - timedelta(days=days)
    out = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except Exception:
            continue
        ts = entry.get("timestamp")
        try:
            dt = datetime.fromisoformat(str(ts))
        except Exception:
            continue
        if dt >= start:
            out.append(entry)
    return out


def recap_markdown(days: int = 1) -> str:
    entries = load_entries(days)
    lines = ["# Avatar Mood Recap"]
    current = {}
    for e in entries:
        avatar = e.get("avatar")
        mood = e.get("mood")
        if not avatar:
            continue
        current.setdefault(avatar, []).append(mood)
    for avatar, moods in current.items():
        lines.append(f"\n## {avatar}\n")
        lines.append(", ".join([m for m in moods if m]))
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar mood recap")
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    md = recap_markdown(args.days)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
    else:
        print(md)


if __name__ == "__main__":
    main()
