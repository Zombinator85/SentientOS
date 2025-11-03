"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import os
import json
import time
from pathlib import Path
from types import ModuleType
from logging_config import get_log_dir
from typing import Any, Dict, List, Optional, TypedDict, cast
from emotions import Emotion, empty_emotion_vector

# Local alias for log entries
LogEntry = Dict[str, Any]
from utils import is_headless

# Optional modules may not be present; declare with fallback None
sr: ModuleType | None
mic_bridge: ModuleType | None

# --- Optional Voice Backends ---
HEADLESS = is_headless()
try:
    import speech_recognition as sr_mod
    sr = sr_mod
except Exception:
    sr = None

try:
    import mic_bridge as mic_mod
    mic_bridge = mic_mod
except Exception:
    mic_bridge = None

if HEADLESS:
    sr = None
    mic_bridge = None

from perception_journal import PerceptionJournal
from scene_recognizer import ObjectRecognitionModule
from screen_awareness import ScreenAwareness
from vision_tracker import FaceEmotionTracker


class VoiceObservation(TypedDict, total=False):
    """Structured voice observation with optional transcript and features."""

    emotions: Emotion
    transcript: Optional[str]
    audio_file: Optional[str]
    emotion_features: Dict[str, float]

class PersonaMemory:
    def __init__(self) -> None:
        self.timelines: Dict[int, List[LogEntry]] = {}

    def add(self, person_id: int, source: str, emotions: Emotion, ts: float) -> None:
        if not emotions:
            return
        self.timelines.setdefault(person_id, []).append(
            {"timestamp": ts, "source": source, "emotions": emotions}
        )

    def average(self, person_id: int, source: Optional[str] = None, window: int = 5) -> Emotion:
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
    """Fuse vision, scene context, and voice observations into per-person timelines."""

    def __init__(
        self,
        enable_vision: bool = True,
        enable_voice: bool = False,
        enable_scene: bool = True,
        enable_screen: bool = True,
        camera_index: Optional[int] = 0,
        voice_device: Optional[int] = None,
        output_dir: Optional[str] = None,
        object_model: Optional[str] = None,
        scene_confidence: float = 0.3,
        perception_journal: Optional[PerceptionJournal] = None,
        screen_interval: float = 1.0,
        screen_awareness: Optional[ScreenAwareness] = None,
    ) -> None:
        if HEADLESS:
            enable_vision = False
            enable_voice = False
            enable_scene = False
            enable_screen = False
        default_dir = get_log_dir() / "multimodal"
        env_dir = os.getenv("MULTI_LOG_DIR")
        self.log_dir = Path(output_dir or env_dir or default_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.journal = perception_journal or PerceptionJournal()
        self.vision: Optional[FaceEmotionTracker]
        if enable_vision:
            try:
                self.vision = FaceEmotionTracker(camera_index=camera_index, output_file=None)
            except TypeError:
                self.vision = FaceEmotionTracker()
        else:
            self.vision = None
        # Decide which voice backend to use
        self.voice_backend: Optional[str] = None
        if enable_voice:
            if mic_bridge is not None:
                self.voice_backend = "mic_bridge"
            elif sr is not None:
                self.voice_backend = "speech_recognition"
            else:
                self.voice_backend = None
        self.scene: Optional[ObjectRecognitionModule] = None
        if enable_scene:
            scene_module = ObjectRecognitionModule(model_path=object_model, confidence=scene_confidence)
            if scene_module.available:
                self.scene = scene_module
        self.environment_log = self.log_dir / "environment.jsonl"
        self.screen_awareness: Optional[ScreenAwareness] = None
        self._last_screen_capture = 0.0
        if enable_screen:
            if screen_awareness is not None:
                self.screen_awareness = screen_awareness
            else:
                self.screen_awareness = ScreenAwareness(
                    interval=screen_interval,
                    log_path=self.log_dir / "screen_awareness.jsonl",
                    journal=self.journal,
                )
        self.memory = PersonaMemory()

    def _log(self, person_id: int, entry: LogEntry) -> None:
        path = self.log_dir / f"{person_id}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _log_environment(self, entry: Dict[str, Any]) -> None:
        try:
            with open(self.environment_log, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _record_journal(self, tags: List[str], note: str, extra: Optional[Dict[str, Any]] = None) -> None:
        try:
            self.journal.record(tags, note, extra=extra or {})
        except Exception:
            pass

    def analyze_voice(self, device_index: Optional[int] = None) -> VoiceObservation:
        if HEADLESS or not self.voice_backend:
            return VoiceObservation()
        if self.voice_backend == "mic_bridge":
            try:
                assert mic_bridge is not None
                res = mic_bridge.recognize_from_mic(save_audio=False)
                emotions_raw: Any = res.get("emotions") or {}
                emotions: Emotion = cast(Emotion, emotions_raw)
                return VoiceObservation(
                    emotions=emotions,
                    transcript=res.get("message"),
                    audio_file=res.get("audio_file"),
                    emotion_features=cast(Dict[str, float], res.get("emotion_features", {})),
                )
            except Exception:
                return VoiceObservation()
        elif self.voice_backend == "speech_recognition":
            try:
                assert sr is not None
                recognizer = sr.Recognizer()
                mic = sr.Microphone(device_index=device_index)
                with mic as source:
                    audio = recognizer.listen(source, phrase_time_limit=3)
                transcript: Optional[str] = None
                try:
                    transcript = recognizer.recognize_sphinx(audio)
                except Exception:
                    try:
                        transcript = recognizer.recognize_google(audio)
                    except Exception:
                        transcript = None
                return VoiceObservation(
                    emotions={},
                    transcript=transcript,
                    audio_file=None,
                    emotion_features={},
                )
            except Exception:
                return VoiceObservation()
        return VoiceObservation()

    def process_once(self, frame: Any) -> LogEntry:
        ts = time.time()
        voice_obs = self.analyze_voice()
        voice_vec = cast(Emotion, voice_obs.get("emotions", {}))
        transcript = voice_obs.get("transcript")
        scene_data = self.scene.describe(frame) if self.scene and frame is not None else None
        screen_snapshot = None
        if self.screen_awareness and ts - self._last_screen_capture >= self.screen_awareness.interval:
            screen_snapshot = self.screen_awareness.capture_once()
            self._last_screen_capture = ts
        # --- Always produce a timestamped log, even if no vision or voice
        data = self.vision.process_frame(frame) if self.vision and frame is not None else {"faces": []}
        data["timestamp"] = ts
        if voice_vec:
            self.memory.add(0, "voice", voice_vec, ts)
        if scene_data:
            data["scene"] = scene_data
            summary = scene_data.get("summary")
            if summary:
                self._record_journal(["vision", "scene"], summary, extra=scene_data)
            if scene_data.get("novel"):
                novel = ", ".join(scene_data["novel"])
                self._record_journal(["vision", "novelty"], f"New objects spotted: {novel}", extra=scene_data)
        if transcript:
            data["voice_transcript"] = transcript
            self._record_journal(["audio", "speech"], transcript, extra={"source": self.voice_backend or "unknown"})
        data["voice"] = voice_vec
        if screen_snapshot:
            screen_payload = {
                "text": screen_snapshot.text,
                "summary": screen_snapshot.summary(),
                "ocr_confidence": screen_snapshot.ocr_confidence,
                "width": screen_snapshot.width,
                "height": screen_snapshot.height,
            }
            data["screen"] = screen_payload
        if not data.get("faces"):
            entry: LogEntry = {"timestamp": ts, "vision": {}, "voice": voice_vec or {}}
            if scene_data:
                entry["scene"] = scene_data
            if transcript:
                entry["voice_transcript"] = transcript
            if screen_snapshot:
                entry["screen"] = screen_payload
            self._log(0, entry)
        for face in data.get("faces", []):
            fid = face["id"]
            emotions = face.get("emotions", empty_emotion_vector())
            self.memory.add(fid, "vision", emotions, ts)
            if voice_vec:
                self.memory.add(fid, "voice", voice_vec, ts)
            entry: LogEntry = {"timestamp": ts, "vision": emotions, "voice": voice_vec}
            if transcript:
                entry["voice_transcript"] = transcript
            if screen_snapshot:
                entry["screen"] = screen_payload
            self._log(fid, entry)
        env_entry: Dict[str, Any] = {"timestamp": ts}
        if voice_vec:
            env_entry["voice"] = voice_vec
        if transcript:
            env_entry["voice_transcript"] = transcript
        if voice_obs.get("audio_file"):
            env_entry["voice_audio_file"] = voice_obs.get("audio_file")
        if voice_obs.get("emotion_features"):
            env_entry["voice_features"] = voice_obs.get("emotion_features")
        if scene_data:
            env_entry["scene"] = scene_data
        if screen_snapshot:
            env_entry["screen"] = screen_payload
        if len(env_entry) > 1:
            self._log_environment(env_entry)
        return data

    def update_text_sentiment(self, person_id: int, sentiment: Emotion) -> None:
        self.memory.add(person_id, "text", sentiment, time.time())

    def run(self, max_frames: Optional[int] = None) -> None:
        if not self.vision or not getattr(self.vision, "cap", None):
            if HEADLESS:
                print("[MULTIMODAL] Headless mode - skipping capture")
            else:
                print("[MULTIMODAL] Camera not available")
            return
        frames = 0
        while True:
            assert self.vision is not None and self.vision.cap is not None
            ret, frame = self.vision.cap.read()
            if not ret:
                break
            self.process_once(frame)
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
        assert self.vision is not None and self.vision.cap is not None
        self.vision.cap.release()
