"""Candidate-only authority metadata for future attempt-identity evidence production."""
from __future__ import annotations

from typing import Any

from sentientos.codex_task_authority_admission import (
    TaskAuthorityDefinition,
    authority_definition_digest,
)

CONTRACT_SCHEMA = "sentientos.production_chat_resource_provisioning_request_attempt_identity_authority_contract:v1"
CANDIDATE_CAPABILITY_ID = "production_chat_resource_provisioning_request_attempt_identity_evidence_create"
CANDIDATE_SUBSYSTEM = "causal_resource_principal_architecture"
CANDIDATE_PRINCIPAL = "deterministic_production_chat_resource_provisioning_request_attempt_identity_evidence_producer"
EFFECTS = (
    "read_exact_pre_effect_production_resource_provisioning_request_publication_intent",
    "establish_one_production_resource_provisioning_request_publication_attempt_identity",
    "create_only_installation_state_production_resource_provisioning_request_attempt_identity_evidence",
    "finalize_production_resource_provisioning_request_attempt_identity_evidence",
)
REQUIRED_GOAL_PHRASES = (
    "create-only publisher attempt identity evidence",
    "exact pre-effect request and intent binding",
    "before first publication custody mutation",
    "independently verifiable lifecycle provenance",
    "no request publication or recovery authority",
)
FORBIDDEN_GOAL_PHRASES = (
    "publish production chat resource provisioning request", "create publication receipt",
    "finalize publication receipt", "terminal publisher closure",
    "terminal abandonment classification", "recovery authority", "automatic recovery",
    "same-id retry", "same id retry", "provisioning id reuse",
    "overwrite attempt identity evidence", "repair attempt identity evidence",
    "delete attempt identity evidence", "caller-selected attempt identity",
    "retrospective attempt identity", "allocation issuance",
    "production provisioning bundle creation", "model inference", "grant local model inference",
    "network egress", "host scheduling", "arbitrary filesystem mutation",
    "widen publisher authority", "modify publisher authority definition",
    "root principal minting", "issuer provenance signing", "private signing key custody",
)
APPROVAL_REQUIREMENTS = (
    "independent operator approval evidence", "exact definition digest binding",
    "exact publisher attempt identity contract digest binding",
    "exact existing publisher authority definition binding",
    "exact installation provisioning request and intent binding",
    "create-only fixed attempt identity evidence custody",
    "identity evidence completed before first publication custody mutation",
    "independently verifiable lifecycle provenance", "production non-synthetic evidence posture",
    "no request publication receipt terminal closure or recovery authority",
)
CANDIDATE_PURPOSE = (
    "Permit only a future separately registered and admitted deterministic production provisioning request "
    "publisher-attempt identity evidence producer to consume exact validated pre-effect request and intent "
    "bindings for one installation and provisioning identity; establish one fresh publisher invocation "
    "identity; and create and finalize one immutable canonical identity evidence artifact in fixed authenticated "
    "installation-state custody before the first durable request-publication custody mutation, while granting "
    "no request or receipt publication, terminal closure, abandonment classification, recovery, retry, "
    "overwrite, cleanup, provisioning-ID reuse, allocation, bundle creation, inference, network, host, "
    "arbitrary filesystem, signing, root-issuance, or publisher-authority-widening authority."
)

CANDIDATE_DEFINITION = TaskAuthorityDefinition(
    capability_id=CANDIDATE_CAPABILITY_ID,
    subsystem_kinds=frozenset({CANDIDATE_SUBSYSTEM}),
    principal_kinds=frozenset({CANDIDATE_PRINCIPAL}),
    required_effects=frozenset(EFFECTS),
    forbidden_goal_phrases=FORBIDDEN_GOAL_PHRASES,
    required_goal_phrases=REQUIRED_GOAL_PHRASES,
    approval_requirements=APPROVAL_REQUIREMENTS,
    purpose=CANDIDATE_PURPOSE,
)
CANDIDATE_DEFINITION_DIGEST = "ad219f43186a8a173e31dda428cff068c5ee2643211284dacf391f858def3b6d"
assert authority_definition_digest(CANDIDATE_DEFINITION) == CANDIDATE_DEFINITION_DIGEST


def definition_as_json() -> dict[str, Any]:
    """Return the registrar-native JSON representation without registering it."""
    return {
        "capability_id": CANDIDATE_DEFINITION.capability_id,
        "subsystem_kinds": sorted(CANDIDATE_DEFINITION.subsystem_kinds),
        "principal_kinds": sorted(CANDIDATE_DEFINITION.principal_kinds),
        "required_effects": sorted(CANDIDATE_DEFINITION.required_effects),
        "required_goal_phrases": list(CANDIDATE_DEFINITION.required_goal_phrases),
        "forbidden_goal_phrases": list(CANDIDATE_DEFINITION.forbidden_goal_phrases),
        "approval_requirements": list(CANDIDATE_DEFINITION.approval_requirements),
        "purpose": CANDIDATE_DEFINITION.purpose,
    }


__all__ = ["APPROVAL_REQUIREMENTS", "CANDIDATE_CAPABILITY_ID", "CANDIDATE_DEFINITION",
           "CANDIDATE_DEFINITION_DIGEST", "CANDIDATE_PRINCIPAL", "CANDIDATE_PURPOSE",
           "CANDIDATE_SUBSYSTEM", "CONTRACT_SCHEMA", "EFFECTS", "FORBIDDEN_GOAL_PHRASES",
           "REQUIRED_GOAL_PHRASES", "definition_as_json"]
