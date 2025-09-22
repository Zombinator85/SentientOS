from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

import pytest

from sentientos.daemons.driver_manager import DriverManager
from sentientos.shell import SentientShell, ShellConfig, ShellEventLogger


def _make_clock() -> Callable[[], datetime]:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    counter = {"value": 0}

    def _clock() -> datetime:
        counter["value"] += 1
        return base + timedelta(seconds=counter["value"])

    return _clock


def _gpu_probe_missing_driver() -> list[dict[str, object]]:
    return [
        {
            "id": "gpu-0",
            "kind": "gpu",
            "name": "NVIDIA GTX 1060",
            "vendor": "NVIDIA",
            "current_driver": None,
            "modules": [],
        }
    ]


def _build_manager(
    *,
    hardware_probe: Callable[[], Iterable[dict[str, object]]] | None = None,
    driver_installer: Callable[[object, object], dict[str, object]] | None = None,
    veil_requester: Callable[[object, object, str], None] | None = None,
    clock: Callable[[], datetime] | None = None,
):
    pulses: list[dict[str, object]] = []
    ledger_entries: list[dict[str, object]] = []
    veil_entries: list[dict[str, object]] = []
    install_calls: list[dict[str, object]] = []
    clock = clock or _make_clock()
    probe = hardware_probe or _gpu_probe_missing_driver

    def ledger_writer(path: Path, entry: dict[str, object]) -> None:
        ledger_entries.append(dict(entry))

    def publisher(event: dict[str, object]) -> dict[str, object]:
        pulses.append(dict(event))
        return event

    def default_installer(status, candidate) -> dict[str, object]:
        install_calls.append({"device": status.device_id, "driver": candidate.name})
        return {"status": "success"}

    def wrap_installer(callback: Callable[[object, object], dict[str, object]]):
        def _inner(status, candidate) -> dict[str, object]:
            install_calls.append({"device": status.device_id, "driver": candidate.name})
            return callback(status, candidate)

        return _inner

    def default_veil(status, candidate, token: str) -> None:
        veil_entries.append({"device": status.device_id, "driver": candidate.name, "token": token})

    def wrap_veil(callback: Callable[[object, object, str], None]):
        def _inner(status, candidate, token: str) -> None:
            veil_entries.append({"device": status.device_id, "driver": candidate.name, "token": token})
            callback(status, candidate, token)

        return _inner

    manager = DriverManager(
        ledger_writer=ledger_writer,
        pulse_publisher=publisher,
        hardware_probe=probe,
        driver_installer=wrap_installer(driver_installer) if driver_installer else default_installer,
        veil_requester=wrap_veil(veil_requester) if veil_requester else default_veil,
        clock=clock,
        subscribe_to_pulse=False,
        autoprobe=False,
    )
    return manager, pulses, ledger_entries, veil_entries, install_calls


def test_missing_gpu_triggers_suggestion() -> None:
    manager, pulses, ledger_entries, veil_entries, install_calls = _build_manager()
    manager.refresh()
    suggestion_events = [event for event in pulses if event["event_type"] == "driver_suggestion"]
    assert suggestion_events, "driver_suggestion pulse was not emitted"
    payload = suggestion_events[0]["payload"]
    assert payload["driver"].startswith("nvidia-driver")
    assert payload["device"]["name"] == "NVIDIA GTX 1060"
    assert any(entry["event"] == "driver_suggestion" for entry in ledger_entries)


def test_install_records_ledger_and_pulse() -> None:
    manager, pulses, ledger_entries, veil_entries, install_calls = _build_manager()
    manager.refresh()
    result = manager.install_driver("gpu-0")
    assert result["status"] == "veil_pending"
    assert install_calls, "driver installer was not invoked"
    install_events = [event for event in pulses if event["event_type"] == "driver_install"]
    assert install_events, "driver_install pulse missing"
    assert ledger_entries[-1]["event"] == "driver_install"
    assert veil_entries, "veil request was not queued"
    pending = manager.pending_veil_requests()
    assert pending and pending[0]["device_id"] == "gpu-0"


def test_install_failure_logs() -> None:
    def failing_installer(status, candidate) -> dict[str, object]:  # pragma: no cover - exercised in test
        raise RuntimeError("installer offline")

    manager, pulses, ledger_entries, veil_entries, install_calls = _build_manager(
        driver_installer=failing_installer
    )
    manager.refresh()
    with pytest.raises(RuntimeError):
        manager.install_driver("gpu-0")
    failure_events = [event for event in pulses if event["event_type"] == "driver_failure"]
    assert failure_events
    assert ledger_entries[-1]["event"] == "driver_failure"
    snapshot = manager.snapshot()
    assert snapshot["devices"][0]["status"] == "error"


def test_shell_dashboard_driver_panel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    manager, pulses, ledger_entries, veil_entries, install_calls = _build_manager()

    shell_pulses: list[dict[str, object]] = []
    shell_ledger: list[dict[str, object]] = []

    def shell_publisher(event: dict[str, object]) -> dict[str, object]:
        shell_pulses.append(dict(event))
        return event

    def shell_ledger_writer(path: Path, entry: dict[str, object]) -> None:
        shell_ledger.append(dict(entry))

    logger = ShellEventLogger(
        ledger_path=tmp_path / "shell_ledger.jsonl",
        pulse_publisher=shell_publisher,
        ledger_writer=shell_ledger_writer,
    )
    config = ShellConfig(path=tmp_path / "shell_config.json")
    shell = SentientShell(
        user="tester",
        logger=logger,
        config=config,
        request_dir=tmp_path / "requests",
        trace_dir=tmp_path / "traces",
        codex_module=None,
        pulse_publisher=shell_publisher,
        home_root=tmp_path / "home" / "tester",
        driver_manager=manager,
    )

    snapshot = shell.open_lumos_dashboard()
    drivers_panel = snapshot["drivers"]
    assert drivers_panel["devices"], "driver devices should be listed"
    assert drivers_panel["devices"][0]["status"] == "missing"

    install_result = shell.install_recommended_driver("gpu-0")
    assert install_result["requires_veil"] is True
    assert veil_entries

    snapshot_after = shell.open_lumos_dashboard()
    assert snapshot_after["drivers"]["devices"][0]["status"] == "veil_pending"
