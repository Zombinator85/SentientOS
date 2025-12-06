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
    success_rate_threshold: float = 0.7,
    failure_streak_threshold: int = 3,
    conflict_rate_threshold: float = 0.3,
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

    priority_path = tmp_path / "priorities.json"
    monkeypatch.setattr(architect_daemon, "ARCHITECT_CYCLE_DIR", cycle_dir)
    monkeypatch.setattr(architect_daemon, "ARCHITECT_TRAJECTORY_DIR", trajectory_dir)
    monkeypatch.setattr(architect_daemon, "ARCHITECT_SESSION_FILE", session_file)
    monkeypatch.setattr(architect_daemon, "ARCHITECT_PRIORITY_BACKLOG_PATH", priority_path)
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
        success_rate_threshold=success_rate_threshold,
        failure_streak_threshold=failure_streak_threshold,
        conflict_rate_threshold=conflict_rate_threshold,
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


def test_success_and_failure_adjustments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    fake_clock = _FakeClock()
    daemon, _, _, _ = _build_daemon(
        tmp_path,
        monkeypatch,
        fake_clock,
        ledger_events,
        published,
        trajectory_interval=2,
        success_rate_threshold=0.8,
        failure_streak_threshold=2,
    )

    first = _start_backlog_cycle(
        daemon, fake_clock, priority_id="prio-success", text="alpha"
    )
    daemon._record_cycle_backlog_outcome("prio-success", status="done", reason=None)
    _finalize_cycle(daemon, first, fake_clock, status="merged")

    second = _start_backlog_cycle(
        daemon, fake_clock, priority_id="prio-fail", text="beta"
    )
    daemon._record_cycle_backlog_outcome(
        "prio-fail", status="discarded", reason="failure"
    )
    daemon._failure_streak = 3
    _finalize_cycle(daemon, second, fake_clock, status="blocked")

    assert daemon._steering_overrides["reflection_interval"] == max(
        1, daemon._default_reflection_interval // 2
    )
    assert daemon._steering_overrides["cooldown_period"] > daemon._default_cooldown_period
    reason = daemon._trajectory_adjustment_reason
    assert "Success rate" in reason
    assert "Failure streak" in reason
    ledger_events_names = [entry["event"] for entry in ledger_events]
    assert "architect_trajectory_adjusted" in ledger_events_names
    pulse_events = [event["event_type"] for event in published]
    assert "architect_trajectory_adjusted" in pulse_events


def test_conflict_rate_escalation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    fake_clock = _FakeClock()
    daemon, cycle_dir, _, _ = _build_daemon(
        tmp_path,
        monkeypatch,
        fake_clock,
        ledger_events,
        published,
        trajectory_interval=2,
        success_rate_threshold=0.2,
        conflict_rate_threshold=0.2,
    )
    daemon._autonomy_enabled = True

    for idx in range(2):
        fake_clock.advance(60)
        ended_at = fake_clock().isoformat()
        summary = {
            "cycle_id": f"manual-{idx}",
            "started_at": ended_at,
            "ended_at": ended_at,
            "reflections": [],
            "backlog_attempts": [
                {"id": f"p-{idx}", "text": "alpha", "status": "done"}
            ],
            "federation_conflicts": [
                {
                    "id": f"conf-{idx}",
                    "status": "pending",
                    "peers": ["peer-a", "peer-b"],
                    "resolution_path": "",
                }
            ],
            "cooldown": False,
            "anomalies": [],
            "notes": "",
        }
        timestamp = daemon._timestamp_for_cycle_filename(ended_at)
        path = cycle_dir / f"cycle_{timestamp}.json"
        path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    daemon._conflicts = {
        "conflict-a": {"status": "pending", "variants": [{"peer": "a"}, {"peer": "b"}]},
    }
    calls: list[str] = []
    monkeypatch.setattr(
        daemon,
        "_process_conflict_resolution",
        lambda conflict_id: calls.append(conflict_id),
    )

    report = daemon._build_trajectory_report(interval=2)
    report_path = daemon._persist_trajectory_report(report)
    daemon._handle_trajectory_success(report, report_path)

    assert daemon._steering_overrides.get("conflict_priority") is True
    assert "Conflict rate" in daemon._trajectory_adjustment_reason
    assert calls, "conflict resolution escalation should trigger"
    assert daemon._conflict_priority_escalated is True


def test_priority_reorder_marks_low_confidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    fake_clock = _FakeClock()
    daemon, _, _, _ = _build_daemon(
        tmp_path,
        monkeypatch,
        fake_clock,
        ledger_events,
        published,
        trajectory_interval=2,
    )
    daemon._priority_active = [
        {"id": "a", "text": "alpha", "status": "pending"},
        {"id": "b", "text": "Network latency", "status": "pending"},
        {"id": "c", "text": "gamma", "status": "pending"},
    ]
    daemon._priority_index = {entry["id"]: entry for entry in daemon._priority_active}

    canonical = architect_daemon._canonicalize_priority_text("Network latency")
    report = {
        "success_rate": 1.0,
        "failure_rate": 0.0,
        "conflict_rate": 0.0,
        "current_failure_streak": 0,
        "priority_failures": [
            {"canonical": canonical, "label": "Network", "count": 3},
        ],
        "priority_status": {canonical: "discarded"},
    }

    daemon._apply_trajectory_adjustments(report)

    assert daemon._priority_active[-1]["id"] == "b"
    assert daemon._priority_active[-1].get("confidence") == "low"
    ledger_events_names = [entry["event"] for entry in ledger_events]
    assert "architect_priority_reordered" in ledger_events_names


def test_dashboard_reflects_adjustments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    fake_clock = _FakeClock()
    daemon, _, _, ledger_path = _build_daemon(
        tmp_path,
        monkeypatch,
        fake_clock,
        ledger_events,
        published,
        trajectory_interval=4,
        success_rate_threshold=0.9,
    )

    request = _start_backlog_cycle(daemon, fake_clock, priority_id="p1", text="alpha")
    daemon._record_cycle_backlog_outcome("p1", status="done", reason=None)
    _finalize_cycle(daemon, request, fake_clock, status="merged")

    for index in range(3):
        priority_id = f"p{index + 2}"
        request2 = _start_backlog_cycle(
            daemon, fake_clock, priority_id=priority_id, text="network"
        )
        daemon._record_cycle_backlog_outcome(
            priority_id, status="discarded", reason="merge_failed"
        )
        daemon._failure_streak = 4
        _finalize_cycle(daemon, request2, fake_clock, status="blocked")
    logger = _DummyLogger()
    dashboard = SystemDashboard(
        logger,
        ledger_path=ledger_path,
        file_explorer=SimpleNamespace(),
        config=_DummyConfig(),
        codex_console=SimpleNamespace(),
    )
    snapshot = dashboard.refresh()
    steering = snapshot["trajectories"].get("steering", {})
    assert "Success rate" in steering.get("reason", "")
    backlog = snapshot["trajectories"].get("backlog", {})
    active_entries = backlog.get("active", []) if isinstance(backlog, Mapping) else []
    assert any(entry.get("confidence") == "low" for entry in active_entries)
    architect_panel = snapshot["architect"]
    assert architect_panel.get("trajectory_adjustment", {}).get(
        "reason"
    ) == daemon._trajectory_adjustment_reason


def test_reset_clears_adjustments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    fake_clock = _FakeClock()
    daemon, _, _, _ = _build_daemon(
        tmp_path,
        monkeypatch,
        fake_clock,
        ledger_events,
        published,
        trajectory_interval=2,
        success_rate_threshold=0.8,
    )

    request = _start_backlog_cycle(daemon, fake_clock, priority_id="p1", text="alpha")
    daemon._record_cycle_backlog_outcome("p1", status="done", reason=None)
    _finalize_cycle(daemon, request, fake_clock, status="merged")

    request2 = _start_backlog_cycle(daemon, fake_clock, priority_id="p2", text="network")
    daemon._record_cycle_backlog_outcome("p2", status="discarded", reason="merge_failed")
    daemon._failure_streak = 4
    _finalize_cycle(daemon, request2, fake_clock, status="blocked")

    daemon.reset_trajectory_adjustments(actor="tester")

    assert daemon._steering_overrides["reflection_interval"] is None
    assert daemon._steering_overrides["cooldown_period"] is None
    assert daemon._steering_overrides["conflict_priority"] is False
    assert daemon._trajectory_adjustment_reason == ""
    assert not daemon._low_confidence_priorities
    assert all("confidence" not in entry for entry in daemon._priority_active)
    ledger_events_names = [entry["event"] for entry in ledger_events]
    assert "architect_adjustments_reset" in ledger_events_names
    pulse_events = [event["event_type"] for event in published]
    assert "architect_adjustments_reset" in pulse_events
