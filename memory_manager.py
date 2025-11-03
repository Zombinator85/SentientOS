"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import collections
import math
import os
import json
import hashlib
import datetime
from datetime import timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union

# Vector type can be either an embedding vector or bag-of-words mapping
Vector = Union[List[float], Dict[str, int]]
from emotions import empty_emotion_vector
import emotion_memory as em
import semantic_embeddings as se

# Optional upgrade: use simple embedding vectors instead of bag-of-words
USE_EMBEDDINGS = os.getenv("USE_EMBEDDINGS", "0") == "1"

# Root folder for persistent memory fragments. The ``MEMORY_DIR`` environment
# variable is described in ``docs/ENVIRONMENT.md``.
MEMORY_DIR = get_log_path("memory", "MEMORY_DIR")
RAW_PATH = MEMORY_DIR / "raw"
DAY_PATH = MEMORY_DIR / "distilled"
TOPIC_PATH = MEMORY_DIR / "topics"
TURN_PATH = MEMORY_DIR / "turns"
SESSION_PATH = MEMORY_DIR / "sessions"
VECTOR_INDEX_PATH = MEMORY_DIR / "vector.idx"
GOALS_PATH = MEMORY_DIR / "goals.json"
TOMB_PATH = MEMORY_DIR / "memory_tomb.jsonl"
OBSERVATION_LOG_PATH = MEMORY_DIR / "perception_observations.jsonl"

RAW_PATH.mkdir(parents=True, exist_ok=True)
DAY_PATH.mkdir(parents=True, exist_ok=True)
TOPIC_PATH.mkdir(parents=True, exist_ok=True)
TURN_PATH.mkdir(parents=True, exist_ok=True)
SESSION_PATH.mkdir(parents=True, exist_ok=True)
TOMB_PATH.parent.mkdir(parents=True, exist_ok=True)
OBSERVATION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# --- Importance & forgetting heuristics -------------------------------------

FORGETTING_HALF_LIFE_DAYS = float(os.getenv("MEMORY_HALF_LIFE_DAYS", "14"))
IMPORTANCE_FLOOR = float(os.getenv("MEMORY_IMPORTANCE_FLOOR", "0.2"))
IMPORTANCE_TAG_BOOSTS = {
    "goal": 0.15,
    "reflection": 0.2,
    "self_patch": 0.1,
    "escalation": 0.25,
    "blessing": 0.12,
}
_INDEX_LOCK = RLock()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _fragment_path(fragment_id: str) -> Path:
    return RAW_PATH / f"{fragment_id}.json"


def _load_fragment(fragment_id: str) -> dict | None:
    path = _fragment_path(fragment_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_fragment(fragment_id: str, data: dict) -> None:
    path = _fragment_path(fragment_id)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def iter_fragments(*, limit: int | None = None, reverse: bool = True) -> Iterable[dict]:
    """Yield raw memory fragments as dictionaries.

    Parameters
    ----------
    limit:
        Maximum number of fragments to yield. ``None`` returns every fragment.
    reverse:
        When ``True`` (default) iterate from newest to oldest.
    """

    files = sorted(RAW_PATH.glob("*.json"), reverse=reverse)
    count = 0
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        yield data
        count += 1
        if limit is not None and count >= limit:
            break


def _load_index_records() -> list[dict]:
    if not VECTOR_INDEX_PATH.exists():
        return []
    lines = VECTOR_INDEX_PATH.read_text(encoding="utf-8").splitlines()
    records: list[dict] = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"[VECTOR INDEX WARNING] Skipped malformed line at #{i}: {exc}")
    return records


def _save_index_records(records: Sequence[dict]) -> None:
    with _INDEX_LOCK:
        with open(VECTOR_INDEX_PATH, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")


def _remove_from_index(fragment_id: str) -> None:
    records = [rec for rec in _load_index_records() if rec.get("id") != fragment_id]
    _save_index_records(records)


def _append_tomb(entry: Dict) -> None:
    """Append a purge record to the immutable memory tomb."""
    payload = entry.copy()
    payload.pop("hash", None)
    if os.getenv("TOMB_HASH", "1") != "0":
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        entry["hash"] = digest
    with open(TOMB_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def list_tomb(
    *, tag: str | None = None, reason: str | None = None, date: str | None = None
) -> List[Dict]:
    """Return tomb entries filtered by tag, reason, or date."""
    if not TOMB_PATH.exists():
        return []
    out: List[Dict] = []
    lines = TOMB_PATH.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        frag = entry.get("fragment", {})
        if tag and tag not in frag.get("tags", []):
            continue
        if reason and reason not in entry.get("reason", ""):
            continue
        ts = entry.get("time", "") or frag.get("timestamp", "")
        if date and not ts.startswith(date):
            continue
        out.append(entry)
    return out


def _estimate_importance(entry: dict) -> float:
    text = entry.get("text", "")
    score = 0.35
    word_count = len(text.split())
    score += min(0.2, word_count / 400.0)
    emotions = entry.get("emotions") or {}
    intensity = max(emotions.values()) if isinstance(emotions, dict) and emotions else 0.0
    score += min(0.2, intensity * 0.5)
    for tag in entry.get("tags", []):
        score += IMPORTANCE_TAG_BOOSTS.get(tag, 0.05)
    if entry.get("source") == "reflector":
        score += 0.05
    return max(0.05, min(1.0, score))


def _touch_fragment(fragment_id: str, *, accessed_at: datetime.datetime) -> None:
    data = _load_fragment(fragment_id)
    if not data:
        return
    data["access_count"] = data.get("access_count", 0) + 1
    data["last_accessed"] = accessed_at.isoformat()
    _write_fragment(fragment_id, data)


def _decay_factor(last_access: datetime.datetime, importance: float, now: datetime.datetime) -> float:
    age_days = max((now - last_access).total_seconds() / 86400.0, 0.0)
    if FORGETTING_HALF_LIFE_DAYS <= 0:
        return importance
    decay = math.exp(-age_days / FORGETTING_HALF_LIFE_DAYS)
    return importance * decay


def _parse_ts(value: str | None) -> datetime.datetime:
    if not value:
        return datetime.datetime.utcnow().replace(tzinfo=timezone.utc)
    try:
        dt = datetime.datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.datetime.utcnow().replace(tzinfo=timezone.utc)


def append_memory(
    text: str,
    tags: List[str] | None = None,
    source: str = "unknown",
    emotions: Dict[str, float] | None = None,
    emotion_features: Dict[str, float] | None = None,
    emotion_breakdown: Dict[str, Dict[str, float]] | None = None,
    meta: Dict[str, object] | None = None,
) -> str:
    if os.getenv("INCOGNITO") == "1":
        print("[MEMORY] Incognito mode enabled – skipping persistence")
        return "incognito"
    fragment_id = _hash(text + datetime.datetime.utcnow().isoformat())
    entry = {
        "id": fragment_id,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "tags": tags or [],
        "source": source,
        "text": text.strip(),
        "emotions": emotions or empty_emotion_vector(),
        "emotion_features": emotion_features or {},
        "emotion_breakdown": emotion_breakdown or {},
    }
    if meta:
        entry["meta"] = meta
    entry["importance"] = _estimate_importance(entry)
    entry["access_count"] = 0
    entry["last_accessed"] = entry["timestamp"]
    em.add_emotion(entry["emotions"])
    _write_fragment(fragment_id, entry)
    _update_vector_index(entry)
    print(f"[MEMORY] Appended fragment → {fragment_id} | tags={tags} | source={source}")
    return fragment_id


def _update_vector_index(entry: Dict):
    vec = _vectorize(entry["text"])
    records = [rec for rec in _load_index_records() if rec.get("id") != entry["id"]]
    record = {
        "id": entry["id"],
        "vector": vec,
        "snippet": entry["text"][:400],
        "importance": entry.get("importance", 0.3),
        "tags": entry.get("tags", []),
        "last_accessed": entry.get("last_accessed"),
        "access_count": entry.get("access_count", 0),
    }
    records.append(record)
    _save_index_records(records)
    print(f"[VECTOR] Index updated for {entry['id']}")


def _bag_of_words(text: str) -> Dict[str, int]:
    words = text.lower().split()
    return {w: words.count(w) for w in set(words)}


def _embedding(text: str) -> List[float]:
    """Return a semantic embedding for ``text`` with deterministic fallback."""

    try:
        vectors = se.encode([text])
        if vectors:
            return vectors[0]
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[EMBEDDING WARNING] Falling back to hash embedding: {exc}")
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [b / 255.0 for b in digest[:64]]


def _vectorize(text: str) -> Vector:
    """Return either an embedding vector or bag-of-words mapping."""
    return _embedding(text) if USE_EMBEDDINGS else _bag_of_words(text)


def _cosine(a: Vector, b: Vector) -> float:
    """Cosine similarity for dict or list vectors."""
    if isinstance(a, dict) and isinstance(b, dict):
        dot = sum(a.get(t, 0) * b.get(t, 0) for t in a)
        mag = (sum(v * v for v in a.values()) ** 0.5) * (
            sum(v * v for v in b.values()) ** 0.5
        )
        return dot / mag if mag else 0.0
    # assume numeric vectors
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    return dot / mag if mag else 0.0


def _load_index() -> List[Dict]:
    return list(_load_index_records())


def _load_observation_records() -> List[Dict[str, Any]]:
    if not OBSERVATION_LOG_PATH.exists():
        return []
    records: List[Dict[str, Any]] = []
    with open(OBSERVATION_LOG_PATH, "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _write_observation_record(record: Mapping[str, Any]) -> None:
    with open(OBSERVATION_LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), ensure_ascii=False) + "\n")


def _parse_observation_timestamp(value: str | None) -> datetime.datetime:
    if not value:
        return datetime.datetime.utcnow().replace(tzinfo=timezone.utc)
    try:
        dt = datetime.datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.datetime.utcnow().replace(tzinfo=timezone.utc)


def store_observation_summary(summary: Mapping[str, Any]) -> Dict[str, Any]:
    """Persist a perception observation summary with novelty scoring."""

    summary_text = str(summary.get("summary") or summary.get("text") or "").strip()
    if not summary_text:
        raise ValueError("Observation summary text is required")
    timestamp = str(summary.get("timestamp") or datetime.datetime.utcnow().isoformat())
    embedding = _embedding(summary_text)
    previous = _load_observation_records()
    similarities = [
        _cosine(embedding, rec.get("embedding", []))
        for rec in previous
        if isinstance(rec.get("embedding"), list)
    ]
    novelty = max(0.0, min(1.0, 1.0 - (max(similarities) if similarities else 0.0)))
    record: Dict[str, Any] = dict(summary)
    record["timestamp"] = timestamp
    record["summary"] = summary_text
    record.setdefault("objects", [])
    record.setdefault("novel_objects", [])
    record.setdefault("transcripts", [])
    record.setdefault("screen", [])
    record.setdefault("emotions", {})
    record.setdefault("source_events", 0)
    record["novelty"] = novelty
    record["embedding"] = embedding
    record["observation_id"] = _hash(summary_text + timestamp)
    meta_payload = {k: v for k, v in record.items() if k not in {"embedding"}}
    fragment_id = append_memory(
        summary_text,
        tags=list(summary.get("tags", ["observation", "perception"])),
        source=str(summary.get("source", "perception_reasoner")),
        emotions=record.get("emotions"),
        meta={"observation": meta_payload},
    )
    record["fragment_id"] = fragment_id
    _write_observation_record(record)
    return record


def _coerce_since(value: object) -> datetime.datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.datetime.fromisoformat(value)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            try:
                return datetime.datetime.fromtimestamp(float(value), tz=timezone.utc)
            except Exception:
                return None
    return None


def recent_observations(
    *,
    limit: int = 20,
    since: object | None = None,
    include_embeddings: bool = False,
) -> List[Dict[str, Any]]:
    """Return recent observation summaries, newest first."""

    records = _load_observation_records()
    since_dt = _coerce_since(since)
    if since_dt is not None:
        filtered: List[Dict[str, Any]] = []
        for rec in records:
            ts = _parse_observation_timestamp(str(rec.get("timestamp")))
            if ts >= since_dt:
                filtered.append(rec)
        records = filtered
    if limit > 0:
        records = records[-int(limit) :]
    records = list(reversed(records))
    if include_embeddings:
        return records
    sanitized: List[Dict[str, Any]] = []
    for rec in records:
        clean = {k: v for k, v in rec.items() if k != "embedding"}
        sanitized.append(clean)
    return sanitized


def latest_observation(*, include_embedding: bool = False) -> Dict[str, Any] | None:
    observations = recent_observations(limit=1, include_embeddings=include_embedding)
    return observations[0] if observations else None


REFLECTION_PHRASES = [
    "logsxt",
    "og.txt",
    "iogs",
    "telegram lumos logsxt",
    "as a helpful assistant",
    "please provide more context",
    "i will always be honest",
    "i do have access to that file",
    "likely in reference to",
    "conversation history",
    "united, and curl",
    "it looks like you're asking",
    "how can i assist you today",
    "1:38 pm",
    "re-confirming their ability",
    "smart quotes",
    "write(memory_manager_pat",
    "mnt/de",
    "with open(memory_manager_path",
]


def is_reflection_loop(snippet: str) -> bool:
    lowered = snippet.lower()
    return any(p in lowered for p in REFLECTION_PHRASES)


def get_context(query: str, k: int = 6) -> List[str]:
    index = _load_index_records()
    q_vec = _vectorize(query)
    now = datetime.datetime.utcnow().replace(tzinfo=timezone.utc)
    scored: List[tuple[float, dict]] = []
    for row in index:
        snippet = row.get("snippet", "")
        if not snippet or is_reflection_loop(snippet):
            continue
        score = _cosine(q_vec, row.get("vector", {}))
        if score <= 0:
            continue
        importance = float(row.get("importance", 0.3))
        access_count = int(row.get("access_count", 0))
        last_access = _parse_ts(row.get("last_accessed"))
        freshness = _decay_factor(last_access, importance, now)
        vote = score * (0.6 + 0.4 * freshness) * (1.0 + min(access_count, 10) * 0.05)
        scored.append((vote, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    top_rows = [row for _, row in scored[:k]]
    if not top_rows:
        return []

    updated_records = index.copy()
    snippets: List[str] = []
    seen: set[str] = set()
    for row in top_rows:
        frag_id = row.get("id")
        if not frag_id or frag_id in seen:
            continue
        seen.add(frag_id)
        snippets.append(row.get("snippet", ""))
        row["access_count"] = int(row.get("access_count", 0)) + 1
        row["last_accessed"] = now.isoformat()
        _touch_fragment(frag_id, accessed_at=now)

    if updated_records:
        _save_index_records(updated_records)

    return [s for s in snippets if s][:k]


def search_by_tags(tags: List[str], limit: int = 5) -> list[dict]:
    """Return recent memory fragments matching all ``tags``.

    Results are ordered from newest to oldest and truncated to ``limit``.
    """
    files = list(RAW_PATH.glob("*.json"))
    entries = []
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            ts = data.get("timestamp")
            entries.append((ts, data))
        except Exception:
            continue
    entries.sort(key=lambda x: x[0] or "", reverse=True)
    results: list[dict] = []
    wanted = set(tags)
    for _, data in entries:
        entry_tags = set(data.get("tags", []))
        if not wanted.issubset(entry_tags):
            continue
        results.append(data)
        if len(results) >= limit:
            break
    return results


# Compatibility alias for legacy bridges
write_mem = append_memory


def purge_memory(
    max_age_days: Optional[int] = None,
    max_files: Optional[int] = None,
    *,
    requestor: str = "system",
    reason: str = "",
) -> None:
    """Delete old fragments by age or limit total count.

    Purged fragments are archived in the memory tomb.
    """
    files = list(RAW_PATH.glob("*.json"))
    entries: List[tuple[datetime.datetime, Path, dict]] = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            ts = _parse_ts(data.get("timestamp")).astimezone(timezone.utc)
            entries.append((ts, f, data))
        except Exception:
            continue
    entries.sort(key=lambda x: x[0])

    now = datetime.datetime.utcnow()
    removed = 0
    if max_age_days is not None:
        cutoff = now - datetime.timedelta(days=max_age_days)
        for ts, fp, data in entries:
            if ts < cutoff:
                _append_tomb({
                    "fragment": data,
                    "requestor": requestor,
                    "time": datetime.datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                fp.unlink(missing_ok=True)
                _remove_from_index(data.get("id", ""))
                removed += 1
    if max_files is not None and len(entries) - removed > max_files:
        remaining = [e for e in entries if e[1].exists()]
        excess = len(remaining) - max_files
        for ts, fp, data in remaining[:excess]:
            _append_tomb({
                "fragment": data,
                "requestor": requestor,
                "time": datetime.datetime.utcnow().isoformat(),
                "reason": reason,
            })
            fp.unlink(missing_ok=True)
            _remove_from_index(data.get("id", ""))
            removed += 1
    if removed:
        print(f"[PURGE] Removed {removed} old memory fragments")


def _write_topic_summaries(entries: Sequence[dict]) -> None:
    topics: Dict[str, List[str]] = {}
    for data in entries:
        tags = data.get("tags", []) or []
        if not tags:
            continue
        ts = data.get("timestamp", "")
        snippet = data.get("text", "").strip().replace("\n", " ")
        for tag in tags:
            topics.setdefault(tag, []).append(f"[{ts}] {snippet}")

    for tag, lines in topics.items():
        if not tag:
            continue
        out = TOPIC_PATH / f"{tag}.md"
        with open(out, "w", encoding="utf-8") as f:
            f.write(f"# {tag} memory capsule\n\n")
            for line in lines[-200:]:  # keep recent history manageable
                f.write(f"- {line}\n")
        print(f"[SUMMARY] Topic capsule updated → {out}")


def _extract_session_id(entry: dict) -> str | None:
    meta = entry.get("meta")
    if isinstance(meta, dict):
        for key in ("session", "conversation", "thread", "goal"):
            value = meta.get(key)
            if value:
                return str(value)
    for tag in entry.get("tags", []) or []:
        if ":" in tag:
            prefix, value = tag.split(":", 1)
            if prefix in {"session", "conversation", "goal"} and value:
                return value
    goal_id = entry.get("goal_id")
    if goal_id:
        return str(goal_id)
    return None


def _write_session_digest(session_id: str, entries: Sequence[dict]) -> None:
    if not session_id or not entries:
        return
    entries = sorted(entries, key=lambda item: item.get("timestamp", ""))
    start = entries[0].get("timestamp", "")
    end = entries[-1].get("timestamp", "")
    tags = collections.Counter()
    highlights: list[str] = []
    for entry in entries[-10:]:
        tags.update(entry.get("tags", []) or [])
        text = (entry.get("summary") or entry.get("text", "")).strip().replace("\n", " ")
        if text:
            highlights.append(text[:240])

    common_tags = ", ".join(tag for tag, _ in tags.most_common(6)) or "(none)"
    out = SESSION_PATH / f"{session_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(f"# Session {session_id}\n\n")
        handle.write(f"* timeframe: {start} → {end}\n")
        handle.write(f"* entries: {len(entries)}\n")
        handle.write(f"* dominant tags: {common_tags}\n\n")
        handle.write("## Highlights\n")
        for bullet in highlights:
            handle.write(f"- {bullet}\n")
    print(f"[SUMMARY] Session digest updated → {out}")


def _write_turn_summaries(entries: Sequence[dict]) -> None:
    sessions: dict[str, list[dict]] = {}
    for entry in entries:
        session_id = _extract_session_id(entry)
        if not session_id:
            continue
        sessions.setdefault(session_id, []).append(entry)

    for session_id, session_entries in sessions.items():
        session_entries.sort(key=lambda item: item.get("timestamp", ""))
        turns: list[dict] = []
        for item in session_entries[-50:]:
            text = (item.get("summary") or item.get("text", "")).strip().replace("\n", " ")
            turns.append(
                {
                    "timestamp": item.get("timestamp"),
                    "summary": text[:280],
                    "importance": item.get("importance"),
                    "tags": item.get("tags", []),
                }
            )
        out = TURN_PATH / f"{session_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(turns, ensure_ascii=False, indent=2))
        _write_session_digest(session_id, session_entries)
        print(f"[SUMMARY] Turn capsule updated → {out}")


def summarize_memory() -> None:
    """Concatenate daily fragments into summary files and topic capsules."""

    summaries: Dict[str, List[str]] = {}
    entries: List[dict] = []
    for fp in RAW_PATH.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        ts = data.get("timestamp")
        if not ts:
            continue
        entries.append(data)
        day = ts.split("T")[0]
        snippet = data.get("text", "").strip().replace("\n", " ")
        summaries.setdefault(day, []).append(f"[{ts}] {snippet}")

    for day, lines in summaries.items():
        out = DAY_PATH / f"{day}.txt"
        with open(out, "a", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
        print(f"[SUMMARY] Updated {out}")

    _write_topic_summaries(entries)
    _write_turn_summaries(entries)


def apply_forgetting_curve(
    *, requestor: str = "curator", reason: str = "forgetting_curve"
) -> int:
    """Apply an Ebbinghaus-inspired decay to prune low-importance fragments.

    Returns the number of fragments removed.
    """

    now = datetime.datetime.utcnow().replace(tzinfo=timezone.utc)
    removed = 0
    kept_records: list[dict] = []

    for record in _load_index_records():
        fragment_id = record.get("id")
        if not fragment_id:
            continue
        data = _load_fragment(fragment_id)
        if not data:
            continue
        if data.get("pinned"):
            kept_records.append(record)
            continue

        importance = float(data.get("importance", 0.3))
        access_count = int(data.get("access_count", 0))
        importance = max(importance, min(0.6, access_count * 0.05))
        last_access = _parse_ts(data.get("last_accessed"))
        retention = _decay_factor(last_access, importance, now)

        if retention < IMPORTANCE_FLOOR:
            _append_tomb(
                {
                    "fragment": data,
                    "requestor": requestor,
                    "time": now.isoformat(),
                    "reason": reason,
                }
            )
            _fragment_path(fragment_id).unlink(missing_ok=True)
            removed += 1
        else:
            data["importance"] = min(1.0, retention + 0.05 * importance)
            _write_fragment(fragment_id, data)
            record["importance"] = data["importance"]
            record["last_accessed"] = data.get("last_accessed")
            record["access_count"] = data.get("access_count", 0)
            kept_records.append(record)

    if kept_records:
        _save_index_records(kept_records)
    elif VECTOR_INDEX_PATH.exists():
        VECTOR_INDEX_PATH.unlink()

    if removed:
        print(f"[FORGET] Archived {removed} stale fragments")
    return removed


def curate_memory() -> dict[str, Any]:
    """Run summarisation and forgetting maintenance cycle."""

    removed = apply_forgetting_curve()
    summarize_memory()
    return {"removed": removed}


def save_reflection(
    *,
    parent: str,
    intent: dict,
    result: dict | None,
    reason: str,
    next_step: str | None = None,
    user: str = "",
    plugin: str = "",
) -> str:
    """Persist a structured reflection entry.

    Parameters
    ----------
    parent: id of the action log this reflection relates to
    intent: the original action intent
    result: action result if any
    reason: why the action was attempted or failed
    next_step: optional proposed follow-up
    """

    reflection = {
        "parent": parent,
        "intent": intent,
        "result": result,
        "reason": reason,
        "next": next_step,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "user": user,
        "plugin": plugin,
    }
    return append_memory(
        json.dumps(reflection, ensure_ascii=False),
        tags=["reflection", plugin],
        source="reflector",
    )


def recent_reflections(
    limit: int = 10,
    *,
    plugin: str | None = None,
    user: str | None = None,
    failures_only: bool = False,
) -> list[dict]:
    """Return recent reflection entries with optional filters."""

    files = sorted(RAW_PATH.glob("*.json"), reverse=True)
    out: list[dict] = []
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "reflection" not in data.get("tags", []):
            continue
        try:
            entry = json.loads(data.get("text", "{}"))
        except Exception:
            continue
        if plugin and entry.get("plugin") != plugin:
            continue
        if user and entry.get("user") != user:
            continue
        if failures_only and entry.get("result") is not None:
            continue
        entry["id"] = data.get("id")
        out.append(entry)
        if len(out) >= limit:
            break
    return out


def recent_patches(limit: int = 5) -> list[str]:
    """Return recent self-improvement patch notes."""
    files = sorted(RAW_PATH.glob("*.json"), reverse=True)
    out: list[str] = []
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "self_patch" not in data.get("tags", []):
            continue
        out.append(data.get("text", ""))
        if len(out) >= limit:
            break
    return out


def recent_escalations(limit: int = 5) -> list[str]:
    """Return recent escalation log snippets."""
    files = sorted(RAW_PATH.glob("*.json"), reverse=True)
    out: list[str] = []
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "escalation" not in data.get("tags", []):
            continue
        out.append(data.get("text", ""))
        if len(out) >= limit:
            break
    return out


# --- Goal management -------------------------------------------------------

def _load_goals() -> list[dict]:
    if GOALS_PATH.exists():
        try:
            return json.loads(GOALS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_goals(goals: list[dict]) -> None:
    GOALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOALS_PATH.write_text(json.dumps(goals, ensure_ascii=False, indent=2), encoding="utf-8")


def add_goal(
    text: str,
    *,
    intent: dict | None = None,
    user: str = "",
    priority: int = 1,
    deadline: str | None = None,
    schedule_at: str | None = None,
) -> dict:
    """Create and persist a new goal entry."""

    goal_id = _hash(text + datetime.datetime.utcnow().isoformat())
    goal = {
        "id": goal_id,
        "text": text,
        "intent": intent or {},
        "created": datetime.datetime.utcnow().isoformat(),
        "status": "open",
        "user": user,
        "priority": priority,
        "deadline": deadline,
        "schedule_at": schedule_at,
    }
    goals = _load_goals()
    goals.append(goal)
    _save_goals(goals)
    from notification import send as notify  # local import to avoid cycle
    notify("goal_created", {"id": goal_id, "text": text})
    return goal


def save_goal(goal: dict) -> None:
    goals = _load_goals()
    for i, g in enumerate(goals):
        if g.get("id") == goal.get("id"):
            goals[i] = goal
            break
    else:
        goals.append(goal)
    _save_goals(goals)


def delete_goal(goal_id: str) -> None:
    """Remove a goal by id."""
    goals = [g for g in _load_goals() if g.get("id") != goal_id]
    _save_goals(goals)


def get_goal(goal_id: str) -> dict | None:
    for g in _load_goals():
        if g.get("id") == goal_id:
            return g
    return None


def next_goal() -> dict | None:
    """Return the next due goal by priority and schedule."""
    goals = get_goals(open_only=False)
    now = datetime.datetime.utcnow()
    due: list[dict] = []
    for g in goals:
        if g.get("status") in {"completed", "stuck"}:
            continue
        at = g.get("schedule_at")
        if at:
            try:
                if datetime.datetime.fromisoformat(at) > now:
                    continue
            except Exception:
                pass
        due.append(g)
    due.sort(
        key=lambda x: (
            -int(x.get("priority", 1)),
            x.get("deadline") or x.get("created"),
        )
    )
    return due[0] if due else None


def get_goals(*, open_only: bool = False) -> list[dict]:
    goals = _load_goals()
    if open_only:
        goals = [g for g in goals if g.get("status") == "open"]
    goals.sort(
        key=lambda x: (
            -int(x.get("priority", 1)),
            x.get("created", ""),
        )
    )
    return goals
