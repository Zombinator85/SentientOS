"""Peer review records for council deliberations."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import memory_manager as mm


def collect_feedback(consensus_record: Dict[str, Any]) -> Dict[str, Any]:
    """Gather reflections and archive a peer review packet."""

    intent = consensus_record.get("intent", {})
    plugin = intent.get("type") or ""
    reflections: List[Dict[str, Any]] = mm.recent_reflections(limit=5, plugin=plugin)
    notes: List[str] = []
    for reflection in reflections:
        reason = reflection.get("reason") or reflection.get("next") or ""
        if reason:
            notes.append(reason)
    packet = {
        "intent": intent,
        "plugin": plugin,
        "notes": notes,
        "votes": consensus_record.get("votes", []),
    }
    mm.append_memory(
        json.dumps({"peer_review": packet}, ensure_ascii=False),
        tags=["peer_review", plugin],
        source="council_peer_review",
    )
    return packet


__all__ = ["collect_feedback"]
