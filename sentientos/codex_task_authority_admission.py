"""Registry-backed admission for task-scaffold authority declarations.

This module admits capability *definitions* to planning.  It never grants a
capability, creates a lease, loads credentials, or performs an effect.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


MODEL_MIRROR_PUBLISH = "sentientos.model_mirror.publish"
LOCAL_MODEL_CATALOG_DEPLOY = "sentientos.local_model_catalog.deploy"
LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE = (
    "sentientos.local_model_catalog.deployment_authorization.issue"
)
LOCAL_MODEL_ARTIFACT_ACQUISITION = "local_model_artifact_acquisition"
LOCAL_MODEL_PRODUCTION_COMMISSIONING = "local_model_production_commissioning"
LOCAL_MODEL_PRODUCTION_ACTIVATION = "local_model_production_activation"


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
    LOCAL_MODEL_ARTIFACT_ACQUISITION: TaskAuthorityDefinition(
        capability_id=LOCAL_MODEL_ARTIFACT_ACQUISITION,
        subsystem_kinds=frozenset({"model_distribution"}),
        principal_kinds=frozenset(
            {"deterministic_model_artifact_acquisition_controller"}
        ),
        required_effects=frozenset(
            {
                "exact_operator_approval_evidence_read",
                "exact_authoritative_deployed_catalog_proof_read",
                "exact_model_artifact_acquisition_plan_read",
                "bounded_exact_https_artifact_stream",
                "exact_content_addressed_model_escrow_write",
                "model_artifact_acquisition_receipt_write",
            }
        ),
        forbidden_goal_phrases=(
            "arbitrary url", "arbitrary host", "arbitrary network",
            "generic network authority", "arbitrary filesystem",
            "arbitrary destination", "mutable artifact alias",
            "provider administration", "credential management",
            "catalog mutation", "model commissioning", "activation",
            "inference", "self-grant", "self grant", "unbounded transfer",
        ),
        required_goal_phrases=(
            "explicit operator approval",
            "authoritative deployed catalog",
            "exact artifact identity",
        ),
    ),
    LOCAL_MODEL_PRODUCTION_COMMISSIONING: TaskAuthorityDefinition(
        capability_id=LOCAL_MODEL_PRODUCTION_COMMISSIONING,
        subsystem_kinds=frozenset({"local_model_chat"}),
        principal_kinds=frozenset(
            {"deterministic_local_model_commissioning_controller"}
        ),
        required_effects=frozenset(
            {
                "exact_operator_approval_evidence_read",
                "exact_authoritative_deployed_catalog_proof_read",
                "exact_hardened_model_artifact_acquisition_receipt_read",
                "exact_commissioning_intent_read",
                "bounded_zero_generation_gguf_compatibility_construction",
                "bounded_exact_local_model_load",
                "bounded_commissioning_smoke_inference",
                "local_model_commissioning_receipt_write",
            }
        ),
        forbidden_goal_phrases=(
            "arbitrary model path", "arbitrary artifact", "arbitrary runtime",
            "arbitrary filesystem", "arbitrary output destination",
            "provider invocation", "provider administration", "credential management",
            "network authority", "catalog mutation", "artifact acquisition",
            "activation", "unrestricted serving", "autonomous inference",
            "background inference", "unbounded inference", "tool authority",
            "memory authority", "action authority", "repository mutation",
            "self-grant", "self grant",
        ),
        required_goal_phrases=(
            "explicit operator approval",
            "authoritative deployed catalog",
            "exact acquired artifact identity",
        ),
    ),
    LOCAL_MODEL_PRODUCTION_ACTIVATION: TaskAuthorityDefinition(
        capability_id=LOCAL_MODEL_PRODUCTION_ACTIVATION,
        subsystem_kinds=frozenset({"local_model_chat"}),
        principal_kinds=frozenset(
            {"deterministic_local_model_activation_controller"}
        ),
        required_effects=frozenset(
            {
                "exact_operator_approval_evidence_read",
                "exact_authoritative_deployed_catalog_proof_read",
                "exact_hardened_local_model_commissioning_receipt_read",
                "exact_commissioned_artifact_identity_read",
                "exact_activation_intent_read",
                "exact_current_activation_state_read",
                "authoritative_active_model_compare_and_swap",
                "local_model_activation_receipt_write",
            }
        ),
        forbidden_goal_phrases=(
            "arbitrary activation path", "arbitrary model path",
            "arbitrary artifact", "arbitrary runtime", "arbitrary filesystem",
            "arbitrary configuration", "arbitrary state root", "blind overwrite",
            "wildcard prior state", "model acquisition", "model commissioning",
            "model load", "serving", "unrestricted serving", "boot load",
            "automatic boot loading", "inference", "autonomous inference",
            "background inference", "provider invocation", "provider administration",
            "credential management", "network authority", "tool authority",
            "memory authority", "action authority", "repository mutation",
            "self-grant", "self grant",
        ),
        required_goal_phrases=(
            "explicit operator approval",
            "authoritative deployed catalog",
            "hardened commissioning receipt",
            "exact prior activation state",
        ),
    ),
}


_GOAL_CLAUSE_BOUNDARY_RE = re.compile(r"[.;\n]+")
_PRECONDITION_DISCLAIMER_RE = re.compile(
    r"\b(?:without|no|not|never|bypass(?:ing|ed)?|omit(?:ting|ted)?|skip(?:ping|ped)?)\b",
    re.IGNORECASE,
)
_PRECONDITION_NEGATED_SUFFIX_RE = re.compile(
    r"^\s*(?:is|are|was|were)?\s*(?:not|required\s+not\s+to\s+be)\s*"
    r"(?:required|needed|used|provided|verified|enforced|included|obtained|present)\b",
    re.IGNORECASE,
)


def _required_precondition_is_affirmative(task_goal: str, phrase: str) -> bool:
    """Return true when ``phrase`` occurs in a mechanically affirmative clause.

    This intentionally rejects a whole local clause when a recognizable disclaimer
    precedes the occurrence.  Trying to resolve double negatives or coordinated
    negation here would make an authority gate guess at author intent; callers must
    instead provide a simple affirmative precondition statement.
    """
    phrase_pattern = re.compile(
        rf"(?<![\w-]){re.escape(phrase).replace(r'\ ', r'\s+')}(?![\w-])",
        re.IGNORECASE,
    )
    for match in phrase_pattern.finditer(task_goal):
        boundaries_before = tuple(_GOAL_CLAUSE_BOUNDARY_RE.finditer(task_goal, 0, match.start()))
        clause_start = boundaries_before[-1].end() if boundaries_before else 0
        boundary_after = _GOAL_CLAUSE_BOUNDARY_RE.search(task_goal, match.end())
        clause_end = boundary_after.start() if boundary_after else len(task_goal)
        prefix = task_goal[clause_start:match.start()]
        suffix = task_goal[match.end():clause_end]
        if _PRECONDITION_DISCLAIMER_RE.search(prefix):
            continue
        if _PRECONDITION_NEGATED_SUFFIX_RE.match(suffix):
            continue
        return True
    return False


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
    if any(
        not _required_precondition_is_affirmative(task_goal, phrase)
        for phrase in definition.required_goal_phrases
    ):
        blockers.append("authority_goal_missing_required_precondition")
    return tuple(sorted(set(blockers)))
