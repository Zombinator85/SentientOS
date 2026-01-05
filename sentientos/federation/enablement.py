"""Explicit federation enablement signal."""

from __future__ import annotations

import os

ENABLEMENT_ENV = "SENTIENTOS_FEDERATION_ENABLED"


def is_enabled() -> bool:
    """Return True when federation is explicitly enabled."""
    value = os.getenv(ENABLEMENT_ENV, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


__all__ = ["ENABLEMENT_ENV", "is_enabled"]
