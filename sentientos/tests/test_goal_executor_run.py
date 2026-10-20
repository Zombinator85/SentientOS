from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest
import sentientos.goal_executor as goal_executor

from sentientos.goal_executor import ExecutorState, GoalExecutor
from sentientos.risk_budget import RiskBudget
from sentientos.work_plan import (Task, WorkPlan, persist_work_plan_evidence,
    load_work_run, persist_work_run, work_plan_id_from_evidence)
from sentientos.work_plan_execution_journal import (WorkPlanExecutionJournal,
    WorkPlanJournalError)


def _plan() -> WorkPlan:
    return WorkPlan(
        schema_version=1,
        plan_id="p1",
        created_at="2026-01-01T00:00:00Z",
        context="manual",
        selected_goals=("g1",),
        tasks=(
            Task(1, "g1:diagnostic", "g1", "diagnostic", (), None, 0, 0, {}, (), False),
            Task(1, "g1:apply", "g1", "forge_apply", (), None, 1, 1, {}, (), True),
        ),
    )


def test_execute_recovery_skips_destructive(tmp_path: Path) -> None:
    state = ExecutorState(
        repo_root=tmp_path,
        created_at="2026-01-01T00:00:00Z",
        context="manual",
        operating_mode="recovery",
        quarantine_active=False,
        allow_mutation=True,
        goal_graph_hash="h",
        allocation_id="a",
        risk_budget=RiskBudget(),
    )
    run = GoalExecutor(repo_root=tmp_path).execute_plan(_plan(), state)
    assert run.task_runs[0].status in {"success", "failed"}
    assert run.task_runs[1].status == "skipped"


def test_execute_quarantine_skips_destructive(tmp_path: Path) -> None:
    state = ExecutorState(
        repo_root=tmp_path,
        created_at="2026-01-01T00:00:00Z",
        context="manual",
        operating_mode="normal",
        quarantine_active=True,
        allow_mutation=False,
        goal_graph_hash="h",
        allocation_id="a",
        risk_budget=RiskBudget(forge_max_files_changed=0),
    )
    run = GoalExecutor(repo_root=tmp_path).execute_plan(_plan(), state)
    assert run.task_runs[1].status == "skipped"
    assert run.task_runs[1].reason == "mutation_disallowed"


def _state(tmp_path: Path, *, operating_mode: str = "normal", allow_mutation: bool = True) -> ExecutorState:
    return ExecutorState(
        repo_root=tmp_path,
        created_at="2026-01-01T00:00:00Z",
        context="manual",
        operating_mode=operating_mode,
        quarantine_active=False,
        allow_mutation=allow_mutation,
        goal_graph_hash="h",
        allocation_id="a",
        risk_budget=RiskBudget(),
    )


def _single_task_plan(task: Task) -> WorkPlan:
    return WorkPlan(1, "p1", "2026-01-01T00:00:00Z", "manual", ("g1",), (task,))


def test_execute_rejects_plan_time_mismatch_before_any_effect_or_journal(
    tmp_path: Path, monkeypatch,
) -> None:
    plan = _single_task_plan(Task(1, "t1", "g1", "forge_propose", (), None,
        0, 0, {}, (), False))
    calls: list[str] = []
    executor = GoalExecutor(repo_root=tmp_path)
    monkeypatch.setattr(executor, "_execute_task",
        lambda task: calls.append(task.task_id) or ("success", None, ()))

    with pytest.raises(goal_executor.WorkPlanError,
                       match="work_run_lookup_plan_time_mismatch"):
        executor.execute_plan(plan, replace(_state(tmp_path),
            created_at="2026-01-02T00:00:00Z"))

    assert calls == []
    assert not (tmp_path / "glow/forge/work_plan_journals").exists()
    assert not (tmp_path / "glow/forge/work_runs").exists()


def test_first_journal_append_syncs_new_directory_entries(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _single_task_plan(Task(1, "t1", "g1", "diagnostic", (), None,
        0, 0, {}, (), False))
    journal = WorkPlanExecutionJournal(tmp_path, plan)
    assert not journal.path.parent.exists()

    sync_targets: list[str] = []
    fsync = os.fsync

    def record_sync_target(descriptor: int) -> None:
        sync_targets.append("directory" if stat.S_ISDIR(os.fstat(descriptor).st_mode)
            else "file")
        fsync(descriptor)

    monkeypatch.setattr(os, "fsync", record_sync_target)
    journal.start("t1")

    assert sync_targets == ["directory", "directory", "directory", "file", "directory"]


def test_executor_stops_before_task_effect_when_journal_directory_sync_fails(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _single_task_plan(Task(1, "t1", "g1", "diagnostic", (), None,
        0, 0, {}, (), False))
    journal = WorkPlanExecutionJournal(tmp_path, plan)
    journal.path.parent.mkdir(parents=True, exist_ok=True)
    executor = GoalExecutor(repo_root=tmp_path)
    effects: list[str] = []

    def record_effect(task: Task) -> tuple[str, str | None, tuple[str, ...]]:
        effects.append(task.task_id)
        return "success", None, ()

    monkeypatch.setattr(executor, "_execute_task", record_effect)
    fsync = os.fsync

    def fail_directory_sync(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("simulated journal directory sync failure")
        fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory_sync)
    with pytest.raises(WorkPlanJournalError,
            match="work_plan_journal_write_failed"):
        executor.execute_plan(plan, _state(tmp_path))

    assert effects == []
    assert not (tmp_path / "glow/forge/work_runs").exists()
    interrupted_bytes = journal.path.read_bytes()
    recovered = WorkPlanExecutionJournal(tmp_path, plan)
    assert recovered.state("t1") == "interrupted"
    assert journal.path.read_bytes() == interrupted_bytes


def test_execute_rejects_changed_canonical_evidence_before_task_effect(
    tmp_path: Path, monkeypatch,
) -> None:
    created_at = "2026-01-01T00:00:00Z"
    evidence_binding = {"goal_graph_hash": "h", "allocation_artifact_path": "a"}
    plan = WorkPlan(
        1,
        work_plan_id_from_evidence(created_at, "h", "a", evidence_binding),
        created_at,
        "canonical",
        ("g1",),
        (Task(1, "t1", "g1", "forge_propose", (), None, 0, 0, {}, (), False),),
    )
    evidence_path, evidence_digest = persist_work_plan_evidence(
        tmp_path, plan, evidence_binding)
    persisted_evidence = tmp_path / evidence_path
    persisted_evidence.write_bytes(persisted_evidence.read_bytes() + b" ")

    calls: list[str] = []
    executor = GoalExecutor(repo_root=tmp_path)
    monkeypatch.setattr(executor, "_execute_task",
        lambda task: calls.append(task.task_id) or ("success", None, ()))
    with pytest.raises(goal_executor.WorkPlanError,
                       match="work_plan_evidence_noncanonical"):
        executor.execute_plan(plan, _state(tmp_path),
            expected_evidence_digest=evidence_digest)

    assert calls == []
    assert not (tmp_path / "glow/forge/work_plan_journals").exists()


def test_execute_requires_digest_for_persisted_plan_evidence_before_task_effect(
    tmp_path: Path, monkeypatch,
) -> None:
    created_at = "2026-01-01T00:00:00Z"
    evidence_binding = {"goal_graph_hash": "h", "allocation_artifact_path": "a"}
    plan = WorkPlan(
        1,
        work_plan_id_from_evidence(created_at, "h", "a", evidence_binding),
        created_at,
        "canonical",
        ("g1",),
        (Task(1, "t1", "g1", "forge_propose", (), None, 0, 0, {}, (), False),),
    )
    persist_work_plan_evidence(tmp_path, plan, evidence_binding)

    calls: list[str] = []
    executor = GoalExecutor(repo_root=tmp_path)
    monkeypatch.setattr(executor, "_execute_task",
        lambda task: calls.append(task.task_id) or ("success", None, ()))
    with pytest.raises(goal_executor.WorkPlanError,
                       match="work_plan_evidence_digest_required"):
        executor.execute_plan(plan, _state(tmp_path))

    assert calls == []
    assert not (tmp_path / "glow/forge/work_plan_journals").exists()
    assert not (tmp_path / "glow/forge/work_runs").exists()


def test_execution_run_persists_exact_verified_plan_evidence_digest(
    tmp_path: Path, monkeypatch,
) -> None:
    created_at = "2026-01-01T00:00:00Z"
    evidence_binding = {"goal_graph_hash": "h", "allocation_artifact_path": "a",
        "selected_reasons": [{"goal_id": "g1", "epistemic_positions": [
            {"proposition_id": "p1", "identity": {"state_id": "s1"}}]}]}
    plan = WorkPlan(1, work_plan_id_from_evidence(created_at, "h", "a",
        evidence_binding), created_at, "canonical", ("g1",),
        (Task(1, "t1", "g1", "forge_propose", (), None, 0, 0, {}, (), False),))
    _, evidence_digest = persist_work_plan_evidence(tmp_path, plan, evidence_binding)
    calls: list[str] = []
    executor = GoalExecutor(repo_root=tmp_path)
    monkeypatch.setattr(executor, "_execute_task",
        lambda task: calls.append(task.task_id) or ("success", None, ()))

    run = executor.execute_plan(plan, _state(tmp_path),
        expected_evidence_digest=evidence_digest)
    assert run.schema_version == 3
    assert run.evidence_digest == evidence_digest
    assert run.task_runs[0].status == "success"
    assert calls == ["t1"]
    run_path = tmp_path / persist_work_run(tmp_path, run)
    persisted = json.loads(run_path.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 3
    assert persisted["evidence_digest"] == evidence_digest
    assert load_work_run(tmp_path, plan, created_at=created_at) == run
    assert executor.execute_plan(plan, _state(tmp_path),
        expected_evidence_digest=evidence_digest) == run
    assert calls == ["t1"]

    persisted["evidence_digest"] = "f" * 64
    run_path.write_text(json.dumps(persisted, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    with pytest.raises(goal_executor.WorkPlanError,
            match="work_run_evidence_binding_mismatch"):
        load_work_run(tmp_path, plan, created_at=created_at)


def test_plan_command_rejects_shell_payload_without_launching(tmp_path: Path, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(goal_executor.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    task = Task(1, "t1", "g1", "diagnostic", ("python -m scripts.contract_drift; touch pwned",), None, 0, 0, {}, (), False)

    run = GoalExecutor(repo_root=tmp_path).execute_plan(_single_task_plan(task), _state(tmp_path))

    assert calls == []
    assert run.task_runs[0].status == "failed"
    assert run.task_runs[0].reason == "command_not_allowlisted"
    assert not (tmp_path / "pwned").exists()


def test_allowlisted_plan_command_uses_argv_without_shell(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(goal_executor.subprocess, "run", fake_run)
    task = Task(1, "t1", "g1", "diagnostic", ("python -m scripts.contract_drift",), None, 0, 0, {}, (), False)

    run = GoalExecutor(repo_root=tmp_path).execute_plan(_single_task_plan(task), _state(tmp_path))

    assert run.task_runs[0].status == "success"
    assert len(calls) == 1
    assert calls[0][0] == ([goal_executor.sys.executable, "-m", "scripts.contract_drift"],)
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["cwd"] == tmp_path.resolve()
    assert calls[0][1]["timeout"] == goal_executor.PLAN_COMMAND_TIMEOUT_SECONDS


def test_terminal_task_replay_reuses_original_run_artifact(tmp_path: Path, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(goal_executor, "_run_commands",
        lambda *_args, **_kwargs: (calls.append("run") or "success", None,
            ("glow/contracts/contract_status.json",)))
    task = Task(1, "t1", "g1", "diagnostic",
        ("python -m scripts.contract_drift",), None, 0, 0, {}, (), False)
    plan = _single_task_plan(task)
    state = _state(tmp_path)

    original = GoalExecutor(repo_root=tmp_path).execute_plan(plan, state)
    path = persist_work_run(tmp_path, original)
    recovered = GoalExecutor(repo_root=tmp_path).execute_plan(plan, state)

    assert calls == ["run"]
    assert recovered == original
    assert persist_work_run(tmp_path, recovered) == path
    assert len((tmp_path / "pulse/work_runs.jsonl").read_text().splitlines()) == 1


def test_allowlisted_plan_command_timeout_is_a_failed_task(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def timeout(*args, **kwargs):
        calls.append((args, kwargs))
        raise goal_executor.subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(goal_executor.subprocess, "run", timeout)
    task = Task(1, "t1", "g1", "diagnostic", ("python -m scripts.contract_drift",), None, 0, 0, {}, (), False)

    run = GoalExecutor(repo_root=tmp_path).execute_plan(
        _single_task_plan(task), _state(tmp_path))

    assert len(calls) == 1
    assert run.task_runs[0].status == "failed"
    assert run.task_runs[0].reason == "command_timeout"
    assert run.task_runs[0].artifacts == ()


def test_forge_apply_kind_is_destructive_even_if_plan_claims_otherwise(tmp_path: Path, monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("forge apply must be blocked before execution")

    monkeypatch.setattr(goal_executor.CathedralForge, "run", forbidden)
    forged_task = Task(1, "t1", "g1", "forge_apply", (), None, 0, 0, {}, (), False)

    run = GoalExecutor(repo_root=tmp_path).execute_plan(
        _single_task_plan(forged_task), _state(tmp_path, operating_mode="recovery")
    )

    assert run.task_runs[0].status == "skipped"
    assert run.task_runs[0].reason == "mode_disallows_destructive:recovery"
    assert run.task_runs[0].destructive is True


def test_unimplemented_plan_tasks_do_not_claim_success(tmp_path: Path) -> None:
    for kind in ("fetch", "doc_update"):
        task = Task(1, "t1", "g1", kind, (), None, 0, 0, {}, ("uncreated-artifact",), False)

        run = GoalExecutor(repo_root=tmp_path).execute_plan(
            replace(_single_task_plan(task), plan_id=f"p-{kind}"), _state(tmp_path))

        assert run.task_runs[0].status == "skipped"
        assert run.task_runs[0].reason == "task_kind_not_implemented"
        assert run.task_runs[0].artifacts == ()


def test_completed_task_is_not_reexecuted_when_same_plan_is_recovered(
    tmp_path: Path, monkeypatch,
) -> None:
    calls = []
    task = Task(1, "g1:propose", "g1", "forge_propose", (), None, 0, 0, {}, (), False)
    plan = WorkPlan(1, "recover-completed", "2026-01-01T00:00:00Z", "manual", ("g1",), (task,))
    monkeypatch.setattr(GoalExecutor, "_execute_task", lambda self, row: (
        calls.append(row.task_id) or ("success", None, ("glow/forge/plan.json",))))

    first = GoalExecutor(repo_root=tmp_path).execute_plan(plan, _state(tmp_path))
    path = persist_work_run(tmp_path, first)
    assert calls == ["g1:propose"]
    assert first.task_runs[0].status == "success"

    journal = WorkPlanExecutionJournal(tmp_path, plan)
    legacy_rows = []
    previous_digest = "0" * 64
    for line in journal.path.read_text(encoding="utf-8").splitlines():
        old = json.loads(line)
        semantic = {key: old[key] for key in (
            "sequence", "plan_id", "plan_digest", "task_id", "event", "status",
            "reason", "recorded_at")}
        semantic = {"schema_version": 1, **semantic, "previous_digest": previous_digest}
        digest = hashlib.sha256(json.dumps(semantic, sort_keys=True,
            separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        legacy_rows.append({**semantic, "digest": digest})
        previous_digest = digest
    journal.path.write_text("".join(json.dumps(row, sort_keys=True,
        separators=(",", ":")) + "\n" for row in legacy_rows), encoding="utf-8")

    child = r'''
import json, sys
from pathlib import Path
from sentientos.goal_executor import ExecutorState, GoalExecutor
from sentientos.risk_budget import RiskBudget
from sentientos.work_plan import Task, WorkPlan, persist_work_run
root = Path(sys.argv[1])
plan = WorkPlan(1, "recover-completed", "2026-01-01T00:00:00Z", "manual", ("g1",),
    (Task(1, "g1:propose", "g1", "forge_propose", (), None, 0, 0, {}, (), False),))
state = ExecutorState(root, plan.created_at, "manual", "normal", False, True, "h", "a", RiskBudget())
def forbidden(self, task):
    raise AssertionError("persisted work run must recover before task execution")
GoalExecutor._execute_task = forbidden
run = GoalExecutor(repo_root=root).execute_plan(plan, state)
path = persist_work_run(root, run)
print(json.dumps({"run": run.to_dict(), "path": path}, sort_keys=True))
'''
    completed = subprocess.run([sys.executable, "-c", child, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True,
        check=True, timeout=15)
    recovered = json.loads(completed.stdout.strip().splitlines()[-1])
    assert recovered["run"] == first.to_dict()
    assert recovered["path"] == path
    assert len((tmp_path / "pulse/work_runs.jsonl").read_text().splitlines()) == 1


def test_interrupted_task_stays_unknown_while_independent_task_continues(
    tmp_path: Path, monkeypatch,
) -> None:
    calls = []
    tasks = (
        Task(1, "g1:propose", "g1", "forge_propose", (), None, 0, 0, {}, (), False),
        Task(1, "g1:apply", "g1", "forge_apply", (), None, 1, 1,
            {"requires_mutation": True}, (), True, ("g1:propose",)),
        Task(1, "g2:diagnostic", "g2", "diagnostic",
            ("python -m scripts.contract_drift",), None, 0, 0, {}, (), False),
    )
    plan = WorkPlan(1, "recover-interrupted", "2026-01-01T00:00:00Z",
        "manual", ("g1", "g2"), tasks)

    def interrupted(self, task):
        calls.append(task.task_id)
        if task.task_id == "g1:propose":
            raise SystemExit("simulated process interruption after task start")
        return "success", None, ()

    monkeypatch.setattr(GoalExecutor, "_execute_task", interrupted)
    with pytest.raises(SystemExit, match="simulated process interruption"):
        GoalExecutor(repo_root=tmp_path).execute_plan(plan, _state(tmp_path))

    recovered = GoalExecutor(repo_root=tmp_path).execute_plan(plan, _state(tmp_path))

    assert calls == ["g1:propose", "g2:diagnostic"]
    assert [(row.task_id, row.status, row.reason) for row in recovered.task_runs] == [
        ("g1:propose", "skipped", "prior_attempt_outcome_unknown"),
        ("g1:apply", "skipped", "dependency_not_satisfied:g1:propose"),
        ("g2:diagnostic", "success", None),
    ]


def test_interrupted_idempotent_check_retries_until_outcome_then_unblocks_dependency(
    tmp_path: Path, monkeypatch,
) -> None:
    checks = []
    tasks = (
        Task(1, "g1:diagnostic", "g1", "diagnostic",
            ("python -m scripts.contract_drift",), None, 0, 0, {}, (), False),
        Task(1, "g1:propose", "g1", "forge_propose", (), None, 0, 0, {}, (), False,
            ("g1:diagnostic",)),
    )
    plan = WorkPlan(1, "retry-safe-check", "2026-01-01T00:00:00Z",
        "manual", ("g1",), tasks)

    def interrupted_twice(self, task):
        checks.append(task.task_id)
        if task.task_id == "g1:diagnostic" and checks.count("g1:diagnostic") <= 2:
            raise SystemExit("simulated interruption during allowlisted check")
        return "success", None, ()

    monkeypatch.setattr(GoalExecutor, "_execute_task", interrupted_twice)
    executor = GoalExecutor(repo_root=tmp_path)
    for _ in range(2):
        with pytest.raises(SystemExit, match="simulated interruption"):
            executor.execute_plan(plan, _state(tmp_path))
    recovered = executor.execute_plan(plan, _state(tmp_path))

    assert checks == ["g1:diagnostic", "g1:diagnostic", "g1:diagnostic", "g1:propose"]
    assert [(row.task_id, row.status) for row in recovered.task_runs] == [
        ("g1:diagnostic", "success"), ("g1:propose", "success")]
    journal = WorkPlanExecutionJournal(tmp_path, plan)
    assert journal.state("g1:diagnostic") == "success"
    assert journal.attempt_count("g1:diagnostic") == 3
    assert journal.result("g1:diagnostic") == recovered.task_runs[0]
    assert journal.state("g1:propose") == "success"


def test_partial_forge_outcome_is_durable_and_does_not_satisfy_dependency(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(goal_executor.CathedralForge, "run",
        lambda *args, **kwargs: SimpleNamespace(
            outcome="partial_success", generated_at="2026-01-01T00:00:01Z"))
    monkeypatch.setattr(goal_executor, "_run_commands",
        lambda *args, **kwargs: ("success", None, ()))
    tasks = (
        Task(1, "g1:apply", "g1", "forge_apply", (), None, 1, 1,
            {"requires_mutation": True}, (), True),
        Task(1, "g1:verify", "g1", "verify", ("python -m scripts.run_tests -q",),
            None, 0, 0, {}, (), False, ("g1:apply",)),
        Task(1, "g2:diagnostic", "g2", "diagnostic",
            ("python -m scripts.contract_drift",), None, 0, 0, {}, (), False),
    )
    plan = WorkPlan(1, "partial-forge-progression", "2026-01-01T00:00:00Z",
        "manual", ("g1", "g2"), tasks)
    first = GoalExecutor(repo_root=tmp_path).execute_plan(plan, _state(tmp_path))

    assert first.status == "partial"
    assert [(row.status, row.reason) for row in first.task_runs] == [
        ("partial", "forge_apply_partial_success"),
        ("skipped", "dependency_not_satisfied:g1:apply"),
        ("success", None),
    ]
    path = persist_work_run(tmp_path, first)
    from sentientos.work_plan import load_work_run
    recovered = load_work_run(tmp_path, plan, created_at=plan.created_at)
    assert recovered == first
    assert (tmp_path / path).exists()
    assert GoalExecutor(repo_root=tmp_path).execute_plan(plan, _state(tmp_path)) == first
    journal = WorkPlanExecutionJournal(tmp_path, plan)
    assert journal.state("g1:apply") == "partial"
    assert journal.result("g1:apply") == first.task_runs[0]


def test_same_plan_id_changed_definition_gets_distinct_execution_journal(
    tmp_path: Path,
) -> None:
    task = Task(1, "goal:diagnostic", "goal", "diagnostic",
        ("python -m scripts.contract_drift",), None, 0, 0, {}, (), False)
    original = WorkPlan(1, "reused-plan-id", "2026-01-01T00:00:00Z",
        "manual", ("goal",), (task,))
    first = WorkPlanExecutionJournal(tmp_path, original)
    first.start(task.task_id)

    changed_task = replace(task, commands=("python -m scripts.different_check",))
    changed = replace(original, tasks=(changed_task,))
    second = WorkPlanExecutionJournal(tmp_path, changed)

    assert second.path != first.path
    assert second.state(task.task_id) is None


def test_failed_dependency_blocks_dependent_but_not_other_goals(
    tmp_path: Path, monkeypatch,
) -> None:
    tasks = (
        Task(1, "g1:verify", "g1", "verify", ("python -m scripts.run_tests -q",),
            None, 0, 0, {}, (), False),
        Task(1, "g1:propose", "g1", "forge_propose", (), None, 0, 0, {}, (), False),
        Task(1, "g1:apply", "g1", "forge_apply", (), None, 1, 1,
            {"requires_mutation": True}, (), True, ("g1:verify", "g1:propose")),
        Task(1, "g2:diagnostic", "g2", "diagnostic",
            ("python -m scripts.contract_drift",), None, 0, 0, {}, (), False),
    )
    plan = WorkPlan(1, "dependency-failure", "2026-01-01T00:00:00Z",
        "manual", ("g1", "g2"), tasks)
    calls = []

    def execute(self, task):
        calls.append(task.task_id)
        if task.task_id == "g1:verify":
            return "failed", "fixture_validation_failed", ()
        return "success", None, ()

    monkeypatch.setattr(GoalExecutor, "_execute_task", execute)
    run = GoalExecutor(repo_root=tmp_path).execute_plan(plan, _state(tmp_path))

    assert calls == ["g1:verify", "g1:propose", "g2:diagnostic"]
    outcomes = {row.task_id: (row.status, row.reason) for row in run.task_runs}
    assert outcomes["g1:apply"] == (
        "skipped", "dependency_not_satisfied:g1:verify")
    assert outcomes["g2:diagnostic"] == ("success", None)
