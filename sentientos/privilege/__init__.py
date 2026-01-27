"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
# Public privilege hooks for SentientOS.

from ..admin_utils import (
    is_admin,
    print_privilege_banner,
    require_admin,
    require_admin_banner,
    require_covenant_alignment,
    require_lumos_approval,
)


def enforce_privilege() -> None:
    """Run privilege gates for explicit runtime entrypoints."""
    require_admin_banner()
    require_lumos_approval()


__all__ = [
    "is_admin",
    "enforce_privilege",
    "print_privilege_banner",
    "require_admin_banner",
    "require_covenant_alignment",
    "require_lumos_approval",
    "require_admin",
]
