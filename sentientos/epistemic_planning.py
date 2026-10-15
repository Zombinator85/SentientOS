from __future__ import annotations

from collections.abc import Mapping, Sequence

from sentientos.persistent_epistemic_state import (EpistemicCognitiveProjection,
    EpistemicStateError, semantic_packets_for_projection, validate_cognitive_projection)


class EpistemicPlanningError(ValueError):
    """A prior projection cannot safely inform a planning choice."""


def review_required_propositions(
        projection: EpistemicCognitiveProjection) -> tuple[str, frozenset[str]]:
    """Validate a semantic prior and return its digest and non-supportive positions."""
    digest, scopes = review_required_applicability(projection)
    return digest, frozenset(scopes)


def review_required_applicability(
        projection: EpistemicCognitiveProjection) -> tuple[str, dict[str, dict[str, object]]]:
    """Return review positions with their exact declared applicability scopes."""
    if not isinstance(projection, EpistemicCognitiveProjection):
        raise EpistemicPlanningError("epistemic_planning_projection_invalid")
    try:
        validate_cognitive_projection(projection, require_meaning=True)
        packets = semantic_packets_for_projection(projection)
    except EpistemicStateError as exc:
        raise EpistemicPlanningError("epistemic_planning_projection_invalid") from exc
    review_scopes = {
        packet["proposition"]["proposition_id"]: dict(packet["proposition"].get(
            "context_scope", {}))
        for packet in packets
        if (packet["state"]["stance"] not in {"provisionally_supported", "supported"}
            or packet["state"]["dependency_unresolved"]
            or packet["state"]["freshness"] != "current")}
    return projection.projection_digest, review_scopes


def epistemic_review_reason_for_goal(tags: Sequence[str],
        review_scopes: Mapping[str, Mapping[str, object]], *,
        target_active_model_identity_digest: str | None = None,
        target_identity_observed_at: str | None = None,
        planning_time: str | None = None) -> str | None:
    """Require explicit family/model applicability before a goal can consume a reviewed position."""
    tag_set = set(tags)
    for proposition_id, scope in review_scopes.items():
        if f"epistemic_proposition:{proposition_id}" not in tag_set:
            continue
        family_id = scope.get("task_family_id")
        identity_digest = scope.get("active_model_identity_digest")
        if family_id is not None:
            if not isinstance(family_id, str) or not family_id:
                return "epistemic_applicability_unresolved"
            if f"epistemic_task_family:{family_id}" not in tag_set:
                return "epistemic_applicability_unresolved"
            if (not isinstance(identity_digest, str) or len(identity_digest) != 71
                    or not identity_digest.startswith("sha256:")
                    or any(character not in "0123456789abcdef" for character in identity_digest[7:])):
                return "epistemic_applicability_unresolved"
            if (not isinstance(target_active_model_identity_digest, str)
                    or target_active_model_identity_digest != identity_digest
                    or not isinstance(target_identity_observed_at, str)
                    or target_identity_observed_at != planning_time):
                return "epistemic_applicability_unresolved"
        if identity_digest is not None:
            if (not isinstance(identity_digest, str) or len(identity_digest) != 71
                    or not identity_digest.startswith("sha256:")
                    or any(character not in "0123456789abcdef" for character in identity_digest[7:])
                    or target_active_model_identity_digest != identity_digest
                    or not isinstance(target_identity_observed_at, str)
                    or target_identity_observed_at != planning_time):
                return "epistemic_applicability_unresolved"
        return "epistemic_review_required"
    return None


__all__ = ["EpistemicPlanningError", "epistemic_review_reason_for_goal",
    "review_required_applicability", "review_required_propositions"]
