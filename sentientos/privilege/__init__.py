"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
# Public privilege hooks for SentientOS.

from ..admin_utils import (
    is_admin,
    print_privilege_banner,
    require_admin,
    require_admin_banner,
    require_lumos_approval,
)

__all__ = [
    "is_admin",
    "print_privilege_banner",
    "require_admin_banner",
    "require_lumos_approval",
    "require_admin",
]
