"""Screen awareness helper capturing text via OCR.

The implementation favours determinism and testability.  Real screen capture
hooks are abstracted behind callables that the unit tests can stub.  The module
tracks hashes of captures to avoid redundant OCR work and exposes observations
compatible with the memory manager.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Optional

from sentientos.metrics import MetricsRegistry


@dataclass
class ScreenConfig:
    enable: bool = False
    interval_s: float = 2.0
    ocr_backend: str = "tesseract"
    max_chars_per_minute: int = 5000


class ScreenCaptureError(RuntimeError):
    pass


class ScreenOCR:
    """Track textual updates on the operator's screen."""

    def __init__(
        self,
        config: ScreenConfig,
        *,
        capture_fn: Callable[[], Mapping[str, str]] | None = None,
        ocr_fn: Callable[[Mapping[str, str]], str] | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._config = config
        self._capture_fn = capture_fn or (lambda: {"data": ""})
        self._ocr_fn = ocr_fn or (lambda payload: str(payload.get("data", "")))
        self._metrics = metrics or MetricsRegistry()
        self._last_hash: str | None = None
        self._chars_window: list[tuple[float, int]] = []
        self._last_text: str | None = None

    def snapshot(self) -> Optional[Mapping[str, object]]:
        if not self._config.enable:
            return None
        try:
            payload = self._capture_fn()
        except Exception as exc:  # pragma: no cover - defensive
            raise ScreenCaptureError(str(exc)) from exc
        raw_bytes = str(payload).encode("utf-8")
        digest = hashlib.sha256(raw_bytes).hexdigest()
        if digest == self._last_hash:
            return None
        self._last_hash = digest
        text = self._ocr_fn(payload)
        text = (text or "").strip()
        if not text:
            return None
        now = time.time()
        self._chars_window.append((now, len(text)))
        self._prune_window(now)
        char_total = sum(count for _, count in self._chars_window)
        limit = max(int(self._config.max_chars_per_minute), 1)
        if char_total > limit:
            self._metrics.increment("sos_screen_ocr_throttled_total")
            return None
        observation = {
            "modality": "screen",
            "text": text,
            "window_title": payload.get("title"),
            "captured_at": now,
            "backend": self._config.ocr_backend,
        }
        self._last_text = text
        self._metrics.increment("sos_screen_captures_total")
        self._metrics.increment("sos_screen_ocr_chars_total", len(text))
        return observation

    def _prune_window(self, now: float) -> None:
        cutoff = now - 60.0
        self._chars_window = [(ts, count) for ts, count in self._chars_window if ts >= cutoff]

    def status(self) -> Mapping[str, object]:
        return {
            "status": "healthy" if self._config.enable else "disabled",
            "ocr_backend": self._config.ocr_backend,
            "last_text_preview": (self._last_text or "")[:64],
        }


__all__ = ["ScreenConfig", "ScreenOCR", "ScreenCaptureError"]

