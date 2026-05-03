"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
import os
LEGACY_PERCEPTION_QUARANTINE = True
PULSE_COMPATIBLE_TELEMETRY = True
PERCEPTION_AUTHORITY = "none"
RAW_RETENTION_DEFAULT = False
CAN_TRIGGER_ACTIONS = False
CAN_WRITE_MEMORY = True
EMBODIMENT_INGRESS_GATE_MODE = os.getenv("EMBODIMENT_INGRESS_GATE_MODE", "compatibility_legacy")
INGRESS_GATE_PRESENT = True
INGRESS_GATE_PROPOSAL_ONLY_SUPPORTED = True
LEGACY_DIRECT_MEMORY_WRITE_REQUIRES_EXPLICIT_MODE = True
MIGRATION_TARGET = "sentientos.perception_api"
NON_AUTHORITY_RATIONALE = "Legacy microphone capture still appends memory records; observation shaping now routes through sentientos.perception_api."


require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import json
import time
from pathlib import Path
from typing import Dict, Optional, TypedDict


from emotions import Emotion, empty_emotion_vector
import emotion_utils as eu
from utils import is_headless

try:
    import speech_recognition as sr
except Exception as e:  # pragma: no cover - dependency missing
    sr = None

if is_headless():
    sr = None

from memory_manager import append_memory
from sentientos.perception_api import emit_legacy_perception_telemetry, normalize_audio_observation
from sentientos.embodiment_fusion import build_embodiment_snapshot
from sentientos.embodiment_ingress import evaluate_embodiment_ingress, mark_legacy_direct_effect_preserved, should_allow_legacy_memory_write


class MicResult(TypedDict):
    message: str | None
    source: str
    audio_file: str | None
    emotions: Emotion
    emotion_features: Dict[str, float]
    ingress_receipt: Dict[str, object] | None

AUDIO_DIR = get_log_path("audio", "AUDIO_LOG_DIR")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def recognize_from_mic(save_audio: bool = True, ingress_gate_mode: str = EMBODIMENT_INGRESS_GATE_MODE) -> MicResult:
    """Capture a single phrase from the default microphone."""
    if sr is None:
        if is_headless():
            print("[MIC] Headless mode - skipping mic capture")
        else:
            print("[MIC] speech_recognition not available")
        return {
            "message": None,
            "source": "mic",
            "audio_file": None,
            "emotions": empty_emotion_vector(),
            "emotion_features": {},
        }

    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("[MIC] Listening...")
        audio = recognizer.listen(source)

    raw_data = None
    try:
        raw_data = audio.get_raw_data(convert_rate=16000, convert_width=2)
    except Exception:
        pass

    audio_path = None
    if save_audio:
        ts = time.strftime("%Y%m%d-%H%M%S")
        audio_path = AUDIO_DIR / f"mic_{ts}.wav"
        with open(audio_path, "wb") as f:
            f.write(audio.get_wav_data())

    if audio_path:
        emotions, features = eu.detect(str(audio_path))
    else:
        emotions, features = empty_emotion_vector(), {}

    text = None
    if hasattr(recognizer, "recognize_whisper"):
        try:
            text = recognizer.recognize_whisper(audio)
        except Exception:
            text = None
    if not text:
        try:
            text = recognizer.recognize_vosk(audio)
        except Exception:
            pass
    if not text:
        try:
            text = recognizer.recognize_sphinx(audio)
        except Exception:
            pass
    if not text:
        try:
            text = recognizer.recognize_google(audio)
        except Exception as e:
            print(f"[MIC] Recognition failed: {e}")
            text = None

    ingress_receipt = None
    if text:
        text_vec = eu.text_sentiment(text)
        audio_emotions = emotions
        fused = eu.fuse(emotions, text_vec)
        emotions = fused
    _obs = normalize_audio_observation(message=text, source="mic", audio_file=str(audio_path) if audio_path else None, emotion_features=features)
    _ = emit_legacy_perception_telemetry("audio", _obs, source_module="mic_bridge", can_write_memory=True, legacy_quarantine=True, quarantine_risk="memory_write")
    ingress_receipt = mark_legacy_direct_effect_preserved(evaluate_embodiment_ingress(build_embodiment_snapshot([_])), effect_type="memory_write", mode=ingress_gate_mode)
    if text and should_allow_legacy_memory_write(ingress_gate_mode):
        append_memory(
            text,
            tags=["voice", "input"],
            source="mic",
            emotions=emotions,
            emotion_features=features,
            emotion_breakdown={"audio": audio_emotions, "text": text_vec},
        )
    return {
        "message": text,
        "source": "mic",
        "audio_file": str(audio_path) if audio_path else None,
        "emotions": emotions,
        "emotion_features": features,
        "ingress_receipt": ingress_receipt,
    }


def recognize_from_file(path: str, ingress_gate_mode: str = EMBODIMENT_INGRESS_GATE_MODE) -> MicResult:
    """Recognize speech from a WAV file."""
    if sr is None:
        return {
            "message": None,
            "source": "file",
            "audio_file": path,
            "emotions": empty_emotion_vector(),
            "emotion_features": {},
        }

    recognizer = sr.Recognizer()
    with sr.AudioFile(path) as source:
        audio = recognizer.record(source)

    emotions, features = eu.detect(path)
    text = None
    try:
        text = recognizer.recognize_google(audio)
    except Exception:
        pass

    ingress_receipt = None
    if text:
        text_vec = eu.text_sentiment(text)
        audio_emotions = emotions
        fused = eu.fuse(emotions, text_vec)
        emotions = fused
    _obs = normalize_audio_observation(message=text, source="file", audio_file=path, emotion_features=features)
    _ = emit_legacy_perception_telemetry("audio", _obs, source_module="mic_bridge", can_write_memory=True, legacy_quarantine=True, quarantine_risk="memory_write")
    ingress_receipt = mark_legacy_direct_effect_preserved(evaluate_embodiment_ingress(build_embodiment_snapshot([_])), effect_type="memory_write", mode=ingress_gate_mode)
    if text and should_allow_legacy_memory_write(ingress_gate_mode):
        append_memory(
            text,
            tags=["voice", "input"],
            source="file",
            emotions=emotions,
            emotion_features=features,
            emotion_breakdown={"audio": audio_emotions, "text": text_vec},
        )
    return {
        "message": text,
        "source": "file",
        "audio_file": path,
        "emotions": emotions,
        "emotion_features": features,
        "ingress_receipt": ingress_receipt,
    }

if __name__ == "__main__":  # pragma: no cover - manual utility
    while True:
        result = recognize_from_mic()
        if result.get("message"):
            print(json.dumps(result, ensure_ascii=False))
