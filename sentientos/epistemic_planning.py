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
    """Return applicability scopes with exact state, event, and outcome identities."""
    if not isinstance(projection, EpistemicCognitiveProjection):
        raise EpistemicPlanningError("epistemic_planning_projection_invalid")
    try:
        validate_cognitive_projection(projection, require_meaning=True)
        packets = semantic_packets_for_projection(projection)
    except EpistemicStateError as exc:
        raise EpistemicPlanningError("epistemic_planning_projection_invalid") from exc
    review_scopes: dict[str, dict[str, object]] = {}
    for packet in packets:
        state = packet["state"]
        if (state["stance"] in {"provisionally_supported", "supported"}
                and not state["dependency_unresolved"]
                and state["freshness"] == "current"):
            continue
        proposition_id = packet["proposition"]["proposition_id"]
        scope = dict(packet["proposition"].get("context_scope", {}))
        scope["position_identity"] = {
            "schema_version": "sentientos.epistemic_review_position_identity:v1",
            "state_id": state["state_id"],
            "state_digest": state["state_digest"],
            "generation": state["generation"],
            "update_event_id": packet["last_update_event"]["event_id"],
            "supporting_binding_ids": list(packet["supporting_evidence"]),
            "contradicting_binding_ids": list(packet["contradicting_evidence"]),
        }
        review_scopes[proposition_id] = scope
    omission_manifest = getattr(projection, "omission_manifest", None)
    if omission_manifest is not None:
        for omitted in omission_manifest.get("omitted_state_identities", ()):
            proposition_id = omitted.get("proposition_id")
            if not isinstance(proposition_id, str) or not proposition_id:
                raise EpistemicPlanningError("epistemic_planning_omission_identity_invalid")
            if proposition_id in review_scopes:
                raise EpistemicPlanningError("epistemic_planning_omission_identity_collision")
            review_scopes[proposition_id] = {
                "omitted_from_prior_projection": True,
                "omitted_state_identity": dict(omitted),
            }
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
        if scope.get("omitted_from_prior_projection") is True:
            return "epistemic_applicability_unresolved"
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
