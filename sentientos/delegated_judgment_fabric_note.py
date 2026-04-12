from __future__ import annotations

from typing import Any


def delegated_judgment_fabric_note() -> dict[str, Any]:
    """Bounded technical note for the delegated judgment fabric layer."""

    return {
        "layer": "delegated_judgment_fabric",
        "what_it_does": [
            "synthesizes bounded delegated-judgment recommendations from existing constitutional evidence",
            "classifies work class, execution venue, next-move posture, and escalation class",
            "emits consolidation-vs-expansion posture and substitution readiness verdicts",
        ],
        "evidence_inputs": [
            "glow/contracts/contract_status.json rollup domains",
            "scoped slice health/stability/retrospective diagnostics",
            "logs/task_admission.jsonl denial patterns",
            "logs/task_executor.jsonl terminal failure patterns",
            "federation handshake log presence as bounded external adapter signal",
        ],
        "what_it_recommends": [
            "work_class",
            "recommended_venue",
            "next_move_posture",
            "consolidation_expansion_posture",
            "escalation_classification",
            "orchestration_substitution_readiness",
        ],
        "what_it_explicitly_does_not_do": [
            "execute tools directly",
            "override kernel/governor or task admission",
            "change release readiness gates",
            "choose sovereign goals",
            "replace final operator authority",
        ],
        "non_sovereign_contract": {
            "diagnostic_only": True,
            "non_authoritative": True,
            "decision_power": "none",
            "recommendation_only": True,
            "does_not_execute_tools": True,
            "does_not_override_existing_admission": True,
        },
    }
