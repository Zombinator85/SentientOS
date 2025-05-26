import os
import time
from pathlib import Path
from typing import Optional

try:
    import pyttsx3
except Exception as e:  # pragma: no cover - dependency missing
    pyttsx3 = None

from memory_manager import append_memory

AUDIO_DIR = Path(os.getenv("AUDIO_LOG_DIR", "logs/audio"))
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

if pyttsx3 is not None:  # pragma: no cover - avoid running in tests
    ENGINE = pyttsx3.init()
else:
    ENGINE = None


def speak(text: str, voice: Optional[str] = None, save_path: Optional[str] = None) -> Optional[str]:
    """Synthesize text to speech and optionally save to a file."""
    if ENGINE is None:
        print("[TTS] pyttsx3 not available")
        return None
    if voice:
        try:
            ENGINE.setProperty("voice", voice)
        except Exception:
            print(f"[TTS] voice '{voice}' not found")
    if save_path is None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        save_path = str(AUDIO_DIR / f"tts_{ts}.mp3")

    ENGINE.save_to_file(text, save_path)
    ENGINE.say(text)
    ENGINE.runAndWait()

    append_memory(text, tags=["voice", "output"], source="tts")
    return save_path


if __name__ == "__main__":  # pragma: no cover - manual utility
    speak("Hello from SentientOS")

