from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Mapping


def _intent_id(source_judgment: Mapping[str, Any], created_at: str) -> str:
    canonical = json.dumps(
        {
            "created_at": created_at,
            "source_judgment": dict(source_judgment),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"orh-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def classify_authority_posture(judgment: Mapping[str, Any]) -> str:
    escalation = str(judgment.get("escalation_classification") or "")
    venue = str(judgment.get("recommended_venue") or "")
    if escalation == "escalate_for_missing_context" or venue == "insufficient_context":
        return "insufficient_context_blocked"
    if escalation == "escalate_for_operator_priority":
        return "operator_priority_required"
    if venue in {"codex_implementation", "deep_research_audit", "operator_decision_required"}:
        return "operator_approval_required"
    return "no_additional_operator_approval_required"


def translate_orchestration_kind(judgment: Mapping[str, Any]) -> tuple[str, str, str]:
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


def derive_admission_state(executability: str, authority_posture: str) -> str:
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


def source_judgment_linkage(judgment: Mapping[str, Any]) -> dict[str, Any]:
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


def synthesize_orchestration_intent_kernel(
    delegated_judgment: Mapping[str, Any],
    *,
    created_at: str | None,
    iso_utc_now: Callable[[], str],
    anti_sovereignty_payload: Callable[..., dict[str, Any]],
    intent_kinds: set[str],
    authority_postures: set[str],
    execution_targets: set[str],
    executability_classes: set[str],
    admission_states: set[str],
) -> dict[str, Any]:
    """Kernel authority for canonical intent synthesis/typing/classification."""

    source_linkage = source_judgment_linkage(delegated_judgment)
    authority_posture = classify_authority_posture(delegated_judgment)
    intent_kind, execution_target, executability = translate_orchestration_kind(delegated_judgment)
    admission_state = derive_admission_state(executability, authority_posture)
    timestamp = created_at or iso_utc_now()
    intent_id = _intent_id(source_linkage, timestamp)

    if intent_kind not in intent_kinds:
        intent_kind = "hold_no_action"
    if authority_posture not in authority_postures:
        authority_posture = "insufficient_context_blocked"
    if execution_target not in execution_targets:
        execution_target = "no_execution_target_yet"
    if executability not in executability_classes:
        executability = "blocked_insufficient_context"
    if admission_state not in admission_states:
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
        **anti_sovereignty_payload(
            recommendation_only=False,
            diagnostic_only=False,
            does_not_invoke_external_tools=True,
        ),
        "staged_handoff_only": executability != "executable_now",
        "does_not_override_existing_admission": True,
        "does_not_override_kernel_or_governor": True,
        "does_not_replace_operator_authority": True,
    }


__all__ = [
    "source_judgment_linkage",
    "translate_orchestration_kind",
    "synthesize_orchestration_intent_kernel",
]
