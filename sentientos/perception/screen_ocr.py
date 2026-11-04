"""Screen awareness helper capturing text via OCR.

The implementation favours determinism and testability.  Real screen capture
hooks are abstracted behind callables that the unit tests can stub.  The module
tracks hashes of captures to avoid redundant OCR work and exposes observations
compatible with the memory manager.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from sentientos.metrics import MetricsRegistry

_SAFE_FAILURE_CODE = re.compile(r"^[a-z0-9_]{1,128}$")
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def _failure_code(exc: BaseException, fallback: str) -> str:
    if isinstance(exc, ScreenCaptureError):
        candidate = str(exc)
        if _SAFE_FAILURE_CODE.fullmatch(candidate):
            return candidate
    return fallback


@dataclass
class ScreenConfig:
    enable: bool = False
    interval_s: float = 2.0
    ocr_backend: str = "tesseract"
    max_chars_per_minute: int = 5000
    refresh_unchanged_observation: bool = False
    visual_change_threshold: float = 0.0


class ScreenCaptureError(RuntimeError):
    pass


class ScreenOCR:
    """Track textual updates on the operator's screen."""

    def __init__(
        self,
        config: ScreenConfig,
        *,
        capture_fn: Callable[[], Mapping[str, Any]] | None = None,
        ocr_fn: Callable[[Mapping[str, Any]], str] | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._config = config
        self._capture_fn = capture_fn
        self._ocr_fn = ocr_fn
        self._metrics = metrics or MetricsRegistry()
        self._last_hash: str | None = None
        self._last_text_digest: str | None = None
        self._last_observation: dict[str, Any] | None = None
        self._last_attempt_monotonic: float | None = None
        self._chars_window: list[tuple[float, int]] = []
        self._last_failure_code: str | None = None
        self._last_visual_sample: tuple[int, ...] | None = None

    @staticmethod
    def _visual_sample(rgb: bytes, width: int, height: int) -> tuple[int, ...]:
        """Return a small deterministic luminance grid; never retain the frame."""
        columns, rows = 32, 18
        values: list[int] = []
        for row in range(rows):
            y = min(height - 1, (row * height + height // (2 * rows)) // rows)
            for column in range(columns):
                x = min(width - 1, (column * width + width // (2 * columns)) // columns)
                offset = (y * width + x) * 3
                red, green, blue = rgb[offset:offset + 3]
                values.append((77 * red + 150 * green + 29 * blue) >> 8)
        return tuple(values)

    def snapshot(self) -> Optional[Mapping[str, object]]:
        if not self._config.enable:
            return None
        if self._capture_fn is None or self._ocr_fn is None:
            self._last_failure_code = "screen_backend_unconfigured"
            self._metrics.increment("sos_screen_backend_unavailable_total")
            return None
        now_monotonic = time.monotonic()
        try:
            interval = float(self._config.interval_s)
        except (TypeError, ValueError):
            interval = 2.0
        if not math.isfinite(interval) or interval < 0:
            interval = 2.0
        if (self._last_attempt_monotonic is not None
                and now_monotonic - self._last_attempt_monotonic < interval):
            self._metrics.increment("sos_screen_capture_rate_limited_total")
            return None
        self._last_attempt_monotonic = now_monotonic
        try:
            payload = self._capture_fn()
        except Exception as exc:  # defensive platform and capture provider boundary
            self._last_failure_code = _failure_code(exc, "screen_capture_failed")
            raise ScreenCaptureError(self._last_failure_code) from exc
        if not isinstance(payload, Mapping):
            self._last_failure_code = "screen_capture_payload_invalid"
            raise ScreenCaptureError(self._last_failure_code)
        rgb = payload.get("rgb")
        if rgb is not None:
            width, height = payload.get("width"), payload.get("height")
            if (not isinstance(rgb, bytes) or type(width) is not int or type(height) is not int
                    or width < 1 or height < 1 or width > 2560 or height > 1440
                    or width * height > 4_194_304
                    or len(rgb) != width * height * 3 or len(rgb) > 12_582_912):
                self._last_failure_code = "screen_capture_payload_size_invalid"
                raise ScreenCaptureError(self._last_failure_code)
            raw_bytes = f"{width}x{height}:".encode("ascii") + rgb
        else:
            try:
                raw_bytes = json.dumps(dict(payload), sort_keys=True, ensure_ascii=False,
                                       separators=(",", ":")).encode("utf-8")
            except (TypeError, ValueError) as exc:
                self._last_failure_code = "screen_capture_payload_invalid"
                raise ScreenCaptureError(self._last_failure_code) from exc
            if len(raw_bytes) > 4_194_304:
                self._last_failure_code = "screen_capture_payload_size_invalid"
                raise ScreenCaptureError(self._last_failure_code)
        digest = hashlib.sha256(raw_bytes).hexdigest()
        threshold = self._config.visual_change_threshold
        if (isinstance(threshold, bool) or not isinstance(threshold, (int, float))
                or not math.isfinite(float(threshold)) or not 0.0 <= threshold <= 1.0):
            raise ScreenCaptureError("screen_visual_change_threshold_invalid")
        visual_sample: tuple[int, ...] | None = None
        visual_change_score: float | None = None
        if isinstance(rgb, bytes):
            assert type(width) is int and type(height) is int
            visual_sample = self._visual_sample(rgb, width, height)
            if self._last_visual_sample is not None:
                visual_change_score = sum(
                    abs(current - previous) >= 24
                    for current, previous in zip(visual_sample, self._last_visual_sample)
                ) / len(visual_sample)
        if (threshold > 0 and visual_sample is not None
                and self._last_observation is not None
                and visual_change_score is not None
                and visual_change_score < threshold):
            if not self._config.refresh_unchanged_observation:
                return None
            refreshed = dict(self._last_observation)
            captured_at = payload.get("captured_at")
            if not isinstance(captured_at, str) or not _UTC_TIMESTAMP.fullmatch(captured_at):
                captured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            refreshed["captured_at"] = captured_at
            capture_digest = payload.get("capture_digest")
            if isinstance(capture_digest, str) and re.fullmatch(r"[a-f0-9]{64}", capture_digest):
                refreshed["capture_digest"] = capture_digest
            refreshed["visual_change_kind"] = "stable"
            refreshed["visual_change_score"] = visual_change_score
            self._last_observation = refreshed
            return dict(refreshed)
        if digest == self._last_hash:
            if not self._config.refresh_unchanged_observation or self._last_observation is None:
                return None
            refreshed = dict(self._last_observation)
            refreshed["text_change_kind"] = "unchanged"
            if visual_sample is not None:
                refreshed["visual_change_kind"] = "stable"
                refreshed["visual_change_score"] = 0.0
            capture_digest = payload.get("capture_digest")
            if isinstance(capture_digest, str) and re.fullmatch(r"[a-f0-9]{64}", capture_digest):
                refreshed["capture_digest"] = capture_digest
            if self._last_text_digest is not None:
                refreshed["previous_text_digest"] = self._last_text_digest
            captured_at = payload.get("captured_at")
            if (not isinstance(captured_at, str)
                    or not _UTC_TIMESTAMP.fullmatch(captured_at)):
                captured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            refreshed["captured_at"] = captured_at
            for key in ("process_name_digest", "consent_id_digest"):
                value = payload.get(key)
                if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value):
                    refreshed[key] = value
            self._last_observation = refreshed
            return dict(refreshed)
        try:
            text = self._ocr_fn(payload)
        except Exception as exc:
            self._last_failure_code = _failure_code(exc, "screen_ocr_failed")
            raise ScreenCaptureError(self._last_failure_code) from exc
        if not isinstance(text, str):
            self._last_failure_code = "screen_ocr_output_invalid"
            raise ScreenCaptureError(self._last_failure_code)
        text_truncated = len(text) > 1200
        text = text[:1200].strip()
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
        self._last_hash = digest
        self._last_failure_code = None
        previous_text_digest = self._last_text_digest
        text_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        text_change_kind = ("initial" if previous_text_digest is None else
                            "unchanged" if text_digest == previous_text_digest else "changed")
        self._last_text_digest = text_digest
        capture_digest = payload.get("capture_digest")
        if not isinstance(capture_digest, str) or not re.fullmatch(r"[a-f0-9]{64}", capture_digest):
            capture_digest = digest
        captured_at = payload.get("captured_at", now)
        if (isinstance(captured_at, bool)
                or (isinstance(captured_at, str) and not _UTC_TIMESTAMP.fullmatch(captured_at))
                or (not isinstance(captured_at, (str, int, float)))
                or (isinstance(captured_at, (int, float)) and not math.isfinite(float(captured_at)))):
            captured_at = now
        backend = self._config.ocr_backend[:64] if isinstance(self._config.ocr_backend, str) else "unknown"
        observation: dict[str, Any] = {
            "modality": "screen",
            "text": text,
            "captured_at": captured_at,
            "backend": backend,
            "capture_digest": capture_digest,
            "raw_frame_retained": False,
            "text_truncated": text_truncated,
            "text_change_kind": text_change_kind,
        }
        if visual_sample is not None:
            observation["visual_change_kind"] = (
                "initial" if self._last_visual_sample is None else "changed")
            observation["visual_change_score"] = visual_change_score
        if previous_text_digest is not None:
            observation["previous_text_digest"] = previous_text_digest
        if payload.get("capture_scope") == "allowlisted_foreground_game_client_area":
            observation["capture_scope"] = payload["capture_scope"]
        for key in ("process_name_digest", "consent_id_digest"):
            value = payload.get(key)
            if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value):
                observation[key] = value
        self._metrics.increment("sos_screen_captures_total")
        self._metrics.increment("sos_screen_ocr_chars_total", len(text))
        self._last_observation = dict(observation)
        if visual_sample is not None:
            self._last_visual_sample = visual_sample
        return observation

    def _prune_window(self, now: float) -> None:
        cutoff = now - 60.0
        self._chars_window = [(ts, count) for ts, count in self._chars_window if ts >= cutoff]

    def status(self) -> Mapping[str, object]:
        return {
            "status": ("disabled" if not self._config.enable else
                       "unconfigured" if self._capture_fn is None or self._ocr_fn is None else
                       "degraded" if self._last_failure_code else "healthy"),
            "ocr_backend": self._config.ocr_backend,
            "last_text_digest": self._last_text_digest,
            "last_failure_code": self._last_failure_code,
            "raw_frame_retained": False,
        }


__all__ = ["ScreenConfig", "ScreenOCR", "ScreenCaptureError"]

