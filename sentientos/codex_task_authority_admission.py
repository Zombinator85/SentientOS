"""Registry-backed admission for task-scaffold authority declarations.

This module admits capability *definitions* to planning.  It never grants a
capability, creates a lease, loads credentials, or performs an effect.
"""

from __future__ import annotations

from dataclasses import dataclass


MODEL_MIRROR_PUBLISH = "sentientos.model_mirror.publish"
LOCAL_MODEL_CATALOG_DEPLOY = "sentientos.local_model_catalog.deploy"
LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE = (
    "sentientos.local_model_catalog.deployment_authorization.issue"
)


@dataclass(frozen=True)
class TaskAuthorityDefinition:
    capability_id: str
    subsystem_kinds: frozenset[str]
    principal_kinds: frozenset[str]
    required_effects: frozenset[str]
    forbidden_goal_phrases: tuple[str, ...]
    required_goal_phrases: tuple[str, ...] = ()


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
    ),
    LOCAL_MODEL_CATALOG_DEPLOY: TaskAuthorityDefinition(
        capability_id=LOCAL_MODEL_CATALOG_DEPLOY,
        subsystem_kinds=frozenset({"model_distribution"}),
        principal_kinds=frozenset({"deterministic_catalog_deployment_controller"}),
        required_effects=frozenset(
            {
                "exact_verified_publication_receipt_read",
                "exact_deployment_eligible_catalog_candidate_read",
                "authoritative_catalog_compare_and_swap",
                "catalog_deployment_receipt_write",
            }
        ),
        forbidden_goal_phrases=(
            "generic deployment", "arbitrary configuration", "generic filesystem",
            "network authority", "provider administration", "credential management",
            "git publication", "model acquisition", "commissioning", "activation",
            "inference", "self-grant", "self grant", "mutable catalog",
            "arbitrary destination", "arbitrary mirror", "hugging face", "blind overwrite",
        ),
        required_goal_phrases=("verified publication", "exact prior-state"),
    ),
    LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE: TaskAuthorityDefinition(
        capability_id=LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE,
        subsystem_kinds=frozenset({"model_distribution"}),
        principal_kinds=frozenset({"deterministic_catalog_deployment_authorization_controller"}),
        required_effects=frozenset(
            {
                "exact_operator_approval_evidence_read",
                "exact_verified_publication_receipt_read",
                "exact_deployment_eligible_catalog_candidate_read",
                "bounded_catalog_deployment_grant_issue",
                "bounded_catalog_deployment_lease_issue",
                "catalog_deployment_authorization_receipt_write",
            }
        ),
        forbidden_goal_phrases=(
            "generic deployment authority", "arbitrary filesystem", "network authority",
            "provider administration", "credential management", "git publication",
            "model acquisition", "commissioning", "activation", "inference",
            "self-grant", "self grant", "unbounded grant", "unbounded lease",
        ),
        required_goal_phrases=(
            "explicit operator approval", "verified publication", "exact prior-state",
        ),
    ),
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
    if any(phrase not in folded_goal for phrase in definition.required_goal_phrases):
        blockers.append("authority_goal_missing_required_precondition")
    return tuple(sorted(set(blockers)))
