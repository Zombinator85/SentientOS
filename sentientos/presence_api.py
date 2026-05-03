from __future__ import annotations

"""Neutral presence façade helpers for canonical presence ledger access.

This module exposes narrow, boundary-safe helpers so formal/core, world, and UI
callers can consume canonical presence behavior without importing
``presence_ledger`` directly.
"""

import importlib
import json
from pathlib import Path
from typing import Any

from logging_config import get_log_path


def _presence_ledger_path() -> Path:
    return get_log_path("user_presence.jsonl", "USER_PRESENCE_LOG")


def _presence_ledger_module() -> Any:
    """Load the canonical presence ledger module lazily."""
    return importlib.import_module("presence_ledger")


def recent_privilege_attempts(limit: int = 5) -> list[dict[str, Any]]:
    """Return recent privilege-check entries with canonical record shape."""
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


def append_presence_event(user: str, event: str, note: str = "") -> None:
    """Append a canonical presence event via presence_ledger.log()."""
    _presence_ledger_module().log(user, event, note)
