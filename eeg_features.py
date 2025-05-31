"""EEG feature extraction helpers.

This module reads raw EEG samples from :mod:`eeg_bridge` and estimates simple
cognitive states such as focus or drowsiness. Detected states are timestamped and
logged to ``logs/eeg_features.jsonl``.

The implementation here uses placeholder heuristics so that unit tests can run
without hardware or heavy dependencies.
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Dict

LOG_FILE = Path(os.getenv("EEG_FEATURE_LOG", "logs/eeg_features.jsonl"))
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def analyze_sample(sample: Dict[str, object]) -> Dict[str, object]:
    """Return cognitive state estimates for a raw EEG sample."""
    bands = sample.get("band_power", {}) if isinstance(sample, dict) else {}
    focus = float(bands.get("beta", random.random()))
    drowsy = float(bands.get("theta", random.random()))
    entry = {
        "timestamp": sample.get("timestamp", time.time()),
        "focus": focus,
        "drowsiness": drowsy,
        "blink": random.random() > 0.9,
        "jaw_clench": random.random() > 0.95,
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


if __name__ == "__main__":  # pragma: no cover - manual usage
    from eeg_bridge import EEGBridge

    bridge = EEGBridge()
    for _ in range(5):
        s = bridge.read_sample()
        print(analyze_sample(s))
        time.sleep(0.5)
