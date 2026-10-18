from pathlib import Path

from sentientos.epistemic_planning import (
    epistemic_review_reason_for_goal,
    review_required_applicability,
)


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
