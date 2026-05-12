from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from .improvement_candidate import FederatedImprovementCandidate, validate_federated_improvement_candidate
from .improvement_local_variant_artifact import (
    FederatedImprovementLocalVariantArtifact,
    validate_federated_improvement_local_variant_artifact,
)


class FederatedImprovementLineageComparisonStatus:
    COMPATIBLE = "federated_improvement_lineage_comparison_compatible"
    COMPATIBLE_WITH_CONDITIONS = "federated_improvement_lineage_comparison_compatible_with_conditions"
    INCOMPATIBLE = "federated_improvement_lineage_comparison_incompatible"
    INCOMPLETE = "federated_improvement_lineage_comparison_incomplete"
    CONTRADICTED = "federated_improvement_lineage_comparison_contradicted"


class FederatedImprovementLineageComparisonDimension:
    SOURCE_IDENTITY_LINEAGE = "source_identity_lineage"
    CANDIDATE_KIND_LINEAGE = "candidate_kind_lineage"
    DIGEST_LINEAGE = "digest_lineage"
    GATE_LINEAGE = "gate_lineage"
    COMPATIBILITY_POSTURE_LINEAGE = "compatibility_posture_lineage"
    POLICY_POSTURE_LINEAGE = "policy_posture_lineage"
    RISK_LINEAGE = "risk_lineage"
    INVARIANT_LINEAGE = "invariant_lineage"
    REHEARSAL_LINEAGE = "rehearsal_lineage"
    REVIEW_LINEAGE = "review_lineage"


LINEAGE_COMPARISON_STATUSES = tuple(v for k, v in FederatedImprovementLineageComparisonStatus.__dict__.items() if k.isupper())
LINEAGE_COMPARISON_DIMENSIONS = tuple(v for k, v in FederatedImprovementLineageComparisonDimension.__dict__.items() if k.isupper())
_DIMENSION_ALLOWED = {"compatible", "compatible_with_conditions", "incompatible", "missing"}
_FORBIDDEN = ("adopt", "apply", "install", "merge", "conflict", "execute")
_PRODUCTION = ("production_execution", "execute_in_production", "prod_execute")
_REMOTE = ("remote_execution", "remote_execute")
_PROVIDER = ("provider", "network", "export", "runtime", "prompt_text", "system_prompt", "http://", "https://")
_SECRET = ("secret", "api_key", "credential", "endpoint", "client")
_RAW = ("diff --git", "patch_body", "raw_patch", "executable_payload", "script_body", "code_payload")
_BYPASS = ("bypass_governance", "skip_review", "control_plane_bypass", "canonical_gate_bypass")


@dataclass(frozen=True)
class LineageComparisonValidation:
    status: str
    blockers: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FederatedImprovementLineageComparisonReceipt:
    comparing_node_id: str
    original_producing_node_id: str
    deriving_node_id: str
    original_candidate_id: str
    original_candidate_digest: str
    expected_original_candidate_digest: str = ""
    local_variant_id: str = ""
    local_variant_digest: str = ""
    expected_local_variant_digest: str = ""
    original_candidate_kind: str = ""
    local_variant_kind: str = ""
    original_candidate_status: str = ""
    local_variant_status: str = ""
    comparison_status: str = FederatedImprovementLineageComparisonStatus.INCOMPLETE
    derivation_reason_codes: tuple[str, ...] = ()
    modified_metadata_field_labels: tuple[str, ...] = ()
    unchanged_invariant_labels: tuple[str, ...] = ()
    comparison_dimensions: tuple[tuple[str, str], ...] = ()
    compatible_dimension_count: int = 0
    conditional_dimension_count: int = 0
    incompatible_dimension_count: int = 0
    missing_dimension_count: int = 0
    warning_codes: tuple[str, ...] = ()
    risk_codes: tuple[str, ...] = ()
    lineage_refs: tuple[str, ...] = ()
    source_intake_receipt_id: str = ""
    source_intake_receipt_digest: str = ""
    source_rehearsal_result_id: str = ""
    source_rehearsal_result_digest: str = ""
    source_local_review_receipt_id: str = ""
    source_local_review_receipt_digest: str = ""
    source_adoption_readiness_manifest_id: str = ""
    source_adoption_readiness_manifest_digest: str = ""
    metadata_only: bool = True
    comparison_only: bool = True
    lineage_preserving: bool = True
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


def _contains(obj: Any, markers: Sequence[str]) -> bool:
    vals = _walk(obj)
    return any(m in t for m in markers for t in vals)


def compute_federated_improvement_lineage_comparison_receipt_digest(receipt: FederatedImprovementLineageComparisonReceipt) -> str:
    return hashlib.sha256(json.dumps(_stable(receipt), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_federated_improvement_lineage_comparison_receipt(receipt: FederatedImprovementLineageComparisonReceipt) -> LineageComparisonValidation:
    b: list[str] = []
    if not receipt.comparing_node_id:
        b.append("missing_comparing_node_id")
    if not receipt.original_candidate_id or not receipt.original_candidate_digest:
        b.append("missing_original_candidate_metadata")
    if not receipt.local_variant_id or not receipt.local_variant_digest:
        b.append("missing_local_variant_metadata")
    if receipt.expected_original_candidate_digest and receipt.original_candidate_digest != receipt.expected_original_candidate_digest:
        b.append("original_candidate_digest_mismatch")
    if receipt.expected_local_variant_digest and receipt.local_variant_digest != receipt.expected_local_variant_digest:
        b.append("local_variant_digest_mismatch")
    if not receipt.derivation_reason_codes:
        b.append("missing_derivation_reason_codes")
    if not receipt.comparison_dimensions:
        b.append("missing_comparison_dimensions")
    dims = {d for d, _ in receipt.comparison_dimensions}
    for d, s in receipt.comparison_dimensions:
        if d not in LINEAGE_COMPARISON_DIMENSIONS:
            b.append("unknown_comparison_dimension")
        if s not in _DIMENSION_ALLOWED:
            b.append("unknown_comparison_status")
    if receipt.original_candidate_id not in " ".join(receipt.lineage_refs) or receipt.original_candidate_digest not in " ".join(receipt.lineage_refs):
        b.append("local_variant_lineage_not_pointing_to_original_candidate")
    if receipt.comparison_status == FederatedImprovementLineageComparisonStatus.COMPATIBLE:
        if any(s == "incompatible" for _, s in receipt.comparison_dimensions):
            b.append("incompatible_dimension_while_claiming_compatible")
        if any(s == "missing" for _, s in receipt.comparison_dimensions):
            b.append("missing_dimension_while_claiming_compatible")
    if dims and not set(LINEAGE_COMPARISON_DIMENSIONS).issubset(dims):
        b.append("missing_comparison_dimensions")
    if receipt.comparison_status not in LINEAGE_COMPARISON_STATUSES:
        b.append("unknown_comparison_status")
    if _contains(receipt, _FORBIDDEN): b.append("forbidden_adoption_apply_install_merge_conflict_resolution_execute_marker")
    if _contains(receipt, _PRODUCTION): b.append("forbidden_production_execution_marker")
    if _contains(receipt, _REMOTE): b.append("forbidden_remote_execution_marker")
    if _contains(receipt, _PROVIDER): b.append("forbidden_provider_network_export_runtime_prompt_marker")
    if _contains(receipt, _SECRET): b.append("forbidden_secret_endpoint_client_marker")
    if _contains(receipt, _RAW): b.append("forbidden_raw_patch_or_executable_payload_marker")
    if _contains(receipt, _BYPASS): b.append("forbidden_local_governance_bypass_marker")
    req = [receipt.metadata_only, receipt.comparison_only, receipt.lineage_preserving, receipt.not_adopted, receipt.not_merged, receipt.not_conflict_resolved, receipt.not_installed_applied, receipt.not_production_executed, receipt.no_remote_authority, receipt.no_forced_update, receipt.no_provider_network_export_prompt_runtime_authority, receipt.no_secret_endpoint_client_material]
    if not all(req):
        b.append("required_sovereignty_safety_flags_missing")
    status = FederatedImprovementLineageComparisonStatus.COMPATIBLE if not b else FederatedImprovementLineageComparisonStatus.CONTRADICTED
    if any(x.startswith("missing_") for x in b):
        status = FederatedImprovementLineageComparisonStatus.INCOMPLETE
    return LineageComparisonValidation(status=status, blockers=tuple(dict.fromkeys(b)))


def summarize_federated_improvement_lineage_comparison_receipt(receipt: FederatedImprovementLineageComparisonReceipt) -> dict[str, object]:
    return {"comparing_node_id": receipt.comparing_node_id, "original_candidate_id": receipt.original_candidate_id, "original_candidate_digest": receipt.original_candidate_digest, "local_variant_id": receipt.local_variant_id, "local_variant_digest": receipt.local_variant_digest, "comparison_status": receipt.comparison_status, "comparison_dimensions": tuple(receipt.comparison_dimensions), "compatible_dimension_count": receipt.compatible_dimension_count, "conditional_dimension_count": receipt.conditional_dimension_count, "incompatible_dimension_count": receipt.incompatible_dimension_count, "missing_dimension_count": receipt.missing_dimension_count, "warning_codes": tuple(receipt.warning_codes), "risk_codes": tuple(receipt.risk_codes), "lineage_refs": tuple(receipt.lineage_refs), "metadata_only": receipt.metadata_only, "comparison_only": receipt.comparison_only, "not_adopted": receipt.not_adopted, "not_merged": receipt.not_merged, "no_remote_authority": receipt.no_remote_authority}


def explain_federated_improvement_lineage_comparison_receipt(receipt: FederatedImprovementLineageComparisonReceipt) -> tuple[str, ...]:
    v = validate_federated_improvement_lineage_comparison_receipt(receipt)
    return tuple([f"status:{v.status}", *[f"blocker:{x}" for x in v.blockers]])


def federated_improvement_lineage_comparison_receipt_is_metadata_only(receipt: FederatedImprovementLineageComparisonReceipt) -> bool:
    return receipt.metadata_only and receipt.comparison_only and not_adopted_lineage_comparison_only(receipt)


def federated_improvement_lineage_comparison_receipt_is_conservative(receipt: FederatedImprovementLineageComparisonReceipt) -> bool:
    v = validate_federated_improvement_lineage_comparison_receipt(receipt)
    return v.status in {FederatedImprovementLineageComparisonStatus.COMPATIBLE, FederatedImprovementLineageComparisonStatus.COMPATIBLE_WITH_CONDITIONS} and not any("forbidden" in x for x in v.blockers)


def not_adopted_lineage_comparison_only(receipt: FederatedImprovementLineageComparisonReceipt) -> bool:
    return receipt.not_adopted and receipt.not_merged and receipt.not_conflict_resolved and receipt.not_installed_applied


def build_federated_improvement_lineage_comparison_receipt(*, comparing_node_id: str, original_candidate: FederatedImprovementCandidate, local_variant: FederatedImprovementLocalVariantArtifact, comparison_status: str, comparison_dimensions: tuple[tuple[str, str], ...], expected_original_candidate_digest: str = "", expected_local_variant_digest: str = "", warning_codes: tuple[str, ...] = (), risk_codes: tuple[str, ...] = (), lineage_refs: tuple[str, ...] = (), source_intake_receipt_id: str = "", source_intake_receipt_digest: str = "", source_rehearsal_result_id: str = "", source_rehearsal_result_digest: str = "", source_local_review_receipt_id: str = "", source_local_review_receipt_digest: str = "", source_adoption_readiness_manifest_id: str = "", source_adoption_readiness_manifest_digest: str = "") -> FederatedImprovementLineageComparisonReceipt:
    from .improvement_candidate import compute_federated_improvement_candidate_digest
    from .improvement_local_variant_artifact import compute_federated_improvement_local_variant_artifact_digest

    original_digest = compute_federated_improvement_candidate_digest(original_candidate)
    variant_digest = compute_federated_improvement_local_variant_artifact_digest(local_variant)
    return FederatedImprovementLineageComparisonReceipt(
        comparing_node_id=comparing_node_id,
        original_producing_node_id=original_candidate.producing_node_id,
        deriving_node_id=local_variant.deriving_node_id,
        original_candidate_id=original_candidate.local_candidate_id,
        original_candidate_digest=original_digest,
        expected_original_candidate_digest=expected_original_candidate_digest,
        local_variant_id=local_variant.local_variant_id,
        local_variant_digest=variant_digest,
        expected_local_variant_digest=expected_local_variant_digest,
        original_candidate_kind=original_candidate.candidate_kind,
        local_variant_kind=local_variant.local_variant_kind,
        original_candidate_status=validate_federated_improvement_candidate(original_candidate).status,
        local_variant_status=validate_federated_improvement_local_variant_artifact(local_variant).status,
        comparison_status=comparison_status,
        derivation_reason_codes=local_variant.derivation_reason_codes,
        modified_metadata_field_labels=local_variant.modified_metadata_field_labels,
        unchanged_invariant_labels=local_variant.unchanged_invariant_labels,
        comparison_dimensions=comparison_dimensions,
        compatible_dimension_count=sum(1 for _, s in comparison_dimensions if s == "compatible"),
        conditional_dimension_count=sum(1 for _, s in comparison_dimensions if s == "compatible_with_conditions"),
        incompatible_dimension_count=sum(1 for _, s in comparison_dimensions if s == "incompatible"),
        missing_dimension_count=sum(1 for _, s in comparison_dimensions if s == "missing"),
        warning_codes=warning_codes,
        risk_codes=risk_codes,
        lineage_refs=lineage_refs or local_variant.lineage_refs,
        source_intake_receipt_id=source_intake_receipt_id or local_variant.source_intake_receipt_id,
        source_intake_receipt_digest=source_intake_receipt_digest or local_variant.source_intake_receipt_digest,
        source_rehearsal_result_id=source_rehearsal_result_id or local_variant.source_rehearsal_result_id,
        source_rehearsal_result_digest=source_rehearsal_result_digest or local_variant.source_rehearsal_result_digest,
        source_local_review_receipt_id=source_local_review_receipt_id or local_variant.source_local_review_receipt_id,
        source_local_review_receipt_digest=source_local_review_receipt_digest or local_variant.source_local_review_receipt_digest,
        source_adoption_readiness_manifest_id=source_adoption_readiness_manifest_id or local_variant.source_adoption_readiness_manifest_id,
        source_adoption_readiness_manifest_digest=source_adoption_readiness_manifest_digest or local_variant.source_adoption_readiness_manifest_digest,
    )
