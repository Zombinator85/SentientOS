from __future__ import annotations

from datetime import datetime, timezone

from sentientos.runtime_governor import get_runtime_governor, reset_runtime_governor


def test_governor_enforce_blocks_restart_budget(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RESTART_LIMIT", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    governor = get_runtime_governor()

    first = governor.admit_restart(daemon_name="alpha", scope="local", origin="local")
    second = governor.admit_restart(daemon_name="alpha", scope="local", origin="local")

    assert first.allowed is True
    assert second.allowed is False
    assert second.reason == "restart_budget_exceeded"


def test_governor_shadow_logs_without_blocking(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "shadow")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_REPAIR_LIMIT", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.95")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.95")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.95")
    reset_runtime_governor()
    governor = get_runtime_governor()

    first = governor.admit_repair(anomaly_kind="daemon_unresponsive", subject="alpha")
    second = governor.admit_repair(anomaly_kind="daemon_unresponsive", subject="alpha")

    assert first.allowed is True
    assert second.allowed is True


def test_scheduling_window_reflects_pressure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "advisory")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_SCHEDULING_THRESHOLD", "0.5")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.2")
    reset_runtime_governor()
    governor = get_runtime_governor()

    assert governor.scheduling_window_open() is True

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "1.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "1.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "1.0")
    reset_runtime_governor()
    governor = get_runtime_governor()
    assert governor.scheduling_window_open() is False


def test_decision_reason_hash_is_stable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.2")
    reset_runtime_governor()
    governor = get_runtime_governor()

    fixed = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
    governor.observe_pulse_event(
        {
            "timestamp": fixed,
            "source_daemon": "network",
            "event_type": "enforcement",
            "priority": "critical",
            "payload": {},
        }
    )
    decision = governor.admit_federated_control(subject="network", origin="peer-a", metadata={"event_type": "restart_request"})
    assert len(decision.reason_hash) == 64


def test_federated_control_blocked_by_critical_storm(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CRITICAL_LIMIT", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.2")
    reset_runtime_governor()
    governor = get_runtime_governor()

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "network",
        "event_type": "critical_alarm",
        "priority": "critical",
        "payload": {},
    }
    governor.observe_pulse_event(event)
    governor.observe_pulse_event(event)

    decision = governor.admit_federated_control(subject="network", origin="peer-a")
    assert decision.allowed is False
    assert decision.reason == "critical_event_storm_detected"


def test_admit_action_routes_control_plane_task(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_TASK_LIMIT", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    governor = get_runtime_governor()

    first = governor.admit_action(
        "control_plane_task",
        "operator",
        "corr-1",
        metadata={"subject": "TASK_EXECUTION"},
    )
    second = governor.admit_action(
        "control_plane_task",
        "operator",
        "corr-2",
        metadata={"subject": "TASK_EXECUTION"},
    )

    assert first.allowed is True
    assert second.allowed is False
    assert second.reason == "control_plane_task_rate_exceeded"
