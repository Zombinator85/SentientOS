"""Autonomous goal discovery based on recurring memory fragments."""

from __future__ import annotations

import json
from collections import Counter
from typing import Dict, Iterable, List

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


__all__ = ["discover", "maybe_schedule_goals"]
