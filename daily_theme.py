"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import json
import os
import random
from datetime import datetime
from pathlib import Path

THEME_LOG = get_log_path("daily_theme.jsonl", "DAILY_THEME_LOG")
THEME_LOG.parent.mkdir(parents=True, exist_ok=True)

THEMES = [
    "Courage in kindness",
    "Quiet reflection",
    "Shared growth",
    "Open hearts",
    "Joyful presence",
]


def _last_entry() -> dict | None:
    if not THEME_LOG.exists():
        return None
    for line in reversed(THEME_LOG.read_text(encoding="utf-8").splitlines()):
        try:
            return json.loads(line)
        except Exception:
            continue
    return None


def generate() -> str:
    """Generate today's theme if not already generated."""
    today = datetime.utcnow().date().isoformat()
    last = _last_entry()
    if last and str(last.get("timestamp", "")).startswith(today):
        return last.get("theme", "")
    theme = random.choice(THEMES)
    entry = {"timestamp": datetime.utcnow().isoformat(), "theme": theme}
    with open(THEME_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return theme


def latest() -> str | None:
    entry = _last_entry()
    return entry.get("theme") if entry else None
