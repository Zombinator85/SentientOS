"""Face emotion detection helper.

This module uses the ``fer`` library to analyze emotions from webcam
frames or still images. Detected vectors match the format used by
``emotion_utils`` and can be fed directly into ``multimodal_tracker``
or other dashboards.

All results are logged to ``logs/face_emotion.jsonl``.

Integration Notes: call ``FaceEmotionDetector.webcam_loop`` with a ``MultiModalEmotionTracker`` instance to automatically update the fusion vector.
"""

from __future__ import annotations
from logging_config import get_log_path

import json
import os
import time
from pathlib import Path
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from multimodal_tracker import MultiModalEmotionTracker

try:
    from fer import FER  # type: ignore  # FER library
    import cv2  # type: ignore  # OpenCV optional
except Exception:  # pragma: no cover - optional dependency
    FER = None
    cv2 = None

LOG_PATH = get_log_path("face_emotion.jsonl", "FACE_EMOTION_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


class FaceEmotionDetector:
    """Detect emotions from webcam or image input."""

    def __init__(self, detector: Optional[FER] = None) -> None:
        self.detector = detector or (FER(mtcnn=False) if FER else None)

    def _log(self, emotions: Dict[str, float]) -> None:
        entry = {"timestamp": time.time(), "emotions": emotions}
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def detect_image(self, path: str) -> Dict[str, float]:
        if not self.detector or not cv2:
            return {}
        img = cv2.imread(path)
        if img is None:
            return {}
        res = self.detector.detect_emotions(img)
        emotions = res[0]["emotions"] if res else {}
        self._log(emotions)
        return {k: float(v) for k, v in emotions.items()}

    def webcam_loop(
        self,
        tracker: Optional["MultiModalEmotionTracker"] = None,
        person_id: int = 0,
        max_frames: Optional[int] = None,
    ) -> None:
        if not self.detector or not cv2:
            print("[FACE_EMOTION] camera or FER not available")
            return
        cap = cv2.VideoCapture(0)
        frames = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            res = self.detector.detect_emotions(frame)
            emotions = res[0]["emotions"] if res else {}
            self._log(emotions)
            if tracker:
                tracker.memory.add(person_id, "vision", emotions, time.time())
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
        cap.release()
