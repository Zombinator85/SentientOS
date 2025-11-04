"""Queued TTS speaker with safety rate-limiting."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Mapping, Optional

from sentientos.metrics import MetricsRegistry


@dataclass
class TTSConfig:
    enable: bool = False
    backend: str = "espeak"
    max_chars_per_minute: int = 2000
    cooldown_seconds: float = 5.0


class TTSError(RuntimeError):
    pass


class TTSSpeaker:
    def __init__(
        self,
        config: TTSConfig,
        *,
        backend_factory: Callable[[str], Callable[[str], None]] | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._config = config
        self._backend_factory = backend_factory or (lambda name: lambda text: None)
        self._speak_fn = self._backend_factory(config.backend)
        self._queue: Deque[tuple[str, Optional[str]]] = deque()
        self._last_spoken: float | None = None
        self._chars_window: list[tuple[float, int]] = []
        self._metrics = metrics or MetricsRegistry()

    def enqueue(self, text: str, *, corr_id: str | None = None, dedupe: bool = True) -> None:
        if not self._config.enable:
            return
        text = text.strip()
        if not text:
            return
        if dedupe and any(existing == text for existing, _ in self._queue):
            return
        self._queue.append((text, corr_id))

    def drain(self) -> list[Mapping[str, object]]:
        if not self._config.enable:
            return []
        spoken: list[Mapping[str, object]] = []
        now = time.time()
        while self._queue:
            text, corr_id = self._queue[0]
            if not self._can_speak(now, len(text)):
                break
            self._queue.popleft()
            self._speak(text)
            record = {
                "text": text,
                "corr_id": corr_id,
                "timestamp": now,
                "backend": self._config.backend,
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

    def _speak(self, text: str) -> None:
        try:
            self._speak_fn(text)
        except Exception as exc:  # pragma: no cover
            raise TTSError(str(exc)) from exc
        now = time.time()
        self._last_spoken = now
        self._chars_window.append((now, len(text)))

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


__all__ = ["TTSConfig", "TTSSpeaker", "TTSError"]

