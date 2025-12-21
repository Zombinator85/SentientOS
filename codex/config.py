"""Configuration flags for Codex runtime behaviors."""
from __future__ import annotations

import os


def _flag_enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


# Single, explicit wet-run toggle for Codex workflows.
WET_RUN_ENABLED = _flag_enabled(os.getenv("CODEX_WET_RUN"))

__all__ = ["WET_RUN_ENABLED"]
