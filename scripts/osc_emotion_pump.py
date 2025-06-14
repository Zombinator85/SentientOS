"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
"""Emit dominant emotion over OSC from distilled memory logs."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import time
from pathlib import Path
from typing import List

try:
    from pythonosc import udp_client
except Exception:  # pragma: no cover - optional
    udp_client = None

from emotions import EMOTIONS
from emotion_utils import text_sentiment

MEM_DIR = Path(os.getenv("MEMORY_DIR", "logs/memory")) / "distilled"
HOST = os.getenv("OSC_HOST", "127.0.0.1")
PORT = int(os.getenv("OSC_PORT", "9001"))
INTERVAL = 0.2  # seconds


def _latest_line() -> str:
    files = sorted(MEM_DIR.glob("*.txt"))
    if not files:
        return ""
    last = files[-1]
    try:
        lines = last.read_text(encoding="utf-8").splitlines()
        return lines[-1] if lines else ""
    except Exception:
        return ""


def _vector(text: str) -> List[float]:
    vec = text_sentiment(text)
    return [float(vec.get(e, 0.0)) for e in EMOTIONS]


def run() -> None:  # pragma: no cover - loop
    if udp_client is None:
        raise RuntimeError("python-osc not installed")
    client = udp_client.SimpleUDPClient(HOST, PORT)
    last = ""
    while True:
        line = _latest_line()
        if line and line != last:
            vec = _vector(line)
            client.send_message("/emotions", vec)
            last = line
        time.sleep(INTERVAL)


if __name__ == "__main__":  # pragma: no cover - manual
    run()
