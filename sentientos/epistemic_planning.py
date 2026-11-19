from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

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
        projection: EpistemicCognitiveProjection, *,
        evaluation_time: str | None = None
        ) -> tuple[str, dict[str, dict[str, object]]]:
    """Return applicability scopes with exact state, event, and outcome identities."""
    if not isinstance(projection, EpistemicCognitiveProjection):
        raise EpistemicPlanningError("epistemic_planning_projection_invalid")
    try:
        validate_cognitive_projection(projection, require_meaning=True)
        packets = semantic_packets_for_projection(projection)
    except EpistemicStateError as exc:
        raise EpistemicPlanningError("epistemic_planning_projection_invalid") from exc
    relation_review_digests: dict[str, set[str]] = {}
    for packet in packets:
        for relation in packet.get("proposition_relations", ()):
            relation_kind = relation.get("relation")
            source_id = relation.get("source_proposition_id")
            target_id = relation.get("target_proposition_id")
            relation_digest = relation.get("relation_digest")
            affected_ids = (() if relation_kind not in {"contradicts", "supersedes"}
                else (source_id, target_id) if relation_kind == "contradicts"
                else (target_id,))
            for proposition_id in affected_ids:
                if isinstance(proposition_id, str):
                    relation_review_digests.setdefault(proposition_id, set()).add(
                        str(relation_digest))
    review_scopes: dict[str, dict[str, object]] = {}
    for packet in packets:
        state = packet["state"]
        proposition_id = packet["proposition"]["proposition_id"]
        scope = dict(packet["proposition"].get("context_scope", {}))
        temporal_freshness = temporal_freshness_review(
            packet, evaluation_time=evaluation_time)
        relation_digests = sorted(relation_review_digests.get(proposition_id, ()))
        correction_binding_ids = sorted({
            item["binding_id"] for item in packet.get(
                "unverified_context_evidence_bindings", ())
            if item.get("source_schema") == "sentientos.local_operator_feedback:v5"
            and item.get("source_class") == "operator_input"
            and item.get("evidence_relation") == "contextualizes"
            and item.get("reliability_posture")
                == "operator_assertion_unverified_context_only"})
        omitted_correction_count = packet.get(
            "omitted_unverified_context_evidence_count", 0)
        omitted_correction_digest = packet.get(
            "omitted_unverified_context_identity_digest")
        correction_review_pending = bool(
            correction_binding_ids or omitted_correction_count)
        positive_current = (
            state["stance"] in {"provisionally_supported", "supported"}
            and not state["dependency_unresolved"]
            and state["freshness"] == "current"
            and (temporal_freshness is None
                or temporal_freshness["status"] == "within_limit"))
        # Unscoped positive history does not constrain canonical planning. A
        # task-family or model-bound positive position must remain visible so
        # planning can prove it still applies to the observed model identity.
        if (positive_current and not relation_digests
                and not correction_review_pending
                and not any(key in scope for key in (
                    "task_family_id", "active_model_identity_digest"))):
            continue
        # Conflicts, supersession, and source-bound but unverified corrections
        # require review even when the evidence posture is positive. A
        # correction is a review signal only; it never revises state or serves
        # as supporting/contradicting evidence.
        scope["position_posture"] = (
            "verified_positive_current" if (positive_current
                and not relation_digests and not correction_review_pending)
            else "review_required")
        if temporal_freshness is not None:
            scope["temporal_freshness_review"] = temporal_freshness
        if relation_digests:
            scope["relation_review_digests"] = relation_digests
        if correction_binding_ids:
            scope["unverified_correction_binding_ids"] = correction_binding_ids
        if omitted_correction_count:
            scope["omitted_unverified_correction_context"] = {
                "count": omitted_correction_count,
                "identity_digest": omitted_correction_digest,
            }
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


def temporal_freshness_review(packet: Mapping[str, object], *,
        evaluation_time: str | None) -> dict[str, object] | None:
    """Evaluate an explicitly time-bounded epistemic position without mutation."""
    proposition = packet.get("proposition")
    temporal_scope = (proposition.get("temporal_scope")
        if isinstance(proposition, Mapping) else None)
    if not isinstance(temporal_scope, Mapping) or (
            "max_evidence_age_seconds" not in temporal_scope):
        return None
    max_age_seconds = temporal_scope.get("max_evidence_age_seconds")
    result: dict[str, object] = {
        "schema_version": "sentientos.epistemic_temporal_freshness_review:v1",
        "max_evidence_age_seconds": max_age_seconds,
    }
    if (type(max_age_seconds) is not int
            or not 1 <= max_age_seconds <= 2_147_483_647):
        result.update({"status": "policy_invalid",
            "reason": "max_evidence_age_seconds_invalid"})
        return result
    if not isinstance(evaluation_time, str) or not evaluation_time:
        result.update({"status": "unresolved",
            "reason": "evaluation_time_unavailable"})
        return result
    try:
        evaluated_at = _aware_datetime(evaluation_time)
    except (TypeError, ValueError):
        result.update({"status": "unresolved",
            "reason": "evaluation_time_invalid"})
        return result

    support_ids = packet.get("supporting_evidence")
    active_rows = packet.get("active_evidence_bindings")
    if not isinstance(support_ids, (list, tuple)) or not isinstance(
            active_rows, (list, tuple)):
        result.update({"status": "unresolved",
            "reason": "supporting_evidence_unavailable"})
        return result
    current_support = [
        row for row in active_rows
        if isinstance(row, Mapping)
        and row.get("binding_id") in support_ids
        and row.get("freshness") == "current"
        and not row.get("withdrawn", False)
        and (row.get("evidence_relation") == "supports"
            or row.get("reliability_posture") == "supports")
    ]
    if not current_support:
        result.update({"status": "unresolved",
            "reason": "current_supporting_evidence_unavailable"})
        return result
    parsed_support = []
    for row in current_support:
        observation_time = row.get("observation_time")
        binding_id = row.get("binding_id")
        if not isinstance(observation_time, str) or not isinstance(
                binding_id, str):
            result.update({"status": "unresolved",
                "reason": "supporting_observation_time_invalid"})
            return result
        try:
            parsed_support.append((_aware_datetime(observation_time), binding_id))
        except (TypeError, ValueError):
            result.update({"status": "unresolved",
                "reason": "supporting_observation_time_invalid"})
            return result
    try:
        latest = max(parsed_support)
    except ValueError:
        result.update({"status": "unresolved",
            "reason": "supporting_observation_time_invalid"})
        return result
    observed_at, binding_id = latest
    age = (evaluated_at - observed_at).total_seconds()
    if age < 0:
        result.update({"status": "unresolved",
            "reason": "supporting_observation_is_future",
            "latest_support_binding_id": binding_id,
            "latest_support_observed_at": observed_at.isoformat()})
        return result
    result.update({
        "status": "within_limit" if age <= max_age_seconds else "expired",
        "latest_support_binding_id": binding_id,
        "latest_support_observed_at": observed_at.isoformat(),
        "evaluation_time": evaluated_at.isoformat(),
        "age_seconds": age,
    })
    if age > max_age_seconds:
        result["reason"] = "supporting_evidence_exceeded_maximum_age"
    return result


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone_required")
    return parsed.astimezone(timezone.utc)


def epistemic_review_reason_for_goal(tags: Sequence[str],
        review_scopes: Mapping[str, Mapping[str, object]], *,
        target_active_model_identity_digest: str | None = None,
        target_identity_observed_at: str | None = None,
        planning_time: str | None = None) -> str | None:
    """Require explicit family/model applicability before a goal can consume a reviewed position."""
    tag_set = set(tags)
    unresolved = False
    review_required = False
    for proposition_id, scope in review_scopes.items():
        if f"epistemic_proposition:{proposition_id}" not in tag_set:
            continue
        if scope.get("omitted_from_prior_projection") is True:
            unresolved = True
            continue
        family_id = scope.get("task_family_id")
        identity_digest = scope.get("active_model_identity_digest")
        if family_id is not None:
            if not isinstance(family_id, str) or not family_id:
                unresolved = True
                continue
            if f"epistemic_task_family:{family_id}" not in tag_set:
                unresolved = True
                continue
            if (not isinstance(identity_digest, str) or len(identity_digest) != 71
                    or not identity_digest.startswith("sha256:")
                    or any(character not in "0123456789abcdef" for character in identity_digest[7:])):
                unresolved = True
                continue
            if (not isinstance(target_active_model_identity_digest, str)
                    or target_active_model_identity_digest != identity_digest
                    or not isinstance(target_identity_observed_at, str)
                    or target_identity_observed_at != planning_time):
                unresolved = True
                continue
        if identity_digest is not None:
            if (not isinstance(identity_digest, str) or len(identity_digest) != 71
                    or not identity_digest.startswith("sha256:")
                    or any(character not in "0123456789abcdef" for character in identity_digest[7:])
                    or target_active_model_identity_digest != identity_digest
                    or not isinstance(target_identity_observed_at, str)
                    or target_identity_observed_at != planning_time):
                unresolved = True
                continue
        if scope.get("position_posture") != "verified_positive_current":
            review_required = True
    if unresolved:
        return "epistemic_applicability_unresolved"
    if review_required:
        return "epistemic_review_required"
    return None


__all__ = ["EpistemicPlanningError", "epistemic_review_reason_for_goal",
    "review_required_applicability", "review_required_propositions"]
