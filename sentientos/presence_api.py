from __future__ import annotations

"""Neutral presence read helpers for formal-core consumers.

This module provides read-only accessors that preserve existing presence ledger
record shapes while keeping formal modules free of presentation/symbolic imports.
"""

import json
from pathlib import Path
from typing import Any

from logging_config import get_log_path


def _presence_ledger_path() -> Path:
    return get_log_path("user_presence.jsonl", "USER_PRESENCE_LOG")


def recent_privilege_attempts(limit: int = 5) -> list[dict[str, Any]]:
    """Return the most recent privilege-check entries from the presence ledger."""
    ledger_path = _presence_ledger_path()
    if not ledger_path.exists():
        return []
    lines = reversed(ledger_path.read_text(encoding="utf-8").splitlines())
    out: list[dict[str, Any]] = []
    for line in lines:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("event") == "admin_privilege_check":
            out.append(obj)
            if len(out) == limit:
                break
    return list(reversed(out))
