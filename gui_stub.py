"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from typing import Any, List


class CathedralGUI:
    """Minimal stub GUI used by plugins."""

    def __init__(self) -> None:
        self.panels: List[Any] = []

    def add_panel(self, panel: Any) -> None:
        """Register a new panel widget."""
        self.panels.append(panel)

    def update(self) -> None:  # Flet compatible
        """Trigger UI update."""
        pass

    def refresh(self) -> None:  # PySide compatible
        """Refresh stacked widget."""
        self.update()
