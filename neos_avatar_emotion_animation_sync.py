from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = Path(os.getenv("NEOS_ANIMATION_LOG", "logs/neos_avatar_animation.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_animation(emotion: str, memory: str, animation: str) -> Dict[str, str]:
    """Record an avatar animation event."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "emotion": emotion,
        "memory": memory,
        "animation": animation,
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


ANIMATION_MAP = {
    "joy": "smile",
    "sadness": "frown",
    "anger": "glare",
    "surprise": "wide_eyes",
}


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Avatar Emotion-Animation Sync")
    sub = ap.add_subparsers(dest="cmd")

    pulse = sub.add_parser("pulse", help="Send test emotion pulse")
    pulse.add_argument("emotion")
    pulse.add_argument("memory")
    pulse.set_defaults(func=lambda a: print(json.dumps(
        log_animation(a.emotion, a.memory, ANIMATION_MAP.get(a.emotion, "neutral")),
        indent=2)))

    hist = sub.add_parser("history", help="Show animation history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
