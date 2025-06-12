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

HERESY_REVIEW_LOG = get_log_path("heresy_review.jsonl", "HERESY_REVIEW_LOG")
HERESY_REVIEW_LOG.parent.mkdir(parents=True, exist_ok=True)


def log_review(heresy_ts: str, user: str, note: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "heresy_ts": heresy_ts,
        "user": user,
        "note": note,
    }
    with HERESY_REVIEW_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def reviewed_timestamps() -> set:
    if not HERESY_REVIEW_LOG.exists():
        return set()
    ts = set()
    for ln in HERESY_REVIEW_LOG.read_text(encoding="utf-8").splitlines():
        try:
            ts.add(json.loads(ln).get("heresy_ts"))
        except Exception:
            continue
    return ts
