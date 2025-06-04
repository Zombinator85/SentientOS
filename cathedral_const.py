from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Dict

from logging_config import get_log_path

# Shared constants for logs and lightweight utilities
PUBLIC_LOG: Path = get_log_path("public_rituals.jsonl", "PUBLIC_RITUAL_LOG")


def log_json(path: Path, obj: Dict[str, Any]) -> None:
    """Append a JSON object to the given log path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")
