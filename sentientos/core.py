"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from dataclasses import dataclass


@dataclass
class Core:
    """Simple core object for SentientOS."""

    name: str

    def greet(self) -> str:
        """Return a greeting message."""
        return f"Hello from {self.name}"
