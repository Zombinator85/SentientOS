"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict

LOG_PATH = get_log_path("headless_actions.jsonl", "HEADLESS_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_skip(event: str, reason: str) -> None:
    entry = {
        "time": datetime.utcnow().isoformat(),
        "event": event,
        "reason": reason,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def review_pending() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    LOG_PATH.write_text("", encoding="utf-8")
    out: List[Dict[str, str]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out
