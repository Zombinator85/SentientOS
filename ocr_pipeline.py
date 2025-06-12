"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import json
import os
import time
from pathlib import Path
from typing import List
import atexit

import requests
from ocr_utils import ocr_chat_bubbles

FOLDER = Path(os.getenv("OCR_WATCH", "screenshots"))
RELAY_URL = os.getenv("RELAY_URL", "http://localhost:5000/relay")
RELAY_SECRET = os.getenv("RELAY_SECRET", "secret")
LOG_FILE = get_log_path("ocr_relay.jsonl", "OCR_RELAY_LOG")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Deduplication state
LAST_MSG: str | None = None
LAST_REPLY: str | None = None
COUNT = 0
FIRST_TS = 0.0


def process_image(path: Path) -> List[str]:
    bubbles = ocr_chat_bubbles(str(path))
    return [b.get("text", "") for b in bubbles if b.get("text")]


def _flush_last() -> None:
    """Write the last seen message to the log."""
    global LAST_MSG, LAST_REPLY, COUNT, FIRST_TS
    if LAST_MSG is None:
        return
    entry = {
        "timestamp": FIRST_TS,
        "message": LAST_MSG,
        "reply": LAST_REPLY,
        "count": COUNT,
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    LAST_MSG = None
    LAST_REPLY = None
    COUNT = 0
    FIRST_TS = 0.0


def _send_message(msg: str) -> str:
    payload = {"message": msg, "model": "openai/gpt-4o"}
    try:
        r = requests.post(
            RELAY_URL,
            headers={"X-Relay-Secret": RELAY_SECRET, "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        return "\n".join(r.json().get("reply_chunks", []))
    except Exception as e:
        return f"error: {e}"


def handle_message(msg: str) -> None:
    """Deduplicate messages and log with a counter."""
    global LAST_MSG, LAST_REPLY, COUNT, FIRST_TS
    if msg == LAST_MSG:
        COUNT += 1
        return
    if LAST_MSG is not None:
        _flush_last()
    LAST_MSG = msg
    LAST_REPLY = _send_message(msg)
    COUNT = 1
    FIRST_TS = time.time()


def flush() -> None:
    """Flush any pending message to disk."""
    _flush_last()


atexit.register(flush)


def watch_folder():
    seen = set()
    while True:
        for img in FOLDER.glob("*.png"):
            if img in seen:
                continue
            seen.add(img)
            msgs = process_image(img)
            for m in msgs:
                handle_message(m)
        time.sleep(2)


if __name__ == "__main__":  # pragma: no cover - manual
    FOLDER.mkdir(parents=True, exist_ok=True)
    watch_folder()
