"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
"""Anniversary notifier that logs cathedral anniversaries."""

from logging_config import get_log_path
import os
import json
import datetime

from cathedral_const import log_json
from pathlib import Path
from sentientos.privilege import require_admin_banner, require_lumos_approval


ANNIVERSARY = os.getenv("CATHEDRAL_BIRTH", "2023-01-01")
LOG_FILE = get_log_path("anniversary_log.jsonl")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def check_and_log() -> None:
    today = datetime.date.today().isoformat()[5:]
    ann = ANNIVERSARY[5:]
    if today == ann:
        entry = {"event": "anniversary", "message": "Presence recap"}
        log_json(LOG_FILE, {"timestamp": datetime.datetime.utcnow().isoformat(), "data": entry})
        print("Anniversary blessing recorded")


if __name__ == "__main__":  # pragma: no cover - manual
    check_and_log()
