"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

"""Optional object recognition module for enriching multimodal awareness."""

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import os
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from logging_config import get_log_path
from utils import is_headless

try:  # pragma: no cover - optional dependency
    from ultralytics import YOLO  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional dependency missing
    YOLO = None  # type: ignore[misc]

try:  # pragma: no cover - optional dependency
    import numpy as np  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional dependency missing
    np = None  # type: ignore[misc]


HEADLESS = is_headless()


@dataclass
class SceneObject:
    """Representation of a detected object in the scene."""

    label: str
    confidence: float
    bbox: List[float]


class ObjectRecognitionModule:
    """Optional YOLO-based object recognizer that converts frames into summaries."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        confidence: float = 0.3,
        max_objects: int = 25,
        log_path: Optional[Path] = None,
    ) -> None:
        self.confidence = confidence
        self.max_objects = max_objects
        self._last_labels: List[str] = []
        self.log_path = log_path or get_log_path("multimodal/environment_objects.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.model = None
        self.available = False

        if HEADLESS or YOLO is None:
            return

        user_model = model_path or os.getenv("SENTIENT_OBJECT_MODEL")
        candidate = user_model or "yolov8n.pt"
        try:
            # Loading will lazily download the default model if available.
            self.model = YOLO(candidate)  # type: ignore[call-arg, assignment]
            self.available = True
        except Exception:
            # Fallback: disable gracefully when the model cannot be loaded
            self.model = None
            self.available = False

    def _serialize(self, detections: List[SceneObject]) -> Dict[str, Any]:
        labels = [det.label for det in detections]
        counts = Counter(labels)
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        summary = ", ".join(
            f"{count} {label}{'s' if count != 1 else ''}" for label, count in ordered
        )
        novel = sorted(set(labels) - set(self._last_labels))
        self._last_labels = labels
        payload: Dict[str, Any] = {
            "summary": summary,
            "objects": [det.__dict__ for det in detections],
        }
        if novel:
            payload["novel"] = novel
        return payload

    def describe(self, frame: Any) -> Optional[Dict[str, Any]]:
        if not self.available or self.model is None or frame is None or np is None:
            return None
        try:
            results = self.model.predict(frame, verbose=False, conf=self.confidence)
        except Exception:
            return None
        if not results:
            return None
        first = results[0]
        detections: List[SceneObject] = []
        names: Dict[int, str] = getattr(first, "names", getattr(self.model, "names", {})) or {}
        boxes = getattr(first, "boxes", None)
        if boxes is None:
            return None
        try:
            confs = boxes.conf.cpu().numpy()  # type: ignore[call-arg]
            classes = boxes.cls.cpu().numpy()  # type: ignore[call-arg]
            coords = boxes.xyxy.cpu().numpy()  # type: ignore[call-arg]
        except Exception:
            return None
        if confs is None or classes is None or coords is None:
            return None
        for idx, (confidence, cls, bbox) in enumerate(zip(confs, classes, coords)):
            if idx >= self.max_objects:
                break
            label = names.get(int(cls), str(int(cls)))
            detections.append(
                SceneObject(label=label, confidence=float(confidence), bbox=[float(x) for x in bbox])
            )
        if not detections:
            return None
        payload = self._serialize(detections)
        payload["timestamp"] = time.time()
        self._log(payload)
        return payload

    def _log(self, payload: Dict[str, Any]) -> None:
        try:
            prefix = os.getenv("JSON_DUMP_PREFIX", "")
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(prefix + json.dumps(payload) + "\n")
        except Exception:
            pass


__all__ = ["ObjectRecognitionModule", "SceneObject"]
