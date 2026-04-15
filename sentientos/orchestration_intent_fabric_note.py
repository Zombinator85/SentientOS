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
