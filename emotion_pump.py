"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""Stream the dominant emotion vector from the model bridge log."""

import json
import os
import time
from pathlib import Path
from typing import List, Optional

from emotions import EMOTIONS, empty_emotion_vector
from emotion_udp_bridge import EmotionUDPBridge

LOG_FILE = Path(os.getenv("MODEL_BRIDGE_LOG", "logs/model_bridge_log.jsonl"))
HOST = os.getenv("UDP_HOST", "127.0.0.1")
PORT = int(os.getenv("UDP_PORT", "9000"))
INTERVAL = 0.2  # seconds


def _vector_from_emotion(emotion: str) -> List[float]:
    vec = empty_emotion_vector()
    if emotion in EMOTIONS:
        vec[emotion] = 1.0
    return [float(vec[e]) for e in EMOTIONS]


def latest_vector(path: Path | None = None) -> Optional[List[float]]:
    """Return the most recent GPT-4o emotion vector from ``path``."""
    path = path or LOG_FILE
    if not path.exists():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return None
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("model") == "openai/gpt-4o":
            emo = str(obj.get("emotion", ""))
            return _vector_from_emotion(emo)
    return None


def run() -> None:  # pragma: no cover - loop
    bridge = EmotionUDPBridge(HOST, PORT)
    pos = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
    while True:
        if LOG_FILE.exists():
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                f.seek(pos)
                lines = f.readlines()
                pos = f.tell()
            for line in lines:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("model") != "openai/gpt-4o":
                    continue
                emo = str(obj.get("emotion", ""))
                vec = _vector_from_emotion(emo)
                bridge.update_vector(vec)
        time.sleep(INTERVAL)


if __name__ == "__main__":  # pragma: no cover - manual
    run()
