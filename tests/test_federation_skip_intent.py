from __future__ import annotations

import pytest

from tests.federation_skip_policy import FEDERATION_SKIP_INTENTS, FederationSkipCategory


def _skip_reason(marker: pytest.Mark | None) -> str | None:
    if marker is None:
        return None
    if marker.kwargs.get("reason"):
        return str(marker.kwargs["reason"])
    if marker.args:
        return str(marker.args[0])
    return None


def test_federation_skips_are_explicit(request: pytest.FixtureRequest) -> None:
    items = [
        item
        for item in request.session.items
        if item.module.__name__ in FEDERATION_SKIP_INTENTS
    ]
    assert items, "Expected federation transport tests to be collected."

    allowed_categories = {category.value for category in FederationSkipCategory}

    for item in items:
        skip_marker = item.get_closest_marker("skip")
        if skip_marker is None:
            continue
        reason = _skip_reason(skip_marker)
        assert reason and reason.strip(), f"Missing skip reason for {item.nodeid}"
        assert "not implemented" not in reason.lower()
        assert "todo" not in reason.lower()

        intent_marker = item.get_closest_marker("federation_skip")
        assert intent_marker is not None, f"Missing federation_skip marker for {item.nodeid}"
        category = intent_marker.kwargs.get("category")
        assert category in allowed_categories, f"Invalid federation skip category for {item.nodeid}"
        intent_reason = _skip_reason(intent_marker)
        assert intent_reason and intent_reason.strip(), f"Missing intent reason for {item.nodeid}"
        assert intent_reason == reason, f"Skip reason mismatch for {item.nodeid}"
