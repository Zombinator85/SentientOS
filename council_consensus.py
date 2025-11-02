from __future__ import annotations

"""Lightweight internal council voting for autonomous intents."""

import json
from typing import Any, Dict, List

import memory_manager as mm

FORBIDDEN_SHELL_PATTERNS = [
    "rm -rf",
    ":(){:|:&};:",
    "> /dev/sda",
    "shutdown",
]


def _safety_vote(intent: Dict[str, Any]) -> Dict[str, Any]:
    if intent.get("type") == "shell":
        cmd = intent.get("cmd", "")
        for pattern in FORBIDDEN_SHELL_PATTERNS:
            if pattern in cmd:
                return {"name": "safety", "approve": False, "reason": f"blocked pattern: {pattern}"}
        if "sudo" in cmd:
            return {"name": "safety", "approve": False, "reason": "sudo requires manual blessing"}
    if intent.get("type") == "http" and intent.get("method", "GET") not in {"GET", "POST"}:
        return {"name": "safety", "approve": False, "reason": "unsafe http method"}
    return {"name": "safety", "approve": True, "reason": "passes static checks"}


def _memory_vote(intent: Dict[str, Any], explanation: str | None) -> Dict[str, Any]:
    query = explanation or json.dumps(intent, ensure_ascii=False)
    context = mm.get_context(query, k=2)
    approve = bool(context)
    reason = "context available" if approve else "no supporting memory"
    return {"name": "memory", "approve": approve, "reason": reason, "context": context}


def _reflection_vote(intent: Dict[str, Any]) -> Dict[str, Any]:
    reflections = mm.recent_reflections(limit=3, plugin=intent.get("type"))
    if any(ref.get("result") is None for ref in reflections):
        return {
            "name": "reflection",
            "approve": False,
            "reason": "recent failures require review",
            "reflections": reflections,
        }
    return {
        "name": "reflection",
        "approve": True,
        "reason": "no recent failures",
        "reflections": reflections,
    }


VOTERS = [_safety_vote, _memory_vote, _reflection_vote]


def deliberate(intent: Dict[str, Any], explanation: str | None = None) -> Dict[str, Any]:
    """Run council voting on ``intent`` and return the verdict."""

    tallies: List[Dict[str, Any]] = []
    for voter in VOTERS:
        try:
            if voter is _memory_vote:
                tallies.append(voter(intent, explanation))
            else:
                tallies.append(voter(intent))
        except Exception as exc:
            tallies.append({"name": getattr(voter, "__name__", "unknown"), "approve": False, "reason": str(exc)})

    approvals = sum(1 for vote in tallies if vote.get("approve"))
    required = (len(tallies) // 2) + 1
    approved = approvals >= required

    record = {
        "intent": intent,
        "explanation": explanation,
        "votes": tallies,
        "approved": approved,
        "required": required,
    }

    mm.append_memory(
        json.dumps({"consensus": record}, ensure_ascii=False),
        tags=["consensus", intent.get("type", "")],
        source="council_consensus",
    )
    return record


__all__ = ["deliberate"]

