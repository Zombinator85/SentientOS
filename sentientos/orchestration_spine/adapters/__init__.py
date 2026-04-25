from __future__ import annotations

"""Substrate-specific helpers consumed by the orchestration kernel/facade.

Adapter modules can shape calls into concrete substrates, but they do not own
orchestration authority policy, lifecycle closure semantics, or new truth sources.
"""

from . import internal_maintenance

__all__ = ["internal_maintenance"]
