from logging_config import get_log_path
import json
import random
import time
from pathlib import Path

from emotion_udp_bridge import EmotionUDPBridge


from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
LOG_FILE = get_log_path("emotion_vectors.jsonl")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def random_vector() -> list[float]:
    return [random.random() for _ in range(64)]


def run() -> None:
    bridge = EmotionUDPBridge()
    while True:
        vec = random_vector()
        bridge.update_vector(vec)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"timestamp": time.time(), "vector": vec}) + "\n")
        time.sleep(10)


if __name__ == "__main__":  # pragma: no cover - manual
    run()
