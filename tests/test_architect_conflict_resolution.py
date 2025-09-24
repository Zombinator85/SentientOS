from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Iterable, Mapping

import json
import pytest

import architect_daemon


class _StubProcess(SimpleNamespace):
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


def _setup_daemon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    subprocess_stub: Callable[..., _StubProcess] | None = None,
) -> tuple[architect_daemon.ArchitectDaemon, list[dict[str, object]], list[dict[str, object]]]:
    pulses: list[dict[str, object]] = []
    ledger_events: list[dict[str, object]] = []

    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")

    def default_run(
        cmd: Iterable[str] | tuple[str, ...],
        capture_output: bool = False,
        text: bool = False,
        **_: object,
    ) -> _StubProcess:
        return _StubProcess(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        architect_daemon.subprocess,
        "run",
        subprocess_stub if subprocess_stub is not None else default_run,
    )

    request_dir = tmp_path / "requests"
    session_file = tmp_path / "session.json"
    ledger_path = tmp_path / "ledger.jsonl"
    config_path = tmp_path / "config.json"
    reflection_dir = tmp_path / "reflections"
    reflection_dir.mkdir(parents=True, exist_ok=True)
    priority_path = reflection_dir / "priorities.json"

    config_payload = {
        "codex_mode": "expand",
        "codex_interval": 3600,
        "codex_max_iterations": 2,
        "architect_autonomy": True,
        "federate_priorities": True,
        "federation_peer_name": "alpha",
    }
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")

    completion_path = tmp_path / "vow" / "first_boot_complete"
    completion_path.parent.mkdir(parents=True, exist_ok=True)
    completion_path.write_text("done", encoding="utf-8")

    monkeypatch.setattr(architect_daemon.pulse_bus, "verify", lambda event: True)

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
        ci_commands=[["true"]],
        immutability_command=["true"],
    )
    daemon.start()
    pulses.clear()
    ledger_events.clear()
    return daemon, ledger_events, pulses


def _make_backlog_event(peer: str, text: str, daemon: architect_daemon.ArchitectDaemon) -> dict[str, object]:
    return {
        "timestamp": daemon._now().isoformat(),
        "source_daemon": "ArchitectDaemon",
        "event_type": "architect_backlog_shared",
        "priority": "info",
        "source_peer": peer,
        "payload": {
            "pending": [{"text": text}],
            "diff": {"added": [{"text": text}], "updated": [], "removed": []},
        },
        "signature": "valid",
    }


def test_conflict_detection_fuzzy_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    daemon, ledger_events, pulses = _setup_daemon(tmp_path, monkeypatch)

    daemon.handle_pulse(_make_backlog_event("beta", "Implement offline sync support", daemon))
    daemon.handle_pulse(
        _make_backlog_event("gamma", "Implement offline synchronization support", daemon)
    )

    assert daemon._conflicts, "conflict records created"
    conflict = next(iter(daemon._conflicts.values()))
    assert conflict["status"] == "pending"
    variants = conflict.get("variants", [])
    assert isinstance(variants, list) and len(variants) == 2
    conflict_pulses = [evt for evt in pulses if evt.get("event_type") == "architect_backlog_conflict"]
    assert conflict_pulses, "conflict pulse emitted"
    payload = conflict_pulses[0]["payload"]
    assert payload["variants"] and {item["peer"] for item in payload["variants"]} == {"beta", "gamma"}
    assert ledger_events, "ledger recorded conflict"


def test_codex_merge_prompt_and_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured_prompts: list[str] = []

    def stub_run(cmd: Iterable[str] | tuple[str, ...], capture_output: bool = False, text: bool = False, **_: object) -> _StubProcess:
        assert list(cmd)[:2] == ["codex", "exec"]
        prompt = list(cmd)[2]
        captured_prompts.append(prompt)
        payload = {"merged_priority": "Unified offline sync", "notes": "merge suggestion"}
        return _StubProcess(returncode=0, stdout=json.dumps(payload), stderr="")

    daemon, ledger_events, pulses = _setup_daemon(tmp_path, monkeypatch, subprocess_stub=stub_run)

    daemon.handle_pulse(_make_backlog_event("beta", "Document covenant sync", daemon))
    daemon.handle_pulse(_make_backlog_event("gamma", "Document covenant syncing", daemon))

    assert captured_prompts, "codex prompt generated"
    assert "covenant sync" in captured_prompts[0]
    conflict_id = next(iter(daemon._conflicts))
    conflict = daemon._conflicts[conflict_id]
    codex_state = conflict.get("codex", {})
    suggestion = codex_state.get("suggestion")
    assert isinstance(suggestion, dict)
    assert suggestion["merged_priority"] == "Unified offline sync"
    resolution_dir = daemon._conflict_resolution_dir
    assert any(resolution_dir.iterdir()), "resolution file stored"
    resolved_events = [evt for evt in pulses if evt.get("event_type") == "architect_backlog_resolved"]
    assert resolved_events, "resolved pulse emitted"
    assert any(event.get("event") == "architect_backlog_resolved" for event in ledger_events)


def test_accept_action_creates_backlog_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def stub_run(*_: object, **__: object) -> _StubProcess:
        payload = {"merged_priority": "Unified priority", "notes": "notes"}
        return _StubProcess(returncode=0, stdout=json.dumps(payload), stderr="")

    daemon, ledger_events, pulses = _setup_daemon(tmp_path, monkeypatch, subprocess_stub=stub_run)
    daemon.handle_pulse(_make_backlog_event("beta", "Align metrics dashboard", daemon))
    daemon.handle_pulse(_make_backlog_event("gamma", "Align metrics dashboards", daemon))

    conflict_id = next(iter(daemon._conflicts))
    assert daemon.accept_conflict_merge(conflict_id)
    active_ids = {entry["id"] for entry in daemon._priority_active}
    suggestion = daemon._conflicts[conflict_id]["codex"]["suggestion"]
    assert suggestion["priority_id"] in active_ids
    accepted_pulses = [evt for evt in pulses if evt.get("event_type") == "architect_backlog_merge_accepted"]
    assert accepted_pulses, "merge accepted pulse emitted"
    merged_flags = [entry.get("merged") for entry in daemon._federated_priorities.values()]
    assert any(merged_flags)


def test_dashboard_actions_reject_and_separate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def stub_run(*_: object, **__: object) -> _StubProcess:
        payload = {"merged_priority": "Unify backlog", "notes": "notes"}
        return _StubProcess(returncode=0, stdout=json.dumps(payload), stderr="")

    daemon, ledger_events, pulses = _setup_daemon(tmp_path, monkeypatch, subprocess_stub=stub_run)
    daemon.handle_pulse(_make_backlog_event("beta", "Prepare backlog merge", daemon))
    daemon.handle_pulse(_make_backlog_event("gamma", "Prepare backlog merging", daemon))
    conflict_id = next(iter(daemon._conflicts))

    daemon.handle_pulse(
        {
            "timestamp": daemon._now().isoformat(),
            "source_daemon": "ReflectionDashboard",
            "event_type": "architect_backlog_action",
            "priority": "info",
            "payload": {"action": "reject", "conflict_id": conflict_id},
        }
    )
    assert daemon._conflicts[conflict_id]["status"] == "rejected"

    daemon.handle_pulse(
        {
            "timestamp": daemon._now().isoformat(),
            "source_daemon": "ReflectionDashboard",
            "event_type": "architect_backlog_action",
            "priority": "info",
            "payload": {"action": "separate", "conflict_id": conflict_id},
        }
    )
    assert daemon._conflicts[conflict_id]["status"] == "separate"
    separate_pulses = [evt for evt in pulses if evt.get("event_type") == "architect_backlog_merge_separated"]
    assert separate_pulses


def test_codex_invalid_output_logs_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def stub_run(*_: object, **__: object) -> _StubProcess:
        return _StubProcess(returncode=0, stdout="not-json", stderr="")

    daemon, ledger_events, pulses = _setup_daemon(tmp_path, monkeypatch, subprocess_stub=stub_run)
    daemon.handle_pulse(_make_backlog_event("beta", "Audit backlog review", daemon))
    daemon.handle_pulse(_make_backlog_event("gamma", "Audit backlog reviews", daemon))

    conflict_id = next(iter(daemon._conflicts))
    codex_state = daemon._conflicts[conflict_id].get("codex", {})
    assert codex_state.get("status") == "failed"
    failure_pulses = [evt for evt in pulses if evt.get("event_type") == "architect_backlog_resolution_failed"]
    assert failure_pulses
    failure_ledger = [evt for evt in ledger_events if evt.get("event") == "architect_backlog_resolution_failed"]
    assert failure_ledger
