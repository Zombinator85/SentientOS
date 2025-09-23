"""Integration tests covering ArchitectDaemon and FirstBootWizard coupling."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

import architect_daemon
from sentientos.daemons import pulse_bus
from sentientos.first_boot import FirstBootWizard, WizardDecisions


def _fixed_clock() -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc)


def _write_config(path: Path, *, autonomy: bool = False) -> None:
    payload = {
        "codex_mode": "observe",
        "codex_interval": 3600,
        "codex_max_iterations": 1,
        "architect_autonomy": autonomy,
        "federation_peer_name": "",
        "federation_peers": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")


@pytest.fixture(autouse=True)
def reset_pulse_bus() -> None:
    pulse_bus.reset()
    yield
    pulse_bus.reset()


def test_daemon_inactive_until_first_boot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request_dir = tmp_path / "requests"
    config_path = tmp_path / "vow" / "config.yaml"
    completion_path = tmp_path / "vow" / "first_boot_complete"
    _write_config(config_path)
    ledger_events: list[dict[str, object]] = []

    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")

    daemon = architect_daemon.ArchitectDaemon(
        request_dir=request_dir,
        session_file=tmp_path / "session.json",
        ledger_path=tmp_path / "ledger.jsonl",
        config_path=config_path,
        completion_path=completion_path,
        ledger_sink=ledger_events.append,
        pulse_publisher=pulse_bus.publish,
        clock=_fixed_clock,
        ci_commands=[["true"]],
        immutability_command=["true"],
    )

    daemon.start()
    assert daemon.active is False

    with pytest.raises(RuntimeError):
        daemon.request_expand("pre_blessing", None)

    pulse_bus.publish(
        {
            "timestamp": _fixed_clock().isoformat(),
            "source_daemon": "MonitoringDaemon",
            "event_type": "monitor_alert",
            "priority": "critical",
            "payload": {"detail": "cpu"},
        }
    )

    assert not any(request_dir.glob("architect_*.txt"))
    assert not ledger_events


def test_wizard_completion_activates_daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request_dir = tmp_path / "requests"
    config_path = tmp_path / "vow" / "config.yaml"
    completion_path = tmp_path / "vow" / "first_boot_complete"
    ledger_events: list[dict[str, object]] = []
    pulse_bus.reset()

    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")

    daemon = architect_daemon.ArchitectDaemon(
        request_dir=request_dir,
        session_file=tmp_path / "session.json",
        ledger_path=tmp_path / "ledger.jsonl",
        config_path=config_path,
        completion_path=completion_path,
        ledger_sink=ledger_events.append,
        pulse_publisher=pulse_bus.publish,
        clock=_fixed_clock,
        ci_commands=[["true"]],
        immutability_command=["true"],
    )
    daemon.start()
    assert daemon.active is False

    wizard = FirstBootWizard(
        driver_manager=None,
        ledger_path=tmp_path / "daemon" / "ledger.jsonl",
        config_path=config_path,
        completion_path=completion_path,
        ledger_writer=lambda path, entry: None,
        pulse_publisher=pulse_bus.publish,
        blessing_hook=lambda: None,
        clock=_fixed_clock,
    )

    wizard.run(decisions=WizardDecisions(codex_mode="repair", codex_interval=1800), force=True)

    assert daemon.active is True
    enabled_events = [entry for entry in ledger_events if entry.get("event") == "architect_enabled"]
    assert enabled_events
    summary = enabled_events[0]["summary"]
    assert summary["codex_mode"] == "repair"
    assert summary["codex_interval"] == 1800

    published = pulse_bus.consume_events()
    assert any(event["event_type"] == "architect_enabled" for event in published)


def test_config_change_emits_update(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request_dir = tmp_path / "requests"
    config_path = tmp_path / "vow" / "config.yaml"
    completion_path = tmp_path / "vow" / "first_boot_complete"
    ledger_events: list[dict[str, object]] = []

    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")

    daemon = architect_daemon.ArchitectDaemon(
        request_dir=request_dir,
        session_file=tmp_path / "session.json",
        ledger_path=tmp_path / "ledger.jsonl",
        config_path=config_path,
        completion_path=completion_path,
        ledger_sink=ledger_events.append,
        pulse_publisher=pulse_bus.publish,
        clock=_fixed_clock,
        ci_commands=[["true"]],
        immutability_command=["true"],
    )
    daemon.start()

    wizard = FirstBootWizard(
        driver_manager=None,
        ledger_path=tmp_path / "daemon" / "ledger.jsonl",
        config_path=config_path,
        completion_path=completion_path,
        ledger_writer=lambda path, entry: None,
        pulse_publisher=pulse_bus.publish,
        blessing_hook=lambda: None,
        clock=_fixed_clock,
    )
    wizard.run(decisions=WizardDecisions(codex_mode="expand", codex_interval=1800), force=True)

    pulse_bus.consume_events()
    ledger_events.clear()

    wizard.run(
        decisions=WizardDecisions(codex_mode="full", codex_interval=600, architect_autonomy=True),
        force=True,
    )

    assert pytest.approx(daemon.interval) == 600
    assert daemon.active is True
    config_updates = [entry for entry in ledger_events if entry.get("event") == "architect_config_update"]
    assert config_updates
    changes = config_updates[0]["changes"]
    assert "codex_mode" in changes
    assert changes["architect_autonomy"]["current"] is True


def test_autonomy_toggle_controls_submission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request_dir = tmp_path / "requests"
    config_path = tmp_path / "vow" / "config.yaml"
    completion_path = tmp_path / "vow" / "first_boot_complete"
    ledger_events: list[dict[str, object]] = []

    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")

    daemon = architect_daemon.ArchitectDaemon(
        request_dir=request_dir,
        session_file=tmp_path / "session.json",
        ledger_path=tmp_path / "ledger.jsonl",
        config_path=config_path,
        completion_path=completion_path,
        ledger_sink=ledger_events.append,
        pulse_publisher=pulse_bus.publish,
        clock=_fixed_clock,
        ci_commands=[["true"]],
        immutability_command=["true"],
    )
    daemon.start()

    wizard = FirstBootWizard(
        driver_manager=None,
        ledger_path=tmp_path / "daemon" / "ledger.jsonl",
        config_path=config_path,
        completion_path=completion_path,
        ledger_writer=lambda path, entry: None,
        pulse_publisher=pulse_bus.publish,
        blessing_hook=lambda: None,
        clock=_fixed_clock,
    )
    wizard.run(
        decisions=WizardDecisions(codex_mode="repair", architect_autonomy=False),
        force=True,
    )
    pulse_bus.consume_events()
    ledger_events.clear()

    request = daemon.request_expand("improvement", None)
    pending_events = [entry for entry in ledger_events if entry.get("event") == "architect_prompt_pending"]
    submitted_events = [entry for entry in ledger_events if entry.get("event") == "architect_prompt_submitted"]
    assert pending_events
    assert not submitted_events
    assert daemon.active is True

    wizard.run(
        decisions=WizardDecisions(codex_mode="repair", architect_autonomy=True),
        force=True,
    )
    pulse_bus.consume_events()
    ledger_events.clear()

    daemon.request_expand("autonomous", None)
    submitted_events = [entry for entry in ledger_events if entry.get("event") == "architect_prompt_submitted"]
    assert submitted_events
    assert daemon.active is True
