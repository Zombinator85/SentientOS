from __future__ import annotations

import json
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import daemon_manager
from daemon import codex_daemon
from sentientos.daemons import pulse_bus


LEDGER_PATH = Path("/daemon/logs/codex.jsonl")


@pytest.fixture(autouse=True)
def reset_environment():
    daemon_manager.reset()
    pulse_bus.reset()
    codex_daemon.reset_failure_monitor()
    with suppress(FileNotFoundError):
        LEDGER_PATH.unlink()
    yield
    daemon_manager.reset()
    pulse_bus.reset()
    codex_daemon.reset_failure_monitor()
    with suppress(FileNotFoundError):
        LEDGER_PATH.unlink()


def _read_ledger_entries() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    with LEDGER_PATH.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_register_and_restart_cycle():
    instances: list[object] = []

    class DummyDaemon:
        def __init__(self, identifier: int) -> None:
            self.identifier = identifier
            self.alive = True
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True
            self.alive = False

    def start() -> DummyDaemon:
        instance = DummyDaemon(len(instances))
        instances.append(instance)
        return instance

    def stop(instance: DummyDaemon) -> None:
        instance.stop()

    status = daemon_manager.register("alpha", start, stop)
    assert status.name == "alpha"
    assert not status.running

    assert daemon_manager.restart("alpha", reason="unit test")
    assert instances[-1].alive

    second_result = daemon_manager.restart("alpha", reason="cycle check")
    assert second_result is True
    assert len(instances) == 2
    assert instances[0].stopped is True

    current_status = daemon_manager.status("alpha")
    assert current_status.running is True
    assert current_status.last_reason == "cycle check"
    assert current_status.last_outcome == "success"


def test_pulse_triggered_restart_logs_and_emits():
    start_counter = {"count": 0}

    class PulseWorker:
        def __init__(self, run_id: int) -> None:
            self.run_id = run_id
            self.alive = True

        def is_alive(self) -> bool:
            return self.alive

    def start() -> PulseWorker:
        start_counter["count"] += 1
        return PulseWorker(start_counter["count"])

    def stop(instance: PulseWorker) -> None:
        instance.alive = False

    daemon_manager.register("beta", start, stop)

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "network",
        "event_type": "restart_request",
        "priority": "critical",
        "payload": {
            "action": "restart_daemon",
            "daemon": "beta",
            "reason": "pulse_request",
        },
    }
    pulse_bus.publish(event)

    assert start_counter["count"] == 1
    status = daemon_manager.status("beta")
    assert status.running is True
    assert status.last_reason == "pulse_request"

    ledger_entries = _read_ledger_entries()
    assert ledger_entries, "Restart should be logged to ledger"
    assert ledger_entries[-1]["daemon"] == "beta"
    assert ledger_entries[-1]["reason"] == "pulse_request"
    assert ledger_entries[-1]["outcome"] == "success"

    restart_events = [
        evt
        for evt in pulse_bus.pending_events()
        if evt["event_type"] == "daemon_restart" and evt["payload"]["daemon"] == "beta"
    ]
    assert restart_events, "Manager should emit daemon_restart pulse event"
    assert restart_events[-1]["payload"]["outcome"] == "success"
    assert restart_events[-1]["priority"] == "info"


def test_codex_triggers_restart_request_after_repeated_criticals():
    pulse_bus.consume_events()
    base = datetime.now(timezone.utc)
    for offset in range(3):
        event = {
            "timestamp": (base + timedelta(seconds=offset * 60)).isoformat(),
            "source_daemon": "network",
            "event_type": "enforcement",
            "priority": "critical",
            "payload": {"detail": "loop_detected"},
        }
        codex_daemon.CRITICAL_FAILURE_MONITOR.record(event)

    restart_requests = [
        evt
        for evt in pulse_bus.pending_events()
        if evt["event_type"] == "restart_request" and evt["source_daemon"] == "codex"
    ]

    assert restart_requests, "Codex should publish restart request"
    payload = restart_requests[-1]["payload"]
    assert payload["action"] == "restart_daemon"
    assert payload["daemon"] == "network"
    assert "codex_detected_repeated_failures" in payload["reason"]


def test_restart_failure_is_logged_without_crash():
    class FaultyDaemon:
        def __init__(self) -> None:
            self.alive = False

        def is_alive(self) -> bool:
            return False

    def start() -> FaultyDaemon:
        return FaultyDaemon()

    def stop(instance: FaultyDaemon) -> None:
        instance.alive = False

    daemon_manager.register("gamma", start, stop)

    result = daemon_manager.restart("gamma", reason="expected_failure")
    assert result is False

    status = daemon_manager.status("gamma")
    assert status.running is False
    assert status.last_outcome == "failure"
    assert status.last_reason == "expected_failure"
    assert status.last_error is not None

    ledger_entries = _read_ledger_entries()
    assert ledger_entries[-1]["daemon"] == "gamma"
    assert ledger_entries[-1]["outcome"] == "failure"

    restart_events = [
        evt
        for evt in pulse_bus.pending_events()
        if evt["event_type"] == "daemon_restart" and evt["payload"]["daemon"] == "gamma"
    ]
    assert restart_events[-1]["payload"]["outcome"] == "failure"
    assert restart_events[-1]["priority"] == "critical"
