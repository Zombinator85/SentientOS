"""Lightweight streaming ASR listener with pluggable backends.

The real system is expected to integrate with hardware microphones and
Whisper-based transcription.  For the unit tests in this repository we emulate
audio input using simple sequences of floats.  The listener focuses on the
budgeting, gating and metrics responsibilities so the behaviour can be tested
reliably without external dependencies.
"""

from __future__ import annotations

import json
import math
import queue
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

from runtime_mode import SENTIENTOS_MODE
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
    sample_rate: int = 16000
    frame_seconds: float = 0.25
    buffer_seconds: float = 5.0
    silence_rms: float = 0.01
    silence_hangover_s: float = 0.5


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
        self._mic_status: Mapping[str, object] = {
            "state": "idle",
            "mode": SENTIENTOS_MODE,
        }

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
        if self._config.vad == "rms" and loudness < self._config.silence_rms:
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

    @property
    def mic_status(self) -> Mapping[str, object]:
        return dict(self._mic_status)

    def run_microphone(
        self,
        *,
        audio_source: Optional[Iterable[Tuple[Sequence[float], int]]] = None,
        pulse_path: Path | str = Path("/pulse/system.json"),
        stop_after: float | None = None,
        mode: str | None = None,
    ) -> Mapping[str, object]:
        runner = _MicrophoneRunner(
            config=self._config,
            listener=self,
            metrics=self._metrics,
            pulse_path=Path(pulse_path),
            mode=mode or SENTIENTOS_MODE,
        )
        status = runner.run(audio_source=audio_source, stop_after=stop_after)
        self._mic_status = status
        return status

    def _prune_durations(self, now: float) -> None:
        cutoff = now - 3600.0
        self._durations = [(ts, duration) for ts, duration in self._durations if ts >= cutoff]


class _MicrophoneRunner:
    def __init__(
        self,
        *,
        config: AudioConfig,
        listener: ASRListener,
        metrics: MetricsRegistry,
        pulse_path: Path,
        mode: str,
    ) -> None:
        self._config = config
        self._listener = listener
        self._metrics = metrics
        self._pulse_path = pulse_path
        self._mode = mode
        self._status: Mapping[str, object] = {
            "state": "idle",
            "mode": mode,
            "reason": "awaiting initialization",
            "backend": listener.backend_name,
        }
        self._capture_backend: str | None = None
        self._device: str | None = None

    def run(
        self,
        *,
        audio_source: Optional[Iterable[Tuple[Sequence[float], int]]] = None,
        stop_after: float | None = None,
    ) -> Mapping[str, object]:
        if not self._config.enable:
            return self._update_status("disabled", "audio capture disabled by configuration")
        if self._mode != "LOCAL_OWNER":
            return self._update_status(
                "muted",
                "microphone gated by SENTIENTOS_MODE",
                warnings=["microphone present but gated"],
            )
        try:
            stream = audio_source or self._probe_microphone()
        except Exception as exc:  # pragma: no cover - hardware/driver failures
            return self._update_status("error", f"microphone error: {exc}")
        if stream is None:
            return self._update_status("unavailable", "no microphone detected")

        self._update_status("listening", "microphone active")
        elapsed = 0.0
        buffer: list[float] = []
        speech_deadline: float | None = None
        started_at: float | None = None
        max_buffer = max(float(self._config.buffer_seconds), float(self._config.frame_seconds))
        max_samples = max(int(max_buffer * self._config.sample_rate), 1)
        frame_seconds = max(float(self._config.frame_seconds), 0.05)

        for samples, sample_rate in stream:
            chunk = [float(value) for value in samples]
            buffer.extend(chunk)
            if len(buffer) > max_samples:
                buffer = buffer[-max_samples:]
            frame_duration = len(chunk) / float(sample_rate or 1)
            elapsed += frame_duration
            self._metrics.increment("sos_asr_microphone_frames_total")
            loudness = _rms(chunk)
            if loudness >= self._config.silence_rms:
                if started_at is None:
                    started_at = elapsed - frame_duration
                speech_deadline = elapsed + self._config.silence_hangover_s
            if speech_deadline is not None and elapsed >= speech_deadline:
                trimmed = self._trim_silence(buffer, sample_rate)
                if trimmed:
                    started = started_at if started_at is not None else elapsed - (len(trimmed) / float(sample_rate))
                    self._listener.process_samples(list(trimmed), sample_rate=sample_rate, started_at=started)
                buffer.clear()
                speech_deadline = None
                started_at = None
            if stop_after is not None and elapsed >= stop_after:
                break
            if audio_source is None and frame_duration < frame_seconds:
                time.sleep(max(frame_seconds - frame_duration, 0.0))

        try:
            close_fn = getattr(stream, "close", None)
            if callable(close_fn):
                close_fn()
        except Exception:
            pass

        if buffer and speech_deadline is not None:
            trimmed = self._trim_silence(buffer, self._config.sample_rate)
            if trimmed:
                started = started_at if started_at is not None else elapsed - (len(trimmed) / float(self._config.sample_rate))
                self._listener.process_samples(list(trimmed), sample_rate=self._config.sample_rate, started_at=started)
        return self._update_status("idle", "microphone loop completed")

    def _probe_microphone(self) -> Iterator[Tuple[Sequence[float], int]] | None:
        return self._sounddevice_stream() or self._pyaudio_stream()

    def _sounddevice_stream(self) -> Iterator[Tuple[Sequence[float], int]] | None:
        try:  # pragma: no cover - optional dependency
            import sounddevice as sd

            devices = sd.query_devices()
            input_devices = [d for d in devices if d.get("max_input_channels", 0) > 0]
            if not input_devices:
                return None
            self._capture_backend = "sounddevice"
            self._device = str(input_devices[0].get("name") or "default")

            def generator() -> Iterator[Tuple[Sequence[float], int]]:
                blocksize = max(int(self._config.sample_rate * self._config.frame_seconds), 256)
                with sd.InputStream(
                    channels=1,
                    samplerate=self._config.sample_rate,
                    blocksize=blocksize,
                    dtype="float32",
                ) as stream:
                    while True:
                        frames, _ = stream.read(blocksize)
                        try:
                            channel = frames[:, 0]
                            payload = channel.tolist()
                        except Exception:
                            payload = [float(x) for x in frames]
                        yield payload, self._config.sample_rate

            return generator()
        except Exception:
            return None

    def _pyaudio_stream(self) -> Iterator[Tuple[Sequence[float], int]] | None:
        try:  # pragma: no cover - optional dependency
            import pyaudio

            audio = pyaudio.PyAudio()
            device_index = None
            for idx in range(audio.get_device_count()):
                info = audio.get_device_info_by_index(idx)
                if info.get("maxInputChannels", 0) > 0:
                    device_index = idx
                    break
            if device_index is None:
                return None
            info = audio.get_device_info_by_index(device_index)
            self._capture_backend = "pyaudio"
            self._device = str(info.get("name") or device_index)

            frames_per_buffer = max(int(self._config.sample_rate * self._config.frame_seconds), 256)

            def generator() -> Iterator[Tuple[Sequence[float], int]]:
                stream = audio.open(
                    format=pyaudio.paFloat32,
                    channels=1,
                    rate=self._config.sample_rate,
                    input=True,
                    frames_per_buffer=frames_per_buffer,
                    input_device_index=device_index,
                )
                try:
                    while True:
                        raw = stream.read(frames_per_buffer, exception_on_overflow=False)
                        data = struct.unpack(f"<{frames_per_buffer}f", raw)
                        yield data, self._config.sample_rate
                finally:
                    stream.stop_stream()
                    stream.close()
                    audio.terminate()

            return generator()
        except Exception:
            return None

    def _trim_silence(self, samples: Sequence[float], sample_rate: int) -> Sequence[float]:
        if not samples:
            return []
        window = max(int(sample_rate * 0.02), 1)
        start = 0
        end = len(samples)
        while start + window <= len(samples) and _rms(samples[start : start + window]) < self._config.silence_rms:
            start += window
        while end - window >= start and _rms(samples[end - window : end]) < self._config.silence_rms:
            end -= window
        return samples[start:end]

    def _update_status(
        self,
        state: str,
        reason: str,
        *,
        warnings: Optional[Sequence[str]] = None,
    ) -> Mapping[str, object]:
        status = {
            "state": state,
            "reason": reason,
            "mode": self._mode,
            "backend": self._listener.backend_name,
            "timestamp": time.time(),
        }
        if self._capture_backend:
            status["capture_backend"] = self._capture_backend
        if self._device:
            status["device"] = self._device
        if warnings:
            status["warnings"] = list(warnings)
        self._status = status
        self._write_pulse_state(status)
        return status

    def _write_pulse_state(self, status: Mapping[str, object]) -> None:
        base: dict[str, object] = {
            "focus": {},
            "context": {},
            "events": [],
            "warnings": [],
        }
        state: dict[str, object]
        try:
            existing = json.loads(self._pulse_path.read_text())
            state = existing if isinstance(existing, dict) else dict(base)
        except FileNotFoundError:
            state = dict(base)
        except json.JSONDecodeError:
            state = dict(base)
        state.setdefault("focus", {})
        state.setdefault("context", {})
        state.setdefault("events", [])
        state.setdefault("warnings", [])
        devices = state.setdefault("devices", {})
        devices["microphone"] = status
        self._pulse_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._pulse_path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(state, sort_keys=True))
            tmp.replace(self._pulse_path)
        except Exception:
            try:
                tmp.unlink()
            except Exception:
                pass


__all__ = [
    "AudioConfig",
    "ASRBackend",
    "ASRListener",
    "CallableASRBackend",
    "NullASRBackend",
]

