"""Cycle-safe privilege hooks for the SentientOS test suite."""
from __future__ import annotations

"""Cycle-safe privilege hooks.

These wrappers import the actual helpers from :mod:`admin_utils` at call-time,
preventing circular-import errors while satisfying static references.
"""

from functools import wraps
from typing import Any, Callable

__all__ = ["require_admin_banner", "require_lumos_approval"]


def _lazy(attr_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Load the real helper from ``admin_utils`` only when called."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            from . import admin_utils
            real = getattr(admin_utils, attr_name)
            return real(*args, **kwargs)

        return wrapper

    return decorator


@_lazy("require_admin_banner")
def require_admin_banner() -> None:
    """Ensure the admin banner has been acknowledged."""
    return None


@_lazy("require_lumos_approval")
def require_lumos_approval() -> None:
    """Require Lumos approval for privileged actions."""
    return None
