"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Experimental trust scoring prototype."""

import json
import os
from datetime import datetime
from typing import Any, Dict, List

from logging_config import get_log_path
import experimental_flags as ex

LOG_PATH = get_log_path("trust_scores.jsonl", "TRUST_SCORE_LOG")


def add_score(agent: str, score: float, reason: str, *, user: str = "system") -> Dict[str, Any]:
    """Record a trust score entry if the experiment is enabled."""
    if not ex.enabled("trust_scoring"):
        return {"disabled": True}
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "agent": agent,
        "score": score,
        "reason": reason,
        "user": user,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def list_scores(limit: int = 20) -> List[Dict[str, Any]]:
    """Return the most recent trust scores."""
    if not LOG_PATH.exists() or not ex.enabled("trust_scoring"):
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(l) for l in lines[-limit:]]
