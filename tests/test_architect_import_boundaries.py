from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

import architect_daemon

pytestmark = pytest.mark.no_legacy_skip


class _Denied(BaseException):
    pass


def _daemon(tmp_path: Path) -> architect_daemon.ArchitectDaemon:
    return architect_daemon.ArchitectDaemon(
        request_dir=tmp_path / "requests",
        session_file=tmp_path / "state" / "session.json",
        ledger_path=tmp_path / "state" / "ledger.jsonl",
        config_path=tmp_path / "config.yaml",
        completion_path=tmp_path / "boot-complete",
        reflection_dir=tmp_path / "reflections",
        priority_path=tmp_path / "reflections" / "priorities.json",
        cycle_dir=tmp_path / "cycles",
        trajectory_dir=tmp_path / "trajectories",
    )


def test_architect_import_isolated_and_inert(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/verify_import_inertness.py",
            "--module-root",
            str(Path(__file__).resolve().parents[1]),
            "--module",
            "architect_daemon",
            "--output",
            str(output),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "import_inertness_ready"
    assert result["module_results"][0]["privilege_invoked"] == []
    assert result["module_results"][0]["effects_invoked"] == []


def test_construction_reads_configuration_without_creating_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        architect_daemon, "require_admin_banner", lambda: pytest.fail("construction authorized")
    )
    monkeypatch.setattr(
        architect_daemon, "require_lumos_approval", lambda: pytest.fail("construction approved")
    )
    daemon = _daemon(tmp_path)

    assert daemon.active is False
    assert not (tmp_path / "requests").exists()
    assert not (tmp_path / "state").exists()
    assert not (tmp_path / "reflections").exists()
    assert not (tmp_path / "cycles").exists()
    assert not (tmp_path / "trajectories").exists()


def test_authorization_precedes_filesystem_process_git_ledger_and_pulse_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon = _daemon(tmp_path)
    events: list[str] = []
    monkeypatch.setattr(architect_daemon, "require_admin_banner", lambda: events.append("admin"))
    monkeypatch.setattr(architect_daemon, "require_lumos_approval", lambda: events.append("lumos"))

    original_mkdir = Path.mkdir
    original_write_text = Path.write_text

    def mkdir(path: Path, *args: object, **kwargs: object) -> None:
        events.append("mkdir")
        original_mkdir(path, *args, **kwargs)

    def write_text(path: Path, *args: object, **kwargs: object) -> int:
        events.append("filesystem_write")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    monkeypatch.setattr(Path, "write_text", write_text)
    daemon._save_session()
    assert events[:2] == ["admin", "lumos"]
    assert events.index("admin") < events.index("mkdir") < events.index("filesystem_write")

    events.clear()
    monkeypatch.setattr(
        architect_daemon.subprocess,
        "run",
        lambda *_args, **_kwargs: (events.append("process") or subprocess.CompletedProcess([], 0)),
    )
    daemon._execute_codex_prompt("review")
    assert events == ["admin", "lumos", "process"]

    events.clear()
    daemon._run_git(["status"])
    assert events == ["admin", "lumos", "process"]

    events.clear()
    daemon._run_command(["pytest", "--version"])
    assert events == ["admin", "lumos", "process"]

    events.clear()
    daemon._ledger_sink = lambda _event: events.append("ledger_sink")
    monkeypatch.setattr(
        architect_daemon, "append_json", lambda *_args, **_kwargs: events.append("ledger_write")
    )
    daemon._emit_ledger_event({"event": "test"})
    assert events[:2] == ["admin", "lumos"]
    assert events[2:] == ["ledger_write", "ledger_sink"]

    events.clear()
    daemon._pulse_publisher = lambda _event: (events.append("pulse") or {})
    daemon._publish_pulse({"event_type": "test"})
    assert events == ["admin", "lumos", "pulse"]


def test_activation_authorizes_before_directory_creation_and_subscription(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon = _daemon(tmp_path)
    daemon._priority_backlog_needs_save = False
    events: list[str] = []
    monkeypatch.setattr(architect_daemon, "require_admin_banner", lambda: events.append("admin"))
    monkeypatch.setattr(architect_daemon, "require_lumos_approval", lambda: events.append("lumos"))
    original_mkdir = Path.mkdir

    def mkdir(path: Path, *args: object, **kwargs: object) -> None:
        events.append("mkdir")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    monkeypatch.setattr(
        architect_daemon.pulse_bus,
        "subscribe",
        lambda *_args, **_kwargs: (events.append("subscribe") or type("S", (), {"active": True})()),
    )

    daemon.start()

    assert events[:2] == ["admin", "lumos"]
    assert events.index("admin", 2) < events.index("subscribe")
    assert events.index("lumos", 2) < events.index("subscribe")
    assert events.index("mkdir") < events.index("subscribe")


def test_denial_stops_filesystem_and_process_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon = _daemon(tmp_path)
    effects: list[str] = []
    monkeypatch.setattr(
        architect_daemon, "require_admin_banner", lambda: (_ for _ in ()).throw(_Denied())
    )
    monkeypatch.setattr(
        architect_daemon, "require_lumos_approval", lambda: effects.append("lumos")
    )
    monkeypatch.setattr(Path, "mkdir", lambda *_a, **_k: effects.append("mkdir"))
    monkeypatch.setattr(Path, "write_text", lambda *_a, **_k: effects.append("write"))
    monkeypatch.setattr(
        architect_daemon.subprocess, "run", lambda *_a, **_k: effects.append("process")
    )

    with pytest.raises(_Denied):
        daemon._save_session()
    with pytest.raises(_Denied):
        daemon._run_git(["status"])
    with pytest.raises(_Denied):
        daemon._run_command(["pytest", "--version"])
    assert effects == []
