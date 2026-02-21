from __future__ import annotations

from pathlib import Path

from sentientos.recovery_tasks import backlog_count, enqueue_audit_chain_repair_task, enqueue_mode_escalation_tasks, list_tasks, mark_done
from scripts import recovery_tasks


def test_enqueue_on_recovery_and_mark_done(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    created = enqueue_mode_escalation_tasks(tmp_path, mode="recovery", reason="pressure")
    assert created
    assert backlog_count(tmp_path) >= 1

    first_kind = str(created[0]["kind"])
    done = mark_done(tmp_path, kind=first_kind, note="handled")
    assert done["status"] == "done"

    rows = list_tasks(tmp_path)
    assert any(str(row.get("status")) == "done" for row in rows)

    monkeypatch.chdir(tmp_path)
    assert recovery_tasks.main(["done", first_kind, "--note", "cli"]) == 0
    assert recovery_tasks.main(["list"]) == 0


def test_audit_mismatch_recovery_mode_enqueues_repair_task(tmp_path: Path) -> None:
    enqueue_mode_escalation_tasks(tmp_path, mode="recovery", reason="pressure")
    row = enqueue_audit_chain_repair_task(tmp_path, reason="audit_chain_mismatch_detected")
    assert row is not None
    rows = list_tasks(tmp_path)
    assert any(str(item.get("kind")) == "audit_chain_repair" and str(item.get("status")) == "open" for item in rows)
