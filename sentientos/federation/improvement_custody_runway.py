from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from .improvement_intake_receipt import (
    FederatedImprovementIntakeReceipt,
    FederatedImprovementIntakeStatus,
    compute_federated_improvement_intake_receipt_digest,
)

_READY_VERIFICATION = frozenset({"verified", "passed", "ok", "not_required_with_reason"})
_FORBIDDEN = ("adopt_on_receipt","apply_on_receipt","install_on_receipt","merge_on_receipt","execute_on_receipt","schedule_on_receipt","route_on_receipt","forced_update")
_PROVIDER = ("provider","network","export","runtime","prompt_text","http://","https://")
_SECRET = ("secret","endpoint","client","api_key","credential")
_RAW = ("raw_patch","patch_body","diff --git","executable_payload")
_BYPASS = ("bypass_governance","skip_review","control_plane_bypass")

class FederatedImprovementRehearsalAuthorizationStatus:
    READY = "federated_improvement_rehearsal_ready"
    READY_WITH_CONDITIONS = "federated_improvement_rehearsal_ready_with_conditions"
    HOLD = "federated_improvement_rehearsal_hold_for_review"
    REJECTED = "federated_improvement_rehearsal_rejected"
    INCOMPLETE = "federated_improvement_rehearsal_incomplete"
    CONTRADICTED = "federated_improvement_rehearsal_contradicted"

class FederatedImprovementRehearsalScope:
    METADATA_ONLY = "metadata_only_rehearsal"
    DRY_RUN = "dry_run_rehearsal"
    SANDBOX = "sandbox_rehearsal"
    DOCUMENTATION = "documentation_rehearsal"
    COMPATIBILITY = "compatibility_rehearsal"

class FederatedImprovementRehearsalResultStatus:
    PASSED = "federated_improvement_rehearsal_result_passed"
    PASSED_WITH_WARNINGS = "federated_improvement_rehearsal_result_passed_with_warnings"
    FAILED = "federated_improvement_rehearsal_result_failed"
    INCOMPLETE = "federated_improvement_rehearsal_result_incomplete"
    CONTRADICTED = "federated_improvement_rehearsal_result_contradicted"

class FederatedImprovementLocalReviewStatus:
    ACCEPTED = "federated_improvement_local_review_accepted"
    ACCEPTED_WITH_CONDITIONS = "federated_improvement_local_review_accepted_with_conditions"
    REJECTED = "federated_improvement_local_review_rejected"
    HOLD = "federated_improvement_local_review_hold"
    INCOMPLETE = "federated_improvement_local_review_incomplete"
    CONTRADICTED = "federated_improvement_local_review_contradicted"

class FederatedImprovementLocalReviewDecision:
    ACCEPT = "accept_for_adoption_readiness"
    ACCEPT_WITH_CONDITIONS = "accept_with_conditions_for_adoption_readiness"
    REJECT = "reject_candidate"
    HOLD_OPERATOR = "hold_for_operator_review"
    HOLD_REHEARSAL = "hold_for_additional_rehearsal"
    HOLD_ADAPTATION = "hold_for_adaptation"

class FederatedImprovementAdoptionReadinessStatus:
    READY = "federated_improvement_adoption_readiness_ready"
    READY_WITH_CONDITIONS = "federated_improvement_adoption_readiness_ready_with_conditions"
    BLOCKED = "federated_improvement_adoption_readiness_blocked"
    INCOMPLETE = "federated_improvement_adoption_readiness_incomplete"
    CONTRADICTED = "federated_improvement_adoption_readiness_contradicted"

@dataclass(frozen=True)
class CustodyValidation:
    status: str
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _stable(v: Any) -> Any:
    if is_dataclass(v) and not isinstance(v, type):
        return {k: _stable(x) for k, x in asdict(v).items()}
    if isinstance(v, Mapping):
        return {str(k): _stable(x) for k, x in sorted(v.items(), key=lambda p: str(p[0]))}
    if isinstance(v, (tuple, list)):
        return [_stable(x) for x in v]
    return v

def _digest(v: Any) -> str:
    return hashlib.sha256(json.dumps(_stable(v), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def _walk(v: Any) -> tuple[str, ...]:
    vals=[]
    def visit(x: Any) -> None:
        if is_dataclass(x) and not isinstance(x, type):
            visit(asdict(x))
        elif isinstance(x, Mapping):
            for y in x.values():
                visit(y)
        elif isinstance(x, (tuple, list, set, frozenset)):
            for y in x:
                visit(y)
        elif isinstance(x, str):
            vals.append(x.lower())
    visit(v)
    return tuple(vals)

def _has(v: Any, markers: Sequence[str]) -> bool:
    vals=_walk(v)
    return any(m in t for m in markers for t in vals)

@dataclass(frozen=True)
class FederatedImprovementRehearsalAuthorization:
    receiving_node_id: str
    producing_node_id: str
    source_candidate_id: str
    source_candidate_digest: str
    intake_receipt_id: str
    intake_receipt_digest: str
    expected_intake_receipt_digest: str
    intake_status: str
    intake_decision: str
    candidate_kind: str
    local_compatibility_posture: str
    local_policy_posture: str
    rehearsal_scope: str
    rehearsal_command_labels: tuple[str, ...] = ()
    rehearsal_expected_result_labels: tuple[str, ...] = ()
    sandbox_profile_label: str = ""
    required_gate_codes: tuple[str, ...] = ()
    accepted_gate_codes: tuple[str, ...] = ()
    rejected_gate_codes: tuple[str, ...] = ()
    pending_gate_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    rejection_reason_codes: tuple[str, ...] = ()
    lineage_refs: tuple[str, ...] = ()
    metadata_only: bool = True
    no_adoption: bool = True
    no_execution: bool = True
    no_remote_authority: bool = True
    no_forced_update: bool = True
    no_provider_network_export_prompt_runtime_authority: bool = True
    no_secret_endpoint_client_material: bool = True

# similar other 3
@dataclass(frozen=True)
class FederatedImprovementRehearsalResult:
    rehearsal_authorization_id: str
    rehearsal_authorization_digest: str
    expected_rehearsal_authorization_digest: str
    receiving_node_id: str
    producing_node_id: str
    candidate_id: str
    candidate_digest: str
    candidate_kind: str
    rehearsal_scope: str
    command_labels: tuple[str, ...] = ()
    result_labels: tuple[str, ...] = ()
    pass_count: int = 0
    fail_count: int = 0
    warning_count: int = 0
    artifact_refs: tuple[str, ...] = ()
    audit_verification_status: str = "unknown"
    immutable_verification_status: str = "unknown"
    compatibility_result_label: str = ""
    risk_warning_codes: tuple[str, ...] = ()
    lineage_refs: tuple[str, ...] = ()
    metadata_only: bool = True
    no_adoption: bool = True
    no_execution: bool = True
    no_remote_authority: bool = True
    no_forced_update: bool = True
    no_provider_network_export_prompt_runtime_authority: bool = True
    no_secret_endpoint_client_material: bool = True

@dataclass(frozen=True)
class FederatedImprovementLocalReviewReceipt:
    local_reviewer_ref_label: str
    receiving_node_id: str
    producing_node_id: str
    candidate_id: str
    candidate_digest: str
    intake_receipt_id: str
    intake_receipt_digest: str
    rehearsal_authorization_id: str
    rehearsal_authorization_digest: str
    rehearsal_result_id: str
    rehearsal_result_digest: str
    required_gate_codes: tuple[str, ...] = ()
    accepted_gate_codes: tuple[str, ...] = ()
    rejected_gate_codes: tuple[str, ...] = ()
    pending_gate_codes: tuple[str, ...] = ()
    accepted_condition_codes: tuple[str, ...] = ()
    rejected_condition_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    rejection_reason_codes: tuple[str, ...] = ()
    review_expiration_label: str = ""
    lineage_refs: tuple[str, ...] = ()
    review_decision: str = FederatedImprovementLocalReviewDecision.HOLD_OPERATOR
    metadata_only: bool = True
    no_adoption: bool = True
    no_execution: bool = True
    no_remote_authority: bool = True
    no_forced_update: bool = True
    no_provider_network_export_prompt_runtime_authority: bool = True
    no_secret_endpoint_client_material: bool = True

@dataclass(frozen=True)
class FederatedImprovementAdoptionReadinessManifest:
    receiving_node_id: str
    producing_node_id: str
    candidate_id: str
    candidate_digest: str
    candidate_kind: str
    intake_receipt_id: str
    intake_receipt_digest: str
    rehearsal_authorization_id: str
    rehearsal_authorization_digest: str
    rehearsal_result_id: str
    rehearsal_result_digest: str
    local_review_receipt_id: str
    local_review_receipt_digest: str
    audit_verification_status: str
    immutable_verification_status: str
    compatibility_posture: str
    local_policy_posture: str
    required_future_adoption_gate_codes: tuple[str, ...] = ()
    accepted_gate_codes: tuple[str, ...] = ()
    rejected_gate_codes: tuple[str, ...] = ()
    pending_gate_codes: tuple[str, ...] = ()
    known_risk_codes: tuple[str, ...] = ()
    condition_codes: tuple[str, ...] = ()
    lineage_refs: tuple[str, ...] = ()
    adoption_not_occurred_statement: str = "adoption_has_not_occurred"
    metadata_only: bool = True
    no_adoption: bool = True
    no_execution: bool = True
    no_remote_authority: bool = True
    no_forced_update: bool = True
    no_provider_network_export_prompt_runtime_authority: bool = True
    no_secret_endpoint_client_material: bool = True

# compute/summarize/explain/predicates and validators
compute_federated_improvement_rehearsal_authorization_digest = _digest
compute_federated_improvement_rehearsal_result_digest = _digest
compute_federated_improvement_local_review_receipt_digest = _digest
compute_federated_improvement_adoption_readiness_manifest_digest = _digest

def _base_blockers(obj: Any) -> list[str]:
    b=[]
    if _has(obj, _FORBIDDEN): b.append("forbidden_adoption_apply_install_merge_execute_marker")
    if _has(obj, _PROVIDER): b.append("provider_network_export_runtime_prompt_marker")
    if _has(obj, _SECRET): b.append("secret_endpoint_client_marker")
    if _has(obj, _RAW): b.append("raw_patch_or_executable_payload_marker")
    if _has(obj, _BYPASS): b.append("local_governance_bypass_marker")
    return b

def validate_federated_improvement_rehearsal_authorization(x: FederatedImprovementRehearsalAuthorization)->CustodyValidation:
    b=_base_blockers(x)
    if not x.receiving_node_id or not x.producing_node_id or not x.source_candidate_id: b.append("missing_required_identity_or_candidate_metadata")
    if x.intake_receipt_digest != x.expected_intake_receipt_digest: b.append("intake_receipt_digest_mismatch")
    if any(g not in x.accepted_gate_codes for g in x.required_gate_codes): b.append("required_gates_not_accepted")
    if x.local_compatibility_posture in {"incompatible","contradicted"}: b.append("incompatible_local_compatibility_posture")
    status = FederatedImprovementRehearsalAuthorizationStatus.READY
    if b: status = FederatedImprovementRehearsalAuthorizationStatus.CONTRADICTED if any("mismatch" in z or "marker" in z for z in b) else FederatedImprovementRehearsalAuthorizationStatus.HOLD
    if not x.receiving_node_id: status = FederatedImprovementRehearsalAuthorizationStatus.INCOMPLETE
    return CustodyValidation(status, tuple(dict.fromkeys(b)), ())

def validate_federated_improvement_rehearsal_result(x: FederatedImprovementRehearsalResult)->CustodyValidation:
    b=_base_blockers(x)
    if not x.rehearsal_authorization_id or not x.candidate_id: b.append("missing_source_evidence")
    if x.rehearsal_authorization_digest != x.expected_rehearsal_authorization_digest: b.append("rehearsal_authorization_digest_mismatch")
    if x.audit_verification_status not in _READY_VERIFICATION: b.append("audit_verification_not_satisfied")
    if x.immutable_verification_status not in _READY_VERIFICATION: b.append("immutable_verification_not_satisfied")
    status = FederatedImprovementRehearsalResultStatus.PASSED if not b and x.fail_count==0 else FederatedImprovementRehearsalResultStatus.FAILED
    if b and any("mismatch" in z or "marker" in z for z in b): status = FederatedImprovementRehearsalResultStatus.CONTRADICTED
    if not x.rehearsal_authorization_id: status = FederatedImprovementRehearsalResultStatus.INCOMPLETE
    return CustodyValidation(status, tuple(dict.fromkeys(b)), ())

def validate_federated_improvement_local_review_receipt(x:FederatedImprovementLocalReviewReceipt)->CustodyValidation:
    b=_base_blockers(x)
    if not x.local_reviewer_ref_label: b.append("missing_local_reviewer_ref")
    if any(g not in x.accepted_gate_codes for g in x.required_gate_codes): b.append("required_gates_not_accepted")
    status=FederatedImprovementLocalReviewStatus.ACCEPTED if not b and x.review_decision.startswith("accept") else FederatedImprovementLocalReviewStatus.HOLD
    if x.review_decision==FederatedImprovementLocalReviewDecision.REJECT: status=FederatedImprovementLocalReviewStatus.REJECTED
    if b and any("marker" in z for z in b): status=FederatedImprovementLocalReviewStatus.CONTRADICTED
    if "missing_local_reviewer_ref" in b: status=FederatedImprovementLocalReviewStatus.INCOMPLETE
    return CustodyValidation(status, tuple(dict.fromkeys(b)), ())

def validate_federated_improvement_adoption_readiness_manifest(x:FederatedImprovementAdoptionReadinessManifest)->CustodyValidation:
    b=_base_blockers(x)
    if not x.receiving_node_id or not x.local_review_receipt_id: b.append("missing_source_evidence")
    if x.audit_verification_status not in _READY_VERIFICATION: b.append("audit_verification_not_satisfied")
    if x.immutable_verification_status not in _READY_VERIFICATION: b.append("immutable_verification_not_satisfied")
    if any(g not in x.accepted_gate_codes for g in x.required_future_adoption_gate_codes): b.append("required_gates_not_accepted")
    if x.compatibility_posture in {"incompatible","contradicted"}: b.append("incompatible_compatibility_posture")
    status=FederatedImprovementAdoptionReadinessStatus.READY if not b else FederatedImprovementAdoptionReadinessStatus.BLOCKED
    if b and any("marker" in z for z in b): status=FederatedImprovementAdoptionReadinessStatus.CONTRADICTED
    if "missing_source_evidence" in b: status=FederatedImprovementAdoptionReadinessStatus.INCOMPLETE
    return CustodyValidation(status, tuple(dict.fromkeys(b)), ())

def summarize_federated_improvement_rehearsal_authorization(x: FederatedImprovementRehearsalAuthorization)->dict[str,Any]: return {"receiving_node_id":x.receiving_node_id,"producing_node_id":x.producing_node_id,"source_candidate_id":x.source_candidate_id,"intake_receipt_id":x.intake_receipt_id,"rehearsal_scope":x.rehearsal_scope,"gate_counts":{"required":len(x.required_gate_codes),"accepted":len(x.accepted_gate_codes),"rejected":len(x.rejected_gate_codes),"pending":len(x.pending_gate_codes)},"metadata_only":x.metadata_only}
def summarize_federated_improvement_rehearsal_result(x: FederatedImprovementRehearsalResult)->dict[str,Any]: return {"candidate_id":x.candidate_id,"rehearsal_authorization_id":x.rehearsal_authorization_id,"counts":{"pass":x.pass_count,"fail":x.fail_count,"warning":x.warning_count},"metadata_only":x.metadata_only}
def summarize_federated_improvement_local_review_receipt(x: FederatedImprovementLocalReviewReceipt)->dict[str,Any]: return {"local_reviewer_ref_label":x.local_reviewer_ref_label,"candidate_id":x.candidate_id,"review_decision":x.review_decision,"metadata_only":x.metadata_only}
def summarize_federated_improvement_adoption_readiness_manifest(x: FederatedImprovementAdoptionReadinessManifest)->dict[str,Any]: return {"receiving_node_id":x.receiving_node_id,"candidate_id":x.candidate_id,"local_review_receipt_id":x.local_review_receipt_id,"adoption_not_occurred_statement":x.adoption_not_occurred_statement,"metadata_only":x.metadata_only}

def explain_federated_improvement_rehearsal_authorization(x:FederatedImprovementRehearsalAuthorization)->tuple[str,...]: return (f"status:{validate_federated_improvement_rehearsal_authorization(x).status}","scope:metadata_only_no_adoption_no_execution")
def explain_federated_improvement_rehearsal_result(x:FederatedImprovementRehearsalResult)->tuple[str,...]: return (f"status:{validate_federated_improvement_rehearsal_result(x).status}","scope:metadata_only_no_adoption_no_execution")
def explain_federated_improvement_local_review_receipt(x:FederatedImprovementLocalReviewReceipt)->tuple[str,...]: return (f"status:{validate_federated_improvement_local_review_receipt(x).status}","scope:metadata_only_no_adoption_no_execution")
def explain_federated_improvement_adoption_readiness_manifest(x:FederatedImprovementAdoptionReadinessManifest)->tuple[str,...]: return (f"status:{validate_federated_improvement_adoption_readiness_manifest(x).status}","scope:metadata_only_no_adoption_no_execution")

def federated_improvement_rehearsal_authorization_is_metadata_only(x:FederatedImprovementRehearsalAuthorization)->bool: return x.metadata_only and x.no_adoption and x.no_execution
def federated_improvement_rehearsal_result_is_metadata_only(x:FederatedImprovementRehearsalResult)->bool: return x.metadata_only and x.no_adoption and x.no_execution
def federated_improvement_local_review_receipt_is_metadata_only(x:FederatedImprovementLocalReviewReceipt)->bool: return x.metadata_only and x.no_adoption and x.no_execution
def federated_improvement_adoption_readiness_manifest_is_metadata_only(x:FederatedImprovementAdoptionReadinessManifest)->bool: return x.metadata_only and x.no_adoption and x.no_execution
