import os
import time
from pathlib import Path
from typing import Optional, Dict
import threading

try:
    from TTS.api import TTS  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    TTS = None

try:
    import pyttsx3
except Exception as e:  # pragma: no cover - dependency missing
    pyttsx3 = None

from memory_manager import append_memory
from emotions import empty_emotion_vector

AUDIO_DIR = Path(os.getenv("AUDIO_LOG_DIR", "logs/audio"))
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

ENGINE_TYPE = os.getenv("TTS_ENGINE", "pyttsx3")
if ENGINE_TYPE == "coqui" and TTS is not None:
    COQUI_MODEL = os.getenv("TTS_COQUI_MODEL", "tts_models/en/vctk/vits")
    ENGINE = TTS(model_name=COQUI_MODEL)
    DEFAULT_VOICE = None
    ALT_VOICE = None
elif pyttsx3 is not None:
    ENGINE = pyttsx3.init()
    VOICES = ENGINE.getProperty("voices")
    DEFAULT_VOICE = VOICES[0].id if VOICES else None
    ALT_VOICE = VOICES[1].id if len(VOICES) > 1 else DEFAULT_VOICE
else:
    ENGINE = None
    DEFAULT_VOICE = None
    ALT_VOICE = None


def speak(
    text: str,
    voice: Optional[str] = None,
    save_path: Optional[str] = None,
    emotions: Optional[Dict[str, float]] = None,
) -> Optional[str]:
    """Synthesize text to speech and optionally save to a file."""
    if ENGINE is None:
        print("[TTS] no TTS engine available")
        return None
    emotions = emotions or empty_emotion_vector()
    chosen_voice = voice
    if chosen_voice is None:
        if emotions.get("Sadness", 0) > 0.6:
            chosen_voice = ALT_VOICE
        elif emotions.get("Anger", 0) > 0.6:
            chosen_voice = DEFAULT_VOICE
    if chosen_voice:
        try:
            ENGINE.setProperty("voice", chosen_voice)
        except Exception:
            print(f"[TTS] voice '{chosen_voice}' not found")

    rate = 150
    if emotions.get("Anger", 0) > 0.6:
        rate = 180
    elif emotions.get("Sadness", 0) > 0.6:
        rate = 120
    elif emotions.get("Enthusiasm", 0) > 0.6:
        rate = 170
    if ENGINE_TYPE == "pyttsx3":
        ENGINE.setProperty("rate", rate)

    if save_path is None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        save_path = str(AUDIO_DIR / f"tts_{ts}.mp3")

    if ENGINE_TYPE == "coqui":
        speed = rate / 150.0
        kwargs = {"file_path": save_path, "speed": speed}
        if voice:
            kwargs["speaker_wav"] = voice
        ENGINE.tts_to_file(text, **kwargs)
    else:
        ENGINE.save_to_file(text, save_path)
        ENGINE.say(text)
        ENGINE.runAndWait()

    append_memory(text, tags=["voice", "output"], source="tts", emotions=emotions)
    return save_path


def speak_async(
    text: str,
    voice: Optional[str] = None,
    save_path: Optional[str] = None,
    emotions: Optional[Dict[str, float]] = None,
) -> threading.Thread:
    """Speak in a background thread."""
    t = threading.Thread(target=speak, args=(text,), kwargs={"voice": voice, "save_path": save_path, "emotions": emotions})
    t.start()
    return t


def stop() -> None:
    """Stop current speech playback if supported."""
    if ENGINE_TYPE == "pyttsx3" and ENGINE is not None:
        ENGINE.stop()


if __name__ == "__main__":  # pragma: no cover - manual utility
    speak("Hello from SentientOS")

