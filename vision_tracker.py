"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import os
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from logging_config import get_log_path
from utils import is_headless

HEADLESS = is_headless()

try:
    import cv2  # type: ignore[import-untyped]  # OpenCV optional
    import mediapipe as mp  # type: ignore[import-untyped]  # mediapipe missing stubs
    from insightface.app import FaceAnalysis  # type: ignore[import-untyped]  # third-party lib
    from fer import FER  # type: ignore[import-untyped]  # FER emotion detector
    import numpy as np  # type: ignore[import-untyped]  # numpy for arrays
except Exception:  # pragma: no cover - optional dependencies
    cv2 = None
    mp = None
    FaceAnalysis = None
    FER = None
    np = None

if HEADLESS:
    cv2 = None
    mp = None
    FaceAnalysis = None
    FER = None
    np = None

from typing import TYPE_CHECKING
if TYPE_CHECKING:  # pragma: no cover - type hint only
    from feedback import FeedbackManager

def _iou(box_a: List[int], box_b: List[int]) -> float:
    """Return intersection-over-union of two boxes."""
    xA = max(box_a[0], box_b[0])
    yA = max(box_a[1], box_b[1])
    xB = min(box_a[2], box_b[2])
    yB = min(box_a[3], box_b[3])
    inter = max(0, xB - xA) * max(0, yB - yA)
    area_a = max(0, box_a[2] - box_a[0]) * max(0, box_a[3] - box_a[1])
    area_b = max(0, box_b[2] - box_b[0]) * max(0, box_b[3] - box_b[1])
    union = float(area_a + area_b - inter)
    return inter / union if union else 0.0

class FaceEmotionTracker:
    """Detect, identify, and track faces with emotion analysis and optional feedback."""

    def __init__(
        self,
        camera_index: Optional[int] = 0,
        output_file: str | None = None,
        feedback: "FeedbackManager | None" = None,
    ) -> None:
        if output_file:
            self.log_path = Path(output_file)
        else:
            self.log_path = get_log_path("vision/vision.jsonl", "VISION_LOG")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if HEADLESS:
            self.cap = None
        else:
            self.cap = cv2.VideoCapture(camera_index) if camera_index is not None and cv2 else None
        if HEADLESS:
            self.detector = None
            self.recognizer = None
            self.emotion = None
        else:
            self.detector = (
                mp.solutions.face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5)
                if mp
                else None
            )
            if FaceAnalysis:
                self.recognizer = FaceAnalysis(name="buffalo_l")
                try:
                    self.recognizer.prepare(ctx_id=0, det_size=(640, 640))
                except Exception:  # pragma: no cover - setup failure
                    self.recognizer = None
            else:
                self.recognizer = None
            self.emotion = FER(mtcnn=False) if FER else None
        self.tracked: Dict[int, Dict[str, Any]] = {}
        self.histories: Dict[int, List[Dict[str, float]]] = {}
        self.feedback = feedback
        self.next_id = 0

    def _assign_id(self, bbox: List[int]) -> int:
        best_id = None
        best_iou = 0.0
        for fid, data in self.tracked.items():
            iou = _iou(bbox, data["bbox"])
            if iou > best_iou:
                best_iou = iou
                best_id = fid
        if best_id is None or best_iou < 0.3:
            best_id = self.next_id
            self.next_id += 1
        self.tracked[best_id] = {"bbox": bbox}
        return best_id

    def _analyze_emotion(self, face_img) -> Dict[str, float]:
        if self.emotion is None:
            return {}
        try:
            result = self.emotion.detect_emotions(face_img)
            if result:
                return {k: float(v) for k, v in result[0]["emotions"].items()}
        except Exception:
            pass  # pragma: no cover - detector failure
        return {}

    def process_frame(self, frame) -> Dict[str, Any]:
        ts = time.time()
        faces: List[Dict[str, Any]] = []
        if self.detector and cv2:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = self.detector.process(rgb)
            detections = res.detections or []
            for det in detections:
                bb = det.location_data.relative_bounding_box
                x1 = int(bb.xmin * frame.shape[1])
                y1 = int(bb.ymin * frame.shape[0])
                w = int(bb.width * frame.shape[1])
                h = int(bb.height * frame.shape[0])
                x2 = x1 + w
                y2 = y1 + h
                crop = frame[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
                fid = self._assign_id([x1, y1, x2, y2])
                emotions = self._analyze_emotion(crop)
                if emotions:
                    self.histories.setdefault(fid, []).append(emotions)
                    if self.feedback:
                        self.feedback.process(fid, emotions)
                faces.append(
                    {
                        "id": fid,
                        "bbox": [x1, y1, x2, y2],
                        "emotions": emotions,
                        "dominant": max(emotions, key=lambda k: emotions[k]) if emotions else None,
                    }
                )
        return {"timestamp": ts, "faces": faces}

    def log_result(self, data: Dict[str, Any]) -> None:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data) + "\n")

    def update_voice_sentiment(self, face_id: int, sentiment: Dict[str, float]) -> None:
        """Optionally update emotional history and feedback from voice sentiment."""
        self.histories.setdefault(face_id, []).append(sentiment)
        if self.feedback:
            self.feedback.process(face_id, sentiment)

    def run(self, max_frames: int | None = None) -> None:
        if self.cap is None:
            if HEADLESS:
                print("[VISION] Headless mode - skipping vision capture")
            else:
                print("[VISION] OpenCV or camera not available")
            return
        frames = 0
        while True:
            ret, frame = self.cap.read()
            if not ret:
                break
            data = self.process_frame(frame)
            self.log_result(data)
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
        self.cap.release()
