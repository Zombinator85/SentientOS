"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import json
import os
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Dict

LOG_PATH = get_log_path("music_log.jsonl")


def digest_week() -> Dict[str, float]:
    cutoff = datetime.utcnow() - timedelta(days=7)
    counts: Dict[str, float] = {}
    if LOG_PATH.exists():
        for ln in LOG_PATH.read_text(encoding="utf-8").splitlines():
            try:
                data = json.loads(ln)
            except Exception:
                continue
            ts = data.get("timestamp")
            if not ts or datetime.fromisoformat(ts) < cutoff:
                continue
            for k, v in (data.get("emotion", {}).get("reported") or {}).items():
                counts[k] = counts.get(k, 0.0) + v
    return counts


if __name__ == "__main__":
    res = digest_week()
    print(json.dumps(res, indent=2))
