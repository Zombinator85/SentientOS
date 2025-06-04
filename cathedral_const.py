from __future__ import annotations

from pathlib import Path
import json
from datetime import datetime
from typing import Any, Dict

from logging_config import get_log_path

# Shared constants for logs and lightweight utilities
PUBLIC_LOG: Path = get_log_path("public_rituals.jsonl", "PUBLIC_RITUAL_LOG")


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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")
