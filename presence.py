"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Presence detection service for wake words and transcripts."""

# Boundary assertion:
# This module only records wake-word events and raw transcript snippets; it does not infer identity, affinity, or relational state.
# Logged data is append-only telemetry and is not used to adjust behaviour or privileges.
# See: NON_GOALS_AND_FREEZE.md §Presence, INVARIANT_CROSS_REFERENCE_INDEX.md §Telemetry-only logging

from logging_config import get_log_path
import os
import json
import time
import datetime
from pathlib import Path
from typing import List, Optional, Callable, Dict

_rec: Optional[Callable[[bool], Dict[str, Optional[str]]]]
try:
    from mic_bridge import recognize_from_mic as _rec
except Exception:  # pragma: no cover - defensive
    _rec = None

recognize_from_mic: Optional[Callable[[bool], Dict[str, Optional[str]]]] = _rec

WAKE_WORDS: List[str] = [w.strip() for w in os.getenv("WAKE_WORDS", "Lumos").split(",") if w.strip()]
LOG_FILE = get_log_path("presence_events.jsonl")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def _log(word: str, text: str) -> None:
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "word": word,
        "heard": text,
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def run_loop() -> None:  # pragma: no cover - realtime usage
    if recognize_from_mic is None:
        print("[PRESENCE] mic capture unavailable")
        return
    print(f"[PRESENCE] Listening for wake words: {', '.join(WAKE_WORDS)}")
    while True:
        result = recognize_from_mic(False)
        text = (result.get("message") or "").lower()
        if not text:
            continue
        for w in WAKE_WORDS:
            if w.lower() in text:
                _log(w, text)
                print(f"[PRESENCE] Detected {w}")
                break
        time.sleep(0.1)


if __name__ == "__main__":  # pragma: no cover - manual
    run_loop()
