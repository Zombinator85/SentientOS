"""Public ritual boundary façade.

This module exposes a narrow API for expressive ritual surfaces that need
relationship timeline and attestation access while avoiding direct coupling to
formal ritual internals.
"""
from __future__ import annotations

from typing import Any

import attestation
import relationship_log


def add_attestation(event_id: str, user: str, comment: str = "", quote: str = "") -> str:
    """Delegate witness attestation writes to canonical attestation storage."""
    return attestation.add(event_id, user, comment=comment, quote=quote)


def ritual_events_history(user: str | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
    """Return ritual relationship history from canonical relationship log."""
    return relationship_log.history(user, limit=limit)


def ritual_attestations_history(event_id: str | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
    """Return ritual attestation history from canonical attestation log."""
    return attestation.history(event_id, limit=limit)


__all__ = [
    "add_attestation",
    "ritual_events_history",
    "ritual_attestations_history",
]
