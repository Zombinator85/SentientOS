from __future__ import annotations

import io
import queue

from scripts.run_local_companion_dev import _TemporaryCompanionEdge


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
