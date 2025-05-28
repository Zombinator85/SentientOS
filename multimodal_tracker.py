import os
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# --- Optional Voice Backends ---
try:
    import speech_recognition as sr  # for default, simple use
except Exception:
    sr = None

try:
    import mic_bridge  # for advanced/plug-in use
except Exception:
    mic_bridge = None

from vision_tracker import FaceEmotionTracker

def empty_emotion_vector() -> Dict[str, float]:
    # You may already have this, but for safety:
    return {e: 0.0 for e in ["happy", "sad", "angry", "disgust", "fear", "surprise", "neutral"]}

class PersonaMemory:
    """Per-person emotion timeline for multiple modalities."""
    def __init__(self):
        self.timelines: Dict[int, List[Dict[str, Any]]] = {}

    def add(self, person_id: int, source: str, emotions: Dict[str, float], ts: float) -> None:
        if not emotions:
            return
        self.timelines.setdefault(person_id, []).append(
            {"timestamp": ts, "source": source, "emotions": emotions}
        )

    def average(self, person_id: int, source: Optional[str] = None, window: int = 5) -> Dict[str, float]:
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
    """Fuse vision and voice sentiment into per-person timelines."""

    def __init__(
        self,
        enable_vision: bool = True,
        enable_voice: bool = False,
        camera_index: Optional[int] = 0,
        voice_device: Optional[int] = None,
        output_dir: Optional[str] = None,
    ) -> None:
        self.log_dir = Path(output_dir or os.getenv("MULTI_LOG_DIR", "logs/multimodal"))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        if enable_vision:
            try:
                self.vision = FaceEmotionTracker(camera_index=camera_index, output_file=None)
            except TypeError:  # pragma: no cover - for simple stubs
                self.vision = FaceEmotionTracker()
        else:
            self.vision = None
        # Decide which voice backend to use
        self.voice_backend = None
        if enable_voice:
            if mic_bridge is not None:
                self.voice_backend = "mic_bridge"
            elif sr is not None:
                self.voice_backend = "speech_recognition"
            else:
                self.voice_backend = None
        self.memory = PersonaMemory()

    def _log(self, person_id: int, entry: Dict[str, Any]) -> None:
        path = self.log_dir / f"{person_id}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def analyze_voice(self, device_index: Optional[int] = None) -> Dict[str, float]:
        if not self.voice_backend:
            return {}
        if self.voice_backend == "mic_bridge":
            try:
                res = mic_bridge.recognize_from_mic(save_audio=False)
                return res.get("emotions") or {}
            except Exception:
                return {}
        elif self.voice_backend == "speech_recognition":
            try:
                recognizer = sr.Recognizer()
                mic = sr.Microphone(device_index=device_index)
                with mic as source:
                    audio = recognizer.listen(source, phrase_time_limit=3)
                # Optional: save to temp file, pass to emotion utils if desired
                # Placeholder: return empty for now, extend with emotion model later
                return {}
            except Exception:
                return {}
        return {}

    def process_once(self, frame) -> Dict[str, Any]:
        ts = time.time()
        voice_vec = self.analyze_voice()
        data = self.vision.process_frame(frame) if self.vision and frame is not None else {"faces": []}
        data["timestamp"] = ts
        if not data.get("faces") and voice_vec:
            self.memory.add(0, "voice", voice_vec, ts)
            self._log(0, {"timestamp": ts, "vision": {}, "voice": voice_vec})
        elif not data.get("faces"):
            self._log(0, {"timestamp": ts, "vision": {}, "voice": {}})
        for face in data.get("faces", []):
            fid = face["id"]
            self.memory.add(fid, "vision", face.get("emotions", empty_emotion_vector()), ts)
            if voice_vec:
                self.memory.add(fid, "voice", voice_vec, ts)
            self._log(fid, {"timestamp": ts, "vision": face.get("emotions", {}) or empty_emotion_vector(), "voice": voice_vec})
        return data

    def update_text_sentiment(self, person_id: int, sentiment: Dict[str, float]) -> None:
        self.memory.add(person_id, "text", sentiment, time.time())

    def run(self, max_frames: Optional[int] = None) -> None:
        if not self.vision or not getattr(self.vision, "cap", None):
            print("[MULTIMODAL] Camera not available")
            return
        frames = 0
        while True:
            ret, frame = self.vision.cap.read()
            if not ret:
                break
            self.process_once(frame)
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
        self.vision.cap.release()
