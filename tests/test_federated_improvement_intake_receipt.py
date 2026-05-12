from __future__ import annotations

from dataclasses import replace
import importlib
import subprocess
import sys

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.federation.improvement_candidate import (
    CandidateTestEvidence,
    FederatedImprovementCandidate,
    FederatedImprovementCandidateKind,
    compute_federated_improvement_candidate_digest,
)
from sentientos.federation.improvement_intake_receipt import (
    INTAKE_DECISIONS,
    INTAKE_STATUSES,
    FederatedImprovementIntakeDecision,
    FederatedImprovementIntakeStatus,
    build_federated_improvement_intake_receipt,
    compute_federated_improvement_intake_receipt_digest,
    explain_federated_improvement_intake_receipt,
    federated_improvement_intake_receipt_allows_adaptation,
    federated_improvement_intake_receipt_allows_inspection,
    federated_improvement_intake_receipt_allows_rehearsal,
    federated_improvement_intake_receipt_has_no_remote_authority,
    federated_improvement_intake_receipt_is_metadata_only,
    federated_improvement_intake_receipt_preserves_local_custody,
    summarize_federated_improvement_intake_receipt,
    validate_federated_improvement_intake_receipt,
)

INSPECT = FederatedImprovementIntakeDecision.INSPECT_ONLY
REHEARSE = FederatedImprovementIntakeDecision.REHEARSE_LOCALLY
ADAPT = FederatedImprovementIntakeDecision.ADAPT_LOCALLY
REJECT = FederatedImprovementIntakeDecision.REJECT_CANDIDATE
HOLD = FederatedImprovementIntakeDecision.HOLD_FOR_OPERATOR_REVIEW
QUEUE = FederatedImprovementIntakeDecision.QUEUE_FOR_LOCAL_GOVERNANCE_REVIEW
READY_INSPECTION = FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_READY_FOR_INSPECTION
READY_REHEARSAL = FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_READY_FOR_REHEARSAL
READY_CONDITIONS = FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_READY_WITH_CONDITIONS
HOLD_REVIEW = FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_HOLD_FOR_LOCAL_REVIEW
REJECTED = FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_REJECTED
INCOMPLETE = FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_INCOMPLETE
CONTRADICTED = FederatedImprovementIntakeStatus.FEDERATED_IMPROVEMENT_INTAKE_CONTRADICTED


def _candidate(**kwargs: object) -> FederatedImprovementCandidate:
    base = FederatedImprovementCandidate(
        producing_node_id="node-alpha",
        local_candidate_id="candidate-001",
        candidate_kind=FederatedImprovementCandidateKind.FEDERATION_PROTOCOL_IMPROVEMENT,
        source_amendment_or_proposal_id="proposal-17",
        source_commit_ref_digest="sha256:abc123",
        rationale_digest_or_label="rationale_digest_001",
        test_evidence=(CandidateTestEvidence("py_compile_candidate_module", "passed"),),
        rehearsal_artifact_refs=("rehearsal_digest_001",),
        audit_verification_status="verified",
        immutable_verification_status="verified",
        federation_compatibility_posture="compatible",
        lineage_refs=("lineage_digest_001",),
    )
    return replace(base, **kwargs)


def _receipt(**kwargs: object):
    values = {
        "receiving_node_id": "node-local",
        "candidate": _candidate(),
        "intake_decision": INSPECT,
        "local_compatibility_posture": "compatible",
        "local_policy_posture": "local_policy_allows_intake",
    }
    values.update(kwargs)
    return build_federated_improvement_intake_receipt(**values)


def test_clean_ready_for_inspection_intake() -> None:
    receipt = _receipt()
    validation = validate_federated_improvement_intake_receipt(receipt)

    assert validation.status == READY_INSPECTION
    assert validation.blockers == ()
    assert federated_improvement_intake_receipt_is_metadata_only(receipt)
    assert federated_improvement_intake_receipt_preserves_local_custody(receipt)
    assert federated_improvement_intake_receipt_has_no_remote_authority(receipt)
    assert federated_improvement_intake_receipt_allows_inspection(receipt)
    assert "scope:intake_only_no_adoption_no_execution_no_forced_update" in explain_federated_improvement_intake_receipt(receipt)


def test_ready_for_rehearsal_intake() -> None:
    receipt = _receipt(intake_decision=REHEARSE, local_rehearsal_required=True)

    assert validate_federated_improvement_intake_receipt(receipt).status == READY_REHEARSAL
    assert federated_improvement_intake_receipt_allows_rehearsal(receipt)


def test_ready_with_conditions_intake() -> None:
    candidate = _candidate(federation_compatibility_posture="compatible_with_conditions")
    receipt = _receipt(candidate=candidate, intake_decision=ADAPT, local_adaptation_required=True)

    assert validate_federated_improvement_intake_receipt(receipt).status == READY_CONDITIONS
    assert federated_improvement_intake_receipt_allows_adaptation(receipt)


def test_hold_for_local_review_intake() -> None:
    candidate = _candidate(required_local_review_gates=("council_review_gate",))
    receipt = _receipt(candidate=candidate, intake_decision=QUEUE, pending_gate_codes=("council_review_gate",))

    assert validate_federated_improvement_intake_receipt(receipt).status == HOLD_REVIEW


def test_rejected_intake() -> None:
    receipt = _receipt(intake_decision=REJECT, rejection_reason_codes=("operator_rejected",))

    assert validate_federated_improvement_intake_receipt(receipt).status == REJECTED


def test_incomplete_intake_from_missing_receiving_node_id() -> None:
    validation = validate_federated_improvement_intake_receipt(_receipt(receiving_node_id=""))

    assert validation.status == INCOMPLETE
    assert "missing_receiving_node_id" in validation.blockers


def test_incomplete_intake_from_missing_candidate_metadata() -> None:
    validation = validate_federated_improvement_intake_receipt(_receipt(candidate=None))

    assert validation.status == INCOMPLETE
    assert "missing_candidate_metadata" in validation.blockers


def test_contradiction_from_candidate_digest_mismatch() -> None:
    receipt = _receipt(expected_candidate_digest="sha256:not-the-candidate")
    validation = validate_federated_improvement_intake_receipt(receipt)

    assert validation.status == CONTRADICTED
    assert "candidate_digest_mismatch" in validation.blockers


def test_contradiction_from_candidate_contradicted_status() -> None:
    receipt = _receipt(candidate=_candidate(adoption_constraints=("execute_on_receipt",)))
    validation = validate_federated_improvement_intake_receipt(receipt)

    assert validation.status == CONTRADICTED
    assert "candidate_contradicted_status" in validation.blockers


def test_blocked_candidate_can_only_be_rejected_or_held() -> None:
    blocked = _candidate(audit_verification_status="failed")
    inspect_validation = validate_federated_improvement_intake_receipt(_receipt(candidate=blocked))
    reject_validation = validate_federated_improvement_intake_receipt(_receipt(candidate=blocked, intake_decision=REJECT))
    hold_validation = validate_federated_improvement_intake_receipt(_receipt(candidate=blocked, intake_decision=HOLD))

    assert inspect_validation.status == HOLD_REVIEW
    assert "blocked_candidate_requires_reject_or_hold" in inspect_validation.blockers
    assert reject_validation.status == REJECTED
    assert hold_validation.status == HOLD_REVIEW


def test_incompatible_federation_posture_fails_closed() -> None:
    validation = validate_federated_improvement_intake_receipt(
        _receipt(candidate=_candidate(federation_compatibility_posture="incompatible"))
    )

    assert validation.status == CONTRADICTED
    assert "candidate_contradicted_status" in validation.blockers


def test_missing_required_local_review_gates_fails_closed() -> None:
    candidate = _candidate(required_local_review_gates=("council_review_gate",))
    validation = validate_federated_improvement_intake_receipt(_receipt(candidate=candidate))

    assert validation.status == HOLD_REVIEW
    assert "missing_required_local_review_gates" in validation.blockers


def test_local_governance_bypass_marker_fails_closed() -> None:
    validation = validate_federated_improvement_intake_receipt(_receipt(pending_gate_codes=("bypass_governance",)))

    assert validation.status == CONTRADICTED
    assert "local_governance_bypass_marker" in validation.blockers


def test_adoption_apply_install_merge_execute_marker_fails_closed() -> None:
    validation = validate_federated_improvement_intake_receipt(_receipt(rejection_reason_codes=("apply_on_receipt",)))

    assert validation.status == CONTRADICTED
    assert "forbidden_adoption_apply_install_merge_execute_marker" in validation.blockers


def test_provider_network_export_runtime_prompt_marker_fails_closed() -> None:
    validation = validate_federated_improvement_intake_receipt(_receipt(warning_codes=("runtime_handle",)))

    assert validation.status == CONTRADICTED
    assert "provider_network_export_runtime_prompt_marker" in validation.blockers


def test_secret_endpoint_client_marker_fails_closed() -> None:
    validation = validate_federated_improvement_intake_receipt(_receipt(warning_codes=("client_handle",)))

    assert validation.status == CONTRADICTED
    assert "secret_endpoint_client_marker" in validation.blockers


def test_raw_patch_or_executable_payload_marker_fails_closed() -> None:
    validation = validate_federated_improvement_intake_receipt(_receipt(warning_codes=("raw_patch",)))

    assert validation.status == CONTRADICTED
    assert "raw_patch_or_executable_payload_marker" in validation.blockers


def test_mapping_candidate_metadata_is_consumed_without_payload() -> None:
    candidate = _candidate()
    mapping = {
        "producing_node_id": candidate.producing_node_id,
        "local_candidate_id": candidate.local_candidate_id,
        "candidate_kind": candidate.candidate_kind,
        "source_amendment_or_proposal_id": candidate.source_amendment_or_proposal_id,
        "source_commit_ref_digest": candidate.source_commit_ref_digest,
        "test_evidence": ({"command_label": "py_compile_candidate_module", "result_label": "passed"},),
        "audit_verification_status": "verified",
        "immutable_verification_status": "verified",
        "federation_compatibility_posture": "compatible",
        "lineage_refs": ("lineage_digest_001",),
    }
    receipt = _receipt(candidate=mapping)

    assert validate_federated_improvement_intake_receipt(receipt).status == READY_INSPECTION
    assert receipt.candidate_digest == compute_federated_improvement_candidate_digest(
        _candidate(rationale_digest_or_label="", rehearsal_artifact_refs=())
    )


def test_deterministic_digest_behavior() -> None:
    first = _receipt()
    equivalent = _receipt()
    changed = _receipt(local_policy_posture="local_policy_requires_review")

    assert compute_federated_improvement_intake_receipt_digest(first) == compute_federated_improvement_intake_receipt_digest(equivalent)
    assert compute_federated_improvement_intake_receipt_digest(first) != compute_federated_improvement_intake_receipt_digest(changed)


def test_summary_shape_contains_only_ids_digests_statuses_counts_booleans_and_labels() -> None:
    summary = summarize_federated_improvement_intake_receipt(_receipt())

    forbidden_keys = {
        "patch_body",
        "raw_patch",
        "prompt_text",
        "endpoint",
        "client_handle",
        "runtime_handle",
        "executable_payload",
    }
    assert forbidden_keys.isdisjoint(summary)
    assert set(summary) == {
        "receiving_node_id",
        "producing_node_id",
        "source_candidate_id",
        "candidate_digest",
        "expected_candidate_digest",
        "receipt_digest",
        "candidate_kind",
        "candidate_status",
        "intake_status",
        "intake_decision",
        "candidate_compatibility_posture",
        "local_compatibility_posture",
        "local_policy_posture",
        "required_local_review_gate_count",
        "accepted_gate_count",
        "rejected_gate_count",
        "pending_gate_count",
        "local_rehearsal_required",
        "local_adaptation_required",
        "rejection_reason_count",
        "warning_count",
        "lineage_ref_count",
        "metadata_only",
        "intake_only",
        "local_custody_preserved",
        "candidate_not_adopted",
        "candidate_not_executed",
        "no_remote_authority",
        "no_forced_update",
        "no_provider_network_export_prompt_runtime_authority",
        "no_secret_endpoint_client_material",
        "blocker_count",
    }
    assert all(not isinstance(value, (dict, list, tuple)) for value in summary.values())


def test_predicate_helpers_remain_conservative() -> None:
    clean = _receipt()
    contradicted = _receipt(rejection_reason_codes=("execute_on_receipt",))
    incomplete = _receipt(receiving_node_id="")

    assert federated_improvement_intake_receipt_allows_inspection(clean)
    assert not federated_improvement_intake_receipt_has_no_remote_authority(contradicted)
    assert not federated_improvement_intake_receipt_preserves_local_custody(incomplete)
    assert federated_improvement_intake_receipt_is_metadata_only(incomplete)


def test_statuses_and_decisions_are_compact_and_complete() -> None:
    assert READY_INSPECTION in INTAKE_STATUSES
    assert READY_REHEARSAL in INTAKE_STATUSES
    assert READY_CONDITIONS in INTAKE_STATUSES
    assert HOLD_REVIEW in INTAKE_STATUSES
    assert REJECTED in INTAKE_STATUSES
    assert INCOMPLETE in INTAKE_STATUSES
    assert CONTRADICTED in INTAKE_STATUSES
    assert INSPECT in INTAKE_DECISIONS
    assert REHEARSE in INTAKE_DECISIONS
    assert ADAPT in INTAKE_DECISIONS
    assert REJECT in INTAKE_DECISIONS
    assert HOLD in INTAKE_DECISIONS
    assert QUEUE in INTAKE_DECISIONS


def test_package_init_exports_receipt_api() -> None:
    module = importlib.import_module("sentientos.federation")

    assert module.FederatedImprovementIntakeReceipt
    assert module.build_federated_improvement_intake_receipt is build_federated_improvement_intake_receipt


def test_no_prompt_assembler_modification() -> None:
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", "prompt_assembler.py"],
        check=False,
        cwd=".",
    )

    assert result.returncode == 0


def test_no_runtime_provider_network_export_authority_imports() -> None:
    before = set(sys.modules)
    module = importlib.import_module("sentientos.federation.improvement_intake_receipt")
    imported = set(sys.modules) - before

    assert module.FederatedImprovementIntakeReceipt
    forbidden_modules = {
        "openai",
        "requests",
        "httpx",
        "socket",
        "prompt_assembler",
        "memory_manager",
        "sentientos.runtime.shell",
    }
    assert forbidden_modules.isdisjoint(imported)
