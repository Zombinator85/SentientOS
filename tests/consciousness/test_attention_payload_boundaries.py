from __future__ import annotations

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.consciousness.attention_arbitrator import AttentionArbitrator, PulseEvent


def test_score_handles_missing_internal_priority() -> None:
    event = PulseEvent(payload={}, internal_priority=None)

    score = AttentionArbitrator()._score(event)

    assert score[1] == 0.0
