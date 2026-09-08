"""Exact, externally supplied authority evidence for model artifact acquisition.

This module is deliberately a consumer, not an approval actuator.  It validates
immutable JSON evidence produced outside the acquisition runtime and projects the
exact metadata submitted to the control-plane kernel.
"""
from __future__ import annotations

from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from sentientos.local_runtime_provisioning import semantic_digest

APPROVAL_SCHEMA = "sentientos.local_model_artifact_acquisition_approval:v1"
PRINCIPAL = "deterministic_model_artifact_acquisition_controller"
CAPABILITY = "local_model_artifact_acquisition"
EFFECTS = (
    "exact_operator_approval_evidence_read",
    "exact_authoritative_deployed_catalog_proof_read",
    "exact_model_artifact_acquisition_plan_read",
    "bounded_exact_https_artifact_stream",
    "exact_content_addressed_model_escrow_write",
    "model_artifact_acquisition_receipt_write",
)
PLACEHOLDER_IDENTITIES = frozenset({"", "*", "anonymous", "default", "sample", "test", "placeholder"})


class AcquisitionApprovalError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def effect_set_digest() -> str:
    return str(semantic_digest({"effects": sorted(EFFECTS)}))


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise AcquisitionApprovalError("acquisition_approval_time_invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AcquisitionApprovalError("acquisition_approval_time_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AcquisitionApprovalError("acquisition_approval_time_invalid")
    return parsed


def expected_approval_bindings(plan: Mapping[str, Any], *, correlation_id: str) -> dict[str, Any]:
    return {
        "target_principal": PRINCIPAL,
        "target_capability": CAPABILITY,
        "effects": sorted(EFFECTS),
        "correlation_id": correlation_id,
        "installation_identity": plan.get("installation_identity"),
        "catalog_custody_identity": plan.get("catalog_custody_identity"),
        "authoritative_catalog_proof_digest": plan.get("authoritative_catalog_proof_digest"),
        "deployment_receipt_id": plan.get("deployment_receipt_id"),
        "deployment_receipt_semantic_digest": plan.get("deployment_receipt_semantic_digest"),
        "acquisition_plan_digest": plan.get("acquisition_plan_digest"),
        "model_id": plan.get("model_id"),
        "artifact_id": plan.get("artifact_id"),
        "artifact_sha256": plan.get("artifact_sha256"),
        "artifact_size_bytes": plan.get("artifact_size_bytes"),
        "canonical_source_url": plan.get("canonical_source_url"),
        "escrow_root": plan.get("escrow_root"),
        "final_relative_escrow_path": plan.get("final_relative_escrow_path"),
    }


def verify_external_approval(evidence: Mapping[str, Any], plan: Mapping[str, Any], *,
                             correlation_id: str, observation_time: datetime,
                             allow_synthetic_for_tests: bool = False) -> Mapping[str, Any]:
    """Verify exact approval semantics and return a read-only projection."""
    if observation_time.tzinfo is None or observation_time.utcoffset() is None:
        raise AcquisitionApprovalError("acquisition_approval_observation_time_invalid")
    value = dict(evidence)
    claimed = value.pop("approval_semantic_digest", None)
    if claimed != semantic_digest(value):
        raise AcquisitionApprovalError("acquisition_approval_digest_invalid")
    value["approval_semantic_digest"] = claimed
    if value.get("schema_version") != APPROVAL_SCHEMA or value.get("approval_status") != "approved":
        raise AcquisitionApprovalError("acquisition_approval_not_approved")
    operator = str(value.get("operator_identity", "")).strip().casefold()
    if operator in PLACEHOLDER_IDENTITIES:
        raise AcquisitionApprovalError("acquisition_approval_operator_invalid")
    if value.get("synthetic_test_evidence") is not False and not allow_synthetic_for_tests:
        raise AcquisitionApprovalError("synthetic_acquisition_approval_forbidden")
    effects = value.get("effects")
    if not isinstance(effects, list) or len(effects) != len(set(map(str, effects))) or effects != sorted(EFFECTS):
        raise AcquisitionApprovalError("acquisition_approval_effects_mismatch")
    for key, expected in expected_approval_bindings(plan, correlation_id=correlation_id).items():
        if value.get(key) != expected:
            raise AcquisitionApprovalError(f"acquisition_approval_{key}_mismatch")
    if not isinstance(value.get("approval_evidence_id"), str) or not value["approval_evidence_id"]:
        raise AcquisitionApprovalError("acquisition_approval_identity_invalid")
    if not isinstance(value.get("evidence_source"), str) or not value["evidence_source"]:
        raise AcquisitionApprovalError("acquisition_approval_provenance_invalid")
    if not isinstance(value.get("evidence_provenance"), str) or not value["evidence_provenance"]:
        raise AcquisitionApprovalError("acquisition_approval_provenance_invalid")
    not_before, expires, approved = (_time(value.get(k)) for k in ("not_before", "expires_at", "approval_timestamp"))
    if not_before > expires or approved < not_before or approved > expires:
        raise AcquisitionApprovalError("acquisition_approval_interval_invalid")
    if observation_time < not_before:
        raise AcquisitionApprovalError("acquisition_approval_not_yet_valid")
    if observation_time > expires:
        raise AcquisitionApprovalError("acquisition_approval_expired")
    return MappingProxyType(value)


def control_plane_metadata(approval: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    """Project only stable exact bindings into a kernel request."""
    return {
        "correlation_id": approval["correlation_id"],
        "acquisition_capability_id": CAPABILITY,
        "effect_set_digest": effect_set_digest(),
        "approval_evidence_id": approval["approval_evidence_id"],
        "approval_semantic_digest": approval["approval_semantic_digest"],
        "acquisition_plan_digest": plan["acquisition_plan_digest"],
        "installation_identity": plan["installation_identity"],
        "catalog_custody_identity": plan["catalog_custody_identity"],
        "authoritative_catalog_proof_digest": plan["authoritative_catalog_proof_digest"],
        "deployment_receipt_id": plan["deployment_receipt_id"],
        "deployment_receipt_semantic_digest": plan["deployment_receipt_semantic_digest"],
        "model_id": plan["model_id"], "artifact_id": plan["artifact_id"],
        "artifact_sha256": plan["artifact_sha256"], "artifact_size_bytes": plan["artifact_size_bytes"],
        "canonical_source_url": plan["canonical_source_url"], "escrow_root": plan["escrow_root"],
        "final_relative_escrow_path": plan["final_relative_escrow_path"],
        "approval_not_before": approval["not_before"], "approval_expires_at": approval["expires_at"],
    }
