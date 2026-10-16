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
from sentientos.goal_executor import GoalExecutor, GoalPlanner
from sentientos.goal_graph import Goal, GoalGraph, persist_goal_graph
from sentientos.orchestrator import (GoalPlanningResult,
    _emit_goal_allocation_artifact, plan_goals)
from sentientos.persistent_epistemic_state import (PersistentEpistemicStateOwner,
    make_proposition)
from sentientos.runtime_governor import RuntimeGovernor
from sentientos.work_allocator import AllocationDecision
from sentientos.work_plan import (WorkPlanError, load_work_plan_evidence,
    WorkPlan, persist_work_plan_evidence)
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
