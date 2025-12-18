from __future__ import annotations

from pathlib import Path

from sentientos.feedback import FeedbackAttributor


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
