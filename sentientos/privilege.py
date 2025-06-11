"""Privilege hooks — enforced by Sanctuary Doctrine.

These wrappers lazily import the real admin_utils helpers at call-time,
eliminating circular-import issues while satisfying static references.
"""

def require_admin_banner() -> None:  # pragma: no cover
    from admin_utils import require_admin_banner as _real
    _real()


def require_lumos_approval() -> None:  # pragma: no cover
    from admin_utils import require_lumos_approval as _real
    _real()
