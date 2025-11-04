"""Queued TTS speaker with safety rate-limiting."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Mapping, Optional

from sentientos.metrics import MetricsRegistry

MOOD_PRESETS: Mapping[str, Mapping[str, float]] = {
    "calm": {"pitch": -0.10, "rate": -0.10, "volume": 0.0},
    "alert": {"pitch": 0.20, "rate": 0.10, "volume": 0.10},
    "sad": {"pitch": -0.15, "rate": -0.12, "volume": -0.05},
    "joyful": {"pitch": 0.10, "rate": 0.05, "volume": 0.05},
    "neutral": {"pitch": 0.0, "rate": 0.0, "volume": 0.0},
}

EXPRESSIVENESS_SCALE: Mapping[str, float] = {
    "low": 0.5,
    "medium": 1.0,
    "high": 1.5,
}


@dataclass
class TTSPersonality:
    expressiveness: str = "medium"
    baseline_mood: str = "calm"
    dynamic_voice: bool = True


@dataclass
class TTSConfig:
    enable: bool = False
    backend: str = "espeak"
    max_chars_per_minute: int = 2000
    cooldown_seconds: float = 5.0
    personality: TTSPersonality = field(default_factory=TTSPersonality)


class TTSError(RuntimeError):
    pass


class TTSSpeaker:
    def __init__(
        self,
        config: TTSConfig,
        *,
        backend_factory: Callable[[str], Callable[..., None]] | None = None,
        metrics: MetricsRegistry | None = None,
        mood_provider: Callable[[], Optional[str]] | None = None,
    ) -> None:
        self._config = config
        self._backend_factory = backend_factory or (lambda name: (lambda text, **_: None))
        self._speak_fn = self._backend_factory(config.backend)
        self._queue: Deque[tuple[str, Optional[str], Optional[str]]] = deque()
        self._last_spoken: float | None = None
        self._chars_window: list[tuple[float, int]] = []
        self._metrics = metrics or MetricsRegistry()
        self._mood_provider = mood_provider
        self._last_voice: Mapping[str, object] | None = None

    def enqueue(
        self,
        text: str,
        *,
        corr_id: str | None = None,
        dedupe: bool = True,
        mood: Optional[str] = None,
    ) -> None:
        if not self._config.enable:
            return
        text = text.strip()
        if not text:
            return
        if dedupe and any(existing == text for existing, _, __ in self._queue):
            return
        self._queue.append((text, corr_id, mood))

    def drain(self) -> list[Mapping[str, object]]:
        if not self._config.enable:
            return []
        spoken: list[Mapping[str, object]] = []
        now = time.time()
        while self._queue:
            text, corr_id, mood_hint = self._queue[0]
            if not self._can_speak(now, len(text)):
                break
            self._queue.popleft()
            resolved_mood, voice_params = self._prepare_voice_parameters(mood_hint)
            self._speak(text, voice_params)
            record = {
                "text": text,
                "corr_id": corr_id,
                "timestamp": now,
                "backend": self._config.backend,
                "voice": {
                    "mood": resolved_mood,
                    "modifiers": voice_params,
                },
            }
            spoken.append(record)
            self._metrics.increment("sos_tts_lines_spoken_total")
            now = time.time()
        if self._queue and spoken:
            self._metrics.increment("sos_tts_dropped_total", 0.0)
        return spoken

    def _can_speak(self, now: float, char_count: int) -> bool:
        if self._last_spoken is not None:
            if now - self._last_spoken < self._config.cooldown_seconds:
                return False
        self._chars_window = [(ts, cnt) for ts, cnt in self._chars_window if ts >= now - 60.0]
        total_chars = sum(cnt for _, cnt in self._chars_window)
        limit = max(int(self._config.max_chars_per_minute), 1)
        if total_chars + char_count > limit:
            self._metrics.increment("sos_tts_dropped_total")
            return False
        return True

    def _prepare_voice_parameters(self, mood_hint: Optional[str]) -> tuple[str, Mapping[str, float]]:
        baseline = (self._config.personality.baseline_mood or "neutral").strip().lower()
        mood = (mood_hint or baseline).strip().lower()
        if self._config.personality.dynamic_voice and self._mood_provider is not None:
            try:
                observed = self._mood_provider()
            except Exception:  # pragma: no cover - defensive against user providers
                observed = None
            if observed:
                mood = str(observed).strip().lower() or mood
        if mood not in MOOD_PRESETS:
            mood = "neutral"
        modifiers = self.voice_parameters_for_mood(mood)
        return mood, modifiers

    def voice_parameters_for_mood(self, mood: str) -> Mapping[str, float]:
        base = MOOD_PRESETS.get(mood.lower(), MOOD_PRESETS["neutral"])
        scale = EXPRESSIVENESS_SCALE.get(
            self._config.personality.expressiveness.lower(),
            EXPRESSIVENESS_SCALE["medium"],
        )
        return {key: round(value * scale, 4) for key, value in base.items()}

    def _speak(self, text: str, voice_params: Mapping[str, float]) -> None:
        try:
            self._invoke_backend(text, voice_params)
        except Exception as exc:  # pragma: no cover
            raise TTSError(str(exc)) from exc
        now = time.time()
        self._last_spoken = now
        self._chars_window.append((now, len(text)))
        self._last_voice = {"text": text, "modifiers": dict(voice_params)}

    def _invoke_backend(self, text: str, voice_params: Mapping[str, float]) -> None:
        try:
            self._speak_fn(text, voice_params=voice_params)
        except TypeError:
            self._speak_fn(text)

    @property
    def queue_length(self) -> int:
        return len(self._queue)

    def status(self) -> Mapping[str, object]:
        status = "healthy" if self._config.enable else "disabled"
        speaking = bool(self._last_spoken and (time.time() - self._last_spoken) < self._config.cooldown_seconds)
        return {
            "status": status,
            "backend": self._config.backend,
            "queue_len": self.queue_length,
            "speaking": speaking,
        }

    @property
    def last_voice_signature(self) -> Mapping[str, object] | None:
        return self._last_voice


__all__ = ["TTSConfig", "TTSPersonality", "TTSSpeaker", "TTSError"]

