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


def test_contention_reserves_capacity_for_recovery(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CONTENTION_LIMIT", "4")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RECOVERY_RESERVED_SLOTS", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_TASK_LIMIT", "32")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_AMENDMENT_LIMIT", "32")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    governor = get_runtime_governor()

    allowed_task = governor.admit_action("control_plane_task", "operator", "corr-task", metadata={"subject": "x"})
    denied_amendment = governor.admit_action("amendment_apply", "operator", "corr-amend", metadata={"subject": "policy"})
    recovery = governor.admit_action("repair_action", "codex_healer", "corr-repair", metadata={"subject": "alpha", "anomaly_kind": "hang"})

    assert allowed_task.allowed is True
    assert denied_amendment.allowed is False
    assert denied_amendment.reason == "deferred_reserved_for_recovery"
    assert recovery.allowed is True


def test_federated_deferred_under_pressure_local_repair_allowed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_BLOCK", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_WARN", "0.7")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.9")
    reset_runtime_governor()
    governor = get_runtime_governor()

    federated = governor.admit_action(
        "federated_control",
        "peer-a",
        "corr-fed",
        metadata={"subject": "integrity", "scope": "federated"},
    )
    repair = governor.admit_action(
        "repair_action",
        "codex_healer",
        "corr-local",
        metadata={"subject": "integrity", "anomaly_kind": "signature"},
    )

    assert federated.allowed is False
    assert federated.reason == "deferred_federated_under_storm"
    assert repair.allowed is True
    assert repair.reason == "allowed_recovery_precedence"


def test_low_priority_burst_deferred_at_warn_pressure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_WARN_LOW_PRIORITY_LIMIT", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_TASK_LIMIT", "64")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_BLOCK", "0.95")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_PRESSURE_WARN", "0.7")
    reset_runtime_governor()
    governor = get_runtime_governor()

    first = governor.admit_action("control_plane_task", "operator", "corr-1", metadata={"subject": "t1"})
    second = governor.admit_action("control_plane_task", "operator", "corr-2", metadata={"subject": "t2"})
    third = governor.admit_action("control_plane_task", "operator", "corr-3", metadata={"subject": "t3"})

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.reason == "deferred_low_priority_under_pressure"


def test_decision_contains_arbitration_metadata(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CONTENTION_LIMIT", "2")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RECOVERY_RESERVED_SLOTS", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    governor = get_runtime_governor()

    governor.admit_action("control_plane_task", "operator", "corr-1", metadata={"subject": "t1"})
    denied = governor.admit_action("amendment_apply", "operator", "corr-2", metadata={"subject": "law"})

    assert denied.allowed is False
    assert denied.action_priority == 4
    assert denied.action_family == "amendment"

    decisions = (tmp_path / "governor" / "decisions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    latest = decisions[-1]
    assert '"correlation_id": "corr-2"' in latest
    assert '"decision": "deny"' in latest
    assert '"governor_mode": "enforce"' in latest
    assert '"pressure_snapshot"' in latest
    assert '"action_priority": 4' in latest
    assert '"action_family": "amendment"' in latest


def test_arbitration_is_deterministic_for_same_sequence(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor-a"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CONTENTION_LIMIT", "3")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_RECOVERY_RESERVED_SLOTS", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    reset_runtime_governor()
    gov_a = get_runtime_governor()
    reasons_a = [
        gov_a.admit_action("control_plane_task", "operator", "a-1", metadata={"subject": "t1"}).reason,
        gov_a.admit_action("control_plane_task", "operator", "a-2", metadata={"subject": "t2"}).reason,
        gov_a.admit_action("amendment_apply", "operator", "a-3", metadata={"subject": "law"}).reason,
        gov_a.admit_action("repair_action", "codex_healer", "a-4", metadata={"subject": "alpha", "anomaly_kind": "hang"}).reason,
    ]

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor-b"))
    reset_runtime_governor()
    gov_b = get_runtime_governor()
    reasons_b = [
        gov_b.admit_action("control_plane_task", "operator", "b-1", metadata={"subject": "t1"}).reason,
        gov_b.admit_action("control_plane_task", "operator", "b-2", metadata={"subject": "t2"}).reason,
        gov_b.admit_action("amendment_apply", "operator", "b-3", metadata={"subject": "law"}).reason,
        gov_b.admit_action("repair_action", "codex_healer", "b-4", metadata={"subject": "alpha", "anomaly_kind": "hang"}).reason,
    ]

    assert reasons_a == reasons_b
