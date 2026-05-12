from sentientos.federation import *


def _candidate():
    return FederatedImprovementCandidate(
        producing_node_id="node-a",
        local_candidate_id="cand-1",
        candidate_kind=FederatedImprovementCandidateKind.FEDERATION_PROTOCOL_IMPROVEMENT,
        source_amendment_or_proposal_id="prop-1",
        source_commit_ref_digest="abc",
        rationale_digest_or_label="r1",
        test_evidence=(CandidateTestEvidence(command_label="pytest", result_label="passed"),),
        rehearsal_artifact_refs=("reh-1",),
        audit_verification_status="verified",
        immutable_verification_status="verified",
        required_local_review_gates=("gate-a",),
        lineage_refs=("cand-1:abc",),
    )


def _variant():
    c = _candidate()
    return build_federated_improvement_local_variant_artifact(
        deriving_node_id="node-b",
        original_candidate=c,
        local_variant_id="var-1",
        local_variant_kind=FederatedImprovementVariantKind.LOCAL_POLICY_VARIANT,
        local_variant_status=FederatedImprovementVariantStatus.READY,
        derivation_reason_codes=("policy-local",),
        modified_metadata_field_labels=("policy",),
        unchanged_invariant_labels=("metadata_only",),
        required_local_gate_codes=("gate-a",),
        accepted_gate_codes=("gate-a",),
        audit_verification_status="verified",
        immutable_verification_status="verified",
        lineage_refs=("cand-1:abc",),
    )


def _lineage():
    return build_federated_improvement_lineage_comparison_receipt(
        comparing_node_id="node-b",
        original_candidate=_candidate(),
        local_variant=_variant(),
        comparison_status=FederatedImprovementLineageComparisonStatus.COMPATIBLE,
        comparison_dimensions=tuple((d, "compatible") for d in LINEAGE_COMPARISON_DIMENSIONS),
        lineage_refs=("cand-1:abc", "var-1:def"),
    )


def test_ready_candidate_only():
    r = build_federated_improvement_dissemination_receipt(
        dissemination_receipt_id="dis-1", disseminating_node_id="node-b", dissemination_status=FederatedImprovementDisseminationStatus.READY,
        dissemination_scope=FederatedImprovementDisseminationScope.LOCAL_CATALOG_ONLY, catalog_label="cat-a", peer_visibility_label="peers:all",
        original_candidate=_candidate(), required_local_gate_codes=("gate-a",), accepted_gate_codes=("gate-a",), lineage_refs=("cand-1:abc",),
    )
    assert validate_federated_improvement_dissemination_receipt(r).status == FederatedImprovementDisseminationStatus.READY


def test_ready_variant_lineage():
    r = build_federated_improvement_dissemination_receipt(
        dissemination_receipt_id="dis-2", disseminating_node_id="node-b", dissemination_status=FederatedImprovementDisseminationStatus.READY,
        dissemination_scope=FederatedImprovementDisseminationScope.PEER_INDEX_METADATA_ONLY, catalog_label="cat", peer_visibility_label="peers:stewards",
        original_candidate=_candidate(), local_variant=_variant(), lineage_comparison=_lineage(), required_local_gate_codes=("gate-a",), accepted_gate_codes=("gate-a",),
    )
    assert r.evidence_ref_count == 3


def test_fail_closed_markers_and_conditions():
    r = build_federated_improvement_dissemination_receipt(
        dissemination_receipt_id="dis-3", disseminating_node_id="", dissemination_status=FederatedImprovementDisseminationStatus.READY,
        dissemination_scope="bad_scope", catalog_label="", peer_visibility_label="endpoint://x",
        original_candidate=_candidate(), required_local_gate_codes=("gate-a",), pending_gate_codes=("gate-a",), lineage_refs=(),
    )
    v = validate_federated_improvement_dissemination_receipt(r)
    assert v.status in {FederatedImprovementDisseminationStatus.INCOMPLETE, FederatedImprovementDisseminationStatus.CONTRADICTED}
    assert "unknown_dissemination_scope" in v.blockers


def test_digest_deterministic_and_summary_shape():
    r1 = build_federated_improvement_dissemination_receipt(
        dissemination_receipt_id="dis-x", disseminating_node_id="node-b", dissemination_status=FederatedImprovementDisseminationStatus.READY_WITH_CONDITIONS,
        dissemination_scope=FederatedImprovementDisseminationScope.STEWARD_REVIEW_INDEX, catalog_label="cat", peer_visibility_label="reviewers",
        original_candidate=_candidate(), required_local_gate_codes=("gate-a",), accepted_gate_codes=("gate-a",), lineage_refs=("cand-1:abc",),
    )
    r2 = build_federated_improvement_dissemination_receipt(
        dissemination_receipt_id="dis-x", disseminating_node_id="node-b", dissemination_status=FederatedImprovementDisseminationStatus.READY_WITH_CONDITIONS,
        dissemination_scope=FederatedImprovementDisseminationScope.STEWARD_REVIEW_INDEX, catalog_label="cat", peer_visibility_label="reviewers",
        original_candidate=_candidate(), required_local_gate_codes=("gate-a",), accepted_gate_codes=("gate-a",), lineage_refs=("cand-1:abc",),
    )
    assert compute_federated_improvement_dissemination_receipt_digest(r1) == compute_federated_improvement_dissemination_receipt_digest(r2)
    s = summarize_federated_improvement_dissemination_receipt(r1)
    assert set(s).issuperset({"candidate_id", "candidate_digest", "dissemination_status", "catalog_label", "evidence_ref_count"})


def test_conservative_helpers_and_integration_style():
    c = _candidate()
    intake = build_federated_improvement_intake_receipt(receiving_node_id="node-b", candidate=c, intake_status=FederatedImprovementIntakeStatus.ACCEPTED_FOR_REHEARSAL, intake_decision=FederatedImprovementIntakeDecision.REHEARSAL_ONLY, local_policy_posture="local_review_required", local_compatibility_posture="compatible", required_gate_codes=("gate-a",), accepted_gate_codes=("gate-a",), lineage_refs=("cand-1:abc",))
    ia = FederatedImprovementRehearsalAuthorization(receiving_node_id="node-b",producing_node_id="node-a",source_candidate_id="cand-1",source_candidate_digest=compute_federated_improvement_candidate_digest(c),intake_receipt_id="i1",intake_receipt_digest=compute_federated_improvement_intake_receipt_digest(intake),expected_intake_receipt_digest=compute_federated_improvement_intake_receipt_digest(intake),required_gate_codes=("gate-a",),accepted_gate_codes=("gate-a",),local_compatibility_posture="compatible")
    rr = FederatedImprovementRehearsalResult(receiving_node_id="node-b",producing_node_id="node-a",candidate_id="cand-1",candidate_digest=compute_federated_improvement_candidate_digest(c),rehearsal_authorization_id="ra1",rehearsal_authorization_digest=compute_federated_improvement_rehearsal_authorization_digest(ia),expected_rehearsal_authorization_digest=compute_federated_improvement_rehearsal_authorization_digest(ia),audit_verification_status="verified",immutable_verification_status="verified")
    lr = FederatedImprovementLocalReviewReceipt(local_reviewer_ref_label="rev",receiving_node_id="node-b",producing_node_id="node-a",candidate_id="cand-1",candidate_digest=compute_federated_improvement_candidate_digest(c),intake_receipt_id="i1",intake_receipt_digest=compute_federated_improvement_intake_receipt_digest(intake),rehearsal_authorization_id="ra1",rehearsal_authorization_digest=compute_federated_improvement_rehearsal_authorization_digest(ia),rehearsal_result_id="rr1",rehearsal_result_digest=compute_federated_improvement_rehearsal_result_digest(rr),review_decision=FederatedImprovementLocalReviewDecision.ACCEPT_WITH_CONDITIONS,required_gate_codes=("gate-a",),accepted_gate_codes=("gate-a",))
    ar = FederatedImprovementAdoptionReadinessManifest(receiving_node_id="node-b",producing_node_id="node-a",candidate_id="cand-1",candidate_digest=compute_federated_improvement_candidate_digest(c),candidate_kind=c.candidate_kind,intake_receipt_id="i1",intake_receipt_digest=compute_federated_improvement_intake_receipt_digest(intake),rehearsal_authorization_id="ra1",rehearsal_authorization_digest=compute_federated_improvement_rehearsal_authorization_digest(ia),rehearsal_result_id="rr1",rehearsal_result_digest=compute_federated_improvement_rehearsal_result_digest(rr),local_review_receipt_id="lr1",local_review_receipt_digest=compute_federated_improvement_local_review_receipt_digest(lr),audit_verification_status="verified",immutable_verification_status="verified",compatibility_posture="compatible",local_policy_posture="compliant")
    v = _variant(); l = _lineage()
    d = build_federated_improvement_dissemination_receipt(dissemination_receipt_id="dis-int", disseminating_node_id="node-b", dissemination_status=FederatedImprovementDisseminationStatus.READY_WITH_CONDITIONS, dissemination_scope=FederatedImprovementDisseminationScope.FEDERATION_DIGEST_ANNOUNCEMENT, catalog_label="digest", peer_visibility_label="federation_peers", original_candidate=c, local_variant=v, lineage_comparison=l, required_local_gate_codes=("gate-a",), accepted_gate_codes=("gate-a",), source_intake_receipt_id="i1", source_intake_receipt_digest=compute_federated_improvement_intake_receipt_digest(intake), source_rehearsal_authorization_id="ra1", source_rehearsal_authorization_digest=compute_federated_improvement_rehearsal_authorization_digest(ia), source_rehearsal_result_id="rr1", source_rehearsal_result_digest=compute_federated_improvement_rehearsal_result_digest(rr), source_local_review_receipt_id="lr1", source_local_review_receipt_digest=compute_federated_improvement_local_review_receipt_digest(lr), source_adoption_readiness_manifest_id="ar1", source_adoption_readiness_manifest_digest=compute_federated_improvement_adoption_readiness_manifest_digest(ar))
    assert federated_improvement_dissemination_receipt_is_metadata_only(d)
    assert federated_improvement_dissemination_receipt_preserves_sovereignty(d)
