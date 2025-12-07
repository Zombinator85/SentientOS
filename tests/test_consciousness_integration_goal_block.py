from sentientos.consciousness import integration


def test_cycle_blocked_when_narrative_goal_unsatisfied(monkeypatch):
    monkeypatch.setattr(
        integration, "narrative_goal_satisfied", lambda goal: False, raising=True
    )

    result = integration.run_consciousness_cycle({})

    assert result == {"status": "narrative_goal_block", "ok": False}


def test_cycle_block_deterministic(monkeypatch):
    monkeypatch.setattr(
        integration, "narrative_goal_satisfied", lambda goal: False, raising=True
    )

    first = integration.run_consciousness_cycle({})
    second = integration.run_consciousness_cycle({})

    assert first == {"status": "narrative_goal_block", "ok": False}
    assert second == {"status": "narrative_goal_block", "ok": False}
