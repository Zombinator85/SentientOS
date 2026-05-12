"""Receiving-node intake receipts for federated improvement candidates.

The receipt in this module is metadata-only and intake-only.  It classifies a
received :class:`FederatedImprovementCandidate` for local inspection,
rehearsal, adaptation, rejection, or separate local governance review without
installing, applying, executing, merging, routing, scheduling, adopting,
exporting, prompting, or granting runtime authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from .improvement_candidate import (
    CANDIDATE_KINDS,
    FederatedImprovementCandidate,
    FederatedImprovementCandidateStatus,
    CandidateTestEvidence,
    compute_federated_improvement_candidate_digest,
    validate_federated_improvement_candidate,
)


class FederatedImprovementIntakeStatus:
    FEDERATED_IMPROVEMENT_INTAKE_READY_FOR_INSPECTION = (
        "federated_improvement_intake_ready_for_inspection"
    )
    FEDERATED_IMPROVEMENT_INTAKE_READY_FOR_REHEARSAL = (
        "federated_improvement_intake_ready_for_rehearsal"
    )
    FEDERATED_IMPROVEMENT_INTAKE_READY_WITH_CONDITIONS = (
        "federated_improvement_intake_ready_with_conditions"
    )
    FEDERATED_IMPROVEMENT_INTAKE_HOLD_FOR_LOCAL_REVIEW = (
        "federated_improvement_intake_hold_for_local_review"
    )
    FEDERATED_IMPROVEMENT_INTAKE_REJECTED = "federated_improvement_intake_rejected"
    FEDERATED_IMPROVEMENT_INTAKE_INCOMPLETE = "federated_improvement_intake_incomplete"
    FEDERATED_IMPROVEMENT_INTAKE_CONTRADICTED = "federated_improvement_intake_contradicted"


class FederatedImprovementIntakeDecision:
    INSPECT_ONLY = "inspect_only"
    REHEARSE_LOCALLY = "rehearse_locally"
    ADAPT_LOCALLY = "adapt_locally"
    REJECT_CANDIDATE = "reject_candidate"
    HOLD_FOR_OPERATOR_REVIEW = "hold_for_operator_review"
    QUEUE_FOR_LOCAL_GOVERNANCE_REVIEW = "queue_for_local_governance_review"


INTAKE_STATUSES = (
    FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_READY_FOR_INSPECTION,
    FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_READY_FOR_REHEARSAL,
    FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_READY_WITH_CONDITIONS,
    FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_HOLD_FOR_LOCAL_REVIEW,
    FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_REJECTED,
    FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_INCOMPLETE,
    FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_CONTRADICTED,
)

INTAKE_DECISIONS = (
    FederatedImprovementIntakeDecision.INSPECT_ONLY,
    FederatedImprovementIntakeDecision.REHEARSE_LOCALLY,
    FederatedImprovementIntakeDecision.ADAPT_LOCALLY,
    FederatedImprovementIntakeDecision.REJECT_CANDIDATE,
    FederatedImprovementIntakeDecision.HOLD_FOR_OPERATOR_REVIEW,
    FederatedImprovementIntakeDecision.QUEUE_FOR_LOCAL_GOVERNANCE_REVIEW,
)

_READY_CANDIDATE_STATUSES = frozenset(
    {
        FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_READY,
        FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_READY_WITH_CONDITIONS,
    }
)
_HOLD_OR_REJECT_DECISIONS = frozenset(
    {
        FederatedImprovementIntakeDecision.REJECT_CANDIDATE,
        FederatedImprovementIntakeDecision.HOLD_FOR_OPERATOR_REVIEW,
        FederatedImprovementIntakeDecision.QUEUE_FOR_LOCAL_GOVERNANCE_REVIEW,
    }
)
_COMPATIBLE_LOCAL_POSTURES = frozenset(
    {"compatible", "compatible_with_conditions", "local_review_required"}
)
_INCOMPATIBLE_LOCAL_POSTURES = frozenset(
    {"incompatible", "contradicted", "forced_adoption_required"}
)
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
class FederatedImprovementIntakeValidation:
    status: str
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FederatedImprovementIntakeReceipt:
    receiving_node_id: str
    producing_node_id: str
    source_candidate_id: str
    candidate_digest: str
    expected_candidate_digest: str
    candidate_kind: str
    candidate_status: str
    candidate_compatibility_posture: str
    candidate_audit_verification_status: str
    candidate_immutable_verification_status: str
    local_compatibility_posture: str
    local_policy_posture: str
    required_local_review_gates: tuple[str, ...] = field(default_factory=tuple)
    accepted_gate_codes: tuple[str, ...] = field(default_factory=tuple)
    rejected_gate_codes: tuple[str, ...] = field(default_factory=tuple)
    pending_gate_codes: tuple[str, ...] = field(default_factory=tuple)
    local_rehearsal_required: bool = False
    local_adaptation_required: bool = False
    rejection_reason_codes: tuple[str, ...] = field(default_factory=tuple)
    warning_codes: tuple[str, ...] = field(default_factory=tuple)
    lineage_refs: tuple[str, ...] = field(default_factory=tuple)
    intake_decision: str = FederatedImprovementIntakeDecision.INSPECT_ONLY
    metadata_only: bool = True
    intake_only: bool = True
    local_custody_preserved: bool = True
    candidate_not_adopted: bool = True
    candidate_not_executed: bool = True
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

    visit(value)
    return tuple(found)


def _contains_marker(value: Any, markers: Sequence[str]) -> bool:
    lowered = tuple(item.lower() for item in _walk_values(value))
    return any(marker in item for marker in markers for item in lowered)


def _tuple_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(str(item) for item in value if str(item))
    return (str(value),) if str(value) else ()


def _coerce_test_evidence(value: Any) -> tuple[CandidateTestEvidence, ...]:
    evidence: list[CandidateTestEvidence] = []
    for item in value or ():
        if isinstance(item, CandidateTestEvidence):
            evidence.append(item)
        elif isinstance(item, Mapping):
            evidence.append(
                CandidateTestEvidence(
                    command_label=str(item.get("command_label", "")),
                    result_label=str(item.get("result_label", "")),
                )
            )
    return tuple(evidence)


def _candidate_from_mapping(mapping: Mapping[str, Any]) -> FederatedImprovementCandidate | None:
    candidate_fields = {item.name for item in fields(FederatedImprovementCandidate)}
    if not any(key in mapping for key in ("producing_node_id", "local_candidate_id", "candidate_kind")):
        return None
    values = {key: mapping[key] for key in candidate_fields if key in mapping}
    values["test_evidence"] = _coerce_test_evidence(values.get("test_evidence", ()))
    for tuple_key in (
        "rehearsal_artifact_refs",
        "required_local_review_gates",
        "adoption_constraints",
        "known_risk_codes",
        "lineage_refs",
    ):
        values[tuple_key] = _tuple_of_strings(values.get(tuple_key, ()))
    for required in ("producing_node_id", "local_candidate_id", "candidate_kind"):
        values.setdefault(required, "")
    try:
        return FederatedImprovementCandidate(**values)
    except TypeError:
        return None


def _candidate_metadata(candidate: FederatedImprovementCandidate | Mapping[str, Any] | None) -> dict[str, Any]:
    if candidate is None:
        return {}
    if isinstance(candidate, FederatedImprovementCandidate):
        validation = validate_federated_improvement_candidate(candidate)
        return {
            "candidate": candidate,
            "producing_node_id": candidate.producing_node_id,
            "source_candidate_id": candidate.local_candidate_id,
            "candidate_kind": candidate.candidate_kind,
            "candidate_digest": compute_federated_improvement_candidate_digest(candidate),
            "candidate_status": validation.status,
            "candidate_compatibility_posture": candidate.federation_compatibility_posture,
            "candidate_audit_verification_status": candidate.audit_verification_status,
            "candidate_immutable_verification_status": candidate.immutable_verification_status,
            "required_local_review_gates": candidate.required_local_review_gates,
            "lineage_refs": candidate.lineage_refs,
            "candidate_blockers": validation.blockers,
            "candidate_warnings": validation.warnings,
        }
    if not isinstance(candidate, Mapping):
        return {}
    coerced = _candidate_from_mapping(candidate)
    if coerced is not None:
        metadata = _candidate_metadata(coerced)
        metadata["candidate_digest"] = str(candidate.get("candidate_digest") or metadata["candidate_digest"])
        metadata["candidate_status"] = str(candidate.get("candidate_status") or metadata["candidate_status"])
        return metadata
    return {
        "producing_node_id": str(candidate.get("producing_node_id", "")),
        "source_candidate_id": str(candidate.get("source_candidate_id", candidate.get("local_candidate_id", ""))),
        "candidate_kind": str(candidate.get("candidate_kind", "")),
        "candidate_digest": str(candidate.get("candidate_digest", "")),
        "candidate_status": str(candidate.get("candidate_status", "")),
        "candidate_compatibility_posture": str(
            candidate.get("candidate_compatibility_posture", candidate.get("federation_compatibility_posture", ""))
        ),
        "candidate_audit_verification_status": str(candidate.get("candidate_audit_verification_status", "")),
        "candidate_immutable_verification_status": str(candidate.get("candidate_immutable_verification_status", "")),
        "required_local_review_gates": _tuple_of_strings(candidate.get("required_local_review_gates", ())),
        "lineage_refs": _tuple_of_strings(candidate.get("lineage_refs", ())),
        "candidate_blockers": _tuple_of_strings(candidate.get("candidate_blockers", ())),
        "candidate_warnings": _tuple_of_strings(candidate.get("candidate_warnings", ())),
        "raw_mapping": candidate,
    }


def build_federated_improvement_intake_receipt(
    *,
    receiving_node_id: str,
    candidate: FederatedImprovementCandidate | Mapping[str, Any] | None,
    intake_decision: str = FederatedImprovementIntakeDecision.INSPECT_ONLY,
    expected_candidate_digest: str = "",
    local_compatibility_posture: str = "local_review_required",
    local_policy_posture: str = "local_governance_required",
    accepted_gate_codes: Sequence[str] = (),
    rejected_gate_codes: Sequence[str] = (),
    pending_gate_codes: Sequence[str] = (),
    local_rehearsal_required: bool = False,
    local_adaptation_required: bool = False,
    rejection_reason_codes: Sequence[str] = (),
    warning_codes: Sequence[str] = (),
) -> FederatedImprovementIntakeReceipt:
    metadata = _candidate_metadata(candidate)
    candidate_digest = str(metadata.get("candidate_digest", ""))
    expected_digest = expected_candidate_digest or candidate_digest
    candidate_rejections = _tuple_of_strings(metadata.get("candidate_blockers", ()))
    candidate_warnings = _tuple_of_strings(metadata.get("candidate_warnings", ()))
    return FederatedImprovementIntakeReceipt(
        receiving_node_id=receiving_node_id,
        producing_node_id=str(metadata.get("producing_node_id", "")),
        source_candidate_id=str(metadata.get("source_candidate_id", "")),
        candidate_digest=candidate_digest,
        expected_candidate_digest=expected_digest,
        candidate_kind=str(metadata.get("candidate_kind", "")),
        candidate_status=str(metadata.get("candidate_status", "")),
        candidate_compatibility_posture=str(metadata.get("candidate_compatibility_posture", "")),
        candidate_audit_verification_status=str(metadata.get("candidate_audit_verification_status", "")),
        candidate_immutable_verification_status=str(metadata.get("candidate_immutable_verification_status", "")),
        local_compatibility_posture=local_compatibility_posture,
        local_policy_posture=local_policy_posture,
        required_local_review_gates=_tuple_of_strings(metadata.get("required_local_review_gates", ())),
        accepted_gate_codes=_tuple_of_strings(accepted_gate_codes),
        rejected_gate_codes=_tuple_of_strings(rejected_gate_codes),
        pending_gate_codes=_tuple_of_strings(pending_gate_codes),
        local_rehearsal_required=local_rehearsal_required,
        local_adaptation_required=local_adaptation_required,
        rejection_reason_codes=tuple(dict.fromkeys((*candidate_rejections, *_tuple_of_strings(rejection_reason_codes)))),
        warning_codes=tuple(dict.fromkeys((*candidate_warnings, *_tuple_of_strings(warning_codes)))),
        lineage_refs=_tuple_of_strings(metadata.get("lineage_refs", ())),
        intake_decision=intake_decision,
    )


def compute_federated_improvement_intake_receipt_digest(receipt: FederatedImprovementIntakeReceipt) -> str:
    payload = _stable(receipt)
    serialised = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialised).hexdigest()


def validate_federated_improvement_intake_receipt(
    receipt: FederatedImprovementIntakeReceipt,
) -> FederatedImprovementIntakeValidation:
    blockers: list[str] = []
    warnings: list[str] = list(receipt.warning_codes)

    if not receipt.receiving_node_id:
        blockers.append("missing_receiving_node_id")
    if not receipt.producing_node_id or not receipt.source_candidate_id or not receipt.candidate_kind:
        blockers.append("missing_candidate_metadata")
    if receipt.candidate_kind and receipt.candidate_kind not in CANDIDATE_KINDS:
        blockers.append("unknown_candidate_kind")
    if not receipt.candidate_digest or not receipt.expected_candidate_digest:
        blockers.append("missing_candidate_digest")
    elif receipt.candidate_digest != receipt.expected_candidate_digest:
        blockers.append("candidate_digest_mismatch")
    if not receipt.candidate_status:
        blockers.append("missing_candidate_status")
    elif receipt.candidate_status == FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_CONTRADICTED:
        blockers.append("candidate_contradicted_status")
    elif receipt.candidate_status == FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_INCOMPLETE:
        blockers.append("candidate_validation_failure")
    elif receipt.candidate_status == FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_BLOCKED:
        if receipt.intake_decision not in _HOLD_OR_REJECT_DECISIONS:
            blockers.append("blocked_candidate_requires_reject_or_hold")
        else:
            warnings.append("blocked_candidate_held_or_rejected")
    elif receipt.candidate_status not in _READY_CANDIDATE_STATUSES:
        blockers.append("candidate_validation_failure")

    if receipt.candidate_compatibility_posture in _INCOMPATIBLE_LOCAL_POSTURES:
        blockers.append("incompatible_federation_posture")
    if receipt.local_compatibility_posture in _INCOMPATIBLE_LOCAL_POSTURES:
        blockers.append("incompatible_local_posture")
    elif receipt.local_compatibility_posture not in _COMPATIBLE_LOCAL_POSTURES:
        warnings.append("local_compatibility_unknown")

    reviewed_gates = set(receipt.accepted_gate_codes) | set(receipt.rejected_gate_codes) | set(receipt.pending_gate_codes)
    missing_gates = tuple(gate for gate in receipt.required_local_review_gates if gate not in reviewed_gates)
    if missing_gates:
        blockers.append("missing_required_local_review_gates")
    if receipt.rejected_gate_codes and receipt.intake_decision != FederatedImprovementIntakeDecision.REJECT_CANDIDATE:
        blockers.append("rejected_gate_requires_reject_decision")
    if receipt.pending_gate_codes and receipt.intake_decision not in _HOLD_OR_REJECT_DECISIONS:
        blockers.append("pending_gate_requires_local_review_hold")
    if receipt.intake_decision not in INTAKE_DECISIONS:
        blockers.append("unknown_intake_decision")

    invariant_checks = {
        "metadata_only_false": receipt.metadata_only,
        "intake_only_false": receipt.intake_only,
        "local_custody_not_preserved": receipt.local_custody_preserved,
        "candidate_adopted_marker": receipt.candidate_not_adopted,
        "candidate_executed_marker": receipt.candidate_not_executed,
        "remote_authority_present": receipt.no_remote_authority,
        "forced_update_present": receipt.no_forced_update,
        "provider_network_export_prompt_runtime_authority_present": (
            receipt.no_provider_network_export_prompt_runtime_authority
        ),
        "secret_endpoint_client_material_present": receipt.no_secret_endpoint_client_material,
    }
    for code, allowed in invariant_checks.items():
        if not allowed:
            blockers.append(code)

    if _contains_marker(receipt, _FORBIDDEN_ADOPTION_MARKERS):
        blockers.append("forbidden_adoption_apply_install_merge_execute_marker")
    if _contains_marker(receipt, _PROVIDER_NETWORK_EXPORT_RUNTIME_PROMPT_MARKERS):
        blockers.append("provider_network_export_runtime_prompt_marker")
    if _contains_marker(receipt, _SECRET_ENDPOINT_CLIENT_MARKERS):
        blockers.append("secret_endpoint_client_marker")
    if _contains_marker(receipt, _LOCAL_GOVERNANCE_BYPASS_MARKERS):
        blockers.append("local_governance_bypass_marker")
    if _contains_marker(receipt, _RAW_PAYLOAD_MARKERS):
        blockers.append("raw_patch_or_executable_payload_marker")

    unique_blockers = tuple(dict.fromkeys(blockers))
    unique_warnings = tuple(dict.fromkeys(warnings))
    return FederatedImprovementIntakeValidation(
        status=_derive_intake_status(receipt, unique_blockers, unique_warnings),
        blockers=unique_blockers,
        warnings=unique_warnings,
    )


def _derive_intake_status(
    receipt: FederatedImprovementIntakeReceipt,
    blockers: tuple[str, ...],
    warnings: tuple[str, ...],
) -> str:
    incomplete_codes = {
        "missing_receiving_node_id",
        "missing_candidate_metadata",
        "missing_candidate_digest",
        "missing_candidate_status",
        "unknown_candidate_kind",
    }
    contradiction_codes = {
        "candidate_digest_mismatch",
        "candidate_contradicted_status",
        "incompatible_federation_posture",
        "incompatible_local_posture",
        "local_governance_bypass_marker",
        "forbidden_adoption_apply_install_merge_execute_marker",
        "provider_network_export_runtime_prompt_marker",
        "secret_endpoint_client_marker",
        "raw_patch_or_executable_payload_marker",
        "metadata_only_false",
        "intake_only_false",
        "local_custody_not_preserved",
        "candidate_adopted_marker",
        "candidate_executed_marker",
        "remote_authority_present",
        "forced_update_present",
        "provider_network_export_prompt_runtime_authority_present",
        "secret_endpoint_client_material_present",
    }
    if any(code in blockers for code in contradiction_codes):
        return FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_CONTRADICTED
    if any(code in blockers for code in incomplete_codes):
        return FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_INCOMPLETE
    if receipt.intake_decision == FederatedImprovementIntakeDecision.REJECT_CANDIDATE:
        return FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_REJECTED
    if blockers or receipt.intake_decision in {
        FederatedImprovementIntakeDecision.HOLD_FOR_OPERATOR_REVIEW,
        FederatedImprovementIntakeDecision.QUEUE_FOR_LOCAL_GOVERNANCE_REVIEW,
    }:
        return FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_HOLD_FOR_LOCAL_REVIEW
    if receipt.intake_decision == FederatedImprovementIntakeDecision.REHEARSE_LOCALLY:
        return FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_READY_FOR_REHEARSAL
    if warnings or receipt.local_adaptation_required or receipt.local_rehearsal_required:
        return FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_READY_WITH_CONDITIONS
    if receipt.intake_decision == FederatedImprovementIntakeDecision.ADAPT_LOCALLY:
        return FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_READY_WITH_CONDITIONS
    return FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_READY_FOR_INSPECTION


def summarize_federated_improvement_intake_receipt(
    receipt: FederatedImprovementIntakeReceipt,
) -> dict[str, object]:
    validation = validate_federated_improvement_intake_receipt(receipt)
    return {
        "receiving_node_id": receipt.receiving_node_id,
        "producing_node_id": receipt.producing_node_id,
        "source_candidate_id": receipt.source_candidate_id,
        "candidate_digest": receipt.candidate_digest,
        "expected_candidate_digest": receipt.expected_candidate_digest,
        "receipt_digest": compute_federated_improvement_intake_receipt_digest(receipt),
        "candidate_kind": receipt.candidate_kind,
        "candidate_status": receipt.candidate_status,
        "intake_status": validation.status,
        "intake_decision": receipt.intake_decision,
        "candidate_compatibility_posture": receipt.candidate_compatibility_posture,
        "local_compatibility_posture": receipt.local_compatibility_posture,
        "local_policy_posture": receipt.local_policy_posture,
        "required_local_review_gate_count": len(receipt.required_local_review_gates),
        "accepted_gate_count": len(receipt.accepted_gate_codes),
        "rejected_gate_count": len(receipt.rejected_gate_codes),
        "pending_gate_count": len(receipt.pending_gate_codes),
        "local_rehearsal_required": receipt.local_rehearsal_required,
        "local_adaptation_required": receipt.local_adaptation_required,
        "rejection_reason_count": len(receipt.rejection_reason_codes),
        "warning_count": len(validation.warnings),
        "lineage_ref_count": len(receipt.lineage_refs),
        "metadata_only": receipt.metadata_only,
        "intake_only": receipt.intake_only,
        "local_custody_preserved": receipt.local_custody_preserved,
        "candidate_not_adopted": receipt.candidate_not_adopted,
        "candidate_not_executed": receipt.candidate_not_executed,
        "no_remote_authority": receipt.no_remote_authority,
        "no_forced_update": receipt.no_forced_update,
        "no_provider_network_export_prompt_runtime_authority": (
            receipt.no_provider_network_export_prompt_runtime_authority
        ),
        "no_secret_endpoint_client_material": receipt.no_secret_endpoint_client_material,
        "blocker_count": len(validation.blockers),
    }


def explain_federated_improvement_intake_receipt(
    receipt: FederatedImprovementIntakeReceipt,
) -> tuple[str, ...]:
    validation = validate_federated_improvement_intake_receipt(receipt)
    explanation = [
        f"status:{validation.status}",
        f"decision:{receipt.intake_decision}",
        f"candidate_digest:{receipt.candidate_digest}",
        f"receipt_digest:{compute_federated_improvement_intake_receipt_digest(receipt)}",
        "custody:receiving_node_local_custody_preserved",
        "scope:intake_only_no_adoption_no_execution_no_forced_update",
        "authority:no_remote_authority_no_provider_network_export_prompt_runtime_authority",
    ]
    explanation.extend(f"blocker:{code}" for code in validation.blockers)
    explanation.extend(f"warning:{code}" for code in validation.warnings)
    return tuple(explanation)


def federated_improvement_intake_receipt_is_metadata_only(
    receipt: FederatedImprovementIntakeReceipt,
) -> bool:
    validation = validate_federated_improvement_intake_receipt(receipt)
    return receipt.metadata_only and "raw_patch_or_executable_payload_marker" not in validation.blockers


def federated_improvement_intake_receipt_preserves_local_custody(
    receipt: FederatedImprovementIntakeReceipt,
) -> bool:
    validation = validate_federated_improvement_intake_receipt(receipt)
    return (
        receipt.intake_only
        and receipt.local_custody_preserved
        and receipt.candidate_not_adopted
        and receipt.candidate_not_executed
        and validation.status
        not in {
            FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_CONTRADICTED,
            FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_INCOMPLETE,
        }
    )


def federated_improvement_intake_receipt_has_no_remote_authority(
    receipt: FederatedImprovementIntakeReceipt,
) -> bool:
    validation = validate_federated_improvement_intake_receipt(receipt)
    return (
        receipt.no_remote_authority
        and receipt.no_forced_update
        and receipt.no_provider_network_export_prompt_runtime_authority
        and receipt.no_secret_endpoint_client_material
        and not any(
            code in validation.blockers
            for code in (
                "forbidden_adoption_apply_install_merge_execute_marker",
                "provider_network_export_runtime_prompt_marker",
                "secret_endpoint_client_marker",
                "local_governance_bypass_marker",
                "remote_authority_present",
                "forced_update_present",
            )
        )
    )


def federated_improvement_intake_receipt_allows_inspection(
    receipt: FederatedImprovementIntakeReceipt,
) -> bool:
    validation = validate_federated_improvement_intake_receipt(receipt)
    return validation.status in {
        FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_READY_FOR_INSPECTION,
        FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_READY_FOR_REHEARSAL,
        FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_READY_WITH_CONDITIONS,
        FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_HOLD_FOR_LOCAL_REVIEW,
    }


def federated_improvement_intake_receipt_allows_rehearsal(
    receipt: FederatedImprovementIntakeReceipt,
) -> bool:
    validation = validate_federated_improvement_intake_receipt(receipt)
    return validation.status == FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_READY_FOR_REHEARSAL


def federated_improvement_intake_receipt_allows_adaptation(
    receipt: FederatedImprovementIntakeReceipt,
) -> bool:
    validation = validate_federated_improvement_intake_receipt(receipt)
    return (
        receipt.intake_decision == FederatedImprovementIntakeDecision.ADAPT_LOCALLY
        and validation.status
        == FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_READY_WITH_CONDITIONS
    )


__all__ = [
    "FederatedImprovementIntakeDecision",
    "FederatedImprovementIntakeReceipt",
    "FederatedImprovementIntakeStatus",
    "FederatedImprovementIntakeValidation",
    "INTAKE_DECISIONS",
    "INTAKE_STATUSES",
    "build_federated_improvement_intake_receipt",
    "compute_federated_improvement_intake_receipt_digest",
    "explain_federated_improvement_intake_receipt",
    "federated_improvement_intake_receipt_allows_adaptation",
    "federated_improvement_intake_receipt_allows_inspection",
    "federated_improvement_intake_receipt_allows_rehearsal",
    "federated_improvement_intake_receipt_has_no_remote_authority",
    "federated_improvement_intake_receipt_is_metadata_only",
    "federated_improvement_intake_receipt_preserves_local_custody",
    "summarize_federated_improvement_intake_receipt",
    "validate_federated_improvement_intake_receipt",
]
