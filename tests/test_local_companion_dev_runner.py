from __future__ import annotations

import io
import queue

from scripts.run_local_companion_dev import (
    _TemporaryCompanionEdge,
    _kill_windows_process_tree,
    _parse_edge_ready,
    _stage_windows_edge_source,
)
from scripts.terminate_owned_process_tree import (
    terminate_owned_process_tree,
)


def test_forward_lines_surfaces_worker_output_after_ready(tmp_path, capsys) -> None:
    lines: queue.Queue[str] = queue.Queue()
    report_file = tmp_path / "renderer-reports.jsonl"

    _TemporaryCompanionEdge._forward_lines(
        io.StringIO("READY 12345\nRuntimeError: worker stopped\n"),
        lines,
        report_file,
    )

    assert lines.get_nowait() == "READY 12345"
    assert lines.get_nowait() == "RuntimeError: worker stopped"
    assert capsys.readouterr().out == (
        "WINDOWS_EDGE RuntimeError: worker stopped\n"
    )


def test_terminate_owned_process_tree_stops_windows_descendants(
    tmp_path, monkeypatch
) -> None:
    class Process:
        pid = 1234
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            self.returncode = 0
            return self.returncode

        def kill(self):
            self.returncode = -9

    process = Process()
    taskkill = tmp_path / "taskkill.exe"
    taskkill.touch()
    calls = []

    def stop_tree(args, **kwargs):
        calls.append((args, kwargs))
        process.returncode = 0

    monkeypatch.setattr(
        "scripts.terminate_owned_process_tree.subprocess.run", stop_tree
    )

    terminate_owned_process_tree(process, taskkill_executable=taskkill)

    assert process.returncode == 0
    assert calls[0][0] == [str(taskkill), "/T", "/F", "/PID", "1234"]
    assert calls[0][1]["timeout"] == 8


def test_parse_edge_ready_includes_exact_godot_pid() -> None:
    assert _parse_edge_ready("READY 12345 67890") == (12345, 67890)


def test_parse_edge_ready_rejects_missing_or_invalid_godot_pid() -> None:
    import pytest

    with pytest.raises(RuntimeError, match="ready_missing_godot_pid"):
        _parse_edge_ready("READY 12345")
    with pytest.raises(RuntimeError, match="invalid_ready_values"):
        _parse_edge_ready("READY 12345 0")


def test_kill_windows_process_tree_targets_only_reported_godot_pid(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "scripts.run_local_companion_dev.shutil.which",
        lambda name: "/mnt/c/Windows/System32/taskkill.exe",
    )
    monkeypatch.setattr(
        "scripts.run_local_companion_dev.subprocess.run",
        lambda args, **kwargs: calls.append((args, kwargs)),
    )

    _kill_windows_process_tree(67890)

    assert calls[0][0] == [
        "/mnt/c/Windows/System32/taskkill.exe", "/T", "/F", "/PID", "67890"
    ]
    assert calls[0][1]["timeout"] == 8


def test_stage_windows_edge_source_uses_only_reviewed_python_source(tmp_path) -> None:
    import zipfile

    repo = tmp_path / "repo"
    (repo / "sentientos").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "sentientos" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "sentientos" / "chat.py").write_text("reviewed module", encoding="utf-8")
    (repo / "avatar_state.py").write_text("reviewed root module", encoding="utf-8")
    (repo / "scripts" / "local_companion_edge_dev_worker.py").write_text(
        "worker source", encoding="utf-8")
    (repo / "scripts" / "terminate_owned_process_tree.py").write_text(
        "cleanup source", encoding="utf-8")
    (repo / "unreviewed.env").write_text("must not be staged", encoding="utf-8")
    (repo / "sentientos" / "private.json").write_text(
        "non-source data must not be staged", encoding="utf-8")

    archive = _stage_windows_edge_source(repo, tmp_path / "temporary-edge")

    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert "sentientos/__init__.py" in names
        assert bundle.read("sentientos/chat.py").decode() == "reviewed module"
        assert bundle.read("avatar_state.py").decode() == "reviewed root module"
        assert bundle.read("terminate_owned_process_tree.py").decode() == "cleanup source"
        assert "unreviewed.env" not in names
        assert "sentientos/private.json" not in names
