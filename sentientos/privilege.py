"""Cycle-safe privilege hooks.

These wrappers import the actual helpers from admin_utils at call-time,
preventing circular-import errors while satisfying static references.
"""

from functools import wraps


def _lazy(attr_name: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            from admin_utils import require_admin_banner, require_lumos_approval
            real = require_admin_banner if attr_name == "require_admin_banner" else require_lumos_approval
            return real(*args, **kwargs)
        return wrapper
    return decorator


@_lazy("require_admin_banner")
def require_admin_banner() -> None:
    """Ensure admin banner has been acknowledged."""
    return None


@_lazy("require_lumos_approval")
def require_lumos_approval() -> None:
    """Require Lumos approval for privileged actions."""
    return None
