from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from .improvement_candidate import (
    FederatedImprovementCandidate,
    compute_federated_improvement_candidate_digest,
    validate_federated_improvement_candidate,
)
from .improvement_lineage_comparison_receipt import (
    FederatedImprovementLineageComparisonReceipt,
    FederatedImprovementLineageComparisonStatus,
    compute_federated_improvement_lineage_comparison_receipt_digest,
)
from .improvement_local_variant_artifact import (
    FederatedImprovementLocalVariantArtifact,
    compute_federated_improvement_local_variant_artifact_digest,
    validate_federated_improvement_local_variant_artifact,
)


class FederatedImprovementDisseminationStatus:
    READY = "federated_improvement_dissemination_ready"
    READY_WITH_CONDITIONS = "federated_improvement_dissemination_ready_with_conditions"
    BLOCKED = "federated_improvement_dissemination_blocked"
    INCOMPLETE = "federated_improvement_dissemination_incomplete"
    CONTRADICTED = "federated_improvement_dissemination_contradicted"


class FederatedImprovementDisseminationScope:
    LOCAL_CATALOG_ONLY = "local_catalog_only"
    PEER_INDEX_METADATA_ONLY = "peer_index_metadata_only"
    STEWARD_REVIEW_INDEX = "steward_review_index"
    SIMULATION_LAB_INDEX = "simulation_lab_index"
    FEDERATION_DIGEST_ANNOUNCEMENT = "federation_digest_announcement"


DISSEMINATION_STATUSES = tuple(v for k, v in FederatedImprovementDisseminationStatus.__dict__.items() if k.isupper())
DISSEMINATION_SCOPES = tuple(v for k, v in FederatedImprovementDisseminationScope.__dict__.items() if k.isupper())
_READYISH = {FederatedImprovementDisseminationStatus.READY, FederatedImprovementDisseminationStatus.READY_WITH_CONDITIONS}
_INCOMPLETE_OR_CONTRADICTED = {"incomplete", "contradicted"}
_COMPATIBLE = {"compatible", "compatible_with_conditions", "local_review_required"}
_POLICY_COMPATIBLE = {"compliant", "compliant_with_conditions", "local_review_required"}

_FORBIDDEN_TRANSPORT = ("transport", "delivery", "upload", "network_egress", "subscription", "sync")
_FORBIDDEN_ACTION = ("adopt", "apply", "install", "merge", "conflict", "execute")
_FORBIDDEN_PRODUCTION = ("production_execution", "execute_in_production", "prod_execute")
_FORBIDDEN_REMOTE = ("remote_execution", "remote_execute")
_FORBIDDEN_PROVIDER = ("provider", "network", "export", "runtime", "prompt_text", "system_prompt", "http://", "https://")
_FORBIDDEN_SECRET = ("secret", "api_key", "credential", "endpoint", "client")
_FORBIDDEN_RAW = ("raw_patch", "patch_body", "diff --git", "executable_payload", "script_body", "code_payload")
_FORBIDDEN_BYPASS = ("bypass_governance", "skip_review", "control_plane_bypass", "canonical_gate_bypass")


@dataclass(frozen=True)
class FederatedImprovementDisseminationValidation:
    status: str
    blockers: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FederatedImprovementDisseminationReceipt:
    dissemination_receipt_id: str
    disseminating_node_id: str
    original_producing_node_id: str
    deriving_node_id: str = ""
    candidate_id: str = ""
    candidate_digest: str = ""
    variant_id: str = ""
    variant_digest: str = ""
    lineage_comparison_id: str = ""
    lineage_comparison_digest: str = ""
    candidate_kind: str = ""
    variant_kind: str = ""
    candidate_status: str = ""
    variant_status: str = ""
    lineage_comparison_status: str = ""
    dissemination_status: str = FederatedImprovementDisseminationStatus.INCOMPLETE
    dissemination_scope: str = ""
    catalog_label: str = ""
    evidence_summary_digest: str = ""
    peer_visibility_label: str = ""
    required_local_gate_codes: tuple[str, ...] = ()
    accepted_gate_codes: tuple[str, ...] = ()
    rejected_gate_codes: tuple[str, ...] = ()
    pending_gate_codes: tuple[str, ...] = ()
    compatibility_posture: str = "local_review_required"
    policy_posture: str = "local_review_required"
    warning_codes: tuple[str, ...] = ()
    risk_codes: tuple[str, ...] = ()
    lineage_refs: tuple[str, ...] = ()
    evidence_ref_count: int = 0
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
    metadata_only: bool = True
    dissemination_catalog_only: bool = True
    evidence_announcement_only: bool = True
    no_transport_performed: bool = True
    no_delivery_upload_network_egress_performed: bool = True
    no_subscription_sync_performed: bool = True
    not_adopted: bool = True
    not_merged: bool = True
    not_conflict_resolved: bool = True
    not_installed_applied: bool = True
    not_production_executed: bool = True
    no_remote_authority: bool = True
    no_forced_update: bool = True
    no_provider_network_export_prompt_runtime_authority: bool = True
    no_secret_endpoint_client_material: bool = True


def _stable(v: Any) -> Any:
    if is_dataclass(v) and not isinstance(v, type):
        return {str(k): _stable(x) for k, x in asdict(v).items()}
    if isinstance(v, Mapping):
        return {str(k): _stable(x) for k, x in sorted(v.items(), key=lambda p: str(p[0]))}
    if isinstance(v, (tuple, list, set, frozenset)):
        return [_stable(x) for x in v]
    return v


def _walk(v: Any) -> tuple[str, ...]:
    out: list[str] = []
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
            out.append(x.lower())
    visit(v)
    return tuple(out)


def _contains(x: Any, markers: Sequence[str]) -> bool:
    vals = _walk(x)
    return any(m in t for m in markers for t in vals)


def compute_federated_improvement_dissemination_receipt_digest(receipt: FederatedImprovementDisseminationReceipt) -> str:
    return hashlib.sha256(json.dumps(_stable(receipt), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_federated_improvement_dissemination_receipt(receipt: FederatedImprovementDisseminationReceipt) -> FederatedImprovementDisseminationValidation:
    b: list[str] = []
    if not receipt.disseminating_node_id:
        b.append("missing_disseminating_node_id")
    if not receipt.candidate_id:
        b.append("missing_candidate_metadata")
    if not receipt.candidate_digest:
        b.append("missing_candidate_digest")
    if not receipt.dissemination_scope:
        b.append("missing_dissemination_scope")
    elif receipt.dissemination_scope not in DISSEMINATION_SCOPES:
        b.append("unknown_dissemination_scope")
    if not receipt.catalog_label:
        b.append("missing_catalog_label")
    if not receipt.lineage_refs:
        b.append("missing_lineage_refs")

    if receipt.dissemination_status not in DISSEMINATION_STATUSES:
        b.append("unknown_dissemination_status")

    if receipt.dissemination_status in _READYISH:
        if any(s in receipt.candidate_status for s in _INCOMPLETE_OR_CONTRADICTED):
            b.append("candidate_incomplete_or_contradicted_while_claiming_ready")
        if receipt.variant_status and any(s in receipt.variant_status for s in _INCOMPLETE_OR_CONTRADICTED):
            b.append("variant_incomplete_or_contradicted_while_claiming_ready")
        if receipt.lineage_comparison_status and any(s in receipt.lineage_comparison_status for s in _INCOMPLETE_OR_CONTRADICTED):
            b.append("lineage_comparison_incomplete_or_contradicted_while_claiming_ready")
        if (
            receipt.dissemination_status == FederatedImprovementDisseminationStatus.READY
            and receipt.lineage_comparison_status == FederatedImprovementLineageComparisonStatus.INCOMPATIBLE
        ):
            b.append("lineage_comparison_incompatible_while_claiming_ready_without_conditions")
        if set(receipt.required_local_gate_codes) - set(receipt.accepted_gate_codes):
            b.append("required_local_gates_not_accepted")
        if receipt.rejected_gate_codes:
            b.append("rejected_local_gates_present")
        if receipt.pending_gate_codes:
            b.append("pending_local_gates_present")
        if receipt.compatibility_posture not in _COMPATIBLE:
            b.append("incompatible_compatibility_posture")
        if receipt.policy_posture not in _POLICY_COMPATIBLE:
            b.append("incompatible_policy_posture")

    if _contains(receipt, _FORBIDDEN_TRANSPORT): b.append("forbidden_transport_delivery_upload_network_egress_subscription_sync_marker")
    if _contains(receipt, _FORBIDDEN_ACTION): b.append("forbidden_adoption_apply_install_merge_conflict_resolution_execute_marker")
    if _contains(receipt, _FORBIDDEN_PRODUCTION): b.append("forbidden_production_execution_marker")
    if _contains(receipt, _FORBIDDEN_REMOTE): b.append("forbidden_remote_execution_marker")
    if _contains(receipt, _FORBIDDEN_PROVIDER): b.append("forbidden_provider_network_export_runtime_prompt_marker")
    if _contains(receipt, _FORBIDDEN_SECRET): b.append("forbidden_secret_endpoint_client_marker")
    if _contains(receipt, _FORBIDDEN_RAW): b.append("forbidden_raw_patch_or_executable_payload_marker")
    if _contains(receipt, _FORBIDDEN_BYPASS): b.append("forbidden_local_governance_bypass_marker")

    required_flags = [
        receipt.metadata_only,
        receipt.dissemination_catalog_only,
        receipt.evidence_announcement_only,
        receipt.no_transport_performed,
        receipt.no_delivery_upload_network_egress_performed,
        receipt.no_subscription_sync_performed,
        receipt.not_adopted,
        receipt.not_merged,
        receipt.not_conflict_resolved,
        receipt.not_installed_applied,
        receipt.not_production_executed,
        receipt.no_remote_authority,
        receipt.no_forced_update,
        receipt.no_provider_network_export_prompt_runtime_authority,
        receipt.no_secret_endpoint_client_material,
    ]
    if not all(required_flags):
        b.append("required_sovereignty_safety_flags_missing")

    status = FederatedImprovementDisseminationStatus.READY if not b else FederatedImprovementDisseminationStatus.BLOCKED
    if any(x.startswith("missing_") for x in b):
        status = FederatedImprovementDisseminationStatus.INCOMPLETE
    if any("forbidden" in x or "contradicted" in x for x in b):
        status = FederatedImprovementDisseminationStatus.CONTRADICTED
    return FederatedImprovementDisseminationValidation(status=status, blockers=tuple(dict.fromkeys(b)))


def summarize_federated_improvement_dissemination_receipt(receipt: FederatedImprovementDisseminationReceipt) -> dict[str, object]:
    return {
        "dissemination_receipt_id": receipt.dissemination_receipt_id,
        "disseminating_node_id": receipt.disseminating_node_id,
        "original_producing_node_id": receipt.original_producing_node_id,
        "deriving_node_id": receipt.deriving_node_id,
        "candidate_id": receipt.candidate_id,
        "candidate_digest": receipt.candidate_digest,
        "variant_id": receipt.variant_id,
        "variant_digest": receipt.variant_digest,
        "lineage_comparison_id": receipt.lineage_comparison_id,
        "lineage_comparison_digest": receipt.lineage_comparison_digest,
        "candidate_status": receipt.candidate_status,
        "variant_status": receipt.variant_status,
        "lineage_comparison_status": receipt.lineage_comparison_status,
        "dissemination_status": receipt.dissemination_status,
        "dissemination_scope": receipt.dissemination_scope,
        "catalog_label": receipt.catalog_label,
        "peer_visibility_label": receipt.peer_visibility_label,
        "evidence_ref_count": receipt.evidence_ref_count,
        "lineage_ref_count": len(receipt.lineage_refs),
        "warning_count": len(receipt.warning_codes),
        "risk_count": len(receipt.risk_codes),
        "metadata_only": receipt.metadata_only,
        "catalog_only": receipt.dissemination_catalog_only,
        "announcement_only": receipt.evidence_announcement_only,
        "no_transport_performed": receipt.no_transport_performed,
        "no_subscription_sync_performed": receipt.no_subscription_sync_performed,
        "not_adopted": receipt.not_adopted,
    }


def explain_federated_improvement_dissemination_receipt(receipt: FederatedImprovementDisseminationReceipt) -> tuple[str, ...]:
    v = validate_federated_improvement_dissemination_receipt(receipt)
    return tuple([f"status:{v.status}", *[f"blocker:{x}" for x in v.blockers]])


def federated_improvement_dissemination_receipt_is_metadata_only(receipt: FederatedImprovementDisseminationReceipt) -> bool:
    return receipt.metadata_only and receipt.dissemination_catalog_only and receipt.evidence_announcement_only


def federated_improvement_dissemination_receipt_is_catalogable(receipt: FederatedImprovementDisseminationReceipt) -> bool:
    v = validate_federated_improvement_dissemination_receipt(receipt)
    return v.status in {FederatedImprovementDisseminationStatus.READY, FederatedImprovementDisseminationStatus.READY_WITH_CONDITIONS}


def federated_improvement_dissemination_receipt_preserves_sovereignty(receipt: FederatedImprovementDisseminationReceipt) -> bool:
    return receipt.not_adopted and receipt.not_merged and receipt.not_conflict_resolved and receipt.no_remote_authority and receipt.no_forced_update


def build_federated_improvement_dissemination_receipt(
    *,
    dissemination_receipt_id: str,
    disseminating_node_id: str,
    dissemination_status: str,
    dissemination_scope: str,
    catalog_label: str,
    peer_visibility_label: str,
    original_candidate: FederatedImprovementCandidate,
    local_variant: FederatedImprovementLocalVariantArtifact | None = None,
    lineage_comparison: FederatedImprovementLineageComparisonReceipt | None = None,
    required_local_gate_codes: tuple[str, ...] = (),
    accepted_gate_codes: tuple[str, ...] = (),
    rejected_gate_codes: tuple[str, ...] = (),
    pending_gate_codes: tuple[str, ...] = (),
    compatibility_posture: str = "local_review_required",
    policy_posture: str = "local_review_required",
    warning_codes: tuple[str, ...] = (),
    risk_codes: tuple[str, ...] = (),
    lineage_refs: tuple[str, ...] = (),
    source_intake_receipt_id: str = "",
    source_intake_receipt_digest: str = "",
    source_rehearsal_authorization_id: str = "",
    source_rehearsal_authorization_digest: str = "",
    source_rehearsal_result_id: str = "",
    source_rehearsal_result_digest: str = "",
    source_local_review_receipt_id: str = "",
    source_local_review_receipt_digest: str = "",
    source_adoption_readiness_manifest_id: str = "",
    source_adoption_readiness_manifest_digest: str = "",
) -> FederatedImprovementDisseminationReceipt:
    candidate_digest = compute_federated_improvement_candidate_digest(original_candidate)
    variant_digest = compute_federated_improvement_local_variant_artifact_digest(local_variant) if local_variant else ""
    lineage_digest = compute_federated_improvement_lineage_comparison_receipt_digest(lineage_comparison) if lineage_comparison else ""
    candidate_status = validate_federated_improvement_candidate(original_candidate).status
    variant_status = validate_federated_improvement_local_variant_artifact(local_variant).status if local_variant else ""
    lineage_status = lineage_comparison.comparison_status if lineage_comparison else ""

    refs = lineage_refs or local_variant.lineage_refs if local_variant else lineage_refs or original_candidate.lineage_refs
    evidence_ref_count = 1 + int(bool(local_variant)) + int(bool(lineage_comparison))

    base = FederatedImprovementDisseminationReceipt(
        dissemination_receipt_id=dissemination_receipt_id,
        disseminating_node_id=disseminating_node_id,
        original_producing_node_id=original_candidate.producing_node_id,
        deriving_node_id=local_variant.deriving_node_id if local_variant else "",
        candidate_id=original_candidate.local_candidate_id,
        candidate_digest=candidate_digest,
        variant_id=local_variant.local_variant_id if local_variant else "",
        variant_digest=variant_digest,
        lineage_comparison_id=(lineage_comparison.local_variant_id + "::lineage") if lineage_comparison else "",
        lineage_comparison_digest=lineage_digest,
        candidate_kind=original_candidate.candidate_kind,
        variant_kind=local_variant.local_variant_kind if local_variant else "",
        candidate_status=candidate_status,
        variant_status=variant_status,
        lineage_comparison_status=lineage_status,
        dissemination_status=dissemination_status,
        dissemination_scope=dissemination_scope,
        catalog_label=catalog_label,
        peer_visibility_label=peer_visibility_label,
        required_local_gate_codes=required_local_gate_codes,
        accepted_gate_codes=accepted_gate_codes,
        rejected_gate_codes=rejected_gate_codes,
        pending_gate_codes=pending_gate_codes,
        compatibility_posture=compatibility_posture,
        policy_posture=policy_posture,
        warning_codes=warning_codes,
        risk_codes=risk_codes,
        lineage_refs=refs,
        evidence_ref_count=evidence_ref_count,
        source_intake_receipt_id=source_intake_receipt_id,
        source_intake_receipt_digest=source_intake_receipt_digest,
        source_rehearsal_authorization_id=source_rehearsal_authorization_id,
        source_rehearsal_authorization_digest=source_rehearsal_authorization_digest,
        source_rehearsal_result_id=source_rehearsal_result_id,
        source_rehearsal_result_digest=source_rehearsal_result_digest,
        source_local_review_receipt_id=source_local_review_receipt_id,
        source_local_review_receipt_digest=source_local_review_receipt_digest,
        source_adoption_readiness_manifest_id=source_adoption_readiness_manifest_id,
        source_adoption_readiness_manifest_digest=source_adoption_readiness_manifest_digest,
    )
    object.__setattr__(base, "evidence_summary_digest", compute_federated_improvement_dissemination_receipt_digest(base))
    return base
