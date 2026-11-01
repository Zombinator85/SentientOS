import pytest

from sentientos.persona import PersonaBoundaryEnforcer


@pytest.mark.no_legacy_skip
def test_persona_boundary_enforcer_reports_only_flags():
    lint = [
        {"persona": "echo", "issue": "self-justify narrative"},
        {"persona": "delta", "issue": "spacing"},
    ]
    decay_audits = [{"persona": "echo", "decay_score": 0.7}]
    continuity = [{"persona": "echo", "gaps": 1}]

    result = PersonaBoundaryEnforcer().evaluate(lint, decay_audits, continuity)

    assert result["can_enqueue_actions"] is False
    categories = {violation.category for violation in result["violations"]}
    assert "narrative_loop" in categories
    assert "decay_drift" in categories
    assert "continuity_gap" in categories


@pytest.mark.no_legacy_skip
def test_persona_boundary_enforcer_ignores_malformed_scores() -> None:
    result = PersonaBoundaryEnforcer().evaluate(
        [],
        [{"persona": "echo", "decay_score": object()}],
        [{"persona": "echo", "gaps": "not a number"}],
    )

    assert result["violations"] == []
