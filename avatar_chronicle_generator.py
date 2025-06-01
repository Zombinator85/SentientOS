"""Ritual Avatar Chronicle Generator

Compile a markdown chronicle of avatar creation, blessings, and retirements.

Example:
    python avatar_chronicle_generator.py --out chronicle.md
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict

LOGS = [
    Path("logs/avatar_memory_link.jsonl"),
    Path("logs/avatar_council_log.jsonl"),
    Path("logs/avatar_retirement.jsonl"),
]


def _load(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def generate_markdown() -> str:
    entries = []
    for path in LOGS:
        entries.extend(_load(path))
    entries.sort(key=lambda e: e.get("timestamp", ""))
    lines = ["# Avatar Chronicle"]
    for e in entries:
        ts = e.get("timestamp")
        avatar = e.get("avatar", "")
        event = e.get("event", e.get("vote", ""))
        mood = e.get("mood", "")
        lines.append(f"- {ts} **{avatar}** {event} {mood}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate avatar chronicle")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    md = generate_markdown()
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
    else:
        print(md)


if __name__ == "__main__":
    main()
