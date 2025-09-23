import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

import pytest

import architect_daemon


class _StubResult(SimpleNamespace):
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


def _setup_daemon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    max_iterations: int = 2,
):
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
        "codex_max_iterations": max_iterations,
        "architect_autonomy": True,
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
        max_iterations=max_iterations,
        ledger_sink=ledger_events.append,
        pulse_publisher=lambda event: (pulses.append(event) or event),
        clock=fixed_clock,
        ci_commands=[["true"]],
        immutability_command=["true"],
    )
    daemon.start()
    return daemon, ledger_events, pulses, priority_path


def _run_reflection(
    daemon: architect_daemon.ArchitectDaemon,
    payload: Mapping[str, object],
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


def test_reflection_priorities_parsed_and_backlog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    daemon, ledger_events, pulses, priority_path = _setup_daemon(tmp_path, monkeypatch)

    reflection_payload = {
        "summary": "All systems steady",
        "successes": ["Stability checks"],
        "failures": [],
        "regressions": [],
        "next_priorities": ["Improve monitoring", "Draft data contract"],
    }
    _run_reflection(daemon, reflection_payload)

    backlog = json.loads(priority_path.read_text(encoding="utf-8"))
    assert backlog["active"], "backlog entries stored"
    texts = {item["text"] for item in backlog["active"]}
    assert texts == set(reflection_payload["next_priorities"])
    assert all(item["status"] == "pending" for item in backlog["active"])
    assert backlog["history"] == []

    parsed_pulses = [
        event for event in pulses if event.get("event_type") == "architect_priorities_parsed"
    ]
    assert parsed_pulses and parsed_pulses[0]["payload"]["count"] == 2
    ledger_parsed = [
        event for event in ledger_events if event.get("event") == "architect_priorities_parsed"
    ]
    assert ledger_parsed and ledger_parsed[0]["count"] == 2
    assert len(ledger_parsed[0]["priority_ids"]) == 2


def test_backlog_selection_and_completion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    daemon, ledger_events, pulses, priority_path = _setup_daemon(tmp_path, monkeypatch)

    reflection_payload = {
        "summary": "Focus backlog",
        "successes": [],
        "failures": [],
        "regressions": [],
        "next_priorities": ["Ship guardian module"],
    }
    _run_reflection(daemon, reflection_payload)

    pulses.clear()
    ledger_events.clear()

    request = daemon._begin_cycle(trigger="scheduled", timestamp=daemon._now())
    assert request is not None and request.mode == "expand"
    priority_id = request.details.get("priority_id")
    assert isinstance(priority_id, str) and priority_id
    assert "Backlog priority" in request.reason

    backlog = json.loads(priority_path.read_text(encoding="utf-8"))
    entry = next(item for item in backlog["active"] if item["id"] == priority_id)
    assert entry["status"] == "in_progress"

    selected_events = [
        event for event in pulses if event.get("event_type") == "architect_priority_selected"
    ]
    assert selected_events and selected_events[0]["payload"]["priority_id"] == priority_id

    pulses.clear()
    ledger_events.clear()

    success_entry = {
        "event": "self_expand",
        "request_id": request.codex_prefix + "ok",
        "files_changed": ["module.py"],
    }
    daemon.handle_ledger_entry(success_entry)

    backlog = json.loads(priority_path.read_text(encoding="utf-8"))
    entry = next(item for item in backlog["active"] if item["id"] == priority_id)
    assert entry["status"] == "done"
    history_entry = next(item for item in backlog["history"] if item["id"] == priority_id)
    assert history_entry["status"] == "done"
    assert history_entry.get("completed_at"), "completion timestamp recorded"

    done_events = [
        event for event in pulses if event.get("event_type") == "architect_priority_done"
    ]
    assert done_events and done_events[0]["payload"]["priority_id"] == priority_id
    ledger_done = [
        event for event in ledger_events if event.get("event") == "architect_priority_done"
    ]
    assert ledger_done and ledger_done[0]["priority_id"] == priority_id


def test_priority_discarded_after_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    daemon, ledger_events, pulses, priority_path = _setup_daemon(tmp_path, monkeypatch, max_iterations=1)

    reflection_payload = {
        "summary": "Investigate issues",
        "successes": [],
        "failures": [],
        "regressions": [],
        "next_priorities": ["Stabilize tests"],
    }
    _run_reflection(daemon, reflection_payload)

    pulses.clear()
    ledger_events.clear()

    request = daemon._begin_cycle(trigger="scheduled", timestamp=daemon._now())
    assert request is not None
    priority_id = request.details.get("priority_id")
    assert isinstance(priority_id, str) and priority_id

    failure_entry = {
        "event": "self_expand_rejected",
        "request_id": request.codex_prefix + "fail",
        "reason": "ci_failed",
    }
    daemon.handle_ledger_entry(failure_entry)

    backlog = json.loads(priority_path.read_text(encoding="utf-8"))
    entry = next(item for item in backlog["active"] if item["id"] == priority_id)
    assert entry["status"] == "discarded"
    history_entry = next(item for item in backlog["history"] if item["id"] == priority_id)
    assert history_entry["status"] == "discarded"

    discarded_events = [
        event for event in pulses if event.get("event_type") == "architect_priority_discarded"
    ]
    assert discarded_events and discarded_events[0]["payload"]["priority_id"] == priority_id
    ledger_discarded = [
        event
        for event in ledger_events
        if event.get("event") == "architect_priority_discarded"
    ]
    assert ledger_discarded and ledger_discarded[0]["priority_id"] == priority_id
