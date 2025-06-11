from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Avatar Emotional Feedback Loop.

Logs user reactions to avatar events for future mood adjustment.
"""
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_feedback.jsonl", "AVATAR_FEEDBACK_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_feedback(
    avatar: str, event: str, reaction: str, mood: str = "", user: str = ""
) -> Dict[str, str]:
    """Record a user reaction to an avatar event."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "event": event,
        "reaction": reaction,
        "mood": mood,
        "user": user,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def _load_entries(avatar: str) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if avatar and entry.get("avatar") != avatar:
            continue
        out.append(entry)
    return out


POSITIVE_REACTIONS = {"smile", "joy", "love", "like"}
NEGATIVE_REACTIONS = {"confusion", "frown", "dislike", "anger"}


def mood_trend(avatar: str) -> str:
    """Return a simple positive/negative/neutral trend for an avatar."""
    entries = _load_entries(avatar)
    score = 0
    for e in entries:
        reaction = str(e.get("reaction", "")).lower()
        if reaction in POSITIVE_REACTIONS:
            score += 1
        elif reaction in NEGATIVE_REACTIONS:
            score -= 1
    if score > 0:
        return "positive"
    if score < 0:
        return "negative"
    return "neutral"


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar emotional feedback loop")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Record user reaction")
    lg.add_argument("avatar")
    lg.add_argument("event")
    lg.add_argument("reaction")
    lg.add_argument("--mood", default="")
    lg.add_argument("--user", default="")
    lg.set_defaults(
        func=lambda a: print(
            json.dumps(
                log_feedback(a.avatar, a.event, a.reaction, a.mood, a.user), indent=2
            )
        )
    )

    tr = sub.add_parser("trend", help="Show reaction trend")
    tr.add_argument("avatar")
    tr.set_defaults(func=lambda a: print(mood_trend(a.avatar)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
