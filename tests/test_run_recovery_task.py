from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_recovery_task

pytestmark = pytest.mark.no_legacy_skip


def test_recovery_task_records_completed_steps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    records: list[dict[str, object]] = []
    monkeypatch.setattr(run_recovery_task.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(
        run_recovery_task,
        "list_tasks",
        lambda _root: [{"kind": "verify", "status": "open", "suggested_command": "python -m pytest"}],
    )
    monkeypatch.setattr(run_recovery_task, "append_task_record", lambda _root, row: records.append(row))
    monkeypatch.setattr(run_recovery_task, "_run_allowed", lambda _command, *, root: (True, 0, "ok"))

    assert run_recovery_task.main([]) == 0
    assert records[0]["result"] == "ok"
    assert records[0]["run_steps"] == [
        {"command": "python -m pytest", "allowed": True, "exit_code": 0, "status": "ok", "stderr": "ok"}
    ]
    reports = list((tmp_path / "glow/forge/recovery_runs").glob("recovery_*.json"))
    assert len(reports) == 1
    assert json.loads(reports[0].read_text(encoding="utf-8"))["result"]["status"] == "done"
