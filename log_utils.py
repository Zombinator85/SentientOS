from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import audit_chain


def append_json(
    path: Path,
    entry: Dict[str, Any],
    *,
    emotion: str = "neutral",
    consent: bool | str = True,
) -> None:
    """Append a JSON entry enforcing audit chain integrity."""
    path.parent.mkdir(parents=True, exist_ok=True)
    audit_chain.append_entry(path, entry, emotion=emotion, consent=consent)


def read_json(path: Path) -> List[Dict[str, Any]]:
    """Return flattened audit entries."""
    out: List[Dict[str, Any]] = []
    for e in audit_chain.read_entries(path):
        row = {"timestamp": e.timestamp, **e.data, "prev_hash": e.prev_hash, "rolling_hash": e.rolling_hash}
        out.append(row)
    return out
