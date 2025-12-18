from sentientos.persona import PersonaBoundaryEnforcer


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
