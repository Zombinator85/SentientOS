from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

from scripts import run_recovery_task
from sentientos.recovery_tasks import append_task_record


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def test_whitelisted_command_runs_and_records_done(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    append_task_record(
        tmp_path,
        {
            "kind": "audit_chain_repair",
            "status": "open",
            "suggested_command": "python -m sentientos.integrity_snapshot",
        },
    )

    monkeypatch.setattr(
        run_recovery_task.subprocess,  # type: ignore[attr-defined]
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr="", stdout="ok"),
    )
    assert run_recovery_task.main([]) == 0

    rows = _read_jsonl(tmp_path / "pulse/recovery_tasks.jsonl")
    assert any(str(row.get("status")) == "done" and str(row.get("kind")) == "audit_chain_repair" for row in rows)


def test_non_whitelisted_command_refused_deterministically(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    append_task_record(
        tmp_path,
        {
            "kind": "evil",
            "status": "open",
            "suggested_command": "python -c print('pwnd')",
        },
    )

    assert run_recovery_task.main([]) == 1
    rows = _read_jsonl(tmp_path / "pulse/recovery_tasks.jsonl")
    done = [row for row in rows if str(row.get("status")) == "done"]
    assert done
    assert done[-1].get("result") == "failed"
