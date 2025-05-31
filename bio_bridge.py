"""Biosignal integration bridge.

Collects physiological metrics from wearables or IoT sensors (heart rate,
skin conductance, temperature) and logs them to ``logs/bio_events.jsonl``.
The implementation uses random data in headless mode or when dependencies are
missing.
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Dict

from utils import is_headless

LOG_FILE = Path(os.getenv("BIO_LOG", "logs/bio_events.jsonl"))
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def read_biosignals() -> Dict[str, float]:
    """Return the latest biosignal measurements."""
    # Real implementations would pull from BLE/USB APIs
    heart_rate = random.randint(60, 90)
    gsr = random.random()
    temp = 36.0 + random.random()
    entry = {
        "timestamp": time.time(),
        "heart_rate": heart_rate,
        "gsr": gsr,
        "temperature": temp,
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


if __name__ == "__main__":  # pragma: no cover - manual
    for _ in range(5):
        print(read_biosignals())
        time.sleep(0.5)
