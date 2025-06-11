from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Banner: This script requires admin & Lumos approval."""

require_admin_banner()
require_lumos_approval()

import os


def is_auto_approve() -> bool:
    """Return True if auto-approval is enabled via environment."""
    return os.getenv("LUMOS_AUTO_APPROVE", "") == "1"


def prompt_yes_no(prompt: str) -> bool:
    """Prompt the user for yes/no unless auto-approval is enabled."""
    if is_auto_approve():
        return True
    return input(f"{prompt} [y/N]: ").lower().startswith("y")
