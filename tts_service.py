"""Utilities to model a streaming TTS pipeline for tests."""

from __future__ import annotations

from typing import Callable, Iterator, Sequence


class TtsStreamer:
    """Produces deterministic byte streams representing spoken text."""

    def __init__(self, voice: str = "en_US-amy-medium", *, chunk_size: int = 32) -> None:
        self.voice = voice
        self.chunk_size = max(8, int(chunk_size))

    def synthesize(self, text: str) -> Iterator[bytes]:
        payload = text.strip()
        if not payload:
            return iter(())
        data = payload.encode("utf-8")
        for idx in range(0, len(data), self.chunk_size):
            yield data[idx : idx + self.chunk_size]

    def stream(self, text: str, consumer: Callable[[bytes], None]) -> None:
        for chunk in self.synthesize(text):
            consumer(chunk)

    def speak(self, text: str) -> Sequence[bytes]:
        return list(self.synthesize(text))


__all__ = ["TtsStreamer"]
