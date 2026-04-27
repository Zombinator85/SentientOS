from __future__ import annotations

"""Admission/handoff legality kernel slice for orchestration spine."""

from pathlib import Path
from typing import Any, Callable, Mapping

import task_admission


def validate_handoff_minimum_fields_kernel(intent: Mapping[str, Any]) -> list[str]:
    """Validate minimum linkage fields required for legal handoff adjudication."""
    missing: list[str] = []
    if not str(intent.get("intent_id") or "").strip():
        missing.append("intent_id")
    if not str(intent.get("intent_kind") or "").strip():
        missing.append("intent_kind")
    if not str(intent.get("execution_target") or "").strip():
        missing.append("execution_target")
    if not str(intent.get("executability_classification") or "").strip():
        missing.append("executability_classification")
    source = intent.get("source_delegated_judgment")
    if not isinstance(source, Mapping):
        missing.append("source_delegated_judgment")
        return missing
    if not str(source.get("recommended_venue") or "").strip():
        missing.append("source_delegated_judgment.recommended_venue")
    if not str(source.get("work_class") or "").strip():
        missing.append("source_delegated_judgment.work_class")
    if not str(source.get("escalation_classification") or "").strip():
        missing.append("source_delegated_judgment.escalation_classification")
    return missing


def derive_packetization_gate_kernel(
    next_move_proposal: Mapping[str, Any],
    next_move_proposal_review: Mapping[str, Any],
    trust_confidence_posture: Mapping[str, Any],
    operator_attention_recommendation: Mapping[str, Any],
    *,
    anti_sovereignty_payload: Callable[..., Mapping[str, Any]],
    packetization_gating_outcomes: set[str],
    operator_resolution_influence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive one bounded packetization gate from existing orchestration-only signals."""
    proposed_action = next_move_proposal.get("proposed_next_action")
    proposed_action_map = proposed_action if isinstance(proposed_action, Mapping) else {}
    operator_state_raw = next_move_proposal.get("operator_escalation_requirement_state")
    operator_state = operator_state_raw if isinstance(operator_state_raw, Mapping) else {}
    trust_pressure_raw = trust_confidence_posture.get("pressure_summary")
    trust_pressure = trust_pressure_raw if isinstance(trust_pressure_raw, Mapping) else {}
    operator_influence_map = operator_resolution_influence if isinstance(operator_resolution_influence, Mapping) else {}

    posture = str(trust_confidence_posture.get("trust_confidence_posture") or "insufficient_history")
    proposal_review_classification = str(next_move_proposal_review.get("review_classification") or "insufficient_history")
    attention_signal = str(
        operator_attention_recommendation.get("operator_attention_recommendation")
        or operator_state.get("attention_signal")
        or "insufficient_context"
    )
    executability = str(next_move_proposal.get("executability_classification") or "blocked_insufficient_context")
    relation_posture = str(next_move_proposal.get("relation_posture") or "insufficient_context")
    proposed_posture = str(proposed_action_map.get("proposed_posture") or "hold")
    requires_operator = bool(operator_state.get("requires_operator_or_escalation"))
    escalation_classification = str(operator_state.get("escalation_classification") or "")
    trust_primary_pressure = str(trust_pressure.get("primary_pressure") or "insufficient_history")
    influence_state = str(operator_influence_map.get("operator_influence_state") or "no_operator_influence_yet")
    operator_approval_applied = bool(operator_influence_map.get("operator_approval_applied"))
    operator_context_applied = bool(operator_influence_map.get("operator_context_applied"))
    operator_decline_preserved_hold = bool(operator_influence_map.get("operator_decline_or_cancel_preserves_hold"))
    operator_defer_preserved_hold = bool(operator_influence_map.get("operator_defer_preserves_hold"))
    operator_influence_active = bool(operator_influence_map.get("operator_influence_applied"))

    hold_operator_required = (
        requires_operator
        or executability == "blocked_operator_required"
        or escalation_classification in {"escalate_for_missing_context", "escalate_for_operator_priority"}
        or attention_signal in {"inspect_handoff_blocks", "inspect_execution_failures", "inspect_pending_stall"}
    )
    hold_fragmentation = posture == "fragmented_or_unreliable" or trust_primary_pressure == "fragmentation"
    hold_insufficient_confidence = (
        posture == "insufficient_history"
        or executability == "blocked_insufficient_context"
        or relation_posture == "insufficient_context"
        or proposal_review_classification in {"proposal_insufficient_context_heavy", "insufficient_history"}
        or attention_signal == "insufficient_context"
    )
    mixed_stress_signals = (
        posture == "stressed_but_usable"
        or proposal_review_classification in {"mixed_proposal_stress", "proposal_venue_thrash", "proposal_escalation_heavy"}
        or attention_signal == "review_mixed_orchestration_stress"
        or trust_primary_pressure in {"mixed_stress", "result_quality_stress", "escalation_operator_dependence"}
    )
    coherent_execution_ready = (
        executability in {"executable_now", "stageable_external_work_order"}
        and relation_posture in {"affirming", "nudging"}
        and proposed_posture in {"expand", "consolidate", "audit"}
        and proposal_review_classification == "coherent_recent_proposals"
    )
    context_relief_execution_ready = (
        operator_context_applied
        and executability in {"executable_now", "stageable_external_work_order"}
        and relation_posture in {"affirming", "nudging"}
        and proposed_posture in {"expand", "consolidate", "audit"}
    )
    approval_can_relieve_operator_hold = operator_approval_applied and not hold_fragmentation
    context_can_relieve_insufficient_hold = (
        operator_context_applied and not hold_fragmentation and executability != "blocked_operator_required"
    )
    hold_operator_required_effective = hold_operator_required and not approval_can_relieve_operator_hold
    hold_insufficient_confidence_effective = hold_insufficient_confidence and not context_can_relieve_insufficient_hold
    if operator_decline_preserved_hold or operator_defer_preserved_hold:
        hold_operator_required_effective = True

    outcome = "packetization_hold_insufficient_confidence"
    compact_rationale = "insufficient_confidence_or_context_requires_conservative_packetization_hold"
    if hold_operator_required_effective:
        outcome = "packetization_hold_operator_review"
        compact_rationale = "operator_or_escalation_requirement_is_active_so_packetization_is_held"
    elif hold_fragmentation:
        outcome = "packetization_hold_fragmentation"
        compact_rationale = "trust_posture_is_fragmented_or_unreliable_so_packetization_is_held"
    elif hold_insufficient_confidence_effective:
        outcome = "packetization_hold_insufficient_confidence"
        compact_rationale = "insufficient_history_or_context_prevents_confident_packetization"
    elif operator_approval_applied and coherent_execution_ready:
        outcome = "packetization_allowed_with_caution"
        compact_rationale = "operator_approval_visible_with_coherent_proposal_allows_bounded_packetization_caution"
    elif operator_context_applied and (coherent_execution_ready or context_relief_execution_ready):
        outcome = "packetization_allowed_with_caution"
        compact_rationale = "operator_supplied_context_relieves_insufficient_context_hold_in_bounded_form"
    elif posture == "trusted_for_bounded_use" and coherent_execution_ready:
        outcome = "packetization_allowed"
        compact_rationale = "trusted_posture_with_coherent_proposal_allows_bounded_packetization"
    elif posture in {"caution_required", "stressed_but_usable"} and coherent_execution_ready and mixed_stress_signals:
        outcome = "packetization_allowed_with_caution"
        compact_rationale = "stress_is_present_but_coherence_is_sufficient_for_cautious_bounded_packetization"
    elif posture == "stressed_but_usable" and mixed_stress_signals:
        outcome = "packetization_hold_escalation_required"
        compact_rationale = "stressed_posture_with_mixed_signals_requires_conservative_escalation_hold"
    elif posture == "caution_required" and coherent_execution_ready:
        outcome = "packetization_allowed_with_caution"
        compact_rationale = "caution_posture_keeps_packetization_allowed_but_explicitly_bounded"
    elif mixed_stress_signals:
        outcome = "packetization_hold_escalation_required"
        compact_rationale = "mixed_stress_signals_require_escalation_before_packetization"

    if outcome not in packetization_gating_outcomes:
        outcome = "packetization_hold_insufficient_confidence"
        compact_rationale = "unrecognized_gate_outcome_defaulted_to_conservative_hold"

    held = outcome.startswith("packetization_hold_")
    return {
        "schema_version": "orchestration_packetization_gate.v1",
        "gate_kind": "next_move_packetization_gate",
        "packetization_outcome": outcome,
        "packetization_allowed": not held,
        "packetization_held": held,
        "summary": {
            "compact_rationale": compact_rationale,
            "signals_used": [
                "orchestration_trust_confidence_posture",
                "next_move_proposal",
                "next_move_proposal_review",
                "orchestration_operator_attention_recommendation",
                "next_move_proposal.operator_escalation_requirement_state",
            ],
            "affects_only": [
                "next_move_proposal_to_handoff_packet_preparation",
                "packet_ready_vs_hold_marking",
            ],
            "explicitly_not": [
                "direct_execution_authority",
                "admission_policy_override",
                "venue_recommendation_rewrite",
                "sovereign_planning",
            ],
        },
        "signal_snapshot": {
            "trust_confidence_posture": posture,
            "proposal_review_classification": proposal_review_classification,
            "operator_attention_recommendation": attention_signal,
            "executability_classification": executability,
            "relation_posture": relation_posture,
            "proposed_posture": proposed_posture,
            "requires_operator_or_escalation": requires_operator,
        },
        "operator_influence": {
            "operator_influence_state": influence_state,
            "operator_influence_applied": operator_influence_active,
            "operator_approval_applied": operator_approval_applied,
            "operator_context_applied": operator_context_applied,
            "operator_decline_preserved_hold": operator_decline_preserved_hold,
            "operator_defer_preserved_hold": operator_defer_preserved_hold,
            "applied_relief_paths": {
                "approval_relaxed_operator_hold": approval_can_relieve_operator_hold,
                "context_relaxed_insufficient_context_hold": context_can_relieve_insufficient_hold,
            },
            "resolution_kind": operator_influence_map.get("resolution_kind"),
            "resolution_receipt_id": operator_influence_map.get("resolution_receipt_id"),
        },
        **anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "gate_only": True,
                "packetization_stage_only": True,
                "does_not_execute_or_route_work": True,
                "non_authoritative": True,
                "does_not_imply_execution": True,
                "does_not_override_admission": True,
                "requires_existing_trigger_path_for_follow_on_action": True,
                "historical_operator_resolution_preserved": True,
            },
        ),
    }


def resolve_handoff_packet_fulfillment_lifecycle_kernel(
    repo_root: Path,
    handoff_packet: Mapping[str, Any],
    *,
    read_jsonl: Callable[[Path], list[dict[str, Any]]],
    staged_external_lifecycle_states: set[str],
) -> dict[str, Any]:
    """Resolve staged/fulfilled visibility for one external handoff packet."""
    root = repo_root.resolve()
    venue = str(handoff_packet.get("target_venue") or "")
    packet_id = str(handoff_packet.get("handoff_packet_id") or "")
    receipts = read_jsonl(root / "glow/orchestration/orchestration_fulfillment_receipts.jsonl")
    linked = [
        row
        for row in receipts
        if str((row.get("source_handoff_packet_ref") or {}).get("handoff_packet_id") or "") == packet_id
    ]
    latest = linked[-1] if linked else None

    readiness = handoff_packet.get("readiness")
    readiness_map = readiness if isinstance(readiness, Mapping) else {}
    packet_status = str(handoff_packet.get("packet_status") or "")
    lifecycle_state = "fragmented_unlinked_work_order_state"
    if latest is None:
        if packet_status == "blocked_operator_required":
            lifecycle_state = "blocked_operator_required"
        elif packet_status == "blocked_insufficient_context":
            lifecycle_state = "blocked_insufficient_context"
        elif bool(readiness_map.get("ready_for_external_trigger")):
            lifecycle_state = "staged_cleanly"
    else:
        fulfillment_kind = str(latest.get("fulfillment_kind") or "")
        lifecycle_state = {
            "externally_completed": "fulfilled_externally",
            "externally_completed_with_issues": "fulfilled_externally_with_issues",
            "externally_declined": "externally_declined",
            "externally_abandoned": "externally_abandoned",
            "externally_result_unusable": "externally_result_unusable",
        }.get(fulfillment_kind, "fragmented_unlinked_work_order_state")

    if lifecycle_state not in staged_external_lifecycle_states:
        lifecycle_state = "fragmented_unlinked_work_order_state"

    return {
        "schema_version": "external_handoff_packet_fulfillment_lifecycle.v1",
        "target_venue": venue,
        "handoff_packet_id": packet_id or None,
        "lifecycle_state": lifecycle_state,
        "fulfillment_received": latest is not None,
        "fulfillment_kind": str(latest.get("fulfillment_kind") or "") if isinstance(latest, Mapping) else None,
        "fulfillment_receipt_id": str(latest.get("fulfillment_receipt_id") or "") if isinstance(latest, Mapping) else None,
        "receipt_artifact_path": "glow/orchestration/orchestration_fulfillment_receipts.jsonl",
        "ingested_external_outcome": bool((latest or {}).get("ingested_external_outcome")) if isinstance(latest, Mapping) else False,
        "does_not_imply_direct_repo_execution": True,
        "non_authoritative": True,
        "decision_power": "none",
        "receipt_only": True,
        "requires_external_actor_or_operator": True,
    }


def resolve_admission_handoff_outcome_kernel(
    intent: Mapping[str, Any],
    *,
    validate_handoff_minimum_fields: Callable[[Mapping[str, Any]], list[str]],
    handoff_outcomes: set[str],
    admit_internal_maintenance_intent: Callable[..., Mapping[str, Any]],
    now_utc_iso: Callable[[], str],
    root: Path,
    admission_context: task_admission.AdmissionContext | None = None,
    admission_policy: task_admission.AdmissionPolicy | None = None,
) -> tuple[str, dict[str, Any]]:
    """Resolve admission legality and canonical handoff outcome for one intent."""
    missing_fields = validate_handoff_minimum_fields(intent)
    execution_target = str(intent.get("execution_target") or "")
    executability = str(intent.get("executability_classification") or "")
    authority_posture = str(intent.get("required_authority_posture") or "")

    outcome = "staged_only"
    details: dict[str, Any] = {
        "intent_id": str(intent.get("intent_id") or ""),
        "intent_kind": str(intent.get("intent_kind") or ""),
        "execution_target": execution_target,
        "executability_classification": executability,
        "required_authority_posture": authority_posture,
        "requires_operator_approval": bool(intent.get("requires_operator_approval")),
    }

    if missing_fields:
        outcome = "blocked_by_insufficient_context"
        details["missing_required_fields"] = missing_fields
    elif executability == "blocked_operator_required" or authority_posture in {"operator_approval_required", "operator_priority_required"}:
        outcome = "blocked_by_operator_requirement"
    elif executability == "blocked_insufficient_context" or authority_posture == "insufficient_context_blocked":
        outcome = "blocked_by_insufficient_context"
    elif executability != "executable_now":
        outcome = "staged_only"
    elif execution_target != "task_admission_executor":
        outcome = "execution_target_unavailable"
    else:
        task_admission_result = admit_internal_maintenance_intent(
            intent=intent,
            root=root,
            admission_context=admission_context,
            admission_policy=admission_policy,
            now_utc_iso=now_utc_iso(),
        )
        details["task_admission"] = task_admission_result
        outcome = "admitted_to_execution_substrate" if bool(task_admission_result.get("allowed")) else "blocked_by_admission"

    if outcome not in handoff_outcomes:
        outcome = "blocked_by_insufficient_context"
    return outcome, details
