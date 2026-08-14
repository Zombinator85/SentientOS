"""Compatibility bus for deliberately admitted, in-memory GUI extensions.

Filesystem discovery and live Python reload were retired because a pathname is
not executable authority.  The legacy loading methods remain as inert
compatibility surfaces; callers must explicitly register an already-created
object.
"""
from __future__ import annotations

from typing import Any

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from gui_stub import CathedralGUI


class PluginBus:
    """Collect already-admitted GUI extensions without loading source."""

    def __init__(self, gui: CathedralGUI, directory: str = "plugins") -> None:
        self.gui = gui
        # Retained only so compatibility callers can inspect their configuration.
        # It is never created, read, watched, or treated as authority.
        self.directory = directory
        self.modules: dict[str, Any] = {}

    def register(self, name: str, plugin: Any) -> None:
        """Register an already-constructed internal object."""
        self.modules[name] = plugin
        refresh = getattr(self.gui, "refresh_plugins", None)
        if callable(refresh):
            refresh()

    def load(self, name: str) -> None:
        """Do nothing: loading caller-selected source is unsupported."""

    def load_all(self) -> None:
        """Do nothing: directory discovery is unsupported."""

    async def watch_plugins(self) -> None:
        """Do nothing: live Python reload is unsupported."""
