from __future__ import annotations

from dataclasses import replace

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.federation import *
from sentientos.federation.improvement_candidate import CandidateTestEvidence, FederatedImprovementCandidate, FederatedImprovementCandidateKind
from sentientos.federation.improvement_intake_receipt import build_federated_improvement_intake_receipt


def _candidate() -> FederatedImprovementCandidate:
    return FederatedImprovementCandidate(
        producing_node_id="node-a", local_candidate_id="cand-1", candidate_kind=FederatedImprovementCandidateKind.FEDERATION_PROTOCOL_IMPROVEMENT,
        source_amendment_or_proposal_id="p1", source_commit_ref_digest="d1", test_evidence=(CandidateTestEvidence("compile_label","passed"),),
        audit_verification_status="verified", immutable_verification_status="verified", federation_compatibility_posture="compatible", lineage_refs=("lin1",)
    )

def _intake():
    return build_federated_improvement_intake_receipt(receiving_node_id="node-b", candidate=_candidate(), local_compatibility_posture="compatible", local_policy_posture="policy_ok")

def _auth(**k):
    r=_intake(); d=compute_federated_improvement_intake_receipt_digest(r)
    x=FederatedImprovementRehearsalAuthorization("node-b","node-a","cand-1","cdig","intake-1",d,d,r.__class__.__name__,r.intake_decision,_candidate().candidate_kind,"compatible","policy_ok",FederatedImprovementRehearsalScope.METADATA_ONLY,("compile_label",),("pass",),"sandbox",("g1",),("g1",),(),(),(),(),("lin1",))
    return replace(x, **k)

def test_artifacts_and_runway() -> None:
    a=_auth(); av=validate_federated_improvement_rehearsal_authorization(a); assert av.status==FederatedImprovementRehearsalAuthorizationStatus.READY
    rd=compute_federated_improvement_rehearsal_authorization_digest(a)
    rr=FederatedImprovementRehearsalResult("ra1",rd,rd,"node-b","node-a","cand-1","cdig",_candidate().candidate_kind,a.rehearsal_scope,("compile_label",),("pass",),1,0,0,("art1:dig",),"verified","verified","compatible",(),("lin1",))
    rv=validate_federated_improvement_rehearsal_result(rr); assert rv.status==FederatedImprovementRehearsalResultStatus.PASSED
    lrr=FederatedImprovementLocalReviewReceipt("operator_label","node-b","node-a","cand-1","cdig","intake-1",a.intake_receipt_digest,"ra1",rd,"rr1",compute_federated_improvement_rehearsal_result_digest(rr),("g1",),("g1",),(),(),(),(),(),(),"expires",("lin1",),FederatedImprovementLocalReviewDecision.ACCEPT)
    lv=validate_federated_improvement_local_review_receipt(lrr); assert lv.status==FederatedImprovementLocalReviewStatus.ACCEPTED
    arm=FederatedImprovementAdoptionReadinessManifest("node-b","node-a","cand-1","cdig",_candidate().candidate_kind,"intake-1",a.intake_receipt_digest,"ra1",rd,"rr1",compute_federated_improvement_rehearsal_result_digest(rr),"lr1",compute_federated_improvement_local_review_receipt_digest(lrr),"verified","verified","compatible","policy_ok",("g1",),("g1",),(),(),(),(),("lin1",),"adoption_has_not_occurred")
    mv=validate_federated_improvement_adoption_readiness_manifest(arm)
    assert mv.status==FederatedImprovementAdoptionReadinessStatus.READY
    assert federated_improvement_adoption_readiness_manifest_is_metadata_only(arm)
    assert arm.no_remote_authority and arm.no_forced_update and arm.no_provider_network_export_prompt_runtime_authority and arm.no_execution and arm.no_adoption

def test_fail_closed_markers_and_digest_mismatch() -> None:
    assert validate_federated_improvement_rehearsal_authorization(_auth(expected_intake_receipt_digest="bad")).status == FederatedImprovementRehearsalAuthorizationStatus.CONTRADICTED
    assert "marker" in validate_federated_improvement_rehearsal_authorization(_auth(warning_codes=("runtime",))).blockers[0]
    rr=FederatedImprovementRehearsalResult("", "x","y","node-b","node-a","cand-1","cdig","k","metadata_only_rehearsal",(),(),0,1,0,(),"failed","failed","incompatible",(),())
    assert validate_federated_improvement_rehearsal_result(rr).status in {FederatedImprovementRehearsalResultStatus.INCOMPLETE, FederatedImprovementRehearsalResultStatus.CONTRADICTED}

def test_package_exports_and_determinism() -> None:
    a=_auth()
    assert compute_federated_improvement_rehearsal_authorization_digest(a)==compute_federated_improvement_rehearsal_authorization_digest(_auth())
    assert summarize_federated_improvement_rehearsal_authorization(a)["metadata_only"]
