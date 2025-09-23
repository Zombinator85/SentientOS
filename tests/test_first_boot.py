from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import pytest
import yaml

from sentientos.first_boot import FirstBootWizard, WizardDecisions
from sentientos.shell import SentientShell, ShellConfig, ShellEventLogger


class DummyDriverManager:
    def __init__(self) -> None:
        self.refresh_calls = 0
        self.installs: List[str] = []

    def refresh(self) -> dict[str, object]:
        self.refresh_calls += 1
        return {
            "devices": [
                {
                    "id": "gpu-1",
                    "name": "NVIDIA RTX 4090",
                    "status": "missing",
                    "needs_driver": True,
                    "recommended_driver": "nvidia-driver",
                }
            ]
        }

    def install_driver(self, device_id: str) -> dict[str, object]:
        self.installs.append(device_id)
        return {
            "device_id": device_id,
            "device": "NVIDIA RTX 4090",
            "driver": "nvidia-driver",
            "status": "veil_pending",
            "requires_veil": True,
        }


class RecordingWizard:
    def __init__(self) -> None:
        self.run_calls: List[Dict[str, object]] = []
        self.reset_calls = 0
        self._summary: dict[str, object] = {
            "status": "completed",
            "drivers": [],
            "codex": {},
            "federation": {},
        }
        self._should_run = True

    def should_run(self) -> bool:
        return self._should_run

    def run(self, decisions=None, force: bool = False) -> dict[str, object]:
        self.run_calls.append({"decisions": decisions, "force": force})
        self._should_run = False
        return dict(self._summary)

    def reset(self) -> None:
        self.reset_calls += 1
        self._should_run = True

    @property
    def last_summary(self) -> dict[str, object]:
        return dict(self._summary)


def test_wizard_requires_blessing(tmp_path: Path) -> None:
    ledger_entries: List[dict[str, object]] = []
    pulses: List[dict[str, object]] = []

    def ledger_writer(path: Path, entry: dict[str, object]) -> None:
        ledger_entries.append({"path": path, "entry": dict(entry)})

    def pulse(event: dict[str, object]) -> dict[str, object]:
        pulses.append(dict(event))
        return event

    wizard = FirstBootWizard(
        driver_manager=None,
        ledger_path=tmp_path / "daemon/logs/ledger.jsonl",
        config_path=tmp_path / "vow/config.yaml",
        completion_path=tmp_path / "vow/first_boot_complete",
        ledger_writer=ledger_writer,
        pulse_publisher=pulse,
        blessing_hook=lambda: None,
    )

    with pytest.raises(PermissionError):
        wizard.run(decisions=WizardDecisions(bless=False), force=True)

    assert any(item["entry"]["event"] == "first_boot_step" for item in ledger_entries)
    assert all(event["event_type"] == "first_boot_step" for event in pulses)


def test_wizard_configures_codex_and_federation(tmp_path: Path) -> None:
    driver_manager = DummyDriverManager()
    ledger_entries: List[dict[str, object]] = []
    pulses: List[dict[str, object]] = []
    blessing_calls: List[str] = []
    connectivity_checks: List[tuple[str, str]] = []

    def ledger_writer(path: Path, entry: dict[str, object]) -> None:
        ledger_entries.append({"path": path, "entry": dict(entry)})

    def pulse(event: dict[str, object]) -> dict[str, object]:
        pulses.append(dict(event))
        return event

    wizard = FirstBootWizard(
        driver_manager=driver_manager,
        ledger_path=tmp_path / "daemon/logs/ledger.jsonl",
        config_path=tmp_path / "vow/config.yaml",
        completion_path=tmp_path / "vow/first_boot_complete",
        ledger_writer=ledger_writer,
        pulse_publisher=pulse,
        blessing_hook=lambda: blessing_calls.append("called"),
        connectivity_tester=lambda peer, address: (connectivity_checks.append((peer, address)) or True),
        clock=lambda: datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    decisions = WizardDecisions(
        bless=True,
        driver_choices={"gpu-1": True},
        codex_mode="expand",
        codex_interval=7200,
        codex_max_iterations=5,
        federation_peer_name="Aurora",
        federation_addresses=("tcp://aurora:7777",),
    )

    summary = wizard.run(decisions=decisions, force=True)

    assert blessing_calls == ["called"]
    assert driver_manager.installs == ["gpu-1"]
    assert (tmp_path / "vow/first_boot_complete").exists()

    config = yaml.safe_load((tmp_path / "vow/config.yaml").read_text(encoding="utf-8"))
    assert config["codex_mode"] == "expand"
    assert config["codex_interval"] == 7200
    assert config["codex_max_iterations"] == 5
    assert config["architect_autonomy"] is False
    assert config["federation_peer_name"] == "Aurora"
    assert config["federation_peers"] == ["tcp://aurora:7777"]

    events = [item["entry"]["event"] for item in ledger_entries]
    assert "first_boot_blessed" in events
    assert "first_boot_codex_configured" in events
    assert "first_boot_federation_configured" in events
    assert any(event["event_type"] == "first_boot_complete" for event in pulses)

    assert summary["codex"]["mode"] == "expand"
    assert summary["codex"]["autonomy_enabled"] is False
    assert summary["drivers"][0]["requires_veil"] is True
    assert summary["federation"]["connectivity"]["tcp://aurora:7777"] is True
    assert connectivity_checks == [("Aurora", "tcp://aurora:7777")]
    assert len(wizard.panels) >= 4
    assert wizard.last_summary == summary


def test_wizard_skip_when_completed(tmp_path: Path) -> None:
    ledger_entries: List[dict[str, object]] = []
    blessing_calls: List[str] = []

    def ledger_writer(path: Path, entry: dict[str, object]) -> None:
        ledger_entries.append(dict(entry))

    wizard = FirstBootWizard(
        driver_manager=None,
        ledger_path=tmp_path / "daemon/logs/ledger.jsonl",
        config_path=tmp_path / "vow/config.yaml",
        completion_path=tmp_path / "vow/first_boot_complete",
        ledger_writer=ledger_writer,
        pulse_publisher=lambda event: event,
        blessing_hook=lambda: blessing_calls.append("blessed"),
    )

    wizard.run(decisions=WizardDecisions(), force=True)
    initial_ledger_count = len(ledger_entries)
    assert blessing_calls == ["blessed"]

    result = wizard.run()
    assert result == {"status": "skipped", "reason": "first_boot_complete"}
    assert len(ledger_entries) == initial_ledger_count
    assert blessing_calls == ["blessed"]


def test_shell_integration_invokes_wizard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    pulses: List[dict[str, object]] = []

    def pulse(event: dict[str, object]) -> dict[str, object]:
        pulses.append(dict(event))
        return event

    logger = ShellEventLogger(
        ledger_path=tmp_path / "logs" / "shell.jsonl",
        pulse_publisher=pulse,
    )
    wizard = RecordingWizard()

    shell = SentientShell(
        user="tester",
        logger=logger,
        config=ShellConfig(path=tmp_path / "shell_config.json"),
        request_dir=tmp_path / "requests",
        trace_dir=tmp_path / "traces",
        codex_module=None,
        ci_runner=lambda: True,
        pulse_publisher=pulse,
        home_root=tmp_path / "home" / "tester",
        first_boot_wizard=wizard,
    )

    assert wizard.run_calls == [{"decisions": None, "force": False}]
    assert shell.first_boot_summary == wizard.last_summary

    search_results = shell.search("first-boot")
    assert "re-run first-boot wizard" in search_results["settings"]

    rerun_summary = shell.start_menu.open_setting("Re-run First-Boot Wizard")
    assert rerun_summary == wizard.last_summary
    assert wizard.reset_calls == 1
    assert wizard.run_calls[-1]["force"] is True
    assert shell.first_boot_summary == wizard.last_summary
