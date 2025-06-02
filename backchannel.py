from logging_config import get_log_path
import os
import json
import time
import random
import datetime
from pathlib import Path
from typing import Dict, List

try:
    from tts_bridge import speak_async
except Exception:  # pragma: no cover - optional
    speak_async = None

from mic_bridge import recognize_from_mic

PHRASES: List[str] = ["mm-hmm", "right...", "go on..."]
GAP_SECONDS = float(os.getenv("BACKCHANNEL_GAP", "6"))
LOG_FILE = get_log_path("backchannel_audit.jsonl")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def _log(trigger: str, phrase: str, extra: Dict[str, str] | None = None) -> None:
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "trigger": trigger,
        "phrase": phrase,
    }
    if extra:
        entry.update(extra)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def run_loop() -> None:  # pragma: no cover - real-time loop
    last_speech = time.time()
    print(f"[BACKCHANNEL] Running with gap {GAP_SECONDS}s")
    while True:
        result = recognize_from_mic(save_audio=False)
        text = result.get("message")
        emotions = result.get("emotions") or {}
        if text:
            last_speech = time.time()
            continue
        if time.time() - last_speech > GAP_SECONDS:
            phrase = random.choice(PHRASES)
            _log("gap", phrase, {"emotions": emotions})
            if speak_async is not None:
                t = speak_async(phrase)
                t.join()
            else:
                print(phrase)
            last_speech = time.time()


if __name__ == "__main__":  # pragma: no cover - manual usage
    run_loop()
