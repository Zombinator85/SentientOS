from __future__ import annotations

from pathlib import Path

import pytest

from sentientos.feedback import FeedbackAttributor

pytestmark = pytest.mark.no_legacy_skip


def test_feedback_attributor_links_regressions(tmp_path: Path):
    workspace = tmp_path / "feedback"
    attributor = FeedbackAttributor(workspace)

    feedback = [
        {
            "type": "regression",
            "description": "Test suite failure in integration memory",
            "culprit_daemon": "IntegrationMemory",
            "responsible_patch": "patch-77",
            "trigger_reflex": "reflex-beta",
            "contributing_factors": ["cache invalidation", "stale feature flag"],
            "links": ["logs://regressions/3301"],
            "confidence_score": 0.84,
        }
    ]

    attributed = attributor.attribute_feedback(feedback)
    assert attributed[0]["culprit_daemon"] == "IntegrationMemory"
    assert attributed[0]["confidence_score"] > 0.5

    stored = workspace / "feedback_trace.jsonl"
    assert stored.exists()
    content = stored.read_text(encoding="utf-8")
    assert "logs://regressions/3301" in content

def test_feedback_attributor_handles_malformed_optional_values(tmp_path: Path) -> None:
    attributor = FeedbackAttributor(tmp_path / "feedback")

    [attributed] = attributor.attribute_feedback(
        [
            {
                "contributing_factors": 42,
                "links": {"invalid": "mapping"},
                "confidence_score": object(),
            }
        ]
    )

    assert attributed["contributing_factors"] == []
    assert attributed["links"] == []
    assert attributed["confidence_score"] == 0.5
\n