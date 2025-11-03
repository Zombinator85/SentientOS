"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
"""SentientOS core package."""

__version__: str = "1.1.0-alpha"

from .core import Core
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
    "is_admin",
    "print_privilege_banner",
    "require_admin_banner",
    "require_lumos_approval",
    "require_admin",
]
