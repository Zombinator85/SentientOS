"""Frozen future-only metadata for publisher-attempt identity evidence."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

CONTRACT_SCHEMA = "sentientos.production_chat_resource_provisioning_request_publisher_attempt_identity_contract:v1"
FUTURE_EVIDENCE_SCHEMA = "sentientos.production_chat_resource_provisioning_request_publisher_attempt_identity:v1"
PUBLISHER_CAPABILITY_ID = "production_chat_resource_provisioning_request_publish"
PUBLISHER_PRINCIPAL = "deterministic_production_chat_resource_provisioning_request_publisher"
PUBLISHER_AUTHORITY_DEFINITION_DIGEST = "349058b7e6959c06bfae1a8acabd01c6c022245c6fd404e63535cac6ed608cf5"

FUTURE_EVIDENCE_FIELDS = (
    "schema_version", "publication_attempt_id", "installation_identity",
    "resource_provisioning_id", "request_digest", "request_storage_sha256",
    "request_storage_bytes", "intent_digest", "publisher_capability_id",
    "publisher_principal", "publisher_authority_definition_digest",
    "attempt_started_at", "attempt_identity_contract_digest",
    "synthetic_test_evidence", "identity_digest",
)
EVIDENCE_DIGEST_EXCLUDED_FIELDS = ("identity_digest",)
PROVENANCE_REQUIREMENTS: Mapping[str, bool] = {
    "verifier_created_or_verifier_authenticated_evidence_required": True,
    "caller_authored_provenance_sufficient": False,
    "artifact_self_attestation_sufficient": False,
    "string_evidence_source_sufficient": False,
    "log_line_sufficient": False,
    "model_output_sufficient": False,
    "operator_recollection_sufficient": False,
    "synthetic_test_evidence_satisfies_production": False,
    "independent_authority_definition_recomputation_required": True,
    "exact_identity_digest_binding_required": True,
    "pre_effect_ordering_proof_required": True,
}
DENIED_INFERENCES = (
    "request_existence", "bare_request_doctor_status", "request_digest_alone",
    "request_storage_hash_alone", "intent_digest_alone", "installation_and_provisioning_id_alone",
    "caller_supplied_attempt_id", "retrospectively_generated_attempt_id", "timestamp_alone",
    "pid", "process_identity", "lock_file_identity", "log_correlation_id",
    "chat_or_session_correlation_id", "arbitrary_uuid", "model_generated_id",
    "operator_recollection", "matching_publisher_principal_string", "matching_capability_string",
    "matching_authority_definition_digest_literal", "structurally_valid_identity_json_without_independent_provenance",
    "valid_identity_digest_over_caller_authored_json", "synthetic_test_evidence_in_production",
)
NON_AUTHORITY_POSTURE: Mapping[str, bool] = {key: True for key in (
    "attempt_identity_contract_is_metadata_only", "attempt_identity_contract_is_contract_only",
    "attempt_identity_contract_is_future_only", "attempt_identity_contract_does_not_emit_evidence",
    "attempt_identity_contract_does_not_verify_live_evidence", "attempt_identity_contract_does_not_observe_runtime_state",
    "attempt_identity_contract_does_not_write_installation_state", "attempt_identity_contract_does_not_modify_publisher",
    "attempt_identity_contract_does_not_lock", "attempt_identity_contract_does_not_publish_request",
    "attempt_identity_contract_does_not_publish_receipt", "attempt_identity_contract_does_not_create_terminal_closure",
    "attempt_identity_contract_does_not_infer_terminality", "attempt_identity_contract_does_not_recover",
    "attempt_identity_contract_does_not_retry", "attempt_identity_contract_does_not_authorize_reuse",
    "attempt_identity_contract_does_not_allocate", "attempt_identity_contract_does_not_execute",
    "attempt_identity_contract_does_not_register_authority", "attempt_identity_contract_does_not_grant_authority",
    "attempt_identity_contract_does_not_widen_publisher_authority",
)}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def attempt_identity_contract_digest(contract: Mapping[str, Any]) -> str:
    body = dict(contract)
    body.pop("canonical_contract_digest", None)
    return hashlib.sha256(_canonical(body)).hexdigest()


def build_production_chat_resource_provisioning_request_attempt_identity_contract() -> dict[str, Any]:
    future_gap = {"future_only": True, "currently_implemented": False, "currently_satisfied": False}
    contract: dict[str, Any] = {
        "schema": CONTRACT_SCHEMA,
        "future_evidence_schema": FUTURE_EVIDENCE_SCHEMA,
        "purpose": "A valid publisher-attempt identity artifact identifies exactly one governed publisher invocation and binds the exact request the invocation intended to publish before that invocation performs its first durable mutation of publication custody.",
        "proves_only": "pre_effect_identity_of_one_exact_governed_publisher_invocation_and_its_exact_intended_request",
        "does_not_prove": ["request_publication_completed", "request_creation_occurred", "receipt_creation_occurred", "publisher_later_failed", "publisher_later_succeeded", "terminality", "recovery_eligibility", "same_id_reuse_eligibility", "allocation", "execution"],
        "publisher_definition_binding": {"capability_id": PUBLISHER_CAPABILITY_ID, "principal": PUBLISHER_PRINCIPAL, "authority_definition_digest": PUBLISHER_AUTHORITY_DEFINITION_DIGEST, "independent_recomputation_required": True},
        "future_evidence_fields": list(FUTURE_EVIDENCE_FIELDS),
        "closed_future_evidence_schema": True,
        "canonical_evidence_law": {"hash_algorithm": "sha256", "encoding": "utf-8", "sort_keys": True, "separators": [",", ":"], "ensure_ascii": True, "finite_json_only": True, "digest_fields": [field for field in FUTURE_EVIDENCE_FIELDS if field != "identity_digest"], "excluded_fields": list(EVIDENCE_DIGEST_EXCLUDED_FIELDS), "output": "lowercase_64_hex", "artifact_bytes_must_be_exact_canonical_json": True, "semantic_rewrites_are_not_same_durable_bytes": True},
        "request_binding_law": {"constructed_only_after_publisher_has_deterministically_constructed_and_validated": ["exact_actuator_compatible_request_bytes", "request_digest", "request_storage_sha256", "request_storage_bytes", "intent_digest"], "same_request_future_destination": "local-model/resource-provisioning-requests/<resource_provisioning_id>/request.json", "second_request_schema_forbidden": True, "translation_forbidden": True, "normalization_forbidden": True, "independent_reconstruction_from_caller_fields_forbidden": True, "eventual_emitter_consumes_publishers_exact_validated_request_bytes_and_intent": True, "source_bytes_or_request_packet_embedded": False},
        "attempt_id_law": {"identifies_exactly_one_publisher_invocation": True, "immutable": True, "nonempty": True, "maximum_length": 128, "forbidden_placeholder_values": ["*", "any", "current", "default", "latest", "placeholder", "sample", "test", "wildcard"], "wildcard_or_metacharacter_forms_forbidden": True, "must_not_equal_or_alias_resource_provisioning_id": True, "derivation_solely_from_installation_provisioning_and_request_digest_forbidden": True, "retrospective_synthesis_after_observing_failure_forbidden": True, "established_before_first_publication_custody_mutation": True, "unchanged_in_later_terminal_closure_evidence": True, "generated_or_established_by_future_governed_lifecycle_evidence_boundary": True, "unauthenticated_caller_claim_sufficient": False, "generation_mechanism_defined_here": False},
        "attempt_start_instant_law": {"canonical_utc": True, "second_resolution": True, "z_suffix": True, "historical_binding_metadata_only": True, "establishes_terminality_expiry_timeout_abandonment_or_recovery_eligibility": False, "time_passage_is_sufficient_evidence": False},
        "pre_effect_ordering_law": {"complete_provenance_verifiable_identity_evidence_required_before_first_publication_custody_mutation": True, "attempt_evidence_mutation_precedes_publication_custody_mutation": True, "publication_custody_root": "local-model/resource-provisioning-requests/<resource_provisioning_id>/", "publication_custody_files": ["request.json", "publication-receipt.json"], "timestamp_comparison_sufficient": False, "mechanical_governed_custody_provenance_proof_required": True, "identity_evidence_is_mutation_free": False},
        "future_fixed_custody_law": {"path_template": "local-model/resource-provisioning-request-attempts/<publication_attempt_id>/identity.json", "authenticated_installation_state_custody": True, "caller_selected_destination": False, "create_only": True, "immutable": True, "overwrite": False, "repair": False, "automatic_retry": False, "deletion_or_cleanup_authority_granted": False, "custody_attempt_id_matches_artifact": True, "artifact_installation_identity_matches_authenticated_installation": True, "resource_provisioning_id_is_binding_metadata_not_destination": True, "distinct_from_request_publication_custody": True, "counts_as_request_or_receipt_publication": False, "writer_implemented": False},
        "independently_verifiable_provenance": {**PROVENANCE_REQUIREMENTS, "must_establish": ["artifact_came_from_separately_governed_lifecycle_evidence_boundary", "boundary_authorized_for_exact_evidence_class", "exact_publisher_definition_binding", "identity_digest_matches_exact_durable_artifact_bytes", "evidence_completed_before_publication_custody_mutation_for_exact_attempt", "not_caller_authored_or_substituted", "production_evidence_explicitly_non_synthetic"], "correct_content_is_sufficient_provenance": False, "digest_proves_creator_or_lifecycle_order": False},
        "future_provenance_boundary_requirements": {name: dict(future_gap) for name in ("dedicated_governed_lifecycle_evidence_producer", "independently_verifiable_provenance_verifier", "exact_effect_surface", "exact_authority_definition_digest_once_registered", "production_non_synthetic_posture", "create_only_fixed_attempt_evidence_custody", "ordering_proof_before_publication_mutation")},
        "future_authority_identifiers": {"capability_id": None, "principal": None, "approval_id": None, "authority_definition_digest": None},
        "publisher_authority_relationship": {"publisher_request_publication_authority_equals_publisher_attempt_lifecycle_evidence_authority": False, "separately_reviewed_express_authority_required": True, "existing_five_effect_surface_reinterpreted_or_widened": False, "publisher_definition_modified": False},
        "recovery_review_relationship": {"refines_only_evidence_class": "pre_effect_publisher_attempt_identity_evidence", "covered_bindings": ["publication_attempt_id", "installation_identity", "resource_provisioning_id", "request_digest", "request_storage_sha256", "request_storage_bytes", "publisher_authority_definition_digest", "publisher_principal_identity", "publisher_principal_kind", "canonical_attempt_start_instant", "immutable_evidence_digest", "independently_verifiable_governed_lifecycle_provenance"], "recovery_review_machine_contract_modified": False, "remaining_open_gap": "publisher_attempt_identity_evidence_missing"},
        "current_state": {"future_evidence_schema_defined": True, "attempt_identity_emission_implemented": False, "attempt_identity_fixed_custody_implemented": False, "independent_provenance_mechanism_implemented": False, "provenance_verifier_implemented": False, "lifecycle_evidence_authority_registered": False, "publisher_modified_to_emit_evidence": False, "production_attempt_identity_evidence_currently_available": False},
        "denied_inferences": list(DENIED_INFERENCES),
        "emphatic_laws": ["correct_content_is_not_sufficient_provenance", "a_digest_proves_content_identity_not_creator_or_lifecycle_creation_time"],
        "non_authority_posture": dict(NON_AUTHORITY_POSTURE),
    }
    contract["canonical_contract_digest"] = attempt_identity_contract_digest(contract)
    return contract


ATTEMPT_IDENTITY_CONTRACT = build_production_chat_resource_provisioning_request_attempt_identity_contract()
ATTEMPT_IDENTITY_CONTRACT_DIGEST = ATTEMPT_IDENTITY_CONTRACT["canonical_contract_digest"]

__all__ = ["CONTRACT_SCHEMA", "FUTURE_EVIDENCE_SCHEMA", "PUBLISHER_CAPABILITY_ID",
           "PUBLISHER_PRINCIPAL", "PUBLISHER_AUTHORITY_DEFINITION_DIGEST", "FUTURE_EVIDENCE_FIELDS",
           "EVIDENCE_DIGEST_EXCLUDED_FIELDS", "PROVENANCE_REQUIREMENTS", "DENIED_INFERENCES",
           "NON_AUTHORITY_POSTURE", "ATTEMPT_IDENTITY_CONTRACT", "ATTEMPT_IDENTITY_CONTRACT_DIGEST",
           "attempt_identity_contract_digest", "build_production_chat_resource_provisioning_request_attempt_identity_contract"]
