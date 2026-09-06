"""Registry-backed admission for task-scaffold authority declarations.

This module admits capability *definitions* to planning.  It never grants a
capability, creates a lease, loads credentials, or performs an effect.
"""

from __future__ import annotations

from dataclasses import dataclass


MODEL_MIRROR_PUBLISH = "sentientos.model_mirror.publish"


@dataclass(frozen=True)
class TaskAuthorityDefinition:
    capability_id: str
    subsystem_kinds: frozenset[str]
    principal_kinds: frozenset[str]
    required_effects: frozenset[str]
    forbidden_goal_phrases: tuple[str, ...]


AUTHORITY_DEFINITIONS = {
    MODEL_MIRROR_PUBLISH: TaskAuthorityDefinition(
        capability_id=MODEL_MIRROR_PUBLISH,
        subsystem_kinds=frozenset({"model_distribution"}),
        principal_kinds=frozenset({"deterministic_publication_controller"}),
        required_effects=frozenset(
            {
                "exact_curator_artifact_read",
                "canonical_sovereign_create_only_write",
                "bounded_outbound_transfer",
                "publication_receipt_write",
            }
        ),
        forbidden_goal_phrases=(
            "arbitrary host",
            "arbitrary url",
            "mutable alias",
            "overwrite",
            "provider administration",
            "credential management",
            "credential selection",
            "self-grant",
            "self grant",
            "hugging face",
            "github publication",
            "git publication",
        ),
    )
}


def authority_admission_blockers(
    *, capability_id: str, subsystem_kind: str, principal_kind: str,
    requested_effects: tuple[str, ...], task_goal: str,
) -> tuple[str, ...]:
    """Return deterministic blockers; an empty tuple means definition eligibility.

    Eligibility is not a grant and cannot be presented as effect authority.
    """
    definition = AUTHORITY_DEFINITIONS.get(capability_id)
    if definition is None:
        return ("unregistered_authority_capability",)
    blockers: list[str] = []
    if subsystem_kind not in definition.subsystem_kinds:
        blockers.append("authority_subsystem_not_admitted")
    if principal_kind not in definition.principal_kinds:
        blockers.append("authority_principal_not_admitted")
    effects = tuple(requested_effects)
    if len(effects) != len(set(effects)) or frozenset(effects) != definition.required_effects:
        blockers.append("authority_effect_surface_not_exact")
    folded_goal = task_goal.casefold()
    if any(phrase in folded_goal for phrase in definition.forbidden_goal_phrases):
        blockers.append("authority_goal_requests_forbidden_scope")
    return tuple(sorted(set(blockers)))
