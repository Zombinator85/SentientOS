"""Metadata-only federated improvement candidate evidence.

This module defines a bounded artifact for sharing local improvement evidence
between SentientOS nodes.  It never installs, applies, executes, merges,
routes, schedules, adopts, exports, prompts, or grants runtime authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence


class FederatedImprovementCandidateStatus:
    FEDERATED_IMPROVEMENT_CANDIDATE_READY = "federated_improvement_candidate_ready"
    FEDERATED_IMPROVEMENT_CANDIDATE_READY_WITH_CONDITIONS = (
        "federated_improvement_candidate_ready_with_conditions"
    )
    FEDERATED_IMPROVEMENT_CANDIDATE_BLOCKED = "federated_improvement_candidate_blocked"
    FEDERATED_IMPROVEMENT_CANDIDATE_INCOMPLETE = "federated_improvement_candidate_incomplete"
    FEDERATED_IMPROVEMENT_CANDIDATE_CONTRADICTED = "federated_improvement_candidate_contradicted"


class FederatedImprovementCandidateKind:
    MEMORY_DISTILLATION_IMPROVEMENT = "memory_distillation_improvement"
    CONTEXT_SELECTION_IMPROVEMENT = "context_selection_improvement"
    EMBODIMENT_GUARD_IMPROVEMENT = "embodiment_guard_improvement"
    AUDIT_INTEGRITY_IMPROVEMENT = "audit_integrity_improvement"
    INSTALLER_BOOTSTRAP_IMPROVEMENT = "installer_bootstrap_improvement"
    FEDERATION_PROTOCOL_IMPROVEMENT = "federation_protocol_improvement"
    GENESIS_FORGE_SCAFFOLD_IMPROVEMENT = "genesis_forge_scaffold_improvement"
    CODEX_REPAIR_IMPROVEMENT = "codex_repair_improvement"
    POLICY_GATE_IMPROVEMENT = "policy_gate_improvement"
    DOCUMENTATION_OR_DEMO_IMPROVEMENT = "documentation_or_demo_improvement"


CANDIDATE_STATUSES = (
    FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_READY,
    FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_READY_WITH_CONDITIONS,
    FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_BLOCKED,
    FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_INCOMPLETE,
    FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_CONTRADICTED,
)

CANDIDATE_KINDS = (
    FederatedImprovementCandidateKind.MEMORY_DISTILLATION_IMPROVEMENT,
    FederatedImprovementCandidateKind.CONTEXT_SELECTION_IMPROVEMENT,
    FederatedImprovementCandidateKind.EMBODIMENT_GUARD_IMPROVEMENT,
    FederatedImprovementCandidateKind.AUDIT_INTEGRITY_IMPROVEMENT,
    FederatedImprovementCandidateKind.INSTALLER_BOOTSTRAP_IMPROVEMENT,
    FederatedImprovementCandidateKind.FEDERATION_PROTOCOL_IMPROVEMENT,
    FederatedImprovementCandidateKind.GENESIS_FORGE_SCAFFOLD_IMPROVEMENT,
    FederatedImprovementCandidateKind.CODEX_REPAIR_IMPROVEMENT,
    FederatedImprovementCandidateKind.POLICY_GATE_IMPROVEMENT,
    FederatedImprovementCandidateKind.DOCUMENTATION_OR_DEMO_IMPROVEMENT,
)

_READY_VERIFICATION = frozenset({"verified", "passed", "ok", "not_required_with_reason"})
_FAILED_VERIFICATION = frozenset({"failed", "failure", "invalid", "contradicted"})
_COMPATIBLE_POSTURES = frozenset({"compatible", "compatible_with_conditions", "local_review_required"})
_CONTRADICTED_COMPATIBILITY = frozenset({"incompatible", "contradicted", "forced_adoption_required"})
_PASSING_TEST_RESULTS = frozenset({"passed", "ok", "warning", "not_required_with_reason"})
_FORBIDDEN_ADOPTION_MARKERS = (
    "adopt_on_receipt",
    "auto_adopt",
    "auto-adopt",
    "autoadopt",
    "auto_update",
    "auto-update",
    "forced_update",
    "forced_adoption",
    "install_on_receipt",
    "apply_on_receipt",
    "merge_on_receipt",
    "execute_on_receipt",
    "remote_execution",
    "remote-execution",
    "remote_execute",
    "schedule_on_receipt",
    "route_on_receipt",
)
_PROVIDER_NETWORK_EXPORT_RUNTIME_PROMPT_MARKERS = (
    "provider",
    "llm_call",
    "model_call",
    "network",
    "http://",
    "https://",
    "socket",
    "webhook",
    "export_payload",
    "runtime_handle",
    "runtime_authority",
    "tool_call",
    "function_call",
    "memory_handle",
    "routing_handle",
    "execution_handle",
    "prompt_text",
    "system_prompt",
    "assembled_prompt",
    "raw_prompt",
)
_SECRET_ENDPOINT_CLIENT_MARKERS = (
    "api_key",
    "apikey",
    "secret",
    "credential",
    "authorization",
    "bearer",
    "access_token",
    "refresh_token",
    "endpoint",
    "base_url",
    "client_handle",
    "provider_client",
    "sdk_client",
    "session_handle",
)
_LOCAL_GOVERNANCE_BYPASS_MARKERS = (
    "bypass_governance",
    "governance_bypass",
    "skip_review",
    "skip_local_review",
    "bypass_review_gate",
    "ignore_review_gate",
    "canonical_gate_bypass",
    "control_plane_bypass",
)
_RAW_PAYLOAD_MARKERS = (
    "diff --git",
    "patch_body",
    "raw_patch",
    "executable_payload",
    "script_body",
    "code_payload",
)


@dataclass(frozen=True)
class CandidateTestEvidence:
    command_label: str
    result_label: str


@dataclass(frozen=True)
class CandidateValidation:
    status: str
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FederatedImprovementCandidate:
    producing_node_id: str
    local_candidate_id: str
    candidate_kind: str
    source_amendment_or_proposal_id: str = ""
    source_commit_ref_digest: str = ""
    rationale_digest_or_label: str = ""
    test_evidence: tuple[CandidateTestEvidence, ...] = field(default_factory=tuple)
    rehearsal_artifact_refs: tuple[str, ...] = field(default_factory=tuple)
    audit_verification_status: str = "unknown"
    immutable_verification_status: str = "unknown"
    federation_compatibility_posture: str = "local_review_required"
    required_local_review_gates: tuple[str, ...] = field(default_factory=tuple)
    adoption_constraints: tuple[str, ...] = field(default_factory=tuple)
    known_risk_codes: tuple[str, ...] = field(default_factory=tuple)
    lineage_refs: tuple[str, ...] = field(default_factory=tuple)
    require_audit_verification: bool = True
    require_immutable_verification: bool = True
    require_test_or_rehearsal_evidence: bool = True
    metadata_only: bool = True
    locally_produced: bool = True
    transmissible_evidence_only: bool = True
    not_adopted_by_default: bool = True
    not_executable_by_receipt: bool = True
    no_remote_authority: bool = True
    no_forced_update: bool = True
    no_provider_network_export_prompt_runtime_authority: bool = True
    no_secret_endpoint_client_material: bool = True


def _is_dataclass_instance(value: Any) -> bool:
    return is_dataclass(value) and not isinstance(value, type)


def _stable(value: Any) -> Any:
    if _is_dataclass_instance(value):
        return {str(key): _stable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _stable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list)):
        return [_stable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_stable(item) for item in value)
    return value


def _walk_values(value: Any) -> tuple[str, ...]:
    found: list[str] = []

    def visit(child: Any) -> None:
        if _is_dataclass_instance(child):
            visit(asdict(child))
        elif isinstance(child, Mapping):
            for nested in child.values():
                visit(nested)
        elif isinstance(child, (tuple, list, set, frozenset)):
            for nested in child:
                visit(nested)
        elif isinstance(child, str):
            found.append(child)
        else:
            return

    visit(value)
    return tuple(found)


def _contains_marker(candidate: FederatedImprovementCandidate, markers: Sequence[str]) -> bool:
    lowered = tuple(item.lower() for item in _walk_values(candidate))
    return any(marker in item for marker in markers for item in lowered)


def _has_source_or_lineage(candidate: FederatedImprovementCandidate) -> bool:
    return bool(
        candidate.source_amendment_or_proposal_id
        or candidate.source_commit_ref_digest
        or candidate.lineage_refs
    )


def _has_test_or_rehearsal_evidence(candidate: FederatedImprovementCandidate) -> bool:
    return bool(candidate.test_evidence or candidate.rehearsal_artifact_refs)


def _tests_are_not_failed(candidate: FederatedImprovementCandidate) -> bool:
    return all(evidence.result_label in _PASSING_TEST_RESULTS for evidence in candidate.test_evidence)


def compute_federated_improvement_candidate_digest(candidate: FederatedImprovementCandidate) -> str:
    payload = _stable(candidate)
    serialised = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialised).hexdigest()


def validate_federated_improvement_candidate(candidate: FederatedImprovementCandidate) -> CandidateValidation:
    blockers: list[str] = []
    warnings: list[str] = []

    if not candidate.producing_node_id:
        blockers.append("missing_producing_node_id")
    if not candidate.local_candidate_id:
        blockers.append("missing_local_candidate_id")
    if candidate.candidate_kind not in CANDIDATE_KINDS:
        blockers.append("unknown_candidate_kind")
    if not _has_source_or_lineage(candidate):
        blockers.append("missing_lineage_or_source_evidence")
    if candidate.require_audit_verification and candidate.audit_verification_status not in _READY_VERIFICATION:
        blockers.append("audit_verification_not_satisfied")
    if candidate.audit_verification_status in _FAILED_VERIFICATION:
        blockers.append("audit_verification_failed")
    if candidate.require_immutable_verification and candidate.immutable_verification_status not in _READY_VERIFICATION:
        blockers.append("immutable_verification_not_satisfied")
    if candidate.immutable_verification_status in _FAILED_VERIFICATION:
        blockers.append("immutable_verification_failed")
    if candidate.require_test_or_rehearsal_evidence and not _has_test_or_rehearsal_evidence(candidate):
        blockers.append("missing_test_or_rehearsal_evidence")
    if not _tests_are_not_failed(candidate):
        blockers.append("test_evidence_failed")
    if candidate.federation_compatibility_posture in _CONTRADICTED_COMPATIBILITY:
        blockers.append("federation_compatibility_contradiction")
    elif candidate.federation_compatibility_posture not in _COMPATIBLE_POSTURES:
        warnings.append("federation_compatibility_unknown")

    invariant_checks = {
        "metadata_only_false": candidate.metadata_only,
        "locally_produced_false": candidate.locally_produced,
        "transmissible_evidence_only_false": candidate.transmissible_evidence_only,
        "not_adopted_by_default_false": candidate.not_adopted_by_default,
        "not_executable_by_receipt_false": candidate.not_executable_by_receipt,
        "remote_authority_present": candidate.no_remote_authority,
        "forced_update_present": candidate.no_forced_update,
        "provider_network_export_prompt_runtime_authority_present": (
            candidate.no_provider_network_export_prompt_runtime_authority
        ),
        "secret_endpoint_client_material_present": candidate.no_secret_endpoint_client_material,
    }
    for code, allowed in invariant_checks.items():
        if not allowed:
            blockers.append(code)

    if _contains_marker(candidate, _FORBIDDEN_ADOPTION_MARKERS):
        blockers.append("forbidden_adoption_or_remote_execution_marker")
    if _contains_marker(candidate, _PROVIDER_NETWORK_EXPORT_RUNTIME_PROMPT_MARKERS):
        blockers.append("provider_network_export_runtime_prompt_marker")
    if _contains_marker(candidate, _SECRET_ENDPOINT_CLIENT_MARKERS):
        blockers.append("secret_endpoint_client_marker")
    if _contains_marker(candidate, _LOCAL_GOVERNANCE_BYPASS_MARKERS):
        blockers.append("local_governance_gate_bypass_marker")
    if _contains_marker(candidate, _RAW_PAYLOAD_MARKERS):
        blockers.append("raw_or_executable_payload_marker")

    unique_blockers = tuple(dict.fromkeys(blockers))
    unique_warnings = tuple(dict.fromkeys(warnings))
    return CandidateValidation(
        status=_derive_status(candidate, unique_blockers, unique_warnings),
        blockers=unique_blockers,
        warnings=unique_warnings,
    )


def _derive_status(
    candidate: FederatedImprovementCandidate,
    blockers: tuple[str, ...],
    warnings: tuple[str, ...],
) -> str:
    contradiction_codes = (
        "forbidden_adoption_or_remote_execution_marker",
        "provider_network_export_runtime_prompt_marker",
        "secret_endpoint_client_marker",
        "federation_compatibility_contradiction",
        "local_governance_gate_bypass_marker",
        "raw_or_executable_payload_marker",
        "metadata_only_false",
        "locally_produced_false",
        "transmissible_evidence_only_false",
        "not_adopted_by_default_false",
        "not_executable_by_receipt_false",
        "remote_authority_present",
        "forced_update_present",
        "provider_network_export_prompt_runtime_authority_present",
        "secret_endpoint_client_material_present",
    )
    incomplete_codes = (
        "missing_producing_node_id",
        "missing_local_candidate_id",
        "missing_lineage_or_source_evidence",
        "missing_test_or_rehearsal_evidence",
        "unknown_candidate_kind",
    )
    if any(code in blockers for code in contradiction_codes):
        return FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_CONTRADICTED
    if any(code in blockers for code in incomplete_codes):
        return FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_INCOMPLETE
    if blockers:
        return FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_BLOCKED
    if warnings or candidate.required_local_review_gates or candidate.adoption_constraints:
        return FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_READY_WITH_CONDITIONS
    return FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_READY


def summarize_federated_improvement_candidate(candidate: FederatedImprovementCandidate) -> dict[str, object]:
    validation = validate_federated_improvement_candidate(candidate)
    return {
        "producing_node_id": candidate.producing_node_id,
        "local_candidate_id": candidate.local_candidate_id,
        "candidate_kind": candidate.candidate_kind,
        "status": validation.status,
        "digest": compute_federated_improvement_candidate_digest(candidate),
        "source_amendment_or_proposal_id": candidate.source_amendment_or_proposal_id,
        "source_commit_ref_digest": candidate.source_commit_ref_digest,
        "rationale_digest_or_label": candidate.rationale_digest_or_label,
        "test_evidence_count": len(candidate.test_evidence),
        "test_result_labels": tuple(evidence.result_label for evidence in candidate.test_evidence),
        "rehearsal_artifact_ref_count": len(candidate.rehearsal_artifact_refs),
        "audit_verification_status": candidate.audit_verification_status,
        "immutable_verification_status": candidate.immutable_verification_status,
        "federation_compatibility_posture": candidate.federation_compatibility_posture,
        "required_local_review_gate_count": len(candidate.required_local_review_gates),
        "adoption_constraint_count": len(candidate.adoption_constraints),
        "known_risk_code_count": len(candidate.known_risk_codes),
        "lineage_ref_count": len(candidate.lineage_refs),
        "metadata_only": candidate.metadata_only,
        "locally_produced": candidate.locally_produced,
        "transmissible_evidence_only": candidate.transmissible_evidence_only,
        "not_adopted_by_default": candidate.not_adopted_by_default,
        "not_executable_by_receipt": candidate.not_executable_by_receipt,
        "no_remote_authority": candidate.no_remote_authority,
        "no_forced_update": candidate.no_forced_update,
        "no_provider_network_export_prompt_runtime_authority": (
            candidate.no_provider_network_export_prompt_runtime_authority
        ),
        "no_secret_endpoint_client_material": candidate.no_secret_endpoint_client_material,
        "blocker_count": len(validation.blockers),
        "warning_count": len(validation.warnings),
    }


def explain_federated_improvement_candidate(candidate: FederatedImprovementCandidate) -> tuple[str, ...]:
    validation = validate_federated_improvement_candidate(candidate)
    explanation = [
        f"status:{validation.status}",
        f"candidate_kind:{candidate.candidate_kind}",
        f"digest:{compute_federated_improvement_candidate_digest(candidate)}",
        "custody:local_production_required",
        "receipt:inspection_rehearsal_adaptation_rejection_or_separate_local_adoption_only",
        "authority:no_install_no_apply_no_execute_no_merge_no_route_no_schedule_no_remote_authority",
    ]
    explanation.extend(f"blocker:{code}" for code in validation.blockers)
    explanation.extend(f"warning:{code}" for code in validation.warnings)
    return tuple(explanation)


def federated_improvement_candidate_is_metadata_only(candidate: FederatedImprovementCandidate) -> bool:
    validation = validate_federated_improvement_candidate(candidate)
    return candidate.metadata_only and "raw_or_executable_payload_marker" not in validation.blockers


def federated_improvement_candidate_is_transmissible_evidence_only(
    candidate: FederatedImprovementCandidate,
) -> bool:
    validation = validate_federated_improvement_candidate(candidate)
    return (
        candidate.transmissible_evidence_only
        and candidate.not_adopted_by_default
        and candidate.not_executable_by_receipt
        and validation.status
        in {
            FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_READY,
            FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_READY_WITH_CONDITIONS,
        }
    )


def federated_improvement_candidate_has_no_remote_authority(candidate: FederatedImprovementCandidate) -> bool:
    validation = validate_federated_improvement_candidate(candidate)
    return (
        candidate.no_remote_authority
        and candidate.no_forced_update
        and candidate.no_provider_network_export_prompt_runtime_authority
        and candidate.no_secret_endpoint_client_material
        and not any(
            code in validation.blockers
            for code in (
                "forbidden_adoption_or_remote_execution_marker",
                "provider_network_export_runtime_prompt_marker",
                "secret_endpoint_client_marker",
                "local_governance_gate_bypass_marker",
            )
        )
    )


def federated_improvement_candidate_ready_for_receipt_inspection(
    candidate: FederatedImprovementCandidate,
) -> bool:
    validation = validate_federated_improvement_candidate(candidate)
    return validation.status in {
        FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_READY,
        FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_READY_WITH_CONDITIONS,
    }


__all__ = [
    "CandidateTestEvidence",
    "CandidateValidation",
    "CANDIDATE_KINDS",
    "CANDIDATE_STATUSES",
    "FederatedImprovementCandidate",
    "FederatedImprovementCandidateKind",
    "FederatedImprovementCandidateStatus",
    "compute_federated_improvement_candidate_digest",
    "explain_federated_improvement_candidate",
    "federated_improvement_candidate_has_no_remote_authority",
    "federated_improvement_candidate_is_metadata_only",
    "federated_improvement_candidate_is_transmissible_evidence_only",
    "federated_improvement_candidate_ready_for_receipt_inspection",
    "summarize_federated_improvement_candidate",
    "validate_federated_improvement_candidate",
]
