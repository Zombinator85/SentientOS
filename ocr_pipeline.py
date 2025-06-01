import json
import os
import time
from pathlib import Path
from typing import List

import requests
from ocr_utils import ocr_chat_bubbles

FOLDER = Path(os.getenv("OCR_WATCH", "screenshots"))
RELAY_URL = os.getenv("RELAY_URL", "http://localhost:5000/relay")
RELAY_SECRET = os.getenv("RELAY_SECRET", "secret")
LOG_FILE = Path(os.getenv("OCR_RELAY_LOG", "logs/ocr_relay.jsonl"))
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def process_image(path: Path) -> List[str]:
    bubbles = ocr_chat_bubbles(str(path))
    return [b.get("text", "") for b in bubbles if b.get("text")]


def send_messages(messages: List[str]) -> List[str]:
    replies = []
    for msg in messages:
        payload = {"message": msg, "model": "openai/gpt-4o"}
        try:
            r = requests.post(
                RELAY_URL,
                headers={"X-Relay-Secret": RELAY_SECRET, "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            r.raise_for_status()
            rep = "\n".join(r.json().get("reply_chunks", []))
        except Exception as e:
            rep = f"error: {e}"
        LOG_FILE.touch(exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"message": msg, "reply": rep}) + "\n")
        replies.append(rep)
    return replies


def watch_folder():
    seen = set()
    while True:
        for img in FOLDER.glob("*.png"):
            if img in seen:
                continue
            seen.add(img)
            msgs = process_image(img)
            if msgs:
                send_messages(msgs)
        time.sleep(2)


if __name__ == "__main__":  # pragma: no cover - manual
    FOLDER.mkdir(parents=True, exist_ok=True)
    watch_folder()
