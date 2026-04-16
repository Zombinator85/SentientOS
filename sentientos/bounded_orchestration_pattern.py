from __future__ import annotations

from typing import Any, Mapping


_REQUIRED_LAYER = "required_for_new_venue"
_OPTIONAL_LAYER = "optional_or_advanced"
_CURRENT_INTERNAL_SPECIFIC_LAYER = "current_internal_task_admission_specific"

_REQUIRED_VENUE_FIELDS = (
    "venue_id",
    "supported_intent_kinds",
    "executability_classes",
    "handoff_substrate",
    "result_source",
    "required_linkage_fields",
    "review_attention_capabilities",
    "anti_sovereignty_guarantees",
)


def bounded_orchestration_layers() -> list[dict[str, Any]]:
    """Return the compact reusable layer model for bounded orchestration venues."""

    return [
        {
            "layer": "delegated_judgment_input",
            "classification": _REQUIRED_LAYER,
            "implementation_anchor": "sentientos.delegated_judgment_fabric.synthesize_delegated_judgment",
            "why": "every venue must inherit recommendation + escalation provenance before intent typing",
        },
        {
            "layer": "orchestration_intent_typing",
            "classification": _REQUIRED_LAYER,
            "implementation_anchor": "sentientos.orchestration_intent_fabric.synthesize_orchestration_intent",
            "why": "typed intent/work-order artifacts are the constitutional handoff unit",
        },
        {
            "layer": "executability_classification",
            "classification": _REQUIRED_LAYER,
            "implementation_anchor": "sentientos.orchestration_intent_fabric._translate_kind",
            "why": "venue rollout requires explicit executable_now vs staged/blocked semantics",
        },
        {
            "layer": "handoff_substrate_target",
            "classification": _REQUIRED_LAYER,
            "implementation_anchor": "sentientos.orchestration_intent_fabric.admit_orchestration_intent",
            "why": "venue must declare where admitted work is staged or executed",
        },
        {
            "layer": "handoff_outcome_semantics",
            "classification": _REQUIRED_LAYER,
            "implementation_anchor": "sentientos.orchestration_intent_fabric.admit_orchestration_intent",
            "why": "bounded outcomes keep admission, staged-only, and blocked states machine-readable",
        },
        {
            "layer": "downstream_result_resolution",
            "classification": _REQUIRED_LAYER,
            "implementation_anchor": "sentientos.orchestration_intent_fabric.resolve_orchestration_result",
            "why": "handoff closure requires linking admitted execution records to result evidence",
        },
        {
            "layer": "retrospective_orchestration_review",
            "classification": _OPTIONAL_LAYER,
            "implementation_anchor": "sentientos.orchestration_intent_fabric.derive_orchestration_outcome_review",
            "why": "recommended for diagnostics; not required for initial venue handoff viability",
        },
        {
            "layer": "operator_attention_recommendation",
            "classification": _OPTIONAL_LAYER,
            "implementation_anchor": "sentientos.orchestration_intent_fabric.derive_orchestration_attention_recommendation",
            "why": "bounded attention guidance is valuable but should not gate initial venue onboarding",
        },
        {
            "layer": "task_admission_executor_noop_task_materialization",
            "classification": _CURRENT_INTERNAL_SPECIFIC_LAYER,
            "implementation_anchor": "sentientos.orchestration_intent_fabric._build_internal_maintenance_task",
            "why": "specific to the currently operational internal task-admission substrate",
        },
        {
            "layer": "task_executor_jsonl_task_result_resolution",
            "classification": _CURRENT_INTERNAL_SPECIFIC_LAYER,
            "implementation_anchor": "logs/task_executor.jsonl task_result linkage",
            "why": "current venue-specific result source and linkage surface",
        },
        {
            "layer": "explicit_anti_sovereignty_boundaries",
            "classification": _REQUIRED_LAYER,
            "implementation_anchor": "sentientos.orchestration_intent_fabric._anti_sovereignty_payload",
            "why": "venue onboarding must preserve non-authoritative constitutional posture",
        },
    ]


def bounded_orchestration_venue_scaffold() -> dict[str, Any]:
    """Return the reusable machine-readable scaffold for bounded venue onboarding."""

    return {
        "schema_version": "bounded_orchestration_venue_scaffold.v1",
        "pattern_scope": "bounded_orchestration_venue_expansion",
        "current_reference_venue": {
            "venue_id": "internal_task_admission",
            "supported_intent_kinds": ["internal_maintenance_execution"],
            "executability_classes": ["executable_now", "blocked_operator_required", "blocked_insufficient_context"],
            "handoff_substrate": "task_admission_executor",
            "result_source": {
                "surface": "logs/task_executor.jsonl",
                "event": "task_result",
                "status_values": ["completed", "failed"],
            },
            "required_linkage_fields": {
                "intent_to_handoff": ["intent_id"],
                "handoff_to_admission": ["details.task_admission.task_id"],
                "admission_to_result": ["task_id"],
            },
            "review_attention_capabilities": {
                "outcome_review_enabled": True,
                "attention_recommendation_enabled": True,
            },
            "anti_sovereignty_guarantees": {
                "non_authoritative": True,
                "decision_power": "none",
                "does_not_invoke_external_tools": True,
                "does_not_change_admission_or_execution": True,
                "does_not_replace_operator_authority": True,
            },
        },
        "layer_model": bounded_orchestration_layers(),
    }


def validate_bounded_orchestration_venue(candidate: Mapping[str, Any]) -> list[str]:
    """Return missing required venue fields for bounded orchestration onboarding."""

    missing: list[str] = []
    for field in _REQUIRED_VENUE_FIELDS:
        if field not in candidate:
            missing.append(field)

    linkage = candidate.get("required_linkage_fields")
    if isinstance(linkage, Mapping):
        for required_link in ("intent_to_handoff", "handoff_to_admission", "admission_to_result"):
            if required_link not in linkage:
                missing.append(f"required_linkage_fields.{required_link}")

    guarantees = candidate.get("anti_sovereignty_guarantees")
    if isinstance(guarantees, Mapping):
        if guarantees.get("non_authoritative") is not True:
            missing.append("anti_sovereignty_guarantees.non_authoritative")
        if str(guarantees.get("decision_power") or "") != "none":
            missing.append("anti_sovereignty_guarantees.decision_power")

    return missing


def codex_implementation_bounded_venue() -> dict[str, Any]:
    """Return the onboarded bounded venue scaffold payload for codex staged work orders."""

    return {
        "venue_id": "codex_implementation",
        "supported_intent_kinds": ["codex_work_order"],
        "executability_classes": [
            "stageable_external_work_order",
            "blocked_operator_required",
            "blocked_insufficient_context",
        ],
        "handoff_substrate": "glow/orchestration/codex_work_orders.jsonl",
        "result_source": {
            "surface": "glow/orchestration/codex_work_orders.jsonl",
            "event": "codex_staged_work_order",
            "status_values": [
                "staged",
                "blocked_operator_required",
                "blocked_insufficient_context",
                "cancelled",
            ],
        },
        "required_linkage_fields": {
            "intent_to_handoff": ["intent_id", "source_intent_id"],
            "handoff_to_admission": ["details.codex_work_order_ref.work_order_id", "work_order_id"],
            "admission_to_result": ["work_order_id", "source_intent_id"],
        },
        "review_attention_capabilities": {
            "outcome_review_enabled": True,
            "attention_recommendation_enabled": True,
            "staged_lifecycle_visibility_enabled": True,
        },
        "anti_sovereignty_guarantees": {
            "non_authoritative": True,
            "decision_power": "none",
            "staged_only": True,
            "does_not_invoke_codex_directly": True,
            "requires_external_tool_or_operator_trigger": True,
            "does_not_replace_operator_authority": True,
        },
    }


def deep_research_audit_bounded_venue() -> dict[str, Any]:
    """Return the onboarded bounded venue scaffold payload for deep-research staged work orders."""

    return {
        "venue_id": "deep_research_audit",
        "supported_intent_kinds": ["deep_research_work_order"],
        "executability_classes": [
            "stageable_external_work_order",
            "blocked_operator_required",
            "blocked_insufficient_context",
        ],
        "handoff_substrate": "glow/orchestration/deep_research_work_orders.jsonl",
        "result_source": {
            "surface": "glow/orchestration/deep_research_work_orders.jsonl",
            "event": "deep_research_staged_work_order",
            "status_values": [
                "staged",
                "blocked_operator_required",
                "blocked_insufficient_context",
                "cancelled",
            ],
        },
        "required_linkage_fields": {
            "intent_to_handoff": ["intent_id", "source_intent_id"],
            "handoff_to_admission": ["details.deep_research_work_order_ref.work_order_id", "work_order_id"],
            "admission_to_result": ["work_order_id", "source_intent_id"],
        },
        "review_attention_capabilities": {
            "outcome_review_enabled": True,
            "attention_recommendation_enabled": True,
            "staged_lifecycle_visibility_enabled": True,
        },
        "anti_sovereignty_guarantees": {
            "non_authoritative": True,
            "decision_power": "none",
            "staged_only": True,
            "does_not_invoke_deep_research_directly": True,
            "requires_external_tool_or_operator_trigger": True,
            "does_not_replace_operator_authority": True,
        },
    }


def next_bounded_venue_candidate_assessment() -> dict[str, Any]:
    """Provide the grounded next venue candidate assessment without onboarding it."""

    return {
        "recommended_next_venue": "deep_research_audit",
        "why_best_next": (
            "it now has delegated-judgment recommendation coverage and typed orchestration intent/work-order "
            "classification, so expansion can focus on bounded handoff/result linkage without changing constitutional authority posture"
        ),
        "already_present_prerequisites": [
            "delegated_judgment_fabric emits recommended_venue=deep_research_audit",
            "orchestration_intent_fabric emits intent_kind=deep_research_work_order",
            "executability_classification=stageable_external_work_order keeps it non-executable in current pass",
            "append-only intent and handoff ledgers now capture staged deep-research work-order artifacts",
        ],
        "largest_missing_prerequisite": (
            "a bounded, append-only external handoff admission/result substrate with stable linkage keys equivalent to "
            "the current task_admission.task_id -> task_executor.task_result closure"
        ),
        "relative_difficulty_vs_current_internal_venue": "harder_than_internal_task_admission",
        "difficulty_rationale": (
            "external venue rollout adds transport, admission parity, and downstream proof-linkage constraints absent in the current internal substrate"
        ),
        "not_implemented_in_this_pass": False,
    }
