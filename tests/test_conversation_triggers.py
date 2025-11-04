from __future__ import annotations

from sentientos.autonomy.conversation_triggers import ConversationConfig, ConversationTriggers
from sentientos.metrics import MetricsRegistry


def test_conversation_quiet_hours_and_rate_limit() -> None:
    now = 0.0

    def clock() -> float:
        nonlocal now
        return now

    config = ConversationConfig(
        enable=True,
        quiet_hours="00:00-01:00",
        max_prompts_per_hour=2,
    )
    triggers = ConversationTriggers(config, metrics=MetricsRegistry(), clock=clock)

    now = 3600 * 2  # 2am -> outside quiet hours
    assert triggers.should_trigger("presence")
    assert triggers.should_trigger("name")
    assert not triggers.should_trigger("novelty")  # exceeds hourly cap

    now = 1800  # within quiet hours
    assert not triggers.should_trigger("presence")
