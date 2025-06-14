"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Helpers for experimental feature flags."""
import os

def enabled(name: str) -> bool:
    """Return True if ``EXPERIMENT_<NAME>`` is set to ``1``."""
    return os.getenv(f"EXPERIMENT_{name.upper()}") == "1"
