"""Lightweight speech-to-text helpers used by the WebRTC bridge tests."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Sequence


@dataclass(frozen=True)
class TranscriptionEvent:
    """Represents a unit of text emitted by the streaming recogniser."""

    text: str
    final: bool
    timestamp: float


class StreamingTranscriber:
    """Very small placeholder VAD/transcription pipeline used in tests.

    The production build relies on dedicated audio models, however for the
    repository tests we simulate the behaviour with UTF-8 payloads. Every
    newline terminates an utterance, otherwise partial transcripts are emitted
    as non-final events.
    """

    def __init__(self, *, vad_sensitivity: float = 0.6) -> None:
        self._vad_sensitivity = vad_sensitivity
        self._buffer: List[str] = []
        self._active = False
        self._last_emit: float = 0.0

    @property
    def vad_sensitivity(self) -> float:
        return self._vad_sensitivity

    @property
    def is_active(self) -> bool:
        return self._active

    def submit_audio(self, chunk: bytes | str) -> Sequence[TranscriptionEvent]:
        if not chunk:
            return []
        if isinstance(chunk, bytes):
            try:
                decoded = chunk.decode("utf-8")
            except UnicodeDecodeError:
                decoded = ""
        else:
            decoded = chunk
        if not decoded:
            return []
        timestamp = time.time()
        self._last_emit = timestamp
        events: List[TranscriptionEvent] = []
        for symbol in decoded.splitlines(True):
            if symbol.endswith("\n"):
                text = ("".join(self._buffer) + symbol.rstrip("\n")).strip()
                self._buffer.clear()
                self._active = False
                if text:
                    events.append(TranscriptionEvent(text=text, final=True, timestamp=timestamp))
            else:
                self._buffer.append(symbol)
                text = "".join(self._buffer).strip()
                if text:
                    self._active = True
                    events.append(TranscriptionEvent(text=text, final=False, timestamp=timestamp))
        return events

    def flush(self) -> Sequence[TranscriptionEvent]:
        if not self._buffer:
            self._active = False
            return []
        timestamp = time.time()
        text = "".join(self._buffer).strip()
        self._buffer.clear()
        self._active = False
        if not text:
            return []
        self._last_emit = timestamp
        return [TranscriptionEvent(text=text, final=True, timestamp=timestamp)]

    def reset(self) -> None:
        self._buffer.clear()
        self._active = False
        self._last_emit = 0.0


__all__ = ["StreamingTranscriber", "TranscriptionEvent"]
