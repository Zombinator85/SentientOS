from sentientos.federation import (
    FederatedImprovementCandidate,
    FederatedImprovementCandidateKind,
    FederatedImprovementCandidateStatus,
    FederatedImprovementIntakeDecision,
    FederatedImprovementVariantKind,
    FederatedImprovementVariantStatus,
    FederatedImprovementLocalVariantArtifact,
    build_federated_improvement_intake_receipt,
    build_federated_improvement_local_variant_artifact,
    compute_federated_improvement_local_variant_artifact_digest,
    federated_improvement_local_variant_artifact_is_conservative_evidence_only,
    summarize_federated_improvement_local_variant_artifact,
    validate_federated_improvement_local_variant_artifact,
)
from sentientos.federation.improvement_custody_runway import FederatedImprovementAdoptionReadinessManifest


def _candidate() -> FederatedImprovementCandidate:
    return FederatedImprovementCandidate(
        producing_node_id="node-upstream",
        local_candidate_id="cand-1",
        candidate_kind=FederatedImprovementCandidateKind.POLICY_GATE_IMPROVEMENT,
        audit_verification_status="verified",
        immutable_verification_status="verified",
        lineage_refs=("cand:seed@sha256:abc",),
        source_amendment_or_proposal_id="prop-1",
        test_evidence=(),
        rehearsal_artifact_refs=("reh:1",),
        require_test_or_rehearsal_evidence=True,
    )


def _base(**kwargs):
    c = _candidate()
    d = {
        "candidate": c,
        "deriving_node_id": "node-local",
        "local_variant_id": "variant-1",
        "local_variant_kind": FederatedImprovementVariantKind.LOCAL_POLICY_VARIANT,
        "local_variant_status": FederatedImprovementVariantStatus.READY,
        "derivation_reason_codes": ("local_policy_adjustment",),
        "lineage_refs": ("cand-1@sha256:abc",),
        "audit_verification_status": "verified",
        "immutable_verification_status": "verified",
        "required_local_gate_codes": ("gate:a",),
        "accepted_gate_codes": ("gate:a",),
        "local_compatibility_posture": "compatible",
        "local_policy_posture": "compliant",
    }
    d.update(kwargs)
    return build_federated_improvement_local_variant_artifact(**d)


def test_clean_ready_metadata_only_variant():
    v = _base()
    assert validate_federated_improvement_local_variant_artifact(v).blockers == ()
    assert federated_improvement_local_variant_artifact_is_conservative_evidence_only(v)


def test_ready_with_conditions_and_blocked_variants():
    assert _base(local_variant_status=FederatedImprovementVariantStatus.READY_WITH_CONDITIONS)
    assert _base(local_variant_status=FederatedImprovementVariantStatus.BLOCKED)


def test_fail_closed_conditions_and_markers():
    assert "missing_deriving_node_id" in validate_federated_improvement_local_variant_artifact(_base(deriving_node_id="")).blockers
    assert "missing_original_candidate_metadata" in validate_federated_improvement_local_variant_artifact(_base(candidate=FederatedImprovementCandidate("n","",FederatedImprovementCandidateKind.POLICY_GATE_IMPROVEMENT))).blockers
    assert "original_candidate_digest_mismatch" in validate_federated_improvement_local_variant_artifact(_base(expected_original_candidate_digest="sha256:bad")).blockers
    assert "unknown_variant_kind" in validate_federated_improvement_local_variant_artifact(_base(local_variant_kind="unknown")).blockers
    assert "missing_derivation_reason_codes" in validate_federated_improvement_local_variant_artifact(_base(derivation_reason_codes=())).blockers
    assert "missing_lineage_refs" in validate_federated_improvement_local_variant_artifact(_base(lineage_refs=())).blockers
    assert "audit_verification_failed_or_missing" in validate_federated_improvement_local_variant_artifact(_base(audit_verification_status="failed")).blockers
    assert "immutable_verification_failed_or_missing" in validate_federated_improvement_local_variant_artifact(_base(immutable_verification_status="failed")).blockers
    assert "pending_local_gates_present" in validate_federated_improvement_local_variant_artifact(_base(pending_gate_codes=("gate:a",))).blockers
    assert "rejected_local_gates_present" in validate_federated_improvement_local_variant_artifact(_base(rejected_gate_codes=("gate:a",))).blockers
    assert "incompatible_local_compatibility_posture" in validate_federated_improvement_local_variant_artifact(_base(local_compatibility_posture="incompatible")).blockers
    assert "incompatible_local_policy_posture" in validate_federated_improvement_local_variant_artifact(_base(local_policy_posture="violates")).blockers
    assert "forbidden_adoption_execution_marker" in validate_federated_improvement_local_variant_artifact(_base(derivation_reason_codes=("install",))).blockers
    assert "forbidden_provider_network_export_runtime_prompt_marker" in validate_federated_improvement_local_variant_artifact(_base(modified_metadata_field_labels=("prompt_text",))).blockers
    assert "forbidden_secret_endpoint_client_marker" in validate_federated_improvement_local_variant_artifact(_base(modified_metadata_field_labels=("api_key",))).blockers
    assert "forbidden_raw_patch_or_executable_payload_marker" in validate_federated_improvement_local_variant_artifact(_base(modified_metadata_field_labels=("diff --git",))).blockers
    assert "forbidden_governance_bypass_marker" in validate_federated_improvement_local_variant_artifact(_base(derivation_reason_codes=("bypass_governance",))).blockers


def test_digest_and_summary_shape_and_exports_and_integration_path():
    c = _candidate()
    i = build_federated_improvement_intake_receipt(c, receiving_node_id="node-local", intake_receipt_id="intake-1", intake_decision=FederatedImprovementIntakeDecision.ADAPT_LOCALLY)
    readiness = FederatedImprovementAdoptionReadinessManifest(
        receiving_node_id="node-local", producing_node_id="node-upstream", candidate_id="cand-1", candidate_digest="d", candidate_kind=FederatedImprovementCandidateKind.POLICY_GATE_IMPROVEMENT,
        intake_receipt_id="intake-1", intake_receipt_digest="d1", rehearsal_authorization_id="a", rehearsal_authorization_digest="d2", rehearsal_result_id="r", rehearsal_result_digest="d3",
        local_review_receipt_id="l", local_review_receipt_digest="d4", audit_verification_status="verified", immutable_verification_status="verified", compatibility_posture="compatible", local_policy_posture="compliant", lineage_refs=("cand-1@d",)
    )
    v = _base(intake_receipt=i, adoption_readiness_manifest=readiness)
    assert compute_federated_improvement_local_variant_artifact_digest(v) == compute_federated_improvement_local_variant_artifact_digest(v)
    s = summarize_federated_improvement_local_variant_artifact(v)
    assert set(s.keys()) == {"deriving_node_id","original_producing_node_id","original_candidate_id","original_candidate_digest","local_variant_id","local_variant_kind","local_variant_status","required_gate_count","accepted_gate_count","rejected_gate_count","pending_gate_count","warning_count","risk_count","lineage_ref_count","metadata_only","not_adopted","no_remote_authority"}
    assert v.not_adopted and v.not_production_executed and v.no_remote_authority and v.no_forced_update and v.no_provider_network_export_prompt_runtime_authority
    assert isinstance(v, FederatedImprovementLocalVariantArtifact)
