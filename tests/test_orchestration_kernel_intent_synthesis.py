from sentientos.orchestration_spine.kernel.intent_synthesis import (
    source_judgment_linkage,
    synthesize_orchestration_intent_kernel,
    translate_orchestration_kind,
)


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


def _anti_sovereignty_payload(**_kwargs: object) -> dict[str, object]:
    return {
        "non_authoritative": True,
        "decision_power": "none",
    }


def test_kernel_translate_kind_external_tool_stageable() -> None:
    kind, target, executability = translate_orchestration_kind(
        {
            "recommended_venue": "internal_direct_execution",
            "work_class": "external_tool_orchestration",
            "escalation_classification": "none",
        }
    )

    assert kind == "operator_review_request"
    assert target == "external_tool_placeholder"
    assert executability == "stageable_external_work_order"


def test_kernel_synthesize_orchestration_intent_deterministic_identity() -> None:
    delegated_judgment = {
        "work_class": "internal_runtime_maintenance",
        "recommended_venue": "internal_direct_execution",
        "next_move_posture": "expand",
        "consolidation_expansion_posture": "consolidate",
        "escalation_classification": "none",
        "basis": {
            "signal_reasons": ["keep-runtime-healthy"],
            "slice_health_status": "healthy",
            "slice_stability_classification": "stable",
            "slice_review_classification": "clean_recent_orchestration",
        },
    }

    first = synthesize_orchestration_intent_kernel(
        delegated_judgment,
        created_at="2026-04-12T00:00:00Z",
        iso_utc_now=lambda: "2026-04-12T00:00:00Z",
        anti_sovereignty_payload=_anti_sovereignty_payload,
        intent_kinds=_INTENT_KINDS,
        authority_postures=_AUTHORITY_POSTURES,
        execution_targets=_EXECUTION_TARGETS,
        executability_classes=_EXECUTABILITY,
        admission_states=_ADMISSION_STATES,
    )
    second = synthesize_orchestration_intent_kernel(
        delegated_judgment,
        created_at="2026-04-12T00:00:00Z",
        iso_utc_now=lambda: "2026-04-12T00:00:00Z",
        anti_sovereignty_payload=_anti_sovereignty_payload,
        intent_kinds=_INTENT_KINDS,
        authority_postures=_AUTHORITY_POSTURES,
        execution_targets=_EXECUTION_TARGETS,
        executability_classes=_EXECUTABILITY,
        admission_states=_ADMISSION_STATES,
    )

    assert first["intent_id"] == second["intent_id"]
    assert first["intent_kind"] == "internal_maintenance_execution"
    assert first["executability_classification"] == "executable_now"


def test_kernel_source_linkage_preserves_canonical_defaults() -> None:
    linkage = source_judgment_linkage({})

    assert linkage["work_class"] == "operator_required"
    assert linkage["recommended_venue"] == "insufficient_context"
    assert linkage["escalation_classification"] == "escalate_for_missing_context"
