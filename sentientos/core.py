from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Core:
    """Simple core object for SentientOS."""

    name: str

    def greet(self) -> str:
        """Return a greeting message."""
        return f"Hello from {self.name}"
