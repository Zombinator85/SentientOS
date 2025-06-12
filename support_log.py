"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
from pathlib import Path
import ledger

LOG_PATH = get_log_path("support_log.jsonl")


def add(name: str, message: str, amount: str = "") -> dict[str, str]:
    """Record a supporter blessing in the living ledger."""
    return ledger.log_support(name, message, amount)
