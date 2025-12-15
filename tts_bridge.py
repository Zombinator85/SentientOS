"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Bridge module for text-to-speech engines."""

from logging_config import get_log_path
import os
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any
import threading
import random
import asyncio
from sentientos.parliament_bus import Turn
from runtime_mode import IS_LOCAL_OWNER, SENTIENTOS_MODE
from speech_to_avatar_bridge import SpeechToAvatarBridge

try:
    from TTS.api import TTS  # Coqui TTS, optional dependency
except Exception:
    TTS = None

try:  # optional edge-tts dependency
    from edge_tts import Communicate as EdgeCommunicate  # type: ignore[import-untyped]
except Exception:
    EdgeCommunicate = None
Communicate: Any = EdgeCommunicate

try:
    import requests  # type: ignore[import-untyped]  # used for ElevenLabs
except Exception:
    requests = None  # type: ignore[misc]  # requests missing

try:  # Bark TTS optional
    from bark import generate_audio  # type: ignore[import-untyped]  # Bark library has no stubs
except Exception:
    generate_audio = None

try:
    import pyttsx3
except Exception:
    pyttsx3 = None

from memory_manager import append_memory
from emotions import empty_emotion_vector
from utils import is_headless

AUDIO_DIR = get_log_path("audio", "AUDIO_LOG_DIR")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

_CYCLE_ID = uuid.uuid4().hex
_TURN_ID = 0

ENGINE_TYPE = os.getenv("TTS_ENGINE", "pyttsx3")
HEADLESS = is_headless()
_AVATAR_BRIDGE: SpeechToAvatarBridge | None = SpeechToAvatarBridge()

ELEVEN_KEY = os.getenv("ELEVEN_API_KEY")
ELEVEN_VOICE = os.getenv("ELEVEN_VOICE", "Rachel")
BARK_SPEAKER = os.getenv("BARK_SPEAKER", "v2/en_speaker_6")
EDGE_VOICE = os.getenv("EDGE_VOICE", "en-US-GuyNeural")

if ENGINE_TYPE == "coqui" and TTS is not None:
    COQUI_MODEL = os.getenv("TTS_COQUI_MODEL", "tts_models/en/vctk/vits")
    ENGINE = TTS(model_name=COQUI_MODEL)
    DEFAULT_VOICE = None
    ALT_VOICE = None
elif ENGINE_TYPE == "elevenlabs" and requests is not None and ELEVEN_KEY and not HEADLESS:
    ENGINE = "elevenlabs"
    DEFAULT_VOICE = ELEVEN_VOICE
    ALT_VOICE = ELEVEN_VOICE
elif ENGINE_TYPE == "bark" and generate_audio is not None and not HEADLESS:
    ENGINE = "bark"
    DEFAULT_VOICE = BARK_SPEAKER
    ALT_VOICE = BARK_SPEAKER
elif ENGINE_TYPE == "edge-tts" and Communicate is not None and not HEADLESS:
    ENGINE = "edge-tts"
    DEFAULT_VOICE = EDGE_VOICE
    ALT_VOICE = EDGE_VOICE
elif pyttsx3 is not None and not HEADLESS:
    ENGINE = pyttsx3.init()
    VOICES = ENGINE.getProperty("voices")
    DEFAULT_VOICE = VOICES[0].id if VOICES else None
    ALT_VOICE = VOICES[1].id if len(VOICES) > 1 else DEFAULT_VOICE
else:
    ENGINE = None
    DEFAULT_VOICE = None
    ALT_VOICE = None

# Current persona/voice style used when "voice" argument is omitted
CURRENT_PERSONA = DEFAULT_VOICE

def set_voice_persona(name: str) -> None:
    """Change the default voice/persona used for speech."""
    global CURRENT_PERSONA
    CURRENT_PERSONA = name

def adapt_persona(trend_vec: Dict[str, float]) -> None:
    """Adjust persona according to emotion trend."""
    global CURRENT_PERSONA
    if trend_vec.get("Sadness", 0) > 0.2 and ALT_VOICE:
        set_voice_persona(ALT_VOICE)
    elif trend_vec.get("Joy", 0) > 0.2 and DEFAULT_VOICE:
        set_voice_persona(DEFAULT_VOICE)

def speak(
    text: str,
    voice: Optional[str] = None,
    save_path: Optional[str] = None,
    emotions: Optional[Dict[str, float]] = None,
    style: Optional[str] = None,
) -> Optional[str]:
    """Synthesize text to speech and optionally save to a file."""
    spoken = text.strip()
    if not spoken:
        return None

    muted = HEADLESS or ENGINE is None or IS_LOCAL_OWNER
    if _AVATAR_BRIDGE:
        _AVATAR_BRIDGE.handle_event({"text": spoken, "muted": muted, "mode": SENTIENTOS_MODE, "started_at": time.time()})

    if HEADLESS:
        print("[TTS] Headless mode - skipping synthesis")
        if _AVATAR_BRIDGE:
            _AVATAR_BRIDGE.handle_event({"event": "end"})
        return None
    if IS_LOCAL_OWNER:
        print("[TTS] LOCAL_OWNER mode - suppressing playback")
        if _AVATAR_BRIDGE:
            _AVATAR_BRIDGE.handle_event({"event": "end"})
        return None
    if ENGINE is None:
        print("[TTS] no TTS engine available")
        if _AVATAR_BRIDGE:
            _AVATAR_BRIDGE.handle_event({"event": "end"})
        return None
    emotions = emotions or empty_emotion_vector()
    chosen_voice = voice or CURRENT_PERSONA
    if chosen_voice is None:
        if emotions.get("Sadness", 0) > 0.6:
            chosen_voice = ALT_VOICE
        elif emotions.get("Anger", 0) > 0.6 or emotions.get("Joy", 0) > 0.5:
            chosen_voice = DEFAULT_VOICE
    if ENGINE_TYPE == "pyttsx3" and chosen_voice:
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
    # Coqui doesn't take rate directly, but we can modulate speed in kwargs below

    global _TURN_ID
    if save_path is None:
        _TURN_ID += 1
        ext = ".wav" if ENGINE_TYPE in {"bark", "coqui"} else ".mp3"
        demo_dir = Path("demos") / "audio" / _CYCLE_ID
        demo_dir.mkdir(parents=True, exist_ok=True)
        save_path = str(demo_dir / f"{_TURN_ID}{ext}")

    if ENGINE_TYPE == "coqui" and TTS is not None:
        speed = rate / 150.0
        kwargs = {"file_path": save_path, "speed": speed}
        if voice:
            kwargs["speaker_wav"] = voice
        ENGINE.tts_to_file(text, **kwargs)
    elif ENGINE_TYPE == "elevenlabs" and requests is not None and ELEVEN_KEY:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE}"
        headers = {"xi-api-key": ELEVEN_KEY}
        resp = requests.post(url, json={"text": text}, headers=headers, timeout=30)
        if resp.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(resp.content)
        else:
            print("[TTS] ElevenLabs request failed")
            return None
    elif ENGINE_TYPE == "bark" and generate_audio is not None:
        audio_arr = generate_audio(text, history_prompt=BARK_SPEAKER)
        if hasattr(audio_arr, "save"):
            audio_arr.save(save_path)
        else:
            from scipy.io.wavfile import write as wavwrite  # type: ignore[import-untyped]  # scipy optional for bark
            wavwrite(save_path, 22050, audio_arr)
    elif ENGINE_TYPE == "edge-tts" and Communicate is not None:
        async def _edge_run() -> None:
            comm = Communicate(text=text, voice=chosen_voice, style=style)
            await comm.save(save_path)

        asyncio.run(_edge_run())
    elif ENGINE_TYPE == "pyttsx3":
        ENGINE.save_to_file(text, save_path)
        ENGINE.say(text)
        ENGINE.runAndWait()
    else:
        print("[TTS] No usable TTS engine found")
        return None

    append_memory(
        text,
        tags=["voice", "output"],
        source="tts",
        emotions=emotions,
        emotion_features={},
    )
    if _AVATAR_BRIDGE:
        _AVATAR_BRIDGE.handle_event({"event": "end"})
    return save_path

def speak_async(
    text: str,
    voice: Optional[str] = None,
    save_path: Optional[str] = None,
    emotions: Optional[Dict[str, float]] = None,
    style: Optional[str] = None,
) -> threading.Thread:
    """Speak in a background thread."""
    t = threading.Thread(target=speak, args=(text,), kwargs={"voice": voice, "save_path": save_path, "emotions": emotions, "style": style})
    t.start()
    return t


PARALINGUISTIC = ["mm-hmm", "uh-huh", "*sigh*", "*breath*"]


def backchannel(emotions: Optional[Dict[str, float]] = None) -> Optional[threading.Thread]:
    """Inject a short non-verbal utterance asynchronously."""
    if HEADLESS or ENGINE is None:
        return None
    cue = random.choice(PARALINGUISTIC)
    return speak_async(cue, emotions=emotions)


EMOTION_STYLES = {
    "joy": {"style": "cheerful"},
    "anger": {"style": "angry"},
    "sadness": {"style": "sad"},
}

EMOTION_VOICES = {
    "joy": DEFAULT_VOICE,
    "anger": ALT_VOICE or DEFAULT_VOICE,
    "sadness": ALT_VOICE or DEFAULT_VOICE,
}


def speak_turn(turn: "Turn") -> Optional[str]:
    """Speak a :class:`Turn` using its emotion tag for style."""
    emotion = (turn.emotion or "").lower()
    mapping = EMOTION_STYLES.get(emotion, {})
    style = mapping.get("style")
    voice = EMOTION_VOICES.get(emotion, DEFAULT_VOICE)
    return speak(turn.text, voice=voice, emotions=None, style=style)

def stop() -> None:
    """Stop current speech playback if supported."""
    if ENGINE_TYPE == "pyttsx3" and ENGINE is not None:
        ENGINE.stop()

if __name__ == "__main__":  # pragma: no cover - manual utility
    speak("Hello from SentientOS")
