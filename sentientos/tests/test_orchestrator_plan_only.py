from __future__ import annotations

from datetime import datetime
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
    _emit_goal_allocation_artifact, _latest_verified_prior_plan,
    _plan_goal_work, plan_goals)
from sentientos.persistent_epistemic_state import (PersistentEpistemicStateOwner,
    make_proposition)
from sentientos.runtime_governor import RuntimeGovernor
from sentientos.work_allocator import AllocationDecision
from sentientos.work_plan import (WorkPlanError, load_work_plan_evidence,
    TaskRun, WorkPlan, WorkPlanRun, persist_work_plan,
    persist_work_plan_evidence, persist_work_run, work_run_id)
from sentientos.work_plan_execution_journal import WorkPlanExecutionJournal
from sentientos.risk_budget import RiskBudget
from sentientosd import HostResourceRuntimeCoordinator, RuntimeMaintenanceSurfaces

pytestmark = pytest.mark.no_legacy_skip


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
    artifact = tmp_path / path
    original = artifact.read_bytes()

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
        summary={"status": "failed", "evidence_digest": prior_evidence_digest})

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
def test_daemon_planning_binds_verified_owner_and_observed_identity_without_execution(
    tmp_path: Path, monkeypatch,
) -> None:
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")
    persist_goal_graph(
        tmp_path,
        GoalGraph(schema_version=1, goals=(
            Goal("g1", "diagnostic", 1.0, 5, (), "task:forge_propose", 1, 1,
                ("integrity",), True),
        )),
    )

    class ProjectionOwner:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int | None]] = []

        def cognitive_projection(self, *, max_states: int,
                                 current_tick: int | None = None):
            self.calls.append((max_states, current_tick))
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
    assert owner.calls == [(7, int(datetime.fromisoformat(tick_id).timestamp()))]
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
    )
    plan = WorkPlan(1, "plan-g1", "2026-10-16T09:00:00Z",
        "orchestrator_tick", ("g1",), ())
    result = SimpleNamespace(
        allocation=allocation, allocation_artifact_path="glow/allocation.json",
        work_plan=plan, work_plan_path="glow/forge/work_plans/plan_g1.json",
        work_plan_evidence_path="glow/forge/work_plan_evidence/evidence_g1.json",
        work_plan_evidence_digest="sha256:fixture",
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
    assert feedback["work_plan_id"] == "plan-g1"
    assert feedback["execution_performed"] is False
    assert feedback["model_invoked"] is False
    assert feedback["authority"] is False
    assert surfaces.governance_feedback()["surfaces"][
        "canonical_goal_planning"] == feedback


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
    persist_goal_graph(tmp_path, GoalGraph(schema_version=1, goals=(
        Goal("g_experienced", "history-scoped goal", 10.0, 100, (),
            "task:forge_propose", 1, 1,
            ("integrity", f"epistemic_proposition:{proposition.proposition_id}"), True),
        Goal("g_omitted", "omitted history goal", 8.0, 1, (),
            "task:forge_propose", 1, 1,
            ("integrity", f"epistemic_proposition:{omitted_proposition.proposition_id}"), True),
        Goal("g_baseline", "unscoped goal", 1.0, 1, (),
            "task:forge_propose", 1, 1, ("integrity",), True),
    )))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))

    without_history = plan_goals(
        tmp_path, planning_time="2026-10-16T09:00:00+00:00")
    assert "g_experienced" in without_history.allocation.selected

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
    assert evidence["plan_id"] == with_history.work_plan.plan_id
    assert evidence["plan_digest"] == with_history.work_plan.identity_digest()
    assert evidence["evidence_binding"]["planning_time"] == (
        with_history.work_plan.created_at)
    assert evidence["evidence_binding"]["goal_graph_hash"] == (
        with_history.goal_graph_hash)
    assert evidence["evidence_binding"]["allocation_artifact_path"] == (
        with_history.allocation_artifact_path)
    assert evidence["evidence_binding"]["risk_budget"]["router_k_max"] > 0
    assert evidence["evidence_binding"]["projection_digest"]
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
    assert observer.calls == 1
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
    assert observer.calls == 2

    evidence_binding = dict(evidence["evidence_binding"])
    assert persist_work_plan_evidence(tmp_path, with_history.work_plan,
        evidence_binding) == (with_history.work_plan_evidence_path,
            with_history.work_plan_evidence_digest)
    with pytest.raises(WorkPlanError, match="work_plan_evidence_identity_mismatch"):
        persist_work_plan_evidence(tmp_path, with_history.work_plan,
            {**evidence_binding, "selected_reasons": ["tampered"]})
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
