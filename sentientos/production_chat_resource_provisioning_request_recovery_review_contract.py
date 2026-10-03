"""Frozen metadata for future review of an exact abandoned publication attempt.

This module deliberately contains no evidence evaluator or runtime observation.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

SCHEMA = "sentientos.production_chat_resource_provisioning_request_recovery_review_contract:v1"
PUBLISHER_AUTHORITY_DEFINITION_DIGEST = "349058b7e6959c06bfae1a8acabd01c6c022245c6fd404e63535cac6ed608cf5"

REQUIRED_EVIDENCE_CLASSES = (
    "bound_bare_request_custody_observation",
    "pre_effect_publisher_attempt_identity_evidence",
    "exact_publisher_attempt_terminal_closure_evidence",
    "post_terminal_same_request_custody_observation",
    "no_contradictory_evidence",
)

DENIED_INFERENCES = (
    "one_bare_request_doctor_report", "multiple_repeated_bare_request_doctor_reports",
    "elapsed_wall_clock_time", "arbitrary_timeout_threshold", "request_file_age",
    "filesystem_mtime_or_ctime", "lock_file_existence", "lock_file_absence", "lock_file_age",
    "inability_to_acquire_unrelated_lock", "pid_absence", "process_list_absence",
    "pid_file_absence", "host_restart", "service_restart", "machine_uptime",
    "caller_assertion", "operator_recollection", "chat_text", "model_output",
    "log_text_without_authenticated_lifecycle_provenance", "request_validity",
    "deterministic_intent_validity", "same_id_burn_semantics", "consumer_rejection",
    "publication_doctor_incomplete", "automatic_retry_is_forbidden",
)

NON_AUTHORITY_POSTURE: Mapping[str, bool] = {
    key: True for key in (
        "recovery_review_contract_is_metadata_only", "recovery_review_contract_is_contract_only",
        "recovery_review_contract_is_future_only", "recovery_review_contract_does_not_observe_runtime_state",
        "recovery_review_contract_does_not_poll", "recovery_review_contract_does_not_lock",
        "recovery_review_contract_does_not_publish", "recovery_review_contract_does_not_create_receipt",
        "recovery_review_contract_does_not_delete", "recovery_review_contract_does_not_repair",
        "recovery_review_contract_does_not_cleanup", "recovery_review_contract_does_not_retry",
        "recovery_review_contract_does_not_overwrite", "recovery_review_contract_does_not_authorize_reuse",
        "recovery_review_contract_does_not_allocate", "recovery_review_contract_does_not_execute",
        "recovery_review_contract_does_not_create_final_bundle", "recovery_review_contract_does_not_register_authority",
        "recovery_review_contract_does_not_grant_authority", "recovery_review_contract_does_not_classify_any_actual_attempt",
        "recovery_review_contract_does_not_treat_time_as_terminality",
        "recovery_review_contract_does_not_treat_lockfile_state_as_terminality",
    )
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def recovery_review_contract_digest(contract: Mapping[str, Any]) -> str:
    """Digest canonical finite JSON, excluding its non-self-referential digest field."""
    body = dict(contract)
    body.pop("canonical_contract_digest", None)
    return hashlib.sha256(_canonical(body)).hexdigest()


def build_production_chat_resource_provisioning_request_recovery_review_contract() -> dict[str, Any]:
    contract: dict[str, Any] = {
        "schema": SCHEMA,
        "purpose": "Define external evidence required to classify one exact bare-request publisher attempt as terminally abandoned.",
        "relationship_to_publication_doctor": {
            "doctor_proposition": "bare_request_at_observation_time",
            "review_proposition": "terminally_abandoned_exact_publication_attempt",
            "doctor_status_alone_satisfies_review": False,
            "rule": "Terminal abandonment is a conjunctive evidentiary classification, never an inference from one lock-free custody snapshot.",
        },
        "evidence_classes": {
            "bound_bare_request_custody_observation": {
                "required": True, "necessary_but_insufficient": True, "currently_implemented": True,
                "bindings": ["installation_identity", "resource_provisioning_id", "request_storage_sha256", "request_storage_bytes", "request_digest_when_structurally_valid"],
                "claims": {"custody_shape": "bare_request", "publication_complete": False, "snapshot_is_lock_free": True, "concurrent_publication_excluded": False, "terminal_failure_inferred": False},
                "proves_only": "incomplete_unpublished_custody_at_observation_point",
            },
            "pre_effect_publisher_attempt_identity_evidence": {
                "required": True, "future_only": True, "currently_implemented": False, "currently_satisfied": False,
                "created_before": "first_durable_publication_mutation",
                "bindings": ["publication_attempt_id", "installation_identity", "resource_provisioning_id", "request_digest", "request_storage_sha256", "request_storage_bytes", "publisher_authority_definition_digest", "publisher_principal_identity", "publisher_principal_kind", "canonical_attempt_start_instant", "immutable_evidence_digest", "independently_verifiable_governed_lifecycle_provenance"],
            },
            "exact_publisher_attempt_terminal_closure_evidence": {
                "required": True, "future_only": True, "currently_implemented": False, "currently_satisfied": False,
                "same_bindings": ["publication_attempt_id", "installation_identity", "resource_provisioning_id", "request_digest", "request_storage_sha256", "publisher_authority_definition_digest"],
                "must_establish": ["exact_invocation_terminal", "durable_request_creation_completed", "durable_receipt_creation_did_not_complete", "no_execution_for_exact_attempt_remains_active", "bounded_explicit_terminal_outcome", "terminal_reason_code", "canonical_terminal_instant", "immutable_provenance_bound_closure"],
                "distinguishes": ["normal_success", "failure_before_receipt", "abort_before_receipt", "cancellation_before_receipt"],
            },
            "post_terminal_same_request_custody_observation": {
                "required": True, "currently_implemented": True, "must_occur_after_terminal_closure": True,
                "same_bindings": ["installation_identity", "resource_provisioning_id", "request_storage_sha256", "request_storage_bytes", "request_digest_when_valid"],
                "claims": {"custody_shape": "bare_request", "receipt_genuinely_absent": True},
                "doctor_remains_lock_free_and_non_authoritative": True,
            },
            "no_contradictory_evidence": {"required": True, "must_be_true": True},
        },
        "required_evidence_classes": list(REQUIRED_EVIDENCE_CLASSES),
        "attempt_identity_law": {"bind_merely_to_installation_and_provisioning_id": False, "unique_for_one_publisher_invocation": True, "immutable": True, "created_before_first_publication_mutation": True, "included_in_identity_and_closure_evidence": True, "retrospective_synthesis_forbidden": True},
        "publisher_authority_definition_digest": PUBLISHER_AUTHORITY_DEFINITION_DIGEST,
        "evidence_provenance_law": {"caller_authored_terminality_claim_sufficient": False, "separately_governed_lifecycle_evidence_boundary_required": True, "independent_provenance_verification_required": True, "future_authority_defined_or_registered_here": False},
        "contradictions": ["valid_completed_publication_receipt", "installation_identity_mismatch", "resource_provisioning_id_mismatch", "request_bytes_or_hash_mismatch", "request_digest_mismatch", "publication_attempt_id_mismatch", "publisher_authority_definition_digest_mismatch", "successful_publisher_terminal_outcome", "terminal_closure_before_durable_request_creation", "durable_receipt_creation_completed", "malformed_or_unverifiable_attempt_lifecycle_provenance"],
        "terminal_abandonment_conjunction": {"outcome": "terminal_abandonment_evidence_complete", "all_required_evidence_classes_present": True, "all_evidence_internally_valid": True, "all_evidence_mutually_bound": True, "no_contradictory_evidence": True, "meaning_only": "evidence_standard_for_classifying_this_exact_publication_attempt_as_terminally_abandoned_is_satisfied"},
        "denied_inferences": list(DENIED_INFERENCES),
        "emphatic_laws": ["time_passage_is_not_terminality_evidence", "lock_pathname_state_is_not_publisher_attempt_lifecycle_evidence", "repeated_doctor_observations_do_not_replace_lifecycle_evidence"],
        "current_state": {"terminal_abandonment_classification_available": False, "recovery_authority_available": False, "same_id_reuse_authority_available": False, "blocking_gaps": ["publisher_attempt_identity_evidence_missing", "publisher_attempt_terminal_closure_evidence_missing", "publisher_attempt_lifecycle_provenance_missing"]},
        "review_outcomes": ["evidence_incomplete", "evidence_contradictory", "terminal_abandonment_evidence_complete", "completed_publication_observed"],
        "classification_and_recovery": {"terminal_abandonment_classification_equals_recovery_authorization": False, "permissions_granted": [], "still_forbidden": ["deletion", "repair", "cleanup", "receipt_completion", "retry", "republication", "overwrite", "rename_move_or_quarantine", "provisioning_id_reuse", "allocation", "bundle_creation", "execution"], "separately_governed_recovery_contract_and_authority_required": True},
        "existing_runtime_schemas_changed": False,
        "non_authority_posture": dict(NON_AUTHORITY_POSTURE),
    }
    contract["canonical_contract_digest"] = recovery_review_contract_digest(contract)
    return contract


RECOVERY_REVIEW_CONTRACT = build_production_chat_resource_provisioning_request_recovery_review_contract()
RECOVERY_REVIEW_CONTRACT_DIGEST = RECOVERY_REVIEW_CONTRACT["canonical_contract_digest"]

__all__ = ["SCHEMA", "PUBLISHER_AUTHORITY_DEFINITION_DIGEST", "REQUIRED_EVIDENCE_CLASSES",
           "DENIED_INFERENCES", "NON_AUTHORITY_POSTURE", "RECOVERY_REVIEW_CONTRACT",
           "RECOVERY_REVIEW_CONTRACT_DIGEST", "recovery_review_contract_digest",
           "build_production_chat_resource_provisioning_request_recovery_review_contract"]
