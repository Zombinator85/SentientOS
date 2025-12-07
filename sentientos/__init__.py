"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
"""SentientOS core package."""

__version__: str = "1.2.0-beta"

from .core import Core
from .orchestrator import SentientOrchestrator
from .privilege import (
    is_admin,
    print_privilege_banner,
    require_admin_banner,
    require_lumos_approval,
    require_admin,
)

__all__ = [
    "__version__",
    "Core",
    "SentientOrchestrator",
    "is_admin",
    "print_privilege_banner",
    "require_admin_banner",
    "require_lumos_approval",
    "require_admin",
]
