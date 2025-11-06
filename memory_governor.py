"""Coordinated access to long-term memory for SentientOS dream cycles."""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List

try:  # pragma: no cover - optional dependency during tests
    from verifier_store import VerifierStore
except Exception:  # pragma: no cover - fallback when verifier not initialised
    VerifierStore = None  # type: ignore[assignment]

import memory_manager as mm

from emotion_utils import combine_emotions, dominant_emotion
import secure_memory_storage as secure_store
from node_registry import registry


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


_LAST_REFLECTION: "ReflectionSummary | None" = None


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
    source_iterable: Iterable[dict]
    if secure_store.is_enabled():
        source_iterable = secure_store.iterate_plaintext(limit=500)
    else:
        source_iterable = mm.iter_fragments(limit=500, reverse=True)
    for idx, entry in enumerate(source_iterable):
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


def _incognito_enabled() -> bool:
    return os.getenv("MEM_INCOGNITO", "0") == "1"


def remember(entry: dict, *, importance: float | None = None) -> dict | str:
    """Persist ``entry`` as a memory fragment and return the stored record."""

    if _incognito_enabled():
        return ""
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
    normalised = _normalise(data)
    if secure_store.is_enabled():
        try:
            secure_store.save_fragment(normalised)
        except Exception as exc:  # pragma: no cover - defensive
            logging.warning("[MemoryGovernor] secure store write failed: %s", exc)
    return normalised


def remember_voice_session(
    summary: str,
    *,
    emotions: dict | None = None,
    importance: float = 0.4,
    meta: dict | None = None,
) -> dict | str:
    """Capture a voice session summary in encrypted storage when available."""

    summary_text = (summary or "").strip()
    if not summary_text or _incognito_enabled():
        return ""

    fragment = {
        "id": uuid.uuid4().hex,
        "text": summary_text,
        "summary": summary_text,
        "category": "voice_session",
        "tags": ["voice_session"],
        "importance": importance,
        "emotions": emotions or {},
        "meta": dict(meta or {}),
        "timestamp": _now().isoformat(),
        "source": "voice",
    }

    if secure_store.is_enabled():
        secure_store.save_fragment(fragment)
        return fragment

    return remember(fragment, importance=importance)


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

    if secure_store.is_enabled():
        try:
            import mem_admin

            mem_admin.reflect()
        except Exception as exc:  # pragma: no cover - defensive logging only
            logging.debug("[MemoryGovernor] secure reflect skipped: %s", exc)

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

    global _LAST_REFLECTION
    summary = ReflectionSummary(updated=updated, trimmed_snapshots=trimmed)
    _LAST_REFLECTION = summary
    return summary


def _category_counts(limit: int = 500) -> dict[str, int]:
    counts: dict[str, int] = {}
    if secure_store.is_enabled():
        iterator = secure_store.iterate_plaintext(limit=limit)
    else:
        iterator = mm.iter_fragments(limit=limit, reverse=True)
    for entry in iterator:
        category = str(entry.get("category") or "event")
        counts[category] = counts.get(category, 0) + 1
    return counts


def metrics(limit: int = 500) -> dict[str, object]:
    """Expose summary metrics for administrative dashboards."""

    counts = _category_counts(limit=limit)
    total = sum(counts.values())
    reflection_summary: dict[str, int] | None = None
    if _LAST_REFLECTION is not None:
        reflection_summary = {
            "updated": _LAST_REFLECTION.updated,
            "trimmed_snapshots": _LAST_REFLECTION.trimmed_snapshots,
        }
    verifier_stats = _verifier_stats()
    return {
        "total": total,
        "categories": counts,
        "secure_store": secure_store.is_enabled(),
        "incognito": _incognito_enabled(),
        "last_reflection": reflection_summary,
        "verifier": verifier_stats,
    }


def _verifier_stats() -> dict[str, object]:
    if VerifierStore is None:
        return {"counts": {}, "proof_counts": {}, "consensus": {}, "trust": {}}
    try:
        store = VerifierStore.default()
        today = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=_dt.timezone.utc)
        stats = store.stats(since=today.timestamp())
        consensus_index = store.consensus_index()
        finalized = 0
        ok = 0
        diverged = 0
        inconclusive = 0
        for entry in consensus_index.values():
            if not isinstance(entry, dict):
                continue
            if entry.get("finalized"):
                finalized += 1
                verdict = entry.get("final_verdict")
                if verdict == "VERIFIED_OK":
                    ok += 1
                elif verdict == "DIVERGED":
                    diverged += 1
                elif verdict == "INCONCLUSIVE":
                    inconclusive += 1
            else:
                inconclusive += 1
        stats["consensus"] = {
            "finalized": finalized,
            "ok": ok,
            "diverged": diverged,
            "inconclusive": inconclusive,
        }
        stats["trust"] = _trust_histogram()
        return stats
    except Exception:  # pragma: no cover - defensive
        return {"counts": {}, "proof_counts": {}, "consensus": {}, "trust": {}}


def _trust_histogram() -> dict[str, int]:
    buckets = {
        "<=-4": 0,
        "-3..-1": 0,
        "0": 0,
        "1..3": 0,
        ">=4": 0,
    }
    try:
        for record in registry.records():
            if record.capabilities.get("verifier_capable") is not True:
                continue
            score = int(record.trust_score)
            if score <= -4:
                buckets["<=-4"] += 1
            elif -3 <= score <= -1:
                buckets["-3..-1"] += 1
            elif score == 0:
                buckets["0"] += 1
            elif 1 <= score <= 3:
                buckets["1..3"] += 1
            else:
                buckets[">=4"] += 1
    except Exception:  # pragma: no cover - defensive
        return {}
    return {key: value for key, value in buckets.items() if value}


__all__ = [
    "recall",
    "remember",
    "remember_voice_session",
    "reflect",
    "metrics",
    "combine_emotions",
    "dominant_emotion",
    "ReflectionSummary",
]

