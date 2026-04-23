import json
import inspect
from pathlib import Path

from codex.orchestrator import StrategyOrchestrator
from codex.strategy import CodexStrategy, StrategyPlan, configure_strategy_root
from integration_memory import configure_integration_root
from sentientos import scoped_lifecycle_diagnostic
from sentientos.orchestration_intent_fabric import (
    resolve_current_orchestration_handoff_acceptance_posture,
    resolve_current_orchestration_export_packet_consumer_receipt,
    resolve_current_orchestration_next_move_brief,
    resolve_current_re_evaluation_basis_brief,
)


def _strategy(
    strategy_id: str,
    *,
    goal: str,
    channels: list[str],
    horizon: float,
    priority: float,
) -> CodexStrategy:
    return CodexStrategy(
        strategy_id=strategy_id,
        goal=goal,
        status="active",
        plan_chain=[
            StrategyPlan(
                plan_id=f"{strategy_id}-plan",
                title="stabilize",
                branches=[],
            )
        ],
        metadata={
            "channels": channels,
            "horizon": horizon,
            "priority": priority,
        },
    )


def test_orchestrator_detects_conflicts_and_resolution(tmp_path: Path) -> None:
    integration_root = tmp_path / "integration"
    configure_integration_root(integration_root)
    configure_strategy_root(integration_root)

    orchestrator = StrategyOrchestrator(integration_root)
    first = _strategy(
        "vision-stability",
        goal="Stabilize embodiment vision channel",
        channels=["embodiment:vision"],
        horizon=4,
        priority=0.7,
    )
    second = _strategy(
        "vision-boost",
        goal="Boost embodiment vision clarity",
        channels=["embodiment:vision"],
        horizon=5,
        priority=0.68,
    )

    orchestrator.track_strategy(first)
    orchestrator.track_strategy(second)
    conflicts = orchestrator.scan()

    assert conflicts, "Expected a conflict to be detected"
    conflict = conflicts[0]
    assert "resource" in conflict.classes
    assert conflict.proposed_resolution == "merge"

    active_path = integration_root / "strategies" / "active.jsonl"
    assert active_path.exists()
    lines = [line for line in active_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 2

    conflict_files = list((tmp_path / "pulse" / "conflicts").glob("*.json"))
    assert conflict_files, "Conflicts should be logged to /pulse/conflicts"


def test_orchestrator_sequences_and_escalates(tmp_path: Path) -> None:
    integration_root = tmp_path / "integration"
    configure_integration_root(integration_root)
    configure_strategy_root(integration_root)

    orchestrator = StrategyOrchestrator(integration_root)
    long_horizon = _strategy(
        "cooling-long",
        goal="Sustain thermal drift mitigation",
        channels=["daemon:cooling"],
        horizon=9,
        priority=0.55,
    )
    short_horizon = _strategy(
        "cooling-short",
        goal="Immediate cooling pulse",
        channels=["daemon:cooling"],
        horizon=1,
        priority=0.52,
    )
    orchestrator.track_strategy(long_horizon)
    orchestrator.track_strategy(short_horizon)

    high_priority = _strategy(
        "narrative-emergency",
        goal="Narrative crisis escalation",
        channels=["daemon:narrative"],
        horizon=2,
        priority=0.95,
    )
    low_priority = _strategy(
        "narrative-sustain",
        goal="Narrative stability assurance",
        channels=["daemon:narrative"],
        horizon=2,
        priority=0.2,
    )
    orchestrator.track_strategy(high_priority)
    orchestrator.track_strategy(low_priority)

    conflicts = orchestrator.scan()
    assert len(conflicts) >= 2
    by_pair = {tuple(conflict.strategies): conflict for conflict in conflicts}

    cooling_key = tuple(sorted(["cooling-long", "cooling-short"]))
    narrative_key = tuple(sorted(["narrative-emergency", "narrative-sustain"]))

    cooling_conflict = by_pair[(cooling_key[0], cooling_key[1])]
    assert "temporal" in cooling_conflict.classes
    assert cooling_conflict.proposed_resolution == "sequence"

    narrative_conflict = by_pair[(narrative_key[0], narrative_key[1])]
    assert "priority" in narrative_conflict.classes
    assert narrative_conflict.proposed_resolution == "escalate"


def test_dashboard_and_operator_override(tmp_path: Path) -> None:
    integration_root = tmp_path / "integration"
    configure_integration_root(integration_root)
    configure_strategy_root(integration_root)

    orchestrator = StrategyOrchestrator(integration_root)
    alpha = _strategy(
        "relay-alpha",
        goal="Relay anomaly suppression",
        channels=["channel:relay"],
        horizon=3,
        priority=0.45,
    )
    beta = _strategy(
        "relay-beta",
        goal="Relay optimization",
        channels=["channel:relay"],
        horizon=4,
        priority=0.42,
    )

    orchestrator.track_strategy(alpha)
    orchestrator.track_strategy(beta)
    conflicts = orchestrator.scan()
    conflict = conflicts[0]

    snapshot = orchestrator.dashboard_snapshot()
    assert snapshot["active"], "Active strategies should appear on the dashboard"
    assert snapshot["conflicts"], "Conflicts should appear on the dashboard"

    orchestrator.apply_decision(
        conflict.conflict_id,
        decision="override",
        operator="warden",
        new_resolution="sequence",
        rationale="Queue after inspection",
    )

    updated = orchestrator.dashboard_snapshot()
    dashboard_conflict = updated["conflicts"][0]
    assert dashboard_conflict["resolution"] == "sequence"
    assert dashboard_conflict["status"] == "operator_override"

    log_path = integration_root / "orchestration_log.jsonl"
    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    assert any(entry["action"] == "operator_decision" for entry in entries)

    # Adaptive preference after operator override
    orchestrator.resolve_strategy("relay-alpha")
    orchestrator.resolve_strategy("relay-beta")

    gamma = _strategy(
        "relay-gamma",
        goal="Relay audit",
        channels=["channel:relay"],
        horizon=3,
        priority=0.4,
    )
    delta = _strategy(
        "relay-delta",
        goal="Relay stabilizer",
        channels=["channel:relay"],
        horizon=5,
        priority=0.43,
    )
    orchestrator.track_strategy(gamma)
    orchestrator.track_strategy(delta)
    learned_conflict = orchestrator.scan()[0]
    assert learned_conflict.proposed_resolution == "sequence"
    assert learned_conflict.metadata.get("origin") in {"heuristic", "learned"}

    orchestrator.apply_decision(
        learned_conflict.conflict_id,
        decision="quarantine",
        operator="warden",
        target_strategy="relay-delta",
        rationale="Hold delta until audit",
    )
    refreshed = orchestrator.dashboard_snapshot()
    active = {item["strategy_id"]: item for item in refreshed["active"]}
    assert active["relay-delta"]["metadata"]["quarantined"] is True


def _resolve_basis(
    tmp_path: Path,
    *,
    watchpoint_class: str,
    satisfaction_status: str,
    recommendation: str,
    expected_actor: str = "orchestration_body",
    resolution_path: str = "none",
    operator_influence_state: str = "no_operator_influence_yet",
    readiness_verdict: str = "ready_to_proceed",
    wait_kind: str = "awaiting_internal_result_closure",
    pressure_classification: str = "stable_or_low_pressure",
    wake_classification: str = "wake_ready",
    wake_posture: str = "informational_only",
    resume_ready: bool = True,
) -> dict[str, object]:
    return resolve_current_re_evaluation_basis_brief(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "state-1",
            "current_resolution_path": resolution_path,
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "watch-1",
            "watchpoint_class": watchpoint_class,
        },
        watchpoint_satisfaction={
            "watchpoint_satisfaction_id": "sat-1",
            "satisfaction_status": satisfaction_status,
        },
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-1",
            "recommendation": recommendation,
            "expected_actor": expected_actor,
        },
        current_orchestration_resumption_candidate={
            "orchestration_resumption_candidate_id": "cand-1",
            "resumption_candidate_class": "resumption_candidate" if resume_ready else "no_resume_candidate",
            "resume_ready": resume_ready,
        },
        current_resumed_operation_readiness={
            "resumed_operation_readiness_verdict": readiness_verdict,
        },
        current_orchestration_watchpoint_brief={
            "wait_kind": wait_kind,
        },
        current_orchestration_pressure_signal={
            "pressure_classification": pressure_classification,
        },
        current_orchestration_wake_readiness_detector={
            "wake_readiness_classification": wake_classification,
            "result_posture": wake_posture,
        },
        operator_resolution_influence={
            "operator_influence_state": operator_influence_state,
        },
        unified_result={
            "resolution_path": resolution_path,
        },
    )


def _resolve_next_move(
    tmp_path: Path,
    *,
    watchpoint_class: str,
    satisfaction_status: str,
    recommendation: str,
    basis_classification: str,
    readiness_verdict: str = "ready_to_proceed",
    wake_classification: str = "wake_ready",
    pressure_classification: str = "stable_or_low_pressure",
    wait_kind: str = "awaiting_internal_result_closure",
    active_packet_available: bool = False,
    operator_influence_state: str = "no_operator_influence_yet",
) -> dict[str, object]:
    return resolve_current_orchestration_next_move_brief(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "state-1",
            "current_resolution_path": "none",
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "watch-1",
            "watchpoint_class": watchpoint_class,
        },
        watchpoint_satisfaction={
            "watchpoint_satisfaction_id": "sat-1",
            "satisfaction_status": satisfaction_status,
        },
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-1",
            "recommendation": recommendation,
            "expected_actor": "orchestration_body",
        },
        current_re_evaluation_basis_brief={
            "basis_classification": basis_classification,
        },
        current_orchestration_resumption_candidate={
            "orchestration_resumption_candidate_id": "cand-1",
            "resume_ready": True,
        },
        current_resumed_operation_readiness={
            "resumed_operation_readiness_verdict": readiness_verdict,
        },
        current_orchestration_wake_readiness_detector={
            "wake_readiness_classification": wake_classification,
            "result_posture": "informational_only",
        },
        current_orchestration_watchpoint_brief={
            "wait_kind": wait_kind,
        },
        current_orchestration_pressure_signal={
            "pressure_classification": pressure_classification,
        },
        active_packet_visibility={
            "active_packet_available": active_packet_available,
        },
        current_proposal={
            "proposal_id": "proposal-1",
        },
        operator_resolution_influence={
            "operator_influence_state": operator_influence_state,
        },
        unified_result={
            "resolution_path": "none",
        },
    )


def test_current_re_evaluation_basis_brief_classifications(tmp_path: Path) -> None:
    satisfaction = _resolve_basis(
        tmp_path,
        watchpoint_class="await_new_proposal",
        satisfaction_status="watchpoint_satisfied",
        recommendation="rerun_delegated_judgment",
    )
    assert satisfaction["basis_classification"] == "satisfaction_driven_re_evaluation"

    operator = _resolve_basis(
        tmp_path,
        watchpoint_class="await_operator_resolution",
        satisfaction_status="watchpoint_satisfied",
        recommendation="rerun_packet_synthesis",
        operator_influence_state="operator_resolution_applied",
    )
    assert operator["basis_classification"] == "operator_resolution_driven_re_evaluation"

    internal = _resolve_basis(
        tmp_path,
        watchpoint_class="await_internal_execution_result",
        satisfaction_status="watchpoint_satisfied",
        recommendation="rerun_delegated_judgment",
        resolution_path="internal_execution",
    )
    assert internal["basis_classification"] == "internal_result_driven_re_evaluation"

    external = _resolve_basis(
        tmp_path,
        watchpoint_class="await_external_fulfillment_receipt",
        satisfaction_status="watchpoint_satisfied",
        recommendation="rerun_delegated_judgment",
        resolution_path="external_fulfillment",
    )
    assert external["basis_classification"] == "external_fulfillment_driven_re_evaluation"

    continuity = _resolve_basis(
        tmp_path,
        watchpoint_class="await_new_proposal",
        satisfaction_status="watchpoint_stale",
        recommendation="hold_for_manual_review",
        wait_kind="continuity_uncertain",
        pressure_classification="fragmentation_pressure",
        wake_classification="wake_blocked_by_fragmentation",
        wake_posture="strongly_blocked",
        readiness_verdict="hold_for_operator_review",
        resume_ready=False,
    )
    assert continuity["basis_classification"] == "continuity_uncertainty_driven_re_evaluation"
    assert continuity["posture"] == "conservative_wake_or_re_entry_posture"

    no_basis = _resolve_basis(
        tmp_path,
        watchpoint_class="no_watchpoint_needed",
        satisfaction_status="no_active_watchpoint",
        recommendation="no_re_evaluation_needed",
        resume_ready=False,
        readiness_verdict="not_ready",
    )
    assert no_basis["basis_classification"] == "no_current_re_evaluation_basis"


def test_current_re_evaluation_basis_brief_is_non_authoritative(tmp_path: Path) -> None:
    brief = _resolve_basis(
        tmp_path,
        watchpoint_class="await_new_proposal",
        satisfaction_status="watchpoint_satisfied",
        recommendation="rerun_delegated_judgment",
    )
    boundaries = brief.get("boundaries", {})
    assert boundaries.get("non_authoritative") is True
    assert boundaries.get("non_executing") is True
    assert boundaries.get("does_not_execute_or_route_work") is True
    assert brief.get("decision_power") == "none"
    assert brief.get("basis", {}).get("historical_honesty", {}).get("derived_from_existing_surfaces_only") is True


def test_current_re_evaluation_basis_brief_surface_is_in_scoped_lifecycle_diagnostic() -> None:
    source = inspect.getsource(scoped_lifecycle_diagnostic.build_scoped_lifecycle_diagnostic)
    assert "current_re_evaluation_basis_brief" in source


def test_current_orchestration_next_move_brief_classifications(tmp_path: Path) -> None:
    delegated = _resolve_next_move(
        tmp_path,
        watchpoint_class="await_new_proposal",
        satisfaction_status="watchpoint_satisfied",
        recommendation="rerun_delegated_judgment",
        basis_classification="satisfaction_driven_re_evaluation",
    )
    assert delegated["next_move_classification"] == "rerun_delegated_judgment_next"

    gate = _resolve_next_move(
        tmp_path,
        watchpoint_class="await_operator_resolution",
        satisfaction_status="watchpoint_satisfied",
        recommendation="rerun_packetization_gate",
        basis_classification="operator_resolution_driven_re_evaluation",
        operator_influence_state="operator_resolution_applied",
    )
    assert gate["next_move_classification"] == "rerun_packetization_gate_next"

    synthesis = _resolve_next_move(
        tmp_path,
        watchpoint_class="await_operator_resolution",
        satisfaction_status="watchpoint_satisfied",
        recommendation="rerun_packet_synthesis",
        basis_classification="operator_resolution_driven_re_evaluation",
        operator_influence_state="operator_resolution_applied",
    )
    assert synthesis["next_move_classification"] == "rerun_packet_synthesis_next"

    continue_packet = _resolve_next_move(
        tmp_path,
        watchpoint_class="await_internal_execution_result",
        satisfaction_status="watchpoint_satisfied",
        recommendation="clear_wait_and_continue_current_packet",
        basis_classification="satisfaction_driven_re_evaluation",
        active_packet_available=True,
    )
    assert continue_packet["next_move_classification"] == "continue_current_packet_next"
    assert continue_packet["continues_existing_packet"] is True

    hold = _resolve_next_move(
        tmp_path,
        watchpoint_class="await_operator_resolution",
        satisfaction_status="watchpoint_pending",
        recommendation="hold_for_manual_review",
        basis_classification="continuity_uncertainty_driven_re_evaluation",
        readiness_verdict="hold_for_operator_review",
        wake_classification="wake_blocked_pending_operator",
        pressure_classification="hold_pressure",
        wait_kind="awaiting_operator_resolution",
    )
    assert hold["next_move_classification"] == "hold_for_operator_review_next"
    assert hold["next_move_posture"] == "blocked"

    no_next = _resolve_next_move(
        tmp_path,
        watchpoint_class="no_watchpoint_needed",
        satisfaction_status="no_active_watchpoint",
        recommendation="no_re_evaluation_needed",
        basis_classification="no_current_re_evaluation_basis",
        readiness_verdict="not_ready",
        wake_classification="wake_not_applicable",
    )
    assert no_next["next_move_classification"] == "no_current_next_move"


def test_current_orchestration_next_move_brief_is_derived_and_non_authoritative(tmp_path: Path) -> None:
    brief = _resolve_next_move(
        tmp_path,
        watchpoint_class="await_new_proposal",
        satisfaction_status="watchpoint_satisfied",
        recommendation="rerun_delegated_judgment",
        basis_classification="satisfaction_driven_re_evaluation",
    )
    assert brief.get("decision_power") == "none"
    boundaries = brief.get("boundaries", {})
    assert boundaries.get("non_authoritative") is True
    assert boundaries.get("non_executing") is True
    assert boundaries.get("does_not_execute_or_route_work") is True
    assert brief.get("basis", {}).get("historical_honesty", {}).get("derived_from_existing_surfaces_only") is True


def test_current_orchestration_next_move_brief_surface_is_in_scoped_lifecycle_diagnostic() -> None:
    source = inspect.getsource(scoped_lifecycle_diagnostic.build_scoped_lifecycle_diagnostic)
    assert "current_orchestration_next_move_brief" in source


def _resolve_export_packet_consumer_receipt(
    tmp_path: Path,
    *,
    export_packet_classification: str,
    export_packet_maturity_posture: str,
    export_packet_suitable: bool = True,
    digest_classification: str = "mature_current_picture",
    coherence_classification: str = "coherent_current_picture",
    transition_classification: str = "poised_for_resumed_progress",
    closure_classification: str = "closure_pending_on_internal_result",
    next_move_classification: str = "continue_current_packet_next",
    handoff_classification: str = "packet_ready_for_continuation",
    operator_loop_posture: str = "informational",
    path_classification: str = "path_following_current_watchpoint",
    pressure_classification: str = "stable_or_low_pressure",
    resumed_readiness_verdict: str = "ready_to_proceed",
    wake_classification: str = "wake_ready",
    include_basis: bool = True,
) -> dict[str, object]:
    export_packet: dict[str, object] = {
        "current_orchestration_export_packet_id": "oep-test-1",
        "export_packet_classification": export_packet_classification,
        "export_packet_maturity_posture": export_packet_maturity_posture,
        "suitable_for_bounded_downstream_inspection": export_packet_suitable,
    }
    if include_basis:
        export_packet["basis"] = {"basis_evidence": {"current_orchestration_state_id": "state-1"}}
    return resolve_current_orchestration_export_packet_consumer_receipt(
        tmp_path,
        current_orchestration_export_packet=export_packet,
        current_orchestration_digest={"digest_classification": digest_classification},
        current_orchestration_coherence_brief={"coherence_classification": coherence_classification},
        current_orchestration_transition_brief={"transition_classification": transition_classification},
        current_orchestration_closure_brief={"closure_classification": closure_classification},
        current_orchestration_next_move_brief={"next_move_classification": next_move_classification},
        current_orchestration_handoff_packet_brief={"handoff_packet_brief_classification": handoff_classification},
        current_operator_facing_orchestration_brief={"loop_posture": operator_loop_posture},
        current_orchestration_resolution_path_brief={"resolution_path_classification": path_classification},
        current_orchestration_pressure_signal={"pressure_classification": pressure_classification},
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": resumed_readiness_verdict},
        current_orchestration_wake_readiness_detector={"wake_readiness_classification": wake_classification},
    )


def test_current_orchestration_export_packet_consumer_receipt_classifications(tmp_path: Path) -> None:
    structurally_consumable = _resolve_export_packet_consumer_receipt(
        tmp_path,
        export_packet_classification="export_packet_ready",
        export_packet_maturity_posture="mature",
    )
    assert structurally_consumable["receipt_classification"] == "receipt_structurally_consumable"

    cautionary = _resolve_export_packet_consumer_receipt(
        tmp_path,
        export_packet_classification="export_packet_cautionary",
        export_packet_maturity_posture="cautionary",
        operator_loop_posture="cautionary",
        wake_classification="wake_ready_with_caution",
        resumed_readiness_verdict="hold_for_operator_review",
    )
    assert cautionary["receipt_classification"] == "receipt_consumable_with_caution"

    fragmented = _resolve_export_packet_consumer_receipt(
        tmp_path,
        export_packet_classification="export_packet_fragmented",
        export_packet_maturity_posture="fragmented",
        pressure_classification="fragmentation_pressure",
        handoff_classification="packet_continuity_uncertain",
        path_classification="fragmented_path",
    )
    assert fragmented["receipt_classification"] == "receipt_fragmented"
    assert fragmented["consumable_as_bounded_observational_packet"] is False

    contradicted = _resolve_export_packet_consumer_receipt(
        tmp_path,
        export_packet_classification="export_packet_contradicted",
        export_packet_maturity_posture="contradicted",
        digest_classification="contradictory_current_picture",
        coherence_classification="materially_contradictory",
        transition_classification="transition_contradicted",
    )
    assert contradicted["receipt_classification"] == "receipt_contradicted"
    assert contradicted["consumable_as_bounded_observational_packet"] is False

    minimal = _resolve_export_packet_consumer_receipt(
        tmp_path,
        export_packet_classification="export_packet_minimal",
        export_packet_maturity_posture="minimal",
        digest_classification="mature_current_picture",
        coherence_classification="coherent_current_picture",
        transition_classification="poised_for_result_closure",
    )
    assert minimal["receipt_classification"] == "receipt_minimal"

    no_receipt_needed = _resolve_export_packet_consumer_receipt(
        tmp_path,
        export_packet_classification="export_packet_minimal",
        export_packet_maturity_posture="minimal",
        digest_classification="minimal_current_picture",
        coherence_classification="insufficient_current_signal",
        transition_classification="transition_uncertain",
        closure_classification="no_current_closure_posture",
        next_move_classification="no_current_next_move",
        handoff_classification="no_current_packet_brief",
        path_classification="no_current_resolution_path",
        pressure_classification="insufficient_signal",
        resumed_readiness_verdict="not_ready",
        wake_classification="not_wake_ready",
    )
    assert no_receipt_needed["receipt_classification"] == "no_current_receipt_needed"
    assert no_receipt_needed["consumable_as_bounded_observational_packet"] is False


def test_current_orchestration_export_packet_consumer_receipt_is_derived_non_authoritative_and_linked(tmp_path: Path) -> None:
    receipt = _resolve_export_packet_consumer_receipt(
        tmp_path,
        export_packet_classification="export_packet_ready",
        export_packet_maturity_posture="mature",
    )
    assert receipt["source_current_orchestration_export_packet_ref"]["current_orchestration_export_packet_id"] == "oep-test-1"
    assert receipt["linkage_to_underlying_current_surfaces_present"] is True
    assert receipt["linkage_to_underlying_current_surfaces_sufficient"] is True
    boundaries = receipt.get("boundaries", {})
    assert boundaries.get("non_authoritative") is True
    assert boundaries.get("non_executing") is True
    assert boundaries.get("does_not_execute_or_route_work") is True
    assert receipt.get("decision_power") == "none"
    assert receipt.get("basis", {}).get("historical_honesty", {}).get("derived_from_existing_surfaces_only") is True


def test_current_orchestration_export_packet_consumer_receipt_surface_is_in_scoped_lifecycle_diagnostic() -> None:
    source = inspect.getsource(scoped_lifecycle_diagnostic.build_scoped_lifecycle_diagnostic)
    assert "current_orchestration_export_packet_consumer_receipt" in source


def _resolve_handoff_acceptance_posture(
    tmp_path: Path,
    *,
    export_packet_classification: str,
    receipt_classification: str,
    export_packet_maturity_posture: str = "mature",
    receipt_consumable: bool = True,
    digest_classification: str = "mature_current_picture",
    coherence_classification: str = "coherent_current_picture",
    transition_classification: str = "poised_for_resumed_progress",
    closure_classification: str = "closure_pending_on_internal_result",
    next_move_classification: str = "continue_current_packet_next",
    handoff_classification: str = "packet_ready_for_continuation",
    operator_loop_posture: str = "informational",
    path_classification: str = "path_following_current_watchpoint",
    pressure_classification: str = "stable_or_low_pressure",
    resumed_readiness_verdict: str = "ready_to_proceed",
    wake_classification: str = "wake_ready",
    linkage_present: bool = True,
    linkage_sufficient: bool = True,
) -> dict[str, object]:
    return resolve_current_orchestration_handoff_acceptance_posture(
        tmp_path,
        current_orchestration_export_packet={
            "current_orchestration_export_packet_id": "oep-test-1",
            "export_packet_classification": export_packet_classification,
            "export_packet_maturity_posture": export_packet_maturity_posture,
            "basis": {"basis_evidence": {"current_orchestration_state_id": "state-1"}},
        },
        current_orchestration_export_packet_consumer_receipt={
            "current_orchestration_export_packet_consumer_receipt_id": "ocr-test-1",
            "receipt_classification": receipt_classification,
            "consumable_as_bounded_observational_packet": receipt_consumable,
            "linkage_to_underlying_current_surfaces_present": linkage_present,
            "linkage_to_underlying_current_surfaces_sufficient": linkage_sufficient,
        },
        current_orchestration_digest={"digest_classification": digest_classification},
        current_orchestration_coherence_brief={"coherence_classification": coherence_classification},
        current_orchestration_transition_brief={"transition_classification": transition_classification},
        current_orchestration_closure_brief={"closure_classification": closure_classification},
        current_orchestration_next_move_brief={"next_move_classification": next_move_classification},
        current_orchestration_handoff_packet_brief={"handoff_packet_brief_classification": handoff_classification},
        current_operator_facing_orchestration_brief={"loop_posture": operator_loop_posture},
        current_orchestration_resolution_path_brief={"resolution_path_classification": path_classification},
        current_orchestration_pressure_signal={"pressure_classification": pressure_classification},
        current_resumed_operation_readiness={"resumed_operation_readiness_verdict": resumed_readiness_verdict},
        current_orchestration_wake_readiness_detector={"wake_readiness_classification": wake_classification},
    )


def test_current_orchestration_handoff_acceptance_posture_classifications(tmp_path: Path) -> None:
    clear = _resolve_handoff_acceptance_posture(
        tmp_path,
        export_packet_classification="export_packet_ready",
        receipt_classification="receipt_structurally_consumable",
    )
    assert clear["handoff_acceptance_classification"] == "handoff_acceptance_clear"

    cautionary = _resolve_handoff_acceptance_posture(
        tmp_path,
        export_packet_classification="export_packet_cautionary",
        receipt_classification="receipt_consumable_with_caution",
        operator_loop_posture="cautionary",
        wake_classification="wake_ready_with_caution",
    )
    assert cautionary["handoff_acceptance_classification"] == "handoff_acceptance_cautionary"

    fragmented = _resolve_handoff_acceptance_posture(
        tmp_path,
        export_packet_classification="export_packet_fragmented",
        receipt_classification="receipt_fragmented",
        handoff_classification="packet_continuity_uncertain",
        path_classification="fragmented_path",
        pressure_classification="fragmentation_pressure",
    )
    assert fragmented["handoff_acceptance_classification"] == "handoff_acceptance_fragmented"

    contradicted = _resolve_handoff_acceptance_posture(
        tmp_path,
        export_packet_classification="export_packet_contradicted",
        receipt_classification="receipt_contradicted",
        digest_classification="contradictory_current_picture",
        coherence_classification="materially_contradictory",
        transition_classification="transition_contradicted",
    )
    assert contradicted["handoff_acceptance_classification"] == "handoff_acceptance_contradicted"

    minimal = _resolve_handoff_acceptance_posture(
        tmp_path,
        export_packet_classification="export_packet_minimal",
        receipt_classification="receipt_minimal",
        export_packet_maturity_posture="minimal",
    )
    assert minimal["handoff_acceptance_classification"] == "handoff_acceptance_minimal"

    no_current = _resolve_handoff_acceptance_posture(
        tmp_path,
        export_packet_classification="export_packet_minimal",
        receipt_classification="no_current_receipt_needed",
        export_packet_maturity_posture="minimal",
        receipt_consumable=False,
        digest_classification="minimal_current_picture",
        coherence_classification="insufficient_current_signal",
        transition_classification="transition_uncertain",
        closure_classification="no_current_closure_posture",
        next_move_classification="no_current_next_move",
        handoff_classification="no_current_packet_brief",
        path_classification="no_current_resolution_path",
        pressure_classification="insufficient_signal",
        resumed_readiness_verdict="not_ready",
        wake_classification="not_wake_ready",
    )
    assert no_current["handoff_acceptance_classification"] == "no_current_handoff_acceptance_posture"


def test_current_orchestration_handoff_acceptance_posture_is_derived_non_authoritative_and_linked(tmp_path: Path) -> None:
    posture = _resolve_handoff_acceptance_posture(
        tmp_path,
        export_packet_classification="export_packet_ready",
        receipt_classification="receipt_structurally_consumable",
    )
    assert posture["source_current_orchestration_export_packet_ref"]["current_orchestration_export_packet_id"] == "oep-test-1"
    assert (
        posture["source_current_orchestration_export_packet_consumer_receipt_ref"][
            "current_orchestration_export_packet_consumer_receipt_id"
        ]
        == "ocr-test-1"
    )
    assert posture["linkage_to_export_packet_and_consumer_receipt_present"] is True
    assert posture["linkage_to_export_packet_and_consumer_receipt_sufficient"] is True
    boundaries = posture.get("boundaries", {})
    assert boundaries.get("non_authoritative") is True
    assert boundaries.get("non_executing") is True
    assert boundaries.get("does_not_execute_or_route_work") is True
    assert posture.get("decision_power") == "none"
    assert posture.get("basis", {}).get("historical_honesty", {}).get("derived_from_existing_surfaces_only") is True


def test_current_orchestration_handoff_acceptance_posture_surface_is_in_scoped_lifecycle_diagnostic() -> None:
    source = inspect.getsource(scoped_lifecycle_diagnostic.build_scoped_lifecycle_diagnostic)
    assert "current_orchestration_handoff_acceptance_posture" in source
