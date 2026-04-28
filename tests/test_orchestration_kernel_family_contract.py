from pathlib import Path

from sentientos.orchestration_spine.kernel.admission_handoff import (
    resolve_admission_handoff_outcome_kernel,
    validate_handoff_minimum_fields_kernel,
)
from sentientos.orchestration_spine.kernel.intent_synthesis import synthesize_orchestration_intent_kernel
from sentientos.orchestration_spine.kernel.unified_results import resolve_unified_orchestration_result_kernel

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

_UNIFIED_CLASSIFICATIONS = {
    "completed_successfully",
    "completed_with_issues",
    "declined_or_abandoned",
    "failed_after_execution",
    "blocked_before_execution",
    "pending_or_unresolved",
    "fragmented_result_history",
}


def _anti_sovereignty_payload(**_kwargs: object) -> dict[str, object]:
    return {
        "non_authoritative": True,
        "decision_power": "none",
    }


def _synthesize(delegated_judgment: dict[str, object], *, created_at: str = "2026-04-28T00:00:00Z") -> dict[str, object]:
    return synthesize_orchestration_intent_kernel(
        delegated_judgment,
        created_at=created_at,
        iso_utc_now=lambda: created_at,
        anti_sovereignty_payload=_anti_sovereignty_payload,
        intent_kinds=_INTENT_KINDS,
        authority_postures=_AUTHORITY_POSTURES,
        execution_targets=_EXECUTION_TARGETS,
        executability_classes=_EXECUTABILITY,
        admission_states=_ADMISSION_STATES,
    )


def test_kernel_family_internal_intent_identity_legality_and_closure_linkage() -> None:
    intent = _synthesize(
        {
            "work_class": "internal_runtime_maintenance",
            "recommended_venue": "internal_direct_execution",
            "next_move_posture": "expand",
            "consolidation_expansion_posture": "consolidate",
            "escalation_classification": "none",
        }
    )

    handoff_outcome, details = resolve_admission_handoff_outcome_kernel(
        intent,
        validate_handoff_minimum_fields=validate_handoff_minimum_fields_kernel,
        handoff_outcomes=_HANDOFF_OUTCOMES,
        admit_internal_maintenance_intent=lambda **_kwargs: {"allowed": True, "receipt_id": "adm-1"},
        now_utc_iso=lambda: "2026-04-28T00:00:00Z",
        root=Path("."),
    )

    handoff = {
        "intent_ref": {
            "intent_id": intent["intent_id"],
            "intent_kind": intent["intent_kind"],
        },
        "handoff_outcome": handoff_outcome,
        "details": details,
    }

    result = resolve_unified_orchestration_result_kernel(
        Path("."),
        handoff=handoff,
        handoff_packet=None,
        executor_log_path=None,
        resolve_orchestration_result=lambda *_args, **_kwargs: {
            "orchestration_result_state": "execution_succeeded",
            "execution_observed": True,
        },
        resolve_handoff_packet_fulfillment_lifecycle=lambda *_args, **_kwargs: {},
        iso_utc_now=lambda: "2026-04-28T00:00:00Z",
        unified_result_classifications=_UNIFIED_CLASSIFICATIONS,
        unified_result_resolution_paths={"internal_execution", "external_fulfillment"},
    )

    assert handoff_outcome == "admitted_to_execution_substrate"
    assert result["source_intent_ref"]["intent_id"] == intent["intent_id"]
    assert result["result_classification"] == "completed_successfully"
    assert result["evidence_presence"]["proof_linkage_present"] is True
    assert intent["non_authoritative"] is True
    assert result["non_authoritative"] is True


def test_kernel_family_classification_alignment_for_admitted_staged_and_blocked() -> None:
    admitted_intent = _synthesize(
        {
            "work_class": "internal_runtime_maintenance",
            "recommended_venue": "internal_direct_execution",
            "escalation_classification": "none",
        },
        created_at="2026-04-28T00:00:01Z",
    )
    staged_intent = _synthesize(
        {
            "work_class": "external_tool_orchestration",
            "recommended_venue": "internal_direct_execution",
            "escalation_classification": "none",
        },
        created_at="2026-04-28T00:00:02Z",
    )
    blocked_intent = _synthesize(
        {
            "work_class": "operator_required",
            "recommended_venue": "insufficient_context",
            "escalation_classification": "escalate_for_missing_context",
        },
        created_at="2026-04-28T00:00:03Z",
    )

    admitted_outcome, _ = resolve_admission_handoff_outcome_kernel(
        admitted_intent,
        validate_handoff_minimum_fields=validate_handoff_minimum_fields_kernel,
        handoff_outcomes=_HANDOFF_OUTCOMES,
        admit_internal_maintenance_intent=lambda **_kwargs: {"allowed": True},
        now_utc_iso=lambda: "2026-04-28T00:00:00Z",
        root=Path("."),
    )
    staged_outcome, _ = resolve_admission_handoff_outcome_kernel(
        staged_intent,
        validate_handoff_minimum_fields=validate_handoff_minimum_fields_kernel,
        handoff_outcomes=_HANDOFF_OUTCOMES,
        admit_internal_maintenance_intent=lambda **_kwargs: {"allowed": True},
        now_utc_iso=lambda: "2026-04-28T00:00:00Z",
        root=Path("."),
    )
    blocked_outcome, _ = resolve_admission_handoff_outcome_kernel(
        blocked_intent,
        validate_handoff_minimum_fields=validate_handoff_minimum_fields_kernel,
        handoff_outcomes=_HANDOFF_OUTCOMES,
        admit_internal_maintenance_intent=lambda **_kwargs: {"allowed": True},
        now_utc_iso=lambda: "2026-04-28T00:00:00Z",
        root=Path("."),
    )

    assert admitted_intent["executability_classification"] == "executable_now"
    assert admitted_outcome == "admitted_to_execution_substrate"

    assert staged_intent["executability_classification"] == "stageable_external_work_order"
    assert staged_outcome == "staged_only"

    assert blocked_intent["executability_classification"] == "blocked_insufficient_context"
    assert blocked_outcome == "blocked_by_insufficient_context"


def test_kernel_family_fragmented_external_linkage_degrades_to_fragmented_result_history() -> None:
    external_intent = _synthesize(
        {
            "work_class": "implementation",
            "recommended_venue": "codex_implementation",
            "escalation_classification": "none",
        }
    )

    staged_outcome, _ = resolve_admission_handoff_outcome_kernel(
        external_intent,
        validate_handoff_minimum_fields=validate_handoff_minimum_fields_kernel,
        handoff_outcomes=_HANDOFF_OUTCOMES,
        admit_internal_maintenance_intent=lambda **_kwargs: {"allowed": True},
        now_utc_iso=lambda: "2026-04-28T00:00:00Z",
        root=Path("."),
    )
    assert staged_outcome == "blocked_by_operator_requirement"

    packet = {
        "handoff_packet_id": "pkt-22",
        "target_venue": "codex_implementation",
        "operator_escalation_requirement_state": {
            "requires_operator_or_escalation": True,
            "requires_operator_approval": True,
            "escalation_classification": "operator_approval_required",
        },
    }

    result = resolve_unified_orchestration_result_kernel(
        Path("."),
        handoff=None,
        handoff_packet=packet,
        executor_log_path=None,
        resolve_orchestration_result=lambda *_args, **_kwargs: {},
        resolve_handoff_packet_fulfillment_lifecycle=lambda *_args, **_kwargs: {
            "lifecycle_state": "fulfilled_externally",
            "fulfillment_received": True,
            "ingested_external_outcome": True,
        },
        iso_utc_now=lambda: "2026-04-28T00:00:00Z",
        unified_result_classifications=_UNIFIED_CLASSIFICATIONS,
        unified_result_resolution_paths={"internal_execution", "external_fulfillment"},
    )

    assert result["resolution_path"] == "external_fulfillment"
    assert result["evidence_presence"]["fragmented_linkage"] is True
    assert result["result_classification"] == "fragmented_result_history"
    assert result["path_honesty"]["does_not_imply_direct_repo_execution"] is True
