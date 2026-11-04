from __future__ import annotations

import io
import queue

from scripts.run_local_companion_dev import _TemporaryCompanionEdge
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
