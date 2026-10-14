from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import sentientos.goal_executor as goal_executor

from sentientos.goal_executor import ExecutorState, GoalExecutor
from sentientos.risk_budget import RiskBudget
from sentientos.work_plan import Task, WorkPlan, persist_work_run


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
    second = GoalExecutor(repo_root=tmp_path).execute_plan(plan, _state(tmp_path))

    assert calls == ["g1:propose"]
    assert first.task_runs[0].status == "success"
    assert second.task_runs[0] == first.task_runs[0]
    assert second.status == first.status


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
