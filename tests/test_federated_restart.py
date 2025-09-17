from __future__ import annotations

import base64
import copy
import json
import os
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

import pytest
from nacl.signing import SigningKey

import daemon_manager
from daemon import codex_daemon
from sentientos.daemons import pulse_bus, pulse_federation
from sentientos.daemons.monitoring_daemon import MonitoringDaemon


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    original_ledger = daemon_manager.LEDGER_PATH
    ledger_path = tmp_path / "federated_ledger.jsonl"
    monkeypatch.setattr(daemon_manager, "LEDGER_PATH", ledger_path)
    daemon_manager.reset()
    pulse_bus.reset()
    pulse_federation.reset()
    codex_daemon.reset_failure_monitor()
    key_dir = tmp_path / "federation_keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PULSE_FEDERATION_KEYS_DIR", str(key_dir))
    yield
    daemon_manager.reset()
    pulse_bus.reset()
    pulse_federation.reset()
    codex_daemon.reset_failure_monitor()
    with suppress(FileNotFoundError):
        ledger_path.unlink()
    monkeypatch.setattr(daemon_manager, "LEDGER_PATH", original_ledger)


def _register_daemon(counter: dict[str, int]) -> None:
    class Worker:
        def __init__(self, run_id: int) -> None:
            self.run_id = run_id
            self.alive = True

        def is_alive(self) -> bool:
            return self.alive

    def start() -> Worker:
        counter["count"] += 1
        return Worker(counter["count"])

    def stop(instance: Worker) -> None:
        instance.alive = False

    daemon_manager.register("testd", start, stop)


def _sign_event(signing_key: SigningKey, event: dict) -> dict:
    payload = copy.deepcopy(event)
    payload.setdefault("priority", "critical")
    signature = signing_key.sign(pulse_bus._serialize_for_signature(payload)).signature
    payload["signature"] = base64.b64encode(signature).decode("ascii")
    return payload


def test_local_restart_request_remains_operational():
    counter = {"count": 0}
    _register_daemon(counter)
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "monitor",
        "event_type": "restart_request",
        "priority": "critical",
        "payload": {
            "action": "restart_daemon",
            "daemon_name": "testd",
            "reason": "local_check",
            "scope": "local",
        },
    }
    pulse_bus.publish(event)
    assert counter["count"] == 1
    status = daemon_manager.status("testd")
    assert status.running is True
    entries = []
    ledger_path = daemon_manager.LEDGER_PATH
    if ledger_path.exists():
        entries = [json.loads(line) for line in ledger_path.read_text().splitlines() if line.strip()]
    assert entries and entries[-1]["scope"] == "local"
    assert entries[-1]["source_peer"] == "local"


def test_federated_restart_requires_valid_signature():
    counter = {"count": 0}
    _register_daemon(counter)
    key_dir = Path(os.environ["PULSE_FEDERATION_KEYS_DIR"])
    signing_key = SigningKey.generate()
    (key_dir / "peer-alpha.pub").write_bytes(signing_key.verify_key.encode())
    pulse_federation.configure(
        enabled=True,
        peers=[{"name": "peer-alpha", "endpoint": "http://peer-alpha"}],
    )

    invalid_event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "codex",
        "event_type": "restart_request",
        "priority": "critical",
        "payload": {
            "action": "restart_daemon",
            "daemon_name": "testd",
            "reason": "remote_invalid",
            "scope": "federated",
        },
        "signature": "invalid",
        "source_peer": "peer-alpha",
    }
    pulse_bus.ingest(invalid_event, source_peer="peer-alpha")
    assert counter["count"] == 0
    ledger_path = daemon_manager.LEDGER_PATH
    assert not ledger_path.exists() or not ledger_path.read_text().strip()


def test_federated_restart_with_valid_signature():
    counter = {"count": 0}
    _register_daemon(counter)
    key_dir = Path(os.environ["PULSE_FEDERATION_KEYS_DIR"])
    signing_key = SigningKey.generate()
    (key_dir / "peer-alpha.pub").write_bytes(signing_key.verify_key.encode())
    pulse_federation.configure(
        enabled=True,
        peers=[{"name": "peer-alpha", "endpoint": "http://peer-alpha"}],
    )

    base_event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "codex",
        "event_type": "restart_request",
        "priority": "critical",
        "payload": {
            "action": "restart_daemon",
            "daemon_name": "testd",
            "reason": "remote_recovery",
            "scope": "federated",
        },
    }
    signed = _sign_event(signing_key, base_event)
    ingested = pulse_federation.ingest_remote_event(signed, "peer-alpha")
    assert ingested["source_peer"] == "peer-alpha"
    assert counter["count"] == 1

    status = daemon_manager.status("testd")
    assert status.running is True
    ledger_entries = []
    ledger_path = daemon_manager.LEDGER_PATH
    if ledger_path.exists():
        ledger_entries = [json.loads(line) for line in ledger_path.read_text().splitlines() if line.strip()]
    assert ledger_entries
    assert ledger_entries[-1]["scope"] == "federated"
    assert ledger_entries[-1]["source_peer"] == "peer-alpha"

    restart_events = [
        evt
        for evt in pulse_bus.pending_events()
        if evt["event_type"] == "daemon_restart"
        and evt["payload"]["daemon_name"] == "testd"
    ]
    assert restart_events
    assert restart_events[-1]["payload"]["scope"] == "federated"
    assert restart_events[-1]["payload"]["requested_by"] == "peer-alpha"


def test_federated_restart_rejected_for_untrusted_peer():
    counter = {"count": 0}
    _register_daemon(counter)
    pulse_federation.configure(
        enabled=True,
        peers=[{"name": "peer-alpha", "endpoint": "http://peer-alpha"}],
    )

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "codex",
        "event_type": "restart_request",
        "priority": "critical",
        "payload": {
            "action": "restart_daemon",
            "daemon_name": "testd",
            "reason": "remote_untrusted",
            "scope": "federated",
        },
        "signature": "untrusted",
        "source_peer": "peer-omega",
    }
    pulse_bus.ingest(event, source_peer="peer-omega")
    assert counter["count"] == 0
    ledger_path = daemon_manager.LEDGER_PATH
    assert not ledger_path.exists() or not ledger_path.read_text().strip()


def test_monitoring_daemon_logs_federated_restart():
    counter = {"count": 0}
    _register_daemon(counter)
    key_dir = Path(os.environ["PULSE_FEDERATION_KEYS_DIR"])
    signing_key = SigningKey.generate()
    (key_dir / "peer-alpha.pub").write_bytes(signing_key.verify_key.encode())
    pulse_federation.configure(
        enabled=True,
        peers=[{"name": "peer-alpha", "endpoint": "http://peer-alpha"}],
    )

    monitor = MonitoringDaemon()
    try:
        base_event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_daemon": "codex",
            "event_type": "restart_request",
            "priority": "critical",
            "payload": {
                "action": "restart_daemon",
                "daemon_name": "testd",
                "reason": "remote_monitor",
                "scope": "federated",
            },
        }
        signed = _sign_event(signing_key, base_event)
        pulse_federation.ingest_remote_event(signed, "peer-alpha")
    finally:
        monitor.stop()

    assert counter["count"] == 1
    assert monitor.federated_restarts
    summary = monitor.federated_restarts[-1]
    assert summary["daemon_name"] == "testd"
    assert summary["requested_by"] == "peer-alpha"
    assert summary["executor_peer"] == "local"
    assert summary["outcome"] == "success"


def test_local_node_ignores_outbound_federated_requests():
    counter = {"count": 0}
    _register_daemon(counter)
    pulse_bus.publish(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_daemon": "codex",
            "event_type": "restart_request",
            "priority": "critical",
            "payload": {
                "action": "restart_daemon",
                "daemon_name": "testd",
                "reason": "peer_request",
                "scope": "federated",
            },
        }
    )
    assert counter["count"] == 0
    ledger_path = daemon_manager.LEDGER_PATH
    assert not ledger_path.exists() or not ledger_path.read_text().strip()
