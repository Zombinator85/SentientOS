from logging_config import get_log_path
import json
import os
import uuid
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

LOG_PATH = get_log_path("ritual_attestations.jsonl", "RITUAL_ATTEST_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def add(event_id: str, user: str, comment: str = "", quote: str = "") -> str:
    """Record a witness attestation or comment for a ritual event."""
    entry_id = uuid.uuid4().hex[:8]
    entry = {
        "id": entry_id,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "event": event_id,
        "user": user,
        "comment": comment,
        "quote": quote,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry_id


def history(event_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Return recent attestations, optionally filtered by event."""
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    if event_id:
        lines = [ln for ln in lines if f'"event": "{event_id}"' in ln]
    lines = lines[-limit:]
    out: List[Dict[str, Any]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out
