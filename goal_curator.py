"""Autonomous goal discovery based on recurring memory fragments."""

from __future__ import annotations

import json
from collections import Counter
from typing import Dict, Iterable, List, Mapping

import memory_manager as mm

_SIGNAL_TAGS = {"habit", "recurring", "summary_request", "user_request", "goal_hint"}
_MIN_REPETITIONS = 3


def _normalise(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned.lower()


def _candidate_fragments(limit: int = 200) -> Iterable[dict]:
    for entry in mm.iter_fragments(limit=limit):
        tags = set(entry.get("tags", []) or [])
        if tags & _SIGNAL_TAGS:
            yield entry
        elif isinstance(entry.get("meta"), dict) and entry["meta"].get("suggest_goal"):
            yield entry


def discover(limit: int = 200, *, min_repetitions: int = _MIN_REPETITIONS) -> List[Dict[str, str]]:
    """Return potential autonomous goals inferred from memory."""

    counts: Counter[str] = Counter()
    exemplars: Dict[str, dict] = {}
    for entry in _candidate_fragments(limit=limit):
        text = entry.get("meta", {}).get("goal_text") or entry.get("text", "")
        if not text:
            continue
        key = _normalise(text)
        counts[key] += 1
        exemplars.setdefault(key, entry)

    suggestions: List[Dict[str, str]] = []
    for key, count in counts.items():
        if count < min_repetitions:
            continue
        exemplar = exemplars[key]
        suggestions.append(
            {
                "text": exemplar.get("meta", {}).get("goal_text") or exemplar.get("text", ""),
                "tags": exemplar.get("tags", []),
                "count": count,
            }
        )
    return suggestions


def maybe_schedule_goals(limit: int = 200, *, min_repetitions: int = _MIN_REPETITIONS, author: str = "goal_curator") -> List[dict]:
    """Create background goals when recurring requests are detected."""

    open_goals = {_normalise(g.get("text", "")) for g in mm.get_goals(open_only=False)}
    created: List[dict] = []
    for suggestion in discover(limit=limit, min_repetitions=min_repetitions):
        text = suggestion["text"]
        if _normalise(text) in open_goals:
            continue
        goal = mm.add_goal(text, intent={"type": "background"}, user=author, priority=2)
        created.append(goal)
        mm.append_memory(
            json.dumps({"auto_goal": {"text": text, "count": suggestion["count"]}}, ensure_ascii=False),
            tags=["goal", "autonomous", author],
            source="goal_curator",
        )
    return created


def spawn_curiosity_goal(
    summary: Mapping[str, object],
    *,
    novelty: float,
    author: str = "perception_reasoner",
) -> dict | None:
    """Create a curiosity-driven goal derived from a perception summary."""

    summary_text = str(summary.get("summary") or "").strip()
    if not summary_text:
        return None
    novel_objects = summary.get("novel_objects") or summary.get("novel") or []
    if isinstance(novel_objects, str):
        novel_objects = [novel_objects]
    if novel_objects:
        focus = ", ".join(str(obj) for obj in novel_objects)
        goal_text = f"Investigate novel perception: {focus}"
    else:
        goal_text = f"Investigate perception: {summary_text[:160]}"
    existing = {_normalise(goal.get("text", "")) for goal in mm.get_goals(open_only=False)}
    if _normalise(goal_text) in existing:
        return None
    intent = {
        "type": "curiosity",
        "novelty": float(novelty),
        "observation": {
            "summary": summary_text,
            "novel_objects": list(novel_objects),
        },
    }
    goal = mm.add_goal(goal_text, intent=intent, user=author, priority=2)
    mm.append_memory(
        json.dumps({"curiosity_task": {"goal": goal_text, "novelty": novelty}}, ensure_ascii=False),
        tags=["goal", "curiosity", author],
        source="perception_reasoner",
    )
    return goal


__all__ = ["discover", "maybe_schedule_goals", "spawn_curiosity_goal"]
