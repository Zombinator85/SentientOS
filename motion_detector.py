"""Motion detection utilities for SentientOS camera streams."""
from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

_np_spec = importlib.util.find_spec("numpy")
np = importlib.import_module("numpy") if _np_spec is not None else None

_cv2_spec = importlib.util.find_spec("cv2")
cv2 = importlib.import_module("cv2") if _cv2_spec is not None else None


@dataclass
class MotionDetectionResult:
    """Result returned when motion is detected."""

    timestamp: datetime
    score: float
    mask: Any = None


class MotionDetector:
    """Simple frame differencing detector with background adaptation."""

    def __init__(
        self,
        sensitivity: float = 0.12,
        learning_rate: float = 0.05,
        minimum_pixels: int = 500,
    ) -> None:
        if sensitivity <= 0 or sensitivity >= 1:
            raise ValueError("sensitivity must be between 0 and 1")
        if learning_rate <= 0 or learning_rate >= 1:
            raise ValueError("learning_rate must be between 0 and 1")
        if minimum_pixels <= 0:
            raise ValueError("minimum_pixels must be positive")
        self.sensitivity = sensitivity
        self.learning_rate = learning_rate
        self.minimum_pixels = minimum_pixels
        self._background: Optional[Any] = None

    def _to_gray(self, frame: Any) -> Any:
        if np is not None:
            arr = np.asarray(frame)
            if arr.ndim == 2:
                return arr.astype(np.float32)
            if arr.ndim == 3 and arr.shape[2] >= 3:
                if cv2 is not None:
                    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
                    return gray.astype(np.float32)
                weights = np.array([0.2989, 0.5870, 0.1140], dtype=np.float32)
                return np.tensordot(arr[..., :3], weights, axes=([-1], [0])).astype(np.float32)
            raise ValueError("unsupported frame shape")
        # Fallback: treat frame as nested lists
        if not frame:
            raise ValueError("empty frame")
        if isinstance(frame[0][0], (int, float)):
            return [[float(value) for value in row] for row in frame]
        # assume RGB structure
        weights = (0.2989, 0.5870, 0.1140)
        return [
            [
                float(pixel[0] * weights[0] + pixel[1] * weights[1] + pixel[2] * weights[2])
                for pixel in row
            ]
            for row in frame
        ]

    def update(self, frame: Any, timestamp: Optional[datetime] = None) -> MotionDetectionResult | None:
        """Process a frame and return a detection if motion surpasses the threshold."""

        ts = timestamp or datetime.utcnow()
        gray = self._to_gray(frame)
        if self._background is None:
            if np is not None:
                self._background = gray
            else:
                self._background = [row[:] for row in gray]
            return None

        if np is not None:
            diff = np.abs(gray - self._background)
            if cv2 is not None:
                diff = cv2.GaussianBlur(diff, (5, 5), 0)
            score = float(diff.mean() / 255.0)
            changed = diff > (self.sensitivity * 255.0)
            changed_pixels = int(np.count_nonzero(changed))
            self._background = (1 - self.learning_rate) * self._background + self.learning_rate * gray
            if changed_pixels < self.minimum_pixels:
                return None
            return MotionDetectionResult(timestamp=ts, score=score, mask=changed)

        height = len(gray)
        width = len(gray[0]) if height else 0
        diff_total = 0.0
        changed_pixels = 0
        for y in range(height):
            row = gray[y]
            bg_row = self._background[y]
            for x in range(width):
                value = abs(row[x] - bg_row[x])
                diff_total += value
                if value > self.sensitivity * 255.0:
                    changed_pixels += 1
                bg_row[x] = (1 - self.learning_rate) * bg_row[x] + self.learning_rate * row[x]
        score = diff_total / max(1.0, height * width * 255.0)
        if changed_pixels < self.minimum_pixels:
            return None
        return MotionDetectionResult(timestamp=ts, score=score, mask=None)


__all__ = ["MotionDetector", "MotionDetectionResult"]
