"""Persistent stream of reflection events."""

from logging_config import get_log_path
import os
import json
import datetime
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

STREAM_DIR = get_log_path("reflections", "REFLECTION_DIR")
STREAM_FILE = STREAM_DIR / "stream.jsonl"
REFLEX_LEARN_FILE = STREAM_DIR / "reflex_learn.jsonl"
STREAM_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    """Return the current UTC timestamp."""
    return datetime.datetime.utcnow().isoformat()


def log_event(
    source: str,
    event_type: str,
    cause: str,
    action: str,
    explanation: str = "",
    data: Optional[Dict[str, Any]] = None,
) -> str:
    """Append an entry to the reflection stream and return its id."""
    entry_id = uuid.uuid4().hex[:8]
    entry = {
        "id": entry_id,
        "timestamp": _now(),
        "source": source,
        "event": event_type,
        "cause": cause,
        "action": action,
        "explanation": explanation,
        "data": data or {},
    }
    with STREAM_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry_id


def log_reflex_learn(data: Dict[str, Any]) -> str:
    """Log autonomous reflex learning events."""
    entry_id = uuid.uuid4().hex[:8]
    entry = {
        "id": entry_id,
        "timestamp": _now(),
        "data": data,
    }
    with REFLEX_LEARN_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry_id


def recent(limit: int = 10) -> List[Dict[str, Any]]:
    if not STREAM_FILE.exists():
        return []
    lines = STREAM_FILE.read_text(encoding="utf-8").splitlines()
    out: List[Dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def recent_reflex_learn(limit: int = 10) -> List[Dict[str, Any]]:
    if not REFLEX_LEARN_FILE.exists():
        return []
    lines = REFLEX_LEARN_FILE.read_text(encoding="utf-8").splitlines()
    out: List[Dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def get(entry_id: str) -> Optional[Dict[str, Any]]:
    if not STREAM_FILE.exists():
        return None
    with STREAM_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            entry = cast(Dict[str, Any], obj)
            if entry.get("id") == entry_id:
                return entry
    return None


def stats() -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for entry in recent(1000):
        typ = entry.get("event")
        if isinstance(typ, str):
            counts[typ] = counts.get(typ, 0) + 1
    return counts
