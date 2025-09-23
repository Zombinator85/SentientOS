"""Unit tests for the ArchitectDaemon meta-orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import architect_daemon


class _Result(SimpleNamespace):
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


def _fixed_clock() -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc)


def test_monitor_anomaly_generates_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request_dir = tmp_path / "requests"
    session_file = tmp_path / "session.json"
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []

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

    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "ETHICS")

    daemon = architect_daemon.ArchitectDaemon(
        request_dir=request_dir,
        session_file=session_file,
        ledger_path=ledger_path,
        config_path=config_path,
        completion_path=completion_path,
        ledger_sink=ledger_events.append,
        pulse_publisher=lambda event: (published.append(event) or event),
        clock=_fixed_clock,
        ci_commands=[["echo", "ok"]],
        immutability_command=["echo", "audit"],
    )

    event = {
        "timestamp": "2025-01-01T00:00:00Z",
        "source_daemon": "MonitoringDaemon",
        "event_type": "monitor_alert",
        "priority": "critical",
        "payload": {"detail": "cpu spike"},
    }
    daemon.handle_pulse(event)

    files = sorted(request_dir.glob("architect_*.txt"))
    assert len(files) == 1
    prompt_text = files[0].read_text(encoding="utf-8")
    assert "Ethics Context" in prompt_text
    assert "Covenant Safety Envelope" in prompt_text
    assert "monitor_alert" in prompt_text
    assert "cpu spike" in prompt_text

    metadata_path = files[0].with_suffix(".json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["mode"] == "repair"
    assert metadata["reason"] == "monitor_alert"
    assert metadata["details"]["trigger"] == "monitor_alert"


def test_codex_success_records_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    commands: list[list[str]] = []

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

    def fake_run(cmd: list[str], capture_output: bool = False, text: bool = False, **_: object) -> _Result:
        commands.append(list(cmd))
        return _Result(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(architect_daemon.subprocess, "run", fake_run)
    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")

    daemon = architect_daemon.ArchitectDaemon(
        request_dir=tmp_path / "requests",
        session_file=tmp_path / "session.json",
        ledger_path=tmp_path / "ledger.jsonl",
        config_path=config_path,
        completion_path=completion_path,
        ledger_sink=ledger_events.append,
        pulse_publisher=lambda event: (published.append(event) or event),
        clock=_fixed_clock,
        ci_commands=[["true"]],
        immutability_command=["true"],
    )

    request = daemon.request_expand("Add telemetry", [{"source": "test", "event_type": "note"}])
    request_id = request.codex_prefix + "abc123"

    ledger_entry = {
        "event": "self_expand",
        "request_id": request_id,
        "files_changed": ["module.py"],
    }
    daemon.handle_ledger_entry(ledger_entry)

    success_events = [entry for entry in ledger_events if entry["event"] == "architect_success"]
    assert success_events and success_events[0]["merge_status"] == "merged"
    merge_events = [entry for entry in ledger_events if entry["event"] == "architect_merge"]
    assert merge_events, "merge event missing"

    session_data = json.loads(daemon.session_file.read_text(encoding="utf-8"))
    assert session_data["successes"] == 1

    git_commands = [cmd for cmd in commands if cmd and cmd[0] == "git"]
    assert any(cmd[:2] == ["git", "checkout"] for cmd in git_commands)
    assert any(cmd[:2] == ["git", "merge"] for cmd in git_commands)


def test_failed_attempts_retries_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_events: list[dict[str, object]] = []
    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")

    config_path = tmp_path / "vow" / "config.yaml"
    completion_path = tmp_path / "vow" / "first_boot_complete"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            [
                "codex_mode: expand",
                "codex_interval: 3600",
                "codex_max_iterations: 2",
                "architect_autonomy: true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    completion_path.parent.mkdir(parents=True, exist_ok=True)
    completion_path.write_text("completed\n", encoding="utf-8")

    daemon = architect_daemon.ArchitectDaemon(
        request_dir=tmp_path / "requests",
        session_file=tmp_path / "session.json",
        ledger_path=tmp_path / "ledger.jsonl",
        config_path=config_path,
        completion_path=completion_path,
        ledger_sink=ledger_events.append,
        pulse_publisher=lambda event: event,
        clock=_fixed_clock,
        max_iterations=2,
        ci_commands=[["true"]],
        immutability_command=["true"],
    )

    request = daemon.request_expand("Add feature", None)
    first_prefix = request.codex_prefix

    failure_entry = {
        "event": "self_expand_rejected",
        "request_id": first_prefix + "000",
        "reason": "ci_failed",
    }
    daemon.handle_ledger_entry(failure_entry)

    retry_events = [entry for entry in ledger_events if entry["event"] == "architect_retry"]
    assert retry_events and retry_events[0]["next_iteration"] == 1

    prompt_files = sorted((tmp_path / "requests").glob("architect_*.txt"))
    assert len(prompt_files) >= 2

    second_prefix = request.codex_prefix
    assert second_prefix != first_prefix

    failure_entry2 = {
        "event": "self_expand_rejected",
        "request_id": second_prefix + "111",
        "reason": "ci_failed",
    }
    daemon.handle_ledger_entry(failure_entry2)

    failure_events = [entry for entry in ledger_events if entry["event"] == "architect_failure"]
    assert failure_events
    assert request.status == "failed"


def test_veil_pending_publishes_pulse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_events: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")

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

    daemon = architect_daemon.ArchitectDaemon(
        request_dir=tmp_path / "requests",
        session_file=tmp_path / "session.json",
        ledger_path=tmp_path / "ledger.jsonl",
        config_path=config_path,
        completion_path=completion_path,
        ledger_sink=ledger_events.append,
        pulse_publisher=lambda event: (published.append(event) or event),
        clock=_fixed_clock,
        ci_commands=[["true"]],
        immutability_command=["true"],
    )

    request = daemon.request_expand("Add feature", None)
    patch_entry = {
        "event": "veil_pending",
        "patch_id": request.codex_prefix + "xyz",
        "files_changed": ["a.py"],
    }
    daemon.handle_ledger_entry(patch_entry)

    veil_events = [event for event in published if event["event_type"] == "veil_request"]
    assert veil_events
    payload = veil_events[0]["payload"]
    assert payload["architect_id"] == request.architect_id
    assert payload["request_id"].startswith(request.codex_prefix)

    ledger_veil = [entry for entry in ledger_events if entry["event"] == "architect_veil_pending"]
    assert ledger_veil


def test_branch_merge_failure_logged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_events: list[dict[str, object]] = []
    commands: list[list[str]] = []

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

    def fake_run(cmd: list[str], capture_output: bool = False, text: bool = False, **_: object) -> _Result:
        commands.append(list(cmd))
        if cmd and cmd[0] == "pytest":
            return _Result(returncode=1, stdout="fail", stderr="boom")
        return _Result(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(architect_daemon.subprocess, "run", fake_run)
    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")

    daemon = architect_daemon.ArchitectDaemon(
        request_dir=tmp_path / "requests",
        session_file=tmp_path / "session.json",
        ledger_path=tmp_path / "ledger.jsonl",
        config_path=config_path,
        completion_path=completion_path,
        ledger_sink=ledger_events.append,
        pulse_publisher=lambda event: event,
        clock=_fixed_clock,
        ci_commands=[["pytest"]],
        immutability_command=["true"],
    )

    request = daemon.request_expand("Add feature", None)
    ledger_entry = {
        "event": "self_expand",
        "request_id": request.codex_prefix + "ok",
        "files_changed": ["a.py"],
    }
    daemon.handle_ledger_entry(ledger_entry)

    ci_fail = [entry for entry in ledger_events if entry["event"] == "architect_ci_failed"]
    assert ci_fail
    success = [entry for entry in ledger_events if entry["event"] == "architect_success"]
    assert success and success[0]["merge_status"] == "blocked"

    git_commands = [cmd for cmd in commands if cmd and cmd[0] == "git"]
    assert any(cmd[:2] == ["git", "checkout"] for cmd in git_commands)
