from __future__ import annotations

from dataclasses import replace
import importlib
import subprocess
import sys

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.federation.improvement_candidate import (
    CANDIDATE_KINDS,
    CANDIDATE_STATUSES,
    CandidateTestEvidence,
    FederatedImprovementCandidate,
    FederatedImprovementCandidateKind,
    FederatedImprovementCandidateStatus,
    compute_federated_improvement_candidate_digest,
    explain_federated_improvement_candidate,
    federated_improvement_candidate_has_no_remote_authority,
    federated_improvement_candidate_is_metadata_only,
    federated_improvement_candidate_is_transmissible_evidence_only,
    federated_improvement_candidate_ready_for_receipt_inspection,
    summarize_federated_improvement_candidate,
    validate_federated_improvement_candidate,
)

READY = FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_READY
READY_WITH_CONDITIONS = (
    FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_READY_WITH_CONDITIONS
)
BLOCKED = FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_BLOCKED
INCOMPLETE = FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_INCOMPLETE
CONTRADICTED = FederatedImprovementCandidateStatus.FEDERATED_IMPROVEMENT_CANDIDATE_CONTRADICTED


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


def test_clean_metadata_only_candidate_is_ready() -> None:
    candidate = _candidate()
    validation = validate_federated_improvement_candidate(candidate)

    assert validation.status == READY
    assert validation.blockers == ()
    assert federated_improvement_candidate_is_metadata_only(candidate)
    assert federated_improvement_candidate_is_transmissible_evidence_only(candidate)
    assert federated_improvement_candidate_has_no_remote_authority(candidate)
    assert federated_improvement_candidate_ready_for_receipt_inspection(candidate)
    assert "receipt:inspection_rehearsal_adaptation_rejection_or_separate_local_adoption_only" in explain_federated_improvement_candidate(candidate)


def test_ready_with_conditions_candidate() -> None:
    candidate = _candidate(
        required_local_review_gates=("council_review_gate",),
        adoption_constraints=("local_adoption_requires_separate_vote",),
        federation_compatibility_posture="compatible_with_conditions",
    )

    validation = validate_federated_improvement_candidate(candidate)

    assert validation.status == READY_WITH_CONDITIONS
    assert validation.blockers == ()
    assert federated_improvement_candidate_is_transmissible_evidence_only(candidate)


def test_blocked_candidate_from_failed_audit_verification() -> None:
    validation = validate_federated_improvement_candidate(_candidate(audit_verification_status="failed"))

    assert validation.status == BLOCKED
    assert "audit_verification_failed" in validation.blockers


def test_blocked_candidate_from_failed_immutable_verification() -> None:
    validation = validate_federated_improvement_candidate(_candidate(immutable_verification_status="failed"))

    assert validation.status == BLOCKED
    assert "immutable_verification_failed" in validation.blockers


def test_incomplete_candidate_from_missing_node_candidate_or_source_evidence() -> None:
    validation = validate_federated_improvement_candidate(
        _candidate(
            producing_node_id="",
            local_candidate_id="",
            source_amendment_or_proposal_id="",
            source_commit_ref_digest="",
            lineage_refs=(),
        )
    )

    assert validation.status == INCOMPLETE
    assert "missing_producing_node_id" in validation.blockers
    assert "missing_local_candidate_id" in validation.blockers
    assert "missing_lineage_or_source_evidence" in validation.blockers


def test_incomplete_candidate_from_missing_test_or_rehearsal_evidence_when_required() -> None:
    validation = validate_federated_improvement_candidate(
        _candidate(test_evidence=(), rehearsal_artifact_refs=())
    )

    assert validation.status == INCOMPLETE
    assert "missing_test_or_rehearsal_evidence" in validation.blockers


def test_contradiction_from_auto_adoption_or_remote_execution_markers() -> None:
    validation = validate_federated_improvement_candidate(
        _candidate(adoption_constraints=("adopt_on_receipt", "remote_execution"))
    )

    assert validation.status == CONTRADICTED
    assert "forbidden_adoption_or_remote_execution_marker" in validation.blockers
    assert not federated_improvement_candidate_is_transmissible_evidence_only(_candidate(adoption_constraints=("auto_update",)))


def test_contradiction_from_provider_network_export_runtime_prompt_markers() -> None:
    validation = validate_federated_improvement_candidate(
        _candidate(known_risk_codes=("provider_client_requested", "network_handle", "prompt_text"))
    )

    assert validation.status == CONTRADICTED
    assert "provider_network_export_runtime_prompt_marker" in validation.blockers


def test_contradiction_from_secret_endpoint_client_material() -> None:
    validation = validate_federated_improvement_candidate(
        _candidate(known_risk_codes=("api_key_present", "endpoint_present", "client_handle_present"))
    )

    assert validation.status == CONTRADICTED
    assert "secret_endpoint_client_marker" in validation.blockers


def test_federation_compatibility_contradiction() -> None:
    validation = validate_federated_improvement_candidate(
        _candidate(federation_compatibility_posture="incompatible")
    )

    assert validation.status == CONTRADICTED
    assert "federation_compatibility_contradiction" in validation.blockers


def test_local_governance_bypass_marker() -> None:
    validation = validate_federated_improvement_candidate(
        _candidate(required_local_review_gates=("bypass_governance",))
    )

    assert validation.status == CONTRADICTED
    assert "local_governance_gate_bypass_marker" in validation.blockers


def test_deterministic_digest_behavior() -> None:
    first = _candidate()
    equivalent = _candidate()
    changed = _candidate(local_candidate_id="candidate-002")

    assert compute_federated_improvement_candidate_digest(first) == compute_federated_improvement_candidate_digest(equivalent)
    assert compute_federated_improvement_candidate_digest(first) != compute_federated_improvement_candidate_digest(changed)


def test_summary_shape_contains_only_metadata_labels_counts_booleans_and_statuses() -> None:
    summary = summarize_federated_improvement_candidate(_candidate())

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
        "producing_node_id",
        "local_candidate_id",
        "candidate_kind",
        "status",
        "digest",
        "source_amendment_or_proposal_id",
        "source_commit_ref_digest",
        "rationale_digest_or_label",
        "test_evidence_count",
        "test_result_labels",
        "rehearsal_artifact_ref_count",
        "audit_verification_status",
        "immutable_verification_status",
        "federation_compatibility_posture",
        "required_local_review_gate_count",
        "adoption_constraint_count",
        "known_risk_code_count",
        "lineage_ref_count",
        "metadata_only",
        "locally_produced",
        "transmissible_evidence_only",
        "not_adopted_by_default",
        "not_executable_by_receipt",
        "no_remote_authority",
        "no_forced_update",
        "no_provider_network_export_prompt_runtime_authority",
        "no_secret_endpoint_client_material",
        "blocker_count",
        "warning_count",
    }
    assert all(not isinstance(value, dict) for value in summary.values())


def test_predicate_helpers_remain_conservative() -> None:
    contradicted = _candidate(adoption_constraints=("execute_on_receipt",))
    incomplete = _candidate(producing_node_id="")

    assert not federated_improvement_candidate_is_transmissible_evidence_only(contradicted)
    assert not federated_improvement_candidate_has_no_remote_authority(contradicted)
    assert not federated_improvement_candidate_ready_for_receipt_inspection(incomplete)
    assert federated_improvement_candidate_is_metadata_only(incomplete)


def test_statuses_and_kinds_are_compact_and_complete() -> None:
    assert READY in CANDIDATE_STATUSES
    assert READY_WITH_CONDITIONS in CANDIDATE_STATUSES
    assert BLOCKED in CANDIDATE_STATUSES
    assert INCOMPLETE in CANDIDATE_STATUSES
    assert CONTRADICTED in CANDIDATE_STATUSES
    assert FederatedImprovementCandidateKind.MEMORY_DISTILLATION_IMPROVEMENT in CANDIDATE_KINDS
    assert FederatedImprovementCandidateKind.CODEX_REPAIR_IMPROVEMENT in CANDIDATE_KINDS
    assert FederatedImprovementCandidateKind.DOCUMENTATION_OR_DEMO_IMPROVEMENT in CANDIDATE_KINDS


def test_no_prompt_assembler_modification() -> None:
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", "prompt_assembler.py"],
        check=False,
        cwd=".",
    )

    assert result.returncode == 0


def test_no_runtime_provider_network_export_authority_imports() -> None:
    before = set(sys.modules)
    module = importlib.import_module("sentientos.federation.improvement_candidate")
    imported = set(sys.modules) - before

    assert module.FederatedImprovementCandidate is FederatedImprovementCandidate
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
