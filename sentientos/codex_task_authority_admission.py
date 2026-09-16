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
