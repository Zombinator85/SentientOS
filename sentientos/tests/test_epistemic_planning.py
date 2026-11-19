from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sentientos.epistemic_planning import (
    epistemic_review_reason_for_goal,
    review_required_applicability,
)


def test_resident_epistemic_evaluation_clock_requires_known_timezone() -> None:
    from sentientos.resident_developmental_cognition import (
        ResidentDevelopmentalCognitionOwner,
    )

    owner = object.__new__(ResidentDevelopmentalCognitionOwner)
    owner.clock = lambda: datetime(2026, 11, 18, 10, 0,
        tzinfo=timezone(timedelta(hours=-5)))
    assert owner._current_epistemic_evaluation_time() == (
        "2026-11-18T15:00:00Z")

    owner.clock = lambda: datetime(2026, 11, 18, 10, 0)
    assert owner._current_epistemic_evaluation_time() is None


def test_resident_tick_captures_one_epistemic_evaluation_time() -> None:
    from contextlib import nullcontext
    from types import SimpleNamespace

    from sentientos.resident_developmental_cognition import (
        ResidentDevelopmentalCognitionOwner,
    )

    owner = object.__new__(ResidentDevelopmentalCognitionOwner)
    owner.config = SimpleNamespace(enabled=True)
    clock_reads = []
    clock_values = iter((
        datetime(2026, 11, 18, 10, 4, 59, tzinfo=timezone.utc),
        datetime(2026, 11, 18, 10, 5, 1, tzinfo=timezone.utc),
    ))

    def clock() -> datetime:
        clock_reads.append(True)
        return next(clock_values)

    owner.clock = clock
    owner._composition_lock = lambda: nullcontext()
    owner._run_tick_locked = lambda **kwargs: kwargs
    captured = owner._run_tick(snapshot=SimpleNamespace(snapshot_id="snapshot"),
        tick_id="tick", prior_self_model=None, prior_epistemic_state=object(),
        objective_task=None, objective_only=False, objective_request_id=None,
        objective_request_digest=None)
    assert len(clock_reads) == 1
    assert captured["epistemic_evaluation_time"] == "2026-11-18T10:04:59Z"


def test_task_family_review_requires_exact_model_applicability() -> None:
    proposition_id = "p-1"
    identity_digest = "sha256:" + "a" * 64
    review_scopes = {proposition_id: {
        "task_family_id": "integer_affine_prediction",
        "active_model_identity_digest": identity_digest,
    }}

    def reason(identity: str | None, observed_at: str | None = "tick-1") -> str | None:
        tags = ["epistemic_proposition:p-1",
            "epistemic_task_family:integer_affine_prediction"]
        if identity is not None:
            tags.append(f"epistemic_active_model_identity_digest:{identity}")
        return epistemic_review_reason_for_goal(tags, review_scopes,
            target_active_model_identity_digest=identity,
            target_identity_observed_at=observed_at, planning_time="tick-1")

    assert reason(identity_digest) == "epistemic_review_required"
    assert reason(None) == "epistemic_applicability_unresolved"
    assert reason("sha256:" + "b" * 64) == "epistemic_applicability_unresolved"
    assert reason(identity_digest, "stale-tick") == "epistemic_applicability_unresolved"
    assert epistemic_review_reason_for_goal(
        ("epistemic_proposition:p-1", "epistemic_task_family:other_family",
            f"epistemic_active_model_identity_digest:{identity_digest}"),
        review_scopes) == "epistemic_applicability_unresolved"


@pytest.mark.parametrize(("relation_kind", "tagged_index"), [
    ("contradicts", 0), ("supersedes", 1),
])
def test_projected_relations_change_tagged_goal_review_decision(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        relation_kind: str, tagged_index: int) -> None:
    from types import SimpleNamespace

    from sentientos.goal_graph import Goal, GoalGraph
    from sentientos.persistent_epistemic_state import (
        PersistentEpistemicStateOwner, PropositionRelation,
        make_evidence_binding, make_proposition,
    )
    from sentientos.risk_budget import RiskBudget
    from sentientos.work_allocator import allocate_goals
    from sentientos.work_plan import WorkPlan
    from sentientosd import RuntimeMaintenanceSurfaces

    owner = PersistentEpistemicStateOwner(
        tmp_path / "epistemic", allowed_namespaces=("embodiment",))
    propositions = [make_proposition(namespace="embodiment",
        subject="sensor:planning", predicate="reports_condition",
        object_value=value, polarity="positive", qualifiers={},
        temporal_scope={"window": "prior"}, context_scope={},
        proposition_class="environmental") for value in ("stable", "degraded")]
    for index, proposition in enumerate(propositions, start=1):
        owner.register_proposition(proposition)
        binding = make_evidence_binding(
            proposition_id=proposition.proposition_id,
            source_artifact_id=f"planning-observation:{index}",
            source_digest="sha256:" + str(index) * 64,
            source_schema="sentientos.test_observation:v1",
            source_class="independent_fixture",
            observation_time=f"2026-10-16T08:0{index}:00Z",
            evidence_relation="supports",
            dependency_kind="independently_sourced_observation",
            dependency_group=None, upstream_binding_ids=(),
            freshness="current", reliability_posture="supports")
        owner.bind_evidence(binding)
        owner.commit_update(proposition_id=proposition.proposition_id,
            expected_predecessor_digest=None, stance="supported",
            reason="initialization", active_binding_ids=(binding.binding_id,),
            added_binding_ids=(binding.binding_id,),
            correlation_id=f"planning-initialize:{index}", tick=index,
            recorded_at=f"2026-10-16T08:0{index}:00Z")

    tagged = propositions[tagged_index]
    goal = Goal("apply-tagged-epistemic-position",
        "apply the prior sensor position", 2.0, 10, (), "rule", 1, 1,
        (f"epistemic_proposition:{tagged.proposition_id}",), True)
    graph = GoalGraph(schema_version=1, goals=(goal,))
    budget = RiskBudget(router_k_max=1, router_m_max=1)

    def allocate():
        projection = owner.cognitive_projection(max_states=2, current_tick=4,
            prioritized_proposition_ids=(tagged.proposition_id,))
        assert projection is not None
        return allocate_goals(graph=graph, budget=budget,
            operating_mode="normal", integrity_pressure_level=0,
            quarantine_active=False, posture="balanced",
            prior_epistemic_projection=projection)

    baseline = allocate()
    assert baseline.selected == (goal.goal_id,)

    owner.add_relation(PropositionRelation(
        source_proposition_id=propositions[0].proposition_id,
        target_proposition_id=propositions[1].proposition_id,
        relation=relation_kind, recorded_at="2026-10-16T08:03:00Z"))
    reviewed = allocate()
    assert reviewed.selected == ()
    [deferred] = reviewed.deferred
    assert deferred.reason == "epistemic_review_required"
    [position] = deferred.epistemic_positions
    assert position["proposition_id"] == tagged.proposition_id
    assert position["posture"] == "review_required"
    assert len(position["relation_review_digests"]) == 1
    reviewed_projection = owner.cognitive_projection(max_states=2,
        current_tick=4, prioritized_proposition_ids=(tagged.proposition_id,))
    assert reviewed_projection is not None
    _, review_scopes = review_required_applicability(reviewed_projection)
    assert review_scopes[tagged.proposition_id]["position_posture"] == (
        "review_required")
    assert len(review_scopes[tagged.proposition_id][
        "relation_review_digests"]) == 1

    # Carry the actual relation-driven deferral through the daemon feedback
    # serializer, which is what later maintenance consumers observe.
    surfaces = RuntimeMaintenanceSurfaces(tmp_path / "daemon")
    plan = WorkPlan(1, "relation-review-plan", "2026-10-16T08:04:00Z",
        "relation-review-fixture", (), ())
    result = SimpleNamespace(
        allocation=reviewed,
        allocation_artifact_path="glow/allocations/relation.json",
        allocation_artifact_digest="sha256:" + "c" * 64,
        work_plan=plan,
        work_plan_path="glow/forge/work_plans/relation.json",
        work_plan_evidence_path="glow/forge/work_plan_evidence/relation.json",
        work_plan_evidence_digest="sha256:" + "d" * 64,
        target_active_model_identity_digest=None,
        target_identity_observed_at=None,
    )
    monkeypatch.setattr(surfaces, "plan_canonical_goals",
        lambda *, tick_id: result)
    feedback = surfaces.run_canonical_goal_planning(
        tick_id="2026-10-16T08:04:00+00:00")
    [deferred_feedback] = feedback["deferred_goals"]
    assert deferred_feedback["goal_id"] == goal.goal_id
    [position_feedback] = deferred_feedback["epistemic_positions"]
    assert position_feedback["proposition_id"] == tagged.proposition_id
    assert position_feedback["relation_review_digests"] == (
        position["relation_review_digests"])
    assert feedback["execution_performed"] is False
    assert feedback["model_invoked"] is False
    assert feedback["authority"] is False


def test_cited_unverified_correction_defers_goal_without_revising_state(
        tmp_path: Path) -> None:
    from sentientos.goal_graph import Goal, GoalGraph
    from sentientos.persistent_epistemic_state import (
        MAX_COGNITIVE_PROJECTION_UNVERIFIED_CONTEXT_BINDINGS_PER_STATE,
        PersistentEpistemicStateOwner, make_evidence_binding,
        make_proposition, semantic_packets_for_projection,
    )
    from sentientos.risk_budget import RiskBudget
    from sentientos.work_allocator import allocate_goals

    owner = PersistentEpistemicStateOwner(
        tmp_path / "epistemic", allowed_namespaces=("embodiment",))
    proposition = make_proposition(namespace="embodiment",
        subject="sensor:correction-review", predicate="reports_condition",
        object_value="stable", polarity="positive", qualifiers={},
        temporal_scope={"window": "prior"}, context_scope={},
        proposition_class="environmental")
    owner.register_proposition(proposition)
    support = make_evidence_binding(
        proposition_id=proposition.proposition_id,
        source_artifact_id="observation:correction-review-baseline",
        source_digest="sha256:" + "a" * 64,
        source_schema="sentientos.test_observation:v1",
        source_class="independent_fixture",
        observation_time="2026-11-18T10:00:00Z",
        evidence_relation="supports",
        dependency_kind="independently_sourced_observation",
        dependency_group=None, upstream_binding_ids=(), freshness="current",
        reliability_posture="supports")
    owner.bind_evidence(support)
    original_state, _ = owner.commit_update(
        proposition_id=proposition.proposition_id,
        expected_predecessor_digest=None, stance="supported",
        reason="initialization", active_binding_ids=(support.binding_id,),
        added_binding_ids=(support.binding_id,),
        correlation_id="correction-review-baseline", tick=1,
        recorded_at="2026-11-18T10:00:00Z")

    goal = Goal("apply-cited-position", "apply prior sensor position", 2.0,
        10, (), "rule", 1, 1,
        (f"epistemic_proposition:{proposition.proposition_id}",), True)
    graph = GoalGraph(schema_version=1, goals=(goal,))
    budget = RiskBudget(router_k_max=1, router_m_max=1)

    def allocate():
        projection = owner.cognitive_projection(max_states=1, current_tick=2,
            prioritized_proposition_ids=(proposition.proposition_id,),
            relevance_query="sensor condition correction review")
        assert projection is not None
        return projection, allocate_goals(graph=graph, budget=budget,
            operating_mode="normal", integrity_pressure_level=0,
            quarantine_active=False, posture="balanced",
            prior_epistemic_projection=projection)

    baseline_projection, baseline = allocate()
    assert baseline.selected == (goal.goal_id,)
    baseline_state = baseline_projection.states[0]

    correction = make_evidence_binding(
        proposition_id=proposition.proposition_id,
        source_artifact_id="operator-feedback:correction-review",
        source_digest="sha256:" + "b" * 64,
        source_schema="sentientos.local_operator_feedback:v5",
        source_class="operator_input",
        observation_time="2026-11-18T10:01:00Z",
        evidence_relation="contextualizes",
        dependency_kind="unknown_dependency", dependency_group=None,
        upstream_binding_ids=(), freshness="unknown",
        reliability_posture="operator_assertion_unverified_context_only",
        unverified_context_text="The prior sensor condition may be wrong.")
    owner.bind_evidence(correction)

    corrected_projection, corrected = allocate()
    assert corrected_projection.states[0] == baseline_state
    assert corrected_projection.state_ids == baseline_projection.state_ids
    assert corrected.selected == ()
    [deferred] = corrected.deferred
    assert deferred.reason == "epistemic_review_required"
    [position] = deferred.epistemic_positions
    assert position["posture"] == "review_required"
    assert position["unverified_correction_binding_ids"] == [
        correction.binding_id]
    [packet] = semantic_packets_for_projection(corrected_projection)
    assert position["unverified_context_selection_provenance"] == packet[
        "unverified_context_selection_provenance"]
    assert original_state.state_digest == corrected_projection.states[0][
        "state_digest"]
    assert original_state.generation == corrected_projection.states[0][
        "generation"]

    # Context pressure must not erase the review signal when the original
    # correction is among the bounded, omitted context records.
    for index in range(
            MAX_COGNITIVE_PROJECTION_UNVERIFIED_CONTEXT_BINDINGS_PER_STATE):
        owner.bind_evidence(make_evidence_binding(
            proposition_id=proposition.proposition_id,
            source_artifact_id=f"operator-feedback:correction-review-{index}",
            source_digest=f"{index + 1:064x}",
            source_schema="sentientos.local_operator_feedback:v5",
            source_class="operator_input",
            observation_time=f"2026-11-18T10:{index + 2:02d}:00Z",
            evidence_relation="contextualizes",
            dependency_kind="unknown_dependency", dependency_group=None,
            upstream_binding_ids=(), freshness="unknown",
            reliability_posture="operator_assertion_unverified_context_only",
            unverified_context_text=f"Additional correction context {index}."))

    bounded_projection, bounded = allocate()
    assert bounded_projection.states[0]["state_digest"] == original_state.state_digest
    assert bounded_projection.states[0]["generation"] == original_state.generation
    assert bounded.selected == ()
    [bounded_deferred] = bounded.deferred
    [bounded_position] = bounded_deferred.epistemic_positions
    assert bounded_deferred.reason == "epistemic_review_required"
    assert bounded_position["omitted_unverified_correction_context"]["count"] == 1
    assert bounded_position["omitted_unverified_correction_context"][
        "identity_digest"].startswith("sha256:")
    [bounded_packet] = semantic_packets_for_projection(bounded_projection)
    assert bounded_position["unverified_context_selection_provenance"] == bounded_packet[
        "unverified_context_selection_provenance"]


def test_expired_scoped_evidence_defers_only_its_goal_until_fresh_support(
        tmp_path: Path) -> None:
    from sentientos.goal_graph import Goal, GoalGraph
    from sentientos.persistent_epistemic_state import (
        PersistentEpistemicStateOwner,
        make_evidence_binding,
        make_proposition,
    )
    from sentientos.risk_budget import RiskBudget
    from sentientos.work_allocator import allocate_goals

    owner = PersistentEpistemicStateOwner(
        tmp_path / "epistemic", allowed_namespaces=("embodiment",))
    bounded = make_proposition(namespace="embodiment",
        subject="sensor:bounded-freshness", predicate="reports_condition",
        object_value="stable", polarity="positive", qualifiers={},
        temporal_scope={"window": "current", "max_evidence_age_seconds": 300},
        context_scope={}, proposition_class="environmental")
    unrelated = make_proposition(namespace="embodiment",
        subject="sensor:unrelated-freshness", predicate="reports_condition",
        object_value="stable", polarity="positive", qualifiers={},
        temporal_scope={"window": "current"}, context_scope={},
        proposition_class="environmental")
    goals = GoalGraph(schema_version=1, goals=(
        Goal("use-bounded-position", "use bounded sensor position", 2.0,
            10, (), "rule", 1, 1,
            (f"epistemic_proposition:{bounded.proposition_id}",), True),
        Goal("use-unrelated-position", "use unrelated sensor position", 1.0,
            5, (), "rule", 1, 1,
            (f"epistemic_proposition:{unrelated.proposition_id}",), True),
    ))
    evidence_by_proposition = {}
    for index, proposition in enumerate((bounded, unrelated), start=1):
        owner.register_proposition(proposition)
        evidence = make_evidence_binding(
            proposition_id=proposition.proposition_id,
            source_artifact_id=f"observation:freshness-baseline-{index}",
            source_digest="sha256:" + str(index) * 64,
            source_schema="sentientos.test_observation:v1",
            source_class="independent_fixture",
            observation_time="2026-11-18T10:00:00Z",
            evidence_relation="supports",
            dependency_kind="independently_sourced_observation",
            dependency_group=f"sensor-{index}",
            upstream_binding_ids=(), freshness="current",
            reliability_posture="supports")
        owner.bind_evidence(evidence)
        owner.commit_update(proposition_id=proposition.proposition_id,
            expected_predecessor_digest=None, stance="supported",
            reason="initialization", active_binding_ids=(evidence.binding_id,),
            added_binding_ids=(evidence.binding_id,),
            correlation_id=f"freshness-baseline-{index}", tick=1,
            recorded_at="2026-11-18T10:00:00Z")
        evidence_by_proposition[proposition.proposition_id] = evidence

    budget = RiskBudget(router_k_max=2, router_m_max=2)

    def allocate(*, current_tick: int, planning_time: str | None):
        projection = owner.cognitive_projection(max_states=2,
            current_tick=current_tick,
            prioritized_proposition_ids=tuple(sorted(
                (bounded.proposition_id, unrelated.proposition_id))))
        assert projection is not None
        return allocate_goals(graph=goals, budget=budget,
            operating_mode="normal", integrity_pressure_level=0,
            quarantine_active=False, posture="balanced",
            prior_epistemic_projection=projection,
            planning_time=planning_time)

    within_limit = allocate(current_tick=2,
        planning_time="2026-11-18T10:04:59Z")
    assert set(within_limit.selected) == {
        "use-bounded-position", "use-unrelated-position"}

    unevaluated = allocate(current_tick=2, planning_time=None)
    assert unevaluated.selected == ("use-unrelated-position",)
    [unevaluated_deferred] = [item for item in unevaluated.deferred
        if item.goal_id == "use-bounded-position"]
    [unevaluated_position] = unevaluated_deferred.epistemic_positions
    assert unevaluated_position["temporal_freshness_review"]["status"] == (
        "unresolved")

    expired = allocate(current_tick=2,
        planning_time="2026-11-18T10:05:01Z")
    assert expired.selected == ("use-unrelated-position",)
    [deferred] = [item for item in expired.deferred
        if item.goal_id == "use-bounded-position"]
    assert deferred.reason == "epistemic_review_required"
    [position] = deferred.epistemic_positions
    review = position["temporal_freshness_review"]
    assert review["status"] == "expired"
    assert review["reason"] == "supporting_evidence_exceeded_maximum_age"
    assert review["max_evidence_age_seconds"] == 300
    assert review["age_seconds"] == 301
    assert review["latest_support_binding_id"] == (
        evidence_by_proposition[bounded.proposition_id].binding_id)
    original_state = owner.current_state(bounded.proposition_id)
    assert original_state is not None and original_state.generation == 0

    from sentientos.goal_planner import ExecutorState, GoalPlanner
    projection = owner.cognitive_projection(max_states=2, current_tick=2,
        prioritized_proposition_ids=tuple(sorted((
            bounded.proposition_id, unrelated.proposition_id))))
    assert projection is not None
    draft = GoalPlanner(repo_root=tmp_path).build_plan_with_evidence(
        expired, ExecutorState(repo_root=tmp_path,
            created_at="2026-11-18T10:05:01Z", context="freshness review",
            operating_mode="normal", quarantine_active=False,
            allow_mutation=True, goal_graph_hash="abcd" * 16,
            allocation_id="freshness-allocation", risk_budget=budget,
            prior_epistemic_projection=projection), goals)
    [plan_review] = [item for item in draft.evidence_binding["deferred_goals"]
        if item["goal_id"] == "use-bounded-position"]
    [plan_position] = plan_review["epistemic_positions"]
    assert plan_position["temporal_freshness_review"] == review

    from sentientos.resident_developmental_cognition import (
        _bind_history_and_epistemic_context,
    )
    probe_context = {
        "instruction": "Use prior epistemic context carefully.",
        "epistemic_revision_probe": {
            "response_contract": "sentientos.epistemic_revision_answer:v2",
            "question": "Which evidence remains current?",
        },
    }
    within_context, _, _, _, _ = _bind_history_and_epistemic_context(
        context=probe_context,
        records=(), projection=projection, history_present=False,
        evaluation_time="2026-11-18T10:04:59Z")
    [within_context_review] = within_context["prior_epistemic_state"][
        "temporal_freshness_reviews"]
    assert within_context_review["review"]["status"] == "within_limit"
    within_allowlist = set(within_context["epistemic_revision_probe"][
        "allowed_evidence_binding_ids"])
    assert (evidence_by_proposition[bounded.proposition_id].binding_id
        in within_allowlist)
    assert evidence_by_proposition[unrelated.proposition_id].binding_id in (
        within_allowlist)
    bound_context, context_metadata, prompt, _, _ = (
        _bind_history_and_epistemic_context(
        context=probe_context,
        records=(), projection=projection, history_present=False,
        evaluation_time="2026-11-18T10:05:01Z"))
    [context_review] = bound_context["prior_epistemic_state"][
        "temporal_freshness_reviews"]
    assert context_review["proposition_id"] == bounded.proposition_id
    assert context_review["packet_digest"]
    assert context_review["review"] == review
    assert context_review["excluded_supporting_binding_ids"] == [
        evidence_by_proposition[bounded.proposition_id].binding_id]
    expired_allowlist = set(bound_context["epistemic_revision_probe"][
        "allowed_evidence_binding_ids"])
    assert evidence_by_proposition[bounded.proposition_id].binding_id not in (
        expired_allowlist)
    assert evidence_by_proposition[unrelated.proposition_id].binding_id in (
        expired_allowlist)
    assert context_metadata["epistemic_temporal_freshness_reviews"] == [
        context_review]
    assert "historical context only" in prompt
    assert unrelated.proposition_id not in {
        item["proposition_id"] for item in
        bound_context["prior_epistemic_state"]["temporal_freshness_reviews"]}

    unresolved_context, _, _, _, _ = _bind_history_and_epistemic_context(
        context=probe_context, records=(), projection=projection,
        history_present=False, evaluation_time=None)
    unresolved_allowlist = set(unresolved_context["epistemic_revision_probe"][
        "allowed_evidence_binding_ids"])
    assert evidence_by_proposition[bounded.proposition_id].binding_id not in (
        unresolved_allowlist)
    assert evidence_by_proposition[unrelated.proposition_id].binding_id in (
        unresolved_allowlist)

    fresh = make_evidence_binding(
        proposition_id=bounded.proposition_id,
        source_artifact_id="observation:freshness-refresh",
        source_digest="sha256:" + "f" * 64,
        source_schema="sentientos.test_observation:v1",
        source_class="independent_fixture",
        observation_time="2026-11-18T10:05:30Z",
        evidence_relation="supports",
        dependency_kind="independently_sourced_observation",
        dependency_group="sensor-refresh",
        upstream_binding_ids=(), freshness="current",
        reliability_posture="supports")
    owner.bind_evidence(fresh)
    owner.commit_update(proposition_id=bounded.proposition_id,
        expected_predecessor_digest=original_state.state_digest,
        stance="supported",
        reason="new_evidence",
        active_binding_ids=tuple(sorted((
            evidence_by_proposition[bounded.proposition_id].binding_id,
            fresh.binding_id))),
        added_binding_ids=(fresh.binding_id,),
        correlation_id="freshness-refresh", tick=2,
        recorded_at="2026-11-18T10:05:30Z")
    refreshed = allocate(current_tick=3,
        planning_time="2026-11-18T10:06:00Z")
    assert set(refreshed.selected) == {
        "use-bounded-position", "use-unrelated-position"}
    refreshed_projection = owner.cognitive_projection(max_states=2,
        current_tick=3, prioritized_proposition_ids=tuple(sorted((
            bounded.proposition_id, unrelated.proposition_id))))
    assert refreshed_projection is not None
    refreshed_context, _, _, _, _ = _bind_history_and_epistemic_context(
        context=probe_context, records=(), projection=refreshed_projection,
        history_present=False, evaluation_time="2026-11-18T10:06:00Z")
    [refreshed_review] = refreshed_context["prior_epistemic_state"][
        "temporal_freshness_reviews"]
    assert refreshed_review["review"]["status"] == "within_limit"
    assert refreshed_review["excluded_supporting_binding_ids"] == [
        evidence_by_proposition[bounded.proposition_id].binding_id]
    refreshed_allowlist = set(refreshed_context["epistemic_revision_probe"][
        "allowed_evidence_binding_ids"])
    assert evidence_by_proposition[bounded.proposition_id].binding_id not in (
        refreshed_allowlist)
    assert fresh.binding_id in refreshed_allowlist


def test_supported_model_bound_position_requires_exact_identity_and_reaches_plan_evidence(
    tmp_path: Path,
) -> None:
    from sentientos.goal_graph import Goal, GoalGraph
    from sentientos.goal_planner import ExecutorState, GoalPlanner
    from sentientos.persistent_epistemic_state import (
        PersistentEpistemicStateOwner,
        make_evidence_binding,
        make_proposition,
    )
    from sentientos.risk_budget import RiskBudget
    from sentientos.work_allocator import allocate_goals

    proposition = make_proposition(
        namespace="embodiment",
        subject="task_family:integer_affine_prediction",
        predicate="heldout_episode_supported",
        object_value={"family": "integer_affine_prediction"},
        polarity="positive",
        qualifiers={},
        temporal_scope={"kind": "measured_episode"},
        context_scope={
            "task_family_id": "integer_affine_prediction",
            "active_model_identity_digest": "sha256:" + "a" * 64,
        },
        proposition_class="causal_hypothesis",
        statement="A measured held-out episode supports this model-bound family.",
    )
    owner = PersistentEpistemicStateOwner(
        tmp_path / "epistemic", allowed_namespaces=("embodiment",))
    owner.register_proposition(proposition)
    support = make_evidence_binding(
        proposition_id=proposition.proposition_id,
        source_artifact_id="developmental-run:positive-episode",
        source_digest="sha256:" + "b" * 64,
        source_schema="sentientos.developmental_run:v1",
        source_class="deterministic_task_family_evaluation",
        observation_time="2026-10-16T08:00:00Z",
        evidence_relation="supports",
        dependency_kind="independently_sourced_observation",
        dependency_group=None,
        upstream_binding_ids=(),
        freshness="current",
        reliability_posture="supports",
    )
    owner.bind_evidence(support)
    supported, event = owner.commit_update(
        proposition_id=proposition.proposition_id,
        expected_predecessor_digest=None,
        stance="supported",
        reason="new_evidence",
        active_binding_ids=(support.binding_id,),
        added_binding_ids=(support.binding_id,),
        correlation_id="positive-model-bound-episode",
        tick=1,
        recorded_at="2026-10-16T08:00:00Z",
    )
    recovered = PersistentEpistemicStateOwner(
        tmp_path / "epistemic", allowed_namespaces=("embodiment",))
    projection = recovered.cognitive_projection(max_states=1, current_tick=2)
    assert projection is not None
    _, scopes = review_required_applicability(projection)
    scope = scopes[proposition.proposition_id]
    identity = scope["position_identity"]
    assert identity == {
        "schema_version": "sentientos.epistemic_review_position_identity:v1",
        "state_id": supported.state_id,
        "state_digest": supported.state_digest,
        "generation": supported.generation,
        "update_event_id": event.event_id,
        "supporting_binding_ids": [support.binding_id],
        "contradicting_binding_ids": [],
    }
    assert scope["position_posture"] == "verified_positive_current"

    goal = Goal(
        "history-sensitive", "continue the measured family", 2.0, 10, (),
        "rule", 1, 1,
        (
            f"epistemic_proposition:{proposition.proposition_id}",
            "epistemic_task_family:integer_affine_prediction",
        ),
        True,
    )
    graph = GoalGraph(schema_version=1, goals=(goal,))
    budget = RiskBudget(router_k_max=1, router_m_max=1)

    def allocate(identity_digest: str, observed_at: str):
        return allocate_goals(
            graph=graph,
            budget=budget,
            operating_mode="normal",
            integrity_pressure_level=0,
            quarantine_active=False,
            posture="balanced",
            prior_epistemic_projection=projection,
            target_active_model_identity_digest=identity_digest,
            target_identity_observed_at=observed_at,
            planning_time="tick-2",
        )

    matching = allocate("sha256:" + "a" * 64, "tick-2")
    assert matching.selected == (goal.goal_id,)
    selected_position = matching.selected_reasons[0]["epistemic_positions"][0]
    assert selected_position["proposition_id"] == proposition.proposition_id
    assert selected_position["identity"] == identity
    assert selected_position["posture"] == "verified_positive_current"
    changed_model = allocate("sha256:" + "c" * 64, "tick-2")
    assert changed_model.selected == ()
    assert {row.goal_id: row.reason for row in changed_model.deferred} == {
        goal.goal_id: "epistemic_applicability_unresolved"}
    deferred_position = changed_model.deferred[0].epistemic_positions[0]
    assert deferred_position["identity"] == identity
    assert deferred_position["posture"] == "verified_positive_current"

    draft = GoalPlanner(repo_root=tmp_path).build_plan_with_evidence(
        matching,
        ExecutorState(
            repo_root=tmp_path,
            created_at="tick-2",
            context="reconstructed_positive_episode",
            operating_mode="normal",
            quarantine_active=False,
            allow_mutation=True,
            goal_graph_hash="a" * 64,
            allocation_id="allocation:positive-episode",
            risk_budget=budget,
            prior_epistemic_projection=projection,
            target_active_model_identity_digest="sha256:" + "a" * 64,
            target_identity_observed_at="tick-2",
        ),
        graph,
    )
    bound_scope = draft.evidence_binding["review_scopes"][proposition.proposition_id]
    assert bound_scope["position_identity"] == identity
    assert draft.evidence_binding["selected_reasons"][0][
        "epistemic_positions"][0]["identity"] == identity
    assert draft.evidence_binding["goal_applicability"][goal.goal_id] is None

    spoofed = make_proposition(
        namespace="embodiment",
        subject="task_family:adverse_history_spoof",
        predicate="heldout_episode_contradicted",
        object_value={"family": "integer_affine_prediction"},
        polarity="negative",
        qualifiers={},
        temporal_scope={"kind": "measured_episode"},
        context_scope={
            "task_family_id": "integer_affine_prediction",
            "active_model_identity_digest": "sha256:" + "a" * 64,
            "position_posture": "verified_positive_current",
        },
        proposition_class="causal_hypothesis",
        statement="A measured held-out episode contradicts this model-bound family.",
    )
    adverse_owner = PersistentEpistemicStateOwner(
        tmp_path / "adverse-epistemic", allowed_namespaces=("embodiment",))
    adverse_owner.register_proposition(spoofed)
    contradiction = make_evidence_binding(
        proposition_id=spoofed.proposition_id,
        source_artifact_id="developmental-run:adverse-episode",
        source_digest="sha256:" + "d" * 64,
        source_schema="sentientos.developmental_run:v1",
        source_class="deterministic_task_family_evaluation",
        observation_time="2026-10-16T08:01:00Z",
        evidence_relation="contradicts",
        dependency_kind="independently_sourced_observation",
        dependency_group=None,
        upstream_binding_ids=(),
        freshness="current",
        reliability_posture="contradicts",
    )
    adverse_owner.bind_evidence(contradiction)
    adverse_owner.commit_update(
        proposition_id=spoofed.proposition_id,
        expected_predecessor_digest=None,
        stance="provisionally_contradicted",
        reason="initialization",
        active_binding_ids=(contradiction.binding_id,),
        added_binding_ids=(contradiction.binding_id,),
        correlation_id="adverse-model-bound-episode",
        tick=1,
        recorded_at="2026-10-16T08:01:00Z",
    )
    adverse_projection = adverse_owner.cognitive_projection(max_states=1, current_tick=2)
    assert adverse_projection is not None
    _, adverse_scopes = review_required_applicability(adverse_projection)
    assert adverse_scopes[spoofed.proposition_id]["position_posture"] == "review_required"
    assert epistemic_review_reason_for_goal(
        (
            f"epistemic_proposition:{spoofed.proposition_id}",
            "epistemic_task_family:integer_affine_prediction",
        ),
        adverse_scopes,
        target_active_model_identity_digest="sha256:" + "a" * 64,
        target_identity_observed_at="tick-2",
        planning_time="tick-2",
    ) == "epistemic_review_required"

    # A positive position must not short-circuit review of a second tagged
    # position. The result is independent of the bounded projection's order.
    positive_scope = scopes[proposition.proposition_id]
    mixed_positive_first = {
        proposition.proposition_id: positive_scope,
        spoofed.proposition_id: adverse_scopes[spoofed.proposition_id],
    }
    mixed_adverse_first = dict(reversed(tuple(mixed_positive_first.items())))
    mixed_tags = (
        f"epistemic_proposition:{proposition.proposition_id}",
        f"epistemic_proposition:{spoofed.proposition_id}",
        "epistemic_task_family:integer_affine_prediction",
    )
    review_kwargs = {
        "target_active_model_identity_digest": "sha256:" + "a" * 64,
        "target_identity_observed_at": "tick-2",
        "planning_time": "tick-2",
    }
    assert epistemic_review_reason_for_goal(
        mixed_tags, mixed_positive_first, **review_kwargs
    ) == "epistemic_review_required"
    assert epistemic_review_reason_for_goal(
        mixed_tags, mixed_adverse_first, **review_kwargs
    ) == "epistemic_review_required"

    omitted = {
        "p-omitted": {
            "omitted_from_prior_projection": True,
            "omitted_state_identity": {"proposition_id": "p-omitted"},
        },
        proposition.proposition_id: positive_scope,
    }
    assert epistemic_review_reason_for_goal(
        (
            f"epistemic_proposition:{proposition.proposition_id}",
            "epistemic_proposition:p-omitted",
            "epistemic_task_family:integer_affine_prediction",
        ),
        omitted,
        **review_kwargs,
    ) == "epistemic_applicability_unresolved"
