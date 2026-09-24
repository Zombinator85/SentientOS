"""Registry-backed admission for task-scaffold authority declarations.

This module admits capability *definitions* to planning.  It never grants a
capability, creates a lease, loads credentials, or performs an effect.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


MODEL_MIRROR_PUBLISH = "sentientos.model_mirror.publish"
LOCAL_MODEL_CATALOG_DEPLOY = "sentientos.local_model_catalog.deploy"
LOCAL_MODEL_CATALOG_DEPLOYMENT_AUTHORIZATION_ISSUE = (
    "sentientos.local_model_catalog.deployment_authorization.issue"
)
LOCAL_MODEL_ARTIFACT_ACQUISITION = "local_model_artifact_acquisition"
LOCAL_MODEL_PRODUCTION_COMMISSIONING = "local_model_production_commissioning"
LOCAL_MODEL_PRODUCTION_ACTIVATION = "local_model_production_activation"
LOCAL_MODEL_PRODUCTION_SERVING = "local_model_production_serving"
LOCAL_MODEL_CHAT_RECOVERY = "local_model_chat_recovery"
MAINTENANCE_WAKE_DAEMON_ADOPTION = "maintenance_wake_daemon_adoption"
MAINTENANCE_AUTHORITY_CONTINUITY = "maintenance_authority_continuity"
MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION = (
    "maintenance_authority_continuity_auto_derivation"
)
MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION = (
    "maintenance_successor_generation_adoption"
)
MAINTENANCE_RESIDENT_RUNTIME_ADOPTION = "maintenance_resident_runtime_adoption"
MAINTENANCE_RESIDENT_PARENT_SUPERVISION = "maintenance_resident_parent_supervision"
RESIDENT_DEVELOPMENTAL_WRITEBACK = "resident_developmental_writeback"
DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING = (
    "developmental_model_replacement_experimental_serving"
)
EXTERNAL_MODEL_INFERENCE = "external_model_inference"


@dataclass(frozen=True)
class TaskAuthorityDefinition:
    capability_id: str
    subsystem_kinds: frozenset[str]
    principal_kinds: frozenset[str]
    required_effects: frozenset[str]
    forbidden_goal_phrases: tuple[str, ...]
    required_goal_phrases: tuple[str, ...] = ()
    approval_requirements: tuple[str, ...] = ()
    purpose: str = ""


@dataclass(frozen=True)
class AuthorityDefinitionRegistrationResult:
    status: str
    blocker_codes: tuple[str, ...]
    task_name: str
    capability_id: str
    definition_digest: str
    operator_approval_evidence_id: str
    authority_definitions: Mapping[str, TaskAuthorityDefinition]
    definition_registered: bool
    capability_granted: bool = False
    runtime_authority: None = None
    effect_performed: bool = False
    runtime_mutation_performed: bool = False


AUTHORITY_DEFINITION_REGISTRATION = "authority_definition_registration"
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_BROAD_VALUES = frozenset({"*", "all", "any", "all_current_and_future", "all current and future"})
_REGISTRATION_ALLOWED_ROOTS = frozenset({"sentientos", "scripts", "tests", "docs", "artifacts", ".codex_task"})


def authority_definition_digest(definition: TaskAuthorityDefinition) -> str:
    payload = {
        "capability_id": definition.capability_id,
        "subsystem_kinds": sorted(definition.subsystem_kinds),
        "principal_kinds": sorted(definition.principal_kinds),
        "required_effects": sorted(definition.required_effects),
        "required_goal_phrases": list(definition.required_goal_phrases),
        "forbidden_goal_phrases": list(definition.forbidden_goal_phrases),
        "approval_requirements": list(definition.approval_requirements),
        "purpose": definition.purpose,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def operator_approval_evidence_digest(evidence: Mapping[str, Any]) -> str:
    payload = {key: evidence[key] for key in sorted(evidence) if key != "evidence_digest"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _registration_definition_blockers(definition: object) -> list[str]:
    if not isinstance(definition, TaskAuthorityDefinition):
        return ["authority_definition_malformed"]
    blockers: list[str] = []
    collection_surfaces: tuple[tuple[str, Any], ...] = (
        ("subsystem", definition.subsystem_kinds),
        ("principal", definition.principal_kinds),
        ("effect", definition.required_effects),
    )
    for label, values in collection_surfaces:
        if not values:
            blockers.append(f"authority_definition_{label}s_empty")
        if any(not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value) for value in values):
            blockers.append(f"authority_definition_{label}_malformed")
        if any(value.casefold() in _BROAD_VALUES for value in values):
            blockers.append(f"authority_definition_{label}_wildcard")
        if len(values) != len(set(values)):
            blockers.append(f"authority_definition_{label}_duplicate")
    if not _IDENTIFIER_RE.fullmatch(definition.capability_id):
        blockers.append("authority_definition_capability_id_malformed")
    for label, values in (("required_goal_phrases", definition.required_goal_phrases), ("forbidden_goal_phrases", definition.forbidden_goal_phrases), ("approval_requirements", definition.approval_requirements)):
        if not values or any(not isinstance(value, str) or not value.strip() for value in values):
            blockers.append(f"authority_definition_{label}_missing")
        if len(values) != len(set(value.casefold() for value in values)):
            blockers.append(f"authority_definition_{label}_duplicate")
    if not definition.purpose.strip():
        blockers.append("authority_definition_purpose_missing")
    if {x.casefold() for x in definition.required_goal_phrases} & {x.casefold() for x in definition.forbidden_goal_phrases}:
        blockers.append("authority_definition_contradictory_goal_semantics")
    return blockers


def register_authority_definition(artifact: Mapping[str, Any], *, authority_definitions: Mapping[str, TaskAuthorityDefinition] | None = None) -> AuthorityDefinitionRegistrationResult:
    """Validate one governance-only registration and return a new catalog view.

    Neither the canonical catalog nor a supplied catalog is mutated.  The new
    view is eligible only for ordinary exact admission in a subsequent task.
    """
    catalog = AUTHORITY_DEFINITIONS if authority_definitions is None else authority_definitions
    blockers: list[str] = []
    task_name = artifact.get("task_name", "")
    definitions = artifact.get("definitions")
    if artifact.get("task_classification") != AUTHORITY_DEFINITION_REGISTRATION:
        blockers.append("authority_definition_registration_classification_required")
    if not isinstance(task_name, str) or not task_name.strip():
        blockers.append("authority_definition_registration_task_missing")
    if not isinstance(definitions, (list, tuple)) or len(definitions) != 1:
        blockers.append("authority_definition_registration_requires_exactly_one_definition")
    definition = definitions[0] if isinstance(definitions, (list, tuple)) and len(definitions) == 1 else None
    blockers.extend(_registration_definition_blockers(definition))
    capability_id = definition.capability_id if isinstance(definition, TaskAuthorityDefinition) else ""
    digest = authority_definition_digest(definition) if isinstance(definition, TaskAuthorityDefinition) else ""
    if capability_id in catalog:
        blockers.append("authority_definition_capability_id_duplicate")
    approval = artifact.get("operator_approval")
    evidence_id = ""
    if not isinstance(approval, Mapping):
        blockers.append("authority_definition_operator_approval_missing")
    else:
        evidence_id = approval.get("evidence_id", "") if isinstance(approval.get("evidence_id"), str) else ""
        bindings = {"schema_version": "sentientos.authority_definition_operator_approval:v1", "approval_status": "approved", "approved_capability_id": capability_id, "approved_definition_digest": digest, "approved_task_name": task_name}
        if not evidence_id or not isinstance(approval.get("operator_identity_label"), str) or not approval.get("operator_identity_label", "").strip():
            blockers.append("authority_definition_operator_approval_identity_missing")
        if any(approval.get(key) != value for key, value in bindings.items()):
            blockers.append("authority_definition_operator_approval_binding_mismatch")
        if approval.get("evidence_digest") != operator_approval_evidence_digest(approval):
            blockers.append("authority_definition_operator_approval_digest_invalid")
    if artifact.get("requested_capability_id") or artifact.get("authority_principal") or artifact.get("requested_effects"):
        blockers.append("authority_definition_registration_cannot_request_capability")
    if artifact.get("runtime_mutations"):
        blockers.append("authority_definition_registration_runtime_mutation_forbidden")
    changed_paths = artifact.get("changed_paths", ())
    if not isinstance(changed_paths, (list, tuple)) or any(not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/") or path.split("/", 1)[0] not in _REGISTRATION_ALLOWED_ROOTS for path in changed_paths):
        blockers.append("authority_definition_registration_changed_paths_malformed")
    blocker_codes = tuple(sorted(set(blockers)))
    updated = dict(catalog)
    if not blocker_codes and isinstance(definition, TaskAuthorityDefinition):
        updated[definition.capability_id] = definition
    return AuthorityDefinitionRegistrationResult("authority_definition_registered" if not blocker_codes else "authority_definition_registration_blocked", blocker_codes, task_name if isinstance(task_name, str) else "", capability_id, digest, evidence_id, MappingProxyType(updated), not blocker_codes)


EXTERNAL_MODEL_INFERENCE_DEFINITION = TaskAuthorityDefinition(
    capability_id=EXTERNAL_MODEL_INFERENCE,
    subsystem_kinds=frozenset({"external_model_inference"}),
    principal_kinds=frozenset({"deterministic_external_model_inference_controller"}),
    required_effects=frozenset({"bounded_external_model_network_egress"}),
    required_goal_phrases=(
        "explicit operator approval of definition registration",
        "exact registered external model inference definition",
        "authenticated bounded operator runtime grant",
        "admitted deterministic external model inference controller",
        "enabled configured external model service",
        "exact service endpoint model request and configuration binding",
        "service bound opaque credential reference when configured",
        "valid runtime grant policy decision",
        "valid bounded runtime admission",
        "request provenance",
        "durable hash linked invocation receipt",
    ),
    forbidden_goal_phrases=(
        "arbitrary network authority", "arbitrary internet access",
        "arbitrary host", "arbitrary url", "arbitrary endpoint",
        "credential creation", "credential modification", "credential rotation",
        "credential inspection", "credential export", "credential administration",
        "provider administration", "provider account administration",
        "billing administration", "account administration", "shell authority",
        "shell execution", "arbitrary subprocess authority",
        "arbitrary subprocess execution", "unrelated filesystem mutation",
        "repository mutation", "maintenance authority", "runtime adoption",
        "host actuation", "device actuation", "capability definition mutation",
        "capability self modification", "grant issuance", "admission issuance",
        "self grant", "model output authorization", "cognition authorization",
        "configuration authorization", "credential possession authorization",
        "service availability authorization", "response receipt cognition trust",
    ),
    approval_requirements=(
        "authenticated bounded operator runtime grant",
        "enabled configured external model service",
        "exact service endpoint model request and configuration binding",
        "service bound opaque credential reference when configured",
        "valid runtime grant policy decision",
        "valid bounded runtime admission",
        "request provenance",
        "durable hash linked invocation receipt",
    ),
    purpose=(
        "Permit a separately granted and admitted deterministic external-model "
        "inference controller to perform one configuration-bound invocation of an "
        "enabled external-model service at its exact HTTPS endpoint for an allowed "
        "model and bounded request, using its service-bound opaque credential "
        "reference when configured, and to custody the result and durable invocation "
        "receipt, without granting generic network, credential-administration, "
        "provider-administration, cognition-trust, grant-issuance, or "
        "admission-issuance authority."
    ),
)

EXTERNAL_MODEL_INFERENCE_OPERATOR_APPROVAL = MappingProxyType({
    "schema_version": "sentientos.authority_definition_operator_approval:v1",
    "evidence_id": "approval:external_model_inference:539ff509bbea:001",
    "operator_identity_label": "operator:primary",
    "approval_status": "approved",
    "approved_capability_id": EXTERNAL_MODEL_INFERENCE,
    "approved_definition_digest": "539ff509bbeabe50cd2be17adf9ebbe58958e894b3cb6728a5c809a605db7b9c",
    "approved_task_name": "register_governed_external_model_inference_authority_definition",
    "evidence_digest": "a2e33b07a3ed411fefaa5d4f9dbcd05a12ef951eae5fa405bb209ea33203f028",
})


RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION = TaskAuthorityDefinition(
    capability_id=RESIDENT_DEVELOPMENTAL_WRITEBACK,
    subsystem_kinds=frozenset({"memory_context_reflection"}),
    principal_kinds=frozenset(
        {"deterministic_resident_developmental_writeback_controller"}
    ),
    required_effects=frozenset({
        "exact_world_state_evidence_snapshot_read",
        "bounded_governed_local_developmental_inference_request",
        "exact_resident_developmental_candidate_observation",
        "bounded_resident_developmental_history_append",
        "exact_resident_developmental_history_retrieval",
        "exact_resident_developmental_source_provenance_read",
        "resident_developmental_writeback_receipt_write",
        "read_only_resident_developmental_history_projection",
    }),
    required_goal_phrases=(
        "canonical resident path", "selected evidence",
        "bounded developmental writeback", "source-bound transformation provenance",
        "memory is not current truth", "subsequent retrieval",
        "measured changed cognition", "preserve canonical explicit user retention",
    ),
    forbidden_goal_phrases=(
        "automatic truth adoption", "belief overwrite", "arbitrary memory mutation",
        "canonical user memory mutation", "automatic goal creation",
        "automatic self-model update", "persona bootstrap", "identity prescription",
        "autonomous host action", "generic service restart", "arbitrary process control",
        "repository mutation", "git mutation", "provider invocation", "network authority",
        "external disclosure", "resource allocation", "federation adoption",
        "memory deletion", "tomb completion", "policy creation", "authority widening",
        "consent inference", "survival objective", "novelty reward",
        "unrestricted autonomous cognition",
    ),
    approval_requirements=(
        "operator-approved capability-definition registration",
        "separate exact runtime control-plane admission",
        "model output or observed evidence does not itself grant retention authority",
        "runtime implementation requires a later separately admitted task",
    ),
    purpose=(
        "Permit a future bounded resident path from selected evidence through governed "
        "local interpretation to source-bound developmental-history append and later "
        "provenance-preserving retrieval, while treating retained interpretations as "
        "historical records rather than current truth and preserving the separate "
        "authority of canonical explicit user retention."
    ),
)

RESIDENT_DEVELOPMENTAL_WRITEBACK_OPERATOR_APPROVAL = MappingProxyType({
    "schema_version": "sentientos.authority_definition_operator_approval:v1",
    "evidence_id": "approval:resident_developmental_writeback:a263a62ee135:001",
    "operator_identity_label": "repository_operator",
    "approval_status": "approved",
    "approved_capability_id": RESIDENT_DEVELOPMENTAL_WRITEBACK,
    "approved_definition_digest": "a263a62ee13570a1dd11fc3d9bf25f3d28f8d5e75eadea6ea0dc4000c2252cd6",
    "approved_task_name": "register_resident_developmental_writeback_authority",
    "evidence_digest": "f7c14b9ea064a59026a23b05f2adb69c18171d77cc6c69f18129e334d2fe2281",
})


DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING_DEFINITION = TaskAuthorityDefinition(
    capability_id=DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING,
    subsystem_kinds=frozenset({"local_model_chat"}),
    principal_kinds=frozenset({
        "deterministic_developmental_model_replacement_experimental_serving_controller"
    }),
    required_effects=frozenset({
        "exact_operator_approval_evidence_read",
        "exact_preregistered_model_replacement_protocol_read",
        "exact_hardened_model_commissioning_receipt_read",
        "exact_model_artifact_identity_revalidation",
        "bounded_exact_experimental_local_model_load",
        "exact_experimental_loaded_model_identity_observation",
        "bounded_exact_experimental_local_model_unload",
        "experimental_model_serving_receipt_write",
    }),
    required_goal_phrases=(
        "preregistered model replacement protocol",
        "exact operator approval",
        "hardened commissioning evidence",
        "exact model artifact identity",
        "experiment scoped model load",
        "exact loaded model identity",
        "separate local model inference admission",
        "canonical activation preservation",
        "canonical production serving preservation",
        "bounded model unload",
        "durable experimental serving receipt",
    ),
    forbidden_goal_phrases=(
        "arbitrary model load", "arbitrary model path", "arbitrary model artifact",
        "arbitrary runtime", "model acquisition", "model commissioning",
        "catalog mutation", "canonical activation mutation",
        "activation compare and swap", "hot activation switching",
        "canonical production serving mutation", "production chat replacement",
        "default resident model mutation", "autonomous model selection",
        "autonomous model acquisition", "generic model serving",
        "generic process execution", "inference authority", "background inference",
        "provider invocation", "network authority", "tool authority",
        "host actuation", "repository mutation", "developmental history mutation",
        "canonical user memory mutation", "policy creation", "authority widening",
        "grant issuance", "admission issuance", "self grant", "resource allocation",
        "autonomous repetition", "identity conclusion", "sentience conclusion",
        "consciousness conclusion",
    ),
    approval_requirements=(
        "operator-approved capability-definition registration",
        "future runtime implementation requires a later separately admitted task",
        "exact runtime operator approval bound to the preregistered experiment and exact model identities",
        "exact non-synthetic hardened commissioning evidence for any claim of production experimental evidence",
        "separate exact MODEL_SERVING control-plane admission for experimental model loading",
        "separate exact LOCAL_MODEL_INFERENCE admission for every inference",
        "canonical activation state preservation",
        "canonical production serving state preservation",
        "bounded model unload",
        "durable experiment-scoped serving receipt",
    ),
    purpose=(
        "Permit a future separately admitted deterministic developmental-model-replacement "
        "experimental-serving controller to consume exact operator approval, a preregistered "
        "model-replacement protocol, and exact hardened commissioning evidence; revalidate "
        "the exact model artifact; load only the protocol-bound commissioned local model into "
        "an experiment-scoped worker; observe and bind its exact production model identity; "
        "and unload it with a durable experimental-serving receipt. The capability preserves "
        "canonical activation and canonical production serving and grants no local-model "
        "inference authority, model acquisition, model commissioning, provider or network "
        "authority, memory mutation, host action, repository mutation, resource allocation, "
        "or identity conclusion. This task registers that definition only."
    ),
)


DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING_OPERATOR_APPROVAL = MappingProxyType({
    "schema_version": "sentientos.authority_definition_operator_approval:v1",
    "evidence_id": "approval:developmental_model_replacement_experimental_serving:b48ad4ae9622:001",
    "operator_identity_label": "repository_operator",
    "approval_status": "approved",
    "approved_capability_id": DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING,
    "approved_definition_digest": "b48ad4ae9622f31f5b49f926d9f295dbb5f0154a411204fe06040fef4a18638c",
    "approved_task_name": "register_developmental_model_replacement_experimental_serving_authority",
    "evidence_digest": "186fb04de307392072c40922e3defdde12dff32f2070244bf6d2175822d58950",
})


AUTHORITY_DEFINITIONS = {
    EXTERNAL_MODEL_INFERENCE: EXTERNAL_MODEL_INFERENCE_DEFINITION,
    RESIDENT_DEVELOPMENTAL_WRITEBACK: RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
    DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING:
        DEVELOPMENTAL_MODEL_REPLACEMENT_EXPERIMENTAL_SERVING_DEFINITION,
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
    LOCAL_MODEL_PRODUCTION_SERVING: TaskAuthorityDefinition(
        capability_id=LOCAL_MODEL_PRODUCTION_SERVING,
        subsystem_kinds=frozenset({"local_model_chat"}),
        principal_kinds=frozenset(
            {"deterministic_activated_model_serving_controller"}
        ),
        required_effects=frozenset(
            {
                "authenticated_current_hardened_activation_state_read",
                "exact_current_activation_receipt_read",
                "exact_authoritative_deployed_catalog_proof_read",
                "exact_hardened_local_model_commissioning_receipt_read",
                "exact_activated_artifact_identity_and_bytes_read",
                "exact_activated_runtime_identity_read",
                "bounded_exact_activated_model_load",
                "authoritative_serving_session_bind",
                "stale_serving_session_invalidation",
                "local_model_serving_session_receipt_write",
            }
        ),
        forbidden_goal_phrases=(
            "arbitrary activation", "arbitrary model path", "arbitrary artifact",
            "arbitrary runtime", "arbitrary filesystem", "caller-selected activation",
            "legacy activation path", "legacy autoload", "stale activation",
            "skip currentness", "retain stale model", "boot integration",
            "chat integration", "perform inference", "generation call",
            "provider invocation", "provider administration", "credential management",
            "network authority", "tool authority", "memory authority",
            "action authority", "repository mutation", "self-grant", "self grant",
        ),
        required_goal_phrases=(
            "authenticated current hardened activation state",
            "current catalog provenance",
            "exact artifact and runtime identity",
            "activation-change invalidation",
            "separate local model inference",
        ),
    ),
    LOCAL_MODEL_CHAT_RECOVERY: TaskAuthorityDefinition(
        capability_id=LOCAL_MODEL_CHAT_RECOVERY,
        subsystem_kinds=frozenset({"local_model_chat"}),
        principal_kinds=frozenset(
            {"deterministic_local_model_chat_recovery_controller"}
        ),
        required_effects=frozenset(
            {
                "exact_operator_recovery_approval_evidence_read",
                "exact_runtime_supervisor_local_model_chat_state_read",
                "exact_prior_serving_lifetime_evidence_read",
                "authenticated_current_hardened_activation_state_read",
                "exact_local_model_chat_startup_configuration_read",
                "exact_fresh_serving_operation_identity_read",
                "bounded_exact_local_model_chat_child_restart",
                "post_restart_semantic_readiness_observation",
                "local_model_chat_recovery_receipt_write",
            }
        ),
        forbidden_goal_phrases=(
            "automatic recovery", "automatic restart", "silent recovery",
            "hot activation switching", "hot activation switch",
            "changed activation recovery", "reuse serving operation",
            "reuse operation id", "arbitrary executable", "arbitrary argv",
            "arbitrary command", "arbitrary model path",
            "arbitrary activation path", "arbitrary runtime",
            "arbitrary state root", "simulation fallback", "provider invocation",
            "network authority", "tool authority", "memory authority",
            "action authority", "repository mutation", "perform inference",
            "generation call", "self-grant", "self grant",
        ),
        required_goal_phrases=(
            "explicit operator recovery approval",
            "exact prior serving lifetime evidence",
            "unchanged activation provenance",
            "fresh serving operation identity",
            "separate model serving and local model inference authority",
        ),
    ),
    MAINTENANCE_WAKE_DAEMON_ADOPTION: TaskAuthorityDefinition(
        capability_id=MAINTENANCE_WAKE_DAEMON_ADOPTION,
        subsystem_kinds=frozenset({"maintenance"}),
        principal_kinds=frozenset(
            {"deterministic_maintenance_wake_daemon_controller"}
        ),
        required_effects=frozenset(
            {
                "exact_operator_wake_adoption_configuration_read",
                "exact_maintenance_wake_configuration_read",
                "bounded_maintenance_wake_cycle_invoke",
                "bounded_maintenance_wake_daemon_lifecycle",
                "maintenance_wake_daemon_evidence_write",
                "read_only_maintenance_wake_health_projection",
            }
        ),
        forbidden_goal_phrases=(
            "automatic authority renewal", "silent authority renewal",
            "self-grant", "self grant", "unapproved self-modification",
            "unapproved self modification", "arbitrary command",
            "arbitrary scheduler target", "arbitrary executable",
            "first-boot authority", "first boot authority",
            "candidate admission", "lease issuance", "git publication",
            "provider invocation", "network authority", "credential management",
            "automatic runtime adoption", "os scheduler installation",
            "windows-native support", "windows native support",
        ),
        required_goal_phrases=(
            "explicit operator adoption", "exact wake configuration",
            "bounded wake cycle", "separate downstream maintenance authority",
        ),
    ),
    MAINTENANCE_AUTHORITY_CONTINUITY: TaskAuthorityDefinition(
        capability_id=MAINTENANCE_AUTHORITY_CONTINUITY,
        subsystem_kinds=frozenset({"maintenance"}),
        principal_kinds=frozenset(
            {"deterministic_maintenance_authority_continuity_controller"}
        ),
        required_effects=frozenset(
            {
                "exact_prior_maintenance_authority_generation_read",
                "exact_completed_maintenance_generation_evidence_read",
                "exact_successor_repository_state_read",
                "bounded_successor_maintenance_authority_derive",
                "successor_maintenance_configuration_generation_write",
                "maintenance_authority_continuity_receipt_write",
            }
        ),
        forbidden_goal_phrases=(
            "arbitrary authority widening", "widen authority",
            "new authority class", "arbitrary path expansion",
            "extend authority expiry", "ignore prior authority",
            "unverified successor", "arbitrary successor state",
            "publication alone proves successor", "pr creation proves successor",
            "self-grant from model output", "model output grants authority",
            "arbitrary policy mutation", "arbitrary grant creation",
            "credential management", "provider invocation", "network authority",
            "automatic runtime adoption", "os scheduler installation",
        ),
        required_goal_phrases=(
            "successful prior maintenance generation",
            "exact successor repository state",
            "same or narrower authority",
            "bounded successor authority",
        ),
    ),
    MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION: TaskAuthorityDefinition(
        capability_id=MAINTENANCE_AUTHORITY_CONTINUITY_AUTO_DERIVATION,
        subsystem_kinds=frozenset({"maintenance"}),
        principal_kinds=frozenset(
            {"deterministic_maintenance_authority_continuity_auto_derivation_controller"}
        ),
        required_effects=frozenset(
            {
                "exact_maintenance_continuity_policy_read",
                "exact_prior_maintenance_authority_generation_read",
                "exact_completed_maintenance_generation_evidence_read",
                "exact_successor_repository_state_read",
                "bounded_successor_maintenance_authority_derive",
                "successor_maintenance_configuration_generation_write",
                "maintenance_authority_continuity_receipt_write",
                "exact_maintenance_successor_generation_adoption_state_read",
                "bounded_canonical_completed_maintenance_transition_discovery",
                "maintenance_authority_continuity_evidence_normalization_write",
                "bounded_maintenance_authority_continuity_auto_derivation_lifecycle",
                "maintenance_authority_continuity_auto_derivation_receipt_write",
                "read_only_maintenance_authority_continuity_auto_derivation_health_projection",
            }
        ),
        forbidden_goal_phrases=(
            "unadopted generation derivation", "derive ahead of adoption",
            "skip generation", "arbitrary completed task", "caller-selected task",
            "newest task", "mtime selection", "arbitrary evidence",
            "self-asserted completion", "weak v1 continuity evidence",
            "authority widening", "extend authority expiry", "unverified successor",
            "arbitrary successor state", "publication alone proves successor",
            "pr creation proves successor", "wake owner handoff",
            "automatic runtime adoption", "runtime code adoption", "hot reload",
            "automatic process restart", "git mutation", "git publication",
            "provider invocation", "network authority", "credential management",
            "candidate admission", "lease issuance", "arbitrary command",
            "arbitrary executable", "os scheduler installation",
            "windows-native support",
        ),
        required_goal_phrases=(
            "currently adopted maintenance generation",
            "canonical successful maintenance closure",
            "exact successor repository state",
            "bounded automatic continuity derivation",
            "same or narrower authority",
        ),
    ),
    MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION: TaskAuthorityDefinition(
        capability_id=MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION,
        subsystem_kinds=frozenset({"maintenance"}),
        principal_kinds=frozenset(
            {"deterministic_maintenance_successor_generation_adoption_controller"}
        ),
        required_effects=frozenset(
            {
                "exact_maintenance_continuity_policy_read",
                "exact_successor_maintenance_authority_generation_read",
                "exact_maintenance_authority_continuity_receipt_read",
                "exact_current_maintenance_wake_adoption_state_read",
                "successor_maintenance_configuration_generation_write",
                "bounded_maintenance_wake_owner_generation_handoff",
                "maintenance_successor_generation_adoption_receipt_write",
                "read_only_maintenance_successor_generation_health_projection",
            }
        ),
        forbidden_goal_phrases=(
            "authority widening", "extend authority expiry",
            "unverified successor generation", "arbitrary successor generation",
            "caller-selected generation", "skip generation",
            "arbitrary wake configuration", "arbitrary adoption configuration",
            "self-grant from model output", "model output grants authority",
            "runtime code adoption", "hot reload", "automatic process restart",
            "arbitrary command", "arbitrary executable", "candidate admission",
            "lease issuance", "git mutation", "git publication",
            "provider invocation", "network authority", "credential management",
            "os scheduler installation", "windows-native support",
        ),
        required_goal_phrases=(
            "verified successor authority generation",
            "exact continuity receipt",
            "bounded wake owner handoff",
            "same lineage authority",
        ),
    ),
    MAINTENANCE_RESIDENT_RUNTIME_ADOPTION: TaskAuthorityDefinition(
        capability_id=MAINTENANCE_RESIDENT_RUNTIME_ADOPTION,
        subsystem_kinds=frozenset({"maintenance"}),
        principal_kinds=frozenset(
            {"deterministic_maintenance_resident_runtime_adoption_controller"}
        ),
        required_effects=frozenset(
            {
                "exact_successor_maintenance_authority_generation_read",
                "exact_maintenance_authority_continuity_receipt_read",
                "exact_maintenance_successor_generation_adoption_state_read",
                "exact_successor_repository_state_read",
                "exact_resident_runtime_adoption_configuration_read",
                "exact_resident_runtime_launch_provenance_read",
                "bounded_maintenance_runtime_quiescence",
                "maintenance_resident_runtime_adoption_intent_write",
                "bounded_exact_sentientosd_self_exec",
                "exact_successor_resident_runtime_readiness_read",
                "maintenance_resident_runtime_adoption_receipt_write",
                "read_only_maintenance_resident_runtime_health_projection",
            }
        ),
        forbidden_goal_phrases=(
            "arbitrary service restart", "generic service restart",
            "arbitrary process restart", "arbitrary process kill",
            "arbitrary executable", "arbitrary command", "shell command",
            "arbitrary argv", "arbitrary environment",
            "caller-selected executable", "caller-selected commit",
            "caller-selected generation", "newest commit", "newest generation",
            "skip generation", "unverified successor", "non-consecutive successor",
            "wake before resident readiness",
            "successor maintenance before resident readiness",
            "hot reload", "module reload", "sys.modules patching",
            "dynamic code injection", "runtime monkeypatch adoption",
            "automatic rollback to older code", "git checkout rollback",
            "git mutation", "git fetch", "git pull", "git publication",
            "provider invocation", "network authority", "credential management",
            "os service manager", "systemd control", "windows service control",
            "parent supervisor installation", "authority widening",
            "extend authority expiry", "candidate admission", "lease issuance",
            "maintenance implementation", "maintenance validation",
        ),
        required_goal_phrases=(
            "verified successor maintenance generation",
            "exact pending successor wake handoff",
            "exact successor repository state",
            "resident runtime launch provenance",
            "bounded sentientosd self replacement",
            "post replacement resident readiness",
            "before successor wake effects",
        ),
    ),
    MAINTENANCE_RESIDENT_PARENT_SUPERVISION: TaskAuthorityDefinition(
        capability_id=MAINTENANCE_RESIDENT_PARENT_SUPERVISION,
        subsystem_kinds=frozenset({"maintenance"}),
        principal_kinds=frozenset(
            {"deterministic_maintenance_resident_parent_supervision_controller"}
        ),
        required_effects=frozenset({
            "exact_sentientosd_parent_supervision_configuration_read",
            "exact_sentientosd_child_specification_read",
            "exact_resident_runtime_transition_custody_read",
            "exact_resident_runtime_launch_provenance_read",
            "exact_sentientosd_child_lifecycle_observation",
            "bounded_exact_sentientosd_child_custody",
            "bounded_exact_sentientosd_process_death_recovery",
            "exact_post_restart_resident_readiness_read",
            "maintenance_resident_parent_supervision_receipt_write",
            "read_only_maintenance_resident_parent_supervision_health_projection",
        }),
        forbidden_goal_phrases=(
            "generic service restart", "arbitrary service restart",
            "generic process supervision", "arbitrary process restart",
            "arbitrary process kill", "arbitrary pid", "caller-selected pid",
            "arbitrary executable", "arbitrary command", "shell command",
            "arbitrary argv", "arbitrary environment", "arbitrary cwd",
            "caller-selected executable", "caller-selected repository",
            "caller-selected commit", "caller-selected generation",
            "newest commit", "newest generation", "latest branch",
            "generation skipping", "non-consecutive generation recovery",
            "bypass resident transaction custody", "bypass launch provenance",
            "bypass resident readiness", "unlimited restart",
            "unlimited self-healing", "restart loops", "hot reload",
            "module reload", "dynamic code injection", "monkeypatch adoption",
            "systemd", "generic os service-manager control",
            "windows service control", "generic subprocess authority",
            "generic runtimesupervisor widening", "generic real_service_restart",
            "git mutation", "git fetch", "git pull", "git checkout",
            "git publication", "repository mutation", "provider invocation",
            "network authority", "credential management", "candidate admission",
            "maintenance lease issuance", "authority widening",
            "authority expiry extension", "automatic rollback",
            "rollback to arbitrary", "rollback to older code",
        ),
        required_goal_phrases=(
            "exact sentientosd child", "resident transaction custody",
            "bounded parent supervision", "process-death recovery",
            "exact resident launch provenance", "post-restart resident readiness",
            "exact maintenance-lineage",
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
    authority_definitions: Mapping[str, TaskAuthorityDefinition] | None = None,
) -> tuple[str, ...]:
    """Return deterministic blockers; an empty tuple means definition eligibility.

    Eligibility is not a grant and cannot be presented as effect authority.
    """
    definitions = AUTHORITY_DEFINITIONS if authority_definitions is None else authority_definitions
    definition = definitions.get(capability_id)
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
