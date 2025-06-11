from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_festival_mood_arc.jsonl", "NEOS_FESTIVAL_MOOD_ARC_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def animate(festival: str, mood: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "festival": festival,
        "mood": mood,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="NeosVR Festival Mood/Arc Animator")
    sub = ap.add_subparsers(dest="cmd")

    an = sub.add_parser("animate", help="Record mood animation")
    an.add_argument("festival")
    an.add_argument("mood")
    an.set_defaults(func=lambda a: print(json.dumps(animate(a.festival, a.mood), indent=2)))

    hist = sub.add_parser("history", help="Show animation history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
