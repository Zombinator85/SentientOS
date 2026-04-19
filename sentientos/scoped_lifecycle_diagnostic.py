from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sentientos.scoped_mutation_lifecycle import SCOPED_ACTION_IDS, resolve_scoped_mutation_lifecycle
from sentientos.scoped_slice_health import synthesize_scoped_slice_health
from sentientos.scoped_slice_health_history import persist_scoped_slice_health_history
from sentientos.scoped_slice_stability import derive_scoped_slice_stability
from sentientos.scoped_slice_retrospective_integrity import derive_scoped_slice_retrospective_integrity_review
from sentientos.scoped_slice_attention_recommendation import derive_scoped_slice_attention_recommendation
from sentientos.delegated_judgment_fabric import collect_delegated_judgment_evidence, synthesize_delegated_judgment
from sentientos.orchestration_intent_fabric import (
    admit_orchestration_intent,
    append_handoff_packet_ledger,
    append_next_move_proposal_ledger,
    append_operator_action_brief_ledger,
    append_orchestration_intent_ledger,
    build_split_closure_map,
    build_handoff_execution_gap_map,
    derive_orchestration_attention_recommendation,
    derive_packetization_gate,
    derive_proposal_packet_continuity_review,
    derive_external_feedback_gap_map,
    derive_repacketization_gap_map,
    derive_operator_resolution_feedback_gap_map,
    derive_operator_resolution_influence,
    derive_operator_adjusted_next_move_proposal_visibility,
    derive_operator_adjusted_next_venue_recommendation,
    derive_orchestration_trust_confidence_posture,
    derive_next_venue_recommendation,
    derive_orchestration_outcome_review,
    derive_delegated_operation_readiness_verdict,
    derive_unified_result_quality_review,
    derive_next_move_proposal_review,
    derive_orchestration_venue_mix_review,
    executable_handoff_map,
    resolve_codex_staged_work_order_lifecycle,
    resolve_deep_research_staged_work_order_lifecycle,
    resolve_handoff_packet_fulfillment_lifecycle,
    resolve_handoff_packet_history_for_proposal,
    resolve_active_handoff_packet_candidate,
    resolve_current_orchestration_state,
    resolve_current_orchestration_watchpoint,
    resolve_latest_operator_resolution_for_proposal,
    resolve_operator_action_brief_lifecycle,
    resolve_orchestration_result,
    resolve_unified_orchestration_result,
    resolve_unified_orchestration_result_surface,
    synthesize_next_move_proposal,
    synthesize_handoff_packet,
    synthesize_operator_refreshed_handoff_packet,
    synthesize_orchestration_intent,
    synthesize_operator_action_brief,
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _staged_external_venue_diagnostic(
    repo_root: Path,
    orchestration_intent: dict[str, Any],
    handoff_result: dict[str, Any],
    orchestration_result: dict[str, Any],
    handoff_packet: dict[str, Any],
    *,
    venue: str,
    lifecycle_key: str,
    handoff_ref_key: str,
    default_ledger_path: str,
    direct_boundary_key: str,
    resolve_lifecycle: Any,
    schema_version: str,
) -> dict[str, Any] | None:
    recommended_venue = str(orchestration_intent.get("source_delegated_judgment", {}).get("recommended_venue") or "")
    if recommended_venue != venue:
        return None

    lifecycle = orchestration_result.get(lifecycle_key)
    lifecycle_map = lifecycle if isinstance(lifecycle, dict) else resolve_lifecycle(repo_root, orchestration_intent, handoff_result)
    packet_fulfillment = resolve_handoff_packet_fulfillment_lifecycle(repo_root, handoff_packet)
    work_order_ref = handoff_result.get("details", {}).get(handoff_ref_key, {})
    ref_map = work_order_ref if isinstance(work_order_ref, dict) else {}
    executability_visibility = {
        "executability_classification": str(orchestration_intent.get("executability_classification") or ""),
        "not_directly_executable_here": True,
        "staged_only": True,
    }
    executability_visibility[direct_boundary_key] = True

    return {
        "schema_version": schema_version,
        "venue": venue,
        "staged_work_order_present": bool(ref_map),
        "staged_work_order_id": ref_map.get("work_order_id"),
        "proof_artifact": {
            "ledger_path": ref_map.get("ledger_path", default_ledger_path),
            "status": ref_map.get("status"),
        },
        "operator_requirement_state": {
            "required_authority_posture": str(orchestration_intent.get("required_authority_posture") or ""),
            "requires_operator_approval": bool(orchestration_intent.get("requires_operator_approval")),
            "escalation_classification": str(orchestration_intent.get("source_delegated_judgment", {}).get("escalation_classification") or ""),
        },
        "lifecycle_visibility": lifecycle_map,
        "packet_fulfillment_visibility": packet_fulfillment,
        "executability_visibility": executability_visibility,
        "observability_only": True,
    }


def build_scoped_lifecycle_diagnostic(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    router_rows = _read_jsonl(root / "pulse/forge_events.jsonl")
    rows: list[dict[str, Any]] = []
    for action_id in SCOPED_ACTION_IDS:
        correlation_id = ""
        for row in reversed(router_rows):
            if row.get("event") == "constitutional_mutation_router_execution" and str(row.get("typed_action_id") or "") == action_id:
                correlation_id = str(row.get("correlation_id") or "")
                break
        if correlation_id:
            rows.append(resolve_scoped_mutation_lifecycle(root, action_id=action_id, correlation_id=correlation_id))
        else:
            rows.append(
                {
                    "typed_action_identity": action_id,
                    "correlation_id": None,
                    "outcome_class": "fragmented_unresolved",
                    "findings": [{"kind": "router_event_missing", "surface": "pulse/forge_events.jsonl"}],
                }
            )

    order = {"success": 0, "denied": 1, "failed_after_admission": 2, "fragmented_unresolved": 3}
    overall = max((str(item.get("outcome_class") or "fragmented_unresolved") for item in rows), key=lambda val: order.get(val, 99))
    slice_health = synthesize_scoped_slice_health(rows)
    slice_health_history = persist_scoped_slice_health_history(root, slice_health=slice_health)
    recent_history = slice_health_history.get("recent_history") or []
    slice_stability = derive_scoped_slice_stability(recent_history)
    retrospective_integrity_review = derive_scoped_slice_retrospective_integrity_review(
        recent_history,
        slice_stability=slice_stability,
    )
    operator_attention_recommendation = derive_scoped_slice_attention_recommendation(
        slice_health=slice_health,
        slice_health_history=slice_health_history,
        slice_stability=slice_stability,
        retrospective_integrity_review=retrospective_integrity_review,
    )
    delegated_judgment_evidence = collect_delegated_judgment_evidence(
        root,
        scoped_lifecycle={
            "slice_health": slice_health,
            "slice_stability": slice_stability,
            "slice_retrospective_integrity_review": retrospective_integrity_review,
        },
    )
    delegated_judgment = synthesize_delegated_judgment(delegated_judgment_evidence)
    orchestration_intent = synthesize_orchestration_intent(delegated_judgment)
    orchestration_ledger_path = append_orchestration_intent_ledger(root, orchestration_intent)
    handoff_result = admit_orchestration_intent(root, orchestration_intent)
    orchestration_result = resolve_orchestration_result(root, handoff_result)
    orchestration_outcome_review = derive_orchestration_outcome_review(root)
    orchestration_venue_mix_review = derive_orchestration_venue_mix_review(root)
    orchestration_attention_recommendation = derive_orchestration_attention_recommendation(orchestration_outcome_review)
    next_venue_recommendation = derive_next_venue_recommendation(
        delegated_judgment,
        orchestration_outcome_review,
        orchestration_venue_mix_review,
        orchestration_attention_recommendation,
    )
    external_feedback_gap_map = derive_external_feedback_gap_map(
        orchestration_outcome_review,
        orchestration_venue_mix_review,
        next_venue_recommendation,
    )
    next_move_proposal = synthesize_next_move_proposal(
        delegated_judgment,
        next_venue_recommendation,
        orchestration_outcome_review,
        orchestration_venue_mix_review,
        orchestration_attention_recommendation,
    )
    next_move_proposal_ledger_path = append_next_move_proposal_ledger(root, next_move_proposal)
    unified_result_quality_review = derive_unified_result_quality_review(root)
    next_move_proposal_review = derive_next_move_proposal_review(root)
    proposal_packet_continuity_review = derive_proposal_packet_continuity_review(root)
    orchestration_trust_confidence_posture = derive_orchestration_trust_confidence_posture(
        next_move_proposal_review,
        orchestration_venue_mix_review,
        orchestration_outcome_review,
        unified_result_quality_review,
        orchestration_attention_recommendation,
        proposal_packet_continuity_review,
    )
    packetization_gate = derive_packetization_gate(
        next_move_proposal,
        next_move_proposal_review,
        orchestration_trust_confidence_posture,
        orchestration_attention_recommendation,
    )
    handoff_packet = synthesize_handoff_packet(
        next_move_proposal,
        delegated_judgment,
        next_move_proposal_review,
        orchestration_trust_confidence_posture,
        orchestration_attention_recommendation,
    )
    handoff_packet_ledger_path = append_handoff_packet_ledger(root, handoff_packet)
    operator_action_brief = synthesize_operator_action_brief(
        next_move_proposal,
        packetization_gate,
        orchestration_trust_confidence_posture,
        orchestration_attention_recommendation,
        next_move_proposal_review=next_move_proposal_review,
    )
    operator_action_brief_ledger_path = (
        append_operator_action_brief_ledger(root, operator_action_brief) if operator_action_brief else None
    )
    operator_brief_lifecycle = resolve_operator_action_brief_lifecycle(root, operator_action_brief)
    linked_operator_receipt = resolve_latest_operator_resolution_for_proposal(
        root, str(next_move_proposal.get("proposal_id") or "")
    )
    operator_influence = derive_operator_resolution_influence(linked_operator_receipt)
    adjusted_next_venue = derive_operator_adjusted_next_venue_recommendation(next_venue_recommendation, operator_influence)
    adjusted_next_move_proposal = derive_operator_adjusted_next_move_proposal_visibility(next_move_proposal, operator_influence)
    packetization_gate = derive_packetization_gate(
        adjusted_next_move_proposal,
        next_move_proposal_review,
        orchestration_trust_confidence_posture,
        orchestration_attention_recommendation,
        operator_influence,
    )
    refreshed_handoff_packet = synthesize_operator_refreshed_handoff_packet(
        adjusted_next_move_proposal,
        delegated_judgment,
        next_move_proposal_review,
        orchestration_trust_confidence_posture,
        orchestration_attention_recommendation,
        linked_operator_receipt,
        handoff_packet,
    )
    refreshed_handoff_packet_ledger_path = (
        append_handoff_packet_ledger(root, refreshed_handoff_packet) if refreshed_handoff_packet is not None else None
    )
    effective_handoff_packet = refreshed_handoff_packet if refreshed_handoff_packet is not None else handoff_packet
    packet_history = resolve_handoff_packet_history_for_proposal(root, str(next_move_proposal.get("proposal_id") or ""))
    active_packet = resolve_active_handoff_packet_candidate(
        root,
        str(next_move_proposal.get("proposal_id") or ""),
        operator_influence=operator_influence,
    )
    repacketization_gap_map = derive_repacketization_gap_map(
        operator_brief_lifecycle,
        operator_influence,
        packet_history,
        active_packet,
    )
    operator_feedback_gap_map = derive_operator_resolution_feedback_gap_map(
        adjusted_next_move_proposal,
        packetization_gate,
        adjusted_next_venue,
        operator_brief_lifecycle,
        operator_influence,
    )
    unified_result = resolve_unified_orchestration_result(root, handoff=handoff_result, handoff_packet=effective_handoff_packet)
    unified_result_surface = resolve_unified_orchestration_result_surface(root)
    current_orchestration_state = resolve_current_orchestration_state(
        root,
        current_proposal=adjusted_next_move_proposal,
        active_packet_visibility=active_packet,
        operator_brief_lifecycle=operator_brief_lifecycle,
        packetization_gate=packetization_gate,
        unified_result=unified_result,
    )
    current_orchestration_watchpoint = resolve_current_orchestration_watchpoint(
        root,
        current_orchestration_state=current_orchestration_state,
        current_proposal=adjusted_next_move_proposal,
        active_packet_visibility=active_packet,
        operator_brief_lifecycle=operator_brief_lifecycle,
        packetization_gate=packetization_gate,
        unified_result=unified_result,
    )
    delegated_operation_readiness = derive_delegated_operation_readiness_verdict(
        orchestration_trust_confidence_posture,
        proposal_packet_continuity_review,
        unified_result_quality_review,
        packetization_gate,
        orchestration_attention_recommendation,
        outcome_review=orchestration_outcome_review,
        venue_mix_review=orchestration_venue_mix_review,
        next_move_proposal_review=next_move_proposal_review,
        active_packet_visibility=active_packet,
        current_orchestration_state={
            **current_orchestration_state,
            "current_watchpoint": current_orchestration_watchpoint,
        },
    )
    unified_result_quality_review = derive_unified_result_quality_review(root)
    substitution_readiness = dict(delegated_judgment.get("orchestration_substitution_readiness") or {})
    substitution_readiness["trust_confidence_basis"] = {
        "orchestration_trust_confidence_posture": str(
            orchestration_trust_confidence_posture.get("trust_confidence_posture") or "insufficient_history"
        ),
        "delegated_operation_readiness_verdict": str(
            delegated_operation_readiness.get("readiness_verdict") or "insufficient_history"
        ),
        "diagnostic_only": True,
        "review_only": True,
        "does_not_change_existing_readiness_logic": True,
    }
    codex_staged_venue = _staged_external_venue_diagnostic(
        root,
        orchestration_intent,
        handoff_result,
        orchestration_result,
        effective_handoff_packet,
        venue="codex_implementation",
        lifecycle_key="codex_staged_lifecycle",
        handoff_ref_key="codex_work_order_ref",
        default_ledger_path="glow/orchestration/codex_work_orders.jsonl",
        direct_boundary_key="does_not_invoke_codex_directly",
        resolve_lifecycle=resolve_codex_staged_work_order_lifecycle,
        schema_version="codex_staged_venue_diagnostic.v1",
    )
    deep_research_staged_venue = _staged_external_venue_diagnostic(
        root,
        orchestration_intent,
        handoff_result,
        orchestration_result,
        effective_handoff_packet,
        venue="deep_research_audit",
        lifecycle_key="deep_research_staged_lifecycle",
        handoff_ref_key="deep_research_work_order_ref",
        default_ledger_path="glow/orchestration/deep_research_work_orders.jsonl",
        direct_boundary_key="does_not_invoke_deep_research_directly",
        resolve_lifecycle=resolve_deep_research_staged_work_order_lifecycle,
        schema_version="deep_research_staged_venue_diagnostic.v1",
    )
    return {
        "scope": "constitutional_execution_fabric_scoped_slice",
        "overall_outcome": overall,
        "slice_health": slice_health,
        "slice_health_history": slice_health_history,
        "slice_stability": slice_stability,
        "slice_retrospective_integrity_review": retrospective_integrity_review,
        "slice_operator_attention_recommendation": operator_attention_recommendation,
        "delegated_judgment": {
            **delegated_judgment,
            "orchestration_substitution_readiness": substitution_readiness,
        },
        "orchestration_handoff": {
            "gap_map": build_handoff_execution_gap_map(root),
            "split_closure_map": build_split_closure_map(),
            "executable_handoff_map": executable_handoff_map(),
            "intent": orchestration_intent,
            "intent_ledger_path": str(orchestration_ledger_path.relative_to(root)),
            "handoff_result": handoff_result,
            "execution_result": orchestration_result,
            "unified_result": unified_result,
            "unified_result_surface": unified_result_surface,
            "unified_result_quality_review": unified_result_quality_review,
            "outcome_review": orchestration_outcome_review,
            "venue_mix_review": orchestration_venue_mix_review,
            "attention_recommendation": orchestration_attention_recommendation,
            "next_venue_recommendation": adjusted_next_venue,
            "external_fulfillment_feedback_visibility": external_feedback_gap_map,
            "operator_resolution_feedback_gap_map": operator_feedback_gap_map,
            "repacketization_gap_map": repacketization_gap_map,
            "next_move_proposal": {
                **adjusted_next_move_proposal,
                "ledger_path": str(next_move_proposal_ledger_path.relative_to(root)),
                "current_delegated_judgment_venue": delegated_judgment.get("recommended_venue"),
                "ready_for_internal_executable_handoff": adjusted_next_move_proposal.get("executability_classification")
                == "executable_now",
                "staged_only": adjusted_next_move_proposal.get("executability_classification") == "stageable_external_work_order",
                "blocked_or_hold": adjusted_next_move_proposal.get("executability_classification")
                in {"blocked_operator_required", "blocked_insufficient_context", "no_action_recommended"},
            },
            "next_move_proposal_review": next_move_proposal_review,
            "proposal_packet_continuity_review": proposal_packet_continuity_review,
            "trust_confidence_posture": orchestration_trust_confidence_posture,
            "delegated_operation_readiness": delegated_operation_readiness,
            "current_orchestration_state": current_orchestration_state,
            "current_orchestration_watchpoint": current_orchestration_watchpoint,
            "current_orchestration_watchpoint_summary": {
                "current_orchestration_state": current_orchestration_state.get("current_supervisory_state"),
                "watchpoint_class": current_orchestration_watchpoint.get("watchpoint_class"),
                "expected_actor": current_orchestration_watchpoint.get("expected_actor"),
                "expected_signal_type": current_orchestration_watchpoint.get("expected_signal_type"),
                "compact_rationale": (current_orchestration_watchpoint.get("basis") or {}).get("compact_rationale"),
                "non_sovereign_boundaries": {
                    "diagnostic_only": True,
                    "non_authoritative": True,
                    "decision_power": "none",
                    "watchpoint_only": True,
                    "does_not_execute_or_route_work": True,
                },
            },
            "packetization_gating": {
                **packetization_gate,
                "packetization_allowed_or_caution": packetization_gate.get("packetization_outcome")
                in {"packetization_allowed", "packetization_allowed_with_caution"},
                "packetization_held_or_escalated": bool(packetization_gate.get("packetization_held")),
                "non_sovereign_boundaries": {
                    "non_authoritative": True,
                    "does_not_execute_or_route_work": True,
                    "does_not_override_kernel_or_governor": True,
                    "does_not_imply_execution": True,
                    "does_not_override_admission": True,
                    "requires_existing_trigger_path_for_follow_on_action": True,
                    "historical_operator_resolution_preserved": True,
                },
            },
            "operator_action_brief": {
                "brief_produced": operator_action_brief is not None,
                "loop_held_pending_operator_intervention": bool(packetization_gate.get("packetization_held"))
                and bool(operator_brief_lifecycle.get("awaiting_operator_input")),
                "intervention_class": None if operator_action_brief is None else operator_action_brief.get("intervention_class"),
                "target_venue_or_posture": None
                if operator_action_brief is None
                else operator_action_brief.get("target_venue_or_posture"),
                "lifecycle_visibility": operator_brief_lifecycle,
                "operator_resolution_received": bool(operator_brief_lifecycle.get("operator_resolution_received")),
                "resolution_kind": operator_brief_lifecycle.get("resolution_kind"),
                "resolution_receipt_artifact_linkage": {
                    "ledger_path": operator_brief_lifecycle.get("receipt_artifact_path"),
                    "operator_resolution_receipt_id": operator_brief_lifecycle.get("operator_resolution_receipt_id"),
                },
                "awaiting_operator_input": bool(operator_brief_lifecycle.get("awaiting_operator_input")),
                "has_operator_guidance": bool(operator_brief_lifecycle.get("has_operator_guidance")),
                "brief_artifact_linkage": None
                if operator_action_brief_ledger_path is None
                else {
                    "ledger_path": str(operator_action_brief_ledger_path.relative_to(root)),
                    "operator_action_brief_id": operator_action_brief.get("operator_action_brief_id")
                    if operator_action_brief
                    else None,
                },
                "brief": operator_action_brief,
                "non_sovereign_boundaries": {
                    "non_authoritative": True,
                    "operator_guidance_only": True,
                    "ingested_operator_outcome": bool(operator_brief_lifecycle.get("ingested_operator_outcome")),
                    "explicit_clarity": "ingested operator outcome, not repo execution",
                    "does_not_override_packetization_gate": True,
                    "does_not_convert_hold_to_execution": True,
                    "does_not_execute_or_route_work": True,
                },
            },
            "operator_influence": operator_influence,
            "handoff_packet": {
                **effective_handoff_packet,
                "ledger_path": str(handoff_packet_ledger_path.relative_to(root))
                if refreshed_handoff_packet_ledger_path is None
                else str(refreshed_handoff_packet_ledger_path.relative_to(root)),
                "staged_only": bool((effective_handoff_packet.get("readiness") or {}).get("staged_only")),
                "blocked": bool((effective_handoff_packet.get("readiness") or {}).get("blocked")),
                "ready_for_internal_trigger": bool((effective_handoff_packet.get("readiness") or {}).get("ready_for_internal_trigger")),
                "ready_for_external_trigger": bool((effective_handoff_packet.get("readiness") or {}).get("ready_for_external_trigger")),
                "fulfillment_visibility": resolve_handoff_packet_fulfillment_lifecycle(root, effective_handoff_packet),
                "repacketized_from_operator_feedback": refreshed_handoff_packet is not None,
                "historical_packet_state_preserved": True,
                "lineage_history": packet_history,
                "active_packet_candidate": active_packet,
                "initial_handoff_packet": {
                    **handoff_packet,
                    "ledger_path": str(handoff_packet_ledger_path.relative_to(root)),
                },
                "refreshed_handoff_packet": None
                if refreshed_handoff_packet is None
                else {
                    **refreshed_handoff_packet,
                    "ledger_path": str(refreshed_handoff_packet_ledger_path.relative_to(root))
                    if refreshed_handoff_packet_ledger_path is not None
                    else None,
                },
            },
            "codex_staged_venue": codex_staged_venue,
            "deep_research_staged_venue": deep_research_staged_venue,
        },
        "actions": rows,
    }
