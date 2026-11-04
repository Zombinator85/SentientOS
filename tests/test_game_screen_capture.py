from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sentientos.perception.game_screen_capture import (
    CapturedGameFrame,
    ForegroundGameWindow,
    GameScreenCaptureConsent,
    LocalTesseractOCR,
    WindowsGameScreenCapture,
    build_windows_game_screen_ocr,
)
from sentientos.perception.screen_ocr import ScreenCaptureError, ScreenConfig

pytestmark = pytest.mark.no_legacy_skip


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
CONSENT = GameScreenCaptureConsent(
    consent_id="consent-game-1",
    allowed_process_names=("ExampleGame.exe",),
    expires_at="2026-01-01T00:10:00Z",
)
WINDOW = ForegroundGameWindow("ExampleGame.exe", 10, 20, 110, 70)
FRAME = CapturedGameFrame(100, 50, bytes(100 * 50 * 3))


def test_screen_ocr_builder_uses_explicit_local_tesseract_executable(monkeypatch) -> None:
    from sentientos.perception import game_screen_capture

    observed = {}
    monkeypatch.setattr(game_screen_capture, "WindowsGameScreenCapture",
                        lambda **_kwargs: (lambda: None))
    def make_ocr(*, executable):
        observed["executable"] = executable
        return lambda _payload: ""

    monkeypatch.setattr(game_screen_capture, "LocalTesseractOCR", make_ocr)

    build_windows_game_screen_ocr(
        config=ScreenConfig(enable=True),
        consent_provider=lambda: CONSENT,
        tesseract_executable=r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    )

    assert observed["executable"] == r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def test_capture_requires_current_explicit_consent_before_window_query() -> None:
    queried: list[bool] = []
    capture = WindowsGameScreenCapture(
        consent_provider=lambda: None,
        window_provider=lambda: (queried.append(True) or WINDOW),
        frame_provider=lambda _window: FRAME,
        clock=lambda: NOW,
    )
    with pytest.raises(ScreenCaptureError, match="game_screen_consent_required"):
        capture()
    assert queried == []


def test_capture_accepts_only_allowlisted_foreground_client_area() -> None:
    frames: list[ForegroundGameWindow] = []
    capture = WindowsGameScreenCapture(
        consent_provider=lambda: CONSENT,
        window_provider=lambda: WINDOW,
        frame_provider=lambda window: (frames.append(window) or FRAME),
        clock=lambda: NOW,
        monotonic=lambda: 1.0,
    )
    observation_payload = capture()
    assert frames == [WINDOW]
    assert observation_payload["rgb"] == FRAME.rgb
    assert observation_payload["capture_scope"] == "allowlisted_foreground_game_client_area"
    assert observation_payload["raw_frame_retained"] is False
    assert observation_payload["process_name_digest"]
    assert observation_payload["consent_id_digest"]
    assert "process_name" not in observation_payload


def test_capture_rejects_non_allowlisted_or_expired_consent() -> None:
    capture = WindowsGameScreenCapture(
        consent_provider=lambda: CONSENT,
        window_provider=lambda: ForegroundGameWindow("Browser.exe", 0, 0, 100, 50),
        frame_provider=lambda _window: FRAME,
        clock=lambda: NOW,
    )
    with pytest.raises(ScreenCaptureError, match="not_allowlisted"):
        capture()

    expired = GameScreenCaptureConsent("old", ("ExampleGame.exe",), "2025-12-31T23:59:00Z")
    expired_capture = WindowsGameScreenCapture(
        consent_provider=lambda: expired, window_provider=lambda: WINDOW,
        frame_provider=lambda _window: FRAME, clock=lambda: NOW,
    )
    with pytest.raises(ScreenCaptureError, match="consent_expired"):
        expired_capture()


def test_capture_enforces_rate_and_frame_size_bounds() -> None:
    attempts: list[bool] = []
    ticks = iter([1.0, 1.5])
    capture = WindowsGameScreenCapture(
        consent_provider=lambda: CONSENT, window_provider=lambda: WINDOW,
        frame_provider=lambda _window: (attempts.append(True) or FRAME),
        clock=lambda: NOW, monotonic=lambda: next(ticks), min_interval_seconds=1.0,
    )
    capture()
    with pytest.raises(ScreenCaptureError, match="rate_limited"):
        capture()
    assert attempts == [True]

    oversized = WindowsGameScreenCapture(
        consent_provider=lambda: CONSENT,
        window_provider=lambda: ForegroundGameWindow("ExampleGame.exe", 0, 0, 3000, 1600),
        frame_provider=lambda _window: FRAME,
        clock=lambda: NOW,
    )
    with pytest.raises(ScreenCaptureError, match="bounds_invalid"):
        oversized()

    with pytest.raises(ValueError, match="game_screen_interval_invalid"):
        WindowsGameScreenCapture(consent_provider=lambda: CONSENT, min_interval_seconds=0.1)


def test_capture_rejects_bad_frame_shape_and_process_paths_are_reduced_to_basename() -> None:
    capture = WindowsGameScreenCapture(
        consent_provider=lambda: CONSENT,
        window_provider=lambda: ForegroundGameWindow(r"C:\Games\ExampleGame.exe", 0, 0, 100, 50),
        frame_provider=lambda _window: CapturedGameFrame(100, 50, b"short"),
        clock=lambda: NOW,
    )
    with pytest.raises(ScreenCaptureError, match="frame_bytes_invalid"):
        capture()


def test_tesseract_backend_uses_bounded_in_memory_local_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess
    from types import SimpleNamespace

    from sentientos.perception import game_screen_capture as capture_module

    calls: list[dict[str, object]] = []

    def run(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return SimpleNamespace(returncode=0, stdout=b"recognized text")

    monkeypatch.setattr(capture_module.importlib, "import_module", lambda _name: SimpleNamespace(
        to_png=lambda rgb, size: b"png"))
    monkeypatch.setattr(subprocess, "run", run)
    ocr = LocalTesseractOCR(timeout_seconds=1.5)
    assert ocr({"rgb": bytes(100 * 50 * 3), "width": 100, "height": 50}) == "recognized text"
    assert calls[0]["command"] == ["tesseract", "stdin", "stdout"]
    assert calls[0]["input"] == b"png"
    assert calls[0]["timeout"] == 1.5
    assert "shell" not in calls[0]
