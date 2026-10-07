"""Library-friendly exports for :mod:`privilege_lint`."""
from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "audit_use",
    "BANNER_ASCII",
    "DEFAULT_BANNER_ASCII",
    "FUTURE_IMPORT",
    "PrivilegeLinter",
    "main",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    cli = import_module("privilege_lint_cli")
    value = getattr(cli, name)
    globals()[name] = value
    return value
