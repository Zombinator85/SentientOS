from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

from scripts import run_recovery_task, run_remediation_pack
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


def test_run_remediation_pack_executes_steps_in_order(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    (tmp_path / "glow/forge/remediation/packs").mkdir(parents=True, exist_ok=True)
    pack_path = tmp_path / "glow/forge/remediation/packs/pack_test.json"
    pack_path.write_text(
        json.dumps(
            {
                "pack_id": "pack_test",
                "steps": [
                    {"name": "verify", "command": "python scripts/verify_receipt_chain.py --last 50"},
                    {"name": "snapshot", "command": "python -m sentientos.integrity_snapshot"},
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    calls: list[tuple[object, ...]] = []

    def _fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(tuple(args[0]))
        return SimpleNamespace(returncode=0, stderr="", stdout="ok")

    monkeypatch.setattr(run_recovery_task.subprocess, "run", _fake_run)  # type: ignore[attr-defined]
    assert run_remediation_pack.main([str(pack_path.relative_to(tmp_path))]) == 0
    assert len(calls) == 2
    runs = sorted((tmp_path / "glow/forge/remediation/runs").glob("run_*.json"))
    assert runs
