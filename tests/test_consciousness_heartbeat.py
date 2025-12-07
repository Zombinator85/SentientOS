import sentientos.consciousness.integration as integration
from sentientos.consciousness.recursion_guard import RecursionGuard


def test_run_cycle_heartbeat_interrupt(monkeypatch):
    monkeypatch.setattr(integration, "daemon_heartbeat", lambda: False)

    result = integration.run_consciousness_cycle({})

    assert result == {
        "status": "error",
        "error": "heartbeat_interrupt",
        "message": "Daemon heartbeat check failed",
    }


def test_run_cycle_recursion_limit_error(monkeypatch):
    guard = RecursionGuard(max_depth=0)
    monkeypatch.setattr(integration, "_RECURSION_GUARD", guard)

    result = integration.run_consciousness_cycle({})

    assert result["error"] == "recursion_limit_exceeded"
    assert guard.depth == 0


def test_run_cycle_depth_does_not_leak(monkeypatch):
    guard = RecursionGuard(max_depth=2)
    monkeypatch.setattr(integration, "_RECURSION_GUARD", guard)

    first = integration.run_consciousness_cycle({})
    second = integration.run_consciousness_cycle({})

    assert first.get("error") is None
    assert second.get("error") is None
    assert guard.depth == 0
