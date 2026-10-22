from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from sentientos.control_plane_kernel import ControlPlaneKernel
from sentientos.artifact_catalog import append_catalog_entry
from sentientos.goal_executor import ExecutorState, GoalExecutor, GoalPlanner
from sentientos.goal_graph import Goal, GoalGraph, goal_graph_hash, persist_goal_graph
from sentientos.orchestrator import (GoalPlanningResult,
    _emit_goal_allocation_artifact, _goal_tagged_epistemic_positions,
    _goal_tagged_epistemic_priority_selection,
    _latest_verified_prior_plan,
    _plan_goal_work, plan_goals)
from sentientos.persistent_epistemic_state import (PersistentEpistemicStateOwner,
    make_proposition)
from sentientos.runtime_governor import RuntimeGovernor
from sentientos.work_allocator import AllocationDecision
from sentientos.work_plan import (WorkPlanError, load_work_plan,
    load_work_plan_evidence,
    TaskRun, WorkPlan, WorkPlanRun, persist_work_plan,
    persist_work_plan_evidence, persist_work_run, work_plan_id_from_evidence,
    work_run_id)
from sentientos.work_plan_execution_journal import (WorkPlanExecutionJournal,
    WorkPlanJournalError)
from sentientos.risk_budget import RiskBudget
from sentientosd import HostResourceRuntimeCoordinator, RuntimeMaintenanceSurfaces

pytestmark = pytest.mark.no_legacy_skip


def test_plan_goals_rejects_unknown_offset_before_reading_projection_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ProjectionOwner:
        calls = 0

        def cognitive_projection(self, **_kwargs):
            self.calls += 1
            raise AssertionError("unknown planning time must be rejected first")

    def forbidden_graph_read(_root):
        raise AssertionError("unknown planning time must be rejected before repository reads")

    owner = ProjectionOwner()
    monkeypatch.setattr("sentientos.orchestrator.load_goal_graph", forbidden_graph_read)
    with pytest.raises(ValueError, match="planning_time_offset_unknown"):
        plan_goals(
            tmp_path, prior_epistemic_projection_owner=owner,  # type: ignore[arg-type]
            prior_epistemic_projection_max_states=1,
            planning_time="2026-10-22T01:00:00-00:00")
    assert owner.calls == 0


def test_plan_goals_rejects_unrepresentable_projection_time_before_owner_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnrepresentableInstant:
        tzinfo = timezone.utc

        @staticmethod
        def utcoffset():
            return timedelta(0)

        @staticmethod
        def timestamp() -> float:
            raise OverflowError("outside platform timestamp range")

    class FixedDateTime:
        @staticmethod
        def fromisoformat(_value: str) -> UnrepresentableInstant:
            return UnrepresentableInstant()

    class ProjectionOwner:
        calls = 0

        def cognitive_projection(self, **_kwargs):
            self.calls += 1
            raise AssertionError("unrepresentable planning time must be rejected first")

    owner = ProjectionOwner()
    monkeypatch.setattr("sentientos.orchestrator.datetime", FixedDateTime)
    monkeypatch.setattr(
        "sentientos.orchestrator.load_goal_graph",
        lambda _root: (_ for _ in ()).throw(
            AssertionError("unrepresentable time must be rejected before repository reads")))
    with pytest.raises(ValueError, match="planning_time_unrepresentable"):
        plan_goals(
            tmp_path, prior_epistemic_projection_owner=owner,  # type: ignore[arg-type]
            prior_epistemic_projection_max_states=1,
            planning_time="2026-10-22T01:00:00Z")
    assert owner.calls == 0


def test_goal_history_priorities_follow_enabled_deterministic_goal_precedence() -> None:
    first = "proposition:" + "a" * 24
    second = "proposition:" + "b" * 24
    disabled = "proposition:" + "c" * 24
    graph = GoalGraph(schema_version=1, goals=(
        Goal("lower", "lower precedence", 1.0, 1, (), "task:forge_propose", 1, 1,
            (f"epistemic_proposition:{first}",
                "epistemic_proposition:malformed", f"epistemic_proposition:{second}"), True),
        Goal("higher", "higher precedence", 1.0, 9, (), "task:forge_propose", 1, 1,
            (f"epistemic_proposition:{second}",
                f"epistemic_proposition:{first}"), True),
        Goal("disabled", "disabled", 1.0, 99, (), "task:forge_propose", 1, 1,
            (f"epistemic_proposition:{disabled}",), False),
    ))

    assert _goal_tagged_epistemic_positions(graph) == (second, first)


def test_goal_history_priorities_respect_projection_bound_deterministically() -> None:
    goals = tuple(
        Goal(f"g{index:04d}", "bounded priority", 1.0, 513 - index, (),
            "task:forge_propose", 1, 1,
            (f"epistemic_proposition:proposition:{index:024x}",), True)
        for index in range(513)
    )
    expected = tuple(f"proposition:{index:024x}" for index in range(512))

    assert _goal_tagged_epistemic_positions(
        GoalGraph(schema_version=1, goals=goals)) == expected
    assert _goal_tagged_epistemic_positions(
        GoalGraph(schema_version=1, goals=tuple(reversed(goals)))) == expected
    assert _goal_tagged_epistemic_priority_selection(
        GoalGraph(schema_version=1, goals=goals)) == (expected, True)
    assert _goal_tagged_epistemic_priority_selection(
        GoalGraph(schema_version=1, goals=goals[:512])) == (expected, False)
    duplicate = Goal("duplicate", "same priority", 1.0, 0, (),
        "task:forge_propose", 1, 1,
        (f"epistemic_proposition:{expected[0]}",), True)
    disabled = Goal("disabled-overflow", "disabled", 1.0, 0, (),
        "task:forge_propose", 1, 1,
        ("epistemic_proposition:proposition:" + "f" * 24,), False)
    assert _goal_tagged_epistemic_priority_selection(
        GoalGraph(schema_version=1, goals=goals[:512] + (duplicate, disabled))) == (
            expected, False)


def test_overflowed_goal_history_remains_review_required_in_daemon_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    admitted = make_proposition(
        namespace="embodiment", subject="goal:admitted",
        predicate="historical_outcome", object_value={"result": "unknown"},
        polarity="positive", qualifiers={}, temporal_scope={"kind": "bounded_trial"},
        context_scope={}, proposition_class="predictive")
    overflowed = make_proposition(
        namespace="embodiment", subject="goal:overflowed",
        predicate="historical_outcome", object_value={"result": "unknown"},
        polarity="positive", qualifiers={}, temporal_scope={"kind": "bounded_trial"},
        context_scope={}, proposition_class="predictive")
    priorities = [f"proposition:{index:024x}" for index in range(513)]
    priorities[0] = admitted.proposition_id
    priorities[-1] = overflowed.proposition_id
    goals = tuple(
        Goal(f"g{index:04d}", "bounded priority", 1.0, 513 - index, (),
            "task:forge_propose", 1, 1,
            (f"epistemic_proposition:{priorities[index]}",), True)
        for index in range(513)
    )
    graph = GoalGraph(schema_version=1, goals=goals)
    admitted_priorities = _goal_tagged_epistemic_positions(graph)
    assert len(admitted_priorities) == 512
    assert admitted_priorities[0] == admitted.proposition_id
    assert overflowed.proposition_id not in admitted_priorities

    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text(
        "{}\n", encoding="utf-8")
    persist_goal_graph(tmp_path, graph)
    owner = PersistentEpistemicStateOwner(
        tmp_path / "epistemic", allowed_namespaces=["embodiment"])
    for index, proposition in enumerate((admitted, overflowed)):
        owner.register_proposition(proposition)
        owner.commit_update(
            proposition_id=proposition.proposition_id,
            expected_predecessor_digest=None, stance="provisionally_contradicted",
            reason="initialization", active_binding_ids=(),
            correlation_id=f"overflow-{index}", tick=index + 1,
            recorded_at="2026-01-01T00:00:00Z")

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, epistemic_state_owner=owner,
        epistemic_state_config={
            "status": "configured", "cognitive_consumption_enabled": True,
            "max_cognitive_projection_count": 1})

    def forbidden_execute(*_args, **_kwargs):
        raise AssertionError("planning must not execute goals")

    monkeypatch.setattr(GoalExecutor, "execute_plan", forbidden_execute)
    feedback = surfaces.run_canonical_goal_planning(
        tick_id="2033-05-18T03:33:20+00:00")
    assert feedback["execution_performed"] is False
    assert feedback["authority"] is False
    assert feedback["prior_epistemic_priority_overflowed"] is True
    assert feedback["prior_epistemic_priority_limit"] == 512
    evidence = json.loads((tmp_path / feedback[
        "work_plan_evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["evidence_binding"][
        "prior_epistemic_priority_admission"] == {
            "limit": 512, "overflowed": True}
    persisted_plan = load_work_plan(tmp_path / feedback["work_plan_path"])
    recovered_evidence = load_work_plan_evidence(tmp_path, persisted_plan)
    assert recovered_evidence["evidence_binding"][
        "prior_epistemic_priority_admission"] == {
            "limit": 512, "overflowed": True}
    binding = evidence["evidence_binding"]
    changed_admission = {
        **binding,
        "prior_epistemic_priority_admission": {
            "limit": 512, "overflowed": False},
    }
    assert work_plan_id_from_evidence(
        binding["planning_time"], binding["goal_graph_hash"],
        binding["allocation_artifact_path"], changed_admission,
    ) != evidence["plan_id"]
    allocation = json.loads((tmp_path / feedback[
        "allocation_artifact_path"]).read_text(encoding="utf-8"))
    assert allocation["prior_epistemic_priority_overflowed"] is True
    assert allocation["prior_epistemic_priority_limit"] == 512
    manifest = evidence["evidence_binding"]["projection_omission_manifest"]
    assert manifest["prioritized_proposition_ids"] == [admitted.proposition_id]
    [omitted_identity] = manifest["omitted_state_identities"]
    assert omitted_identity["proposition_id"] == overflowed.proposition_id
    assert omitted_identity["stance"] == "provisionally_contradicted"
    assert omitted_identity["omission_reason"] == "projection_state_bound"
    assert omitted_identity["state_digest"] == owner.current_state(
        overflowed.proposition_id).state_digest
    assert evidence["evidence_binding"]["goal_applicability"]["g0512"] == (
        "epistemic_applicability_unresolved")
    assert not list((tmp_path / "glow/forge/work_runs").glob("run_*.json"))


def test_canonical_plan_import_and_composition_do_not_load_goal_executor(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    env = {
        **os.environ,
        "SENTIENTOS_REPO_ROOT": str(tmp_path),
        "SENTIENTOS_GOVERNOR_ROOT": str(tmp_path / "governor"),
        "SENTIENTOS_FEDERATION_ROOT": str(tmp_path / "federation"),
        "SENTIENTOS_RUNTIME_STATE_ROOT": str(tmp_path / "runtime"),
    }
    result = subprocess.run(
        [sys.executable, "-c",
            "import sys; from pathlib import Path; "
            "import sentientos.goal_planner; "
            "from sentientos.orchestrator import plan_goals; "
            "plan_goals(Path(sys.argv[1]), "
            "planning_time='2026-10-16T09:00:00+00:00'); "
            "assert 'sentientos.goal_executor' not in sys.modules",
            str(tmp_path)], cwd=repo_root, env=env, capture_output=True,
        text=True, check=False, timeout=20,
    )
    assert result.returncode == 0, result.stderr


def test_goal_allocation_artifact_retry_is_idempotent_and_conflict_never_overwrites(
    tmp_path: Path,
) -> None:
    allocation = AllocationDecision(
        selected=("g1",), deferred=(), selected_reasons=(),
        budget_summary={"risk_spent": 1, "risk_cap": 1,
            "throughput_spent": 1, "throughput_cap": 1},
    )
    arguments = {
        "root": tmp_path, "generated_at": "2026-10-16T09:00:00+00:00",
        "operating_mode": "normal", "pressure_level": 0,
        "posture": "balanced", "goal_graph_hash_value": "graph-digest",
        "allocation": allocation,
    }

    path = _emit_goal_allocation_artifact(**arguments)
    artifact_path, artifact_digest = path
    artifact = tmp_path / artifact_path
    original = artifact.read_bytes()

    assert artifact_digest == "sha256:" + hashlib.sha256(original).hexdigest()
    assert _emit_goal_allocation_artifact(**arguments) == path
    assert artifact.read_bytes() == original
    with pytest.raises(WorkPlanError,
                       match="goal_allocation_artifact_identity_conflict"):
        _emit_goal_allocation_artifact(**{**arguments, "posture": "velocity"})
    assert artifact.read_bytes() == original


def test_reconstructed_completion_changes_next_canonical_allocation(
    tmp_path: Path,
) -> None:
    completed_goal = Goal("completed", "done", 1.0, 2, (),
        "check_forge_last_run_ok", 1, 1, ("integrity",), True)
    prior_graph = GoalGraph(schema_version=1, goals=(completed_goal,))
    prior_time = "2026-10-16T08:00:00Z"
    prior_allocation = AllocationDecision(selected=("completed",), deferred=(),
        selected_reasons=(), budget_summary={})
    budget = RiskBudget(router_k_max=8, router_m_max=8, forge_max_files_changed=0)
    prior_state = ExecutorState(repo_root=tmp_path, created_at=prior_time,
        context="orchestrator_tick", operating_mode="normal",
        quarantine_active=False, allow_mutation=False,
        goal_graph_hash=goal_graph_hash(prior_graph), allocation_id="allocation_prior",
        risk_budget=budget)
    prior_draft = GoalPlanner(repo_root=tmp_path).build_plan_with_evidence(
        prior_allocation, prior_state, prior_graph)
    prior_plan = prior_draft.work_plan
    prior_plan_path = persist_work_plan(tmp_path, prior_plan)
    prior_evidence_path, prior_evidence_digest = persist_work_plan_evidence(
        tmp_path, prior_plan, dict(prior_draft.evidence_binding))
    prior_run_id = work_run_id(prior_plan, created_at=prior_plan.created_at)
    prior_task_runs = tuple(TaskRun(task.task_id, task.goal_id, task.kind,
        "success", None, prior_time, prior_time, 0, (), task.destructive)
        for task in prior_plan.tasks)
    prior_journal = WorkPlanExecutionJournal(tmp_path, prior_plan)
    for task_run in prior_task_runs:
        prior_journal.start(task_run.task_id)
        prior_journal.finish(task_run.task_id, status=task_run.status,
            reason=task_run.reason, result=task_run)
    prior_run = WorkPlanRun(schema_version=3, run_id=prior_run_id,
        plan_id=prior_plan.plan_id, created_at=prior_time, status="ok",
        operating_mode="normal", quarantine_active=False,
        task_runs=prior_task_runs, reason_stack=(),
        plan_digest=prior_plan.identity_digest(),
        evidence_digest=prior_evidence_digest)
    prior_run_path = persist_work_run(tmp_path, prior_run)
    append_catalog_entry(tmp_path, kind="work_plan", artifact_id=prior_plan.plan_id,
        relative_path=prior_plan_path, schema_name="work_plan", schema_version=1,
        links={"work_plan_id": prior_plan.plan_id}, summary={"status": "persisted"})
    append_catalog_entry(tmp_path, kind="work_plan_evidence",
        artifact_id=f"evidence_{prior_plan.plan_id}",
        relative_path=prior_evidence_path, schema_name="work_plan_evidence",
        schema_version=1, links={"work_plan_id": prior_plan.plan_id},
        summary={"evidence_digest": prior_evidence_digest,
            "plan_digest": prior_plan.identity_digest()})
    append_catalog_entry(tmp_path, kind="work_run", artifact_id=prior_run_id,
        relative_path=prior_run_path, schema_name="", schema_version=3,
        links={"work_run_id": prior_run_id, "goal_ids": ["completed"]},
        summary={"status": "ok", "evidence_digest": prior_evidence_digest})

    dependent_goal = Goal("dependent", "next", 1.0, 1, ("completed",),
        "unrecognized_check", 1, 1, ("integrity",), True)
    graph = GoalGraph(schema_version=1, goals=(completed_goal, dependent_goal))
    result = _plan_goal_work(root=tmp_path, graph=graph, budget=budget,
        operating_mode="normal", pressure_level=0, quarantine_active=False,
        posture="balanced", mutation_allowed=False,
        prior_epistemic_projection=None, target_model_identity_observer=None,
        planning_time="2026-10-16T09:00:00Z",
        catalog_timestamp="2026-10-16T09:00:00Z", context="orchestrator_tick")

    assert result.allocation.selected == ("dependent",)
    completed = next(item for item in result.allocation.deferred
        if item.goal_id == "completed")
    assert completed.reason == "verified_completion"
    assert completed.completion_evidence == {
        "check_name": "check_forge_last_run_ok",
        "evidence_digest": prior_evidence_digest,
        "evidence_paths": [prior_run_path],
    }
    assert result.work_plan is not None
    evidence = load_work_plan_evidence(tmp_path, result.work_plan)
    binding = evidence["evidence_binding"]
    assert isinstance(binding, dict)
    assert binding["deferred_goals"][0]["completion_evidence"] == completed.completion_evidence
    assert binding["selected_reasons"][0]["verified_completed_dependencies"] == [
        {"goal_id": "completed", **completed.completion_evidence}
    ]
    assert binding["prior_run_journal_digest"] == prior_journal.head_digest


def test_canonical_planning_uses_reconstructed_adverse_run_for_review_gate(
    tmp_path: Path,
) -> None:
    from sentientos.artifact_catalog import append_catalog_entry

    goal = Goal("g1", "recover from prior apply", 1.0, 1, (),
        "check_forge_last_run_ok", 2, 1, ("integrity",), True)
    graph = GoalGraph(schema_version=1, goals=(goal,))
    budget = RiskBudget(router_k_max=20, router_m_max=20,
        forge_max_files_changed=10)
    allocation = AllocationDecision(selected=("g1",), deferred=(),
        selected_reasons=(), budget_summary={})
    prior_time = "2026-10-16T08:00:00Z"
    prior_state = ExecutorState(repo_root=tmp_path, created_at=prior_time,
        context="orchestrator_tick", operating_mode="normal",
        quarantine_active=False, allow_mutation=True,
        goal_graph_hash=goal_graph_hash(graph), allocation_id="prior-allocation",
        risk_budget=budget)
    prior_draft = GoalPlanner(repo_root=tmp_path).build_plan_with_evidence(
        allocation, prior_state, graph)
    prior_plan = prior_draft.work_plan
    prior_plan_path = persist_work_plan(tmp_path, prior_plan)
    prior_evidence_path, prior_evidence_digest = persist_work_plan_evidence(
        tmp_path, prior_plan, dict(prior_draft.evidence_binding))
    apply_failure = "forge_apply_failed"
    prior_tasks = tuple(TaskRun(task.task_id, task.goal_id, task.kind,
        "failed" if task.kind == "forge_apply" else "success",
        apply_failure if task.kind == "forge_apply" else None,
        prior_time, prior_time, 0,
        ("glow/forge/report.json",) if task.kind == "forge_apply" else (),
        task.destructive) for task in prior_plan.tasks)
    prior_journal = WorkPlanExecutionJournal(tmp_path, prior_plan)
    for task_run in prior_tasks:
        prior_journal.start(task_run.task_id)
        prior_journal.finish(task_run.task_id, status=task_run.status,
            reason=task_run.reason, result=task_run)
    prior_run = WorkPlanRun(schema_version=3,
        run_id=work_run_id(prior_plan, created_at=prior_time),
        plan_id=prior_plan.plan_id, created_at=prior_time, status="failed",
        operating_mode="normal", quarantine_active=False,
        task_runs=prior_tasks, reason_stack=(apply_failure,),
        plan_digest=prior_plan.identity_digest(),
        evidence_digest=prior_evidence_digest)
    prior_run_path = persist_work_run(tmp_path, prior_run)
    append_catalog_entry(tmp_path, kind="work_plan", artifact_id=prior_plan.plan_id,
        relative_path=prior_plan_path, schema_name="work_plan", schema_version=1,
        links={"work_plan_id": prior_plan.plan_id}, summary={"status": "persisted"})
    append_catalog_entry(tmp_path, kind="work_plan_evidence",
        artifact_id=f"evidence_{prior_plan.plan_id}",
        relative_path=prior_evidence_path, schema_name="work_plan_evidence",
        schema_version=1, links={"work_plan_id": prior_plan.plan_id},
        summary={"evidence_digest": prior_evidence_digest,
            "plan_digest": prior_plan.identity_digest()})
    append_catalog_entry(tmp_path, kind="work_run", artifact_id=prior_run.run_id,
        relative_path=prior_run_path, schema_name="", schema_version=3,
        links={"work_run_id": prior_run.run_id, "goal_ids": ["g1"]},
        summary={"status": "failed", "evidence_digest": prior_evidence_digest},
        ts=prior_time)

    result = _plan_goal_work(root=tmp_path, graph=graph, budget=budget,
        operating_mode="normal", pressure_level=0, quarantine_active=False,
        posture="balanced", mutation_allowed=True,
        prior_epistemic_projection=None, target_model_identity_observer=None,
        planning_time="2026-10-16T09:00:00Z",
        catalog_timestamp="2026-10-16T09:00:00Z", context="orchestrator_tick")

    assert result.work_plan is not None
    assert not any(task.goal_id == "g1" and task.kind == "forge_apply"
        for task in result.work_plan.tasks)
    assert ("g1", "forge_apply", "prior_terminal_outcome_requires_review") in {
        (row.goal_id, row.kind, row.reason) for row in result.work_plan.omissions}
    evidence = load_work_plan_evidence(tmp_path, result.work_plan)
    binding = evidence["evidence_binding"]
    assert isinstance(binding, dict)
    assert binding["no_replay_goal_outcomes"] == {"g1": ["failed"]}
    assert binding["prior_run_digest"] is not None
    assert binding["prior_run_journal_digest"] == prior_journal.head_digest

    journal_bytes = prior_journal.path.read_bytes()
    assert b'"status":"failed"' in journal_bytes
    prior_journal.path.write_bytes(
        journal_bytes.replace(b'"status":"failed"', b'"status":"success"', 1))
    with pytest.raises(WorkPlanJournalError, match="work_plan_journal_digest_mismatch"):
        _plan_goal_work(root=tmp_path, graph=graph, budget=budget,
            operating_mode="normal", pressure_level=0, quarantine_active=False,
            posture="balanced", mutation_allowed=True,
            prior_epistemic_projection=None, target_model_identity_observer=None,
            planning_time="2026-10-16T10:00:00Z",
            catalog_timestamp="2026-10-16T10:00:00Z", context="orchestrator_tick")


def test_legacy_prior_run_is_unknown_instead_of_clean(tmp_path: Path) -> None:
    run_id = "run_" + "a" * 64
    relative_path = f"glow/forge/work_runs/{run_id}.json"
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 2, "run_id": run_id,
        "plan_id": "legacy-plan"}) + "\n", encoding="utf-8")
    append_catalog_entry(tmp_path, kind="work_run", artifact_id=run_id,
        relative_path=relative_path, schema_name="", schema_version=2,
        links={"work_run_id": run_id}, summary={"status": "failed"})

    prior_plan, outcome_unknown, journal_digest = _latest_verified_prior_plan(tmp_path)

    assert prior_plan is None
    assert outcome_unknown is True
    assert journal_digest is None


def test_clean_journal_backed_review_cycle_reenables_apply_plan(
    tmp_path: Path,
) -> None:
    goal = Goal("g1", "revalidate after a failed apply", 1.0, 1, (),
        "check_mypy_forge_ok", 2, 1, ("integrity",), True)
    graph = GoalGraph(schema_version=1, goals=(goal,))
    budget = RiskBudget(router_k_max=20, router_m_max=20,
        forge_max_files_changed=10)
    allocation = AllocationDecision(selected=("g1",), deferred=(),
        selected_reasons=(), budget_summary={})
    prior_time = "2026-10-16T08:00:00Z"
    prior_state = ExecutorState(repo_root=tmp_path, created_at=prior_time,
        context="orchestrator_tick", operating_mode="normal",
        quarantine_active=False, allow_mutation=True,
        goal_graph_hash=goal_graph_hash(graph), allocation_id="prior-allocation",
        risk_budget=budget)
    prior_draft = GoalPlanner(repo_root=tmp_path).build_plan_with_evidence(
        allocation, prior_state, graph)
    prior_plan = prior_draft.work_plan
    prior_plan_path = persist_work_plan(tmp_path, prior_plan)
    prior_evidence_path, prior_evidence_digest = persist_work_plan_evidence(
        tmp_path, prior_plan, dict(prior_draft.evidence_binding))
    prior_tasks = tuple(TaskRun(task.task_id, task.goal_id, task.kind,
        "failed" if task.kind == "forge_apply" else "success",
        "forge_apply_failed" if task.kind == "forge_apply" else None,
        prior_time, prior_time, 0,
        ("glow/forge/report.json",) if task.kind == "forge_apply" else (),
        task.destructive) for task in prior_plan.tasks)
    prior_journal = WorkPlanExecutionJournal(tmp_path, prior_plan)
    for task_run in prior_tasks:
        prior_journal.start(task_run.task_id)
        prior_journal.finish(task_run.task_id, status=task_run.status,
            reason=task_run.reason, result=task_run)
    prior_run = WorkPlanRun(schema_version=3,
        run_id=work_run_id(prior_plan, created_at=prior_time),
        plan_id=prior_plan.plan_id, created_at=prior_time, status="failed",
        operating_mode="normal", quarantine_active=False,
        task_runs=prior_tasks, reason_stack=("forge_apply_failed",),
        plan_digest=prior_plan.identity_digest(),
        evidence_digest=prior_evidence_digest)
    prior_run_path = persist_work_run(tmp_path, prior_run)
    append_catalog_entry(tmp_path, kind="work_plan", artifact_id=prior_plan.plan_id,
        relative_path=prior_plan_path, schema_name="work_plan", schema_version=1,
        links={"work_plan_id": prior_plan.plan_id}, summary={"status": "persisted"})
    append_catalog_entry(tmp_path, kind="work_plan_evidence",
        artifact_id=f"evidence_{prior_plan.plan_id}",
        relative_path=prior_evidence_path, schema_name="work_plan_evidence",
        schema_version=1, links={"work_plan_id": prior_plan.plan_id},
        summary={"evidence_digest": prior_evidence_digest,
            "plan_digest": prior_plan.identity_digest()})
    append_catalog_entry(tmp_path, kind="work_run", artifact_id=prior_run.run_id,
        relative_path=prior_run_path, schema_name="", schema_version=3,
        links={"work_run_id": prior_run.run_id, "goal_ids": ["g1"]},
        summary={"status": "failed", "evidence_digest": prior_evidence_digest},
        ts=prior_time)

    review = _plan_goal_work(root=tmp_path, graph=graph, budget=budget,
        operating_mode="normal", pressure_level=0, quarantine_active=False,
        posture="balanced", mutation_allowed=True,
        prior_epistemic_projection=None, target_model_identity_observer=None,
        planning_time="2026-10-16T09:00:00Z",
        catalog_timestamp="2026-10-16T09:00:00Z", context="orchestrator_tick")
    assert review.work_plan is not None
    assert not any(task.kind == "forge_apply" for task in review.work_plan.tasks)

    review_plan = review.work_plan
    review_time = "2026-10-16T09:00:00Z"
    review_tasks = tuple(TaskRun(task.task_id, task.goal_id, task.kind,
        "success", None, review_time, review_time, 0, (), task.destructive)
        for task in review_plan.tasks)
    review_journal = WorkPlanExecutionJournal(tmp_path, review_plan)
    for task_run in review_tasks:
        review_journal.start(task_run.task_id)
        review_journal.finish(task_run.task_id, status=task_run.status,
            reason=task_run.reason, result=task_run)
    assert review.work_plan_evidence_digest is not None
    review_run = WorkPlanRun(schema_version=3,
        run_id=work_run_id(review_plan, created_at=review_time),
        plan_id=review_plan.plan_id, created_at=review_time, status="ok",
        operating_mode="normal", quarantine_active=False,
        task_runs=review_tasks, reason_stack=(),
        plan_digest=review_plan.identity_digest(),
        evidence_digest=review.work_plan_evidence_digest)
    review_run_path = persist_work_run(tmp_path, review_run)
    append_catalog_entry(tmp_path, kind="work_run", artifact_id=review_run.run_id,
        relative_path=review_run_path, schema_name="", schema_version=3,
        links={"work_run_id": review_run.run_id, "goal_ids": ["g1"]},
        summary={"status": "ok",
            "evidence_digest": review.work_plan_evidence_digest}, ts=review_time)

    recovered = _plan_goal_work(root=tmp_path, graph=graph, budget=budget,
        operating_mode="normal", pressure_level=0, quarantine_active=False,
        posture="balanced", mutation_allowed=True,
        prior_epistemic_projection=None, target_model_identity_observer=None,
        planning_time="2026-10-16T10:00:00Z",
        catalog_timestamp="2026-10-16T10:00:00Z", context="orchestrator_tick")

    assert recovered.work_plan is not None
    assert any(task.kind == "forge_apply" for task in recovered.work_plan.tasks)
    recovered_evidence = load_work_plan_evidence(tmp_path, recovered.work_plan)
    recovered_binding = recovered_evidence["evidence_binding"]
    assert isinstance(recovered_binding, dict)
    assert recovered_binding["prior_run_journal_digest"] == review_journal.head_digest
    assert recovered_binding["no_replay_goal_outcomes"] == {}
def test_daemon_planning_binds_verified_owner_and_observed_identity_without_execution(
    tmp_path: Path, monkeypatch,
) -> None:
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    goals = tuple(
        Goal(f"g{index:04d}", "diagnostic", 1.0, 513 - index, (),
            "task:forge_propose", 1, 1,
            ("integrity", f"epistemic_proposition:proposition:{index:024x}"),
            True)
        for index in range(513)
    )
    persist_goal_graph(tmp_path, GoalGraph(schema_version=1, goals=goals))

    class ProjectionOwner:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int | None, tuple[str, ...]]] = []

        def cognitive_projection(self, *, max_states: int,
                                 current_tick: int | None = None,
                                 prioritized_proposition_ids: tuple[str, ...] = ()):
            self.calls.append((max_states, current_tick,
                prioritized_proposition_ids))
            return None

    class ServingObserver:
        def __init__(self) -> None:
            self.calls = 0

        def observed_current_model_identity(self):
            self.calls += 1
            return {"provider": "fixture", "model": "current"}

        def current_session(self):
            raise AssertionError("planning must not acquire a serving session")

        def invoke(self, *_args, **_kwargs):
            raise AssertionError("planning must not invoke a model")

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    owner = ProjectionOwner()
    observer = ServingObserver()
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path,
        epistemic_state_owner=owner,  # type: ignore[arg-type]
        epistemic_state_config={
            "status": "configured", "cognitive_consumption_enabled": True,
            "max_cognitive_projection_count": 7,
        },
        resident_cognitive_invoker=observer,
    )

    def forbidden_execute(*_args, **_kwargs):
        raise AssertionError("planning must not execute goals")

    monkeypatch.setattr(GoalExecutor, "execute_plan", forbidden_execute)
    assert not hasattr(GoalExecutor, "build_plan")
    assert callable(GoalPlanner.build_plan)
    tick_id = "2026-10-16T09:00:00+00:00"
    result = surfaces.plan_canonical_goals(tick_id=tick_id)

    assert isinstance(result, GoalPlanningResult)
    assert result.work_plan is not None
    assert result.work_plan_path is not None
    assert (tmp_path / result.work_plan_path).is_file()
    assert result.work_plan_evidence_path is not None
    assert result.work_plan_evidence_digest is not None
    assert (tmp_path / result.work_plan_evidence_path).is_file()
    evidence = json.loads((tmp_path / result.work_plan_evidence_path).read_text())
    assert evidence["plan_digest"] == result.work_plan.identity_digest()
    assert evidence["evidence_digest"] == result.work_plan_evidence_digest
    assert load_work_plan_evidence(tmp_path, result.work_plan) == evidence
    assert owner.calls == [(
        7, int(datetime.fromisoformat(tick_id).timestamp()),
        tuple(f"proposition:{index:024x}" for index in range(512)),
    )]
    assert observer.calls == 1
    assert result.target_active_model_identity_digest is not None
    assert list((tmp_path / "glow/forge/work_runs").glob("run_*.json")) == []


def test_daemon_plan_feedback_is_non_authorizing_and_execution_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    kernel = ControlPlaneKernel(
        runtime_governor=RuntimeGovernor(),
        decisions_path=tmp_path / "decisions.jsonl",
    )
    monkeypatch.setattr("sentientos.control_plane_kernel._KERNEL", kernel)
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path,
        runtime_state_root=tmp_path / "runtime",
        host_resource_runtime=HostResourceRuntimeCoordinator(
            kernel=kernel, runtime_state_root=tmp_path / "runtime"),
    )
    allocation = AllocationDecision(
        selected=("g1",), deferred=(), selected_reasons=(),
        budget_summary={"risk_spent": 0, "risk_cap": 1,
            "throughput_spent": 0, "throughput_cap": 1},
        prior_epistemic_projection_digest="sha256:prior-projection",
    )
    plan = WorkPlan(1, "plan-g1", "2026-10-16T09:00:00Z",
        "orchestrator_tick", ("g1",), ())
    result = SimpleNamespace(
        allocation=allocation, allocation_artifact_path="glow/allocation.json",
        allocation_artifact_digest="sha256:fixture-allocation",
        work_plan=plan, work_plan_path="glow/forge/work_plans/plan_g1.json",
        work_plan_evidence_path="glow/forge/work_plan_evidence/evidence_g1.json",
        work_plan_evidence_digest="sha256:fixture",
        target_active_model_identity_digest="sha256:fixture-model",
        target_identity_observed_at="2026-10-16T09:00:00Z",
    )
    monkeypatch.setattr(surfaces, "plan_canonical_goals",
        lambda *, tick_id: result)

    def forbidden_execute(*_args, **_kwargs):
        raise AssertionError("daemon planning feedback must never execute goals")

    monkeypatch.setattr(GoalExecutor, "execute_plan", forbidden_execute)
    feedback = surfaces.run_canonical_goal_planning(
        tick_id="2026-10-16T09:00:00+00:00")

    assert feedback["status"] == "planned"
    assert feedback["selected_goals"] == ["g1"]
    assert feedback["allocation_artifact_digest"] == "sha256:fixture-allocation"
    assert feedback["prior_epistemic_projection_digest"] == (
        "sha256:prior-projection")
    assert feedback["work_plan_id"] == "plan-g1"
    assert feedback["target_active_model_identity_digest"] == "sha256:fixture-model"
    assert feedback["target_identity_observed_at"] == "2026-10-16T09:00:00Z"
    assert feedback["execution_performed"] is False
    assert feedback["model_invoked"] is False
    assert feedback["authority"] is False
    assert surfaces.governance_feedback()["surfaces"][
        "canonical_goal_planning"] == feedback


def test_daemon_goal_feedback_reports_bounded_listing_omissions(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    kernel = ControlPlaneKernel(
        runtime_governor=RuntimeGovernor(),
        decisions_path=tmp_path / "decisions.jsonl",
    )
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path,
        runtime_state_root=tmp_path / "runtime",
        host_resource_runtime=HostResourceRuntimeCoordinator(
            kernel=kernel, runtime_state_root=tmp_path / "runtime"),
    )
    selected = tuple(f"selected-{index:02d}" for index in range(35))
    deferred = tuple(SimpleNamespace(goal_id=f"deferred-{index:02d}", reason="fixture")
        for index in range(41))
    allocation = AllocationDecision(
        selected=selected, deferred=deferred, selected_reasons=(),
        budget_summary={"risk_spent": 0, "risk_cap": 1,
            "throughput_spent": 0, "throughput_cap": 1},
    )
    plan = WorkPlan(1, "plan-bounded", "2026-10-16T09:00:00Z",
        "orchestrator_tick", selected, ())
    result = SimpleNamespace(
        allocation=allocation, allocation_artifact_path="glow/allocation.json",
        allocation_artifact_digest="sha256:fixture-allocation",
        work_plan=plan, work_plan_path="glow/forge/work_plans/plan.json",
        work_plan_evidence_path="glow/forge/work_plan_evidence/evidence.json",
        work_plan_evidence_digest="sha256:fixture",
        target_active_model_identity_digest=None,
        target_identity_observed_at=None,
    )
    monkeypatch.setattr(surfaces, "plan_canonical_goals",
        lambda *, tick_id: result)

    feedback = surfaces.run_canonical_goal_planning(
        tick_id="2026-10-16T09:00:00+00:00")

    assert feedback["selected_goals"] == list(selected[:32])
    assert feedback["selected_goal_count"] == 35
    assert feedback["omitted_selected_goal_count"] == 3
    assert feedback["target_active_model_identity_digest"] is None
    assert feedback["target_identity_observed_at"] is None
    assert feedback["deferred_goals"] == [
        {"goal_id": item.goal_id, "reason": item.reason} for item in deferred[:32]]
    assert feedback["deferred_goal_count"] == 41
    assert feedback["omitted_deferred_goal_count"] == 9
    assert feedback["goal_decision_listing_limit"] == 32
    assert feedback["allocation_artifact_path"] == "glow/allocation.json"
    assert feedback["allocation_artifact_digest"] == "sha256:fixture-allocation"
    assert feedback["execution_performed"] is False
    assert feedback["authority"] is False


def test_verified_prior_epistemic_position_changes_canonical_goal_allocation(
    tmp_path: Path, monkeypatch,
) -> None:
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    proposition = make_proposition(
        namespace="embodiment", subject="planning:fixture",
        predicate="candidate_requires_review", object_value={"goal_id": "g_experienced"},
        polarity="positive", qualifiers={"fixture": "plan-only"},
        temporal_scope={"kind": "bounded_planning_fixture"},
        context_scope={"fixture": "plan-only"}, proposition_class="predictive",
        statement="The historical position is scoped to one canonical goal.",
    )
    additional_proposition = make_proposition(
        namespace="embodiment", subject="planning:omitted-fixture",
        predicate="bounded_history_omitted", object_value={"goal_id": "g_omitted"},
        polarity="negative", qualifiers={"fixture": "plan-only-omission"},
        temporal_scope={"kind": "bounded_planning_fixture"},
        context_scope={"fixture": "plan-only-omission"},
        proposition_class="predictive",
        statement="This position may be omitted by the prior projection bound.",
    )
    proposition, omitted_proposition = sorted(
        (proposition, additional_proposition), key=lambda item: item.proposition_id)
    goal_graph = GoalGraph(schema_version=1, goals=(
        Goal("g_experienced", "history-scoped goal", 10.0, 100, (),
            "task:forge_propose", 1, 1,
            ("integrity", f"epistemic_proposition:{proposition.proposition_id}"), True),
        Goal("g_omitted", "omitted history goal", 8.0, 1, (),
            "task:forge_propose", 1, 1,
            ("integrity", f"epistemic_proposition:{omitted_proposition.proposition_id}"), True),
        Goal("g_baseline", "unscoped goal", 1.0, 1, (),
            "task:forge_propose", 1, 1, ("integrity",), True),
    ))
    persist_goal_graph(tmp_path, goal_graph)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))

    without_history = plan_goals(
        tmp_path, planning_time="2026-10-16T09:00:00+00:00")
    assert "g_experienced" in without_history.allocation.selected
    assert without_history.allocation.prior_epistemic_projection_digest is None
    assert without_history.allocation.prior_epistemic_projection_omitted_state_count is None

    owner = PersistentEpistemicStateOwner(
        tmp_path / "epistemic", allowed_namespaces=["embodiment"])
    owner.register_proposition(proposition)
    owner.register_proposition(omitted_proposition)
    owner.commit_update(
        proposition_id=proposition.proposition_id,
        expected_predecessor_digest=None, stance="unknown",
        reason="initialization", active_binding_ids=(),
        correlation_id="prior-review-position", tick=1,
        recorded_at="2026-10-16T08:00:00Z",
    )
    owner.commit_update(
        proposition_id=omitted_proposition.proposition_id,
        expected_predecessor_digest=None, stance="provisionally_contradicted",
        reason="initialization", active_binding_ids=(),
        correlation_id="prior-omitted-position", tick=2,
        recorded_at="2026-10-16T08:00:01Z",
    )
    state_before_planning = owner.current_state(proposition.proposition_id)
    omitted_state_before_planning = owner.current_state(omitted_proposition.proposition_id)
    assert state_before_planning is not None and omitted_state_before_planning is not None

    class ServingObserver:
        def __init__(self) -> None:
            self.calls = 0

        def observed_current_model_identity(self):
            self.calls += 1
            return {"provider": "fixture", "model": "current"}

        def current_session(self):
            raise AssertionError("planning must not acquire a serving session")

        def invoke(self, *_args, **_kwargs):
            raise AssertionError("planning must not invoke a model")

    observer = ServingObserver()

    def forbidden_execute(*_args, **_kwargs):
        raise AssertionError("canonical planning must not execute goals")

    monkeypatch.setattr(GoalExecutor, "execute_plan", forbidden_execute)
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path,
        epistemic_state_owner=owner,
        epistemic_state_config={
            "status": "configured", "cognitive_consumption_enabled": True,
            "max_cognitive_projection_count": 1,
        },
        resident_cognitive_invoker=observer,
    )
    with_history = surfaces.plan_canonical_goals(
        tick_id="2026-10-16T09:01:00+00:00")

    assert "g_experienced" not in with_history.allocation.selected
    assert "g_omitted" not in with_history.allocation.selected
    assert "g_baseline" in with_history.allocation.selected
    assert {item.goal_id: item.reason for item in with_history.allocation.deferred}[
        "g_experienced"] == "epistemic_review_required"
    assert {item.goal_id: item.reason for item in with_history.allocation.deferred}[
        "g_omitted"] == "epistemic_applicability_unresolved"
    assert with_history.work_plan is not None
    assert with_history.work_plan.selected_goals == ("g_baseline",)
    assert with_history.work_plan_evidence_path is not None
    evidence_path = tmp_path / with_history.work_plan_evidence_path
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    allocation_bytes = (tmp_path / with_history.allocation_artifact_path).read_bytes()
    expected_allocation_digest = "sha256:" + hashlib.sha256(allocation_bytes).hexdigest()
    assert with_history.allocation_artifact_digest == expected_allocation_digest
    assert evidence["plan_id"] == with_history.work_plan.plan_id
    assert evidence["plan_digest"] == with_history.work_plan.identity_digest()
    assert evidence["evidence_binding"]["planning_time"] == (
        with_history.work_plan.created_at)
    assert evidence["evidence_binding"]["goal_graph_hash"] == (
        with_history.goal_graph_hash)
    assert evidence["evidence_binding"]["allocation_artifact_path"] == (
        with_history.allocation_artifact_path)
    assert evidence["evidence_binding"]["allocation_artifact_digest"] == (
        with_history.allocation_artifact_digest)
    assert evidence["evidence_binding"]["risk_budget"]["router_k_max"] > 0
    assert evidence["evidence_binding"]["projection_digest"]
    assert with_history.allocation.prior_epistemic_projection_digest == (
        evidence["evidence_binding"]["projection_digest"])
    assert evidence["evidence_binding"]["projection_omission_manifest"][
        "omitted_state_count"] == 1
    assert with_history.allocation.prior_epistemic_projection_omitted_state_count == 1
    daemon_root = tmp_path / "daemon-plan"
    (daemon_root / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (daemon_root / "glow/contracts/ci_baseline.json").write_text(
        "{}\n", encoding="utf-8")
    persist_goal_graph(daemon_root, goal_graph)
    daemon_surfaces = RuntimeMaintenanceSurfaces(
        daemon_root,
        epistemic_state_owner=owner,
        epistemic_state_config={
            "status": "configured", "cognitive_consumption_enabled": True,
            "max_cognitive_projection_count": 1,
        },
        resident_cognitive_invoker=observer,
    )
    daemon_feedback = daemon_surfaces.run_canonical_goal_planning(
        tick_id="2026-10-16T09:02:00+00:00")
    daemon_evidence = json.loads((daemon_root / daemon_feedback[
        "work_plan_evidence_path"]).read_text(encoding="utf-8"))
    daemon_allocation_bytes = (daemon_root / daemon_feedback[
        "allocation_artifact_path"]).read_bytes()
    daemon_allocation_digest = "sha256:" + hashlib.sha256(
        daemon_allocation_bytes).hexdigest()
    assert daemon_feedback["allocation_artifact_digest"] == daemon_allocation_digest
    assert daemon_evidence["evidence_binding"][
        "allocation_artifact_digest"] == daemon_allocation_digest
    assert daemon_feedback["prior_epistemic_projection_digest"] == (
        daemon_evidence["evidence_binding"]["projection_digest"])
    assert daemon_feedback[
        "prior_epistemic_projection_omitted_state_count"] == (
            daemon_evidence["evidence_binding"][
                "projection_omission_manifest"]["omitted_state_count"])
    assert daemon_feedback["execution_performed"] is False
    assert daemon_feedback["authority"] is False
    assert evidence["evidence_binding"]["review_scopes"]
    assert evidence["evidence_binding"]["goal_applicability"]["g_experienced"] == (
        "epistemic_review_required")
    omission_manifest = evidence["evidence_binding"]["projection_omission_manifest"]
    assert omission_manifest["omitted_state_count"] == 1
    assert omission_manifest["omitted_state_identities"][0]["proposition_id"] == (
        omitted_proposition.proposition_id)
    assert omission_manifest["omitted_state_identities"][0]["state_digest"] == (
        omitted_state_before_planning.state_digest)
    assert evidence["evidence_binding"]["goal_applicability"]["g_omitted"] == (
        "epistemic_applicability_unresolved")
    assert {item["goal_id"]: item["reason"]
        for item in evidence["evidence_binding"]["deferred_goals"]} == {
            "g_experienced": "epistemic_review_required",
            "g_omitted": "epistemic_applicability_unresolved"}
    deferred_evidence = {item["goal_id"]: item["epistemic_positions"]
        for item in evidence["evidence_binding"]["deferred_goals"]}
    experienced_position = deferred_evidence["g_experienced"][0]
    experienced_scope = evidence["evidence_binding"]["review_scopes"][
        proposition.proposition_id]
    assert experienced_position["proposition_id"] == proposition.proposition_id
    assert experienced_position["identity"] == experienced_scope["position_identity"]
    assert experienced_position["posture"] == "review_required"
    omitted_position = deferred_evidence["g_omitted"][0]
    assert omitted_position["proposition_id"] == omitted_proposition.proposition_id
    assert omitted_position["omitted_state_identity"]["state_id"] == (
        omitted_state_before_planning.state_id)
    assert omitted_position["omitted_state_identity"]["state_digest"] == (
        omitted_state_before_planning.state_digest)
    allocation_artifact = json.loads((tmp_path /
        with_history.allocation_artifact_path).read_text(encoding="utf-8"))
    allocation_deferred = {item["goal_id"]: item["epistemic_positions"]
        for item in allocation_artifact["deferred_goals"]}
    assert allocation_deferred == deferred_evidence
    assert observer.calls == 2
    state_after_planning = owner.current_state(proposition.proposition_id)
    assert state_after_planning == state_before_planning
    assert owner.current_state(omitted_proposition.proposition_id) == (
        omitted_state_before_planning)

    reconstructed_owner = PersistentEpistemicStateOwner(
        tmp_path / "epistemic", allowed_namespaces=["embodiment"])
    assert reconstructed_owner.current_state(omitted_proposition.proposition_id) == (
        omitted_state_before_planning)
    complete_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, epistemic_state_owner=reconstructed_owner,
        epistemic_state_config={
            "status": "configured", "cognitive_consumption_enabled": True,
            "max_cognitive_projection_count": 2,
        },
        resident_cognitive_invoker=observer,
    )
    after_reconstruction = complete_surfaces.plan_canonical_goals(
        tick_id="2026-10-16T09:02:00+00:00")
    assert "g_omitted" not in after_reconstruction.allocation.selected
    assert (after_reconstruction.allocation
        .prior_epistemic_projection_omitted_state_count is None)
    assert {item.goal_id: item.reason for item in after_reconstruction.allocation.deferred}[
        "g_omitted"] == "epistemic_review_required"
    assert after_reconstruction.work_plan is not None
    assert after_reconstruction.work_plan_evidence_path is not None
    recovered_evidence = json.loads((tmp_path /
        after_reconstruction.work_plan_evidence_path).read_text(encoding="utf-8"))
    recovered_binding = recovered_evidence["evidence_binding"]
    assert "projection_omission_manifest" not in recovered_binding
    assert recovered_binding["projection_digest"] != evidence["evidence_binding"][
        "projection_digest"]
    recovered_scope = recovered_binding["review_scopes"][
        omitted_proposition.proposition_id]
    assert {key: value for key, value in recovered_scope.items()
        if key not in {"position_identity", "position_posture"}} == dict(
            omitted_proposition.context_scope)
    assert recovered_scope["position_posture"] == "review_required"
    assert recovered_scope.get("omitted_from_prior_projection") is not True
    recovered_identity = recovered_scope["position_identity"]
    assert recovered_identity["state_id"] == omitted_state_before_planning.state_id
    assert recovered_identity["state_digest"] == omitted_state_before_planning.state_digest
    assert recovered_identity["generation"] == omitted_state_before_planning.generation
    assert recovered_identity["update_event_id"] == (
        omitted_state_before_planning.last_update_event_id)
    assert recovered_binding["goal_applicability"]["g_omitted"] == (
        "epistemic_review_required")
    assert owner.current_state(omitted_proposition.proposition_id) == (
        omitted_state_before_planning)
    assert reconstructed_owner.current_state(omitted_proposition.proposition_id) == (
        omitted_state_before_planning)
    assert observer.calls == 3

    evidence_binding = dict(evidence["evidence_binding"])
    assert persist_work_plan_evidence(tmp_path, with_history.work_plan,
        evidence_binding) == (with_history.work_plan_evidence_path,
            with_history.work_plan_evidence_digest)
    allocation_path = tmp_path / with_history.allocation_artifact_path
    allocation_path.write_bytes(allocation_bytes + b"tampered")
    with pytest.raises(WorkPlanError,
            match="work_plan_allocation_artifact_digest_mismatch"):
        load_work_plan_evidence(tmp_path, with_history.work_plan)
    allocation_path.write_bytes(allocation_bytes)
    with pytest.raises(WorkPlanError, match="work_plan_evidence_identity_mismatch"):
        persist_work_plan_evidence(tmp_path, with_history.work_plan,
            {**evidence_binding, "selected_reasons": ["tampered"]})
    with pytest.raises(WorkPlanError, match="work_plan_evidence_identity_mismatch"):
        persist_work_plan_evidence(tmp_path, with_history.work_plan,
            {**evidence_binding, "allocation_artifact_digest": "sha256:invalid"})
    evidence["evidence_binding"]["selected_reasons"] = ["tampered"]
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    with pytest.raises(WorkPlanError, match="work_plan_evidence_identity_mismatch"):
        load_work_plan_evidence(tmp_path, with_history.work_plan)
    evidence["evidence_binding"] = evidence_binding
    evidence["evidence_digest"] = "0" * 64
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    with pytest.raises(WorkPlanError, match="work_plan_artifact_identity_conflict"):
        persist_work_plan_evidence(tmp_path, with_history.work_plan,
            evidence_binding)
    with pytest.raises(WorkPlanError, match="work_plan_evidence_digest_mismatch"):
        load_work_plan_evidence(tmp_path, with_history.work_plan)
    assert list((tmp_path / "glow/forge/work_runs").glob("run_*.json")) == []


def test_supported_prior_experience_enables_daemon_canonical_goal_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sentientos.local_model_authority import digest_payload
    from sentientos.persistent_epistemic_state import make_evidence_binding

    model_identity = {"provider": "fixture", "model": "developmental-model-v1"}
    identity_digest = "sha256:" + digest_payload(model_identity)
    proposition = make_proposition(
        namespace="embodiment", subject="task_family:integer_affine_prediction",
        predicate="heldout_episode_supported",
        object_value={"family": "integer_affine_prediction"}, polarity="positive",
        qualifiers={"fixture": "canonical-plan"},
        temporal_scope={"kind": "measured_episode"},
        context_scope={"task_family_id": "integer_affine_prediction",
            "active_model_identity_digest": identity_digest},
        proposition_class="causal_hypothesis",
        statement="A current measured episode supports this model-bound task family.")
    owner = PersistentEpistemicStateOwner(
        tmp_path / "epistemic", allowed_namespaces=["embodiment"])
    owner.register_proposition(proposition)
    support = make_evidence_binding(
        proposition_id=proposition.proposition_id,
        source_artifact_id="developmental-run:positive-current-episode",
        source_digest="sha256:" + "b" * 64,
        source_schema="sentientos.developmental_run:v1",
        source_class="deterministic_task_family_evaluation",
        observation_time="2026-10-16T08:00:00Z", evidence_relation="supports",
        dependency_kind="independently_sourced_observation", dependency_group=None,
        upstream_binding_ids=(), freshness="current", reliability_posture="supports")
    owner.bind_evidence(support)
    supported, event = owner.commit_update(
        proposition_id=proposition.proposition_id,
        expected_predecessor_digest=None, stance="supported", reason="new_evidence",
        active_binding_ids=(support.binding_id,), added_binding_ids=(support.binding_id,),
        correlation_id="positive-current-experience", tick=1,
        recorded_at="2026-10-16T08:00:00Z")
    recovered_owner = PersistentEpistemicStateOwner(
        tmp_path / "epistemic", allowed_namespaces=["embodiment"])
    graph = GoalGraph(schema_version=1, goals=(Goal(
        "g_experienced", "continue the measured task family", 3.0, 20, (),
        "rule", 1, 1,
        ("integrity", f"epistemic_proposition:{proposition.proposition_id}",
            "epistemic_task_family:integer_affine_prediction"), True),))
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    persist_goal_graph(tmp_path, graph)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))

    class ServingObserver:
        def __init__(self) -> None:
            self.identity_calls = 0
            self.current_identity = model_identity

        def observed_current_model_identity(self):
            self.identity_calls += 1
            return self.current_identity

        def current_session(self):
            raise AssertionError("planning must not acquire a serving session")

        def invoke(self, *_args, **_kwargs):
            raise AssertionError("planning must not invoke a model")

    observer = ServingObserver()

    def forbidden_execute(*_args, **_kwargs):
        raise AssertionError("canonical planning must not execute goals")

    monkeypatch.setattr(GoalExecutor, "execute_plan", forbidden_execute)
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, epistemic_state_owner=recovered_owner,
        epistemic_state_config={"status": "configured",
            "cognitive_consumption_enabled": True, "max_cognitive_projection_count": 1},
        resident_cognitive_invoker=observer)
    result = surfaces.plan_canonical_goals(tick_id="2026-10-16T09:00:00Z")

    assert result.work_plan is not None
    assert result.work_plan.selected_goals == ("g_experienced",)
    assert result.target_active_model_identity_digest == identity_digest
    assert result.target_identity_observed_at == "2026-10-16T09:00:00Z"
    assert result.work_plan_evidence_path is not None
    evidence = json.loads((tmp_path / result.work_plan_evidence_path).read_text(
        encoding="utf-8"))
    binding = evidence["evidence_binding"]
    scope = binding["review_scopes"][proposition.proposition_id]
    assert scope["position_posture"] == "verified_positive_current"
    assert scope["position_identity"]["state_id"] == supported.successor_state_id
    assert scope["position_identity"]["state_digest"] == supported.successor_state_digest
    assert scope["position_identity"]["update_event_id"] == event.event_id
    assert binding["goal_applicability"]["g_experienced"] is None
    assert result.allocation.selected_reasons[0]["epistemic_positions"][0][
        "posture"] == "verified_positive_current"
    assert observer.identity_calls == 1
    assert owner.current_state(proposition.proposition_id) == supported
    assert recovered_owner.current_state(proposition.proposition_id) == supported

    # A later planning tick observes a different serving model. Previously
    # supported experience stays visible as evidence but cannot select the goal.
    drifted_model_identity = {
        "provider": "fixture", "model": "developmental-model-v2"}
    observer.current_identity = drifted_model_identity
    drift_tick = "2026-10-16T10:00:00Z"
    drifted = surfaces.run_canonical_goal_planning(tick_id=drift_tick)
    assert drifted["status"] == "empty"
    assert drifted["work_plan_id"] is None
    assert drifted["selected_goals"] == []
    assert drifted["deferred_goals"] == [{
        "goal_id": "g_experienced",
        "reason": "epistemic_applicability_unresolved"}]
    assert drifted["target_active_model_identity_digest"] == (
        "sha256:" + digest_payload(drifted_model_identity))
    assert drifted["target_identity_observed_at"] == drift_tick
    assert drifted["execution_performed"] is False
    assert drifted["model_invoked"] is False
    assert drifted["authority"] is False
    drifted_allocation = json.loads((tmp_path / drifted[
        "allocation_artifact_path"]).read_text(encoding="utf-8"))
    drifted_allocation_bytes = (tmp_path / drifted[
        "allocation_artifact_path"]).read_bytes()
    drifted_allocation_digest = "sha256:" + hashlib.sha256(
        drifted_allocation_bytes).hexdigest()
    assert drifted["allocation_artifact_digest"] == drifted_allocation_digest
    assert drifted_allocation["selected_goals"] == []
    drifted_position = drifted_allocation["deferred_goals"][0][
        "epistemic_positions"][0]
    assert drifted_position["posture"] == "verified_positive_current"
    assert drifted_position["identity"]["state_id"] == supported.state_id
    assert drifted_allocation["deferred_goals"][0]["reason"] == (
        "epistemic_applicability_unresolved")
    assert observer.identity_calls == 2
    assert owner.current_state(proposition.proposition_id) == supported
    assert recovered_owner.current_state(proposition.proposition_id) == supported
    assert not list((tmp_path / "glow/forge/work_runs").glob("run_*.json"))


def test_receipt_verified_prior_state_changes_daemon_plan_only_after_recovery(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only receipt-verified durable experience may change a canonical plan."""
    from sentientos.codex_task_authority_admission import (
        AUTHORITY_DEFINITIONS, RESIDENT_EPISTEMIC_STATE_MUTATION,
        RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION,
    )
    from sentientos.persistent_epistemic_state import (
        EpistemicStateError, make_epistemic_update_candidate,
    )
    from sentientos.resident_epistemic_state_mutation import (
        PRINCIPAL, STATE_UPDATE_EFFECTS, ResidentEpistemicStateMutationController,
    )
    from sentientos.runtime_admission import (
        AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier,
    )

    proposition = make_proposition(
        namespace="embodiment", subject="planning:receipt-fixture",
        predicate="candidate_requires_review", object_value={"goal_id": "g_receipt"},
        polarity="positive", qualifiers={"fixture": "receipt-backed-plan"},
        temporal_scope={"kind": "bounded_planning_fixture"},
        context_scope={"goal_id": "g_receipt"}, proposition_class="predictive",
        statement="This prior position must be receipt-verified before planning.")
    graph = GoalGraph(schema_version=1, goals=(Goal(
        "g_receipt", "receipt-backed history goal", 5.0, 10, (),
        "task:forge_propose", 1, 1,
        ("integrity", f"epistemic_proposition:{proposition.proposition_id}"), True),))
    persist_goal_graph(tmp_path, graph)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\\n", encoding="utf-8")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))

    planning_time = "2026-10-16T09:00:00Z"
    without_history = plan_goals(tmp_path, planning_time=planning_time)
    assert without_history.allocation.selected == ("g_receipt",)

    owner = PersistentEpistemicStateOwner(
        tmp_path / "epistemic", allowed_namespaces=("embodiment",))
    owner.register_proposition(proposition)
    ledger = AdmissionLedger(tmp_path / "admissions.json")
    authority = RuntimeAdmissionAuthority(
        definitions=AUTHORITY_DEFINITIONS, ledger=ledger)
    receipt_root = tmp_path / "controller"
    controller = ResidentEpistemicStateMutationController(
        owner=owner,
        admission_verifier=RuntimeAdmissionVerifier(
            definitions=AUTHORITY_DEFINITIONS, ledger=ledger),
        current_sequence=lambda: 10, receipt_root=receipt_root)
    operation_id = "receipt-backed-plan-state"
    candidate = make_epistemic_update_candidate(
        proposition_id=proposition.proposition_id,
        predecessor_state_digest=None, proposed_stance="unknown",
        evidence_binding_ids=(), reason="initialization",
        rationale="receipt-backed canonical planning fixture",
        uncertainty="unknown", model_id="fixture")
    admission = authority.issue(
        admission_id="receipt-backed-plan-admission",
        capability_id=RESIDENT_EPISTEMIC_STATE_MUTATION, definition_version=1,
        subsystem_kind="epistemics", principal_id=PRINCIPAL,
        principal_kind=PRINCIPAL, effects=STATE_UPDATE_EFFECTS,
        subject_id=candidate.candidate_id,
        request_configuration_digest=controller.state_configuration_digest(
            candidate=candidate, operation_id=operation_id),
        provenance="test:receipt-backed-canonical-plan",
        issued_sequence=1, valid_through_sequence=20,
        affirmative_preconditions=(
            RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION.approval_requirements))
    receipt = controller.commit_update_candidate(
        candidate=candidate, admission=admission, operation_id=operation_id,
        correlation_id="receipt-backed-canonical-plan", tick=1,
        recorded_at="2026-10-16T08:00:00Z")
    assert receipt.storage_verified is True

    recovered_owner = PersistentEpistemicStateOwner(
        tmp_path / "epistemic", allowed_namespaces=("embodiment",))
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, epistemic_state_owner=recovered_owner,
        epistemic_state_config={"status": "configured",
            "cognitive_consumption_enabled": True,
            "max_cognitive_projection_count": 1})
    with pytest.raises(EpistemicStateError,
            match="epistemic_mutation_lineage_unverified"):
        surfaces.plan_canonical_goals(tick_id=planning_time)

    recovered_controller = ResidentEpistemicStateMutationController(
        owner=recovered_owner,
        admission_verifier=RuntimeAdmissionVerifier(
            definitions=AUTHORITY_DEFINITIONS, ledger=ledger),
        current_sequence=lambda: 10, receipt_root=receipt_root)
    assert recovered_controller.recovery_status["status"] == "verified"

    def forbidden_execute(*_args, **_kwargs):
        raise AssertionError("canonical planning must not execute goals")

    monkeypatch.setattr(GoalExecutor, "execute_plan", forbidden_execute)
    planned = surfaces.plan_canonical_goals(
        tick_id="2026-10-16T09:01:00Z")
    assert planned.allocation.selected == ()
    assert {item.goal_id: item.reason
        for item in planned.allocation.deferred}["g_receipt"] == (
            "epistemic_review_required")
    assert planned.work_plan is None
    assert recovered_owner.current_state(proposition.proposition_id) is not None


def test_receipt_verified_outcomes_change_canonical_goal_selection_after_recovery(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only admitted and recovered evidence can move a goal from review to selection."""
    from sentientos.codex_task_authority_admission import (
        AUTHORITY_DEFINITIONS, RESIDENT_EPISTEMIC_STATE_MUTATION,
        RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION,
    )
    from sentientos.local_model_authority import digest_payload
    from sentientos.persistent_epistemic_state import (
        make_epistemic_update_candidate,
        make_evidence_binding,
    )
    from sentientos.resident_epistemic_state_mutation import (
        PRINCIPAL, STATE_UPDATE_EFFECTS, ResidentEpistemicStateMutationController,
    )
    from sentientos.runtime_admission import (
        AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier,
    )

    model_identity = {"provider": "fixture", "model": "developmental-model-v1"}
    identity_digest = "sha256:" + digest_payload(model_identity)
    proposition = make_proposition(
        namespace="embodiment", subject="task_family:integer_affine_prediction",
        predicate="heldout_episode_outcome",
        object_value={"family": "integer_affine_prediction"}, polarity="positive",
        qualifiers={"fixture": "receipt-backed-outcome-planning"},
        temporal_scope={"kind": "measured_episode"},
        context_scope={"task_family_id": "integer_affine_prediction",
            "active_model_identity_digest": identity_digest},
        proposition_class="causal_hypothesis",
        statement="A measured episode outcome informs this model-bound task family.")
    graph = GoalGraph(schema_version=1, goals=(Goal(
        "g_outcome", "continue the measured family", 3.0, 20, (), "rule", 1, 1,
        ("integrity", f"epistemic_proposition:{proposition.proposition_id}",
            "epistemic_task_family:integer_affine_prediction"), True),))
    persist_goal_graph(tmp_path, graph)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))

    class ServingObserver:
        def __init__(self):
            self.identity = model_identity

        def observed_current_model_identity(self):
            return self.identity

        def current_session(self):
            raise AssertionError("planning must not acquire a serving session")

        def invoke(self, *_args, **_kwargs):
            raise AssertionError("planning must not invoke a model")

    def forbidden_execute(*_args, **_kwargs):
        raise AssertionError("canonical planning must not execute goals")

    monkeypatch.setattr(GoalExecutor, "execute_plan", forbidden_execute)
    observer = ServingObserver()
    owner = PersistentEpistemicStateOwner(
        tmp_path / "epistemic", allowed_namespaces=("embodiment",))
    owner.register_proposition(proposition)
    ledger = AdmissionLedger(tmp_path / "admissions.json")
    authority = RuntimeAdmissionAuthority(
        definitions=AUTHORITY_DEFINITIONS, ledger=ledger)
    receipt_root = tmp_path / "controller"
    controller = ResidentEpistemicStateMutationController(
        owner=owner,
        admission_verifier=RuntimeAdmissionVerifier(
            definitions=AUTHORITY_DEFINITIONS, ledger=ledger),
        current_sequence=lambda: 10, receipt_root=receipt_root)
    operation_number = 0

    def update(*, stance: str, binding_ids: tuple[str, ...],
            added_binding_ids: tuple[str, ...], tick: int, recorded_at: str):
        nonlocal operation_number
        operation_number += 1
        operation_id = f"outcome-planning-update-{operation_number}"
        previous = owner.current_state(proposition.proposition_id)
        candidate = make_epistemic_update_candidate(
            proposition_id=proposition.proposition_id,
            predecessor_state_digest=(previous.state_digest if previous else None),
            proposed_stance=stance, evidence_binding_ids=binding_ids,
            reason="initialization" if previous is None else "new_evidence",
            rationale="authority-bound measured outcome planning regression",
            uncertainty="unknown" if stance == "unknown" else "low", model_id="fixture")
        admission = authority.issue(
            admission_id=f"outcome-planning-admission-{operation_number}",
            capability_id=RESIDENT_EPISTEMIC_STATE_MUTATION, definition_version=1,
            subsystem_kind="epistemics", principal_id=PRINCIPAL,
            principal_kind=PRINCIPAL, effects=STATE_UPDATE_EFFECTS,
            subject_id=candidate.candidate_id,
            request_configuration_digest=controller.state_configuration_digest(
                candidate=candidate, operation_id=operation_id),
            provenance="test:receipt-backed-outcome-canonical-planning",
            issued_sequence=operation_number, valid_through_sequence=20,
            affirmative_preconditions=(
                RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION.approval_requirements))
        return controller.commit_update_candidate(
            candidate=candidate, admission=admission, operation_id=operation_id,
            correlation_id=operation_id, tick=tick, recorded_at=recorded_at)

    def recover_and_plan(tick_id: str):
        nonlocal owner, controller
        owner = PersistentEpistemicStateOwner(
            tmp_path / "epistemic", allowed_namespaces=("embodiment",))
        controller = ResidentEpistemicStateMutationController(
            owner=owner,
            admission_verifier=RuntimeAdmissionVerifier(
                definitions=AUTHORITY_DEFINITIONS, ledger=ledger),
            current_sequence=lambda: 10, receipt_root=receipt_root)
        assert controller.recovery_status["status"] == "verified"
        surfaces = RuntimeMaintenanceSurfaces(
            tmp_path, epistemic_state_owner=owner,
            epistemic_state_config={"status": "configured",
                "cognitive_consumption_enabled": True,
                "max_cognitive_projection_count": 1},
            resident_cognitive_invoker=observer)
        return surfaces.plan_canonical_goals(tick_id=tick_id)

    without_history = RuntimeMaintenanceSurfaces(
        tmp_path, epistemic_state_owner=owner,
        epistemic_state_config={"status": "configured",
            "cognitive_consumption_enabled": True,
            "max_cognitive_projection_count": 1},
        resident_cognitive_invoker=observer).plan_canonical_goals(
            tick_id="2026-10-16T09:00:00Z")
    assert without_history.allocation.selected == ("g_outcome",)

    update(stance="unknown", binding_ids=(), added_binding_ids=(), tick=1,
        recorded_at="2026-10-16T08:00:00Z")
    unknown = recover_and_plan("2026-10-16T09:01:00Z")
    assert unknown.work_plan is None
    assert {row.goal_id: row.reason for row in unknown.allocation.deferred} == {
        "g_outcome": "epistemic_review_required"}

    support = make_evidence_binding(
        proposition_id=proposition.proposition_id,
        source_artifact_id="developmental-run:positive-episode",
        source_digest="sha256:" + "b" * 64,
        source_schema="sentientos.developmental_run:v1",
        source_class="deterministic_task_family_evaluation",
        observation_time="2026-10-16T09:02:00Z", evidence_relation="supports",
        dependency_kind="independently_sourced_observation", dependency_group=None,
        upstream_binding_ids=(), freshness="current", reliability_posture="supports")
    owner.bind_evidence(support)
    supported = update(stance="supported", binding_ids=(support.binding_id,),
        added_binding_ids=(support.binding_id,), tick=2,
        recorded_at="2026-10-16T09:02:00Z")
    positive = recover_and_plan("2026-10-16T09:03:00Z")
    assert positive.work_plan is not None
    assert positive.work_plan.selected_goals == ("g_outcome",)
    assert positive.target_active_model_identity_digest == identity_digest
    assert positive.target_identity_observed_at == "2026-10-16T09:03:00Z"
    evidence = json.loads((tmp_path / positive.work_plan_evidence_path).read_text(
        encoding="utf-8"))
    scope = evidence["evidence_binding"]["review_scopes"][proposition.proposition_id]
    assert scope["position_posture"] == "verified_positive_current"
    assert scope["position_identity"]["state_id"] == supported.successor_state_id
    assert scope["position_identity"]["state_digest"] == supported.successor_state_digest
    assert scope["position_identity"]["update_event_id"] == supported.update_event_id
    assert scope["position_identity"]["supporting_binding_ids"] == [support.binding_id]

    # Retained support is model-bound: a different observed model cannot inherit
    # the previous model's successful outcome.
    observer.identity = {"provider": "fixture", "model": "developmental-model-v2"}
    cross_model = recover_and_plan("2026-10-16T09:03:30Z")
    assert cross_model.target_active_model_identity_digest == (
        "sha256:" + digest_payload(observer.identity))
    assert cross_model.work_plan is None
    assert {row.goal_id: row.reason for row in cross_model.allocation.deferred} == {
        "g_outcome": "epistemic_applicability_unresolved"}
    assert not list((tmp_path / "glow/forge/work_runs").glob("run_*.json"))
    observer.identity = model_identity

    adverse = make_evidence_binding(
        proposition_id=proposition.proposition_id,
        source_artifact_id="developmental-run:adverse-episode",
        source_digest="sha256:" + "c" * 64,
        source_schema="sentientos.developmental_run:v1",
        source_class="deterministic_task_family_evaluation",
        observation_time="2026-10-16T09:04:00Z", evidence_relation="contradicts",
        dependency_kind="independently_sourced_observation", dependency_group=None,
        upstream_binding_ids=(), freshness="current", reliability_posture="contradicts")
    owner.bind_evidence(adverse)
    contradicted = update(stance="contradicted",
        binding_ids=(support.binding_id, adverse.binding_id),
        added_binding_ids=(adverse.binding_id,), tick=3,
        recorded_at="2026-10-16T09:04:00Z")
    negative = recover_and_plan("2026-10-16T09:05:00Z")
    assert negative.work_plan is None
    assert {row.goal_id: row.reason for row in negative.allocation.deferred} == {
        "g_outcome": "epistemic_review_required"}
    allocation_artifact = json.loads((tmp_path / negative.allocation_artifact_path).read_text(
        encoding="utf-8"))
    negative_position = allocation_artifact["deferred_goals"][0]["epistemic_positions"][0]
    assert negative_position["posture"] == "review_required"
    assert negative_position["identity"]["state_id"] == contradicted.successor_state_id
    assert negative_position["identity"]["contradicting_binding_ids"] == [
        adverse.binding_id]
    assert not list((tmp_path / "glow/forge/work_runs").glob("run_*.json"))

