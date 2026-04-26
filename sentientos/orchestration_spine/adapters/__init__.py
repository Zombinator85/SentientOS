from __future__ import annotations

"""Substrate-specific helpers consumed by the orchestration kernel/facade.

Adapter modules can shape calls into concrete substrates, but they do not own
orchestration authority policy, lifecycle closure semantics, or new truth sources.

Adapter family inventory (documentation-only):
- ``internal_maintenance`` substrate handoff helpers for internal-maintenance
  execution through ``task_admission``/``task_executor`` surfaces.

Kernel/facade ownership remains canonical for identity/linkage/legality/closure
meaning; adapters only normalize and relay substrate-local evidence.
"""

from . import internal_maintenance

ADAPTER_FAMILY_INTERNAL_MAINTENANCE = "internal_maintenance"
ADAPTER_FAMILIES = (ADAPTER_FAMILY_INTERNAL_MAINTENANCE,)

__all__ = [
    "internal_maintenance",
    "ADAPTER_FAMILY_INTERNAL_MAINTENANCE",
    "ADAPTER_FAMILIES",
]
