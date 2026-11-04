from __future__ import annotations

import pytest

from sentientos.metrics import MetricsRegistry
from sentientos.perception.screen_ocr import ScreenConfig, ScreenOCR

pytestmark = pytest.mark.no_legacy_skip


def test_screen_ocr_throttling_and_hashing() -> None:
    metrics = MetricsRegistry()
    payloads = iter(
        [
            {"data": "first frame", "title": "Window"},
            {"data": "first frame", "title": "Window"},
            {"data": "second frame", "title": "Window"},
            {"data": "long text" * 200, "title": "Window"},
        ]
    )

    def capture() -> dict[str, str]:
        return next(payloads)

    ocr = ScreenOCR(
        ScreenConfig(enable=True, interval_s=0, max_chars_per_minute=100),
        capture_fn=capture,
        ocr_fn=lambda payload: payload["data"],
        metrics=metrics,
    )

    first = ocr.snapshot()
    assert first is not None
    assert first["text"] == "first frame"

    # Same hash should not emit a new observation.
    assert ocr.snapshot() is None

    second = ocr.snapshot()
    assert second is not None
    assert second["text"] == "second frame"

    # Excessively long text should be throttled by budget.
    assert ocr.snapshot() is None

    counters = metrics.snapshot()["counters"]
    assert counters["sos_screen_captures_total"] == 2.0
    assert counters["sos_screen_ocr_chars_total"] > 0


def test_screen_ocr_is_unconfigured_without_explicit_capture_and_ocr_backends() -> None:
    ocr = ScreenOCR(ScreenConfig(enable=True))
    assert ocr.snapshot() is None
    assert ocr.status()["status"] == "unconfigured"
    assert ocr.status()["raw_frame_retained"] is False
    assert "last_text_preview" not in ocr.status()


def test_screen_ocr_enforces_sampling_interval_and_returns_provenance_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter([1.0, 1.5, 3.0])
    captures = iter([
        {"rgb": b"one", "width": 1, "height": 1, "capture_digest": "a" * 64,
         "captured_at": "2026-01-01T00:00:00Z", "capture_scope": "allowlisted_foreground_game_client_area",
         "process_name_digest": "b" * 64, "consent_id_digest": "c" * 64},
        {"rgb": b"two", "width": 1, "height": 1, "capture_digest": "d" * 64,
         "captured_at": "2026-01-01T00:00:03Z", "capture_scope": "allowlisted_foreground_game_client_area",
         "process_name_digest": "b" * 64, "consent_id_digest": "c" * 64},
    ])
    ocr = ScreenOCR(
        ScreenConfig(enable=True, interval_s=2), capture_fn=lambda: next(captures),
        ocr_fn=lambda _payload: "x" * 1500,
    )
    from sentientos.perception import screen_ocr as screen_ocr_module
    monkeypatch.setattr(screen_ocr_module.time, "monotonic", lambda: next(ticks))
    first = ocr.snapshot()
    assert first is not None
    assert len(first["text"]) == 1200
    assert first["text_truncated"] is True
    assert first["raw_frame_retained"] is False
    assert first["capture_scope"] == "allowlisted_foreground_game_client_area"
    assert "rgb" not in first and "window_title" not in first
    assert ocr.snapshot() is None
    second = ocr.snapshot()
    assert second is not None and second["captured_at"] == "2026-01-01T00:00:03Z"

def test_screen_ocr_retries_identical_frame_after_transient_ocr_failure():
    from sentientos.perception.screen_ocr import ScreenCaptureError

    calls = []

    def ocr(_payload):
        calls.append("ocr")
        if len(calls) == 1:
            raise RuntimeError("temporary OCR failure")
        return "objective: reach the observatory"

    owner = ScreenOCR(
        ScreenConfig(enable=True, interval_s=0),
        capture_fn=lambda: {"frame": "same"},
        ocr_fn=ocr,
    )

    with pytest.raises(ScreenCaptureError, match="screen_ocr_failed"):
        owner.snapshot()
    observation = owner.snapshot()

    assert observation is not None
    assert observation["text_change_kind"] == "initial"
    assert calls == ["ocr", "ocr"]


def test_screen_ocr_distinguishes_text_changes_from_frame_changes():
    import hashlib

    payloads = iter([
        {"frame": "first", "text": "objective: reach the observatory"},
        {"frame": "animated", "text": "objective: reach the observatory"},
        {"frame": "objective-updated", "text": "objective: enter the observatory"},
    ])
    ocr = ScreenOCR(
        ScreenConfig(enable=True, interval_s=0),
        capture_fn=lambda: next(payloads),
        ocr_fn=lambda payload: payload["text"],
    )

    initial = ocr.snapshot()
    same_text = ocr.snapshot()
    changed_text = ocr.snapshot()

    assert initial is not None and initial["text_change_kind"] == "initial"
    assert "previous_text_digest" not in initial
    assert same_text is not None and same_text["text_change_kind"] == "unchanged"
    assert same_text["previous_text_digest"] == hashlib.sha256(
        initial["text"].encode("utf-8")).hexdigest()
    assert changed_text is not None and changed_text["text_change_kind"] == "changed"
    assert changed_text["previous_text_digest"] == same_text["previous_text_digest"]


def test_screen_ocr_can_refresh_identical_capture_without_rerunning_ocr():
    captures = iter([
        {"rgb": b"one", "width": 1, "height": 1, "capture_digest": "a" * 64,
         "captured_at": "2026-11-04T12:00:00Z",
         "capture_scope": "allowlisted_foreground_game_client_area",
         "process_name_digest": "b" * 64, "consent_id_digest": "c" * 64},
        {"rgb": b"one", "width": 1, "height": 1, "capture_digest": "a" * 64,
         "captured_at": "2026-11-04T12:00:02Z",
         "capture_scope": "allowlisted_foreground_game_client_area",
         "process_name_digest": "b" * 64, "consent_id_digest": "c" * 64},
    ])
    calls = []
    ocr = ScreenOCR(
        ScreenConfig(enable=True, interval_s=0, refresh_unchanged_observation=True),
        capture_fn=lambda: next(captures),
        ocr_fn=lambda _payload: calls.append("ocr") or "objective: observatory",
    )

    first = ocr.snapshot()
    second = ocr.snapshot()

    assert first is not None and second is not None
    assert first["text"] == second["text"] == "objective: observatory"
    assert second["captured_at"] == "2026-11-04T12:00:02Z"
    assert second["capture_digest"] == "a" * 64
    assert second["text_change_kind"] == "unchanged"
    assert second["previous_text_digest"]
    assert calls == ["ocr"]
    assert "rgb" not in second
