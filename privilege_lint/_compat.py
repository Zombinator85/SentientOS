from __future__ import annotations

import importlib
import types
import warnings


class RuleSkippedError(Exception):
    """Raised when an optional lint rule is skipped."""


def safe_import(name: str, stub: dict[str, object] | None = None) -> object:
    """Import ``name`` if available, otherwise return a stub module."""
    try:
        return importlib.import_module(name)
    except Exception:
        warnings.warn(f"optional module {name} missing; using stub", RuntimeWarning)
        return types.SimpleNamespace(**(stub or {}))

