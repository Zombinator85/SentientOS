from __future__ import annotations

from scripts.perception import screen_adapter


def test_screen_url_full_requires_private_and_flag(monkeypatch) -> None:
    monkeypatch.setattr(
        screen_adapter,
        "snapshot_screen_context",
        lambda: {
            "active_app": "Chrome",
            "window_title": "Example https://example.com/path",
            "cursor_position": {"x": 1.0, "y": 2.0},
            "screen_geometry": {"width": 1920.0, "height": 1080.0},
            "confidence": 0.9,
            "degraded": False,
            "degradation_reason": None,
        },
    )

    blocked = screen_adapter.build_perception_payload(
        privacy_class="internal",
        text_excerpt="sample",
        focused_element_hint=None,
        include_domain=True,
        include_url_full=True,
        include_text_excerpt=False,
    )
    assert blocked.get("browser_domain") == "example.com"
    assert "browser_url_full" not in blocked
    assert blocked["redaction_applied"] is True

    allowed = screen_adapter.build_perception_payload(
        privacy_class="private",
        text_excerpt="sample",
        focused_element_hint=None,
        include_domain=True,
        include_url_full=True,
        include_text_excerpt=False,
    )
    assert allowed.get("browser_url_full") == "https://example.com/path"


def test_text_excerpt_requires_opt_in_and_is_truncated(monkeypatch) -> None:
    monkeypatch.setattr(
        screen_adapter,
        "snapshot_screen_context",
        lambda: {
            "active_app": "Editor",
            "window_title": "README.md",
            "cursor_position": None,
            "screen_geometry": None,
            "confidence": 0.9,
            "degraded": False,
            "degradation_reason": None,
        },
    )

    payload = screen_adapter.build_perception_payload(
        privacy_class="internal",
        text_excerpt="x" * 400,
        focused_element_hint="editor",
        include_domain=False,
        include_url_full=False,
        include_text_excerpt=True,
    )
    assert len(payload["text_excerpt"]) == 256
    assert payload["raw_artifact_retained"] is False
    assert payload["ui_context"]["kind"] == "editor"
