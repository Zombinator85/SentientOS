from __future__ import annotations

"""Autonomous skill registry for SentientOS agents.

Skills are lightweight records extracted from successful autonomous goals. Each
skill captures the intent that was executed, any contextual hints that helped,
and a short reflection. The registry powers retrieval of prior solutions so
that future goals can reuse proven strategies instead of starting from a blank
slate.
"""

import datetime
import json
from typing import Any, Dict, List

import memory_manager as mm

SKILL_LOG = mm.MEMORY_DIR / "skills.jsonl"
SKILL_LOG.parent.mkdir(parents=True, exist_ok=True)


def _load() -> List[Dict[str, Any]]:
    if not SKILL_LOG.exists():
        return []
    entries: List[Dict[str, Any]] = []
    for line in SKILL_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            continue
    return entries


def register_skill(goal: dict, result: dict, *, curator: str = "autonomy") -> dict | None:
    """Persist a reusable skill extracted from a successful goal."""

    if result.get("status") != "finished":
        return None

    intent = goal.get("intent", {}) or {}
    description = goal.get("text") or intent.get("description") or ""
    tags = set(goal.get("tags", []) or [])
    intent_tag = intent.get("type")
    if intent_tag:
        tags.add(intent_tag)

    skill = {
        "id": mm._hash(json.dumps(intent, sort_keys=True) + result.get("log_id", "")),
        "intent": intent,
        "description": description,
        "reflection": result.get("reflection", ""),
        "timestamp": result.get("timestamp")
        or goal.get("updated_at")
        or datetime.datetime.utcnow().isoformat(),
        "curator": curator,
        "tags": sorted(tags),
    }

    with SKILL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(skill, ensure_ascii=False) + "\n")

    mm.append_memory(
        json.dumps({"skill": skill}, ensure_ascii=False),
        tags=["skill", intent.get("type", ""), curator],
        source="skill_registry",
    )
    return skill


def list_skills(limit: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent skills."""

    entries = _load()
    return entries[-limit:]


def _score(text: str, query: str) -> float:
    if not text or not query:
        return 0.0
    text_words = set(text.lower().split())
    query_words = set(query.lower().split())
    overlap = len(text_words & query_words)
    if not overlap:
        return 0.0
    return overlap / max(len(query_words), 1)


def suggest_skills(query: str, *, limit: int = 3) -> List[Dict[str, Any]]:
    """Return skill suggestions relevant to ``query``."""

    entries = _load()
    scored: List[tuple[float, Dict[str, Any]]] = []
    for skill in entries:
        description = skill.get("description", "")
        reflection = skill.get("reflection", "")
        score = max(_score(description, query), _score(reflection, query))
        if score > 0:
            scored.append((score, skill))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [skill for _, skill in scored[:limit]]


__all__ = ["register_skill", "list_skills", "suggest_skills"]

