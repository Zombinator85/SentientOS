"""Opt-in, foreground-game-only Windows screen capture and local OCR.

This adapter accepts only an explicit, current consent record and captures only
the allowlisted foreground window's client area. Frames stay in memory and are
discarded after local OCR; the returned observation contains bounded text and
digests, never the raw frame.
"""
from __future__ import annotations

import csv
import hashlib
import importlib
import io
import math
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .screen_ocr import ScreenCaptureError, ScreenConfig, ScreenOCR

MAX_FRAME_PIXELS = 4_194_304
MAX_FRAME_BYTES = MAX_FRAME_PIXELS * 3
MAX_FRAME_WIDTH = 2560
MAX_FRAME_HEIGHT = 1440
MAX_OCR_TEXT_CHARS = 1200
_PROCESS_NAME = re.compile(r"^[a-zA-Z0-9_. -]{1,128}$")
MIN_TESSERACT_WORD_CONFIDENCE = 45.0
MAX_TESSERACT_TSV_BYTES = 65_536


def _confident_tesseract_text(tsv: str) -> str:
    """Keep only Tesseract word rows above the bounded confidence floor."""
    rows = csv.reader(io.StringIO(tsv), delimiter="\t")
    try:
        header = next(rows)
        indexes = {name: header.index(name) for name in
                   ("block_num", "par_num", "line_num", "conf", "text")}
    except (StopIteration, ValueError) as exc:
        raise ScreenCaptureError("game_screen_ocr_tsv_invalid") from exc
    line_tokens: dict[tuple[str, str, str], list[str]] = {}
    line_order: list[tuple[str, str, str]] = []
    required_index = max(indexes.values())
    for row in rows:
        if len(row) <= required_index:
            continue
        token = row[indexes["text"]].strip()
        if not token:
            continue
        try:
            confidence = float(row[indexes["conf"]])
        except ValueError:
            continue
        if not math.isfinite(confidence) or confidence < MIN_TESSERACT_WORD_CONFIDENCE:
            continue
        line = (row[indexes["block_num"]], row[indexes["par_num"]],
                row[indexes["line_num"]])
        if line not in line_tokens:
            line_tokens[line] = []
            line_order.append(line)
        line_tokens[line].append(token)
    return "\n".join(
        " ".join(line_tokens[line]) for line in line_order
    )[:MAX_OCR_TEXT_CHARS]


@dataclass(frozen=True)
class GameScreenCaptureConsent:
    """Operator-owned, revocable opt-in for named foreground game processes."""

    consent_id: str
    allowed_process_names: tuple[str, ...]
    expires_at: str


@dataclass(frozen=True)
class ForegroundGameWindow:
    process_name: str
    left: int
    top: int
    right: int
    bottom: int


@dataclass(frozen=True)
class CapturedGameFrame:
    width: int
    height: int
    rgb: bytes


ConsentProvider = Callable[[], GameScreenCaptureConsent | None]
WindowProvider = Callable[[], ForegroundGameWindow]
FrameProvider = Callable[[ForegroundGameWindow], CapturedGameFrame]
OCRProvider = Callable[[CapturedGameFrame], str]


def _normalize_process_name(value: str) -> str:
    candidate = value.strip().replace("\\", "/").rsplit("/", 1)[-1].casefold()
    if not _PROCESS_NAME.fullmatch(candidate):
        raise ScreenCaptureError("game_screen_process_name_invalid")
    return candidate


def _validate_consent(consent: GameScreenCaptureConsent, *, now: datetime) -> tuple[str, ...]:
    if (type(consent) is not GameScreenCaptureConsent
            or not isinstance(consent.consent_id, str) or not consent.consent_id
            or len(consent.consent_id) > 128
            or type(consent.allowed_process_names) is not tuple
            or not consent.allowed_process_names):
        raise ScreenCaptureError("game_screen_consent_invalid")
    if type(now) is not datetime or now.tzinfo is None:
        raise ScreenCaptureError("game_screen_clock_invalid")
    try:
        expires = datetime.fromisoformat(consent.expires_at.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ScreenCaptureError("game_screen_consent_expiry_invalid") from exc
    if expires.tzinfo is None or expires.utcoffset() != timezone.utc.utcoffset(expires):
        raise ScreenCaptureError("game_screen_consent_expiry_invalid")
    if now >= expires:
        raise ScreenCaptureError("game_screen_consent_expired")
    try:
        names = tuple(sorted({_normalize_process_name(name) for name in consent.allowed_process_names}))
    except (AttributeError, TypeError) as exc:
        raise ScreenCaptureError("game_screen_consent_processes_invalid") from exc
    if not names:
        raise ScreenCaptureError("game_screen_consent_processes_invalid")
    return names


def _windows_foreground_game_window() -> ForegroundGameWindow:
    if os.name != "nt":
        raise ScreenCaptureError("game_screen_capture_windows_only")
    try:
        win32gui = importlib.import_module("win32gui")
        win32process = importlib.import_module("win32process")
        psutil = importlib.import_module("psutil")
        handle = win32gui.GetForegroundWindow()
        if not handle:
            raise ScreenCaptureError("game_screen_foreground_window_unavailable")
        if win32gui.IsIconic(handle):
            raise ScreenCaptureError("game_screen_window_minimized")
        _thread_id, process_id = win32process.GetWindowThreadProcessId(handle)
        process_name = psutil.Process(int(process_id)).name()
        left, top, right, bottom = win32gui.GetClientRect(handle)
        screen_left, screen_top = win32gui.ClientToScreen(handle, (left, top))
        screen_right, screen_bottom = win32gui.ClientToScreen(handle, (right, bottom))
        return ForegroundGameWindow(str(process_name), int(screen_left), int(screen_top),
                                    int(screen_right), int(screen_bottom))
    except ScreenCaptureError:
        raise
    except Exception as exc:
        raise ScreenCaptureError("game_screen_foreground_window_unavailable") from exc


def _capture_with_mss(window: ForegroundGameWindow) -> CapturedGameFrame:
    try:
        mss = importlib.import_module("mss")
        with mss.mss() as capture:
            shot = capture.grab({"left": window.left, "top": window.top,
                                 "width": window.right - window.left,
                                 "height": window.bottom - window.top})
            return CapturedGameFrame(int(shot.width), int(shot.height), bytes(shot.rgb))
    except Exception as exc:
        raise ScreenCaptureError("game_screen_capture_backend_unavailable") from exc


def _validate_frame(frame: CapturedGameFrame) -> None:
    if type(frame) is not CapturedGameFrame:
        raise ScreenCaptureError("game_screen_frame_invalid")
    if (type(frame.width) is not int or type(frame.height) is not int
            or frame.width < 1 or frame.height < 1
            or frame.width > MAX_FRAME_WIDTH or frame.height > MAX_FRAME_HEIGHT
            or frame.width * frame.height > MAX_FRAME_PIXELS):
        raise ScreenCaptureError("game_screen_frame_dimensions_invalid")
    if type(frame.rgb) is not bytes or len(frame.rgb) != frame.width * frame.height * 3:
        raise ScreenCaptureError("game_screen_frame_bytes_invalid")
    if len(frame.rgb) > MAX_FRAME_BYTES:
        raise ScreenCaptureError("game_screen_frame_size_exceeded")


class WindowsGameScreenCapture:
    """Capture one fresh, consented, allowlisted foreground game frame."""

    def __init__(self, *, consent_provider: ConsentProvider,
                 window_provider: WindowProvider = _windows_foreground_game_window,
                 frame_provider: FrameProvider = _capture_with_mss,
                 clock: Callable[[], datetime] | None = None,
                 monotonic: Callable[[], float] = time.monotonic,
                 min_interval_seconds: float = 2.0) -> None:
        if not callable(consent_provider) or not callable(window_provider) or not callable(frame_provider):
            raise TypeError("game_screen_providers_must_be_callable")
        if (isinstance(min_interval_seconds, bool) or not isinstance(min_interval_seconds, (int, float))
                or not math.isfinite(float(min_interval_seconds)) or min_interval_seconds < 0.5):
            raise ValueError("game_screen_interval_invalid")
        self._consent_provider = consent_provider
        self._window_provider = window_provider
        self._frame_provider = frame_provider
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic
        self._min_interval_seconds = float(min_interval_seconds)
        self._last_capture_monotonic: float | None = None

    def __call__(self) -> Mapping[str, Any]:
        consent = self._consent_provider()
        if consent is None:
            raise ScreenCaptureError("game_screen_consent_required")
        now = self._clock()
        allowed_process_names = _validate_consent(consent, now=now)
        monotonic_now = self._monotonic()
        if (self._last_capture_monotonic is not None
                and monotonic_now - self._last_capture_monotonic < self._min_interval_seconds):
            raise ScreenCaptureError("game_screen_capture_rate_limited")
        window = self._window_provider()
        if type(window) is not ForegroundGameWindow:
            raise ScreenCaptureError("game_screen_window_invalid")
        process_name = _normalize_process_name(window.process_name)
        if process_name not in allowed_process_names:
            raise ScreenCaptureError("game_screen_foreground_process_not_allowlisted")
        width, height = window.right - window.left, window.bottom - window.top
        if (width < 1 or height < 1 or width > MAX_FRAME_WIDTH or height > MAX_FRAME_HEIGHT
                or width * height > MAX_FRAME_PIXELS):
            raise ScreenCaptureError("game_screen_window_bounds_invalid")
        frame = self._frame_provider(window)
        _validate_frame(frame)
        if frame.width != width or frame.height != height:
            raise ScreenCaptureError("game_screen_frame_bounds_mismatch")
        self._last_capture_monotonic = monotonic_now
        digest = hashlib.sha256(
            f"{frame.width}x{frame.height}:".encode("ascii") + frame.rgb
        ).hexdigest()
        process_digest = hashlib.sha256(process_name.encode("utf-8")).hexdigest()
        consent_digest = hashlib.sha256(consent.consent_id.encode("utf-8")).hexdigest()
        return {
            "rgb": frame.rgb,
            "width": frame.width,
            "height": frame.height,
            "capture_digest": digest,
            "process_name_digest": process_digest,
            "consent_id_digest": consent_digest,
            "captured_at": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "capture_scope": "allowlisted_foreground_game_client_area",
            "raw_frame_retained": False,
        }


class LocalTesseractOCR:
    """Invoke the local Tesseract CLI using in-memory PNG input and a timeout."""

    def __init__(self, *, executable: str = "tesseract", timeout_seconds: float = 2.0) -> None:
        if (not executable or isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(float(timeout_seconds))
                or timeout_seconds <= 0 or timeout_seconds > 10):
            raise ValueError("game_screen_ocr_configuration_invalid")
        self._executable = executable
        self._timeout_seconds = float(timeout_seconds)

    def __call__(self, payload: Mapping[str, Any]) -> str:
        try:
            frame = CapturedGameFrame(payload["width"], payload["height"], payload["rgb"])
            _validate_frame(frame)
            tools = importlib.import_module("mss.tools")
            png = tools.to_png(frame.rgb, (frame.width, frame.height))
            completed = subprocess.run(
                [self._executable, "stdin", "stdout", "tsv"], input=png, capture_output=True,
                check=False, timeout=self._timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ScreenCaptureError("game_screen_ocr_timeout") from exc
        except ScreenCaptureError:
            raise
        except Exception as exc:
            raise ScreenCaptureError("game_screen_ocr_backend_unavailable") from exc
        if completed.returncode != 0:
            raise ScreenCaptureError("game_screen_ocr_failed")
        if not isinstance(completed.stdout, bytes):
            raise ScreenCaptureError("game_screen_ocr_output_invalid")
        if len(completed.stdout) > MAX_TESSERACT_TSV_BYTES:
            raise ScreenCaptureError("game_screen_ocr_output_size_invalid")
        return _confident_tesseract_text(
            completed.stdout.decode("utf-8", errors="replace"))


def build_windows_game_screen_ocr(*, config: ScreenConfig,
                                  consent_provider: ConsentProvider,
                                  tesseract_executable: str = "tesseract") -> ScreenOCR:
    """Build the disabled-by-default screen OCR owner with local Windows adapters."""

    return ScreenOCR(config, capture_fn=WindowsGameScreenCapture(consent_provider=consent_provider),
                     ocr_fn=LocalTesseractOCR(executable=tesseract_executable))


__all__ = [
    "CapturedGameFrame", "ForegroundGameWindow", "GameScreenCaptureConsent",
    "LocalTesseractOCR", "WindowsGameScreenCapture", "build_windows_game_screen_ocr",
]
