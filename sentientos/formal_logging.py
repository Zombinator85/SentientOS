from __future__ import annotations

"""Neutral formal logging helpers for audit/privilege modules.

This module is intentionally presentation-free and symbolic-free. It preserves
existing JSONL validation and healing behavior used by formal core modules.
"""

from datetime import datetime
import gzip
import json
import os
import shutil
from pathlib import Path
from typing import Any

from logging_config import get_log_path

REQUIRED_FIELDS = {"timestamp", "data"}
PUBLIC_LOG: Path = get_log_path("public_rituals.jsonl", "PUBLIC_RITUAL_LOG")
_MAX_BYTES = int(os.getenv("LOG_JSON_MAX_BYTES", "0"))


def validate_log_entry(entry: dict[str, Any]) -> None:
    """Raise ``ValueError`` if required fields are missing."""
    missing = REQUIRED_FIELDS - entry.keys()
    if missing:
        raise ValueError(f"log entry missing required fields: {', '.join(sorted(missing))}")
    if "foo" in entry:
        raise ValueError("legacy field 'foo' is not allowed")


def log_json(path: Path, obj: dict[str, Any]) -> None:
    """Append a JSON object to a JSONL log with schema healing and validation."""
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
