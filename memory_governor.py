"""Coordinated access to long-term memory for SentientOS dream cycles."""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

import memory_manager as mm

from emotion_utils import combine_emotions, dominant_emotion


_QUERY_OPERATOR = re.compile(r"^(importance)\s*([<>]=?)\s*([0-9.]+)$", re.IGNORECASE)
_DEFAULT_THRESHOLD = float(os.getenv("DREAM_RECALL_THRESHOLD", "0.7"))
_VALID_CATEGORIES = {
    "event",
    "dream",
    "goal",
    "insight",
    "emotion_snapshot",
    "goal_reinforcement",
}


def _now() -> _dt.datetime:
    return _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)


def _parse_timestamp(value: str | None) -> _dt.datetime:
    if not value:
        return _now()
    try:
        ts = _dt.datetime.fromisoformat(value)
    except ValueError:
        return _now()
    if ts.tzinfo is None:
        return ts.replace(tzinfo=_dt.timezone.utc)
    return ts


def _normalise(entry: dict) -> dict:
    data = dict(entry)
    if not data.get("category"):
        data["category"] = "event"
    if data["category"] not in _VALID_CATEGORIES:
        data["category"] = "event"
    if "emotions" not in data or not isinstance(data["emotions"], dict):
        data["emotions"] = {}
    data.setdefault("tags", [])
    if not isinstance(data.get("meta"), dict):
        data["meta"] = {}
    if "dominant_emotion" not in data:
        data["dominant_emotion"] = dominant_emotion(data["emotions"])
    return data


def _clause_predicate(clause: str) -> Callable[[dict], bool]:
    clause = clause.strip()
    if not clause:
        return lambda _: True
    if clause.lower().startswith("tag:"):
        tag = clause.split(":", 1)[1].strip().lower()
        return lambda entry: any(t.lower() == tag for t in entry.get("tags", []))
    if clause.lower().startswith("category:"):
        category = clause.split(":", 1)[1].strip().lower()
        return lambda entry: str(entry.get("category", "")).lower() == category
    match = _QUERY_OPERATOR.match(clause)
    if match:
        field, op, value = match.groups()
        target = float(value)

        def predicate(entry: dict) -> bool:
            score = float(entry.get(field, 0.0))
            if op == ">":
                return score > target
            if op == ">=":
                return score >= target
            if op == "<":
                return score < target
            if op == "<=":
                return score <= target
            return False

        return predicate
    return lambda _: False


def _compile_query(query: str | None) -> Callable[[dict], bool]:
    if not query:
        return lambda entry: float(entry.get("importance", 0.0)) >= _DEFAULT_THRESHOLD
    or_groups: List[List[Callable[[dict], bool]]] = []
    for group in query.split("OR"):
        clauses = [
            _clause_predicate(part)
            for part in group.split("AND")
            if part.strip()
        ]
        if clauses:
            or_groups.append(clauses)
    if not or_groups:
        return lambda entry: float(entry.get("importance", 0.0)) >= _DEFAULT_THRESHOLD

    def predicate(entry: dict) -> bool:
        return any(all(clause(entry) for clause in group) for group in or_groups)

    return predicate


def recall(query: str | None = None, k: int = 10) -> list[dict]:
    """Return up to ``k`` memories that satisfy ``query``.

    The filter language supports simple ``importance`` comparisons and
    ``tag:foo``/``category:bar`` expressions joined by ``AND``/``OR``.
    """

    predicate = _compile_query(query)
    matches: list[dict] = []
    for idx, entry in enumerate(mm.iter_fragments(limit=500, reverse=True)):
        data = _normalise(entry)
        if predicate(data) or float(data.get("importance", 0.0)) >= _DEFAULT_THRESHOLD:
            matches.append(data)
        if len(matches) >= k * 3 or idx >= 1000:
            break
    matches.sort(
        key=lambda item: (
            float(item.get("importance", 0.0)),
            _parse_timestamp(item.get("timestamp")).timestamp(),
        ),
        reverse=True,
    )
    return matches[:k]


def remember(entry: dict, *, importance: float | None = None) -> dict:
    """Persist ``entry`` as a memory fragment and return the stored record."""

    payload = dict(entry)
    text = str(payload.get("text", "")).strip()
    if not text:
        raise ValueError("memory text is required")
    tags = [t for t in payload.get("tags", []) if t]
    source = payload.get("source") or payload.get("category") or "dream_loop"
    summary = payload.get("summary")
    emotions = payload.get("emotions")
    meta = payload.get("meta")
    reflective = payload.get("reflective", False)
    category = payload.get("category")
    override_importance = importance if importance is not None else payload.get("importance")
    fragment_id = mm.append_memory(
        text,
        tags=tags,
        source=source,
        emotions=emotions,
        meta=meta,
        category=category,
        summary=summary,
        importance=override_importance,
        reflective=reflective,
    )
    path = mm.RAW_PATH / f"{fragment_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {
            "id": fragment_id,
            "text": text,
            "tags": tags,
            "category": category,
            "summary": summary,
            "importance": override_importance,
            "source": source,
            "emotions": emotions or {},
        }
        data.setdefault("timestamp", _now().isoformat())
    return _normalise(data)


@dataclass
class ReflectionSummary:
    updated: int
    trimmed_snapshots: int


def _write_entry(path: Path, entry: dict) -> None:
    serialised = {k: v for k, v in entry.items() if k != "_path"}
    path.write_text(json.dumps(serialised, ensure_ascii=False), encoding="utf-8")
    try:
        mm._update_vector_index(serialised)  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - fallback for legacy builds
        pass


def reflect() -> ReflectionSummary:
    """Apply retention rules for dream, insight, and snapshot memories."""

    entries: list[dict] = []
    for fp in sorted(mm.RAW_PATH.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        data["_path"] = fp
        entries.append(data)

    now = _now()
    updated = 0
    snapshots: list[dict] = []

    for entry in entries:
        category = entry.get("category")
        dirty = False
        if not category or category not in _VALID_CATEGORIES:
            entry["category"] = "event"
            category = "event"
            dirty = True
        emotions = entry.get("emotions") or {}
        dominant = dominant_emotion(emotions)
        if dominant and entry.get("dominant_emotion") != dominant:
            entry["dominant_emotion"] = dominant
            dirty = True
        if category == "dream":
            if not entry.get("reflective"):
                entry["reflective"] = True
                dirty = True
            if float(entry.get("importance", 0.0)) < 0.65:
                entry["importance"] = 0.65
                dirty = True
            if dirty:
                _write_entry(entry["_path"], entry)
                updated += 1
        elif category == "insight":
            if not entry.get("reflective") or float(entry.get("importance", 0.0)) < 0.95:
                entry["reflective"] = True
                entry["importance"] = max(0.95, float(entry.get("importance", 0.0)))
                dirty = True
            if dirty:
                _write_entry(entry["_path"], entry)
                updated += 1
        elif category == "emotion_snapshot":
            snapshots.append(entry)
        else:
            peak = max(emotions.values()) if emotions else 0.0
            ts = _parse_timestamp(entry.get("timestamp"))
            if peak < 0.15 and float(entry.get("importance", 0.0)) > mm.IMPORTANCE_FLOOR:
                age_days = (now - ts).total_seconds() / 86400.0
                if age_days > 2:
                    entry["importance"] = max(
                        mm.IMPORTANCE_FLOOR,
                        float(entry.get("importance", 0.0)) * 0.9,
                    )
                    dirty = True
            if dirty:
                _write_entry(entry["_path"], entry)
                updated += 1

    trimmed = 0
    if snapshots:
        buckets: dict[int, tuple[_dt.datetime, dict]] = {}
        for snapshot in snapshots:
            ts = _parse_timestamp(snapshot.get("timestamp"))
            bucket = int(ts.timestamp() // (6 * 3600))
            current = buckets.get(bucket)
            if current is None or ts > current[0]:
                buckets[bucket] = (ts, snapshot)
        keep_ids = {snap["id"] for _, snap in buckets.values() if snap.get("id")}
        for snapshot in snapshots:
            if snapshot.get("id") not in keep_ids:
                path = snapshot["_path"]
                path.unlink(missing_ok=True)
                try:
                    mm._remove_from_index(snapshot.get("id", ""))  # type: ignore[attr-defined]
                except AttributeError:  # pragma: no cover - legacy compatibility
                    pass
                trimmed += 1

    return ReflectionSummary(updated=updated, trimmed_snapshots=trimmed)


__all__ = [
    "recall",
    "remember",
    "reflect",
    "combine_emotions",
    "dominant_emotion",
    "ReflectionSummary",
]

