from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

import pytest

import architect_daemon
from sentientos.shell import SystemDashboard


class _FakeClock:
    def __init__(self) -> None:
        self._now = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self._now

    def advance(self, seconds: int) -> datetime:
        self._now += timedelta(seconds=seconds)
        return self._now


class _DummyLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def record(self, event_type: str, payload: dict[str, object]) -> dict[str, object]:
        self.events.append((event_type, payload))
        return {"event": event_type, "payload": payload}


class _DummyConfig:
    def snapshot(self) -> dict[str, object]:
        return {
            "federation_peers": [],
            "auto_apply_predictive": False,
            "auto_apply_federated": False,
        }


def _build_daemon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_clock: _FakeClock,
    ledger_events: list[dict[str, object]],
    published: list[dict[str, object]],
    *,
    trajectory_interval: int = 2,
) -> tuple[architect_daemon.ArchitectDaemon, Path, Path, Path]:
    config_path = tmp_path / "vow" / "config.yaml"
    completion_path = tmp_path / "vow" / "first_boot_complete"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            [
                "codex_mode: expand",
                "codex_interval: 3600",
                "codex_max_iterations: 1",
                "architect_autonomy: true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    completion_path.parent.mkdir(parents=True, exist_ok=True)
    completion_path.write_text("completed\n", encoding="utf-8")

    cycle_dir = tmp_path / "cycles"
    reflection_dir = tmp_path / "reflections"
    trajectory_dir = tmp_path / "trajectories"
    request_dir = tmp_path / "requests"
    session_file = tmp_path / "session.json"
    ledger_path = tmp_path / "ledger.jsonl"

    monkeypatch.setattr(architect_daemon, "ARCHITECT_CYCLE_DIR", cycle_dir)
    monkeypatch.setattr(architect_daemon, "ARCHITECT_TRAJECTORY_DIR", trajectory_dir)
    monkeypatch.setattr(
        architect_daemon, "ARCHITECT_TRAJECTORY_INTERVAL", trajectory_interval
    )
    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")

    def fake_run(
        cmd: list[str],
        capture_output: bool = False,
        text: bool = False,
        **_: object,
    ) -> SimpleNamespace:
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(architect_daemon.subprocess, "run", fake_run)

    daemon = architect_daemon.ArchitectDaemon(
        request_dir=request_dir,
        session_file=session_file,
        ledger_path=ledger_path,
        config_path=config_path,
        completion_path=completion_path,
        reflection_dir=reflection_dir,
        cycle_dir=cycle_dir,
        trajectory_dir=trajectory_dir,
        trajectory_interval=trajectory_interval,
        ledger_sink=ledger_events.append,
        pulse_publisher=lambda event: (published.append(event) or event),
        clock=fake_clock,
        ci_commands=[["true"]],
        immutability_command=["true"],
    )
    return daemon, cycle_dir, trajectory_dir, ledger_path


def _start_backlog_cycle(
    daemon: architect_daemon.ArchitectDaemon,
    fake_clock: _FakeClock,
    *,
    priority_id: str = "prio-1",
    text: str = "Backlog item",
) -> architect_daemon.ArchitectRequest:
    daemon._priority_active.clear()
    daemon._priority_index.clear()
    entry = {"id": priority_id, "text": text, "status": "pending"}
    daemon._priority_active.append(entry)
    daemon._priority_index[priority_id] = entry
    request = daemon._begin_cycle(trigger="scheduled", timestamp=fake_clock())
    assert request is not None
    return request


def _finalize_cycle(
    daemon: architect_daemon.ArchitectDaemon,
    request: architect_daemon.ArchitectRequest,
    fake_clock: _FakeClock,
    *,
    status: str,
    reason: str | None = None,
) -> None:
    fake_clock.advance(45)
    daemon._finalize_cycle_summary(request, result=status, reason=reason)
    daemon._requests.pop(request.architect_id, None)


def test_trajectory_report_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    fake_clock = _FakeClock()
    daemon, _, trajectory_dir, _ = _build_daemon(
        tmp_path, monkeypatch, fake_clock, ledger_events, published, trajectory_interval=2
    )

    first = _start_backlog_cycle(daemon, fake_clock, priority_id="prio-1", text="alpha")
    daemon._record_cycle_backlog_outcome("prio-1", status="done", reason=None)
    _finalize_cycle(daemon, first, fake_clock, status="merged")

    second = _start_backlog_cycle(daemon, fake_clock, priority_id="prio-2", text="beta")
    daemon._record_cycle_backlog_outcome("prio-2", status="done", reason=None)
    _finalize_cycle(daemon, second, fake_clock, status="merged")

    reports = sorted(trajectory_dir.glob("trajectory_*.json"))
    assert len(reports) == 1
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    assert payload["trajectory_id"]
    assert len(payload["cycles_included"]) == 2
    assert pytest.approx(payload["success_rate"], rel=1e-3) == 1.0

    ledger_events_names = [entry["event"] for entry in ledger_events]
    assert "architect_trajectory_start" in ledger_events_names
    assert "architect_trajectory_report" in ledger_events_names

    pulse_events = [event["event_type"] for event in published]
    assert "architect_trajectory_start" in pulse_events
    assert "architect_trajectory_report" in pulse_events


def test_trajectory_validation_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    fake_clock = _FakeClock()
    daemon, _, trajectory_dir, _ = _build_daemon(
        tmp_path, monkeypatch, fake_clock, ledger_events, published, trajectory_interval=1
    )

    monkeypatch.setattr(
        daemon,
        "_validate_trajectory_report",
        lambda report: (False, "schema_error"),
    )

    request = _start_backlog_cycle(daemon, fake_clock, priority_id="prio-x", text="gamma")
    daemon._record_cycle_backlog_outcome("prio-x", status="done", reason=None)
    _finalize_cycle(daemon, request, fake_clock, status="merged")

    assert not list(trajectory_dir.glob("trajectory_*.json"))
    ledger_events_names = [entry["event"] for entry in ledger_events]
    assert "architect_trajectory_failed" in ledger_events_names
    pulse_events = [event["event_type"] for event in published]
    assert "architect_trajectory_failed" in pulse_events


def test_trajectory_recurring_regressions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    fake_clock = _FakeClock()
    daemon, _, trajectory_dir, _ = _build_daemon(
        tmp_path, monkeypatch, fake_clock, ledger_events, published, trajectory_interval=2
    )

    label = "test_bandwidth_event_emits"

    first = _start_backlog_cycle(daemon, fake_clock, priority_id="prio-a", text=label)
    daemon._record_cycle_backlog_outcome("prio-a", status="failed", reason="flaky")
    _finalize_cycle(daemon, first, fake_clock, status="blocked", reason="failed")

    second = _start_backlog_cycle(daemon, fake_clock, priority_id="prio-b", text=label)
    daemon._record_cycle_backlog_outcome("prio-b", status="discarded", reason="timeout")
    _finalize_cycle(daemon, second, fake_clock, status="blocked", reason="failed")

    report_path = next(trajectory_dir.glob("trajectory_*.json"))
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert label in payload["recurring_regressions"]
    assert payload["priority_followthrough"]["planned"] >= 0


def test_dashboard_includes_trajectory_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    fake_clock = _FakeClock()
    daemon, _, trajectory_dir, ledger_path = _build_daemon(
        tmp_path, monkeypatch, fake_clock, ledger_events, published, trajectory_interval=1
    )

    request = _start_backlog_cycle(daemon, fake_clock, priority_id="prio-z", text="delta")
    daemon._record_cycle_backlog_outcome("prio-z", status="done", reason=None)
    _finalize_cycle(daemon, request, fake_clock, status="merged")

    reports = list(trajectory_dir.glob("trajectory_*.json"))
    assert reports

    logger = _DummyLogger()
    dashboard = SystemDashboard(
        logger,
        ledger_path=ledger_path,
        file_explorer=SimpleNamespace(),
        config=_DummyConfig(),
        codex_console=SimpleNamespace(),
    )
    snapshot = dashboard.refresh()
    trajectories = snapshot["trajectories"]
    assert isinstance(trajectories, Mapping)
    reports_payload = trajectories.get("reports", [])
    assert reports_payload
    latest = reports_payload[0]
    assert latest["trajectory_id"]
    assert latest["report_path"]
    charts = trajectories.get("charts", {})
    assert charts.get("success_ratio")
    assert isinstance(charts.get("followthrough"), list)

