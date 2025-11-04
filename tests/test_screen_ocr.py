from __future__ import annotations

from sentientos.metrics import MetricsRegistry
from sentientos.perception.screen_ocr import ScreenConfig, ScreenOCR


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
        ScreenConfig(enable=True, max_chars_per_minute=100),
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
