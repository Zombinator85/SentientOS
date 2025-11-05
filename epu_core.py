"""Simple emotion state with decay and caching."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from typing import Dict
from pathlib import Path
import json
import os

from logging_config import get_log_path
from emotions import EMOTIONS, empty_emotion_vector


CACHE_PATH = get_log_path("epu_state.json", "EPU_STATE_CACHE")


_GLOBAL_STATE: "EmotionState" | None = None


class EmotionState:
    """Maintain a 64-dimension emotion vector with decay."""

    def __init__(self, decay: float = 0.9, cache_path: Path | None = None) -> None:
        self.decay = decay
        self.cache_path = cache_path or CACHE_PATH
        self.vector: Dict[str, float] = empty_emotion_vector()
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self.cache_path.exists():
            return
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k in EMOTIONS:
                    if k in data:
                        self.vector[k] = float(data[k])
        except Exception:
            pass

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.vector, f)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def update(self, emotions: Dict[str, float]) -> Dict[str, float]:
        """Apply new emotion values with decay."""
        if not emotions:
            return self.vector
        for emo in EMOTIONS:
            val = emotions.get(emo)
            target = float(val) if val is not None else 0.0
            self.vector[emo] = self.vector[emo] * self.decay + target * (1 - self.decay)
        # Unknown emotions map to Ambivalence channel
        for k, v in emotions.items():
            if k not in EMOTIONS:
                self.vector["Ambivalence"] = self.vector["Ambivalence"] * self.decay + float(v) * (1 - self.decay)
        self._save()
        return self.vector

    def state(self) -> Dict[str, float]:
        return dict(self.vector)

    def apply_recall_emotion(
        self, emotions: Dict[str, float], *, influence: float = 0.2
    ) -> Dict[str, float]:
        """Blend historical emotions into the current baseline."""

        if not emotions:
            return dict(self.vector)
        weight = max(0.0, min(1.0, float(influence)))
        if weight <= 0.0:
            return dict(self.vector)
        for emo in EMOTIONS:
            target = float(emotions.get(emo, 0.0))
            self.vector[emo] = self.vector[emo] * (1 - weight) + target * weight
        for label, raw_value in emotions.items():
            if label in EMOTIONS:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            self.vector["Ambivalence"] = self.vector["Ambivalence"] * (1 - weight) + value * weight
        self._save()
        return dict(self.vector)


def get_global_state() -> EmotionState:
    """Return a process-wide ``EmotionState`` instance."""

    global _GLOBAL_STATE
    if _GLOBAL_STATE is None:
        _GLOBAL_STATE = EmotionState()
    return _GLOBAL_STATE
