from __future__ import annotations

from typing import Any


def bounded_orchestration_pattern_note() -> dict[str, Any]:
    """Compact developer/operator note for bounded orchestration venue onboarding."""

    return {
        "title": "bounded_orchestration_pattern",
        "what_it_is": (
            "A compact constitutional pattern: delegated judgment -> typed orchestration intent -> bounded handoff -> "
            "result resolution -> retrospective review -> operator-attention recommendation, with explicit non-sovereign boundaries."
        ),
        "reusable_parts": [
            "intent typing + executability classification",
            "append-only intent/handoff ledgers",
            "handoff-to-result linkage fields",
            "bounded retrospective review and operator-attention recommendation",
            "explicit anti-sovereignty payload fields",
        ],
        "onboarding_checklist": [
            "define venue_id with supported_intent_kinds and executability_classes",
            "declare handoff_substrate and append-only result_source",
            "define required linkage fields from intent -> handoff -> result",
            "preserve non_authoritative decision_power=none boundaries",
            "add focused tests for required fields and missing-field detection",
        ],
        "what_not_to_do": [
            "do not add direct external actuation by default",
            "do not create a new sovereign or hidden orchestrator authority",
            "do not bypass admission/result linkage proof surfaces",
            "do not expand venue coverage without scaffold + tests",
        ],
        "current_staged_external_venues": [
            "codex_implementation",
            "deep_research_audit",
        ],
    }
