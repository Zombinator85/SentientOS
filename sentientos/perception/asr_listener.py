"""Lightweight streaming ASR listener with pluggable backends.

The real system is expected to integrate with hardware microphones and
Whisper-based transcription.  For the unit tests in this repository we emulate
audio input using simple sequences of floats.  The listener focuses on the
budgeting, gating and metrics responsibilities so the behaviour can be tested
reliably without external dependencies.
"""

from __future__ import annotations

import math
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable, List, Mapping, Optional

from sentientos.metrics import MetricsRegistry


@dataclass
class AudioConfig:
    """Configuration parameters for the ASR listener."""

    enable: bool = False
    backend: str = "whisper_local"
    vad: str = "rms"
    chunk_seconds: float = 25.0
    max_minutes_per_hour: float = 20.0
    max_concurrent: int = 1


class ASRBackend:
    """Interface implemented by concrete transcription backends."""

    name = "abstract"

    def transcribe(self, audio: List[float], sample_rate: int) -> Mapping[str, object]:
        raise NotImplementedError


class NullASRBackend(ASRBackend):
    name = "null"

    def transcribe(self, audio: List[float], sample_rate: int) -> Mapping[str, object]:
        return {"text": "", "confidence": 0.0, "language": None}


class CallableASRBackend(ASRBackend):
    """Backend that delegates to a callable; used primarily for testing."""

    def __init__(self, name: str, fn: Callable[[List[float], int], Mapping[str, object]]):
        self.name = name
        self._fn = fn

    def transcribe(self, audio: List[float], sample_rate: int) -> Mapping[str, object]:
        return dict(self._fn(audio, sample_rate))


class BudgetLimiter:
    """Sliding window limiter for minutes-per-hour guardrails."""

    def __init__(self, limit_minutes: float) -> None:
        self._limit = float(max(limit_minutes, 0.0))
        self._events: queue.Queue[float] = queue.Queue()
        self._lock = threading.Lock()

    def consume(self, duration_seconds: float, now: Optional[float] = None) -> bool:
        if self._limit <= 0:
            return True
        instant = time.time() if now is None else float(now)
        window_start = instant - 3600.0
        with self._lock:
            retained: List[float] = []
            try:
                while True:
                    event = self._events.get_nowait()
                    if event >= window_start:
                        retained.append(event)
            except queue.Empty:
                pass
            for event in retained:
                self._events.put(event)
            minutes_used = len(retained) * (duration_seconds / 60.0)
            projected = minutes_used + duration_seconds / 60.0
            if projected > self._limit:
                return False
            self._events.put(instant)
            return True


def _rms(samples: Iterable[float]) -> float:
    total = 0.0
    count = 0
    for sample in samples:
        total += float(sample) ** 2
        count += 1
    if count == 0:
        return 0.0
    return math.sqrt(total / count)


class ASRListener:
    """Chunk microphone audio and run gated transcriptions."""

    def __init__(
        self,
        config: AudioConfig,
        *,
        backend_factory: Callable[[str], ASRBackend] | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._config = config
        self._backend_factory = backend_factory or (lambda name: NullASRBackend())
        self._backend = self._backend_factory(config.backend)
        self._metrics = metrics or MetricsRegistry()
        self._chunk_seconds = max(float(config.chunk_seconds), 1.0)
        self._limiter = BudgetLimiter(config.max_minutes_per_hour)
        self._semaphore = threading.BoundedSemaphore(max(int(config.max_concurrent), 1))
        self._durations: list[tuple[float, float]] = []

    @property
    def backend_name(self) -> str:
        return getattr(self._backend, "name", "unknown")

    def process_samples(
        self,
        samples: List[float],
        *,
        sample_rate: int = 16000,
        started_at: float | None = None,
    ) -> Optional[Mapping[str, object]]:
        if not self._config.enable or not samples:
            return None
        started_ts = time.time() if started_at is None else float(started_at)
        duration = len(samples) / float(sample_rate)
        if duration > self._chunk_seconds:
            samples = samples[: int(self._chunk_seconds * sample_rate)]
            duration = len(samples) / float(sample_rate)
        loudness = _rms(samples)
        if self._config.vad == "rms" and loudness < 0.01:
            return None
        if not self._limiter.consume(duration):
            self._metrics.increment("sos_asr_dropped_total")
            return None
        if not self._semaphore.acquire(blocking=False):
            self._metrics.increment("sos_asr_dropped_total")
            return None
        try:
            start_time = time.perf_counter()
            result = self._backend.transcribe(samples, sample_rate)
            latency_ms = (time.perf_counter() - start_time) * 1000.0
        finally:
            self._semaphore.release()
        transcript = str(result.get("text", "")).strip()
        confidence = float(result.get("confidence", 0.0))
        language = result.get("language")
        if not transcript:
            return None
        observation = {
            "modality": "audio",
            "transcript": transcript,
            "confidence": confidence,
            "language": language,
            "started_at": started_ts,
            "duration_s": duration,
            "backend": self.backend_name,
        }
        now = time.time()
        self._durations.append((now, duration))
        self._prune_durations(now)
        self._metrics.increment("sos_asr_segments_total")
        self._metrics.observe("sos_asr_latency_ms", latency_ms)
        return observation

    def minutes_used(self) -> float:
        now = time.time()
        self._prune_durations(now)
        return sum(duration for _, duration in self._durations) / 60.0

    def status(self) -> Mapping[str, object]:
        return {
            "status": "healthy" if self._config.enable else "disabled",
            "backend": self.backend_name,
            "minutes_used": round(self.minutes_used(), 3),
            "max_minutes_per_hour": self._config.max_minutes_per_hour,
        }

    def _prune_durations(self, now: float) -> None:
        cutoff = now - 3600.0
        self._durations = [(ts, duration) for ts, duration in self._durations if ts >= cutoff]


__all__ = [
    "AudioConfig",
    "ASRBackend",
    "ASRListener",
    "CallableASRBackend",
    "NullASRBackend",
]

