from logging_config import get_log_path
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

LOG_PATH = get_log_path("confessional_log.jsonl", "CONFESSIONAL_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_confession(
    subsystem: str,
    event: str,
    detail: str,
    *,
    tags: List[str] | None = None,
    reflection: str = "",
    severity: str = "info",
    links: List[str] | None = None,
    ) -> Dict[str, Any]:
    """Record a red-flag confession entry."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "subsystem": subsystem,
        "event": event,
        "detail": detail,
        "tags": tags or [],
        "reflection": reflection,
        "severity": severity,
        "links": links or [],
        "council_required": severity == "critical",
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def tail(limit: int = 20) -> List[Dict[str, Any]]:
    """Return the most recent confessions."""
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    out: List[Dict[str, Any]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def search(term: str) -> List[Dict[str, Any]]:
    """Search confessions containing ``term``."""
    if not LOG_PATH.exists():
        return []
    out = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if term.lower() in ln.lower():
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    return out
