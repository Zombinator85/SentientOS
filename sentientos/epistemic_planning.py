from __future__ import annotations

from sentientos.persistent_epistemic_state import (EpistemicCognitiveProjection,
    EpistemicStateError, semantic_packets_for_projection, validate_cognitive_projection)


class EpistemicPlanningError(ValueError):
    """A prior projection cannot safely inform a planning choice."""


def review_required_propositions(
        projection: EpistemicCognitiveProjection) -> tuple[str, frozenset[str]]:
    """Validate a semantic prior and return its digest and non-supportive positions."""
    if not isinstance(projection, EpistemicCognitiveProjection):
        raise EpistemicPlanningError("epistemic_planning_projection_invalid")
    try:
        validate_cognitive_projection(projection, require_meaning=True)
        packets = semantic_packets_for_projection(projection)
    except EpistemicStateError as exc:
        raise EpistemicPlanningError("epistemic_planning_projection_invalid") from exc
    review_ids = frozenset(
        packet["proposition"]["proposition_id"]
        for packet in packets
        if (packet["state"]["stance"] not in {"provisionally_supported", "supported"}
            or packet["state"]["dependency_unresolved"]
            or packet["state"]["freshness"] != "current"))
    return projection.projection_digest, review_ids


__all__ = ["EpistemicPlanningError", "review_required_propositions"]
