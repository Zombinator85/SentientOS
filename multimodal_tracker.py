import os
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from emotions import empty_emotion_vector
from vision_tracker import FaceEmotionTracker

try:
    import mic_bridge  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    mic_bridge = None


class PersonaMemory:
    """Per-person emotion timeline for multiple modalities."""

    def __init__(self) -> None:
        self.timelines: Dict[int, List[Dict[str, Any]]] = {}

    def add(self, person_id: int, source: str, emotions: Dict[str, float], ts: float) -> None:
        if not emotions:
            return
        self.timelines.setdefault(person_id, []).append(
            {"timestamp": ts, "source": source, "emotions": emotions}
        )

    def average(self, person_id: int, source: str | None = None, window: int = 5) -> Dict[str, float]:
        hist = [h["emotions"] for h in self.timelines.get(person_id, []) if source is None or h["source"] == source]
        hist = hist[-window:]
        avg = empty_emotion_vector()
        if not hist:
            return avg
        for h in hist:
            for k, v in h.items():
                avg[k] = avg.get(k, 0.0) + v
        for k in avg:
            avg[k] /= len(hist)
        return avg


class MultiModalEmotionTracker:
    """Fuse vision and voice emotion tracking with persona memory."""

    def __init__(self, camera_index: Optional[int] = 0, output_dir: str | None = None) -> None:
        self.face_tracker = FaceEmotionTracker(camera_index=camera_index, output_file=None)
        self.voice_available = mic_bridge is not None
        self.log_dir = Path(output_dir or os.getenv("MULTI_LOG_DIR", "logs/multimodal"))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.memory = PersonaMemory()

    def _log(self, person_id: int, entry: Dict[str, Any]) -> None:
        path = self.log_dir / f"{person_id}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def analyze_voice(self) -> Dict[str, float]:
        if not self.voice_available or mic_bridge is None:
            return {}
        try:
            res = mic_bridge.recognize_from_mic(save_audio=False)
            return res.get("emotions") or {}
        except Exception:
            return {}

    def process_once(self, frame) -> Dict[str, Any]:
        ts = time.time()
        voice_vec = self.analyze_voice()
        data = self.face_tracker.process_frame(frame)
        for face in data.get("faces", []):
            fid = face["id"]
            self.memory.add(fid, "vision", face.get("emotions", {}), ts)
            if voice_vec:
                self.memory.add(fid, "voice", voice_vec, ts)
            self._log(fid, {"timestamp": ts, "vision": face.get("emotions", {}), "voice": voice_vec})
        return data

    def update_text_sentiment(self, person_id: int, sentiment: Dict[str, float]) -> None:
        self.memory.add(person_id, "text", sentiment, time.time())

    def run(self, max_frames: Optional[int] = None) -> None:  # pragma: no cover - realtime loop
        if self.face_tracker.cap is None:
            print("[MULTIMODAL] Camera not available")
            return
        frames = 0
        while True:
            ret, frame = self.face_tracker.cap.read()
            if not ret:
                break
            self.process_once(frame)
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
        self.face_tracker.cap.release()
