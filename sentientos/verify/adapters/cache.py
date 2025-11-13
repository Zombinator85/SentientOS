"""Simple caching helpers for non-deterministic adapters."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from logging_config import get_log_path

_CACHE_FILE = get_log_path("adapter_cache.jsonl", "EXPERIMENT_ADAPTER_CACHE")
_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
_CACHE_INDEX: Dict[str, Any] | None = None


def cache_key(adapter: str, method: str, payload: Dict[str, Any]) -> str:
    """Return a stable hash key for the adapter call."""

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256()
    digest.update(adapter.encode("utf-8"))
    digest.update(b"::")
    digest.update(method.encode("utf-8"))
    digest.update(b"::")
    digest.update(canonical.encode("utf-8"))
    return digest.hexdigest()


def _ensure_index() -> Dict[str, Any]:
    global _CACHE_INDEX
    if _CACHE_INDEX is not None:
        return _CACHE_INDEX
    index: Dict[str, Any] = {}
    if _CACHE_FILE.exists():
        for line in _CACHE_FILE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = entry.get("key")
            if isinstance(key, str) and "value" in entry:
                index[key] = entry["value"]
    _CACHE_INDEX = index
    return index


def load_cached(adapter: str, method: str, payload: Dict[str, Any]) -> Any | None:
    """Return a cached value if present for the adapter call."""

    key = cache_key(adapter, method, payload)
    index = _ensure_index()
    return index.get(key)


def store_cached(adapter: str, method: str, payload: Dict[str, Any], result: Any) -> None:
    """Persist a cache entry for the adapter call if missing."""

    key = cache_key(adapter, method, payload)
    index = _ensure_index()
    if key in index:
        return
    entry = {"key": key, "adapter": adapter, "method": method, "payload": payload, "value": result}
    with _CACHE_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    index[key] = result
