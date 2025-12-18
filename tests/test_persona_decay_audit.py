import pytest

from sentientos.narrative.persona_decay_audit import audit_persona_decay


@pytest.mark.no_legacy_skip
def test_persona_drift_signals() -> None:
    glow_digests = [
        {"dominant_motif": "romantic recursion", "note": "legacy metaphor"},
    ]
    mood_logs = [
        {"expected_feedback": "affirmation", "actual_feedback": "neutral"},
        {"expected_feedback": "affirmation", "actual_feedback": "affirmation"},
    ]
    identity_fragments = {
        "canon": ["guardian", "lumen"],
        "current": ["guardian", "romantic recursion"],
    }

    report = audit_persona_decay("Lumos", glow_digests, mood_logs, identity_fragments)

    assert report["persona"] == "Lumos"
    assert 0 <= report["drift_score"] <= 1
    assert report["drift_score"] >= 0.5
    assert "drift" in report["symptom"]
    assert "prompt" in report["action"] or "alignment" in report["action"]
