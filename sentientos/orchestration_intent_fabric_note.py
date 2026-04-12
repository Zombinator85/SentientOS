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
            "it stages executable internal intents for admission; all execution remains downstream",
        ],
        "venue_to_executability": {
            "internal_direct_execution": "executable_now via task admission staging",
            "codex_implementation": "stageable_external_work_order",
            "deep_research_audit": "stageable_external_work_order",
            "operator_decision_required": "blocked_operator_required",
            "insufficient_context": "blocked_insufficient_context",
        },
        "proof_visible_artifact": "glow/orchestration/orchestration_intents.jsonl",
        "not_in_scope_yet": [
            "direct Codex invocation",
            "direct Deep Research invocation",
            "direct external adapter actuation",
            "direct browser/mouse/keyboard tool control",
        ],
    }
