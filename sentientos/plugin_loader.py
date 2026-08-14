"""Fail-closed compatibility surfaces for the retired external plugin loader.

Neither files in a configured directory nor installed distribution metadata
are inspected or executed.  Repository-owned plugin-framework built-ins are a
separate boundary managed by :mod:`sentientos.plugin_builtin_registry`.
"""
from __future__ import annotations

import argparse
from types import ModuleType
from typing import Any, Iterable

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from gui_stub import CathedralGUI

RETIRED_MESSAGE = "External Python extension activation is unsupported."


class PluginBus:
    """Narrow bus for already-admitted, in-memory objects."""

    def __init__(self) -> None:
        self.plugins: dict[str, Any] = {}

    def register(self, name: str, plugin: Any) -> None:
        self.plugins[name] = plugin


class PluginLoader:
    """Inert compatibility object that never examines its configured directory."""

    def __init__(self, gui: CathedralGUI, directory: str = "plugins") -> None:
        self.gui = gui
        self.directory = directory
        self.bus = PluginBus()
        self.modules: dict[str, ModuleType] = {}
        self.errors: dict[str, str] = {}
        self.observer = None

    def stop(self) -> None:
        """Compatibility no-op; no observer is started."""

    def _start(self) -> None:
        """Compatibility no-op; external activation remains retired."""

    def _load_existing(self) -> None:
        """Compatibility no-op; directory contents are not inspected."""

    def _load_plugin(self, name: str) -> None:
        """Compatibility no-op; a caller-supplied name grants no authority."""

    def _handle(self, event: object) -> None:
        """Compatibility no-op; filesystem events have no executable effect."""

    def _refresh(self) -> None:
        refresh = getattr(self.gui, "update", None) or getattr(self.gui, "refresh", None)
        if callable(refresh):
            refresh()

    def active_plugins(self) -> list[str]:
        return []

    def error_log(self) -> dict[str, str]:
        return {}

    def set_trusted_only(self, value: bool) -> None:
        """Retired compatibility no-op; TRUSTED never governed execution."""


class PluginPanel:
    """Read-only compatibility panel describing the retired mechanism."""

    def __init__(self, loader: PluginLoader) -> None:
        self.loader = loader
        self.gui = loader.gui
        self.control: object = RETIRED_MESSAGE

    def refresh(self) -> None:
        self.loader._refresh()


def load_plugins(bus: PluginBus, *, load: bool = True) -> Iterable[str]:
    """Return no external plugins without enumerating distribution metadata."""
    return ()


def main(argv: list[str] | None = None) -> None:
    """Report the deterministic retired status; never activate Python."""
    parser = argparse.ArgumentParser(description="SentientOS retired plugin loader")
    parser.add_argument("--list", action="store_true", help="Show external plugin status")
    parser.parse_args(argv)
    print(RETIRED_MESSAGE)


if __name__ == "__main__":  # pragma: no cover
    main()
