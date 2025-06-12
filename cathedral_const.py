from __future__ import annotations

from pathlib import Path
import json
from datetime import datetime
from typing import Any, Dict
import os
import gzip
import shutil

from logging_config import get_log_path

REQUIRED_FIELDS = {"timestamp", "data"}


def validate_log_entry(entry: Dict[str, Any]) -> None:
    """Raise ``ValueError`` if required fields are missing."""
    missing = REQUIRED_FIELDS - entry.keys()
    if missing:
        raise ValueError(f"log entry missing required fields: {', '.join(sorted(missing))}")
    if "foo" in entry:
        raise ValueError("legacy field 'foo' is not allowed")

# Shared constants for logs and lightweight utilities
PUBLIC_LOG: Path = get_log_path("public_rituals.jsonl", "PUBLIC_RITUAL_LOG")

# Optional size-based rotation for ``log_json``.
_MAX_BYTES = int(os.getenv("LOG_JSON_MAX_BYTES", "0"))


def log_json(path: Path, obj: Dict[str, Any]) -> None:
    """Append a JSON object to the given log path.

    Missing fields are healed automatically to satisfy audit schema:
    - ``timestamp`` will be added with ``datetime.utcnow().isoformat()`` if absent.
    - ``data`` will be added as an empty object if absent.
    - the legacy field ``foo`` is stripped if present.
    """
    if "timestamp" not in obj:
        obj["timestamp"] = datetime.utcnow().isoformat()
    if "data" not in obj:
        obj["data"] = {}
    obj.pop("foo", None)
    validate_log_entry(obj)
    path.parent.mkdir(parents=True, exist_ok=True)
    if _MAX_BYTES and path.exists() and path.stat().st_size >= _MAX_BYTES:
        rotated = path.with_suffix(path.suffix + ".1.gz")
        with path.open("rb") as src, gzip.open(rotated, "wb") as dst:
            shutil.copyfileobj(src, dst)
        path.unlink()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")
