from __future__ import annotations
from logging_config import get_log_path

import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:  # optional speech output
    import tts_bridge  # type: ignore  # internal TTS bridge
except Exception:  # pragma: no cover - optional
    tts_bridge = None  # type: ignore  # disable speech

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("avatar_storyteller.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_story(avatar: str, memory: str, mood: str) -> dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "memory": memory,
        "mood": mood,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def recite(avatar: str, memory: str) -> dict[str, Any]:
    """Speak a memory snippet and log the performance."""
    mood = "excited" if "!" in memory else "neutral"
    if tts_bridge is not None:
        try:
            tts_bridge.speak(memory, emotions={mood: 1.0})
        except Exception:  # pragma: no cover - audio errors
            pass
    return log_story(avatar, memory, mood)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Avatar storyteller and reciter")
    ap.add_argument("avatar")
    ap.add_argument("memory")
    args = ap.parse_args()
    entry = recite(args.avatar, args.memory)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
