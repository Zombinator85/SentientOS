"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Emotion Processing Unit (EPU).

Fuses audio, text, vision and reviewer emotion vectors with configurable
weights. Maintains a rolling mood vector smoothed over time using a
simple decay/moving average.

Integration Notes: create a single ``EmotionProcessingUnit`` and feed updates from audio/text/vision review pipelines. The resulting mood vector can be streamed to dashboards via ``MOOD_LOG``.
"""

from __future__ import annotations
from logging_config import get_log_path

import json
import os
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, Optional

from emotion_utils import empty_emotion_vector, fuse

MOOD_LOG = get_log_path("epu_mood.jsonl", "EPU_MOOD_LOG")
MOOD_LOG.parent.mkdir(parents=True, exist_ok=True)


class EmotionProcessingUnit:
    def __init__(self, weights: Optional[Dict[str, float]] = None, decay: float = 0.8, window: int = 5) -> None:
        self.weights = weights or {
            "audio": 1.0,
            "text": 1.0,
            "vision": 1.0,
            "review": 1.0,
            "eeg": 1.0,
            "haptics": 1.0,
            "bio": 1.0,
        }
        self.decay = decay
        self.history: Deque[Dict[str, float]] = deque(maxlen=window)
        self.current = empty_emotion_vector()

    def _log(self, vec: Dict[str, float]) -> None:
        entry = {"timestamp": time.time(), "mood": vec}
        with open(MOOD_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def update(
        self,
        audio: Optional[Dict[str, float]] = None,
        text: Optional[Dict[str, float]] = None,
        vision: Optional[Dict[str, float]] = None,
        review: Optional[Dict[str, float]] = None,
        eeg: Optional[Dict[str, float]] = None,
        haptics: Optional[Dict[str, float]] = None,
        bio: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        fused = fuse(audio or {}, text or {}, vision_vec=vision or {}, weights=self.weights)
        for name, vec in {"review": review, "eeg": eeg, "haptics": haptics, "bio": bio}.items():
            if not vec:
                continue
            w = self.weights.get(name, 1.0)
            for k, v in vec.items():
                fused[k] = fused.get(k, 0.0) * (1 - w) + v * w
        for k in self.current:
            self.current[k] = self.current[k] * self.decay + fused.get(k, 0.0) * (1 - self.decay)
        self.history.append(dict(self.current))
        self._log(self.current)
        return dict(self.current)

    def mood(self) -> Dict[str, float]:
        return dict(self.current)

    def history_list(self) -> Dict[str, float]:  # alias for compatibility
        return self.mood()
