from __future__ import annotations

from typing import Any


def orchestration_intent_fabric_note() -> dict[str, Any]:
    """Short technical note for constitutional judgment-to-execution handoff."""

    return {
        "layer": "orchestration_intent_fabric",
        "what_it_is": [
            "a bounded translation bridge from delegated judgment recommendations to typed orchestration intents",
            "a governed handoff substrate that stages execution intent without claiming sovereign execution authority",
        ],
        "how_it_differs_from_delegated_judgment": [
            "delegated judgment classifies and recommends; orchestration handoff emits typed intent/work-order artifacts",
            "delegated judgment stays recommendation_only; orchestration handoff is recommendation_only=false but still non_authoritative",
        ],
        "how_it_differs_from_execution": [
            "it does not execute external tools, browser, keyboard, or mouse actions",
            "it does not bypass task admission, kernel, or governor decisions",
            "it can hand internal_maintenance_execution intents into task_admission for bounded admission only",
            "handoff admission is not execution completion; execution remains downstream",
            "closed-loop orchestration result now resolves downstream task_executor task_result evidence for admitted internal handoffs",
        ],
        "internal_handoff_now_operational": {
            "intent_kind": "internal_maintenance_execution",
            "execution_target": "task_admission_executor",
            "admission_surface": "task_admission.admit",
            "handoff_outcomes": [
                "admitted_to_execution_substrate",
                "blocked_by_admission",
                "blocked_by_operator_requirement",
                "blocked_by_insufficient_context",
                "execution_target_unavailable",
                "staged_only",
            ],
        },
        "venue_to_executability": {
            "internal_direct_execution": "executable_now via task admission staging",
            "codex_implementation": "stageable_external_work_order",
            "deep_research_audit": "stageable_external_work_order",
            "operator_decision_required": "blocked_operator_required",
            "insufficient_context": "blocked_insufficient_context",
        },
        "proof_visible_artifact": "glow/orchestration/orchestration_intents.jsonl",
        "handoff_artifact": "glow/orchestration/orchestration_handoffs.jsonl",
        "codex_staged_work_order_artifact": "glow/orchestration/codex_work_orders.jsonl",
        "deep_research_staged_work_order_artifact": "glow/orchestration/deep_research_work_orders.jsonl",
        "codex_staged_venue_onboarding": {
            "status": "first_class_bounded_staged_venue",
            "venue": "codex_implementation",
            "constitutional_fields": [
                "work_order_id",
                "source_intent_id",
                "source_judgment_linkage",
                "operator_requirements",
                "executability_classification",
                "staged_only",
                "does_not_invoke_codex_directly",
                "requires_external_tool_or_operator_trigger",
                "non_authoritative",
                "decision_power=none",
            ],
            "lifecycle_states": [
                "staged_cleanly",
                "blocked_operator_required",
                "blocked_insufficient_context",
                "fragmented_unlinked_work_order_state",
            ],
            "still_missing_before_any_direct_codex_delegation": [
                "an approved external transport/trigger path",
                "admission parity for external execution",
                "result attestation proving fulfillment beyond staged state",
            ],
            "still_out_of_scope": [
                "direct Codex invocation from this repository",
                "browser or desktop automation",
                "automatic completion claims without proof-visible external evidence",
            ],
        },
        "deep_research_staged_venue_onboarding": {
            "status": "first_class_bounded_staged_venue",
            "venue": "deep_research_audit",
            "constitutional_fields": [
                "work_order_id",
                "source_intent_id",
                "source_judgment_linkage",
                "operator_requirements",
                "executability_classification",
                "staged_only",
                "does_not_invoke_deep_research_directly",
                "requires_external_tool_or_operator_trigger",
                "non_authoritative",
                "decision_power=none",
            ],
            "lifecycle_states": [
                "staged_cleanly",
                "blocked_operator_required",
                "blocked_insufficient_context",
                "fragmented_unlinked_work_order_state",
            ],
            "still_missing_before_any_direct_deep_research_delegation": [
                "an approved external transport/trigger path",
                "admission parity for external execution",
                "result attestation proving fulfillment beyond staged state",
            ],
            "comparison_to_codex_staged_venue": [
                "both venues are stageable_external_work_order only in this pass",
                "both venues carry stable work_order_id + source intent/judgment linkage",
                "both venues expose append-only proof artifacts and staged lifecycle visibility",
                "both venues remain non-sovereign and non-executable here",
            ],
            "still_out_of_scope": [
                "direct Deep Research invocation from this repository",
                "browser or desktop automation",
                "automatic completion claims without proof-visible external evidence",
            ],
        },
        "result_resolution": {
            "path": "internal_maintenance_execution -> task_admission_executor -> logs/task_executor.jsonl task_result",
            "result_states": [
                "handoff_admitted_pending_result",
                "execution_still_pending",
                "execution_succeeded",
                "execution_failed",
                "execution_result_missing",
                "handoff_not_admitted",
            ],
            "meaning": "handoff admission records substrate entry; orchestration result closure requires downstream task_result evidence.",
        },
        "outcome_review": {
            "meaning": "bounded retrospective classification over recent internal orchestration outcomes.",
            "reads_existing_artifacts_only": [
                "glow/orchestration/orchestration_intents.jsonl",
                "glow/orchestration/orchestration_handoffs.jsonl",
                "logs/task_executor.jsonl task_result linkage",
            ],
            "classifications": [
                "clean_recent_orchestration",
                "handoff_block_heavy",
                "execution_failure_heavy",
                "pending_stall_pattern",
                "mixed_orchestration_stress",
                "insufficient_history",
            ],
            "explicitly_not": [
                "a new admission authority",
                "a governor/kernel override",
                "direct external actuation",
                "a new execution venue",
            ],
        },
        "venue_mix_review": {
            "meaning": "bounded retrospective check of recent venue-selection mix (internal execution vs staged Codex vs staged Deep Research vs operator-heavy escalation states).",
            "reads_existing_artifacts_only": [
                "glow/orchestration/orchestration_intents.jsonl",
                "glow/orchestration/orchestration_handoffs.jsonl",
                "glow/orchestration/codex_work_orders.jsonl",
                "glow/orchestration/deep_research_work_orders.jsonl",
                "orchestration_result_resolution linkage surfaces",
            ],
            "classifications": [
                "balanced_recent_venue_mix",
                "internal_execution_heavy",
                "codex_heavy",
                "deep_research_heavy",
                "operator_escalation_heavy",
                "mixed_venue_stress",
                "insufficient_history",
            ],
            "explicitly_not": [
                "admission authority",
                "execution authority",
                "a new venue",
                "direct external actuation",
            ],
        },
        "operator_attention_recommendation": {
            "meaning": "bounded diagnostic recommendation about what operator attention internal orchestration behavior likely needs.",
            "derived_from": [
                "orchestration_outcome_review.review_classification",
                "orchestration_outcome_review.condition_flags",
                "orchestration_outcome_review.recent_outcome_counts",
            ],
            "values": [
                "none",
                "observe",
                "inspect_handoff_blocks",
                "inspect_execution_failures",
                "inspect_pending_stall",
                "review_mixed_orchestration_stress",
                "insufficient_context",
            ],
            "explicitly_not": [
                "workflow automation authority",
                "admission policy mutation",
                "execution control",
                "a sovereign decision surface",
            ],
        },
        "venues_still_staged_only": [
            "codex_implementation",
            "deep_research_audit",
            "operator_decision_required",
        ],
        "not_in_scope_yet": [
            "direct Codex invocation",
            "direct Deep Research invocation",
            "direct external adapter actuation",
            "direct browser/mouse/keyboard tool control",
            "external tool delegation with real execution authority",
        ],
    }
