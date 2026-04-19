from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import task_admission
import task_executor

_INTENT_KINDS = {
    "internal_maintenance_execution",
    "codex_work_order",
    "deep_research_work_order",
    "operator_review_request",
    "hold_no_action",
}

_AUTHORITY_POSTURES = {
    "no_additional_operator_approval_required",
    "operator_approval_required",
    "operator_priority_required",
    "insufficient_context_blocked",
}

_EXECUTION_TARGETS = {
    "task_admission_executor",
    "mutation_router",
    "federation_canonical_execution",
    "no_execution_target_yet",
    "external_tool_placeholder",
}

_EXECUTABILITY = {
    "executable_now",
    "stageable_external_work_order",
    "blocked_operator_required",
    "blocked_insufficient_context",
    "no_action_recommended",
}

_ADMISSION_STATES = {
    "admitted_for_internal_staging",
    "deferred_operator_approval",
    "deferred_operator_priority",
    "deferred_insufficient_context",
    "staged_non_executable_work_order",
    "no_action",
}

_HANDOFF_OUTCOMES = {
    "staged_only",
    "admitted_to_execution_substrate",
    "blocked_by_admission",
    "blocked_by_operator_requirement",
    "blocked_by_insufficient_context",
    "execution_target_unavailable",
}

_EXECUTION_RESULT_STATES = {
    "handoff_admitted_pending_result",
    "execution_succeeded",
    "execution_failed",
    "execution_result_missing",
    "execution_still_pending",
    "handoff_not_admitted",
}

_UNIFIED_RESULT_RESOLUTION_PATHS = {
    "internal_execution",
    "external_fulfillment",
}

_UNIFIED_RESULT_CLASSIFICATIONS = {
    "completed_successfully",
    "completed_with_issues",
    "declined_or_abandoned",
    "failed_after_execution",
    "blocked_before_execution",
    "pending_or_unresolved",
    "fragmented_result_history",
}


_STAGED_EXTERNAL_WORK_ORDER_STATUSES = {
    "staged",
    "blocked_operator_required",
    "blocked_insufficient_context",
    "cancelled",
    "fulfilled_externally_unverified",
}

_STAGED_EXTERNAL_LIFECYCLE_STATES = {
    "staged_cleanly",
    "blocked_operator_required",
    "blocked_insufficient_context",
    "fulfilled_externally",
    "fulfilled_externally_with_issues",
    "externally_declined",
    "externally_abandoned",
    "externally_result_unusable",
    "fragmented_unlinked_work_order_state",
}

_FULFILLMENT_KINDS = {
    "externally_completed",
    "externally_completed_with_issues",
    "externally_declined",
    "externally_abandoned",
    "externally_result_unusable",
}

_ORCHESTRATION_REVIEW_CLASSES = {
    "clean_recent_orchestration",
    "handoff_block_heavy",
    "execution_failure_heavy",
    "pending_stall_pattern",
    "mixed_orchestration_stress",
    "insufficient_history",
}

_ORCHESTRATION_ATTENTION_RECOMMENDATIONS = {
    "none",
    "observe",
    "inspect_handoff_blocks",
    "inspect_execution_failures",
    "inspect_pending_stall",
    "review_mixed_orchestration_stress",
    "insufficient_context",
}

_ORCHESTRATION_VENUE_MIX_CLASSES = {
    "balanced_recent_venue_mix",
    "internal_execution_heavy",
    "codex_heavy",
    "deep_research_heavy",
    "operator_escalation_heavy",
    "mixed_venue_stress",
    "insufficient_history",
}

_UNIFIED_RESULT_QUALITY_REVIEW_CLASSES = {
    "healthy_recent_results",
    "issues_heavy",
    "abandonment_or_decline_heavy",
    "fragmentation_heavy",
    "mixed_result_stress",
    "insufficient_history",
}

_NEXT_VENUE_RECOMMENDATIONS = {
    "prefer_internal_execution",
    "prefer_codex_implementation",
    "prefer_deep_research_audit",
    "prefer_operator_decision",
    "hold_current_venue_mix",
    "insufficient_context",
}

_NEXT_VENUE_RELATIONS = {
    "affirming",
    "nudging",
    "holding",
    "escalating",
    "insufficient_context",
}

_NEXT_MOVE_PROPOSAL_POSTURES = {
    "expand",
    "consolidate",
    "audit",
    "hold",
    "escalate",
}

_NEXT_MOVE_EXECUTABILITY = {
    "executable_now",
    "stageable_external_work_order",
    "blocked_operator_required",
    "blocked_insufficient_context",
    "no_action_recommended",
}

_NEXT_MOVE_PROPOSAL_REVIEW_CLASSES = {
    "coherent_recent_proposals",
    "proposal_escalation_heavy",
    "proposal_hold_heavy",
    "proposal_insufficient_context_heavy",
    "proposal_venue_thrash",
    "mixed_proposal_stress",
    "insufficient_history",
}

_PROPOSAL_PACKET_CONTINUITY_CLASSES = {
    "coherent_proposal_packet_continuity",
    "hold_heavy_continuity",
    "redirect_heavy_continuity",
    "repacketization_churn",
    "fragmented_continuity",
    "insufficient_history",
}

_ORCHESTRATION_TRUST_POSTURES = {
    "trusted_for_bounded_use",
    "caution_required",
    "stressed_but_usable",
    "fragmented_or_unreliable",
    "insufficient_history",
}

_PACKETIZATION_GATING_OUTCOMES = {
    "packetization_allowed",
    "packetization_allowed_with_caution",
    "packetization_hold_operator_review",
    "packetization_hold_insufficient_confidence",
    "packetization_hold_fragmentation",
    "packetization_hold_escalation_required",
}

_ORCHESTRATION_TRUST_PRESSURE_KINDS = {
    "none",
    "proposal_stress",
    "venue_stress",
    "result_quality_stress",
    "escalation_operator_dependence",
    "fragmentation",
    "mixed_stress",
    "insufficient_history",
}

_HANDOFF_PACKET_STATUSES = {
    "prepared",
    "blocked_operator_required",
    "blocked_insufficient_context",
    "ready_for_external_trigger",
    "ready_for_internal_trigger",
}

_OPERATOR_INTERVENTION_CLASSES = {
    "approve_and_continue",
    "review_fragmentation",
    "resolve_insufficient_context",
    "resolve_escalation_priority",
    "inspect_recent_orchestration_stress",
    "manual_external_trigger_required",
}

_OPERATOR_RESOLUTION_KINDS = {
    "approved_continue",
    "approved_with_constraints",
    "declined",
    "deferred",
    "supplied_missing_context",
    "redirected_venue",
    "cancelled",
}

_OPERATOR_BRIEF_LIFECYCLE_STATES = {
    "brief_emitted",
    "operator_resolution_received",
    "operator_approved_continue",
    "operator_approved_with_constraints",
    "operator_declined",
    "operator_deferred",
    "operator_redirected",
    "operator_supplied_missing_context",
    "fragmented_unlinked_operator_resolution",
}

_OPERATOR_INFLUENCE_STATES = {
    "no_operator_influence_yet",
    "operator_context_applied",
    "operator_approval_applied",
    "operator_redirect_applied",
    "operator_decline_preserved_hold",
    "operator_defer_preserved_hold",
}


def _anti_sovereignty_payload(
    *,
    recommendation_only: bool,
    diagnostic_only: bool,
    does_not_invoke_external_tools: bool | None = None,
    does_not_change_admission_or_execution: bool | None = None,
    additional_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "non_authoritative": True,
        "decision_power": "none",
        "recommendation_only": recommendation_only,
        "diagnostic_only": diagnostic_only,
    }
    if does_not_invoke_external_tools is not None:
        payload["does_not_invoke_external_tools"] = does_not_invoke_external_tools
    if does_not_change_admission_or_execution is not None:
        payload["does_not_change_admission_or_execution"] = does_not_change_admission_or_execution
    if additional_fields:
        payload.update(dict(additional_fields))
    return payload


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _intent_id(source_judgment: Mapping[str, Any], created_at: str) -> str:
    canonical = json.dumps({"created_at": created_at, "source_judgment": source_judgment}, sort_keys=True, separators=(",", ":"))
    return f"orh-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _classify_authority_posture(judgment: Mapping[str, Any]) -> str:
    escalation = str(judgment.get("escalation_classification") or "")
    venue = str(judgment.get("recommended_venue") or "")
    if escalation == "escalate_for_missing_context" or venue == "insufficient_context":
        return "insufficient_context_blocked"
    if escalation == "escalate_for_operator_priority":
        return "operator_priority_required"
    if venue in {"codex_implementation", "deep_research_audit", "operator_decision_required"}:
        return "operator_approval_required"
    return "no_additional_operator_approval_required"


def _translate_kind(judgment: Mapping[str, Any]) -> tuple[str, str, str]:
    venue = str(judgment.get("recommended_venue") or "")
    work_class = str(judgment.get("work_class") or "")
    escalation = str(judgment.get("escalation_classification") or "")

    if escalation == "escalate_for_missing_context" or venue == "insufficient_context":
        return "hold_no_action", "no_execution_target_yet", "blocked_insufficient_context"

    if venue == "internal_direct_execution" and work_class == "internal_runtime_maintenance":
        return "internal_maintenance_execution", "task_admission_executor", "executable_now"

    if venue == "codex_implementation":
        return "codex_work_order", "no_execution_target_yet", "stageable_external_work_order"

    if venue == "deep_research_audit":
        return "deep_research_work_order", "no_execution_target_yet", "stageable_external_work_order"

    if venue == "operator_decision_required":
        return "operator_review_request", "no_execution_target_yet", "blocked_operator_required"

    if work_class == "external_tool_orchestration":
        return "operator_review_request", "external_tool_placeholder", "stageable_external_work_order"

    return "hold_no_action", "no_execution_target_yet", "no_action_recommended"


def _derive_admission_state(executability: str, authority_posture: str) -> str:
    if executability == "executable_now" and authority_posture == "no_additional_operator_approval_required":
        return "admitted_for_internal_staging"
    if authority_posture == "operator_priority_required":
        return "deferred_operator_priority"
    if authority_posture == "insufficient_context_blocked":
        return "deferred_insufficient_context"
    if executability == "stageable_external_work_order":
        return "staged_non_executable_work_order"
    if executability == "blocked_operator_required":
        return "deferred_operator_approval"
    return "no_action"


def _source_judgment_linkage(judgment: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "work_class": str(judgment.get("work_class") or "operator_required"),
        "recommended_venue": str(judgment.get("recommended_venue") or "insufficient_context"),
        "next_move_posture": str(judgment.get("next_move_posture") or "hold"),
        "consolidation_expansion_posture": str(judgment.get("consolidation_expansion_posture") or "insufficient_context"),
        "escalation_classification": str(judgment.get("escalation_classification") or "escalate_for_missing_context"),
        "readiness_basis": {
            "orchestration_substitution_readiness": judgment.get("orchestration_substitution_readiness", {}),
            "basis": judgment.get("basis", {}),
        },
    }


def _work_order_payload(intent_kind: str, source_linkage: Mapping[str, Any], executability: str, authority_posture: str) -> dict[str, Any] | None:
    if intent_kind not in {"codex_work_order", "deep_research_work_order", "operator_review_request"}:
        return None

    venue = str(source_linkage.get("recommended_venue") or "")
    rationale = source_linkage.get("readiness_basis", {}).get("basis", {}) if isinstance(source_linkage.get("readiness_basis"), Mapping) else {}
    return {
        "work_order_kind": intent_kind,
        "intended_venue": venue,
        "bounded_rationale": {
            "signal_reasons": list(rationale.get("signal_reasons") or []),
            "slice_health_status": rationale.get("slice_health_status"),
            "slice_stability_classification": rationale.get("slice_stability_classification"),
            "slice_review_classification": rationale.get("slice_review_classification"),
        },
        "authority_posture": authority_posture,
        "executability_classification": executability,
        "staged_only": executability != "executable_now",
    }


def synthesize_orchestration_intent(
    delegated_judgment: Mapping[str, Any],
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Translate delegated judgment into a bounded, governed orchestration intent."""

    source_linkage = _source_judgment_linkage(delegated_judgment)
    authority_posture = _classify_authority_posture(delegated_judgment)
    intent_kind, execution_target, executability = _translate_kind(delegated_judgment)
    admission_state = _derive_admission_state(executability, authority_posture)
    timestamp = created_at or _iso_utc_now()
    intent_id = _intent_id(source_linkage, timestamp)

    if intent_kind not in _INTENT_KINDS:
        intent_kind = "hold_no_action"
    if authority_posture not in _AUTHORITY_POSTURES:
        authority_posture = "insufficient_context_blocked"
    if execution_target not in _EXECUTION_TARGETS:
        execution_target = "no_execution_target_yet"
    if executability not in _EXECUTABILITY:
        executability = "blocked_insufficient_context"
    if admission_state not in _ADMISSION_STATES:
        admission_state = "deferred_insufficient_context"

    requires_operator_approval = authority_posture != "no_additional_operator_approval_required"
    work_order = _work_order_payload(intent_kind, source_linkage, executability, authority_posture)

    return {
        "schema_version": "orchestration_intent.v1",
        "intent_id": intent_id,
        "created_at": timestamp,
        "intent_kind": intent_kind,
        "source_delegated_judgment": source_linkage,
        "required_authority_posture": authority_posture,
        "execution_target": execution_target,
        "executability_classification": executability,
        "handoff_admission_state": admission_state,
        "work_order": work_order,
        "requires_admission": execution_target in {"task_admission_executor", "mutation_router", "federation_canonical_execution"},
        "requires_operator_approval": requires_operator_approval,
        **_anti_sovereignty_payload(
            recommendation_only=False,
            diagnostic_only=False,
            does_not_invoke_external_tools=True,
        ),
        "staged_handoff_only": executability != "executable_now",
        "does_not_override_existing_admission": True,
        "does_not_override_kernel_or_governor": True,
        "does_not_replace_operator_authority": True,
    }


def append_orchestration_intent_ledger(repo_root: Path, intent: Mapping[str, Any]) -> Path:
    """Append one orchestration intent to the proof-visible handoff ledger."""

    ledger_path = repo_root.resolve() / "glow/orchestration/orchestration_intents.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(intent), sort_keys=True) + "\n")
    return ledger_path


def _validate_handoff_minimum_fields(intent: Mapping[str, Any]) -> list[str]:
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


def _build_internal_maintenance_task(intent: Mapping[str, Any]) -> task_executor.Task:
    source = intent.get("source_delegated_judgment")
    source_mapping = source if isinstance(source, Mapping) else {}
    return task_executor.Task(
        task_id=f"orh-{str(intent.get('intent_id') or 'missing')}",
        objective="orchestration_intent_internal_maintenance_handoff",
        constraints=(
            "bounded_orchestration_handoff_only",
            "no_external_tool_direct_invocation",
            "admission_required_before_execution",
        ),
        steps=(
            task_executor.Step(
                step_id=1,
                kind="noop",
                payload=task_executor.NoopPayload(
                    note=json.dumps(
                        {
                            "intent_kind": intent.get("intent_kind"),
                            "recommended_venue": source_mapping.get("recommended_venue"),
                            "executability_classification": intent.get("executability_classification"),
                        },
                        sort_keys=True,
                    ),
                ),
            ),
        ),
        allow_epr=False,
        required_privileges=("orchestration_intent_handoff",),
    )


def _default_admission_context() -> task_admission.AdmissionContext:
    return task_admission.AdmissionContext(
        actor="orchestration_intent_fabric",
        mode="autonomous",
        node_id="sentientos_orchestration_handoff",
        vow_digest=None,
        doctrine_digest=None,
        now_utc_iso=_iso_utc_now(),
    )


def _default_admission_policy() -> task_admission.AdmissionPolicy:
    return task_admission.AdmissionPolicy(policy_version="orchestration_intent_handoff.v1")


def _staged_work_order_id(intent: Mapping[str, Any], created_at: str, *, prefix: str) -> str:
    canonical = json.dumps(
        {
            "created_at": created_at,
            "intent_id": str(intent.get("intent_id") or ""),
            "source_judgment": dict(intent.get("source_delegated_judgment") or {}),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{prefix}-wo-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _source_judgment_linkage_id(source_map: Mapping[str, Any]) -> str:
    canonical = json.dumps(dict(source_map), sort_keys=True, separators=(",", ":"))
    return f"jdg-link-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _next_move_proposal_id(
    *,
    created_at: str,
    source_linkage_id: str,
    relation_posture: str,
    proposed_venue: str,
    proposed_intent_kind: str,
) -> str:
    canonical = json.dumps(
        {
            "created_at": created_at,
            "source_linkage_id": source_linkage_id,
            "relation_posture": relation_posture,
            "proposed_venue": proposed_venue,
            "proposed_intent_kind": proposed_intent_kind,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"nmp-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _handoff_packet_id(
    *,
    created_at: str,
    source_proposal_id: str,
    source_judgment_linkage_id: str,
    target_venue: str,
    supersedes_handoff_packet_id: str | None = None,
    source_operator_resolution_receipt_id: str | None = None,
) -> str:
    canonical = json.dumps(
        {
            "created_at": created_at,
            "source_proposal_id": source_proposal_id,
            "source_judgment_linkage_id": source_judgment_linkage_id,
            "target_venue": target_venue,
            "supersedes_handoff_packet_id": supersedes_handoff_packet_id or "",
            "source_operator_resolution_receipt_id": source_operator_resolution_receipt_id or "",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"hpk-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _operator_action_brief_id(
    *,
    source_proposal_id: str,
    gate_outcome: str,
    intervention_class: str,
    target_hint: str,
) -> str:
    canonical = json.dumps(
        {
            "gate_outcome": gate_outcome,
            "intervention_class": intervention_class,
            "source_proposal_id": source_proposal_id,
            "target_hint": target_hint,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"oab-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _fulfillment_receipt_id(
    *,
    created_at: str,
    handoff_packet_id: str,
    venue: str,
    fulfillment_kind: str,
) -> str:
    canonical = json.dumps(
        {
            "created_at": created_at,
            "handoff_packet_id": handoff_packet_id,
            "venue": venue,
            "fulfillment_kind": fulfillment_kind,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"frc-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _operator_resolution_receipt_id(
    *,
    created_at: str,
    operator_action_brief_id: str,
    resolution_kind: str,
) -> str:
    canonical = json.dumps(
        {
            "created_at": created_at,
            "operator_action_brief_id": operator_action_brief_id,
            "resolution_kind": resolution_kind,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"orr-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _compact_handoff_task_brief(next_move_proposal: Mapping[str, Any], delegated_judgment: Mapping[str, Any]) -> str:
    proposed = next_move_proposal.get("proposed_next_action")
    proposed_map = proposed if isinstance(proposed, Mapping) else {}
    work_class = str(delegated_judgment.get("work_class") or "operator_required")
    venue = str(proposed_map.get("proposed_venue") or "insufficient_context")
    posture = str(proposed_map.get("proposed_posture") or "hold")
    executability = str(next_move_proposal.get("executability_classification") or "blocked_insufficient_context")
    return f"{work_class}:{venue}:{posture}:{executability}"


def _compact_handoff_rationale(
    next_move_proposal: Mapping[str, Any],
    delegated_judgment: Mapping[str, Any],
) -> str:
    proposal_basis = next_move_proposal.get("basis")
    basis_map = proposal_basis if isinstance(proposal_basis, Mapping) else {}
    compact_rationale = str(basis_map.get("compact_rationale") or "").strip()
    if compact_rationale:
        return compact_rationale
    delegated_basis = delegated_judgment.get("basis")
    delegated_basis_map = delegated_basis if isinstance(delegated_basis, Mapping) else {}
    reasons = delegated_basis_map.get("signal_reasons")
    if isinstance(reasons, list) and reasons:
        return str(reasons[0])
    return "bounded_handoff_packet_derived_from_existing_orchestration_signals"


def _handoff_evidence_pointers(
    delegated_judgment: Mapping[str, Any],
) -> list[str]:
    delegated_basis = delegated_judgment.get("basis")
    delegated_basis_map = delegated_basis if isinstance(delegated_basis, Mapping) else {}
    pointers = [
        "glow/orchestration/orchestration_next_move_proposals.jsonl",
        "glow/orchestration/orchestration_handoffs.jsonl",
        "glow/orchestration/orchestration_intents.jsonl",
    ]
    artifacts = delegated_basis_map.get("artifacts_read")
    if isinstance(artifacts, Mapping):
        for value in artifacts.values():
            if isinstance(value, str) and value:
                pointers.append(value)
    seen: set[str] = set()
    ordered: list[str] = []
    for pointer in pointers:
        if pointer not in seen:
            ordered.append(pointer)
            seen.add(pointer)
    return ordered


def append_codex_work_order_ledger(repo_root: Path, work_order: Mapping[str, Any]) -> Path:
    ledger_path = repo_root.resolve() / "glow/orchestration/codex_work_orders.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(work_order), sort_keys=True) + "\n")
    return ledger_path


def append_deep_research_work_order_ledger(repo_root: Path, work_order: Mapping[str, Any]) -> Path:
    ledger_path = repo_root.resolve() / "glow/orchestration/deep_research_work_orders.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(work_order), sort_keys=True) + "\n")
    return ledger_path


def _build_staged_external_work_order(
    intent: Mapping[str, Any],
    *,
    handoff_outcome: str,
    created_at: str | None = None,
    venue: str,
    schema_version: str,
    work_order_prefix: str,
    direct_invocation_boundary_key: str,
) -> dict[str, Any]:
    timestamp = created_at or _iso_utc_now()
    source = intent.get("source_delegated_judgment")
    source_map = source if isinstance(source, Mapping) else {}
    posture = str(intent.get("required_authority_posture") or "insufficient_context_blocked")
    if handoff_outcome == "blocked_by_operator_requirement":
        status = "blocked_operator_required"
    elif handoff_outcome == "blocked_by_insufficient_context":
        status = "blocked_insufficient_context"
    else:
        status = "staged"

    if status not in _STAGED_EXTERNAL_WORK_ORDER_STATUSES:
        status = "blocked_insufficient_context"

    work_order = {
        "schema_version": schema_version,
        "recorded_at": timestamp,
        "venue": venue,
        "work_order_id": _staged_work_order_id(intent, timestamp, prefix=work_order_prefix),
        "source_intent_id": str(intent.get("intent_id") or ""),
        "source_intent_kind": str(intent.get("intent_kind") or ""),
        "source_judgment_linkage": {
            "source_judgment_linkage_id": _source_judgment_linkage_id(source_map),
            "recommended_venue": str(source_map.get("recommended_venue") or ""),
            "judgment_kind": "execution_venue_recommendation",
            "escalation_classification": str(source_map.get("escalation_classification") or ""),
            "work_class": str(source_map.get("work_class") or ""),
            "next_move_posture": str(source_map.get("next_move_posture") or "hold"),
            "consolidation_expansion_posture": str(source_map.get("consolidation_expansion_posture") or "insufficient_context"),
        },
        "operator_requirements": {
            "requires_operator_approval": bool(intent.get("requires_operator_approval")),
            "required_authority_posture": posture,
            "operator_escalation_classification": str(source_map.get("escalation_classification") or ""),
        },
        "executability_classification": str(intent.get("executability_classification") or "blocked_insufficient_context"),
        "readiness_basis": dict(source_map.get("readiness_basis") or {}),
        "status": status,
        "staged_only": True,
        "requires_external_tool_or_operator_trigger": True,
        **_anti_sovereignty_payload(
            recommendation_only=False,
            diagnostic_only=False,
            does_not_invoke_external_tools=True,
            additional_fields={
                "non_authoritative": True,
                "decision_power": "none",
            },
        ),
    }
    work_order[direct_invocation_boundary_key] = True
    return work_order


def build_codex_staged_work_order(
    intent: Mapping[str, Any],
    *,
    handoff_outcome: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    return _build_staged_external_work_order(
        intent,
        handoff_outcome=handoff_outcome,
        created_at=created_at,
        venue="codex_implementation",
        schema_version="codex_staged_work_order.v1",
        work_order_prefix="codex",
        direct_invocation_boundary_key="does_not_invoke_codex_directly",
    )


def build_deep_research_staged_work_order(
    intent: Mapping[str, Any],
    *,
    handoff_outcome: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    return _build_staged_external_work_order(
        intent,
        handoff_outcome=handoff_outcome,
        created_at=created_at,
        venue="deep_research_audit",
        schema_version="deep_research_staged_work_order.v1",
        work_order_prefix="deep-research",
        direct_invocation_boundary_key="does_not_invoke_deep_research_directly",
    )


def _resolve_staged_external_work_order_lifecycle(
    repo_root: Path,
    intent: Mapping[str, Any],
    handoff: Mapping[str, Any],
    *,
    venue: str,
    ledger_relative_path: str,
    schema_version: str,
    direct_invocation_boundary_key: str,
) -> dict[str, Any]:
    root = repo_root.resolve()
    intent_id = str(intent.get("intent_id") or "")
    ledger_path = root / ledger_relative_path
    records = _read_jsonl(ledger_path)
    linked = [row for row in records if str(row.get("source_intent_id") or "") == intent_id]
    latest = linked[-1] if linked else None
    handoff_outcome = str(handoff.get("handoff_outcome") or "")

    if latest is None:
        lifecycle_state = "fragmented_unlinked_work_order_state"
    elif handoff_outcome == "blocked_by_operator_requirement":
        lifecycle_state = "blocked_operator_required"
    elif handoff_outcome == "blocked_by_insufficient_context":
        lifecycle_state = "blocked_insufficient_context"
    elif str(latest.get("status") or "") == "staged":
        lifecycle_state = "staged_cleanly"
    elif str(latest.get("status") or "") == "fulfilled_externally_unverified":
        lifecycle_state = "fulfilled_externally_with_issues"
    else:
        lifecycle_state = "fragmented_unlinked_work_order_state"

    if lifecycle_state not in _STAGED_EXTERNAL_LIFECYCLE_STATES:
        lifecycle_state = "fragmented_unlinked_work_order_state"

    lifecycle = {
        "schema_version": schema_version,
        "intent_id": intent_id,
        "venue": venue,
        "lifecycle_state": lifecycle_state,
        "work_order_present": latest is not None,
        "work_order_id": str(latest.get("work_order_id") or "") if isinstance(latest, Mapping) else None,
        "work_order_status": str(latest.get("status") or "") if isinstance(latest, Mapping) else None,
        "proof_artifact_path": ledger_relative_path,
        "not_directly_executable_here": True,
        "staged_only": True,
        "requires_external_tool_or_operator_trigger": True,
        "operator_requirement_state": {
            "requires_operator_approval": bool(intent.get("requires_operator_approval")),
            "required_authority_posture": str(intent.get("required_authority_posture") or ""),
        },
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
        ),
    }
    lifecycle[direct_invocation_boundary_key] = True
    return lifecycle


def resolve_codex_staged_work_order_lifecycle(
    repo_root: Path,
    intent: Mapping[str, Any],
    handoff: Mapping[str, Any],
) -> dict[str, Any]:
    return _resolve_staged_external_work_order_lifecycle(
        repo_root,
        intent,
        handoff,
        venue="codex_implementation",
        ledger_relative_path="glow/orchestration/codex_work_orders.jsonl",
        schema_version="codex_staged_lifecycle.v1",
        direct_invocation_boundary_key="does_not_invoke_codex_directly",
    )


def resolve_deep_research_staged_work_order_lifecycle(
    repo_root: Path,
    intent: Mapping[str, Any],
    handoff: Mapping[str, Any],
) -> dict[str, Any]:
    return _resolve_staged_external_work_order_lifecycle(
        repo_root,
        intent,
        handoff,
        venue="deep_research_audit",
        ledger_relative_path="glow/orchestration/deep_research_work_orders.jsonl",
        schema_version="deep_research_staged_lifecycle.v1",
        direct_invocation_boundary_key="does_not_invoke_deep_research_directly",
    )


def append_orchestration_handoff_ledger(repo_root: Path, handoff: Mapping[str, Any]) -> Path:
    ledger_path = repo_root.resolve() / "glow/orchestration/orchestration_handoffs.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(handoff), sort_keys=True) + "\n")
    return ledger_path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def build_handoff_execution_gap_map(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    return {
        "schema_version": "orchestration_handoff_execution_gap.v1",
        "path": [
            "delegated_judgment",
            "orchestration_intent",
            "orchestration_handoff",
            "task_admission",
            "task_executor",
        ],
        "existing_downstream_result_source": {
            "surface": "logs/task_executor.jsonl",
            "event": "task_result",
            "status_values": ["completed", "failed"],
        },
        "stable_linkage_keys": {
            "intent_to_handoff": "intent_id",
            "handoff_to_execution_task": "details.task_admission.task_id",
            "execution_task_to_result": "task_id",
        },
        "stop_point_without_resolution": "handoff_outcome=admitted_to_execution_substrate",
        "minimal_missing_linkage": (
            "resolve admitted handoff task_id against task_executor task_result and classify "
            "orchestration result state."
        ),
        "proof_surfaces": {
            "intent_ledger": "glow/orchestration/orchestration_intents.jsonl",
            "handoff_ledger": "glow/orchestration/orchestration_handoffs.jsonl",
            "admission_log": str(task_admission._resolve_admission_log_path().relative_to(root))
            if task_admission._resolve_admission_log_path().is_relative_to(root)
            else str(task_admission._resolve_admission_log_path()),
            "executor_log": str(Path(task_executor.LOG_PATH).relative_to(root))
            if Path(task_executor.LOG_PATH).is_relative_to(root)
            else str(Path(task_executor.LOG_PATH)),
        },
    }


def resolve_orchestration_result(
    repo_root: Path,
    handoff: Mapping[str, Any],
    *,
    executor_log_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    handoff_outcome = str(handoff.get("handoff_outcome") or "")
    details = handoff.get("details")
    detail_map = details if isinstance(details, Mapping) else {}
    task_admission_details = detail_map.get("task_admission")
    admission_map = task_admission_details if isinstance(task_admission_details, Mapping) else {}
    task_id = str(admission_map.get("task_id") or "")
    log_path = executor_log_path or Path(task_executor.LOG_PATH)
    matching_rows = [row for row in _read_jsonl(log_path) if str(row.get("task_id") or "") == task_id]
    task_result_rows = [row for row in matching_rows if str(row.get("event") or "") == "task_result"]

    state = "handoff_not_admitted"
    execution_observed = False
    loop_closed = False

    if handoff_outcome == "admitted_to_execution_substrate":
        if not task_id:
            state = "execution_result_missing"
        elif task_result_rows:
            execution_observed = True
            latest = task_result_rows[-1]
            status = str(latest.get("status") or "")
            if status == "completed":
                state = "execution_succeeded"
                loop_closed = True
            elif status == "failed":
                state = "execution_failed"
                loop_closed = True
            else:
                state = "execution_result_missing"
        elif matching_rows:
            state = "execution_still_pending"
        else:
            state = "handoff_admitted_pending_result"

    if state not in _EXECUTION_RESULT_STATES:
        state = "execution_result_missing"

    intent_ref = dict(handoff.get("intent_ref") or {})
    codex_staged_lifecycle = None
    deep_research_staged_lifecycle = None
    if str(intent_ref.get("intent_kind") or "") == "codex_work_order":
        codex_staged_lifecycle = resolve_codex_staged_work_order_lifecycle(
            root,
            {
                "intent_id": str(intent_ref.get("intent_id") or ""),
                "required_authority_posture": str(detail_map.get("required_authority_posture") or ""),
                "requires_operator_approval": bool(detail_map.get("requires_operator_approval")),
            },
            handoff,
        )
    if str(intent_ref.get("intent_kind") or "") == "deep_research_work_order":
        deep_research_staged_lifecycle = resolve_deep_research_staged_work_order_lifecycle(
            root,
            {
                "intent_id": str(intent_ref.get("intent_id") or ""),
                "required_authority_posture": str(detail_map.get("required_authority_posture") or ""),
                "requires_operator_approval": bool(detail_map.get("requires_operator_approval")),
            },
            handoff,
        )

    return {
        "schema_version": "orchestration_result_resolution.v1",
        "resolved_at": _iso_utc_now(),
        "intent_ref": intent_ref,
        "handoff_outcome": handoff_outcome,
        "orchestration_result_state": state,
        "loop_closed": loop_closed,
        "execution_observed": execution_observed,
        "execution_task_ref": {
            "task_id": task_id or None,
            "executor_log_path": str(log_path.relative_to(root)) if log_path.is_relative_to(root) else str(log_path),
        },
        "result_evidence": {
            "task_rows_seen": len(matching_rows),
            "task_result_rows_seen": len(task_result_rows),
        },
        "codex_staged_lifecycle": codex_staged_lifecycle,
        "deep_research_staged_lifecycle": deep_research_staged_lifecycle,
    }


def build_split_closure_map() -> dict[str, Any]:
    """Return a compact audit map of current internal/external split closure semantics."""

    return {
        "schema_version": "orchestration_split_closure_map.v1",
        "split_closure_paths": {
            "internal_execution_path": {
                "source_artifacts": [
                    "glow/orchestration/orchestration_intents.jsonl",
                    "glow/orchestration/orchestration_handoffs.jsonl",
                    "logs/task_executor.jsonl task_result",
                ],
                "resolver_surface": "resolve_orchestration_result",
                "resolution_idiom": "orchestration_result_state",
                "shared_linkage_fields": [
                    "intent_ref.intent_id",
                    "intent_ref.intent_kind",
                    "handoff_outcome",
                ],
                "venue_specific_fields": [
                    "details.task_admission.task_id",
                    "execution_task_ref.task_id",
                    "result_evidence.task_result_rows_seen",
                ],
            },
            "external_fulfillment_path": {
                "source_artifacts": [
                    "glow/orchestration/orchestration_handoff_packets.jsonl",
                    "glow/orchestration/orchestration_fulfillment_receipts.jsonl",
                ],
                "resolver_surface": "resolve_handoff_packet_fulfillment_lifecycle",
                "resolution_idiom": "lifecycle_state",
                "shared_linkage_fields": [
                    "source_delegated_judgment_ref.source_judgment_linkage_id",
                    "target_venue",
                    "operator_escalation_requirement_state",
                ],
                "venue_specific_fields": [
                    "handoff_packet_id",
                    "fulfillment_receipt_id",
                    "ingested_external_outcome",
                    "does_not_imply_direct_repo_execution",
                ],
            },
        },
        "shared_semantics": [
            "append-only evidence surfaces",
            "non_authoritative and decision_power=none markers",
            "operator/escalation requirement visibility",
            "venue-aware staged-versus-executable boundaries",
        ],
        "divergence_points": [
            "internal closure keyed by task_result status, external closure keyed by fulfillment_kind/lifecycle_state",
            "internal closure uses handoff->task linkage; external closure uses handoff_packet->receipt linkage",
            "internal success implies observed in-repo execution result event; external fulfillment does not imply direct repo execution",
        ],
    }


def _unified_result_id(
    *,
    intent_id: str,
    handoff_outcome: str,
    handoff_packet_id: str,
    venue: str,
    resolution_path: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            {
                "intent_id": intent_id,
                "handoff_outcome": handoff_outcome,
                "handoff_packet_id": handoff_packet_id,
                "venue": venue,
                "resolution_path": resolution_path,
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    return f"oru-{digest.hexdigest()[:16]}"


def _classify_internal_resolution(
    handoff: Mapping[str, Any],
    internal_resolution: Mapping[str, Any],
) -> str:
    state = str(internal_resolution.get("orchestration_result_state") or "execution_result_missing")
    handoff_outcome = str(handoff.get("handoff_outcome") or "")
    if state == "execution_succeeded":
        return "completed_successfully"
    if state == "execution_failed":
        return "failed_after_execution"
    if state in {"handoff_admitted_pending_result", "execution_still_pending"}:
        return "pending_or_unresolved"
    if state == "execution_result_missing":
        return "fragmented_result_history"
    if handoff_outcome in {
        "blocked_by_admission",
        "blocked_by_operator_requirement",
        "blocked_by_insufficient_context",
        "execution_target_unavailable",
    }:
        return "blocked_before_execution"
    return "pending_or_unresolved"


def _classify_external_lifecycle(lifecycle_state: str) -> str:
    classification = {
        "fulfilled_externally": "completed_successfully",
        "fulfilled_externally_with_issues": "completed_with_issues",
        "externally_declined": "declined_or_abandoned",
        "externally_abandoned": "declined_or_abandoned",
        "externally_result_unusable": "failed_after_execution",
        "blocked_operator_required": "blocked_before_execution",
        "blocked_insufficient_context": "blocked_before_execution",
        "staged_cleanly": "pending_or_unresolved",
        "fragmented_unlinked_work_order_state": "fragmented_result_history",
    }.get(lifecycle_state, "fragmented_result_history")
    if classification not in _UNIFIED_RESULT_CLASSIFICATIONS:
        return "fragmented_result_history"
    return classification


def resolve_unified_orchestration_result(
    repo_root: Path,
    *,
    handoff: Mapping[str, Any] | None = None,
    handoff_packet: Mapping[str, Any] | None = None,
    executor_log_path: Path | None = None,
) -> dict[str, Any]:
    """
    Resolve one bounded venue-aware orchestration result over internal or external closure paths.

    This resolver unifies result shape while preserving path semantics.
    """

    root = repo_root.resolve()
    handoff_map = handoff if isinstance(handoff, Mapping) else {}
    packet_map = handoff_packet if isinstance(handoff_packet, Mapping) else {}
    intent_ref = handoff_map.get("intent_ref")
    intent_ref_map = intent_ref if isinstance(intent_ref, Mapping) else {}
    intent_id = str(intent_ref_map.get("intent_id") or "")
    intent_kind = str(intent_ref_map.get("intent_kind") or "")
    handoff_outcome = str(handoff_map.get("handoff_outcome") or "")
    target_venue = str(packet_map.get("target_venue") or "")
    packet_id = str(packet_map.get("handoff_packet_id") or "")

    is_external = target_venue in {"codex_implementation", "deep_research_audit"} or intent_kind in {
        "codex_work_order",
        "deep_research_work_order",
    }
    resolution_path = "external_fulfillment" if is_external else "internal_execution"
    if resolution_path not in _UNIFIED_RESULT_RESOLUTION_PATHS:
        resolution_path = "internal_execution"

    classification = "fragmented_result_history"
    task_result_observed = False
    fulfillment_receipt_observed = False
    result_state = "fragmented_unlinked_work_order_state" if is_external else "execution_result_missing"
    internal_resolution: dict[str, Any] | None = None
    external_lifecycle: dict[str, Any] | None = None
    fragmented_linkage = False

    if resolution_path == "internal_execution":
        if not handoff_map:
            fragmented_linkage = True
        else:
            internal_resolution = resolve_orchestration_result(root, handoff_map, executor_log_path=executor_log_path)
            result_state = str(internal_resolution.get("orchestration_result_state") or "execution_result_missing")
            task_result_observed = bool(internal_resolution.get("execution_observed"))
            classification = _classify_internal_resolution(handoff_map, internal_resolution)
            if not intent_id:
                fragmented_linkage = True
    else:
        if not packet_map:
            fragmented_linkage = True
        else:
            external_lifecycle = resolve_handoff_packet_fulfillment_lifecycle(root, packet_map)
            lifecycle_state = str(external_lifecycle.get("lifecycle_state") or "fragmented_unlinked_work_order_state")
            result_state = lifecycle_state
            fulfillment_receipt_observed = bool(external_lifecycle.get("fulfillment_received"))
            classification = _classify_external_lifecycle(lifecycle_state)
            if not packet_id:
                fragmented_linkage = True
            if not handoff_map:
                fragmented_linkage = True

    if fragmented_linkage:
        classification = "fragmented_result_history"
    if classification not in _UNIFIED_RESULT_CLASSIFICATIONS:
        classification = "fragmented_result_history"

    operator_state = (
        packet_map.get("operator_escalation_requirement_state")
        if isinstance(packet_map.get("operator_escalation_requirement_state"), Mapping)
        else handoff_map.get("details", {})
        if isinstance(handoff_map.get("details"), Mapping)
        else {}
    )
    operator_state_map = operator_state if isinstance(operator_state, Mapping) else {}
    venue = target_venue or (
        "task_admission_executor"
        if resolution_path == "internal_execution"
        else "insufficient_context"
    )

    result = {
        "schema_version": "orchestration_unified_result.v1",
        "resolved_at": _iso_utc_now(),
        "orchestration_result_id": _unified_result_id(
            intent_id=intent_id,
            handoff_outcome=handoff_outcome,
            handoff_packet_id=packet_id,
            venue=venue,
            resolution_path=resolution_path,
        ),
        "source_intent_ref": {
            "intent_id": intent_id or None,
            "intent_kind": intent_kind or None,
            "intent_ledger_path": "glow/orchestration/orchestration_intents.jsonl",
        },
        "source_linkage": {
            "handoff_outcome": handoff_outcome or None,
            "handoff_ledger_path": "glow/orchestration/orchestration_handoffs.jsonl" if handoff_map else None,
            "handoff_packet_id": packet_id or None,
            "handoff_packet_ledger_path": "glow/orchestration/orchestration_handoff_packets.jsonl" if packet_map else None,
        },
        "venue": venue,
        "resolution_path": resolution_path,
        "result_classification": classification,
        "resolution_state": result_state,
        "evidence_presence": {
            "task_result_observed": task_result_observed,
            "fulfillment_receipt_observed": fulfillment_receipt_observed,
            "proof_linkage_present": not fragmented_linkage,
            "fragmented_linkage": fragmented_linkage,
        },
        "operator_escalation_context": {
            "requires_operator_or_escalation": bool(operator_state_map.get("requires_operator_or_escalation")),
            "requires_operator_approval": bool(operator_state_map.get("requires_operator_approval")),
            "escalation_classification": str(operator_state_map.get("escalation_classification") or ""),
        },
        "path_honesty": {
            "ingested_external_outcome": bool((external_lifecycle or {}).get("ingested_external_outcome")),
            "does_not_imply_direct_repo_execution": resolution_path == "external_fulfillment",
            "task_result_observed": task_result_observed,
            "fulfillment_receipt_observed": fulfillment_receipt_observed,
        },
        "non_authoritative": True,
        "decision_power": "none",
    }
    if internal_resolution is not None:
        result["internal_resolution"] = internal_resolution
    if external_lifecycle is not None:
        result["external_fulfillment_lifecycle"] = external_lifecycle
    return result


def _recent_external_fulfillment_summary(
    repo_root: Path,
    recent_intents: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Collect compact external fulfillment evidence linked to recent external intents."""

    root = repo_root.resolve()
    external_intents = [
        row
        for row in recent_intents
        if str(row.get("intent_kind") or "") in {"codex_work_order", "deep_research_work_order"}
    ]
    linkage_ids = {
        _source_judgment_linkage_id(row.get("source_delegated_judgment", {}))
        for row in external_intents
    }
    linkage_ids.discard("")

    packets = _read_jsonl(root / "glow/orchestration/orchestration_handoff_packets.jsonl")
    receipts = _read_jsonl(root / "glow/orchestration/orchestration_fulfillment_receipts.jsonl")
    recent_packets = [
        row
        for row in packets
        if str((row.get("source_delegated_judgment_ref") or {}).get("source_judgment_linkage_id") or "") in linkage_ids
        and str(row.get("target_venue") or "") in {"codex_implementation", "deep_research_audit"}
    ]
    packet_by_id = {
        str(row.get("handoff_packet_id") or ""): row
        for row in recent_packets
        if str(row.get("handoff_packet_id") or "")
    }
    latest_receipt_by_packet: dict[str, dict[str, Any]] = {}
    for row in receipts:
        packet_id = str((row.get("source_handoff_packet_ref") or {}).get("handoff_packet_id") or "")
        if packet_id and packet_id in packet_by_id and isinstance(row, Mapping):
            latest_receipt_by_packet[packet_id] = dict(row)

    by_kind = {
        "fulfilled_externally": 0,
        "fulfilled_externally_with_issues": 0,
        "externally_declined": 0,
        "externally_abandoned": 0,
        "externally_result_unusable": 0,
    }
    by_venue = {
        "codex_implementation": {
            "healthy": 0,
            "stressed": 0,
            "blocked_or_unusable": 0,
            "fulfilled_externally": 0,
            "fulfilled_externally_with_issues": 0,
            "externally_declined": 0,
            "externally_abandoned": 0,
            "externally_result_unusable": 0,
        },
        "deep_research_audit": {
            "healthy": 0,
            "stressed": 0,
            "blocked_or_unusable": 0,
            "fulfilled_externally": 0,
            "fulfilled_externally_with_issues": 0,
            "externally_declined": 0,
            "externally_abandoned": 0,
            "externally_result_unusable": 0,
        },
    }
    for packet_id, receipt in latest_receipt_by_packet.items():
        fulfillment_kind = str(receipt.get("fulfillment_kind") or "")
        mapped_kind = {
            "externally_completed": "fulfilled_externally",
            "externally_completed_with_issues": "fulfilled_externally_with_issues",
            "externally_declined": "externally_declined",
            "externally_abandoned": "externally_abandoned",
            "externally_result_unusable": "externally_result_unusable",
        }.get(fulfillment_kind)
        if not mapped_kind:
            continue
        by_kind[mapped_kind] += 1
        venue = str(packet_by_id.get(packet_id, {}).get("target_venue") or "")
        venue_bucket = by_venue.get(venue)
        if venue_bucket is None:
            continue
        venue_bucket[mapped_kind] += 1
        if mapped_kind == "fulfilled_externally":
            venue_bucket["healthy"] += 1
        elif mapped_kind == "fulfilled_externally_with_issues":
            venue_bucket["stressed"] += 1
        else:
            venue_bucket["blocked_or_unusable"] += 1

    healthy = by_kind["fulfilled_externally"]
    stressed = by_kind["fulfilled_externally_with_issues"] + by_kind["externally_result_unusable"]
    blocked_or_unusable = by_kind["externally_declined"] + by_kind["externally_abandoned"] + by_kind["externally_result_unusable"]

    return {
        "recent_external_intents_considered": len(external_intents),
        "recent_external_packets_considered": len(recent_packets),
        "receipts_linked": len(latest_receipt_by_packet),
        "receipts_missing_for_recent_packets": max(0, len(recent_packets) - len(latest_receipt_by_packet)),
        "by_kind": by_kind,
        "by_venue": by_venue,
        "healthy_receipt_count": healthy,
        "stressed_receipt_count": stressed,
        "blocked_or_unusable_receipt_count": blocked_or_unusable,
        "has_external_feedback_signal": len(latest_receipt_by_packet) > 0,
    }


def resolve_unified_orchestration_result_surface(
    repo_root: Path,
    *,
    window_size: int = 10,
    executor_log_path: Path | None = None,
) -> dict[str, Any]:
    """Return an inspectable bounded unified result surface over recent orchestration records."""

    root = repo_root.resolve()
    intents = _read_jsonl(root / "glow/orchestration/orchestration_intents.jsonl")
    handoffs = _read_jsonl(root / "glow/orchestration/orchestration_handoffs.jsonl")
    packets = _read_jsonl(root / "glow/orchestration/orchestration_handoff_packets.jsonl")
    intent_map = {
        str(row.get("intent_id") or ""): row
        for row in intents
        if str(row.get("intent_id") or "")
    }
    packet_linkage: dict[tuple[str, str], dict[str, Any]] = {}
    for packet in packets:
        linkage = str((packet.get("source_delegated_judgment_ref") or {}).get("source_judgment_linkage_id") or "")
        venue = str(packet.get("target_venue") or "")
        if linkage and venue in {"codex_implementation", "deep_research_audit"} and isinstance(packet, Mapping):
            packet_linkage[(linkage, venue)] = dict(packet)

    scoped_handoffs: list[dict[str, Any]] = []
    for handoff in handoffs:
        intent_ref = handoff.get("intent_ref")
        intent_ref_map = intent_ref if isinstance(intent_ref, Mapping) else {}
        if str(intent_ref_map.get("intent_id") or "") in intent_map:
            scoped_handoffs.append(handoff)
    recent_handoffs = scoped_handoffs[-max(0, window_size) :] if window_size > 0 else []

    unified_rows: list[dict[str, Any]] = []
    for handoff in recent_handoffs:
        intent_id = str((handoff.get("intent_ref") or {}).get("intent_id") or "")
        intent = intent_map.get(intent_id, {})
        linkage_id = _source_judgment_linkage_id(intent.get("source_delegated_judgment", {}))
        venue = ""
        intent_kind = str((handoff.get("intent_ref") or {}).get("intent_kind") or "")
        if intent_kind == "codex_work_order":
            venue = "codex_implementation"
        elif intent_kind == "deep_research_work_order":
            venue = "deep_research_audit"
        packet = packet_linkage.get((linkage_id, venue)) if linkage_id and venue else None
        unified_rows.append(
            resolve_unified_orchestration_result(
                root,
                handoff=handoff,
                handoff_packet=packet,
                executor_log_path=executor_log_path,
            )
        )

    classification_counts = {name: 0 for name in _UNIFIED_RESULT_CLASSIFICATIONS}
    resolution_path_counts = {name: 0 for name in _UNIFIED_RESULT_RESOLUTION_PATHS}
    fragmented_count = 0
    for row in unified_rows:
        classification = str(row.get("result_classification") or "fragmented_result_history")
        if classification not in classification_counts:
            classification = "fragmented_result_history"
        classification_counts[classification] += 1
        path = str(row.get("resolution_path") or "internal_execution")
        if path not in resolution_path_counts:
            path = "internal_execution"
        resolution_path_counts[path] += 1
        if bool((row.get("evidence_presence") or {}).get("fragmented_linkage")):
            fragmented_count += 1

    return {
        "schema_version": "orchestration_unified_result_surface.v1",
        "window_size": max(0, window_size),
        "records_considered": len(unified_rows),
        "results": unified_rows,
        "result_classification_counts": classification_counts,
        "resolution_path_counts": resolution_path_counts,
        "fragmented_linkage_count": fragmented_count,
        "artifacts_read": {
            "intent_ledger": "glow/orchestration/orchestration_intents.jsonl",
            "handoff_ledger": "glow/orchestration/orchestration_handoffs.jsonl",
            "handoff_packet_ledger": "glow/orchestration/orchestration_handoff_packets.jsonl",
            "fulfillment_receipt_ledger": "glow/orchestration/orchestration_fulfillment_receipts.jsonl",
            "executor_log": str((executor_log_path or Path(task_executor.LOG_PATH)).relative_to(root))
            if (executor_log_path or Path(task_executor.LOG_PATH)).is_relative_to(root)
            else str(executor_log_path or Path(task_executor.LOG_PATH)),
        },
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={"resolver_only": True},
        ),
    }


def derive_unified_result_quality_review(
    repo_root: Path,
    *,
    window_size: int = 10,
    executor_log_path: Path | None = None,
) -> dict[str, Any]:
    """Derive a compact retrospective quality classifier over recent unified orchestration results."""

    unified_surface = resolve_unified_orchestration_result_surface(
        repo_root,
        window_size=window_size,
        executor_log_path=executor_log_path,
    )
    records_considered = int(unified_surface.get("records_considered") or 0)
    counts_raw = unified_surface.get("result_classification_counts")
    counts_map = counts_raw if isinstance(counts_raw, Mapping) else {}
    path_counts_raw = unified_surface.get("resolution_path_counts")
    path_counts_map = path_counts_raw if isinstance(path_counts_raw, Mapping) else {}
    fragmented_linkage_count = int(unified_surface.get("fragmented_linkage_count") or 0)

    classification_counts = {name: int(counts_map.get(name) or 0) for name in _UNIFIED_RESULT_CLASSIFICATIONS}
    resolution_path_counts = {name: int(path_counts_map.get(name) or 0) for name in _UNIFIED_RESULT_RESOLUTION_PATHS}

    success_count = classification_counts["completed_successfully"]
    issue_count = classification_counts["completed_with_issues"] + classification_counts["failed_after_execution"]
    abandonment_count = classification_counts["declined_or_abandoned"]
    fragmentation_count = classification_counts["fragmented_result_history"] + classification_counts["pending_or_unresolved"]
    internal_count = resolution_path_counts["internal_execution"]
    external_count = resolution_path_counts["external_fulfillment"]
    path_total = internal_count + external_count

    success_ratio = (success_count / records_considered) if records_considered else 0.0
    issue_ratio = (issue_count / records_considered) if records_considered else 0.0
    abandonment_ratio = (abandonment_count / records_considered) if records_considered else 0.0
    fragmentation_ratio = (fragmentation_count / records_considered) if records_considered else 0.0
    internal_ratio = (internal_count / path_total) if path_total else 0.0
    external_ratio = (external_count / path_total) if path_total else 0.0

    issue_heavy = issue_count >= 2 and issue_ratio >= 0.5
    abandonment_heavy = abandonment_count >= 2 and abandonment_ratio >= 0.4
    fragmentation_heavy = (fragmentation_count >= 2 and fragmentation_ratio >= 0.5) or (
        fragmented_linkage_count >= 2 and fragmentation_ratio >= 0.4
    )
    stress_flag_count = sum(1 for flag in (issue_heavy, abandonment_heavy, fragmentation_heavy) if flag)
    healthy_pattern = success_count >= 2 and success_ratio >= 0.6 and stress_flag_count == 0

    classification = "insufficient_history"
    if records_considered >= 3:
        if stress_flag_count >= 2:
            classification = "mixed_result_stress"
        elif issue_heavy:
            classification = "issues_heavy"
        elif abandonment_heavy:
            classification = "abandonment_or_decline_heavy"
        elif fragmentation_heavy:
            classification = "fragmentation_heavy"
        elif healthy_pattern:
            classification = "healthy_recent_results"
        else:
            classification = "mixed_result_stress"

    if classification not in _UNIFIED_RESULT_QUALITY_REVIEW_CLASSES:
        classification = "mixed_result_stress"

    health_vs_stress = (
        "healthy"
        if classification == "healthy_recent_results"
        else ("insufficient_evidence" if classification == "insufficient_history" else "stressed")
    )

    return {
        "schema_version": "unified_result_quality_review.v1",
        "review_kind": "unified_result_quality_retrospective",
        "review_classification": classification,
        "window_size": max(0, window_size),
        "records_considered": records_considered,
        "recent_unified_result_counts": classification_counts,
        "recent_resolution_path_counts": resolution_path_counts,
        "condition_flags": {
            "issues_heavy": issue_heavy,
            "abandonment_or_decline_heavy": abandonment_heavy,
            "fragmentation_heavy": fragmentation_heavy,
            "multiple_competing_stress_patterns": stress_flag_count >= 2,
            "healthy_pattern": healthy_pattern,
        },
        "summary": {
            "health_vs_stress": health_vs_stress,
            "path_mix": {
                "internal_execution_count": internal_count,
                "external_fulfillment_count": external_count,
                "internal_execution_ratio": round(internal_ratio, 4),
                "external_fulfillment_ratio": round(external_ratio, 4),
            },
            "basis": {
                "success_count": success_count,
                "issue_count": issue_count,
                "abandonment_or_decline_count": abandonment_count,
                "fragmentation_or_unresolved_count": fragmentation_count,
                "fragmented_linkage_count": fragmented_linkage_count,
                "success_ratio": round(success_ratio, 4),
                "issue_ratio": round(issue_ratio, 4),
                "abandonment_or_decline_ratio": round(abandonment_ratio, 4),
                "fragmentation_or_unresolved_ratio": round(fragmentation_ratio, 4),
            },
            "compact_reason": (
                "recent unified results are mostly successful across available paths"
                if classification == "healthy_recent_results"
                else (
                    "recent unified results show repeated issue/failure outcomes"
                    if classification == "issues_heavy"
                    else (
                        "recent unified results show repeated decline/abandonment outcomes"
                        if classification == "abandonment_or_decline_heavy"
                        else (
                            "recent unified results show repeated unresolved or fragmented closure"
                            if classification == "fragmentation_heavy"
                            else (
                                "recent unified results show competing stress signatures"
                                if classification == "mixed_result_stress"
                                else "recent unified history is too small for a stable quality classification"
                            )
                        )
                    )
                )
            ),
            "boundaries": {
                "review_only": True,
                "diagnostic_only": True,
                "decision_power": "none",
                "non_authoritative": True,
                "does_not_change_admission_or_execution_authority": True,
                "does_not_add_or_invoke_any_new_venue": True,
                "preserves_resolution_path_honesty": True,
            },
        },
        "artifacts_read": {
            "unified_result_surface": "resolve_unified_orchestration_result_surface",
        },
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "review_only": True,
                "does_not_change_admission_or_execution_authority": True,
            },
        ),
    }


def derive_orchestration_outcome_review(
    repo_root: Path,
    *,
    window_size: int = 10,
    executor_log_path: Path | None = None,
) -> dict[str, Any]:
    """Derive a bounded retrospective review over recent orchestration outcomes."""

    root = repo_root.resolve()
    intents = _read_jsonl(root / "glow/orchestration/orchestration_intents.jsonl")
    handoffs = _read_jsonl(root / "glow/orchestration/orchestration_handoffs.jsonl")
    intent_ids = {str(row.get("intent_id") or "") for row in intents}
    scoped_handoffs: list[dict[str, Any]] = []
    for handoff in handoffs:
        intent_ref = handoff.get("intent_ref")
        intent_ref_map = intent_ref if isinstance(intent_ref, Mapping) else {}
        intent_id = str(intent_ref_map.get("intent_id") or "")
        if intent_id and intent_id in intent_ids:
            scoped_handoffs.append(handoff)

    recent_handoffs = scoped_handoffs[-max(0, window_size) :] if window_size > 0 else []
    recent_intent_ids = {
        str((row.get("intent_ref") or {}).get("intent_id") or "")
        for row in recent_handoffs
    }
    recent_intents = [
        row
        for row in intents
        if str(row.get("intent_id") or "") in recent_intent_ids
    ]
    recent_resolutions = [
        resolve_orchestration_result(root, handoff, executor_log_path=executor_log_path)
        for handoff in recent_handoffs
    ]
    unified_surface = resolve_unified_orchestration_result_surface(
        root,
        window_size=window_size,
        executor_log_path=executor_log_path,
    )
    unified_results = list(unified_surface.get("results") or [])
    external_summary = _recent_external_fulfillment_summary(root, recent_intents)

    outcome_counts = {
        "execution_succeeded": 0,
        "execution_failed": 0,
        "handoff_admitted_pending_result": 0,
        "execution_still_pending": 0,
        "execution_result_missing": 0,
        "handoff_not_admitted": 0,
    }
    blocked_handoffs = 0
    admitted_handoffs = 0
    for idx, resolution in enumerate(recent_resolutions):
        state = str(resolution.get("orchestration_result_state") or "execution_result_missing")
        if state not in outcome_counts:
            state = "execution_result_missing"
        outcome_counts[state] += 1

        handoff_outcome = str(recent_handoffs[idx].get("handoff_outcome") or "")
        if handoff_outcome in {
            "blocked_by_admission",
            "blocked_by_operator_requirement",
            "blocked_by_insufficient_context",
            "execution_target_unavailable",
        }:
            blocked_handoffs += 1
        if handoff_outcome == "admitted_to_execution_substrate":
            admitted_handoffs += 1

    unified_counts = {name: 0 for name in _UNIFIED_RESULT_CLASSIFICATIONS}
    unified_path_counts = {name: 0 for name in _UNIFIED_RESULT_RESOLUTION_PATHS}
    for unified in unified_results:
        classification = str(unified.get("result_classification") or "fragmented_result_history")
        if classification not in unified_counts:
            classification = "fragmented_result_history"
        unified_counts[classification] += 1
        path = str(unified.get("resolution_path") or "internal_execution")
        if path not in unified_path_counts:
            path = "internal_execution"
        unified_path_counts[path] += 1

    records_considered = len(unified_results) if unified_results else len(recent_resolutions)
    success_count = unified_counts["completed_successfully"]
    failure_count = unified_counts["failed_after_execution"] + unified_counts["completed_with_issues"]
    pending_count = unified_counts["pending_or_unresolved"] + unified_counts["fragmented_result_history"]
    block_ratio = (blocked_handoffs / records_considered) if records_considered else 0.0
    success_ratio = (success_count / records_considered) if records_considered else 0.0
    failure_ratio = (failure_count / records_considered) if records_considered else 0.0
    pending_ratio = (pending_count / records_considered) if records_considered else 0.0

    blocked_heavy = blocked_handoffs >= 2 and block_ratio >= 0.6
    failure_heavy = admitted_handoffs >= 3 and failure_count >= 2 and failure_ratio >= 0.5
    stall_heavy = admitted_handoffs >= 3 and pending_count >= 2 and pending_ratio >= 0.5
    external_healthy = int(external_summary.get("healthy_receipt_count") or 0)
    external_stressed = int(external_summary.get("stressed_receipt_count") or 0)
    external_blocked_or_unusable = int(external_summary.get("blocked_or_unusable_receipt_count") or 0)
    external_signal_present = bool(external_summary.get("has_external_feedback_signal"))
    external_stress_heavy = external_signal_present and (external_stressed + external_blocked_or_unusable) >= 2 and (
        external_stressed + external_blocked_or_unusable
    ) >= external_healthy
    external_healthy_support = external_signal_present and external_healthy >= 2 and (
        external_stressed + external_blocked_or_unusable
    ) == 0

    classification = "insufficient_history"
    if records_considered >= 3:
        if blocked_heavy:
            classification = "handoff_block_heavy"
        elif failure_heavy:
            classification = "execution_failure_heavy"
        elif stall_heavy:
            classification = "pending_stall_pattern"
        elif success_count >= 2 and success_ratio >= 0.6:
            classification = "clean_recent_orchestration"
        elif external_healthy_support:
            classification = "clean_recent_orchestration"
        else:
            classification = "mixed_orchestration_stress"

    if classification not in _ORCHESTRATION_REVIEW_CLASSES:
        classification = "mixed_orchestration_stress"

    return {
        "schema_version": "orchestration_outcome_review.v1",
        "review_kind": "orchestration_outcome_retrospective",
        "review_classification": classification,
        "window_size": max(0, window_size),
        "records_considered": records_considered,
        "recent_outcome_counts": outcome_counts,
        "unified_result_counts": unified_counts,
        "unified_resolution_path_counts": unified_path_counts,
        "condition_flags": {
            "blocked_heavy": blocked_heavy,
            "failure_heavy": failure_heavy,
            "stall_heavy": stall_heavy,
            "external_feedback_signal_present": external_signal_present,
            "external_stress_heavy": external_stress_heavy,
            "external_healthy_support": external_healthy_support,
        },
        "external_fulfillment_outcome_counts": dict(external_summary.get("by_kind") or {}),
        "summary": {
            "recent_pattern": "healthy_bounded_orchestration"
            if classification == "clean_recent_orchestration"
            else "orchestration_stress_or_uncertainty",
            "diagnostic_summary": "bounded retrospective review derived from internal orchestration artifacts plus external fulfillment receipt outcomes when linked",
            "external_fulfillment_influence": {
                "influenced_outcome_review": external_signal_present,
                "influence_mode": "healthy_support"
                if external_healthy_support
                else ("stress_signal" if external_stress_heavy else ("present_no_strong_shift" if external_signal_present else "none")),
                "healthy_receipt_count": external_healthy,
                "stressed_receipt_count": external_stressed,
                "blocked_or_unusable_receipt_count": external_blocked_or_unusable,
            },
        },
        "artifacts_read": {
            "intent_ledger": "glow/orchestration/orchestration_intents.jsonl",
            "handoff_ledger": "glow/orchestration/orchestration_handoffs.jsonl",
            "executor_log": str((executor_log_path or Path(task_executor.LOG_PATH)).relative_to(root))
            if (executor_log_path or Path(task_executor.LOG_PATH)).is_relative_to(root)
            else str(executor_log_path or Path(task_executor.LOG_PATH)),
            "handoff_packet_ledger": "glow/orchestration/orchestration_handoff_packets.jsonl",
            "fulfillment_receipt_ledger": "glow/orchestration/orchestration_fulfillment_receipts.jsonl",
            "unified_result_surface": "resolve_unified_orchestration_result_surface",
        },
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "review_only": True,
                "does_not_change_admission_or_execution_authority": True,
            },
        ),
    }


def derive_orchestration_venue_mix_review(
    repo_root: Path,
    *,
    window_size: int = 10,
) -> dict[str, Any]:
    """Derive a bounded retrospective classifier over recent orchestration venue mix."""

    root = repo_root.resolve()
    intents = _read_jsonl(root / "glow/orchestration/orchestration_intents.jsonl")
    handoffs = _read_jsonl(root / "glow/orchestration/orchestration_handoffs.jsonl")
    codex_work_orders = _read_jsonl(root / "glow/orchestration/codex_work_orders.jsonl")
    deep_research_work_orders = _read_jsonl(root / "glow/orchestration/deep_research_work_orders.jsonl")

    intent_map: dict[str, dict[str, Any]] = {}
    for row in intents:
        intent_id = str(row.get("intent_id") or "")
        if intent_id:
            intent_map[intent_id] = row

    scoped_handoffs: list[dict[str, Any]] = []
    for handoff in handoffs:
        intent_ref = handoff.get("intent_ref")
        intent_ref_map = intent_ref if isinstance(intent_ref, Mapping) else {}
        intent_id = str(intent_ref_map.get("intent_id") or "")
        if intent_id and intent_id in intent_map:
            scoped_handoffs.append(handoff)

    recent_handoffs = scoped_handoffs[-max(0, window_size) :] if window_size > 0 else []
    recent_intent_ids: set[str] = set()
    venue_counts = {
        "task_admission_executor": 0,
        "codex_implementation": 0,
        "deep_research_audit": 0,
    }
    operator_required_count = 0
    blocked_count = 0

    for handoff in recent_handoffs:
        intent_ref = handoff.get("intent_ref")
        intent_ref_map = intent_ref if isinstance(intent_ref, Mapping) else {}
        details = handoff.get("details")
        details_map = details if isinstance(details, Mapping) else {}
        intent_id = str(intent_ref_map.get("intent_id") or "")
        intent_kind = str(intent_ref_map.get("intent_kind") or "")
        intent = intent_map.get(intent_id, {})
        recent_intent_ids.add(intent_id)

        if intent_kind == "internal_maintenance_execution":
            venue_counts["task_admission_executor"] += 1
        elif intent_kind == "codex_work_order":
            venue_counts["codex_implementation"] += 1
        elif intent_kind == "deep_research_work_order":
            venue_counts["deep_research_audit"] += 1

        handoff_outcome = str(handoff.get("handoff_outcome") or "")
        required_authority_posture = str(details_map.get("required_authority_posture") or intent.get("required_authority_posture") or "")
        escalation_classification = str(
            intent.get("source_delegated_judgment", {}).get("escalation_classification")
            if isinstance(intent.get("source_delegated_judgment"), Mapping)
            else ""
        )

        if (
            required_authority_posture in {"operator_priority_required", "insufficient_context_blocked"}
            or handoff_outcome in {"blocked_by_operator_requirement", "blocked_by_insufficient_context"}
            or intent_kind == "operator_review_request"
            or escalation_classification in {"escalate_for_missing_context", "escalate_for_operator_priority"}
        ):
            operator_required_count += 1

        if handoff_outcome in {
            "blocked_by_admission",
            "blocked_by_operator_requirement",
            "blocked_by_insufficient_context",
            "execution_target_unavailable",
        }:
            blocked_count += 1

    recent_intents = [
        row
        for row in intents
        if str(row.get("intent_id") or "") in recent_intent_ids
    ]
    external_summary = _recent_external_fulfillment_summary(root, recent_intents)

    records_considered = len(recent_handoffs)
    total_primary_venue = sum(venue_counts.values())
    internal_ratio = (venue_counts["task_admission_executor"] / total_primary_venue) if total_primary_venue else 0.0
    codex_ratio = (venue_counts["codex_implementation"] / total_primary_venue) if total_primary_venue else 0.0
    deep_ratio = (venue_counts["deep_research_audit"] / total_primary_venue) if total_primary_venue else 0.0
    operator_ratio = (operator_required_count / records_considered) if records_considered else 0.0
    blocked_ratio = (blocked_count / records_considered) if records_considered else 0.0

    internal_heavy = venue_counts["task_admission_executor"] >= 2 and internal_ratio >= 0.6
    codex_heavy = venue_counts["codex_implementation"] >= 2 and codex_ratio >= 0.6
    deep_research_heavy = venue_counts["deep_research_audit"] >= 2 and deep_ratio >= 0.6
    operator_heavy = operator_required_count >= 2 and operator_ratio >= 0.5
    external_healthy = int(external_summary.get("healthy_receipt_count") or 0)
    external_stressed = int(external_summary.get("stressed_receipt_count") or 0)
    external_blocked_or_unusable = int(external_summary.get("blocked_or_unusable_receipt_count") or 0)
    external_signal_present = bool(external_summary.get("has_external_feedback_signal"))
    external_quality_stressed = external_signal_present and (external_stressed + external_blocked_or_unusable) >= 2 and (
        external_stressed + external_blocked_or_unusable
    ) > external_healthy
    dominant_flags = [internal_heavy, codex_heavy, deep_research_heavy, operator_heavy]
    heavy_pattern_count = sum(1 for flag in dominant_flags if flag)

    classification = "insufficient_history"
    if records_considered >= 3:
        active_primary_venues = sum(1 for count in venue_counts.values() if count > 0)
        balanced_primary_spread = (
            active_primary_venues >= 2
            and max(venue_counts.values()) - min(venue_counts.values()) <= 2
            and not operator_heavy
        )
        if heavy_pattern_count >= 2:
            classification = "mixed_venue_stress"
        elif operator_heavy:
            classification = "operator_escalation_heavy"
        elif internal_heavy:
            classification = "internal_execution_heavy"
        elif codex_heavy:
            classification = "codex_heavy"
        elif deep_research_heavy:
            classification = "deep_research_heavy"
        elif balanced_primary_spread and blocked_ratio < 0.4:
            classification = "balanced_recent_venue_mix"
        else:
            classification = "mixed_venue_stress"
        if classification in {"codex_heavy", "deep_research_heavy", "balanced_recent_venue_mix"} and external_quality_stressed:
            classification = "mixed_venue_stress"

    if classification not in _ORCHESTRATION_VENUE_MIX_CLASSES:
        classification = "mixed_venue_stress"

    recent_codex_work_orders = sum(1 for row in codex_work_orders if str(row.get("source_intent_id") or "") in recent_intent_ids)
    recent_deep_research_work_orders = sum(
        1 for row in deep_research_work_orders if str(row.get("source_intent_id") or "") in recent_intent_ids
    )
    usage_balance = "balanced" if classification == "balanced_recent_venue_mix" else "skewed_or_stressed"
    classification_basis = {
        "heavy_flags": {
            "internal_execution_heavy": internal_heavy,
            "codex_heavy": codex_heavy,
            "deep_research_heavy": deep_research_heavy,
            "operator_escalation_heavy": operator_heavy,
            "conflicting_heavy_patterns": heavy_pattern_count >= 2,
        },
        "ratios": {
            "internal_ratio": round(internal_ratio, 4),
            "codex_ratio": round(codex_ratio, 4),
            "deep_research_ratio": round(deep_ratio, 4),
            "operator_ratio": round(operator_ratio, 4),
            "blocked_ratio": round(blocked_ratio, 4),
        },
    }

    return {
        "schema_version": "orchestration_venue_mix_review.v1",
        "review_kind": "orchestration_venue_mix_retrospective",
        "review_classification": classification,
        "window_size": max(0, window_size),
        "records_considered": records_considered,
        "recent_venue_counts": venue_counts,
        "recent_operator_and_blocked_counts": {
            "operator_required_or_escalated": operator_required_count,
            "blocked_handoffs": blocked_count,
        },
        "summary": {
            "venue_usage_balance": usage_balance,
            "diagnostic_summary": "bounded retrospective venue-mix review derived from existing orchestration artifacts only",
            "external_fulfillment_influence": {
                "influenced_venue_mix_review": external_signal_present,
                "healthy_receipt_count": external_healthy,
                "stressed_receipt_count": external_stressed,
                "blocked_or_unusable_receipt_count": external_blocked_or_unusable,
                "quality_signal": "stressed"
                if external_quality_stressed
                else ("healthy_or_mixed" if external_signal_present else "none"),
            },
            "classification_basis": classification_basis,
        },
        "artifacts_read": {
            "intent_ledger": "glow/orchestration/orchestration_intents.jsonl",
            "handoff_ledger": "glow/orchestration/orchestration_handoffs.jsonl",
            "codex_staged_work_order_ledger": "glow/orchestration/codex_work_orders.jsonl",
            "deep_research_staged_work_order_ledger": "glow/orchestration/deep_research_work_orders.jsonl",
            "orchestration_result_resolution_surface": "sentientos.orchestration_intent_fabric.resolve_orchestration_result",
            "handoff_packet_ledger": "glow/orchestration/orchestration_handoff_packets.jsonl",
            "fulfillment_receipt_ledger": "glow/orchestration/orchestration_fulfillment_receipts.jsonl",
        },
        "evidence_counts": {
            "recent_codex_work_orders": recent_codex_work_orders,
            "recent_deep_research_work_orders": recent_deep_research_work_orders,
        },
        "external_fulfillment_contribution": {
            "by_kind": dict(external_summary.get("by_kind") or {}),
            "by_venue": dict(external_summary.get("by_venue") or {}),
            "healthy_receipt_count": external_healthy,
            "stressed_receipt_count": external_stressed,
            "blocked_or_unusable_receipt_count": external_blocked_or_unusable,
            "receipts_missing_for_recent_packets": int(external_summary.get("receipts_missing_for_recent_packets") or 0),
            "signal_present": external_signal_present,
        },
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "review_only": True,
                "does_not_change_admission_or_execution_authority": True,
            },
        ),
    }


def derive_orchestration_attention_recommendation(
    outcome_review: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive bounded operator-attention recommendation from orchestration outcome review only."""

    review_classification = str(outcome_review.get("review_classification") or "insufficient_history")
    records_considered = int(outcome_review.get("records_considered") or 0)
    condition_flags_raw = outcome_review.get("condition_flags")
    condition_flags = condition_flags_raw if isinstance(condition_flags_raw, Mapping) else {}
    blocked_heavy = bool(condition_flags.get("blocked_heavy"))
    failure_heavy = bool(condition_flags.get("failure_heavy"))
    stall_heavy = bool(condition_flags.get("stall_heavy"))
    recent_counts_raw = outcome_review.get("recent_outcome_counts")
    recent_outcome_counts = recent_counts_raw if isinstance(recent_counts_raw, Mapping) else {}
    handoff_not_admitted = int(recent_outcome_counts.get("handoff_not_admitted") or 0)
    light_block_pattern = handoff_not_admitted >= 1 and not blocked_heavy

    recommendation = "insufficient_context"
    rationale = "insufficient_orchestration_history_for_confident_attention_guidance"

    if review_classification == "clean_recent_orchestration":
        recommendation = "none"
        rationale = "recent_internal_orchestration_outcomes_are_clean_and_loop_closure_is_healthy"
    elif review_classification == "handoff_block_heavy" or blocked_heavy:
        recommendation = "inspect_handoff_blocks"
        rationale = "recent_history_shows_block_heavy_internal_handoff_behavior"
    elif review_classification == "execution_failure_heavy" or failure_heavy:
        recommendation = "inspect_execution_failures"
        rationale = "recent_history_shows_execution_failure_heavy_pattern_after_admission"
    elif review_classification == "pending_stall_pattern" or stall_heavy:
        recommendation = "inspect_pending_stall"
        rationale = "recent_history_shows_pending_or_missing_result_stall_pattern"
    elif review_classification == "mixed_orchestration_stress":
        recommendation = "review_mixed_orchestration_stress"
        rationale = "recent_history_shows_mixed_orchestration_stress_needing_human_interpretation"
    elif review_classification == "insufficient_history":
        recommendation = "insufficient_context"
        rationale = "insufficient_recent_orchestration_history_for_specific_attention_recommendation"
    elif light_block_pattern and records_considered >= 3 and review_classification not in {"clean_recent_orchestration"}:
        recommendation = "observe"
        rationale = "light_non_failure_handoff_block_pattern_detected_observe_before_deeper_intervention"

    if (
        light_block_pattern
        and review_classification == "mixed_orchestration_stress"
        and recommendation == "review_mixed_orchestration_stress"
    ):
        recommendation = "observe"
        rationale = "light_non_failure_handoff_block_pattern_detected_observe_before_deeper_intervention"

    if recommendation not in _ORCHESTRATION_ATTENTION_RECOMMENDATIONS:
        recommendation = "insufficient_context"
        rationale = "unrecognized_review_pattern_defaulted_to_insufficient_context"

    return {
        "schema_version": "orchestration_attention_recommendation.v1",
        "source": "orchestration_outcome_review",
        "review_ref": {
            "schema_version": str(outcome_review.get("schema_version") or ""),
            "review_kind": str(outcome_review.get("review_kind") or ""),
            "review_classification": review_classification,
        },
        "operator_attention_recommendation": recommendation,
        "basis": {
            "records_considered": records_considered,
            "condition_flags": {
                "blocked_heavy": blocked_heavy,
                "failure_heavy": failure_heavy,
                "stall_heavy": stall_heavy,
                "light_block_pattern": light_block_pattern,
            },
            "recent_outcome_counts": {
                "execution_succeeded": int(recent_outcome_counts.get("execution_succeeded") or 0),
                "execution_failed": int(recent_outcome_counts.get("execution_failed") or 0),
                "handoff_admitted_pending_result": int(recent_outcome_counts.get("handoff_admitted_pending_result") or 0),
                "execution_still_pending": int(recent_outcome_counts.get("execution_still_pending") or 0),
                "execution_result_missing": int(recent_outcome_counts.get("execution_result_missing") or 0),
                "handoff_not_admitted": handoff_not_admitted,
            },
            "rationale": rationale,
            "derived_from_existing_signals_only": [
                "orchestration_outcome_review.review_classification",
                "orchestration_outcome_review.condition_flags",
                "orchestration_outcome_review.recent_outcome_counts",
            ],
        },
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
        ),
    }


def derive_next_venue_recommendation(
    delegated_judgment: Mapping[str, Any],
    outcome_review: Mapping[str, Any],
    venue_mix_review: Mapping[str, Any],
    attention_recommendation: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive a bounded next-venue recommendation from existing orchestration signals only."""

    delegated_venue = str(delegated_judgment.get("recommended_venue") or "insufficient_context")
    escalation_classification = str(delegated_judgment.get("escalation_classification") or "")
    outcome_classification = str(outcome_review.get("review_classification") or "insufficient_history")
    venue_mix_classification = str(venue_mix_review.get("review_classification") or "insufficient_history")
    attention_signal = str(attention_recommendation.get("operator_attention_recommendation") or "insufficient_context")
    outcome_records = int(outcome_review.get("records_considered") or 0)
    venue_mix_records = int(venue_mix_review.get("records_considered") or 0)
    blocked_heavy = bool((outcome_review.get("condition_flags") or {}).get("blocked_heavy"))
    failure_heavy = bool((outcome_review.get("condition_flags") or {}).get("failure_heavy"))
    stall_heavy = bool((outcome_review.get("condition_flags") or {}).get("stall_heavy"))
    operator_heavy = venue_mix_classification == "operator_escalation_heavy"
    external_contribution = venue_mix_review.get("external_fulfillment_contribution")
    external_contribution_map = external_contribution if isinstance(external_contribution, Mapping) else {}
    by_venue = external_contribution_map.get("by_venue")
    by_venue_map = by_venue if isinstance(by_venue, Mapping) else {}

    def _venue_external_health(venue: str) -> dict[str, int]:
        venue_map = by_venue_map.get(venue)
        venue_metrics = venue_map if isinstance(venue_map, Mapping) else {}
        return {
            "healthy": int(venue_metrics.get("healthy") or 0),
            "stressed": int(venue_metrics.get("stressed") or 0),
            "blocked_or_unusable": int(venue_metrics.get("blocked_or_unusable") or 0),
            "fulfilled_externally": int(venue_metrics.get("fulfilled_externally") or 0),
            "fulfilled_externally_with_issues": int(venue_metrics.get("fulfilled_externally_with_issues") or 0),
            "externally_declined": int(venue_metrics.get("externally_declined") or 0),
            "externally_abandoned": int(venue_metrics.get("externally_abandoned") or 0),
            "externally_result_unusable": int(venue_metrics.get("externally_result_unusable") or 0),
        }

    codex_external = _venue_external_health("codex_implementation")
    deep_external = _venue_external_health("deep_research_audit")
    delegated_external = _venue_external_health(delegated_venue) if delegated_venue in {
        "codex_implementation",
        "deep_research_audit",
    } else _venue_external_health("")
    delegated_external_total = delegated_external["healthy"] + delegated_external["stressed"] + delegated_external["blocked_or_unusable"]
    delegated_external_healthy_strong = delegated_external["healthy"] >= 2 and (
        delegated_external["stressed"] + delegated_external["blocked_or_unusable"]
    ) == 0
    delegated_external_stressed = delegated_external_total >= 2 and (
        delegated_external["stressed"] + delegated_external["blocked_or_unusable"]
    ) >= delegated_external["healthy"]
    external_signal_present = bool(external_contribution_map.get("signal_present"))
    alternative_external_healthy = (
        deep_external["healthy"] >= 2 and (deep_external["stressed"] + deep_external["blocked_or_unusable"]) == 0
        if delegated_venue == "codex_implementation"
        else (
            codex_external["healthy"] >= 2 and (codex_external["stressed"] + codex_external["blocked_or_unusable"]) == 0
            if delegated_venue == "deep_research_audit"
            else False
        )
    )

    delegated_to_next = {
        "internal_direct_execution": "prefer_internal_execution",
        "codex_implementation": "prefer_codex_implementation",
        "deep_research_audit": "prefer_deep_research_audit",
        "operator_decision_required": "prefer_operator_decision",
    }
    delegated_next = delegated_to_next.get(delegated_venue)

    recommendation = "insufficient_context"
    relation = "insufficient_context"
    rationale = "insufficient_or_conflicting_recent_signal_basis_for_next_venue"

    operator_escalation_dominant = (
        delegated_venue == "operator_decision_required"
        or escalation_classification in {"escalate_for_missing_context", "escalate_for_operator_priority"}
        or operator_heavy
        or (
            attention_signal in {"inspect_handoff_blocks", "inspect_execution_failures", "inspect_pending_stall"}
            and (blocked_heavy or failure_heavy or stall_heavy)
        )
    )
    has_minimum_history = outcome_records >= 3 and venue_mix_records >= 3
    stress_signals_present = (
        outcome_classification in {
            "handoff_block_heavy",
            "execution_failure_heavy",
            "pending_stall_pattern",
            "mixed_orchestration_stress",
        }
        or venue_mix_classification == "mixed_venue_stress"
    )
    external_feedback_affirming = delegated_external_healthy_strong
    external_feedback_stressed = delegated_external_stressed

    if operator_escalation_dominant:
        recommendation = "prefer_operator_decision"
        relation = "escalating"
        rationale = "operator_required_or_escalation_signals_dominate_recent_orchestration_pattern"
    elif not has_minimum_history or delegated_next is None:
        recommendation = "insufficient_context"
        relation = "insufficient_context"
        rationale = "insufficient_recent_orchestration_history_or_delegated_judgment_venue_unavailable"
    elif (
        delegated_venue in {"internal_direct_execution", "codex_implementation"}
        and venue_mix_classification in {"mixed_venue_stress", "deep_research_heavy"}
        and outcome_classification in {"mixed_orchestration_stress", "execution_failure_heavy"}
    ):
        recommendation = "prefer_deep_research_audit"
        relation = "nudging"
        rationale = "recent_stress_or_architectural_ambiguity_pattern_nudges_toward_deep_research_audit"
    elif delegated_venue in {"codex_implementation", "deep_research_audit"} and external_feedback_stressed and alternative_external_healthy:
        recommendation = "prefer_deep_research_audit" if delegated_venue == "codex_implementation" else "prefer_codex_implementation"
        relation = "nudging"
        rationale = "recent_external_fulfillment_for_delegated_external_venue_is_stressed_while_alternative_external_venue_is_recently_healthy"
    elif delegated_venue in {"codex_implementation", "deep_research_audit"} and external_feedback_stressed:
        recommendation = "hold_current_venue_mix"
        relation = "holding"
        rationale = "recent_external_fulfillment_for_delegated_external_venue_is_stressed_without_a_clear_healthy_external_alternative"
    elif delegated_venue in {"codex_implementation", "deep_research_audit"} and external_feedback_affirming:
        recommendation = delegated_next if delegated_next is not None else "insufficient_context"
        relation = "affirming"
        rationale = "recent_external_fulfillment_for_delegated_external_venue_is_healthy_and_supports_affirmation"
    elif delegated_venue == "internal_direct_execution" and outcome_classification == "clean_recent_orchestration" and venue_mix_classification in {
        "balanced_recent_venue_mix",
        "internal_execution_heavy",
    }:
        recommendation = "prefer_internal_execution"
        relation = "affirming"
        rationale = "clean_recent_internal_outcomes_and_compatible_venue_mix_affirm_internal_execution"
    elif delegated_venue == "codex_implementation" and outcome_classification == "clean_recent_orchestration" and venue_mix_classification in {
        "balanced_recent_venue_mix",
        "codex_heavy",
    }:
        recommendation = "prefer_codex_implementation"
        relation = "affirming"
        rationale = "clean_recent_outcomes_and_compatible_codex_usage_affirm_codex_implementation"
    elif delegated_venue == "deep_research_audit" and venue_mix_classification in {
        "balanced_recent_venue_mix",
        "deep_research_heavy",
    } and outcome_classification in {"clean_recent_orchestration", "mixed_orchestration_stress", "execution_failure_heavy"}:
        recommendation = "prefer_deep_research_audit"
        relation = "affirming"
        rationale = "delegated_judgment_and_recent_venue_patterns_support_deep_research_audit"
    elif stress_signals_present:
        recommendation = "hold_current_venue_mix"
        relation = "holding"
        rationale = "recent_venue_behavior_is_stressed_or_unstable_without_clear_safe_correction_target"
    elif delegated_next is not None:
        recommendation = delegated_next
        relation = "affirming"
        rationale = "delegated_judgment_is_compatible_with_recent_orchestration_signals"

    if recommendation not in _NEXT_VENUE_RECOMMENDATIONS:
        recommendation = "insufficient_context"
        relation = "insufficient_context"
        rationale = "unrecognized_next_venue_recommendation_defaulted_to_insufficient_context"
    if relation not in _NEXT_VENUE_RELATIONS:
        relation = "insufficient_context"

    return {
        "schema_version": "next_venue_recommendation.v1",
        "source": "delegated_judgment_plus_orchestration_reviews",
        "current_delegated_judgment_venue": delegated_venue,
        "next_venue_recommendation": recommendation,
        "relation_to_delegated_judgment": relation,
        "basis": {
            "delegated_judgment": {
                "recommended_venue": delegated_venue,
                "escalation_classification": escalation_classification,
            },
            "orchestration_outcome_review": {
                "review_classification": outcome_classification,
                "records_considered": outcome_records,
                "condition_flags": {
                    "blocked_heavy": blocked_heavy,
                    "failure_heavy": failure_heavy,
                    "stall_heavy": stall_heavy,
                },
            },
            "orchestration_venue_mix_review": {
                "review_classification": venue_mix_classification,
                "records_considered": venue_mix_records,
                "external_fulfillment_contribution": {
                    "signal_present": external_signal_present,
                    "delegated_external_venue_health": delegated_external,
                    "codex_external_health": codex_external,
                    "deep_research_external_health": deep_external,
                    "external_feedback_affirming": external_feedback_affirming,
                    "external_feedback_stressed": external_feedback_stressed,
                },
            },
            "orchestration_operator_attention_recommendation": attention_signal,
            "rationale": rationale,
            "derived_from_existing_signals_only": [
                "delegated_judgment.recommended_venue",
                "delegated_judgment.escalation_classification",
                "orchestration_outcome_review.review_classification",
                "orchestration_outcome_review.condition_flags",
                "orchestration_venue_mix_review.review_classification",
                "orchestration_venue_mix_review.external_fulfillment_contribution",
                "orchestration_operator_attention_recommendation.operator_attention_recommendation",
            ],
        },
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "does_not_execute_or_route_work": True,
                "does_not_override_delegated_judgment": True,
            },
        ),
    }


def derive_external_feedback_gap_map(
    outcome_review: Mapping[str, Any],
    venue_mix_review: Mapping[str, Any],
    next_venue_recommendation: Mapping[str, Any],
) -> dict[str, Any]:
    """Return compact audit visibility for external fulfillment influence across review layers."""

    outcome_influence = outcome_review.get("summary", {}).get("external_fulfillment_influence")
    outcome_influence_map = outcome_influence if isinstance(outcome_influence, Mapping) else {}
    venue_mix_influence = venue_mix_review.get("summary", {}).get("external_fulfillment_influence")
    venue_mix_influence_map = venue_mix_influence if isinstance(venue_mix_influence, Mapping) else {}
    next_basis = next_venue_recommendation.get("basis", {}).get("orchestration_venue_mix_review", {})
    next_basis_map = next_basis if isinstance(next_basis, Mapping) else {}
    next_external = next_basis_map.get("external_fulfillment_contribution")
    next_external_map = next_external if isinstance(next_external, Mapping) else {}

    return {
        "schema_version": "orchestration_external_feedback_gap_map.v1",
        "outcome_review": {
            "external_fulfillment_influencing": bool(outcome_influence_map.get("influenced_outcome_review")),
            "influence_mode": str(outcome_influence_map.get("influence_mode") or "none"),
            "remaining_gap": "none"
            if outcome_influence_map.get("influenced_outcome_review")
            else "external_fulfillment_not_currently_visible_to_outcome_review",
        },
        "venue_mix_review": {
            "external_fulfillment_influencing": bool(venue_mix_influence_map.get("influenced_venue_mix_review")),
            "quality_signal": str(venue_mix_influence_map.get("quality_signal") or "none"),
            "remaining_gap": "none"
            if venue_mix_influence_map.get("influenced_venue_mix_review")
            else "external_fulfillment_not_currently_visible_to_venue_mix_review",
        },
        "next_venue_recommendation": {
            "external_fulfillment_influencing": bool(next_external_map.get("signal_present")),
            "delegated_external_feedback_stressed": bool(next_external_map.get("external_feedback_stressed")),
            "delegated_external_feedback_affirming": bool(next_external_map.get("external_feedback_affirming")),
            "remaining_gap": "none"
            if next_external_map.get("signal_present")
            else "next_venue_recommendation_not_currently_using_external_fulfillment_history",
        },
        "non_authoritative": True,
        "decision_power": "none",
        "diagnostic_only": True,
    }


def resolve_latest_operator_resolution_for_proposal(
    repo_root: Path,
    proposal_id: str,
) -> dict[str, Any] | None:
    """Return the latest operator resolution receipt linked to a proposal, if any."""

    if not proposal_id.strip():
        return None
    rows = _read_jsonl(repo_root.resolve() / "glow/orchestration/operator_resolution_receipts.jsonl")
    linked = [
        row
        for row in rows
        if str((row.get("source_next_move_proposal_ref") or {}).get("proposal_id") or "") == proposal_id
    ]
    latest = linked[-1] if linked else None
    return dict(latest) if isinstance(latest, Mapping) else None


def derive_operator_resolution_influence(
    operator_resolution_receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Derive compact bounded influence visibility from a linked operator resolution receipt."""

    receipt_map = operator_resolution_receipt if isinstance(operator_resolution_receipt, Mapping) else {}
    resolution_kind = str(receipt_map.get("resolution_kind") or "")
    mapped_state = {
        "approved_continue": "operator_approval_applied",
        "approved_with_constraints": "operator_approval_applied",
        "supplied_missing_context": "operator_context_applied",
        "redirected_venue": "operator_redirect_applied",
        "declined": "operator_decline_preserved_hold",
        "cancelled": "operator_decline_preserved_hold",
        "deferred": "operator_defer_preserved_hold",
    }.get(resolution_kind, "no_operator_influence_yet")
    if mapped_state not in _OPERATOR_INFLUENCE_STATES:
        mapped_state = "no_operator_influence_yet"

    redirected_venue_raw = str(receipt_map.get("redirected_venue") or "")
    redirected_venue = (
        redirected_venue_raw
        if redirected_venue_raw
        in {"internal_direct_execution", "codex_implementation", "deep_research_audit", "operator_decision_required"}
        else None
    )
    context_refs = [
        ref
        for ref in receipt_map.get("updated_context_refs", [])
        if isinstance(ref, str) and ref.strip()
    ] if isinstance(receipt_map.get("updated_context_refs"), list) else []

    influence = {
        "schema_version": "operator_resolution_influence.v1",
        "operator_influence_state": mapped_state,
        "operator_influence_applied": mapped_state != "no_operator_influence_yet",
        "resolution_kind": resolution_kind or None,
        "resolution_receipt_id": str(receipt_map.get("operator_resolution_receipt_id") or "") or None,
        "resolution_receipt_linked": bool(receipt_map),
        "operator_context_refs_present": bool(context_refs),
        "operator_context_refs_count": len(context_refs),
        "operator_redirected_venue": redirected_venue,
        "operator_redirect_applied": mapped_state == "operator_redirect_applied" and redirected_venue is not None,
        "operator_approval_applied": mapped_state == "operator_approval_applied",
        "operator_context_applied": mapped_state == "operator_context_applied" and bool(context_refs),
        "operator_decline_or_cancel_preserves_hold": mapped_state == "operator_decline_preserved_hold",
        "operator_defer_preserves_hold": mapped_state == "operator_defer_preserved_hold",
        "compact_rationale": (
            "operator_resolution_receipt_not_linked_to_current_proposal"
            if not receipt_map
            else f"operator_resolution_{resolution_kind}_is_visible_as_bounded_influence_only"
        ),
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "does_not_imply_execution": True,
                "does_not_override_admission": True,
                "requires_existing_trigger_path_for_follow_on_action": True,
                "historical_operator_resolution_preserved": True,
            },
        ),
    }
    return influence


def derive_operator_resolution_feedback_gap_map(
    next_move_proposal: Mapping[str, Any],
    packetization_gate: Mapping[str, Any],
    next_venue_recommendation: Mapping[str, Any],
    operator_brief_lifecycle: Mapping[str, Any],
    operator_influence: Mapping[str, Any],
) -> dict[str, Any]:
    """Return compact audit visibility for operator-resolution feedback integration coverage."""

    influence_state = str(operator_influence.get("operator_influence_state") or "no_operator_influence_yet")
    influence_applied = bool(operator_influence.get("operator_influence_applied"))
    receipt_visible = bool(operator_brief_lifecycle.get("operator_resolution_received"))
    proposal_feedback_visible = bool((next_move_proposal.get("operator_feedback") or {}).get("operator_influence_applied"))
    gate_feedback_visible = bool((packetization_gate.get("operator_influence") or {}).get("operator_influence_applied"))
    venue_feedback_visible = bool((next_venue_recommendation.get("operator_feedback") or {}).get("operator_influence_applied"))

    return {
        "schema_version": "orchestration_operator_feedback_gap_map.v1",
        "next_move_proposal_visibility": {
            "operator_resolution_visible": proposal_feedback_visible,
            "remaining_gap": "none" if proposal_feedback_visible or not receipt_visible else "proposal_visibility_not_consuming_operator_resolution",
        },
        "packetization_gating": {
            "operator_resolution_visible": gate_feedback_visible,
            "remaining_gap": "none" if gate_feedback_visible or not receipt_visible else "packetization_gate_not_consuming_operator_resolution",
        },
        "next_venue_recommendation": {
            "operator_resolution_visible": venue_feedback_visible,
            "remaining_gap": "none" if venue_feedback_visible or not receipt_visible else "next_venue_recommendation_not_consuming_operator_resolution",
        },
        "operator_brief_lifecycle_visibility": {
            "operator_resolution_received": receipt_visible,
            "resolution_kind": operator_brief_lifecycle.get("resolution_kind"),
            "influence_state": influence_state,
            "remaining_gap": "none" if receipt_visible else "operator_resolution_not_yet_received",
        },
        "held_loop_static_after_operator_response": bool(receipt_visible and not influence_applied),
        "non_authoritative": True,
        "decision_power": "none",
        "diagnostic_only": True,
    }


def _refresh_reason_from_resolution_kind(resolution_kind: str) -> str:
    return {
        "approved_continue": "operator_approved_continue_refresh",
        "approved_with_constraints": "operator_constraints_applied_refresh",
        "supplied_missing_context": "operator_context_supplied_refresh",
        "redirected_venue": "operator_redirected_venue_refresh",
    }.get(resolution_kind, "operator_feedback_visibility_only")


def _resolution_can_repacketize(resolution_kind: str) -> bool:
    return resolution_kind in {
        "approved_continue",
        "approved_with_constraints",
        "supplied_missing_context",
        "redirected_venue",
    }


def resolve_handoff_packet_history_for_proposal(
    repo_root: Path,
    proposal_id: str,
) -> dict[str, Any]:
    """Resolve compact append-only handoff-packet history for one proposal id."""

    rows = _read_jsonl(repo_root.resolve() / "glow/orchestration/orchestration_handoff_packets.jsonl")
    linked = [
        row
        for row in rows
        if str((row.get("source_next_move_proposal_ref") or {}).get("proposal_id") or "") == proposal_id
    ]
    superseded_by: dict[str, str] = {}
    for row in linked:
        row_id = str(row.get("handoff_packet_id") or "")
        lineage = row.get("packet_lineage")
        lineage_map = lineage if isinstance(lineage, Mapping) else {}
        parent_id = str(lineage_map.get("supersedes_handoff_packet_id") or "")
        if row_id and parent_id:
            superseded_by[parent_id] = row_id

    timeline: list[dict[str, Any]] = []
    for row in linked:
        row_id = str(row.get("handoff_packet_id") or "")
        lineage = row.get("packet_lineage")
        lineage_map = lineage if isinstance(lineage, Mapping) else {}
        timeline.append(
            {
                "handoff_packet_id": row_id or None,
                "recorded_at": str(row.get("recorded_at") or ""),
                "packet_status": str(row.get("packet_status") or ""),
                "target_venue": str(row.get("target_venue") or ""),
                "supersedes_handoff_packet_id": str(lineage_map.get("supersedes_handoff_packet_id") or "") or None,
                "superseded_by_handoff_packet_id": superseded_by.get(row_id),
                "refresh_reason": str(lineage_map.get("refresh_reason") or "") or None,
                "source_operator_resolution_receipt_id": str(lineage_map.get("source_operator_resolution_receipt_id") or "") or None,
                "current_packet_candidate": bool(lineage_map.get("current_packet_candidate", True)),
                "repacketized_from_operator_feedback": bool(row.get("repacketized_from_operator_feedback")),
            }
        )

    active_packet_id: str | None = None
    active_candidates = [
        row
        for row in timeline
        if bool(row.get("current_packet_candidate")) and not row.get("superseded_by_handoff_packet_id")
    ]
    if active_candidates:
        active_packet_id = str(active_candidates[-1].get("handoff_packet_id") or "") or None
    elif timeline:
        active_packet_id = str(timeline[-1].get("handoff_packet_id") or "") or None

    return {
        "schema_version": "handoff_packet_history.v1",
        "proposal_id": proposal_id or None,
        "history_count": len(timeline),
        "timeline": timeline,
        "active_handoff_packet_id": active_packet_id,
        "append_only_history": True,
        "non_authoritative": True,
        "decision_power": "none",
        "diagnostic_only": True,
    }


def synthesize_operator_refreshed_handoff_packet(
    next_move_proposal: Mapping[str, Any],
    delegated_judgment: Mapping[str, Any],
    next_move_proposal_review: Mapping[str, Any],
    trust_confidence_posture: Mapping[str, Any],
    operator_attention_recommendation: Mapping[str, Any],
    operator_resolution_receipt: Mapping[str, Any] | None,
    latest_handoff_packet: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """
    Synthesize a refreshed handoff packet when bounded operator feedback allows repacketization.

    This function is append-only: it emits a new packet and never mutates prior packet rows.
    """

    receipt_map = operator_resolution_receipt if isinstance(operator_resolution_receipt, Mapping) else {}
    resolution_kind = str(receipt_map.get("resolution_kind") or "")
    if not _resolution_can_repacketize(resolution_kind):
        return None

    latest_packet_map = latest_handoff_packet if isinstance(latest_handoff_packet, Mapping) else {}
    supersedes_id = str(latest_packet_map.get("handoff_packet_id") or "")
    if not supersedes_id:
        return None

    latest_lineage = latest_packet_map.get("packet_lineage")
    latest_lineage_map = latest_lineage if isinstance(latest_lineage, Mapping) else {}
    previous_receipt_id = str(latest_lineage_map.get("source_operator_resolution_receipt_id") or "")
    current_receipt_id = str(receipt_map.get("operator_resolution_receipt_id") or "")
    if previous_receipt_id and current_receipt_id and previous_receipt_id == current_receipt_id:
        return None

    refresh_reason = _refresh_reason_from_resolution_kind(resolution_kind)
    refreshed = synthesize_handoff_packet(
        next_move_proposal,
        delegated_judgment,
        next_move_proposal_review,
        trust_confidence_posture,
        operator_attention_recommendation,
        receipt_map,
        supersedes_handoff_packet_id=supersedes_id,
        refresh_reason=refresh_reason,
        current_packet_candidate=True,
    )
    return refreshed


def resolve_active_handoff_packet_candidate(
    repo_root: Path,
    proposal_id: str,
    operator_influence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve the current active handoff packet candidate with compact lineage visibility."""

    history = resolve_handoff_packet_history_for_proposal(repo_root, proposal_id)
    active_packet_id = str(history.get("active_handoff_packet_id") or "")
    rows = _read_jsonl(repo_root.resolve() / "glow/orchestration/orchestration_handoff_packets.jsonl")
    active_packet = next((row for row in reversed(rows) if str(row.get("handoff_packet_id") or "") == active_packet_id), None)
    active_map = active_packet if isinstance(active_packet, Mapping) else {}
    lineage = active_map.get("packet_lineage")
    lineage_map = lineage if isinstance(lineage, Mapping) else {}
    influence_map = operator_influence if isinstance(operator_influence, Mapping) else {}

    return {
        "schema_version": "active_handoff_packet_candidate.v1",
        "proposal_id": proposal_id or None,
        "active_handoff_packet_id": active_packet_id or None,
        "active_packet_present": bool(active_map),
        "is_refreshed_packet": bool(lineage_map.get("supersedes_handoff_packet_id")),
        "current_packet_candidate": bool(lineage_map.get("current_packet_candidate", True)),
        "active_packet_status": str(active_map.get("packet_status") or "") or None,
        "active_target_venue": str(active_map.get("target_venue") or "") or None,
        "lineage": {
            "supersedes_handoff_packet_id": str(lineage_map.get("supersedes_handoff_packet_id") or "") or None,
            "superseded_by_handoff_packet_id": None,
            "refresh_reason": str(lineage_map.get("refresh_reason") or "") or None,
            "source_operator_resolution_receipt_id": str(lineage_map.get("source_operator_resolution_receipt_id") or "") or None,
            "history_count": int(history.get("history_count") or 0),
        },
        "operator_influence": {
            "operator_influence_state": str(influence_map.get("operator_influence_state") or "no_operator_influence_yet"),
            "operator_influence_applied": bool(influence_map.get("operator_influence_applied")),
            "resolution_kind": influence_map.get("resolution_kind"),
            "resolution_receipt_id": influence_map.get("resolution_receipt_id"),
        },
        "does_not_imply_execution": True,
        "does_not_override_admission": True,
        "requires_existing_trigger_path_for_follow_on_action": True,
        "historical_packet_state_preserved": True,
        "non_authoritative": True,
        "decision_power": "none",
        "diagnostic_only": True,
    }


def derive_repacketization_gap_map(
    operator_brief_lifecycle: Mapping[str, Any],
    operator_influence: Mapping[str, Any],
    packet_history: Mapping[str, Any],
    active_packet: Mapping[str, Any],
) -> dict[str, Any]:
    """Return compact visibility describing whether operator feedback can refresh current packet state."""

    resolution_kind = str(operator_brief_lifecycle.get("resolution_kind") or "")
    receipt_received = bool(operator_brief_lifecycle.get("operator_resolution_received"))
    influence_applied = bool(operator_influence.get("operator_influence_applied"))
    eligible_resolution = _resolution_can_repacketize(resolution_kind)
    history_count = int(packet_history.get("history_count") or 0)
    refreshed_visible = bool(active_packet.get("is_refreshed_packet"))

    return {
        "schema_version": "orchestration_repacketization_gap_map.v1",
        "latest_usable_next_packet_artifact": "glow/orchestration/orchestration_handoff_packets.jsonl",
        "operator_feedback_resolution_received": receipt_received,
        "operator_feedback_influence_applied": influence_applied,
        "operator_resolution_kind": resolution_kind or None,
        "operator_resolution_can_repacketize": eligible_resolution,
        "history": {
            "handoff_packets_for_proposal": history_count,
            "active_packet_is_refreshed": refreshed_visible,
            "manual_reconstruction_required": bool(receipt_received and eligible_resolution and not refreshed_visible),
        },
        "lineage_semantics": {
            "supersedes_handoff_packet_id_supported": True,
            "superseded_by_handoff_packet_id_resolved": True,
            "refresh_reason_supported": True,
            "source_operator_resolution_receipt_id_supported": True,
            "current_packet_candidate_supported": True,
        },
        "non_authoritative": True,
        "decision_power": "none",
        "diagnostic_only": True,
    }


def synthesize_next_move_proposal(
    delegated_judgment: Mapping[str, Any],
    next_venue_recommendation: Mapping[str, Any],
    outcome_review: Mapping[str, Any],
    venue_mix_review: Mapping[str, Any],
    attention_recommendation: Mapping[str, Any],
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Synthesize a bounded, non-sovereign next-move proposal from existing orchestration signals."""

    source_linkage = _source_judgment_linkage(delegated_judgment)
    source_linkage_id = _source_judgment_linkage_id(source_linkage)
    delegated_venue = str(source_linkage.get("recommended_venue") or "insufficient_context")
    delegated_posture = str(source_linkage.get("next_move_posture") or "hold")
    escalation_classification = str(source_linkage.get("escalation_classification") or "escalate_for_missing_context")
    relation_posture = str(next_venue_recommendation.get("relation_to_delegated_judgment") or "insufficient_context")
    recommended_next_venue = str(next_venue_recommendation.get("next_venue_recommendation") or "insufficient_context")
    attention_signal = str(attention_recommendation.get("operator_attention_recommendation") or "insufficient_context")
    outcome_classification = str(outcome_review.get("review_classification") or "insufficient_history")
    venue_mix_classification = str(venue_mix_review.get("review_classification") or "insufficient_history")

    recommendation_to_venue = {
        "prefer_internal_execution": "internal_direct_execution",
        "prefer_codex_implementation": "codex_implementation",
        "prefer_deep_research_audit": "deep_research_audit",
        "prefer_operator_decision": "operator_decision_required",
        "hold_current_venue_mix": delegated_venue,
        "insufficient_context": "insufficient_context",
    }
    proposed_venue = recommendation_to_venue.get(recommended_next_venue, "insufficient_context")
    proposed_intent_kind, _, _ = _translate_kind(
        {
            "recommended_venue": proposed_venue,
            "work_class": str(source_linkage.get("work_class") or ""),
            "escalation_classification": escalation_classification,
        }
    )
    proposed_posture = delegated_posture if delegated_posture in _NEXT_MOVE_PROPOSAL_POSTURES else "hold"
    executability = "no_action_recommended"
    if relation_posture == "escalating" or proposed_venue == "operator_decision_required":
        proposed_posture = "escalate"
        executability = "blocked_operator_required"
    elif relation_posture == "holding":
        proposed_posture = "hold"
        executability = "no_action_recommended"
    elif relation_posture == "insufficient_context" or proposed_venue == "insufficient_context":
        proposed_posture = "hold"
        executability = "blocked_insufficient_context"
    elif proposed_venue == "internal_direct_execution":
        executability = "executable_now"
    elif proposed_venue in {"codex_implementation", "deep_research_audit"}:
        executability = "stageable_external_work_order"

    if executability not in _NEXT_MOVE_EXECUTABILITY:
        executability = "blocked_insufficient_context"

    if relation_posture not in _NEXT_VENUE_RELATIONS:
        relation_posture = "insufficient_context"
    if proposed_posture not in _NEXT_MOVE_PROPOSAL_POSTURES:
        proposed_posture = "hold"
    if proposed_intent_kind not in _INTENT_KINDS:
        proposed_intent_kind = "hold_no_action"

    requires_operator = (
        escalation_classification in {"escalate_for_missing_context", "escalate_for_operator_priority"}
        or relation_posture in {"escalating", "insufficient_context"}
        or recommended_next_venue == "prefer_operator_decision"
        or attention_signal in {"inspect_handoff_blocks", "inspect_execution_failures", "inspect_pending_stall"}
    )
    timestamp = created_at or _iso_utc_now()
    proposal = {
        "schema_version": "orchestration_next_move_proposal.v1",
        "proposal_id": _next_move_proposal_id(
            created_at=timestamp,
            source_linkage_id=source_linkage_id,
            relation_posture=relation_posture,
            proposed_venue=proposed_venue,
            proposed_intent_kind=proposed_intent_kind,
        ),
        "recorded_at": timestamp,
        "source_delegated_judgment": {
            "source_judgment_linkage_id": source_linkage_id,
            "recommended_venue": delegated_venue,
            "next_move_posture": delegated_posture,
            "escalation_classification": escalation_classification,
        },
        "current_recommended_venue": recommended_next_venue,
        "relation_posture": relation_posture,
        "proposed_next_action": {
            "intent_kind": proposed_intent_kind,
            "proposed_venue": proposed_venue,
            "proposed_posture": proposed_posture,
        },
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": requires_operator,
            "attention_signal": attention_signal,
            "escalation_classification": escalation_classification,
        },
        "executability_classification": executability,
        "proposal_state": (
            "ready_for_internal_executable_handoff"
            if executability == "executable_now"
            else "staged_external_or_non_executable"
            if executability == "stageable_external_work_order"
            else "blocked_or_hold"
        ),
        "basis": {
            "orchestration_outcome_review": {
                "review_classification": outcome_classification,
                "records_considered": int(outcome_review.get("records_considered") or 0),
            },
            "orchestration_venue_mix_review": {
                "review_classification": venue_mix_classification,
                "records_considered": int(venue_mix_review.get("records_considered") or 0),
            },
            "orchestration_operator_attention_recommendation": attention_signal,
            "next_venue_relation_posture": relation_posture,
            "compact_rationale": str((next_venue_recommendation.get("basis") or {}).get("rationale") or ""),
            "derived_from_existing_signals_only": [
                "delegated_judgment",
                "next_venue_recommendation",
                "orchestration_outcome_review",
                "orchestration_venue_mix_review",
                "orchestration_operator_attention_recommendation",
            ],
        },
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "proposal_only": True,
                "does_not_execute_or_route_work": True,
                "does_not_override_delegated_judgment": True,
                "requires_operator_or_existing_handoff_path": True,
            },
        ),
    }
    return proposal


def derive_operator_adjusted_next_venue_recommendation(
    next_venue_recommendation: Mapping[str, Any],
    operator_influence: Mapping[str, Any],
) -> dict[str, Any]:
    """Produce compact visibility showing operator influence on current venue recommendation."""

    base = dict(next_venue_recommendation)
    original_recommendation = str(base.get("next_venue_recommendation") or "insufficient_context")
    original_relation = str(base.get("relation_to_delegated_judgment") or "insufficient_context")
    redirected_venue = str(operator_influence.get("operator_redirected_venue") or "")
    redirected_applied = bool(operator_influence.get("operator_redirect_applied"))
    venue_to_recommendation = {
        "internal_direct_execution": "prefer_internal_execution",
        "codex_implementation": "prefer_codex_implementation",
        "deep_research_audit": "prefer_deep_research_audit",
        "operator_decision_required": "prefer_operator_decision",
    }
    redirected_recommendation = venue_to_recommendation.get(redirected_venue, original_recommendation)
    current_recommendation = redirected_recommendation if redirected_applied else original_recommendation
    current_relation = "nudging" if redirected_applied else original_relation
    feedback = {
        "operator_influence_state": str(operator_influence.get("operator_influence_state") or "no_operator_influence_yet"),
        "operator_influence_applied": bool(operator_influence.get("operator_influence_applied")),
        "resolution_kind": operator_influence.get("resolution_kind"),
        "redirected_venue": redirected_venue or None,
        "redirect_applied_to_next_venue_recommendation": redirected_applied,
    }
    return {
        **base,
        "operator_feedback": feedback,
        "original_next_venue_recommendation": original_recommendation,
        "current_next_venue_recommendation": current_recommendation,
        "original_relation_to_delegated_judgment": original_relation,
        "current_relation_to_delegated_judgment": current_relation,
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "does_not_imply_execution": True,
                "does_not_override_admission": True,
                "requires_existing_trigger_path_for_follow_on_action": True,
                "historical_operator_resolution_preserved": True,
            },
        ),
    }


def derive_operator_adjusted_next_move_proposal_visibility(
    next_move_proposal: Mapping[str, Any],
    operator_influence: Mapping[str, Any],
) -> dict[str, Any]:
    """Produce compact visibility showing operator influence on proposal hold/packetization posture."""

    proposal = dict(next_move_proposal)
    proposed_action = proposal.get("proposed_next_action")
    proposed_action_map = dict(proposed_action) if isinstance(proposed_action, Mapping) else {}
    original_venue = str(proposed_action_map.get("proposed_venue") or "insufficient_context")
    redirected_venue = str(operator_influence.get("operator_redirected_venue") or "")
    redirect_applied = bool(operator_influence.get("operator_redirect_applied"))
    if redirect_applied:
        proposed_action_map["proposed_venue"] = redirected_venue
    feedback = {
        "operator_influence_state": str(operator_influence.get("operator_influence_state") or "no_operator_influence_yet"),
        "operator_influence_applied": bool(operator_influence.get("operator_influence_applied")),
        "resolution_kind": operator_influence.get("resolution_kind"),
        "resolution_receipt_id": operator_influence.get("resolution_receipt_id"),
        "redirect_applied_to_proposed_venue": redirect_applied,
        "original_proposed_venue": original_venue,
        "current_proposed_venue": str(proposed_action_map.get("proposed_venue") or original_venue),
    }
    return {
        **proposal,
        "proposed_next_action": proposed_action_map,
        "operator_feedback": feedback,
        "original_proposed_next_action": proposed_action if isinstance(proposed_action, Mapping) else {},
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "does_not_imply_execution": True,
                "does_not_override_admission": True,
                "requires_existing_trigger_path_for_follow_on_action": True,
                "historical_operator_resolution_preserved": True,
            },
        ),
    }


def append_next_move_proposal_ledger(repo_root: Path, proposal: Mapping[str, Any]) -> Path:
    """Append one bounded next-move proposal to the proof-visible orchestration proposal ledger."""

    ledger_path = repo_root.resolve() / "glow/orchestration/orchestration_next_move_proposals.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(proposal), sort_keys=True) + "\n")
    return ledger_path


def derive_packetization_gate(
    next_move_proposal: Mapping[str, Any],
    next_move_proposal_review: Mapping[str, Any],
    trust_confidence_posture: Mapping[str, Any],
    operator_attention_recommendation: Mapping[str, Any],
    operator_resolution_influence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Derive one bounded packetization gate from existing orchestration-only signals.

    This gate is non-sovereign and only governs whether packet preparation is ready vs held.
    """

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
        operator_context_applied
        and not hold_fragmentation
        and executability != "blocked_operator_required"
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

    if outcome not in _PACKETIZATION_GATING_OUTCOMES:
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
        **_anti_sovereignty_payload(
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


def synthesize_operator_action_brief(
    next_move_proposal: Mapping[str, Any],
    packetization_gate: Mapping[str, Any],
    trust_confidence_posture: Mapping[str, Any],
    operator_attention_recommendation: Mapping[str, Any],
    *,
    next_move_proposal_review: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any] | None:
    """
    Synthesize a compact operator action brief when packetization is held/escalated.

    This is guidance-only, derived from existing orchestration signals, and never
    grants authority or execution power.
    """

    gate_outcome = str(packetization_gate.get("packetization_outcome") or "packetization_hold_insufficient_confidence")
    if gate_outcome not in {
        "packetization_hold_operator_review",
        "packetization_hold_insufficient_confidence",
        "packetization_hold_fragmentation",
        "packetization_hold_escalation_required",
    }:
        return None

    proposal_id = str(next_move_proposal.get("proposal_id") or "")
    proposed_action = next_move_proposal.get("proposed_next_action")
    proposed_action_map = proposed_action if isinstance(proposed_action, Mapping) else {}
    operator_state_raw = next_move_proposal.get("operator_escalation_requirement_state")
    operator_state = operator_state_raw if isinstance(operator_state_raw, Mapping) else {}
    source_proposal_ref = next_move_proposal.get("source_delegated_judgment")
    source_proposal_ref_map = source_proposal_ref if isinstance(source_proposal_ref, Mapping) else {}
    pressure_summary_raw = trust_confidence_posture.get("pressure_summary")
    pressure_summary = pressure_summary_raw if isinstance(pressure_summary_raw, Mapping) else {}
    review_map = next_move_proposal_review if isinstance(next_move_proposal_review, Mapping) else {}

    executability = str(next_move_proposal.get("executability_classification") or "blocked_insufficient_context")
    target_venue = str(proposed_action_map.get("proposed_venue") or "insufficient_context")
    posture = str(trust_confidence_posture.get("trust_confidence_posture") or "insufficient_history")
    attention_signal = str(
        operator_attention_recommendation.get("operator_attention_recommendation")
        or operator_state.get("attention_signal")
        or "insufficient_context"
    )
    escalation_classification = str(operator_state.get("escalation_classification") or "")
    review_classification = str(review_map.get("review_classification") or "insufficient_history")
    trust_pressure = str(pressure_summary.get("primary_pressure") or "insufficient_history")
    requires_operator = bool(operator_state.get("requires_operator_or_escalation"))
    relation_posture = str(next_move_proposal.get("relation_posture") or "insufficient_context")

    intervention_class = "resolve_insufficient_context"
    if gate_outcome == "packetization_hold_fragmentation":
        intervention_class = "review_fragmentation"
    elif gate_outcome == "packetization_hold_insufficient_confidence":
        intervention_class = "resolve_insufficient_context"
    elif gate_outcome == "packetization_hold_escalation_required":
        intervention_class = (
            "manual_external_trigger_required"
            if executability == "stageable_external_work_order" and target_venue in {"codex_implementation", "deep_research_audit"}
            else "resolve_escalation_priority"
        )
    elif gate_outcome == "packetization_hold_operator_review":
        if executability == "stageable_external_work_order" and target_venue in {"codex_implementation", "deep_research_audit"}:
            intervention_class = "manual_external_trigger_required"
        elif escalation_classification == "escalate_for_operator_priority":
            intervention_class = "resolve_escalation_priority"
        elif attention_signal == "review_mixed_orchestration_stress":
            intervention_class = "inspect_recent_orchestration_stress"
        else:
            intervention_class = "approve_and_continue"

    if intervention_class not in _OPERATOR_INTERVENTION_CLASSES:
        intervention_class = "resolve_insufficient_context"

    target_posture: str | None = None
    if intervention_class == "manual_external_trigger_required":
        target_posture = target_venue if target_venue in {"codex_implementation", "deep_research_audit"} else None
    elif intervention_class == "review_fragmentation":
        target_posture = "fragmented_or_unreliable"
    elif intervention_class == "resolve_insufficient_context":
        target_posture = "insufficient_history"
    elif intervention_class == "inspect_recent_orchestration_stress":
        target_posture = "stressed_but_usable"

    requested_action = {
        "approve_and_continue": "confirm_operator_approval_for_existing_bounded_next_move_proposal",
        "review_fragmentation": "review_fragmentation_and_relink_or_restate_missing_orchestration_artifacts",
        "resolve_insufficient_context": "provide_missing_context_or_explicitly_hold_until_context_is_available",
        "resolve_escalation_priority": "resolve_operator_priority_between_competing_escalation_or_hold_signals",
        "inspect_recent_orchestration_stress": "inspect_recent_orchestration_stress_before_reattempting_packetization",
        "manual_external_trigger_required": "manually_trigger_staged_external_venue_or_explicitly_decline",
    }[intervention_class]
    rationale_tokens = [
        f"gate_outcome={gate_outcome}",
        f"posture={posture}",
        f"pressure={trust_pressure}",
        f"executability={executability}",
        f"relation_posture={relation_posture}",
        f"attention={attention_signal}",
        f"proposal_review={review_classification}",
        f"requires_operator={str(requires_operator).lower()}",
        f"escalation={escalation_classification or 'none'}",
        f"target_venue={target_venue}",
    ]
    rationale = "; ".join(rationale_tokens)
    recorded_at = created_at or _iso_utc_now()
    target_hint = target_posture or target_venue or "none"

    brief: dict[str, Any] = {
        "schema_version": "operator_action_brief.v1",
        "recorded_at": recorded_at,
        "operator_action_brief_id": _operator_action_brief_id(
            source_proposal_id=proposal_id,
            gate_outcome=gate_outcome,
            intervention_class=intervention_class,
            target_hint=target_hint,
        ),
        "source_next_move_proposal_ref": {
            "proposal_id": proposal_id or None,
            "proposal_ledger_path": "glow/orchestration/orchestration_next_move_proposals.jsonl",
            "source_judgment_linkage_id": str(source_proposal_ref_map.get("source_judgment_linkage_id") or "") or None,
        },
        "source_packetization_gate_ref": {
            "gate_kind": str(packetization_gate.get("gate_kind") or "next_move_packetization_gate"),
            "packetization_outcome": gate_outcome,
            "gate_schema_version": str(packetization_gate.get("schema_version") or "orchestration_packetization_gate.v1"),
        },
        "trust_confidence_posture": posture,
        "intervention_class": intervention_class,
        "target_venue_or_posture": target_posture,
        "evidence_summary": rationale,
        "requested_operator_action": requested_action,
        "loop_state": "held_pending_operator_intervention",
        "operator_guidance_only": True,
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_invoke_external_tools=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "explicitly_not_a_workflow_engine": True,
                "does_not_override_packetization_gate": True,
                "does_not_create_execution_path": True,
                "requires_existing_operator_authority_surface": True,
            },
        ),
    }
    return brief


def append_operator_action_brief_ledger(repo_root: Path, brief: Mapping[str, Any]) -> Path:
    """Append one bounded operator action brief to the proof-visible operator brief ledger."""

    ledger_path = repo_root.resolve() / "glow/orchestration/operator_action_briefs.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(brief), sort_keys=True) + "\n")
    return ledger_path


def synthesize_handoff_packet(
    next_move_proposal: Mapping[str, Any],
    delegated_judgment: Mapping[str, Any],
    next_move_proposal_review: Mapping[str, Any] | None = None,
    trust_confidence_posture: Mapping[str, Any] | None = None,
    operator_attention_recommendation: Mapping[str, Any] | None = None,
    operator_resolution_receipt: Mapping[str, Any] | None = None,
    *,
    supersedes_handoff_packet_id: str | None = None,
    refresh_reason: str | None = None,
    current_packet_candidate: bool = True,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Derive a compact venue-specific handoff packet from existing bounded orchestration signals."""

    proposal_ref = next_move_proposal
    proposal_review_map = next_move_proposal_review if isinstance(next_move_proposal_review, Mapping) else {}
    trust_posture_map = trust_confidence_posture if isinstance(trust_confidence_posture, Mapping) else {}
    attention_map = operator_attention_recommendation if isinstance(operator_attention_recommendation, Mapping) else {}
    proposed_action = proposal_ref.get("proposed_next_action")
    proposed_action_map = proposed_action if isinstance(proposed_action, Mapping) else {}
    operator_state_raw = proposal_ref.get("operator_escalation_requirement_state")
    operator_state = operator_state_raw if isinstance(operator_state_raw, Mapping) else {}
    source_judgment = proposal_ref.get("source_delegated_judgment")
    source_judgment_map = source_judgment if isinstance(source_judgment, Mapping) else {}
    target_venue = str(proposed_action_map.get("proposed_venue") or "insufficient_context")
    proposed_posture = str(proposed_action_map.get("proposed_posture") or "hold")
    executability = str(proposal_ref.get("executability_classification") or "blocked_insufficient_context")
    requires_operator = bool(operator_state.get("requires_operator_or_escalation"))
    escalation = str(operator_state.get("escalation_classification") or delegated_judgment.get("escalation_classification") or "")
    source_judgment_linkage_id = str(source_judgment_map.get("source_judgment_linkage_id") or "")
    recorded_at = created_at or _iso_utc_now()
    proposal_id = str(proposal_ref.get("proposal_id") or "")
    source_operator_resolution_receipt_id = (
        str((operator_resolution_receipt or {}).get("operator_resolution_receipt_id") or "")
        if isinstance(operator_resolution_receipt, Mapping)
        else ""
    )

    status = "prepared"
    readiness = {
        "staged_only": False,
        "blocked": False,
        "ready_for_internal_trigger": False,
        "ready_for_external_trigger": False,
    }
    if executability == "blocked_insufficient_context":
        status = "blocked_insufficient_context"
        readiness["blocked"] = True
    elif executability == "blocked_operator_required" or requires_operator:
        status = "blocked_operator_required"
        readiness["blocked"] = True
    elif executability == "executable_now" and target_venue == "internal_direct_execution":
        status = "ready_for_internal_trigger"
        readiness["ready_for_internal_trigger"] = True
    elif executability == "stageable_external_work_order" and target_venue in {"codex_implementation", "deep_research_audit"}:
        status = "ready_for_external_trigger"
        readiness["ready_for_external_trigger"] = True
        readiness["staged_only"] = True
    elif executability in {"no_action_recommended"}:
        status = "prepared"
    if status not in _HANDOFF_PACKET_STATUSES:
        status = "blocked_insufficient_context"
        readiness["blocked"] = True

    if proposal_review_map or trust_posture_map or attention_map:
        packetization_gate = derive_packetization_gate(
            proposal_ref,
            proposal_review_map,
            trust_posture_map,
            attention_map,
        )
    else:
        legacy_outcome = (
            "packetization_hold_operator_review"
            if status == "blocked_operator_required"
            else "packetization_hold_insufficient_confidence"
            if status == "blocked_insufficient_context"
            else "packetization_allowed"
        )
        packetization_gate = {
            "schema_version": "orchestration_packetization_gate.v1",
            "gate_kind": "next_move_packetization_gate",
            "packetization_outcome": legacy_outcome,
            "packetization_allowed": not legacy_outcome.startswith("packetization_hold_"),
            "packetization_held": legacy_outcome.startswith("packetization_hold_"),
            "summary": {
                "compact_rationale": "legacy_packetization_path_without_review_inputs_preserves_existing_status_mapping",
                "signals_used": ["next_move_proposal.executability_classification"],
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
                "trust_confidence_posture": "unprovided",
                "proposal_review_classification": "unprovided",
                "operator_attention_recommendation": "unprovided",
                "executability_classification": executability,
                "relation_posture": str(proposal_ref.get("relation_posture") or "insufficient_context"),
                "proposed_posture": proposed_posture,
                "requires_operator_or_escalation": requires_operator,
            },
            **_anti_sovereignty_payload(
                recommendation_only=True,
                diagnostic_only=True,
                does_not_change_admission_or_execution=True,
                additional_fields={
                    "gate_only": True,
                    "packetization_stage_only": True,
                    "does_not_execute_or_route_work": True,
                    "non_authoritative": True,
                },
            ),
        }
    gate_outcome = str(packetization_gate.get("packetization_outcome") or "packetization_hold_insufficient_confidence")
    if gate_outcome.startswith("packetization_hold_"):
        status = (
            "blocked_operator_required"
            if gate_outcome in {"packetization_hold_operator_review", "packetization_hold_escalation_required"}
            else "blocked_insufficient_context"
        )
        readiness["blocked"] = True
        readiness["ready_for_internal_trigger"] = False
        readiness["ready_for_external_trigger"] = False
        readiness["staged_only"] = False

    common_payload = {
        "target_venue": target_venue,
        "expected_venue_class": "staged_external_work_order"
        if target_venue in {"codex_implementation", "deep_research_audit"}
        else "internal_task_admission_handoff"
        if target_venue == "internal_direct_execution"
        else "operator_or_context_hold",
        "source_links": {
            "next_move_proposal_id": proposal_id,
            "source_judgment_linkage_id": source_judgment_linkage_id,
        },
        "operator_requirement_state": {
            "requires_operator_or_escalation": requires_operator,
            "attention_signal": str(operator_state.get("attention_signal") or ""),
            "escalation_classification": escalation,
        },
    }

    venue_payload: dict[str, Any]
    if target_venue == "codex_implementation":
        venue_payload = {
            **common_payload,
            "implementation_objective": _compact_handoff_task_brief(next_move_proposal, delegated_judgment),
            "scope_constraints": [
                "bounded_orchestration_body_only",
                "no_direct_external_actuation",
                "no_browser_mouse_keyboard_control",
            ],
            "staged_only_not_directly_invoked_here": True,
        }
    elif target_venue == "deep_research_audit":
        venue_payload = {
            **common_payload,
            "audit_objective": _compact_handoff_task_brief(next_move_proposal, delegated_judgment),
            "ambiguity_or_stress_basis": _compact_handoff_rationale(next_move_proposal, delegated_judgment),
            "research_question_class": str(delegated_judgment.get("work_class") or "architectural_audit"),
            "staged_only_not_directly_invoked_here": True,
        }
    elif target_venue == "internal_direct_execution":
        venue_payload = {
            **common_payload,
            "internal_execution_brief": _compact_handoff_task_brief(next_move_proposal, delegated_judgment),
            "executable_now_classification": executability == "executable_now",
            "target_substrate": "task_admission_executor",
            "required_admission_handoff_posture": "admit_before_execute",
        }
    else:
        venue_payload = common_payload

    packet = {
        "schema_version": "orchestration_handoff_packet.v1",
        "recorded_at": recorded_at,
        "handoff_packet_id": _handoff_packet_id(
            created_at=recorded_at,
            source_proposal_id=proposal_id,
            source_judgment_linkage_id=source_judgment_linkage_id,
            target_venue=target_venue,
            supersedes_handoff_packet_id=supersedes_handoff_packet_id,
            source_operator_resolution_receipt_id=source_operator_resolution_receipt_id,
        ),
        "source_next_move_proposal_ref": {
            "proposal_id": proposal_id,
            "proposal_ledger_path": "glow/orchestration/orchestration_next_move_proposals.jsonl",
        },
        "source_operator_resolution_ref": {
            "operator_resolution_receipt_id": source_operator_resolution_receipt_id or None,
            "operator_resolution_receipt_ledger_path": "glow/orchestration/operator_resolution_receipts.jsonl"
            if source_operator_resolution_receipt_id
            else None,
        },
        "source_delegated_judgment_ref": {
            "source_judgment_linkage_id": source_judgment_linkage_id,
            "recommended_venue": str(delegated_judgment.get("recommended_venue") or ""),
            "judgment_kind": str(delegated_judgment.get("recommendation_kind") or ""),
        },
        "packet_lineage": {
            "supersedes_handoff_packet_id": supersedes_handoff_packet_id.strip()
            if isinstance(supersedes_handoff_packet_id, str) and supersedes_handoff_packet_id.strip()
            else None,
            "superseded_by_handoff_packet_id": None,
            "refresh_reason": refresh_reason.strip() if isinstance(refresh_reason, str) and refresh_reason.strip() else None,
            "source_operator_resolution_receipt_id": source_operator_resolution_receipt_id or None,
            "current_packet_candidate": bool(current_packet_candidate),
        },
        "target_venue": target_venue,
        "proposed_posture": proposed_posture,
        "executability_classification": executability,
        "operator_escalation_requirement_state": dict(operator_state),
        "compact_task_brief": _compact_handoff_task_brief(next_move_proposal, delegated_judgment),
        "compact_rationale": _compact_handoff_rationale(next_move_proposal, delegated_judgment),
        "artifact_references": _handoff_evidence_pointers(delegated_judgment),
        "packet_status": status,
        "readiness": readiness,
        "packetization_gate": packetization_gate,
        "venue_payload": venue_payload,
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "packet_only": True,
                "does_not_execute_or_route_work": True,
                "does_not_invoke_external_tools": True,
                "requires_operator_or_existing_trigger_path": True,
                "repacketized_from_operator_feedback": bool(source_operator_resolution_receipt_id),
                "does_not_imply_execution": True,
                "does_not_override_admission": True,
                "requires_existing_trigger_path_for_follow_on_action": True,
                "historical_packet_state_preserved": True,
            },
        ),
    }
    return packet


def append_handoff_packet_ledger(repo_root: Path, packet: Mapping[str, Any]) -> Path:
    """Append one bounded handoff packet to the proof-visible packet ledger."""

    ledger_path = repo_root.resolve() / "glow/orchestration/orchestration_handoff_packets.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(packet), sort_keys=True) + "\n")
    return ledger_path


def append_orchestration_fulfillment_receipt_ledger(repo_root: Path, receipt: Mapping[str, Any]) -> Path:
    """Append one bounded fulfillment receipt to the proof-visible receipt ledger."""

    ledger_path = repo_root.resolve() / "glow/orchestration/orchestration_fulfillment_receipts.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(receipt), sort_keys=True) + "\n")
    return ledger_path


def append_operator_resolution_receipt_ledger(repo_root: Path, receipt: Mapping[str, Any]) -> Path:
    """Append one bounded operator resolution receipt to the proof-visible receipt ledger."""

    ledger_path = repo_root.resolve() / "glow/orchestration/operator_resolution_receipts.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(receipt), sort_keys=True) + "\n")
    return ledger_path


def ingest_operator_resolution_receipt(
    repo_root: Path,
    *,
    operator_action_brief_id: str,
    resolution_kind: str,
    operator_note: str,
    updated_context_refs: list[str] | None = None,
    redirected_venue: str | None = None,
    operator_provenance: str = "human_operator",
    created_at: str | None = None,
) -> dict[str, Any]:
    """
    Ingest one bounded operator resolution outcome for a held/escalated operator brief.

    This path is receipt-only and preserves operator intervention as constitutional history.
    """

    root = repo_root.resolve()
    if not operator_action_brief_id.strip():
        raise ValueError("operator_action_brief_id is required")

    if resolution_kind not in _OPERATOR_RESOLUTION_KINDS:
        raise ValueError(f"unrecognized resolution_kind: {resolution_kind}")

    briefs = _read_jsonl(root / "glow/orchestration/operator_action_briefs.jsonl")
    matching_briefs = [row for row in briefs if str(row.get("operator_action_brief_id") or "") == operator_action_brief_id]
    brief = matching_briefs[-1] if matching_briefs else None
    if not isinstance(brief, Mapping):
        raise ValueError(f"operator action brief not found: {operator_action_brief_id}")

    source_proposal_ref = brief.get("source_next_move_proposal_ref")
    source_proposal_ref_map = source_proposal_ref if isinstance(source_proposal_ref, Mapping) else {}
    source_gate_ref = brief.get("source_packetization_gate_ref")
    source_gate_ref_map = source_gate_ref if isinstance(source_gate_ref, Mapping) else {}

    source_proposal_id = str(source_proposal_ref_map.get("proposal_id") or "")
    gate_outcome = str(source_gate_ref_map.get("packetization_outcome") or "")
    gate_kind = str(source_gate_ref_map.get("gate_kind") or "")
    if not source_proposal_id:
        raise ValueError(f"operator action brief malformed (missing source proposal linkage): {operator_action_brief_id}")
    if not gate_outcome or not gate_kind:
        raise ValueError(f"operator action brief malformed (missing packetization gate linkage): {operator_action_brief_id}")

    target_venue_or_posture = str(brief.get("target_venue_or_posture") or "")
    normalized_refs = [
        ref.strip()
        for ref in (updated_context_refs or [])
        if isinstance(ref, str) and ref.strip()
    ]
    timestamp = created_at or _iso_utc_now()
    resolution_state = {
        "approved_continue": "operator_approved_continue",
        "approved_with_constraints": "operator_approved_with_constraints",
        "declined": "operator_declined",
        "deferred": "operator_deferred",
        "supplied_missing_context": "operator_supplied_missing_context",
        "redirected_venue": "operator_redirected",
        "cancelled": "operator_declined",
    }[resolution_kind]

    receipt = {
        "schema_version": "operator_resolution_receipt.v1",
        "ingested_at": timestamp,
        "operator_resolution_receipt_id": _operator_resolution_receipt_id(
            created_at=timestamp,
            operator_action_brief_id=operator_action_brief_id,
            resolution_kind=resolution_kind,
        ),
        "source_operator_action_brief_ref": {
            "operator_action_brief_id": operator_action_brief_id,
            "operator_action_brief_ledger_path": "glow/orchestration/operator_action_briefs.jsonl",
        },
        "source_next_move_proposal_ref": {
            "proposal_id": source_proposal_id,
            "proposal_ledger_path": "glow/orchestration/orchestration_next_move_proposals.jsonl",
            "source_judgment_linkage_id": source_proposal_ref_map.get("source_judgment_linkage_id"),
        },
        "source_packetization_gate_ref": {
            "gate_kind": gate_kind,
            "packetization_outcome": gate_outcome,
            "gate_schema_version": source_gate_ref_map.get("gate_schema_version"),
        },
        "resolution_kind": resolution_kind,
        "resolution_lifecycle_state": resolution_state,
        "operator_note": operator_note.strip() or "operator_resolution_ingested_without_additional_note",
        "updated_context_refs": normalized_refs,
        "redirected_venue": redirected_venue.strip() if isinstance(redirected_venue, str) and redirected_venue.strip() else None,
        "target_venue_or_posture_hint": target_venue_or_posture or None,
        "trust_confidence_posture": brief.get("trust_confidence_posture"),
        "operator_provenance": operator_provenance.strip() or "human_operator",
        "ingested_operator_outcome": True,
        "explicit_clarity": "ingested operator outcome, not repo execution",
        **_anti_sovereignty_payload(
            recommendation_only=False,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "does_not_imply_repo_self-authorization": True,
                "does_not_imply_repo_self_authorization": True,
                "non_authoritative": True,
                "decision_power": "none",
                "receipt_only": True,
                "requires_existing_trigger_path_for_any_follow-on_action": True,
                "requires_existing_trigger_path_for_any_follow_on_action": True,
            },
        ),
    }
    ledger_path = append_operator_resolution_receipt_ledger(root, receipt)
    return {**receipt, "ledger_path": str(ledger_path.relative_to(root))}


def ingest_external_fulfillment_receipt(
    repo_root: Path,
    *,
    handoff_packet_id: str,
    fulfillment_kind: str,
    operator_or_adapter: str,
    summary_notes: str,
    evidence_refs: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """
    Ingest one externally supplied fulfillment outcome for a staged handoff packet.

    This path is receipt-only and never executes external work directly.
    """

    root = repo_root.resolve()
    packets = _read_jsonl(root / "glow/orchestration/orchestration_handoff_packets.jsonl")
    matching_packets = [row for row in packets if str(row.get("handoff_packet_id") or "") == handoff_packet_id]
    packet = matching_packets[-1] if matching_packets else None
    if not isinstance(packet, Mapping):
        raise ValueError(f"handoff packet not found: {handoff_packet_id}")

    venue = str(packet.get("target_venue") or "")
    if venue not in {"codex_implementation", "deep_research_audit"}:
        raise ValueError(f"handoff packet is not a staged external venue packet: {handoff_packet_id}")

    proposal_ref = packet.get("source_next_move_proposal_ref")
    proposal_ref_map = proposal_ref if isinstance(proposal_ref, Mapping) else {}
    proposal_id = str(proposal_ref_map.get("proposal_id") or "")
    if not proposal_id:
        raise ValueError(f"handoff packet missing source next_move proposal linkage: {handoff_packet_id}")

    if fulfillment_kind not in _FULFILLMENT_KINDS:
        raise ValueError(f"unrecognized fulfillment_kind: {fulfillment_kind}")

    timestamp = created_at or _iso_utc_now()
    compact_refs = [
        ref.strip()
        for ref in (evidence_refs or [])
        if isinstance(ref, str) and ref.strip()
    ]
    operator_state = packet.get("operator_escalation_requirement_state")
    operator_state_map = operator_state if isinstance(operator_state, Mapping) else {}
    source_judgment_ref = packet.get("source_delegated_judgment_ref")
    source_judgment_ref_map = source_judgment_ref if isinstance(source_judgment_ref, Mapping) else {}

    receipt = {
        "schema_version": "orchestration_fulfillment_receipt.v1",
        "ingested_at": timestamp,
        "fulfillment_receipt_id": _fulfillment_receipt_id(
            created_at=timestamp,
            handoff_packet_id=handoff_packet_id,
            venue=venue,
            fulfillment_kind=fulfillment_kind,
        ),
        "source_handoff_packet_ref": {
            "handoff_packet_id": handoff_packet_id,
            "handoff_packet_ledger_path": "glow/orchestration/orchestration_handoff_packets.jsonl",
        },
        "source_next_move_proposal_ref": {
            "proposal_id": proposal_id,
            "proposal_ledger_path": "glow/orchestration/orchestration_next_move_proposals.jsonl",
        },
        "source_venue": venue,
        "fulfillment_kind": fulfillment_kind,
        "operator_or_adapter_provenance": operator_or_adapter.strip() or "unspecified_external_actor",
        "summary_notes": summary_notes.strip() or "external_fulfillment_ingested_without_additional_summary",
        "evidence_refs": compact_refs,
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": bool(operator_state_map.get("requires_operator_or_escalation")),
            "attention_signal": str(operator_state_map.get("attention_signal") or ""),
            "escalation_classification": str(operator_state_map.get("escalation_classification") or ""),
        },
        "source_delegated_judgment_ref": {
            "source_judgment_linkage_id": str(source_judgment_ref_map.get("source_judgment_linkage_id") or ""),
            "recommended_venue": str(source_judgment_ref_map.get("recommended_venue") or ""),
        },
        "ingested_external_outcome": True,
        "explicit_clarity": "ingested external outcome, not direct repo execution",
        **_anti_sovereignty_payload(
            recommendation_only=False,
            diagnostic_only=True,
            does_not_invoke_external_tools=True,
            additional_fields={
                "does_not_imply_direct_repo_execution": True,
                "receipt_only": True,
                "requires_external_actor_or_operator": True,
                "non_authoritative": True,
                "decision_power": "none",
            },
        ),
    }
    ledger_path = append_orchestration_fulfillment_receipt_ledger(root, receipt)
    return {**receipt, "ledger_path": str(ledger_path.relative_to(root))}


def resolve_handoff_packet_fulfillment_lifecycle(
    repo_root: Path,
    handoff_packet: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve staged/fulfilled visibility for one external handoff packet."""

    root = repo_root.resolve()
    venue = str(handoff_packet.get("target_venue") or "")
    packet_id = str(handoff_packet.get("handoff_packet_id") or "")
    receipts = _read_jsonl(root / "glow/orchestration/orchestration_fulfillment_receipts.jsonl")
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

    if lifecycle_state not in _STAGED_EXTERNAL_LIFECYCLE_STATES:
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


def resolve_operator_action_brief_lifecycle(
    repo_root: Path,
    operator_action_brief: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Resolve bounded lifecycle visibility for one operator action brief."""

    root = repo_root.resolve()
    brief_map = operator_action_brief if isinstance(operator_action_brief, Mapping) else {}
    brief_id = str(brief_map.get("operator_action_brief_id") or "")
    receipts = _read_jsonl(root / "glow/orchestration/operator_resolution_receipts.jsonl")
    linked = [
        row
        for row in receipts
        if str((row.get("source_operator_action_brief_ref") or {}).get("operator_action_brief_id") or "") == brief_id
    ]
    latest = linked[-1] if linked else None

    lifecycle_state = "fragmented_unlinked_operator_resolution"
    resolution_received = False
    resolution_kind = None
    receipt_id = None
    if brief_id:
        lifecycle_state = "brief_emitted"
        if isinstance(latest, Mapping):
            resolution_kind_value = str(latest.get("resolution_kind") or "")
            lifecycle_state = {
                "approved_continue": "operator_approved_continue",
                "approved_with_constraints": "operator_approved_with_constraints",
                "declined": "operator_declined",
                "deferred": "operator_deferred",
                "supplied_missing_context": "operator_supplied_missing_context",
                "redirected_venue": "operator_redirected",
                "cancelled": "operator_declined",
            }.get(resolution_kind_value, "fragmented_unlinked_operator_resolution")
            resolution_received = lifecycle_state != "fragmented_unlinked_operator_resolution"
            resolution_kind = resolution_kind_value or None
            receipt_id = str(latest.get("operator_resolution_receipt_id") or "") or None

    if lifecycle_state not in _OPERATOR_BRIEF_LIFECYCLE_STATES:
        lifecycle_state = "fragmented_unlinked_operator_resolution"

    return {
        "schema_version": "operator_action_brief_lifecycle.v1",
        "operator_action_brief_id": brief_id or None,
        "lifecycle_state": lifecycle_state,
        "operator_resolution_received": resolution_received,
        "resolution_kind": resolution_kind,
        "operator_resolution_receipt_id": receipt_id,
        "receipt_artifact_path": "glow/orchestration/operator_resolution_receipts.jsonl",
        "ingested_operator_outcome": bool((latest or {}).get("ingested_operator_outcome")) if isinstance(latest, Mapping) else False,
        "awaiting_operator_input": bool(brief_id) and not resolution_received,
        "has_operator_guidance": resolution_received,
        "operator_intervention_human_mediated": True,
        "does_not_imply_repo_execution": True,
        "non_authoritative": True,
        "decision_power": "none",
        "receipt_only": True,
        "requires_existing_trigger_path_for_any_follow-on_action": True,
    }


def derive_next_move_proposal_review(
    repo_root: Path,
    *,
    window_size: int = 10,
) -> dict[str, Any]:
    """Derive a bounded retrospective review over recent next-move proposal behavior."""

    root = repo_root.resolve()
    proposals = _read_jsonl(root / "glow/orchestration/orchestration_next_move_proposals.jsonl")
    recent = proposals[-max(0, window_size) :] if window_size > 0 else []

    relation_counts = {posture: 0 for posture in _NEXT_VENUE_RELATIONS}
    venue_counts = {
        "internal_direct_execution": 0,
        "codex_implementation": 0,
        "deep_research_audit": 0,
        "operator_decision_required": 0,
        "insufficient_context": 0,
    }
    executability_counts = {name: 0 for name in _NEXT_MOVE_EXECUTABILITY}
    escalation_count = 0
    insufficient_context_count = 0
    venue_switches = 0
    valid_venue_transitions = 0
    prev_venue = ""
    unique_venues: set[str] = set()

    for row in recent:
        relation = str(row.get("relation_posture") or "insufficient_context")
        if relation not in relation_counts:
            relation = "insufficient_context"
        relation_counts[relation] += 1

        proposed_next_action = row.get("proposed_next_action")
        proposed_next_action_map = proposed_next_action if isinstance(proposed_next_action, Mapping) else {}
        venue = str(proposed_next_action_map.get("proposed_venue") or "insufficient_context")
        if venue not in venue_counts:
            venue = "insufficient_context"
        venue_counts[venue] += 1
        if venue != "insufficient_context":
            unique_venues.add(venue)
        if prev_venue and venue != "insufficient_context":
            valid_venue_transitions += 1
            if venue != prev_venue:
                venue_switches += 1
        if venue != "insufficient_context":
            prev_venue = venue

        executability = str(row.get("executability_classification") or "blocked_insufficient_context")
        if executability not in executability_counts:
            executability = "blocked_insufficient_context"
        executability_counts[executability] += 1

        operator_state = row.get("operator_escalation_requirement_state")
        operator_state_map = operator_state if isinstance(operator_state, Mapping) else {}
        if relation == "escalating" or bool(operator_state_map.get("requires_operator_or_escalation")):
            escalation_count += 1
        if relation == "insufficient_context" or executability == "blocked_insufficient_context":
            insufficient_context_count += 1

    records_considered = len(recent)
    heavy_threshold = max(2, (records_considered + 1) // 2)
    escalation_heavy = records_considered >= 3 and escalation_count >= heavy_threshold
    hold_heavy = records_considered >= 3 and relation_counts["holding"] >= heavy_threshold
    insufficient_context_heavy = records_considered >= 3 and insufficient_context_count >= heavy_threshold
    venue_switch_ratio = (venue_switches / valid_venue_transitions) if valid_venue_transitions else 0.0
    venue_thrash = (
        records_considered >= 4
        and valid_venue_transitions >= 3
        and venue_switch_ratio >= 0.6
        and len(unique_venues) >= 2
    )
    stress_flag_count = sum(1 for flag in (escalation_heavy, hold_heavy, insufficient_context_heavy, venue_thrash) if flag)

    relation_supporting_coherence = relation_counts["affirming"] + relation_counts["nudging"]
    executable_or_staged = executability_counts["executable_now"] + executability_counts["stageable_external_work_order"]
    coherent = (
        records_considered >= 3
        and stress_flag_count == 0
        and relation_supporting_coherence >= heavy_threshold
        and executable_or_staged >= heavy_threshold
    )

    classification = "insufficient_history"
    compact_reason = "insufficient_recent_next_move_proposal_history_for_reliable_retrospective_classification"
    if records_considered >= 3:
        if stress_flag_count >= 2:
            classification = "mixed_proposal_stress"
            compact_reason = "multiple_competing_stress_patterns_present_across_recent_next_move_proposals"
        elif escalation_heavy:
            classification = "proposal_escalation_heavy"
            compact_reason = "escalation_signals_dominate_recent_next_move_proposals"
        elif hold_heavy:
            classification = "proposal_hold_heavy"
            compact_reason = "holding_relation_posture_dominates_recent_next_move_proposals"
        elif insufficient_context_heavy:
            classification = "proposal_insufficient_context_heavy"
            compact_reason = "insufficient_context_signals_dominate_recent_next_move_proposals"
        elif venue_thrash:
            classification = "proposal_venue_thrash"
            compact_reason = "recent_next_move_proposals_switch_venues_frequently_without_stable_pattern"
        elif coherent:
            classification = "coherent_recent_proposals"
            compact_reason = "recent_next_move_proposals_are_mostly_relation_consistent_and_executability_sane"
        else:
            classification = "mixed_proposal_stress"
            compact_reason = "recent_next_move_proposals_are_neither_clearly_coherent_nor_singly_stressed"

    if classification not in _NEXT_MOVE_PROPOSAL_REVIEW_CLASSES:
        classification = "mixed_proposal_stress"
        compact_reason = "unrecognized_next_move_proposal_review_classification_defaulted_to_mixed_proposal_stress"

    return {
        "schema_version": "next_move_proposal_review.v1",
        "review_kind": "next_move_proposal_retrospective",
        "review_classification": classification,
        "window_size": max(0, window_size),
        "records_considered": records_considered,
        "recent_counts": {
            "by_relation_posture": relation_counts,
            "by_proposed_venue": venue_counts,
            "by_executability_classification": executability_counts,
            "escalation_or_operator_required": escalation_count,
            "insufficient_context": insufficient_context_count,
        },
        "summary": {
            "proposal_behavior_posture": "coherent" if classification == "coherent_recent_proposals" else "stressed_or_uncertain",
            "compact_reason": compact_reason,
            "diagnostic_summary": "bounded retrospective review derived from existing next-move proposal and orchestration signals only",
        },
        "condition_flags": {
            "escalation_heavy": escalation_heavy,
            "hold_heavy": hold_heavy,
            "insufficient_context_heavy": insufficient_context_heavy,
            "venue_thrash": venue_thrash,
            "competing_stress_patterns": stress_flag_count >= 2,
        },
        "artifacts_read": {
            "next_move_proposal_ledger": "glow/orchestration/orchestration_next_move_proposals.jsonl",
            "relation_posture_field": "relation_posture",
            "proposed_next_action_field": "proposed_next_action.proposed_venue",
            "executability_field": "executability_classification",
            "operator_escalation_field": "operator_escalation_requirement_state.requires_operator_or_escalation",
        },
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "review_only": True,
                "decision_power": "none",
                "non_authoritative": True,
                "diagnostic_only": True,
            },
        ),
    }


def derive_proposal_packet_continuity_review(
    repo_root: Path,
    *,
    window_size: int = 10,
) -> dict[str, Any]:
    """Derive a bounded retrospective continuity classifier from proposal->packet lineage artifacts only."""

    root = repo_root.resolve()
    proposals = _read_jsonl(root / "glow/orchestration/orchestration_next_move_proposals.jsonl")
    packets = _read_jsonl(root / "glow/orchestration/orchestration_handoff_packets.jsonl")
    briefs = _read_jsonl(root / "glow/orchestration/operator_action_briefs.jsonl")
    operator_receipts = _read_jsonl(root / "glow/orchestration/operator_resolution_receipts.jsonl")
    recent = proposals[-max(0, window_size) :] if window_size > 0 else []
    recent_proposal_ids = [str(row.get("proposal_id") or "") for row in recent if str(row.get("proposal_id") or "")]
    proposal_id_set = set(recent_proposal_ids)
    records_considered = len(recent_proposal_ids)

    linked_packets = [
        row
        for row in packets
        if str((row.get("source_next_move_proposal_ref") or {}).get("proposal_id") or "") in proposal_id_set
    ]
    linked_briefs = [
        row
        for row in briefs
        if str((row.get("source_next_move_proposal_ref") or {}).get("proposal_id") or "") in proposal_id_set
    ]
    linked_receipts = [
        row
        for row in operator_receipts
        if str((row.get("source_next_move_proposal_ref") or {}).get("proposal_id") or "") in proposal_id_set
    ]

    hold_related_count = 0
    for row in linked_packets + linked_briefs:
        packetization_outcome = str((row.get("source_packetization_gate_ref") or {}).get("packetization_outcome") or "")
        if packetization_outcome.startswith("packetization_hold_"):
            hold_related_count += 1

    redirect_receipt_count = sum(1 for row in linked_receipts if str(row.get("resolution_kind") or "") == "redirected_venue")
    redirect_refresh_count = 0
    repacketization_count = 0
    broken_lineage_count = 0
    stable_active_packet_count = 0
    for proposal_id in recent_proposal_ids:
        proposal_packets = [
            row
            for row in linked_packets
            if str((row.get("source_next_move_proposal_ref") or {}).get("proposal_id") or "") == proposal_id
        ]
        packet_ids = {str(row.get("handoff_packet_id") or "") for row in proposal_packets if str(row.get("handoff_packet_id") or "")}
        current_candidates = 0
        for row in proposal_packets:
            lineage_map = row.get("packet_lineage") if isinstance(row.get("packet_lineage"), Mapping) else {}
            supersedes_id = str(lineage_map.get("supersedes_handoff_packet_id") or "")
            if supersedes_id:
                repacketization_count += 1
                if supersedes_id not in packet_ids:
                    broken_lineage_count += 1
            if bool(row.get("repacketized_from_operator_feedback")):
                repacketization_count += 1
            refresh_reason = str(lineage_map.get("refresh_reason") or "")
            if refresh_reason == "operator_redirected_venue_refresh":
                redirect_refresh_count += 1
            if bool(lineage_map.get("current_packet_candidate", True)):
                current_candidates += 1
        if current_candidates > 1:
            broken_lineage_count += 1

        active = resolve_active_handoff_packet_candidate(root, proposal_id)
        active_present = bool(active.get("active_packet_present"))
        active_id = str(active.get("active_handoff_packet_id") or "")
        if proposal_packets and (not active_present or not active_id):
            broken_lineage_count += 1
        if active_present and active.get("current_packet_candidate") and active_id:
            stable_active_packet_count += 1

    redirect_related_count = redirect_receipt_count + redirect_refresh_count
    recent_packet_count = len(linked_packets)
    proposals_with_packets = sum(
        1
        for proposal_id in recent_proposal_ids
        if any(str((row.get("source_next_move_proposal_ref") or {}).get("proposal_id") or "") == proposal_id for row in linked_packets)
    )
    stable_emergence_ratio = (stable_active_packet_count / proposals_with_packets) if proposals_with_packets else 0.0
    stable_active_packet_usually_emerges = proposals_with_packets > 0 and stable_emergence_ratio >= 0.67

    hold_heavy = hold_related_count >= max(2, (records_considered + 1) // 2)
    redirect_heavy = redirect_related_count >= max(2, (records_considered + 1) // 2)
    churn_heavy = repacketization_count >= max(3, records_considered) and not stable_active_packet_usually_emerges
    fragmented = broken_lineage_count > 0 or (
        records_considered >= 3 and recent_packet_count > 0 and not stable_active_packet_usually_emerges
    )
    coherent = (
        records_considered >= 3
        and recent_packet_count >= 2
        and hold_related_count <= 1
        and redirect_related_count <= 1
        and repacketization_count <= max(1, records_considered // 2)
        and broken_lineage_count == 0
        and stable_active_packet_usually_emerges
    )

    classification = "insufficient_history"
    compact_reason = "insufficient_recent_proposal_packet_history_for_reliable_continuity_review"
    if records_considered >= 3:
        if churn_heavy:
            classification = "repacketization_churn"
            compact_reason = "repeated_repacketization_without_consistent_stable_active_packet_emergence"
        elif fragmented:
            classification = "fragmented_continuity"
            compact_reason = "proposal_packet_linkage_or_active_candidate_resolution_is_fragmented"
        elif hold_heavy:
            classification = "hold_heavy_continuity"
            compact_reason = "packetization_hold_outcomes_repeat_across_recent_proposal_to_packet_flow"
        elif redirect_heavy:
            classification = "redirect_heavy_continuity"
            compact_reason = "redirect_linked_operator_or_lineage_signals_repeat_across_recent_packets"
        elif coherent:
            classification = "coherent_proposal_packet_continuity"
            compact_reason = "recent_proposals_usually_resolve_to_stable_active_packets_with_low_hold_redirect_churn"
        else:
            classification = "fragmented_continuity"
            compact_reason = "proposal_to_packet_continuity_is_not_yet_coherently_stable"

    if classification not in _PROPOSAL_PACKET_CONTINUITY_CLASSES:
        classification = "fragmented_continuity"
        compact_reason = "unrecognized_continuity_classification_defaulted_to_fragmented_continuity"

    return {
        "schema_version": "proposal_packet_continuity_review.v1",
        "review_kind": "proposal_packet_continuity_retrospective",
        "review_classification": classification,
        "window_size": max(0, window_size),
        "records_considered": records_considered,
        "continuity_counts": {
            "recent_proposal_count": records_considered,
            "recent_packet_count": recent_packet_count,
            "repacketization_count": repacketization_count,
            "redirect_related_count": redirect_related_count,
            "hold_related_count": hold_related_count,
            "broken_lineage_count": broken_lineage_count,
            "stable_active_packet_count": stable_active_packet_count,
            "proposals_with_packets": proposals_with_packets,
        },
        "summary": {
            "stable_active_packet_usually_emerges": stable_active_packet_usually_emerges,
            "stable_active_packet_emergence_ratio": round(stable_emergence_ratio, 4),
            "compact_reason": compact_reason,
            "diagnostic_summary": "bounded retrospective continuity review derived from existing proposal/packet/operator lineage artifacts only",
            "boundaries": {
                "diagnostic_only": True,
                "non_authoritative": True,
                "decision_power": "none",
                "review_only": True,
            },
        },
        "artifacts_read": {
            "next_move_proposal_ledger": "glow/orchestration/orchestration_next_move_proposals.jsonl",
            "handoff_packet_ledger": "glow/orchestration/orchestration_handoff_packets.jsonl",
            "operator_action_brief_ledger": "glow/orchestration/operator_action_briefs.jsonl",
            "operator_resolution_receipt_ledger": "glow/orchestration/operator_resolution_receipts.jsonl",
            "packetization_gate_outcomes_from": [
                "handoff_packet.source_packetization_gate_ref.packetization_outcome",
                "operator_action_brief.source_packetization_gate_ref.packetization_outcome",
            ],
            "active_packet_candidate_resolver": "resolve_active_handoff_packet_candidate",
        },
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "review_only": True,
                "non_authoritative": True,
                "decision_power": "none",
            },
        ),
    }


def derive_orchestration_trust_confidence_posture(
    next_move_proposal_review: Mapping[str, Any],
    venue_mix_review: Mapping[str, Any],
    outcome_review: Mapping[str, Any],
    unified_result_quality_review: Mapping[str, Any],
    operator_attention_recommendation: Mapping[str, Any],
    proposal_packet_continuity_review: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Derive one compact orchestration trust/confidence posture from existing review surfaces only.

    This is diagnostic-only and never grants authority, admission, or execution power.
    """

    proposal_classification = str(next_move_proposal_review.get("review_classification") or "insufficient_history")
    venue_classification = str(venue_mix_review.get("review_classification") or "insufficient_history")
    outcome_classification = str(outcome_review.get("review_classification") or "insufficient_history")
    result_quality_classification = str(unified_result_quality_review.get("review_classification") or "insufficient_history")
    attention = str(operator_attention_recommendation.get("operator_attention_recommendation") or "insufficient_context")
    continuity_map = proposal_packet_continuity_review if isinstance(proposal_packet_continuity_review, Mapping) else {}
    continuity_classification = str(continuity_map.get("review_classification") or "insufficient_history")

    records_counts = {
        "next_move_proposal_review": int(next_move_proposal_review.get("records_considered") or 0),
        "orchestration_venue_mix_review": int(venue_mix_review.get("records_considered") or 0),
        "orchestration_outcome_review": int(outcome_review.get("records_considered") or 0),
        "unified_result_quality_review": int(unified_result_quality_review.get("records_considered") or 0),
    }
    minimum_records = min(records_counts.values()) if records_counts else 0
    insufficient_history = minimum_records < 3

    proposal_stress = proposal_classification in {
        "proposal_escalation_heavy",
        "proposal_hold_heavy",
        "proposal_insufficient_context_heavy",
        "proposal_venue_thrash",
        "mixed_proposal_stress",
    }
    proposal_coherent = proposal_classification == "coherent_recent_proposals"

    venue_stress = venue_classification in {
        "operator_escalation_heavy",
        "mixed_venue_stress",
    }
    venue_balanced = venue_classification == "balanced_recent_venue_mix"

    result_quality_stress = result_quality_classification in {
        "issues_heavy",
        "abandonment_or_decline_heavy",
        "mixed_result_stress",
    }
    result_quality_healthy = result_quality_classification == "healthy_recent_results"

    fragmentation_flag = (
        result_quality_classification == "fragmentation_heavy"
        or outcome_classification == "mixed_orchestration_stress"
        and bool((outcome_review.get("condition_flags") or {}).get("external_stress_heavy"))
        and bool((unified_result_quality_review.get("condition_flags") or {}).get("fragmentation_heavy"))
    )
    outcome_stressed = outcome_classification in {
        "handoff_block_heavy",
        "execution_failure_heavy",
        "pending_stall_pattern",
        "mixed_orchestration_stress",
    }
    escalation_operator_dependence = (
        attention in {"inspect_handoff_blocks", "inspect_execution_failures", "inspect_pending_stall", "insufficient_context"}
        or proposal_classification == "proposal_escalation_heavy"
        or venue_classification == "operator_escalation_heavy"
    )

    stress_components = {
        "proposal_stress": proposal_stress,
        "venue_stress": venue_stress,
        "result_quality_stress": result_quality_stress or outcome_stressed,
        "escalation_operator_dependence": escalation_operator_dependence,
        "fragmentation": fragmentation_flag,
    }
    stress_count = sum(1 for active in stress_components.values() if active)
    major_stress_count = sum(
        1
        for active in (
            proposal_stress,
            venue_stress,
            result_quality_stress,
            fragmentation_flag,
        )
        if active
    )

    posture = "insufficient_history"
    compact_reason = "insufficient_recent_review_history_for_conservative_trust_posture"
    primary_pressure = "insufficient_history"

    if insufficient_history:
        posture = "insufficient_history"
        compact_reason = "insufficient_recent_review_history_for_conservative_trust_posture"
        primary_pressure = "insufficient_history"
    elif fragmentation_flag:
        posture = "fragmented_or_unreliable"
        compact_reason = "fragmentation_or_unreliable_linkage_signals_dominate_recent_orchestration_reviews"
        primary_pressure = "fragmentation"
    elif major_stress_count >= 3:
        posture = "fragmented_or_unreliable"
        compact_reason = "multiple_major_stress_signals_converge_across_proposal_venue_outcome_and_result_quality_reviews"
        primary_pressure = "mixed_stress"
    elif proposal_coherent and venue_balanced and result_quality_healthy and not escalation_operator_dependence:
        posture = "trusted_for_bounded_use"
        compact_reason = "recent_proposals_venues_and_unified_results_are_coherent_with_low_operator_dependence"
        primary_pressure = "none"
    elif stress_count >= 2:
        posture = "stressed_but_usable"
        compact_reason = "repeated_stress_patterns_present_but_recent_orchestration_remains_interpretable_for_bounded_use"
        primary_pressure = "mixed_stress"
    elif stress_count == 1 or outcome_classification in {"mixed_orchestration_stress", "handoff_block_heavy"}:
        posture = "caution_required"
        compact_reason = "some_stress_present_but_loop_remains_coherent_enough_for_conservative_bounded_use"
        if proposal_stress:
            primary_pressure = "proposal_stress"
        elif venue_stress:
            primary_pressure = "venue_stress"
        elif result_quality_stress or outcome_stressed:
            primary_pressure = "result_quality_stress"
        elif escalation_operator_dependence:
            primary_pressure = "escalation_operator_dependence"
        else:
            primary_pressure = "mixed_stress"
    else:
        posture = "caution_required"
        compact_reason = "review_mix_is_non_fragmented_but_not_clean_enough_for_trusted_posture"
        primary_pressure = "mixed_stress"

    if posture not in _ORCHESTRATION_TRUST_POSTURES:
        posture = "caution_required"
    if primary_pressure not in _ORCHESTRATION_TRUST_PRESSURE_KINDS:
        primary_pressure = "mixed_stress"

    return {
        "schema_version": "orchestration_trust_confidence_posture.v1",
        "review_kind": "orchestration_trust_confidence_diagnostic",
        "trust_confidence_posture": posture,
        "window_considered": {
            "records_considered_by_review": records_counts,
            "minimum_records_considered": minimum_records,
        },
        "contributing_reviews": {
            "next_move_proposal_review": {
                "review_classification": proposal_classification,
                "records_considered": records_counts["next_move_proposal_review"],
            },
            "orchestration_venue_mix_review": {
                "review_classification": venue_classification,
                "records_considered": records_counts["orchestration_venue_mix_review"],
            },
            "orchestration_outcome_review": {
                "review_classification": outcome_classification,
                "records_considered": records_counts["orchestration_outcome_review"],
            },
            "unified_result_quality_review": {
                "review_classification": result_quality_classification,
                "records_considered": records_counts["unified_result_quality_review"],
            },
            "operator_attention_recommendation": attention,
            "proposal_packet_continuity_review": {
                "review_classification": continuity_classification,
                "records_considered": int(continuity_map.get("records_considered") or 0),
                "bounded_basis_only": True,
            },
        },
        "pressure_summary": {
            "primary_pressure": primary_pressure,
            "stress_components": stress_components,
            "compact_basis": compact_reason,
        },
        "summary": {
            "diagnostic_summary": "bounded trust/confidence posture derived from existing orchestration review signals only",
            "derived_from_existing_reviews_only": [
                "next_move_proposal_review",
                "orchestration_venue_mix_review",
                "orchestration_outcome_review",
                "unified_result_quality_review",
                "orchestration_operator_attention_recommendation",
                "proposal_packet_continuity_review",
            ],
            "compact_rationale": compact_reason,
        },
        **_anti_sovereignty_payload(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "review_only": True,
                "decision_power": "none",
                "non_authoritative": True,
            },
        ),
    }


def executable_handoff_map() -> dict[str, Any]:
    return {
        "intent_kind_to_handoff": {
            "internal_maintenance_execution": {
                "execution_target": "task_admission_executor",
                "executability_classification": "executable_now",
                "admission_surface": "task_admission.admit",
                "handoff_path_status": "operational",
            },
            "codex_work_order": {
                "execution_target": "no_execution_target_yet",
                "executability_classification": "stageable_external_work_order",
                "admission_surface": "none",
                "handoff_path_status": "staged_only",
            },
            "deep_research_work_order": {
                "execution_target": "no_execution_target_yet",
                "executability_classification": "stageable_external_work_order",
                "admission_surface": "none",
                "handoff_path_status": "staged_only",
            },
            "operator_review_request": {
                "execution_target": "no_execution_target_yet",
                "executability_classification": "blocked_operator_required",
                "admission_surface": "operator-only",
                "handoff_path_status": "blocked_or_staged",
            },
            "hold_no_action": {
                "execution_target": "no_execution_target_yet",
                "executability_classification": "no_action_recommended",
                "admission_surface": "none",
                "handoff_path_status": "not_applicable",
            },
        },
        "known_named_targets_without_handoff_path": [
            "mutation_router",
            "federation_canonical_execution",
            "external_tool_placeholder",
        ],
    }


def admit_orchestration_intent(
    repo_root: Path,
    intent: Mapping[str, Any],
    *,
    admission_context: task_admission.AdmissionContext | None = None,
    admission_policy: task_admission.AdmissionPolicy | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    missing_fields = _validate_handoff_minimum_fields(intent)
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
        ctx = admission_context or _default_admission_context()
        policy = admission_policy or _default_admission_policy()
        task = _build_internal_maintenance_task(intent)
        decision = task_admission.admit(task, ctx, policy)
        task_admission._log_admission_event(decision, task, ctx, policy)
        details["task_admission"] = {
            "task_id": task.task_id,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "policy_version": decision.policy_version,
            "constraints": decision.constraints,
            "log_path": str(task_admission._resolve_admission_log_path().relative_to(root))
            if task_admission._resolve_admission_log_path().is_relative_to(root)
            else str(task_admission._resolve_admission_log_path()),
        }
        outcome = "admitted_to_execution_substrate" if decision.allowed else "blocked_by_admission"

    if outcome not in _HANDOFF_OUTCOMES:
        outcome = "blocked_by_insufficient_context"

    codex_work_order_record = None
    if str(intent.get("intent_kind") or "") == "codex_work_order":
        codex_work_order_record = build_codex_staged_work_order(intent, handoff_outcome=outcome)
        codex_path = append_codex_work_order_ledger(root, codex_work_order_record)
        details["codex_work_order_ref"] = {
            "work_order_id": codex_work_order_record["work_order_id"],
            "ledger_path": str(codex_path.relative_to(root)),
            "status": codex_work_order_record["status"],
            "staged_only": True,
            "does_not_invoke_codex_directly": True,
            "requires_external_tool_or_operator_trigger": True,
        }
    if str(intent.get("intent_kind") or "") == "deep_research_work_order":
        deep_research_work_order_record = build_deep_research_staged_work_order(intent, handoff_outcome=outcome)
        deep_research_path = append_deep_research_work_order_ledger(root, deep_research_work_order_record)
        details["deep_research_work_order_ref"] = {
            "work_order_id": deep_research_work_order_record["work_order_id"],
            "ledger_path": str(deep_research_path.relative_to(root)),
            "status": deep_research_work_order_record["status"],
            "staged_only": True,
            "does_not_invoke_deep_research_directly": True,
            "requires_external_tool_or_operator_trigger": True,
        }

    handoff_record = {
        "schema_version": "orchestration_handoff.v1",
        "recorded_at": _iso_utc_now(),
        "handoff_outcome": outcome,
        "intent_ref": {
            "intent_id": str(intent.get("intent_id") or ""),
            "intent_kind": str(intent.get("intent_kind") or ""),
        },
        "details": details,
        **_anti_sovereignty_payload(
            recommendation_only=False,
            diagnostic_only=False,
            does_not_invoke_external_tools=True,
        ),
        "does_not_execute_task_directly": True,
    }
    handoff_ledger_path = append_orchestration_handoff_ledger(root, handoff_record)
    return {
        **handoff_record,
        "ledger_path": str(handoff_ledger_path.relative_to(root)),
    }
