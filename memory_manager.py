import os
import json
import hashlib
import datetime
from pathlib import Path
from typing import List, Dict, Optional
from emotions import empty_emotion_vector
import emotion_memory as em

# Optional upgrade: use simple embedding vectors instead of bag-of-words
USE_EMBEDDINGS = os.getenv("USE_EMBEDDINGS", "0") == "1"

MEMORY_DIR = Path(os.getenv("MEMORY_DIR", "logs/memory"))
RAW_PATH = MEMORY_DIR / "raw"
DAY_PATH = MEMORY_DIR / "distilled"
VECTOR_INDEX_PATH = MEMORY_DIR / "vector.idx"
GOALS_PATH = MEMORY_DIR / "goals.json"

RAW_PATH.mkdir(parents=True, exist_ok=True)
DAY_PATH.mkdir(parents=True, exist_ok=True)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def append_memory(
    text: str,
    tags: List[str] | None = None,
    source: str = "unknown",
    emotions: Dict[str, float] | None = None,
    emotion_features: Dict[str, float] | None = None,
    emotion_breakdown: Dict[str, Dict[str, float]] | None = None,
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
    em.add_emotion(entry["emotions"])
    (RAW_PATH / f"{fragment_id}.json").write_text(
        json.dumps(entry, ensure_ascii=False), encoding="utf-8"
    )
    _update_vector_index(entry)
    print(f"[MEMORY] Appended fragment → {fragment_id} | tags={tags} | source={source}")
    return fragment_id


def _update_vector_index(entry: Dict):
    vec = _vectorize(entry["text"])
    record = {
        "id": entry["id"],
        "vector": vec,
        "snippet": entry["text"][:400],
    }
    with open(VECTOR_INDEX_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    print(f"[VECTOR] Index updated for {entry['id']}")


def _bag_of_words(text: str) -> Dict[str, int]:
    words = text.lower().split()
    return {w: words.count(w) for w in set(words)}


def _embedding(text: str) -> List[float]:
    """Return a deterministic pseudo-embedding for ``text``."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [b / 255.0 for b in digest[:64]]


def _vectorize(text: str):
    return _embedding(text) if USE_EMBEDDINGS else _bag_of_words(text)


def _cosine(a, b) -> float:
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
    if not VECTOR_INDEX_PATH.exists():
        return []
    lines = VECTOR_INDEX_PATH.read_text(encoding="utf-8").splitlines()
    out: List[Dict] = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"[VECTOR INDEX WARNING] Skipped malformed line at #{i}: {e}")
    return out


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
    index = _load_index()
    q_vec = _vectorize(query)
    scored: List[tuple[float, str]] = []
    for row in index:
        if is_reflection_loop(row.get("snippet", "")):
            continue
        score = _cosine(q_vec, row.get("vector", {}))
        scored.append((score, row.get("snippet", "")))
    scored.sort(reverse=True)
    return [s for _, s in scored[:k]]


# Compatibility alias for legacy bridges
write_mem = append_memory


def purge_memory(max_age_days: Optional[int] = None, max_files: Optional[int] = None) -> None:
    """Delete old fragments by age or limit total count."""
    files = list(RAW_PATH.glob("*.json"))
    entries = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            ts = datetime.datetime.fromisoformat(data.get("timestamp"))
            entries.append((ts, f))
        except Exception:
            continue
    entries.sort(key=lambda x: x[0])

    now = datetime.datetime.utcnow()
    removed = 0
    if max_age_days is not None:
        cutoff = now - datetime.timedelta(days=max_age_days)
        for ts, fp in entries:
            if ts < cutoff:
                fp.unlink(missing_ok=True)
                removed += 1
    if max_files is not None and len(entries) - removed > max_files:
        remaining = [e for e in entries if e[1].exists()]
        excess = len(remaining) - max_files
        for ts, fp in remaining[:excess]:
            fp.unlink(missing_ok=True)
            removed += 1
    if removed:
        print(f"[PURGE] Removed {removed} old memory fragments")


def summarize_memory() -> None:
    """Concatenate daily fragments into summary files."""
    summaries: Dict[str, List[str]] = {}
    for fp in RAW_PATH.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        ts = data.get("timestamp")
        if not ts:
            continue
        day = ts.split("T")[0]
        snippet = data.get("text", "").strip().replace("\n", " ")
        summaries.setdefault(day, []).append(f"[{ts}] {snippet}")

    for day, lines in summaries.items():
        out = DAY_PATH / f"{day}.txt"
        with open(out, "a", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
        print(f"[SUMMARY] Updated {out}")


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


def add_goal(text: str, *, intent: dict | None = None, user: str = "") -> dict:
    goal_id = _hash(text + datetime.datetime.utcnow().isoformat())
    goal = {
        "id": goal_id,
        "text": text,
        "intent": intent or {},
        "created": datetime.datetime.utcnow().isoformat(),
        "status": "open",
        "user": user,
    }
    goals = _load_goals()
    goals.append(goal)
    _save_goals(goals)
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


def get_goals(*, open_only: bool = False) -> list[dict]:
    goals = _load_goals()
    if open_only:
        goals = [g for g in goals if g.get("status") == "open"]
    goals.sort(key=lambda x: x.get("created", ""))
    return goals
