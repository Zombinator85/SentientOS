from __future__ import annotations

"""Bounded orchestration-spine package.

This package clarifies orchestration-internal module boundaries:
- projection/* for current-state and policy projection helpers
- adapters/* for orchestration-internal adapter glue
"""

__all__ = ["projection", "adapters"]
