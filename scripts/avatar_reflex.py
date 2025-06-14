"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
"""Watch relay_log.jsonl for emotion spikes and trigger reflexive feedback."""

import json
import os
import time
from pathlib import Path
from typing import Dict

from logging_config import get_log_path

try:
    from tts_bridge import speak  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional
    speak = None

LOG_FILE = get_log_path("relay_log.jsonl", "RELAY_LOG")
EMOTION_MAP: Dict[str, str] = {
    "rage_pulse": "(╯°□°)╯︵ ┻━┻",
    "joy_surge": "(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧",
}


def _trigger(emotion: str, content: str) -> None:
    art = EMOTION_MAP.get(emotion, ":)")
    print(f"[REFLEX] {emotion}: {art}")
    if speak:
        speak(content or emotion)


def watch_loop() -> None:  # pragma: no cover - realtime loop
    if not LOG_FILE.exists():
        LOG_FILE.touch()
    with LOG_FILE.open("r", encoding="utf-8") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(1)
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            emo = entry.get("emotion")
            if emo in EMOTION_MAP:
                _trigger(emo, entry.get("content", ""))


def main() -> None:  # pragma: no cover - CLI
    print("Avatar reflex bridge active")
    watch_loop()


if __name__ == "__main__":
    main()
