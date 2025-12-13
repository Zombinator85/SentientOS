"""Reflexion-style self critique for autonomous goals.

The module generates short natural language insights describing why a goal
succeeded or failed and persists them as dedicated memory fragments.  The
implementation favours deterministic heuristics so the loop can operate without
external LLM access while still capturing meaningful lessons for future cycles.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, Mapping

from capability_ledger import CapabilityAxis, CapabilityLedgerEntry, append as append_capability_entry
import memory_manager as mm


def _classify_status(result: Dict[str, Any]) -> str:
    status = str(result.get("status", "")).lower()
    if status in {"finished", "success", "succeeded"}:
        return "success"
    if status in {"blocked", "rejected"}:
        return "blocked"
    return "failed"


def generate_insight(goal: Dict[str, Any], result: Dict[str, Any], consensus: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Produce a structured self-critique payload."""

    status = _classify_status(result)
    text = goal.get("text", "")
    lesson: str
    adjustment: str

    if status == "success":
        lesson = f"Completed goal '{text}' successfully."
        adjustment = "Repeat approach and catalogue skill."
    elif status == "blocked":
        reason = "; ".join(v.get("reason", "") for v in (consensus or {}).get("votes", []) if not v.get("approve"))
        lesson = f"Council blocked goal '{text}'. {reason or 'Requires human review.'}"
        adjustment = "Escalate for manual approval and refine intent."
    else:
        critique = result.get("critique") or result.get("error") or "No critique provided."
        lesson = f"Goal '{text}' failed. {critique}"
        adjustment = "Break goal into smaller steps and consult skills."

    insight = {
        "goal": goal.get("id"),
        "status": status,
        "lesson": lesson,
        "adjustment": adjustment,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }
    return insight


def record_insight(goal: Dict[str, Any], result: Dict[str, Any], consensus: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Persist a Reflexion style critique to long-term memory."""

    insight = generate_insight(goal, result, consensus)
    context = mm.latest_observation()
    if context:
        insight["observation_context"] = {
            "summary": context.get("summary"),
            "novelty": context.get("novelty"),
            "timestamp": context.get("timestamp"),
            "novel_objects": context.get("novel_objects", []),
        }
    mm.append_memory(
        json.dumps({"reflexion": insight}, ensure_ascii=False),
        tags=["reflection", "reflexion", goal.get("id", "")],
        source="reflexion_loop",
    )
    append_capability_entry(
        CapabilityLedgerEntry(
            axis=CapabilityAxis.INTERNAL_COHERENCE,
            measurement_method="reflexion_loop.record_insight",
            delta=f"goal={goal.get('id', '') or 'unknown'} status={insight['status']}",
            notes="Epistemic reflection entry only; no behavioural effect.",
            evidence={"lesson": insight["lesson"], "adjustment": insight["adjustment"]},
            source={"module": "reflection", "hook": "reflexion_loop.record_insight"},
        )
    )
    return insight


def narrate_observation(summary: Mapping[str, Any], novelty: float) -> Dict[str, Any]:
    """Record a short narrative about a perception summary."""

    narrative = {
        "summary": summary.get("summary"),
        "novelty": float(novelty),
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "objects": list(summary.get("objects", [])),
        "novel_objects": list(summary.get("novel_objects", [])),
        "transcripts": list(summary.get("transcripts", [])),
    }
    mm.append_memory(
        json.dumps({"perception_reflection": narrative}, ensure_ascii=False),
        tags=["reflection", "perception"],
        source="perception_reasoner",
    )
    return narrative


def reflect_curiosity_result(goal: Mapping[str, Any], insight: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a structured self-reflection about a curiosity investigation."""

    observation = (goal.get("intent") or {}).get("observation", {})
    observation_id = insight.get("observation_id") or observation.get("id")
    summary = insight.get("insight_summary") or goal.get("text")
    lesson = (
        f"Curiosity goal '{goal.get('text')}' explored observation {observation_id or 'unknown'}"
    )
    if insight.get("insight"):
        lesson += f" and learned: {insight['insight']}"
    adjustment = "Apply the finding to future perception reasoning cycles."
    reflection = {
        "goal_id": goal.get("id"),
        "observation_id": observation_id,
        "insight_summary": summary,
        "lesson": lesson,
        "adjustment": adjustment,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }
    if observation_id:
        reflection["observation_ref"] = {
            "id": observation_id,
            "summary": observation.get("summary"),
            "novelty": observation.get("novelty"),
        }
    return reflection


__all__ = [
    "generate_insight",
    "record_insight",
    "narrate_observation",
    "reflect_curiosity_result",
]
