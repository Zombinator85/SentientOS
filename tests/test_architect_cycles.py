from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

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


def _build_daemon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_clock: _FakeClock,
    ledger_events: list[dict[str, object]],
    published: list[dict[str, object]],
    *,
    reflection_interval: int | None = None,
) -> tuple[architect_daemon.ArchitectDaemon, Path, Path]:
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
    request_dir = tmp_path / "requests"
    session_file = tmp_path / "session.json"
    ledger_path = tmp_path / "ledger.jsonl"

    monkeypatch.setattr(architect_daemon, "ARCHITECT_CYCLE_DIR", cycle_dir)
    
    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")

    def fake_run(
        cmd: list[str],
        capture_output: bool = False,
        text: bool = False,
        **_: object,
    ) -> SimpleNamespace:
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(architect_daemon.subprocess, "run", fake_run)

    extra_kwargs: dict[str, object] = {}
    if reflection_interval is not None:
        extra_kwargs["reflection_interval"] = reflection_interval

    daemon = architect_daemon.ArchitectDaemon(
        request_dir=request_dir,
        session_file=session_file,
        ledger_path=ledger_path,
        config_path=config_path,
        completion_path=completion_path,
        reflection_dir=reflection_dir,
        cycle_dir=cycle_dir,
        ledger_sink=ledger_events.append,
        pulse_publisher=lambda event: (published.append(event) or event),
        clock=fake_clock,
        ci_commands=[["true"]],
        immutability_command=["true"],
        **extra_kwargs,
    )
    return daemon, cycle_dir, ledger_path


def _start_backlog_cycle(
    daemon: architect_daemon.ArchitectDaemon, fake_clock: _FakeClock
) -> architect_daemon.ArchitectRequest:
    daemon._priority_active.clear()
    daemon._priority_index.clear()
    entry = {"id": "prio-1", "text": "Test backlog item", "status": "pending"}
    daemon._priority_active.append(entry)
    daemon._priority_index["prio-1"] = entry
    request = daemon._begin_cycle(trigger="scheduled", timestamp=fake_clock())
    assert request is not None
    return request


def test_cycle_summary_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    fake_clock = _FakeClock()
    daemon, cycle_dir, _ = _build_daemon(tmp_path, monkeypatch, fake_clock, ledger_events, published)

    request = _start_backlog_cycle(daemon, fake_clock)
    fake_clock.advance(60)
    request_id = request.codex_prefix + "abc123"
    daemon.handle_ledger_entry(
        {
            "event": "self_expand",
            "request_id": request_id,
            "files_changed": ["module.py"],
        }
    )

    files = list(cycle_dir.glob("cycle_*.json"))
    assert len(files) == 1
    summary = json.loads(files[0].read_text(encoding="utf-8"))
    assert summary["cycle_id"]
    assert summary["started_at"] and summary["ended_at"]
    assert summary["cooldown"] is False
    assert summary["anomalies"] == []
    assert summary["notes"]
    attempts = summary["backlog_attempts"]
    assert attempts and attempts[0]["status"] == "done"

    ledger_events_types = [entry["event"] for entry in ledger_events]
    assert "architect_cycle_summary" in ledger_events_types
    cycle_event = next(entry for entry in ledger_events if entry["event"] == "architect_cycle_summary")
    assert cycle_event["successes"] == 1
    assert cycle_event["failures"] == 0

    pulse_types = [event["event_type"] for event in published]
    assert "architect_cycle_summary" in pulse_types
    pulse_event = next(event for event in published if event["event_type"] == "architect_cycle_summary")
    assert pulse_event["payload"]["successes"] == 1
    assert Path(pulse_event["payload"]["summary_path"]).exists()


def test_cycle_summary_reflection_and_conflicts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    fake_clock = _FakeClock()
    daemon, cycle_dir, _ = _build_daemon(
        tmp_path,
        monkeypatch,
        fake_clock,
        ledger_events,
        published,
        reflection_interval=1,
    )

    request = daemon._begin_cycle(trigger="scheduled", timestamp=fake_clock())
    assert request is not None and request.cycle_type == "reflection"

    conflict_id = "conflict-1"
    daemon._conflicts[conflict_id] = {
        "conflict_id": conflict_id,
        "status": "accepted",
        "variants": [
            {"peer": "alpha", "text": "Item A", "entry_id": "fed-1"},
            {"peer": "beta", "text": "Item B", "entry_id": "fed-2"},
        ],
        "federated_ids": ["fed-1", "fed-2"],
        "codex": {"suggestion": {"path": "/glow/merge.json", "origin_peers": ["alpha", "beta"]}},
    }
    daemon._record_cycle_conflict(conflict_id)

    fake_clock.advance(120)
    reflection_payload = {
        "summary": "Reviewed cycles",
        "successes": ["win"],
        "failures": ["loss"],
        "regressions": [],
        "next_priorities": [],
    }
    request_id = request.codex_prefix + "xyz"
    daemon.handle_ledger_entry(
        {
            "event": "self_reflection",
            "request_id": request_id,
            "reflection": reflection_payload,
        }
    )

    files = list(cycle_dir.glob("cycle_*.json"))
    assert len(files) == 1
    summary = json.loads(files[0].read_text(encoding="utf-8"))
    assert summary["reflections"]
    conflicts = summary["federation_conflicts"]
    assert conflicts and conflicts[0]["id"] == conflict_id
    assert conflicts[0]["status"] == "resolved"
    assert conflicts[0]["resolution_path"] == "/glow/merge.json"


def test_cycle_summary_validation_failure_emits_alert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    fake_clock = _FakeClock()
    daemon, cycle_dir, _ = _build_daemon(tmp_path, monkeypatch, fake_clock, ledger_events, published)

    request = _start_backlog_cycle(daemon, fake_clock)
    monkeypatch.setattr(
        daemon,
        "_validate_cycle_summary",
        lambda summary: (False, "forced_invalid"),
    )
    fake_clock.advance(30)
    request_id = request.codex_prefix + "fail"
    daemon.handle_ledger_entry(
        {
            "event": "self_expand",
            "request_id": request_id,
            "files_changed": ["module.py"],
        }
    )

    assert not list(cycle_dir.glob("cycle_*.json"))
    failure_events = [entry for entry in ledger_events if entry["event"] == "architect_cycle_summary_failed"]
    assert failure_events and failure_events[0]["reason"] == "forced_invalid"
    pulse_types = [event["event_type"] for event in published]
    assert "architect_cycle_summary_failed" in pulse_types


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


def test_dashboard_cycles_panel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    fake_clock = _FakeClock()
    daemon, cycle_dir, ledger_path = _build_daemon(tmp_path, monkeypatch, fake_clock, ledger_events, published)

    request = _start_backlog_cycle(daemon, fake_clock)
    fake_clock.advance(45)
    request_id = request.codex_prefix + "view"
    daemon.handle_ledger_entry(
        {
            "event": "self_expand",
            "request_id": request_id,
            "files_changed": ["module.py"],
        }
    )

    files = list(cycle_dir.glob("cycle_*.json"))
    assert len(files) == 1
    summary_path = files[0].as_posix()
    summary = json.loads(files[0].read_text(encoding="utf-8"))

    logger = _DummyLogger()
    dashboard = SystemDashboard(
        logger,
        ledger_path=ledger_path,
        file_explorer=SimpleNamespace(),
        config=_DummyConfig(),
        codex_console=SimpleNamespace(),
    )
    snapshot = dashboard.refresh()
    cycles = snapshot["cycles"]
    assert cycles and cycles[0]["summary_path"] == summary_path
    assert cycles[0]["successes"] == 1
    assert cycles[0]["failures"] == 0
    assert cycles[0]["success_rate"] == 1.0
    assert cycles[0]["federation_conflicts"] == []
    assert cycles[0]["backlog_attempts"][0]["status"] == "done"
    assert "result=merged" in cycles[0]["notes"]
    assert any(event for event in logger.events if event[0] == "lumos_dashboard_refresh")

    # Dashboard snapshot should expose reflection paths for downstream inspection.
    assert cycles[0]["reflections"] == summary["reflections"]
