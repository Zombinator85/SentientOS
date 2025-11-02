"""Bridges external or archival knowledge sources for the autonomous agent."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import memory_manager as mm


def consult(question: str, *, intent: Dict[str, Any] | None = None, k: int = 3) -> Dict[str, Any]:
    """Retrieve contextual guidance for a pending decision."""

    context: List[str] = mm.get_context(question, k=k)
    if not context and intent:
        context = mm.get_context(json.dumps(intent, ensure_ascii=False), k=k)
    recommendation = "Consider escalation; no precedent found." if not context else "Use retrieved precedent snippets to guide next step."
    payload = {
        "question": question,
        "intent": intent or {},
        "context": context,
        "recommendation": recommendation,
    }
    mm.append_memory(
        json.dumps({"oracle_consult": payload}, ensure_ascii=False),
        tags=["oracle", intent.get("type", "") if intent else ""],
        source="oracle_bridge",
    )
    return payload


__all__ = ["consult"]
