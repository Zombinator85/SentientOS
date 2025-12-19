"""Affective context contract and telemetry overlays for SentientOS.

This module formalises affective context as continuous, bounded telemetry. It
does not introduce new emotions or alter policy, permissions, or action
selection. Overlays are descriptive only and decay over time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import time
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional

import emotion_memory as em
from emotions import EMOTIONS, Emotion, empty_emotion_vector

AFFECTIVE_CONTEXT_CONTRACT_VERSION = "1.0"
"""Versioned contract identifier for affective overlays."""

_REGISTRY_LIMIT = 50
_registry: List[Dict[str, Any]] = []


def _bounded_vector(vector: Mapping[str, float]) -> Emotion:
    bounded = empty_emotion_vector()
    for label in EMOTIONS:
        raw = float(vector.get(label, 0.0))
        bounded[label] = max(0.0, min(1.0, raw))
    return bounded


@dataclass
class AffectiveOverlay:
    """Immutable affective overlay payload."""

    version: str
    vector: Emotion
    reason: str
    bounds: Mapping[str, float]
    decay_seconds: float
    timestamp: float

    def to_payload(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["vector"] = dict(self.vector)
        payload["bounds"] = dict(self.bounds)
        return payload


def capture_affective_context(
    reason: str,
    *,
    overlay: Optional[Mapping[str, float]] = None,
    decay_seconds: float = 30.0,
) -> Dict[str, Any]:
    """Capture a bounded affective overlay for telemetry.

    The overlay always uses a full emotion vector, clamps values to [0, 1], and
    annotates the reason and decay horizon. It coexists with uncertainty or
    learning signals but is never consulted for policy or permissions.
    """

    base = em.average_emotion()
    combined: MutableMapping[str, float] = {**base}
    if overlay:
        combined.update({k: float(v) for k, v in overlay.items()})

    bounded = _bounded_vector(combined)
    overlay_payload = AffectiveOverlay(
        version=AFFECTIVE_CONTEXT_CONTRACT_VERSION,
        vector=bounded,
        reason=str(reason),
        bounds={"min": 0.0, "max": 1.0},
        decay_seconds=float(decay_seconds),
        timestamp=time.time(),
    )
    return overlay_payload.to_payload()


def annotate_payload(
    payload: Mapping[str, Any],
    *,
    reason: str,
    overlay: Optional[Mapping[str, float]] = None,
    decay_seconds: float = 30.0,
) -> Dict[str, Any]:
    """Attach affective context to a payload without altering semantics."""

    affective_context = capture_affective_context(
        reason, overlay=overlay, decay_seconds=decay_seconds
    )
    enriched = {**payload, "affective_context": affective_context}
    return enriched


def require_affective_context(container: Mapping[str, Any]) -> None:
    """Assert that ``container`` carries a compliant affective context."""

    ctx = container.get("affective_context")
    if not isinstance(ctx, Mapping):
        raise AssertionError("affective_context missing; affect-free execution is disallowed")
    if ctx.get("version") != AFFECTIVE_CONTEXT_CONTRACT_VERSION:
        raise AssertionError("affective_context version mismatch")
    vector = ctx.get("vector")
    if not isinstance(vector, Mapping) or not vector:
        raise AssertionError("affective_context vector missing")
    if not ctx.get("reason"):
        raise AssertionError("affective_context must be reason-coded")
    bounds = ctx.get("bounds") or {}
    lower = float(bounds.get("min", 0.0))
    upper = float(bounds.get("max", 1.0))
    for value in vector.values():
        if not (lower <= float(value) <= upper):
            raise AssertionError("affective_context values must be bounded")
    decay_seconds = ctx.get("decay_seconds")
    if decay_seconds is None or float(decay_seconds) <= 0:
        raise AssertionError("affective_context must be decayable")


def register_context(
    actor: str,
    context: Mapping[str, Any],
    *,
    metadata: Optional[Mapping[str, Any]] = None,
) -> None:
    """Persist a contextual overlay for auditing purposes.

    The registry is capped to avoid unbounded growth and is telemetry-only; it
    must not be read by policy or execution paths.
    """

    entry = {
        "actor": actor,
        "affective_context": dict(context),
        "metadata": dict(metadata or {}),
        "recorded_at": time.time(),
    }
    _registry.append(entry)
    if len(_registry) > _REGISTRY_LIMIT:
        del _registry[:-_REGISTRY_LIMIT]


def recent_context(limit: int = 5) -> List[Dict[str, Any]]:
    """Return the most recent recorded affective contexts."""

    if limit <= 0:
        return []
    return list(_registry[-limit:])


def clear_registry() -> None:
    """Clear recorded affective overlays (intended for tests)."""

    _registry.clear()

