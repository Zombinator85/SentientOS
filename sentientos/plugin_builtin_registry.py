"""Static registry for repository-owned plugin-framework built-ins.

This module is intentionally source-explicit.  It is not an extension discovery
mechanism and no environment or filesystem input can add to this set.
"""

from __future__ import annotations

from typing import Any, Callable


BUILTIN_PLUGIN_NAMES = ("wave_hand",)


def register_repository_builtins(register_plugin: Callable[[str, Any], None]) -> None:
    """Register the fixed set of repository-owned built-ins."""
    from gp_plugins.wave_hand import WaveHandPlugin

    register_plugin("wave_hand", WaveHandPlugin())
