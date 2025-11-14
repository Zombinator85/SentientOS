"""pyttsx3 based offline text-to-speech wrapper."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Optional

try:  # pragma: no cover - optional dependency in runtime environments
    import pyttsx3  # type: ignore
except Exception:  # pragma: no cover - fallback when library unavailable
    pyttsx3 = None  # type: ignore[assignment]

LOGGER = logging.getLogger("sentientos.voice.tts")


@dataclass
class TtsConfig:
    enabled: bool = False
    rate: int = 180
    volume: float = 1.0
    voice_name: Optional[str] = None


class TtsEngine:
    """Minimal pyttsx3 wrapper that honours :class:`TtsConfig`."""

    def __init__(self, config: TtsConfig):
        self._config = config
        self._engine = None
        self._init_lock = threading.Lock()
        self._initialised = False

    @property
    def config(self) -> TtsConfig:
        return self._config

    @property
    def available(self) -> bool:
        return self._engine is not None

    def _ensure_engine(self):
        if self._engine is not None or not self._config.enabled:
            return self._engine

        with self._init_lock:
            if self._engine is not None:
                return self._engine
            if not self._config.enabled:
                return None
            if self._initialised:
                return self._engine
            self._initialised = True

            if pyttsx3 is None:
                LOGGER.warning("pyttsx3 is unavailable; TTS disabled")
                return None

            try:
                engine = pyttsx3.init()
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning("Failed to initialise pyttsx3: %s", exc)
                return None

            try:
                engine.setProperty("rate", int(self._config.rate))
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning("Failed to set TTS rate: %s", exc)
            try:
                engine.setProperty("volume", float(self._config.volume))
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning("Failed to set TTS volume: %s", exc)

            voice_name = self._config.voice_name
            if voice_name:
                try:
                    voices = engine.getProperty("voices") or []
                except Exception as exc:  # pragma: no cover - defensive logging
                    LOGGER.warning("Failed to enumerate system voices: %s", exc)
                else:
                    match_id: Optional[str] = None
                    lowered = voice_name.lower()
                    for voice in voices:
                        name = str(getattr(voice, "name", "") or "")
                        if name.lower() == lowered:
                            match_id = str(getattr(voice, "id", name) or name)
                            break
                    if match_id:
                        try:
                            engine.setProperty("voice", match_id)
                        except Exception as exc:  # pragma: no cover - defensive logging
                            LOGGER.warning("Failed to apply requested voice '%s': %s", voice_name, exc)
                    else:
                        LOGGER.info("Requested voice '%s' not found; using default", voice_name)

            self._engine = engine
        return self._engine

    def speak(self, text: str) -> None:
        """Speak ``text`` using pyttsx3 when enabled."""

        if not self._config.enabled or not text:
            return

        engine = self._ensure_engine()
        if engine is None:
            return

        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("TTS playback failed: %s", exc)
