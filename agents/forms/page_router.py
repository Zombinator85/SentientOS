"""Logical routing for SSA disability form pages."""
from __future__ import annotations

from typing import List, Optional

PAGE_FLOW: List[str] = [
    "login",
    "contact_info",
    "conditions",
    "work_history",
]


def next_page(current: str) -> Optional[str]:
    """Return the next page in the logical flow or ``None`` if terminal."""
    try:
        index = PAGE_FLOW.index(current)
    except ValueError:
        return None

    next_index = index + 1
    if next_index < len(PAGE_FLOW):
        return PAGE_FLOW[next_index]
    return None


def page_index(page: str) -> int:
    """Return the position of ``page`` within ``PAGE_FLOW`` or ``-1`` if missing."""
    try:
        return PAGE_FLOW.index(page)
    except ValueError:
        return -1
