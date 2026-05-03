from __future__ import annotations

"""Observational projection helpers for orchestration.

These modules derive summaries/recommendations from already-materialized
orchestration evidence. They must not own admission authority, execution routing,
or canonical lifecycle truth.

Projection family inventory (documentation-only):
- ``current_state`` current-state/current-brief projections, including current
  picture compression plus export/receipt/acceptance projections.
- ``policy_helpers`` policy/recommendation projections that derive bounded
  guidance from kernel-supplied review surfaces.
"""

from . import current_state, policy_helpers
from .current_state import (
    build_current_orchestration_diagnostic_summary_projection,
    resolve_current_orchestration_bundle_projection,
)

PROJECTION_FAMILY_CURRENT_STATE = "current_state"
PROJECTION_FAMILY_POLICY = "policy"
PROJECTION_FAMILIES = (
    PROJECTION_FAMILY_CURRENT_STATE,
    PROJECTION_FAMILY_POLICY,
)

__all__ = [
    "current_state",
    "policy_helpers",
    "PROJECTION_FAMILY_CURRENT_STATE",
    "PROJECTION_FAMILY_POLICY",
    "PROJECTION_FAMILIES",
    "resolve_current_orchestration_bundle_projection",
    "build_current_orchestration_diagnostic_summary_projection",
]
