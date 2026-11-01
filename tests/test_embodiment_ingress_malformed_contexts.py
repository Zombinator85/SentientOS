from __future__ import annotations

import pytest

from sentientos.embodiment_ingress import evaluate_embodiment_ingress

pytestmark = pytest.mark.no_legacy_skip


@pytest.mark.parametrize("value", [None, object(), "invalid"])
def test_malformed_contexts_produce_no_candidates(value: object) -> None:
    receipt = evaluate_embodiment_ingress(
        {
            "current_audio_context": value,
            "current_feedback_context": value,
            "modalities_present": [],
        }
    )

    assert receipt["memory_candidate"] is None
    assert receipt["feedback_candidate"] is None
