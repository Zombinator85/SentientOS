from logging_config import get_log_path
import os
import json
import time
from pathlib import Path
from typing import Dict, Optional


from emotions import empty_emotion_vector
import emotion_utils as eu
from utils import is_headless

try:
    import speech_recognition as sr
except Exception as e:  # pragma: no cover - dependency missing
    sr = None

if is_headless():
    sr = None

from memory_manager import append_memory

AUDIO_DIR = get_log_path("audio", "AUDIO_LOG_DIR")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def recognize_from_mic(save_audio: bool = True) -> Dict[str, Optional[str]]:
    """Capture a single phrase from the default microphone."""
    if sr is None:
        if is_headless():
            print("[MIC] Headless mode - skipping mic capture")
        else:
            print("[MIC] speech_recognition not available")
        return {"message": None, "source": "mic", "audio_file": None}

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

    if text:
        text_vec = eu.text_sentiment(text)
        fused = eu.fuse(emotions, text_vec)
        append_memory(
            text,
            tags=["voice", "input"],
            source="mic",
            emotions=fused,
            emotion_features=features,
            emotion_breakdown={"audio": emotions, "text": text_vec},
        )
        emotions = fused

    return {
        "message": text,
        "source": "mic",
        "audio_file": str(audio_path) if audio_path else None,
        "emotions": emotions,
        "emotion_features": features,
    }


def recognize_from_file(path: str) -> Dict[str, Optional[str]]:
    """Recognize speech from a WAV file."""
    if sr is None:
        return {"message": None, "source": "file", "audio_file": path}

    recognizer = sr.Recognizer()
    with sr.AudioFile(path) as source:
        audio = recognizer.record(source)

    emotions, features = eu.detect(path)
    text = None
    try:
        text = recognizer.recognize_google(audio)
    except Exception:
        pass

    if text:
        text_vec = eu.text_sentiment(text)
        fused = eu.fuse(emotions, text_vec)
        append_memory(
            text,
            tags=["voice", "input"],
            source="file",
            emotions=fused,
            emotion_features=features,
            emotion_breakdown={"audio": emotions, "text": text_vec},
        )
        emotions = fused

    return {
        "message": text,
        "source": "file",
        "audio_file": path,
        "emotions": emotions,
        "emotion_features": features,
    }

if __name__ == "__main__":  # pragma: no cover - manual utility
    while True:
        result = recognize_from_mic()
        if result.get("message"):
            print(json.dumps(result, ensure_ascii=False))
