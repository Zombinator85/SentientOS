"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from logging_config import get_log_path


"""Avatar/Artifact Festival AI Animator."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("festival_animator.jsonl", "FESTIVAL_ANIMATOR_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def animate(event: str, mood: str) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "event": event, "mood": mood}
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
    ap = argparse.ArgumentParser(description="Avatar/Artifact Festival AI Animator")
    sub = ap.add_subparsers(dest="cmd")

    an = sub.add_parser("animate", help="Record an animation")
    an.add_argument("event")
    an.add_argument("mood")
    an.set_defaults(func=lambda a: print(json.dumps(animate(a.event, a.mood), indent=2)))

    hs = sub.add_parser("history", help="Show animation history")
    hs.add_argument("--limit", type=int, default=20)
    hs.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
