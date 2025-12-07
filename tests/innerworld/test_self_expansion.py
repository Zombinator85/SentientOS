from sentientos.self_expansion import SelfExpansionAgent


def test_run_self_audit_derives_fields_without_mutating_input():
    observations = {
        "error_count": 2,
        "tension_avg": 0.3,
        "low_confidence_events": 0,
    }
    agent = SelfExpansionAgent()

    result = agent.run_self_audit(observations)

    assert result["error_count"] == 2
    assert result["attention_flags"] == 1
    assert result["needs_improvement"] is True
    assert result["status"] == "attention_needed"
    assert "needs_improvement" not in observations


def test_run_self_audit_handles_stable_state():
    observations = {"error_count": 0, "tension_avg": 0.1, "low_confidence_events": 0}
    agent = SelfExpansionAgent()

    result = agent.run_self_audit(observations)

    assert result["attention_flags"] == 0
    assert result["needs_improvement"] is False
    assert result["status"] == "stable"


def test_propose_upgrades_includes_all_triggered_sections():
    observations = {"error_count": 1, "tension_avg": 0.7, "low_confidence_events": 3}
    agent = SelfExpansionAgent()

    proposal = agent.propose_upgrades(observations)

    assert proposal.startswith("Proposal:\n")
    assert "- Strengthen error handling pathways" in proposal
    assert "- Tune inner experience integration" in proposal
    assert "- Enhance metacognition rules" in proposal


def test_propose_upgrades_is_deterministic():
    observations = {"error_count": 0, "tension_avg": 0.4, "low_confidence_events": 0}
    agent = SelfExpansionAgent()

    first = agent.propose_upgrades(observations)
    second = agent.propose_upgrades(observations)

    assert first == second
    assert first.count("- ") >= 1
