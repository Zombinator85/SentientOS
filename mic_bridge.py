import os
import json
import time
from pathlib import Path
from typing import Dict, Optional

import audioop

from emotions import empty_emotion_vector

try:
    import speech_recognition as sr
except Exception as e:  # pragma: no cover - dependency missing
    sr = None

from memory_manager import append_memory

AUDIO_DIR = Path(os.getenv("AUDIO_LOG_DIR", "logs/audio"))
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

def detect_emotions_from_audio(data: bytes, sample_width: int = 2) -> Dict[str, float]:
    """Return a simple emotion vector based on RMS volume."""
    vec = empty_emotion_vector()
    if not data:
        return vec
    try:
        rms = audioop.rms(data, sample_width)
    except Exception:
        return vec
    if rms < 500:
        vec["Sadness"] = 1.0
    elif rms > 3000:
        vec["Anger"] = min(1.0, (rms - 3000) / 7000)
        vec["Enthusiasm"] = 0.8
    else:
        vec["Contentment"] = 0.6
    return vec

def recognize_from_mic(save_audio: bool = True) -> Dict[str, Optional[str]]:
    """Capture a single phrase from the default microphone."""
    if sr is None:
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
    emotions = detect_emotions_from_audio(raw_data) if raw_data else empty_emotion_vector()

    audio_path = None
    if save_audio:
        ts = time.strftime("%Y%m%d-%H%M%S")
        audio_path = AUDIO_DIR / f"mic_{ts}.wav"
        with open(audio_path, "wb") as f:
            f.write(audio.get_wav_data())

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
        append_memory(text, tags=["voice", "input"], source="mic", emotions=emotions)

    return {
        "message": text,
        "source": "mic",
        "audio_file": str(audio_path) if audio_path else None,
        "emotions": emotions,
    }

if __name__ == "__main__":  # pragma: no cover - manual utility
    while True:
        result = recognize_from_mic()
        if result.get("message"):
            print(json.dumps(result, ensure_ascii=False))
