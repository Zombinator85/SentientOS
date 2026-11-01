from __future__ import annotations

import pytest

from sentientos.autonomy.conversation_triggers import ConversationConfig, ConversationTriggers

pytestmark = pytest.mark.no_legacy_skip


def test_custom_clock_controls_trigger_window() -> None:
    instant = 7_200.0
    triggers = ConversationTriggers(
        ConversationConfig(enable=True, quiet_hours="00:00-01:00", max_prompts_per_hour=1),
        clock=lambda: instant,
    )

    assert triggers.should_trigger("presence")
    assert not triggers.should_trigger("novelty")
