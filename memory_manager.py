import os
import json
import hashlib
import datetime
from pathlib import Path
from typing import List, Dict, Optional

MEMORY_DIR = Path(os.getenv("MEMORY_DIR", "logs/memory"))
RAW_PATH = MEMORY_DIR / "raw"
DAY_PATH = MEMORY_DIR / "distilled"
VECTOR_INDEX_PATH = MEMORY_DIR / "vector.idx"

RAW_PATH.mkdir(parents=True, exist_ok=True)
DAY_PATH.mkdir(parents=True, exist_ok=True)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def append_memory(text: str, tags: List[str] | None = None, source: str = "unknown") -> str:
    fragment_id = _hash(text + datetime.datetime.utcnow().isoformat())
    entry = {
        "id": fragment_id,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "tags": tags or [],
        "source": source,
        "text": text.strip(),
    }
    (RAW_PATH / f"{fragment_id}.json").write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    _update_vector_index(entry)
    print(f"[MEMORY] Appended fragment → {fragment_id} | tags={tags} | source={source}")
    return fragment_id


def _update_vector_index(entry: Dict):
    vec = _bag_of_words(entry["text"])
    record = {"id": entry["id"], "vector": vec, "snippet": entry["text"][:400]}
    with open(VECTOR_INDEX_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    print(f"[VECTOR] Index updated for {entry['id']}")


def _bag_of_words(text: str) -> Dict[str, int]:
    return {w: text.lower().split().count(w) for w in set(text.lower().split())}


def _cosine(a: Dict[str, int], b: Dict[str, int]) -> float:
    dot = sum(a.get(t, 0) * b.get(t, 0) for t in a)
    mag = (sum(v * v for v in a.values()) ** 0.5) * (sum(v * v for v in b.values()) ** 0.5)
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
    return any(p in snippet.lower() for p in REFLECTION_PHRASES)


def get_context(query: str, k: int = 6) -> List[str]:
    index = _load_index()
    q_vec = _bag_of_words(query)
    scored = []
    for row in index:
        if is_reflection_loop(row.get("snippet", "")):
            continue
        score = _cosine(q_vec, row["vector"])
        scored.append((score, row["snippet"]))
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
