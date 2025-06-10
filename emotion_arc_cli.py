"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""  # plint: disable=banner-order
require_admin_banner()
require_lumos_approval()
#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|    |_\__,_|\__, |_|_| |_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/ 
from __future__ import annotations
"""Privilege Banner: requires admin & Lumos approval."""
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.

from logging_config import get_log_path
import argparse
import json
from datetime import datetime, date
from pathlib import Path

import ledger
from admin_utils import require_admin_banner, require_lumos_approval


def load_today(limit: int = 100) -> list:
    path = get_log_path("music_log.jsonl")
    if not path.exists():
        return []
    today = date.today().isoformat()
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if today not in ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out[-limit:]


def ascii_graph(args: argparse.Namespace) -> None:
    data = load_today(args.limit)
    if not data:
        print("No data")
        return
    points = []
    for e in data:
        emo = e.get("emotion", {}).get("reported") or {}
        val = emo.get(args.mood, 0.0)
        ts = e.get("timestamp")
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                points.append((dt, val))
            except Exception:
                continue
    if not points:
        print("No emotion points")
        return
    points.sort(key=lambda x: x[0])
    max_val = max(v for _, v in points) or 1.0
    for dt, v in points:
        bar = "#" * int((v / max_val) * 50)
        print(f"{dt.time()} {bar}")


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Emotional arc grapher")
    ap.add_argument("mood", help="Emotion key to graph")
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()
    ascii_graph(args)


if __name__ == "__main__":
    main()
