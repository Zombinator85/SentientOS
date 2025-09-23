from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

import pytest

import architect_daemon
import reflection_dashboard


class _StubResult(SimpleNamespace):
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


def _setup_daemon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    peer_name: str = "alpha",
) -> tuple[architect_daemon.ArchitectDaemon, list[dict[str, object]], list[dict[str, object]], Path]:
    pulses: list[dict[str, object]] = []
    ledger_events: list[dict[str, object]] = []

    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")

    def fake_run(
        cmd: list[str] | tuple[str, ...],
        capture_output: bool = False,
        text: bool = False,
        **_: object,
    ) -> _StubResult:
        return _StubResult(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(architect_daemon.subprocess, "run", fake_run)

    request_dir = tmp_path / "requests"
    session_file = tmp_path / "session.json"
    ledger_path = tmp_path / "ledger.jsonl"
    config_path = tmp_path / "config.yaml"
    reflection_dir = tmp_path / "reflections"
    reflection_dir.mkdir(parents=True, exist_ok=True)
    priority_path = reflection_dir / "priorities.json"

    config_payload = {
        "codex_mode": "expand",
        "codex_interval": 3600,
        "codex_max_iterations": 2,
        "architect_autonomy": True,
        "federate_priorities": True,
        "federation_peer_name": peer_name,
    }
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")

    completion_path = tmp_path / "vow" / "first_boot_complete"
    completion_path.parent.mkdir(parents=True, exist_ok=True)
    completion_path.write_text("done", encoding="utf-8")

    clock_value = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def fixed_clock() -> datetime:
        return clock_value

    daemon = architect_daemon.ArchitectDaemon(
        request_dir=request_dir,
        session_file=session_file,
        ledger_path=ledger_path,
        config_path=config_path,
        completion_path=completion_path,
        reflection_dir=reflection_dir,
        priority_path=priority_path,
        reflection_interval=2,
        ledger_sink=ledger_events.append,
        pulse_publisher=lambda event: (pulses.append(event) or event),
        clock=fixed_clock,
        ci_commands=[["true"]],
        immutability_command=["true"],
    )
    daemon.start()
    pulses.clear()
    ledger_events.clear()
    return daemon, ledger_events, pulses, priority_path


def _run_reflection(
    daemon: architect_daemon.ArchitectDaemon, payload: Mapping[str, object]
) -> None:
    daemon._cycle_counter = daemon._reflection_interval - 1
    request = daemon._begin_cycle(trigger="scheduled", timestamp=daemon._now())
    assert request is not None and request.mode == "reflect"
    entry = {
        "event": "self_reflection",
        "request_id": request.codex_prefix + "result",
        "reflection": json.dumps(payload),
    }
    daemon.handle_ledger_entry(entry)


def test_backlog_shared_pulse_emitted_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon, ledger_events, pulses, priority_path = _setup_daemon(tmp_path, monkeypatch)

    payload = {
        "summary": "Sync backlog",
        "successes": [],
        "failures": [],
        "regressions": [],
        "next_priorities": ["Harden API", "Document federation"],
    }
    _run_reflection(daemon, payload)

    shared = [evt for evt in pulses if evt.get("event_type") == "architect_backlog_shared"]
    assert shared, "backlog share pulse emitted"
    share_event = shared[0]
    assert share_event.get("source_peer") == "alpha"
    diff = share_event.get("payload", {}).get("diff", {})
    assert diff.get("added"), "diff includes new priorities"
    backlog = json.loads(priority_path.read_text(encoding="utf-8"))
    assert backlog.get("federated") == []
    ledger_shared = [evt for evt in ledger_events if evt.get("event") == "architect_backlog_shared"]
    assert ledger_shared and ledger_shared[0]["source_peer"] == "alpha"


def test_peer_backlog_storage_with_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon, ledger_events, pulses, priority_path = _setup_daemon(tmp_path, monkeypatch)

    peer_event = {
        "timestamp": daemon._now().isoformat(),
        "source_daemon": "ArchitectDaemon",
        "event_type": "architect_backlog_shared",
        "priority": "info",
        "source_peer": "beta",
        "payload": {
            "pending": [{"text": "Sync docs"}],
            "diff": {"added": [{"text": "Sync docs"}], "updated": [], "removed": []},
        },
        "signature": "valid",
    }

    monkeypatch.setattr(architect_daemon.pulse_bus, "verify", lambda evt: True)

    daemon.handle_pulse(peer_event)

    peer_file = daemon._peer_backlog_dir / "beta.json"
    assert peer_file.exists()
    stored = json.loads(peer_file.read_text(encoding="utf-8"))
    assert stored["peer"] == "beta"
    assert stored["updates"], "backlog updates recorded"
    latest = stored["updates"][-1]
    assert latest["signature_verified"] is True
    assert latest["pending"][0]["text"] == "Sync docs"
    received = [evt for evt in pulses if evt.get("event_type") == "architect_backlog_received"]
    assert received and received[0]["payload"]["peer"] == "beta"
    ledger_received = [evt for evt in ledger_events if evt.get("event") == "architect_backlog_received"]
    assert ledger_received and ledger_received[0]["peer"] == "beta"


def test_reconciliation_merges_identical_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon, _, pulses, priority_path = _setup_daemon(tmp_path, monkeypatch)
    monkeypatch.setattr(architect_daemon.pulse_bus, "verify", lambda evt: True)

    base_event = {
        "timestamp": daemon._now().isoformat(),
        "source_daemon": "ArchitectDaemon",
        "event_type": "architect_backlog_shared",
        "priority": "info",
        "payload": {
            "pending": [{"text": "Align roadmap"}],
            "diff": {"added": [{"text": "Align roadmap"}], "updated": [], "removed": []},
        },
        "signature": "valid",
    }

    event_beta = dict(base_event, source_peer="beta")
    daemon.handle_pulse(event_beta)
    pulses.clear()

    event_gamma = dict(base_event, source_peer="gamma")
    daemon.handle_pulse(event_gamma)

    backlog = json.loads(priority_path.read_text(encoding="utf-8"))
    federated = backlog.get("federated", [])
    assert len(federated) == 1
    entry = federated[0]
    assert sorted(entry.get("origin_peers", [])) == ["beta", "gamma"]
    assert entry.get("conflict") is False
    assert len(entry.get("variants", [])) == 2


def test_conflict_detection_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon, ledger_events, pulses, _ = _setup_daemon(tmp_path, monkeypatch)
    monkeypatch.setattr(architect_daemon.pulse_bus, "verify", lambda evt: True)

    base_event = {
        "timestamp": daemon._now().isoformat(),
        "source_daemon": "ArchitectDaemon",
        "event_type": "architect_backlog_shared",
        "priority": "info",
        "signature": "valid",
    }

    daemon.handle_pulse(
        {
            **base_event,
            "source_peer": "beta",
            "payload": {
                "pending": [{"text": "Ship API"}],
                "diff": {"added": [{"text": "Ship API"}], "updated": [], "removed": []},
            },
        }
    )
    pulses.clear()
    ledger_events.clear()

    daemon.handle_pulse(
        {
            **base_event,
            "source_peer": "gamma",
            "payload": {
                "pending": [{"text": "Ship API!"}],
                "diff": {"added": [{"text": "Ship API!"}], "updated": [], "removed": []},
            },
        }
    )

    conflict_pulses = [evt for evt in pulses if evt.get("event_type") == "architect_backlog_conflict"]
    assert conflict_pulses, "conflict pulse emitted"
    conflict_ledger = [evt for evt in ledger_events if evt.get("event") == "architect_backlog_conflict"]
    assert conflict_ledger, "conflict recorded in ledger"


def test_dashboard_includes_federated_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon, _, _, priority_path = _setup_daemon(tmp_path, monkeypatch)
    monkeypatch.setattr(architect_daemon.pulse_bus, "verify", lambda evt: True)

    peer_event = {
        "timestamp": daemon._now().isoformat(),
        "source_daemon": "ArchitectDaemon",
        "event_type": "architect_backlog_shared",
        "priority": "info",
        "source_peer": "beta",
        "signature": "valid",
        "payload": {
            "pending": [
                {"text": "Draft spec"},
                {"text": "Draft spec!"},
            ],
            "diff": {"added": [{"text": "Draft spec"}], "updated": [], "removed": []},
        },
    }
    daemon.handle_pulse(peer_event)

    monkeypatch.setattr(reflection_dashboard, "PRIORITY_FILE", priority_path)
    backlog = reflection_dashboard.load_priority_backlog()
    assert backlog["federated"], "federated entries exposed"
    assert isinstance(backlog["conflicts"], list)
