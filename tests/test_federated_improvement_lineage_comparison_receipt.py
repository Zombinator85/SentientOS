from __future__ import annotations

import importlib
import sys

from sentientos.federation import *


def _candidate() -> FederatedImprovementCandidate:
    return FederatedImprovementCandidate(
        producing_node_id="node-upstream",
        local_candidate_id="cand-1",
        candidate_kind=FederatedImprovementCandidateKind.POLICY_GATE_IMPROVEMENT,
        source_amendment_or_proposal_id="prop-1",
        audit_verification_status="verified",
        immutable_verification_status="verified",
        lineage_refs=("cand-1@sha256:abc",),
        rehearsal_artifact_refs=("reh:1",),
    )


def _variant(c: FederatedImprovementCandidate) -> FederatedImprovementLocalVariantArtifact:
    return build_federated_improvement_local_variant_artifact(
        candidate=c,
        deriving_node_id="node-local",
        local_variant_id="variant-1",
        local_variant_kind=FederatedImprovementVariantKind.LOCAL_POLICY_VARIANT,
        local_variant_status=FederatedImprovementVariantStatus.READY,
        derivation_reason_codes=("local_policy_adjustment",),
        modified_metadata_field_labels=("local_policy_posture",),
        unchanged_invariant_labels=("metadata_only",),
        lineage_refs=(f"{c.local_candidate_id}@{compute_federated_improvement_candidate_digest(c)}",),
        audit_verification_status="verified",
        immutable_verification_status="verified",
        required_local_gate_codes=("gate:a",),
        accepted_gate_codes=("gate:a",),
        local_compatibility_posture="compatible",
        local_policy_posture="compliant",
    )


def _dims():
    return tuple((d, "compatible") for d in LINEAGE_COMPARISON_DIMENSIONS)


def test_lineage_comparison_matrix_and_integration_flow():
    c = _candidate()
    i = build_federated_improvement_intake_receipt(c, receiving_node_id="node-local", intake_receipt_id="intake-1", intake_decision=FederatedImprovementIntakeDecision.ADAPT_LOCALLY)
    v = _variant(c)
    r = build_federated_improvement_lineage_comparison_receipt(comparing_node_id="node-local", original_candidate=c, local_variant=v, comparison_status=FederatedImprovementLineageComparisonStatus.COMPATIBLE, comparison_dimensions=_dims(), source_intake_receipt_id=i.intake_receipt_id, source_intake_receipt_digest=compute_federated_improvement_intake_receipt_digest(i))
    assert validate_federated_improvement_lineage_comparison_receipt(r).blockers == ()
    assert r.original_candidate_id in " ".join(r.lineage_refs)
    assert r.original_candidate_digest in " ".join(r.lineage_refs)
    assert r.not_adopted and r.not_merged and r.not_production_executed and r.no_remote_authority and r.no_forced_update

    cond = build_federated_improvement_lineage_comparison_receipt(comparing_node_id="node-local", original_candidate=c, local_variant=v, comparison_status=FederatedImprovementLineageComparisonStatus.COMPATIBLE_WITH_CONDITIONS, comparison_dimensions=((LINEAGE_COMPARISON_DIMENSIONS[0], "compatible_with_conditions"), *tuple((d, "compatible") for d in LINEAGE_COMPARISON_DIMENSIONS[1:])))
    assert validate_federated_improvement_lineage_comparison_receipt(cond).status == FederatedImprovementLineageComparisonStatus.COMPATIBLE

    inc = build_federated_improvement_lineage_comparison_receipt(comparing_node_id="node-local", original_candidate=c, local_variant=v, comparison_status=FederatedImprovementLineageComparisonStatus.INCOMPATIBLE, comparison_dimensions=((LINEAGE_COMPARISON_DIMENSIONS[0], "incompatible"), *tuple((d, "compatible") for d in LINEAGE_COMPARISON_DIMENSIONS[1:])))
    assert validate_federated_improvement_lineage_comparison_receipt(inc).status == FederatedImprovementLineageComparisonStatus.COMPATIBLE


def test_fail_closed_and_digest_summary_predicates_and_exports():
    c=_candidate(); v=_variant(c)
    good = build_federated_improvement_lineage_comparison_receipt(comparing_node_id="node-local", original_candidate=c, local_variant=v, comparison_status=FederatedImprovementLineageComparisonStatus.COMPATIBLE, comparison_dimensions=_dims())
    assert compute_federated_improvement_lineage_comparison_receipt_digest(good) == compute_federated_improvement_lineage_comparison_receipt_digest(good)
    s = summarize_federated_improvement_lineage_comparison_receipt(good)
    assert set(s)=={"comparing_node_id","original_candidate_id","original_candidate_digest","local_variant_id","local_variant_digest","comparison_status","comparison_dimensions","compatible_dimension_count","conditional_dimension_count","incompatible_dimension_count","missing_dimension_count","warning_codes","risk_codes","lineage_refs","metadata_only","comparison_only","not_adopted","not_merged","no_remote_authority"}
    assert federated_improvement_lineage_comparison_receipt_is_metadata_only(good)
    assert federated_improvement_lineage_comparison_receipt_is_conservative(good)

    assert "missing_comparing_node_id" in validate_federated_improvement_lineage_comparison_receipt(build_federated_improvement_lineage_comparison_receipt(comparing_node_id="", original_candidate=c, local_variant=v, comparison_status=FederatedImprovementLineageComparisonStatus.COMPATIBLE, comparison_dimensions=_dims())).blockers
    assert "missing_original_candidate_metadata" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"original_candidate_id":""})).blockers
    assert "missing_local_variant_metadata" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"local_variant_id":""})).blockers
    assert "original_candidate_digest_mismatch" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"expected_original_candidate_digest":"bad"})).blockers
    assert "local_variant_digest_mismatch" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"expected_local_variant_digest":"bad"})).blockers
    assert "local_variant_lineage_not_pointing_to_original_candidate" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"lineage_refs":("x",)})).blockers
    assert "missing_derivation_reason_codes" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"derivation_reason_codes":()})).blockers
    assert "missing_comparison_dimensions" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"comparison_dimensions":()})).blockers
    assert "unknown_comparison_dimension" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"comparison_dimensions":(("nope","compatible"),)})).blockers
    assert "unknown_comparison_status" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"comparison_dimensions":((LINEAGE_COMPARISON_DIMENSIONS[0],"nope"),)})).blockers
    assert "incompatible_dimension_while_claiming_compatible" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"comparison_dimensions":((LINEAGE_COMPARISON_DIMENSIONS[0],"incompatible"),*tuple((d,"compatible") for d in LINEAGE_COMPARISON_DIMENSIONS[1:]))})).blockers
    assert "missing_dimension_while_claiming_compatible" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"comparison_dimensions":((LINEAGE_COMPARISON_DIMENSIONS[0],"missing"),*tuple((d,"compatible") for d in LINEAGE_COMPARISON_DIMENSIONS[1:]))})).blockers
    assert "forbidden_adoption_apply_install_merge_conflict_resolution_execute_marker" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"warning_codes":("install",)})).blockers
    assert "forbidden_production_execution_marker" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"warning_codes":("production_execution",)})).blockers
    assert "forbidden_remote_execution_marker" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"warning_codes":("remote_execution",)})).blockers
    assert "forbidden_provider_network_export_runtime_prompt_marker" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"warning_codes":("prompt_text",)})).blockers
    assert "forbidden_secret_endpoint_client_marker" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"warning_codes":("api_key",)})).blockers
    assert "forbidden_raw_patch_or_executable_payload_marker" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"modified_metadata_field_labels":("diff --git",)})).blockers
    assert "forbidden_local_governance_bypass_marker" in validate_federated_improvement_lineage_comparison_receipt(good.__class__(**{**good.__dict__,"warning_codes":("bypass_governance",)})).blockers
    assert not federated_improvement_lineage_comparison_receipt_is_conservative(good.__class__(**{**good.__dict__,"warning_codes":("remote_execution",)}))

    before=set(sys.modules)
    importlib.import_module("sentientos.federation.improvement_lineage_comparison_receipt")
    imported=set(sys.modules)-before
    assert {"openai","requests","httpx","socket","prompt_assembler"}.isdisjoint(imported)
