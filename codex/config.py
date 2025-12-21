"""Configuration flags for Codex runtime behaviors."""
from __future__ import annotations

# Wet run is opt-in only; default to False unless explicitly set by callers.
WET_RUN_ENABLED = False

__all__ = ["WET_RUN_ENABLED"]
