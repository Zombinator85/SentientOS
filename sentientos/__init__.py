"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

"""SentientOS core package."""

from importlib import import_module
from typing import Any

__version__: str = "1.2.0-beta"

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


def __getattr__(name: str) -> Any:
    if name in {"Core"}:
        return getattr(import_module("sentientos.core"), name)
    if name in {"InnerWorldOrchestrator"}:
        return getattr(import_module("sentientos.innerworld"), name)
    if name in {"SentientOrchestrator"}:
        return getattr(import_module("sentientos.orchestrator"), name)
    if name in {
        "is_admin",
        "print_privilege_banner",
        "require_admin_banner",
        "require_lumos_approval",
        "require_admin",
    }:
        return getattr(import_module("sentientos.privilege"), name)
    raise AttributeError(f"module 'sentientos' has no attribute {name!r}")
