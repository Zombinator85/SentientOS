from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from .improvement_candidate import FederatedImprovementCandidate, compute_federated_improvement_candidate_digest


class FederatedImprovementVariantStatus:
    READY = "federated_improvement_variant_ready"
    READY_WITH_CONDITIONS = "federated_improvement_variant_ready_with_conditions"
    BLOCKED = "federated_improvement_variant_blocked"
    INCOMPLETE = "federated_improvement_variant_incomplete"
    CONTRADICTED = "federated_improvement_variant_contradicted"


class FederatedImprovementVariantKind:
    LOCAL_PARAMETER_VARIANT = "local_parameter_variant"
    LOCAL_POLICY_VARIANT = "local_policy_variant"
    LOCAL_DOCUMENTATION_VARIANT = "local_documentation_variant"
    LOCAL_TEST_VARIANT = "local_test_variant"
    LOCAL_GUARDRAIL_VARIANT = "local_guardrail_variant"
    LOCAL_COMPATIBILITY_VARIANT = "local_compatibility_variant"
    LOCAL_REHEARSAL_VARIANT = "local_rehearsal_variant"
    LOCAL_SCAFFOLD_VARIANT = "local_scaffold_variant"
    LOCAL_MEMORY_POLICY_VARIANT = "local_memory_policy_variant"
    LOCAL_FEDERATION_PROTOCOL_VARIANT = "local_federation_protocol_variant"


VARIANT_STATUSES = (
    FederatedImprovementVariantStatus.READY,
    FederatedImprovementVariantStatus.READY_WITH_CONDITIONS,
    FederatedImprovementVariantStatus.BLOCKED,
    FederatedImprovementVariantStatus.INCOMPLETE,
    FederatedImprovementVariantStatus.CONTRADICTED,
)
VARIANT_KINDS = tuple(v for k, v in FederatedImprovementVariantKind.__dict__.items() if k.isupper())
_READY_VERIFICATION = frozenset({"verified", "passed", "ok", "not_required_with_reason"})
_COMPATIBLE = frozenset({"compatible", "compatible_with_conditions", "local_review_required"})
_POLICY_COMPATIBLE = frozenset({"compliant", "compliant_with_conditions", "local_review_required"})
_FORBIDDEN = ("adopt", "install", "apply", "merge", "execute", "schedule", "route", "production_execution", "remote_execution", "forced_update")
_PROVIDER = ("provider", "network", "export", "runtime", "prompt_text", "system_prompt", "http://", "https://")
_SECRET = ("secret", "api_key", "credential", "endpoint", "client")
_RAW = ("raw_patch", "patch_body", "diff --git", "executable_payload", "script_body")
_BYPASS = ("bypass_governance", "skip_review", "control_plane_bypass", "canonical_gate_bypass")


@dataclass(frozen=True)
class FederatedImprovementVariantValidation:
    status: str
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class FederatedImprovementLocalVariantArtifact:
    deriving_node_id: str
    original_producing_node_id: str
    original_candidate_id: str
    original_candidate_digest: str
    expected_original_candidate_digest: str = ""
    local_variant_id: str = ""
    local_variant_kind: str = FederatedImprovementVariantKind.LOCAL_POLICY_VARIANT
    local_variant_status: str = FederatedImprovementVariantStatus.INCOMPLETE
    derivation_reason_codes: tuple[str, ...] = ()
    modified_metadata_field_labels: tuple[str, ...] = ()
    unchanged_invariant_labels: tuple[str, ...] = ()
    local_compatibility_posture: str = "local_review_required"
    local_policy_posture: str = "local_review_required"
    required_local_gate_codes: tuple[str, ...] = ()
    accepted_gate_codes: tuple[str, ...] = ()
    rejected_gate_codes: tuple[str, ...] = ()
    pending_gate_codes: tuple[str, ...] = ()
    source_intake_receipt_id: str = ""
    source_intake_receipt_digest: str = ""
    source_rehearsal_authorization_id: str = ""
    source_rehearsal_authorization_digest: str = ""
    source_rehearsal_result_id: str = ""
    source_rehearsal_result_digest: str = ""
    source_local_review_receipt_id: str = ""
    source_local_review_receipt_digest: str = ""
    source_adoption_readiness_manifest_id: str = ""
    source_adoption_readiness_manifest_digest: str = ""
    audit_verification_status: str = "unknown"
    immutable_verification_status: str = "unknown"
    warning_codes: tuple[str, ...] = ()
    risk_codes: tuple[str, ...] = ()
    lineage_refs: tuple[str, ...] = ()
    metadata_only: bool = True
    locally_derived_variant: bool = True
    lineage_preserved: bool = True
    not_adopted: bool = True
    not_installed_applied_merged: bool = True
    not_production_executed: bool = True
    no_remote_authority: bool = True
    no_forced_update: bool = True
    no_provider_network_export_prompt_runtime_authority: bool = True
    no_secret_endpoint_client_material: bool = True
    explicit_conversion_gate_required_for_local_candidate: bool = True


def _stable(v: Any) -> Any:
    if is_dataclass(v) and not isinstance(v, type):
        return {str(k): _stable(x) for k, x in asdict(v).items()}
    if isinstance(v, Mapping):
        return {str(k): _stable(x) for k, x in sorted(v.items(), key=lambda p: str(p[0]))}
    if isinstance(v, (tuple, list)):
        return [_stable(x) for x in v]
    return v


def _walk(v: Any) -> tuple[str, ...]:
    out: list[str] = []
    def visit(x: Any) -> None:
        if is_dataclass(x) and not isinstance(x, type):
            visit(asdict(x))
        elif isinstance(x, Mapping):
            for y in x.values(): visit(y)
        elif isinstance(x, (tuple, list, set, frozenset)):
            for y in x: visit(y)
        elif isinstance(x, str):
            out.append(x.lower())
    visit(v)
    return tuple(out)


def _has(v: Any, markers: Sequence[str]) -> bool:
    values = _walk(v)
    return any(m in t for m in markers for t in values)


def compute_federated_improvement_local_variant_artifact_digest(artifact: FederatedImprovementLocalVariantArtifact) -> str:
    return hashlib.sha256(json.dumps(_stable(artifact), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_federated_improvement_local_variant_artifact(artifact: FederatedImprovementLocalVariantArtifact) -> FederatedImprovementVariantValidation:
    blockers: list[str] = []
    if not artifact.deriving_node_id: blockers.append("missing_deriving_node_id")
    if not artifact.original_candidate_id or not artifact.original_candidate_digest: blockers.append("missing_original_candidate_metadata")
    if artifact.expected_original_candidate_digest and artifact.original_candidate_digest != artifact.expected_original_candidate_digest: blockers.append("original_candidate_digest_mismatch")
    if not artifact.local_variant_id: blockers.append("missing_local_variant_id")
    if artifact.local_variant_kind not in VARIANT_KINDS: blockers.append("unknown_variant_kind")
    if artifact.local_variant_status not in VARIANT_STATUSES: blockers.append("unknown_variant_status")
    if not artifact.derivation_reason_codes: blockers.append("missing_derivation_reason_codes")
    if not artifact.lineage_refs: blockers.append("missing_lineage_refs")
    if artifact.audit_verification_status not in _READY_VERIFICATION: blockers.append("audit_verification_failed_or_missing")
    if artifact.immutable_verification_status not in _READY_VERIFICATION: blockers.append("immutable_verification_failed_or_missing")
    if artifact.local_variant_status in {FederatedImprovementVariantStatus.READY, FederatedImprovementVariantStatus.READY_WITH_CONDITIONS}:
        missing = set(artifact.required_local_gate_codes) - set(artifact.accepted_gate_codes)
        if missing: blockers.append("required_local_gates_not_accepted")
        if artifact.rejected_gate_codes: blockers.append("rejected_local_gates_present")
        if artifact.pending_gate_codes: blockers.append("pending_local_gates_present")
    if artifact.local_compatibility_posture not in _COMPATIBLE: blockers.append("incompatible_local_compatibility_posture")
    if artifact.local_policy_posture not in _POLICY_COMPATIBLE: blockers.append("incompatible_local_policy_posture")
    if _has(artifact, _FORBIDDEN): blockers.append("forbidden_adoption_execution_marker")
    if _has(artifact, _PROVIDER): blockers.append("forbidden_provider_network_export_runtime_prompt_marker")
    if _has(artifact, _SECRET): blockers.append("forbidden_secret_endpoint_client_marker")
    if _has(artifact, _RAW): blockers.append("forbidden_raw_patch_or_executable_payload_marker")
    if _has(artifact, _BYPASS): blockers.append("forbidden_governance_bypass_marker")
    required_bools = (
        artifact.metadata_only, artifact.locally_derived_variant, artifact.lineage_preserved, artifact.not_adopted,
        artifact.not_installed_applied_merged, artifact.not_production_executed, artifact.no_remote_authority,
        artifact.no_forced_update, artifact.no_provider_network_export_prompt_runtime_authority,
        artifact.no_secret_endpoint_client_material, artifact.explicit_conversion_gate_required_for_local_candidate,
    )
    if not all(required_bools): blockers.append("required_sovereignty_safety_flags_missing")
    status = FederatedImprovementVariantStatus.READY if not blockers else FederatedImprovementVariantStatus.CONTRADICTED
    return FederatedImprovementVariantValidation(status=status, blockers=tuple(sorted(set(blockers))))


def summarize_federated_improvement_local_variant_artifact(artifact: FederatedImprovementLocalVariantArtifact) -> dict[str, object]:
    return {
        "deriving_node_id": artifact.deriving_node_id,
        "original_producing_node_id": artifact.original_producing_node_id,
        "original_candidate_id": artifact.original_candidate_id,
        "original_candidate_digest": artifact.original_candidate_digest,
        "local_variant_id": artifact.local_variant_id,
        "local_variant_kind": artifact.local_variant_kind,
        "local_variant_status": artifact.local_variant_status,
        "required_gate_count": len(artifact.required_local_gate_codes),
        "accepted_gate_count": len(artifact.accepted_gate_codes),
        "rejected_gate_count": len(artifact.rejected_gate_codes),
        "pending_gate_count": len(artifact.pending_gate_codes),
        "warning_count": len(artifact.warning_codes),
        "risk_count": len(artifact.risk_codes),
        "lineage_ref_count": len(artifact.lineage_refs),
        "metadata_only": artifact.metadata_only,
        "not_adopted": artifact.not_adopted,
        "no_remote_authority": artifact.no_remote_authority,
    }


def explain_federated_improvement_local_variant_artifact(artifact: FederatedImprovementLocalVariantArtifact) -> tuple[str, ...]:
    v = validate_federated_improvement_local_variant_artifact(artifact)
    return tuple([f"status:{v.status}", *[f"blocker:{b}" for b in v.blockers]])


def federated_improvement_local_variant_artifact_is_metadata_only(artifact: FederatedImprovementLocalVariantArtifact) -> bool:
    return validate_federated_improvement_local_variant_artifact(artifact).status == FederatedImprovementVariantStatus.READY and artifact.metadata_only


def federated_improvement_local_variant_artifact_has_no_remote_authority(artifact: FederatedImprovementLocalVariantArtifact) -> bool:
    return federated_improvement_local_variant_artifact_is_metadata_only(artifact) and artifact.no_remote_authority


def federated_improvement_local_variant_artifact_is_conservative_evidence_only(artifact: FederatedImprovementLocalVariantArtifact) -> bool:
    return federated_improvement_local_variant_artifact_is_metadata_only(artifact) and artifact.not_adopted and artifact.explicit_conversion_gate_required_for_local_candidate


def build_federated_improvement_local_variant_artifact(
    *,
    candidate: FederatedImprovementCandidate,
    deriving_node_id: str,
    local_variant_id: str,
    local_variant_kind: str,
    local_variant_status: str,
    derivation_reason_codes: Sequence[str],
    lineage_refs: Sequence[str],
    intake_receipt: Any | None = None,
    rehearsal_authorization: Any | None = None,
    rehearsal_result: Any | None = None,
    local_review_receipt: Any | None = None,
    adoption_readiness_manifest: Any | None = None,
    **kwargs: Any,
) -> FederatedImprovementLocalVariantArtifact:
    return FederatedImprovementLocalVariantArtifact(
        deriving_node_id=deriving_node_id,
        original_producing_node_id=candidate.producing_node_id,
        original_candidate_id=candidate.local_candidate_id,
        original_candidate_digest=compute_federated_improvement_candidate_digest(candidate),
        local_variant_id=local_variant_id,
        local_variant_kind=local_variant_kind,
        local_variant_status=local_variant_status,
        derivation_reason_codes=tuple(derivation_reason_codes),
        lineage_refs=tuple(lineage_refs),
        source_intake_receipt_id=getattr(intake_receipt, "intake_receipt_id", ""),
        source_intake_receipt_digest=getattr(intake_receipt, "intake_receipt_digest", ""),
        source_rehearsal_authorization_id=getattr(rehearsal_authorization, "rehearsal_authorization_id", ""),
        source_rehearsal_authorization_digest=getattr(rehearsal_authorization, "rehearsal_authorization_digest", ""),
        source_rehearsal_result_id=getattr(rehearsal_result, "rehearsal_result_id", ""),
        source_rehearsal_result_digest=getattr(rehearsal_result, "rehearsal_result_digest", ""),
        source_local_review_receipt_id=getattr(local_review_receipt, "local_review_receipt_id", ""),
        source_local_review_receipt_digest=getattr(local_review_receipt, "local_review_receipt_digest", ""),
        source_adoption_readiness_manifest_id=getattr(adoption_readiness_manifest, "adoption_readiness_manifest_id", ""),
        source_adoption_readiness_manifest_digest=getattr(adoption_readiness_manifest, "adoption_readiness_manifest_digest", ""),
        **kwargs,
    )
