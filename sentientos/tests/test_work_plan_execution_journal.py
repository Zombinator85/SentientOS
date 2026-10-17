from __future__ import annotations

import json
import hashlib
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import os
from pathlib import Path
import stat
import threading
from typing import Any

import pytest

from sentientos.work_plan import Task, TaskRun, WorkPlan
from sentientos.work_plan_execution_journal import (
    MAX_JOURNAL_BYTES, WorkPlanExecutionJournal, WorkPlanJournalError,
)


def _plan() -> WorkPlan:
    return WorkPlan(1, "journal-plan", "2026-01-01T00:00:00Z", "manual", ("g1",), (
        Task(1, "g1:propose", "g1", "forge_propose", (), None, 0, 0, {}, (), False),))


def _two_task_plan() -> WorkPlan:
    return WorkPlan(1, "journal-crash-plan", "2026-01-01T00:00:00Z", "manual", ("g1",), (
        Task(1, "g1:one", "g1", "forge_propose", (), None, 0, 0, {}, (), False),
        Task(1, "g1:two", "g1", "forge_propose", (), None, 0, 0, {}, (), False),))


def _start_journal_after_process_barrier(
        root: str, task_id: str, ready: Any, release: Any, outcomes: Any) -> None:
    plan = WorkPlan(1, "cross-process-journal-plan", "2026-01-01T00:00:00Z", "manual",
        ("g1",), (
            Task(1, "g1:one", "g1", "forge_propose", (), None, 0, 0, {}, (), False),
            Task(1, "g1:two", "g1", "forge_propose", (), None, 0, 0, {}, (), False),
        ))
    journal = WorkPlanExecutionJournal(Path(root), plan)
    ready.set()
    if not release.wait(timeout=10):
        outcomes.put("barrier_timeout")
        return
    try:
        journal.start(task_id)
        outcomes.put("written")
    except WorkPlanJournalError as exc:
        outcomes.put(str(exc))


def _crash_during_journal_append(root: str, ready: Any) -> None:
    journal = WorkPlanExecutionJournal(Path(root), _two_task_plan())
    write = os.write

    def write_prefix_then_exit(descriptor: int, data: bytes) -> int:
        written = write(descriptor, data[:max(1, len(data) // 2)])
        ready.set()
        os._exit(73)
        return written

    setattr(os, "write", write_prefix_then_exit)
    journal.start("g1:two")
    os._exit(74)


def test_journal_binds_task_events_to_exact_plan_identity(tmp_path: Path) -> None:
    plan = _plan()
    journal = WorkPlanExecutionJournal(tmp_path, plan)
    journal.start("g1:propose")

    changed = WorkPlan(1, plan.plan_id, plan.created_at, plan.context, plan.selected_goals,
        (Task(1, "g1:other", "g1", "forge_propose", (), None, 0, 0, {}, (), False),))
    changed_journal = WorkPlanExecutionJournal(tmp_path, changed)

    assert changed_journal.path != journal.path
    assert changed_journal.state("g1:other") is None
    assert journal.state("g1:propose") == "interrupted"


def test_corrupted_journal_digest_fails_closed(tmp_path: Path) -> None:
    journal = WorkPlanExecutionJournal(tmp_path, _plan())
    journal.start("g1:propose")
    row = json.loads(journal.path.read_text(encoding="utf-8"))
    row["recorded_at"] = "2026-01-02T00:00:00Z"
    journal.path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(WorkPlanJournalError, match="work_plan_journal_digest_mismatch"):
        WorkPlanExecutionJournal(tmp_path, _plan())


def test_oversized_journal_is_rejected_before_unbounded_read(tmp_path: Path) -> None:
    journal = WorkPlanExecutionJournal(tmp_path, _plan())
    journal.path.parent.mkdir(parents=True, exist_ok=True)
    journal.path.write_bytes(b"x" * (MAX_JOURNAL_BYTES + 1))

    with pytest.raises(WorkPlanJournalError, match="work_plan_journal_bounds_invalid"):
        WorkPlanExecutionJournal(tmp_path, _plan())


def test_append_refuses_journal_that_grew_past_bound(tmp_path: Path) -> None:
    journal = WorkPlanExecutionJournal(tmp_path, _plan())
    journal.path.parent.mkdir(parents=True, exist_ok=True)
    journal.path.write_bytes(b"x" * (MAX_JOURNAL_BYTES + 1))

    with pytest.raises(WorkPlanJournalError, match="work_plan_journal_bounds_invalid"):
        journal.start("g1:propose")
    assert journal.path.stat().st_size == MAX_JOURNAL_BYTES + 1


def test_start_append_syncs_file_before_journal_directory(tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    journal = WorkPlanExecutionJournal(tmp_path, _plan())
    journal.path.parent.mkdir(parents=True, exist_ok=True)
    sync_targets: list[bool] = []
    fsync = os.fsync

    def record_sync_target(descriptor: int) -> None:
        sync_targets.append(stat.S_ISDIR(os.fstat(descriptor).st_mode))
        fsync(descriptor)

    monkeypatch.setattr(os, "fsync", record_sync_target)
    journal.start("g1:propose")

    assert sync_targets == [False, True]


def test_directory_sync_failure_is_not_reported_as_durable_append(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal = WorkPlanExecutionJournal(tmp_path, _plan())
    journal.path.parent.mkdir(parents=True, exist_ok=True)
    fsync = os.fsync

    def fail_directory_sync(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("simulated directory sync failure")
        fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory_sync)
    with pytest.raises(WorkPlanJournalError, match="work_plan_journal_write_failed"):
        journal.start("g1:propose")

    assert journal.state("g1:propose") is None
    interrupted_bytes = journal.path.read_bytes()
    recovered = WorkPlanExecutionJournal(tmp_path, _plan())
    assert recovered.state("g1:propose") == "interrupted"
    assert journal.path.read_bytes() == interrupted_bytes


def test_symlinked_journal_is_rejected_without_reading_target(tmp_path: Path) -> None:
    journal = WorkPlanExecutionJournal(tmp_path, _plan())
    target = tmp_path / "external.jsonl"
    target.write_text("external evidence\n", encoding="utf-8")
    journal.path.parent.mkdir(parents=True, exist_ok=True)
    journal.path.symlink_to(target)

    with pytest.raises(WorkPlanJournalError, match="work_plan_journal_bounds_invalid"):
        WorkPlanExecutionJournal(tmp_path, _plan())


def test_append_refuses_symlinked_journal_without_mutating_target(tmp_path: Path) -> None:
    journal = WorkPlanExecutionJournal(tmp_path, _plan())
    target = tmp_path / "external.jsonl"
    target.write_text("external evidence\n", encoding="utf-8")
    journal.path.parent.mkdir(parents=True, exist_ok=True)
    journal.path.symlink_to(target)

    with pytest.raises(WorkPlanJournalError, match="work_plan_journal_write_failed"):
        journal.start("g1:propose")
    assert target.read_text(encoding="utf-8") == "external evidence\n"


def test_oversized_legacy_journal_is_rejected_before_read(tmp_path: Path) -> None:
    plan = _plan()
    journal = WorkPlanExecutionJournal(tmp_path, plan)
    legacy_name = hashlib.sha256(plan.plan_id.encode("utf-8")).hexdigest() + ".jsonl"
    legacy_path = journal.path.parent / legacy_name
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_bytes(b"{" + b"x" * MAX_JOURNAL_BYTES)

    with pytest.raises(WorkPlanJournalError, match="work_plan_journal_bounds_invalid"):
        WorkPlanExecutionJournal(tmp_path, plan)


def test_concurrent_stale_journal_writer_cannot_fork_hash_chain(tmp_path: Path) -> None:
    plan = WorkPlan(1, "concurrent-journal-plan", "2026-01-01T00:00:00Z", "manual",
        ("g1",), (
            Task(1, "g1:one", "g1", "forge_propose", (), None, 0, 0, {}, (), False),
            Task(1, "g1:two", "g1", "forge_propose", (), None, 0, 0, {}, (), False),
        ))
    first = WorkPlanExecutionJournal(tmp_path, plan)
    second = WorkPlanExecutionJournal(tmp_path, plan)
    barrier = threading.Barrier(2)

    def start(journal: WorkPlanExecutionJournal, task_id: str) -> str:
        barrier.wait()
        try:
            journal.start(task_id)
            return "written"
        except WorkPlanJournalError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(start, first, "g1:one"),
            executor.submit(start, second, "g1:two")]
        outcomes = [future.result(timeout=5) for future in futures]

    assert sorted(outcomes) == ["work_plan_journal_stale_writer", "written"]
    recovered = WorkPlanExecutionJournal(tmp_path, plan)
    assert sum(recovered.state(task_id) == "interrupted"
        for task_id in ("g1:one", "g1:two")) == 1
    assert len(recovered.path.read_text(encoding="utf-8").splitlines()) == 1


def test_concurrent_tasks_on_one_journal_serialize_in_sequence(tmp_path: Path) -> None:
    plan = WorkPlan(1, "concurrent-single-writer-plan", "2026-01-01T00:00:00Z", "manual",
        ("g1",), (
            Task(1, "g1:one", "g1", "forge_propose", (), None, 0, 0, {}, (), False),
            Task(1, "g1:two", "g1", "forge_propose", (), None, 0, 0, {}, (), False),
        ))
    journal = WorkPlanExecutionJournal(tmp_path, plan)
    barrier = threading.Barrier(2)

    def start(task_id: str) -> None:
        barrier.wait()
        journal.start(task_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(start, "g1:one"), executor.submit(start, "g1:two")]
        for future in futures:
            future.result(timeout=5)

    recovered = WorkPlanExecutionJournal(tmp_path, plan)
    assert recovered.state("g1:one") == "interrupted"
    assert recovered.state("g1:two") == "interrupted"
    rows = [json.loads(line) for line in recovered.path.read_text().splitlines()]
    assert [row["sequence"] for row in rows] == [1, 2]


def test_stale_writer_detects_same_size_journal_change(tmp_path: Path) -> None:
    plan = WorkPlan(1, "same-size-stale-journal-plan", "2026-01-01T00:00:00Z", "manual",
        ("g1",), (
            Task(1, "g1:one", "g1", "forge_propose", (), None, 0, 0, {}, (), False),
            Task(1, "g1:two", "g1", "forge_propose", (), None, 0, 0, {}, (), False),
        ))
    journal = WorkPlanExecutionJournal(tmp_path, plan)
    journal.start("g1:one")
    original = journal.path.read_bytes()
    changed = original.replace(b'"task_id":"g1:one"', b'"task_id":"g1:two"', 1)
    assert len(changed) == len(original)
    journal.path.write_bytes(changed)

    with pytest.raises(WorkPlanJournalError, match="work_plan_journal_stale_writer"):
        journal.start("g1:two")
    assert journal.path.read_bytes() == changed


@pytest.mark.skipif(os.name != "posix", reason="journal locking uses POSIX flock")
def test_cross_process_writers_cannot_fork_journal_hash_chain(tmp_path: Path) -> None:
    context = multiprocessing.get_context("fork")
    release = context.Event()
    outcomes = context.Queue()
    ready = [context.Event(), context.Event()]
    processes = [
        context.Process(target=_start_journal_after_process_barrier,
            args=(str(tmp_path), task_id, signal, release, outcomes))
        for task_id, signal in zip(("g1:one", "g1:two"), ready)
    ]
    try:
        for process in processes:
            process.start()
        assert all(signal.wait(timeout=10) for signal in ready)
        release.set()
        results = [outcomes.get(timeout=10) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
    finally:
        release.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)

    assert sorted(results) == ["work_plan_journal_stale_writer", "written"]
    recovered = WorkPlanExecutionJournal(tmp_path, WorkPlan(1,
        "cross-process-journal-plan", "2026-01-01T00:00:00Z", "manual", ("g1",), (
            Task(1, "g1:one", "g1", "forge_propose", (), None, 0, 0, {}, (), False),
            Task(1, "g1:two", "g1", "forge_propose", (), None, 0, 0, {}, (), False),
        )))
    assert sum(recovered.state(task_id) == "interrupted"
        for task_id in ("g1:one", "g1:two")) == 1
    assert len(recovered.path.read_text(encoding="utf-8").splitlines()) == 1


@pytest.mark.skipif(os.name != "posix", reason="journal locking uses POSIX flock")
def test_process_crash_during_append_preserves_partial_record_and_releases_lock(
        tmp_path: Path) -> None:
    journal = WorkPlanExecutionJournal(tmp_path, _two_task_plan())
    journal.start("g1:one")
    valid_prefix = journal.path.read_bytes()
    context = multiprocessing.get_context("fork")
    partial_write_started = context.Event()
    process = context.Process(target=_crash_during_journal_append,
        args=(str(tmp_path), partial_write_started))

    process.start()
    try:
        assert partial_write_started.wait(timeout=10)
        process.join(timeout=10)

        assert process.exitcode == 73
        interrupted_bytes = journal.path.read_bytes()
        assert interrupted_bytes.startswith(valid_prefix)
        assert len(interrupted_bytes) > len(valid_prefix)
        assert not interrupted_bytes.endswith(b"\n")

        with pytest.raises(WorkPlanJournalError, match="work_plan_journal_bounds_invalid"):
            WorkPlanExecutionJournal(tmp_path, _two_task_plan())
        assert journal.path.read_bytes() == interrupted_bytes
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)


def test_incomplete_final_record_is_preserved_and_never_repaired(tmp_path: Path) -> None:
    plan = _plan()
    journal = WorkPlanExecutionJournal(tmp_path, plan)
    journal.start("g1:propose")
    with journal.path.open("ab") as handle:
        handle.write(b'{"schema_version":2')
    interrupted = journal.path.read_bytes()

    with pytest.raises(WorkPlanJournalError, match="work_plan_journal_bounds_invalid"):
        WorkPlanExecutionJournal(tmp_path, plan)
    assert journal.path.read_bytes() == interrupted


def test_terminal_task_result_is_recovered_with_original_artifacts_and_times(tmp_path: Path) -> None:
    plan = _plan()
    result = TaskRun("g1:propose", "g1", "forge_propose", "success", None,
        "2026-01-01T00:00:01Z", "2026-01-01T00:00:02Z", 1000,
        ("glow/forge/plan.json",), False)
    journal = WorkPlanExecutionJournal(tmp_path, plan)
    journal.start("g1:propose")
    journal.finish("g1:propose", status="success", reason=None, result=result)

    recovered = WorkPlanExecutionJournal(tmp_path, plan)

    assert recovered.state("g1:propose") == "success"
    assert recovered.result("g1:propose") == result
    rows = [json.loads(line) for line in journal.path.read_text().splitlines()]
    assert all(row["schema_version"] == 2 for row in rows)
    assert rows[-1]["task_result"]["artifacts"] == ["glow/forge/plan.json"]


def test_legacy_v1_started_journal_remains_explicitly_unknown(tmp_path: Path) -> None:
    plan = _plan()
    journal = WorkPlanExecutionJournal(tmp_path, plan)
    semantic = {"schema_version": 1, "sequence": 1, "plan_id": plan.plan_id,
        "plan_digest": journal.plan_digest, "task_id": "g1:propose", "event": "started",
        "status": None, "reason": None, "recorded_at": "2026-01-01T00:00:01Z",
        "previous_digest": "0" * 64}
    digest = hashlib.sha256(json.dumps(semantic, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    journal.path.parent.mkdir(parents=True, exist_ok=True)
    journal.path.write_text(json.dumps({**semantic, "digest": digest}, sort_keys=True,
        separators=(",", ":")) + "\n")

    recovered = WorkPlanExecutionJournal(tmp_path, plan)

    assert recovered.state("g1:propose") == "interrupted"
    assert recovered.result("g1:propose") is None
