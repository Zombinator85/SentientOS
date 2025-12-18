"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
"""SentientOS core package."""

# Ensure runtime patches (e.g., pathlib append helpers) are installed early during
# package import so downstream modules and tests can rely on them.
import sitecustomize  # noqa: F401

__version__: str = "1.2.0-beta"

from .core import Core
from .innerworld import InnerWorldOrchestrator
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
    "InnerWorldOrchestrator",
    "SentientOrchestrator",
    "is_admin",
    "print_privilege_banner",
    "require_admin_banner",
    "require_lumos_approval",
    "require_admin",
]
