import sentientos.consciousness.integration as integration


def test_cycle_gate_status_ready(monkeypatch):
    monkeypatch.setattr(integration, "daemon_heartbeat", lambda: True)
    monkeypatch.setattr(integration, "current_narrative_goal", lambda: "goal-ready")
    monkeypatch.setattr(integration, "narrative_goal_satisfied", lambda goal: True)

    status = integration.cycle_gate_status()

    assert status == {
        "recursion_ok": True,
        "heartbeat_ok": True,
        "narrative_ok": True,
        "ready": True,
    }


def test_cycle_gate_status_heartbeat_block(monkeypatch):
    monkeypatch.setattr(integration, "daemon_heartbeat", lambda: False)
    monkeypatch.setattr(integration, "current_narrative_goal", lambda: "goal-block")
    monkeypatch.setattr(integration, "narrative_goal_satisfied", lambda goal: True)

    status = integration.cycle_gate_status()

    assert status == {
        "recursion_ok": True,
        "heartbeat_ok": False,
        "narrative_ok": True,
        "ready": False,
    }
