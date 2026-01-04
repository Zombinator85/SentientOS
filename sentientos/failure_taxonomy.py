"""Named, read-only failure taxonomy for attribution-only references."""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

_FAILURE_TAXONOMY: Mapping[str, str] = MappingProxyType(
    {
        "catastrophic": "Irreversible harm, integrity loss, or unsafe shutdown risk.",
        "integrity_risk": "Potential audit or data integrity compromise needing review.",
        "recoverable": "Failure that can be remediated without lasting degradation.",
        "quarantined": "Isolated failure retained for inspection before clearance.",
        "informational": "Non-blocking signal recorded for observability only.",
    }
)


def failure_taxonomy() -> Mapping[str, str]:
    """Return the immutable failure taxonomy."""

    return _FAILURE_TAXONOMY


def failure_taxonomy_reference() -> tuple[str, ...]:
    """Return deterministic taxonomy identifiers for attribution-only use."""

    return tuple(sorted(_FAILURE_TAXONOMY.keys()))


__all__ = ["failure_taxonomy", "failure_taxonomy_reference"]
