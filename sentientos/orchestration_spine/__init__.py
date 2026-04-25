from __future__ import annotations

"""Bounded orchestration-spine package.

Boundary ownership:
- ``projection/*`` owns observational/derived projection logic only.
- ``adapters/*`` owns substrate-specific helper logic only.
- authority kernel ownership remains in ``sentientos.orchestration_intent_fabric``.

Dependency direction is intentionally one-way:
``orchestration_intent_fabric -> orchestration_spine.(projection|adapters)``.
Projection and adapter modules must not become new authority or truth sources.
"""

__all__ = ["projection", "adapters"]
