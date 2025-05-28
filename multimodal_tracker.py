import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import speech_recognition as sr  # type: ignore
except Exception:  # pragma: no cover - optional
    sr = None

from emotion_utils import detect, empty_emotion_vector
from vision_tracker import FaceEmotionTracker


class VoiceSentiment:
    """Lightweight wrapper around speech_recognition and emotion_utils."""

    def __init__(self, device_index: Optional[int] = None) -> None:
        self.device_index = device_index
        if sr is not None:
            try:
                self.recognizer = sr.Recognizer()
                self.mic = sr.Microphone(device_index=device_index)
            except Exception:  # pragma: no cover - mic missing
                self.recognizer = None
                self.mic = None
        else:  # pragma: no cover - dependency missing
            self.recognizer = None
            self.mic = None

    def listen(self) -> Dict[str, float]:
        if not self.recognizer or not self.mic:
            return {}
        try:
            with self.mic as source:
                audio = self.recognizer.listen(source, phrase_time_limit=3)
            data = audio.get_wav_data()
        except Exception:  # pragma: no cover - capture failure
            return {}
        path = Path("/tmp") / f"voice_{int(time.time()*1000)}.wav"
        try:
            with open(path, "wb") as f:
                f.write(data)
            vec, _ = detect(str(path))
        finally:
            if path.exists():
                path.unlink()
        return vec


class MultiModalEmotionTracker:
    """Fuse vision and voice sentiment into per-person timelines."""

    def __init__(
        self,
        enable_vision: bool = True,
        enable_voice: bool = False,
        camera_index: Optional[int] = 0,
        voice_device: Optional[int] = None,
        output_file: Optional[str] = None,
    ) -> None:
        self.log_path = Path(
            output_file or os.getenv("MULTIMODAL_LOG", "logs/multimodal/multi.jsonl")
        )
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.vision = (
            FaceEmotionTracker(camera_index=camera_index, output_file=None)
            if enable_vision
            else None
        )
        self.voice = VoiceSentiment(voice_device) if enable_voice else None
        self.timelines: Dict[int, List[Dict[str, Any]]] = {}

    def _log(self, data: Dict[str, Any]) -> None:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data) + "\n")

    def process(self, frame=None) -> Dict[str, Any]:
        ts = time.time()
        entry: Dict[str, Any] = {"timestamp": ts, "faces": []}
        if self.vision and frame is not None:
            vis = self.vision.process_frame(frame)
            entry["faces"] = vis.get("faces", [])
            for face in entry["faces"]:
                fid = face["id"]
                self.timelines.setdefault(fid, []).append({
                    "timestamp": ts,
                    "vision": face.get("emotions", empty_emotion_vector()),
                })
        if self.voice:
            vec = self.voice.listen()
            if vec:
                entry["audio"] = vec
                self.timelines.setdefault(0, []).append({
                    "timestamp": ts,
                    "audio": vec,
                })
        self._log(entry)
        return entry

    def run(self, max_frames: Optional[int] = None) -> None:  # pragma: no cover - loop
        frames = 0
        while True:
            frame = None
            if self.vision and self.vision.cap:
                ret, frame = self.vision.cap.read()
                if not ret:
                    break
            self.process(frame)
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
        if self.vision and self.vision.cap:
            self.vision.cap.release()
