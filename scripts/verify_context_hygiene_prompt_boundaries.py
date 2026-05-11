#!/usr/bin/env python3
"""Static guardrails for context-hygiene prompt assembly boundaries.

This verifier reads source text and AST only. It intentionally does not import
prompt_assembler.py, context-hygiene helpers, memory/runtime modules, provider
SDKs, browser/tool controllers, or optional speech dependencies.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from pathlib import Path
import sys
from typing import Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SCAN_TARGETS: tuple[str, ...] = (
    "prompt_assembler.py",
    "sentientos/context_hygiene/prompt_synthetic_materializer.py",
    "sentientos/context_hygiene/prompt_internal_candidate.py",
    "sentientos/context_hygiene/prompt_internal_display.py",
    "sentientos/context_hygiene/prompt_model_call_preflight.py",
    "sentientos/context_hygiene/prompt_model_call_review.py",
    "sentientos/context_hygiene/prompt_provider_dry_run.py",
    "sentientos/context_hygiene/prompt_provider_dry_run_review.py",
    "sentientos/context_hygiene/prompt_provider_simulation.py",
    "sentientos/context_hygiene/prompt_network_egress_preflight.py",
    "sentientos/context_hygiene/prompt_network_egress_review.py",
    "sentientos/context_hygiene/prompt_provider_null_transport.py",
    "sentientos/context_hygiene/prompt_provider_transport_registry.py",
    "sentientos/context_hygiene/prompt_provider_transport_capability.py",
    "sentientos/context_hygiene/prompt_provider_credential_custody.py",
    "sentientos/context_hygiene/prompt_provider_endpoint_custody.py",
    "sentientos/context_hygiene/prompt_provider_client_custody.py",
    "sentientos/context_hygiene/prompt_provider_invocation_readiness.py",
    "sentientos/context_hygiene/prompt_provider_invocation_denial_review.py",
    "sentientos/context_hygiene/prompt_external_security_review.py",
    "sentientos/context_hygiene/prompt_external_audit_export.py",
    "sentientos/context_hygiene/prompt_provider_invocation_denial_attestation.py",
    "sentientos/context_hygiene/prompt_provider_invocation_denial_closure.py",
    "sentientos/context_hygiene/prompt_materialization_policy.py",
    "sentientos/context_hygiene/prompt_operator_review.py",
    "sentientos/context_hygiene/prompt_materialization_audit.py",
    "sentientos/context_hygiene/prompt_assembler_compliance.py",
    "sentientos/context_hygiene/prompt_adapter_contract.py",
    "sentientos/context_hygiene/prompt_constraint_verifier.py",
    "sentientos/context_hygiene/prompt_dry_run_envelope.py",
    "sentientos/context_hygiene/prompt_handoff_manifest.py",
    "sentientos/context_hygiene/prompt_preflight.py",
    "sentientos/context_hygiene/context_packet.py",
    "sentientos/context_hygiene/safety_metadata.py",
    "sentientos/context_hygiene/source_kind_contracts.py",
    "sentientos/context_hygiene/selector.py",
)

FORBIDDEN_FIELD_PATTERNS: tuple[str, ...] = (
    "final_prompt",
    "final_prompt_text",
    "assembled_prompt",
    "prompt_text",
    "rendered_prompt",
    "materialized_prompt",
    "system_prompt",
    "developer_prompt",
    "llm_params",
    "llm_parameters",
    "model_params",
    "provider_params",
    "api_key",
    "endpoint",
    "headers",
    "auth",
    "client",
    "session",
    "raw_payload",
    "raw_memory_payload",
    "raw_screen_payload",
    "raw_audio_payload",
    "raw_vision_payload",
    "raw_multimodal_payload",
    "execution_handle",
    "action_handle",
    "retention_handle",
    "retrieval_handle",
    "browser_handle",
    "mouse_handle",
    "keyboard_handle",
)

NEGATIVE_MARKER_PREFIXES: tuple[str, ...] = (
    "does_not_",
    "no_",
    "non_",
    "not_",
    "without_",
    "must_not_",
)

PROMPT_TEXT_ALLOWLIST_PATHS: frozenset[str] = frozenset(
    {
        "sentientos/context_hygiene/prompt_synthetic_materializer.py",
        "tests/test_phase79_synthetic_only_prompt_candidate_harness.py",
        "sentientos/context_hygiene/prompt_internal_candidate.py",
        "tests/test_phase80_internal_no_llm_prompt_candidate_contract.py",
        "sentientos/context_hygiene/prompt_provider_dry_run.py",
        "tests/test_phase84_provider_dry_run_request_envelope.py",
        "sentientos/context_hygiene/prompt_provider_simulation.py",
        "tests/test_phase86_provider_simulation_result_envelope.py",
    }
)

PROMPT_TEXT_ALLOWLIST_NAMES: frozenset[str] = frozenset(
    {
        "synthetic_prompt_text",
        "synthetic_prompt_candidate",
        "SyntheticPromptCandidate",
        "internal_candidate_text",
        "internal_prompt_candidate",
        "InternalPromptCandidate",
        "dry_run_prompt_text",
        "simulated_result_stub",
        "dry_run_prompt_text_digest",
        "dry_run_prompt_text_length",
    }
)


METADATA_ONLY_FIELD_ALLOWLIST_NAMES: frozenset[str] = frozenset(
    {
        "provider_client_allowed",
        "provider_client_forbidden",
        "endpoint_allowed",
        "endpoint_used",
        "provider_client_used",
        "NULL_TRANSPORT_ENDPOINT_DETECTED",
        "NULL_TRANSPORT_CLIENT_DETECTED",
        "raw_payload_marker_detected",
        "provider_model_params_detected",
        "endpoint_adapters_registered",
        "endpoint_transport_forbidden",
        "provider_client_absent",
        "client_detected",
        "TRANSPORT_SELECTION_ENDPOINT_DETECTED",
        "TRANSPORT_SELECTION_CLIENT_DETECTED",
        "credentials_capable",
        "endpoint_capable",
        "provider_client_capable",
        "socket_capable",
        "http_capable",
        "provider_sdk_capable",
        "network_egress_capable",
        "provider_send_capable",
        "semantic_generation_capable",
        "memory_access_capable",
        "retention_capable",
        "action_execution_capable",
        "routing_capable",
        "tool_calling_capable",
        "streaming_capable",
        "no_endpoint",
        "no_provider_client",
        "no_http",
        "no_socket",
        "no_provider_sdk",
        "no_raw_payload_marker",
        "no_runtime_handle_marker",
        "no_provider_model_params",
        "raw_payload_marker_detected",
        "runtime_handle_marker_detected",
        "provider_model_params_detected",
        "endpoint_transport_registration_allowed",
        "socket_transport_registration_allowed",
        "http_transport_registration_allowed",
        "provider_sdk_registration_allowed",
        "credentialed_transport_registration_allowed",
        "network_transport_registration_allowed",
        "semantic_generation_transport_registration_allowed",
        "TRANSPORT_CAPABILITY_ENDPOINT_DETECTED",
        "TRANSPORT_CAPABILITY_CLIENT_DETECTED",
        "TRANSPORT_REGISTRATION_ENDPOINT_DETECTED",
        "TRANSPORT_REGISTRATION_CLIENT_DETECTED",
        "TRANSPORT_CAPABILITY_ENDPOINT",
        "TRANSPORT_CAPABILITY_PROVIDER_CLIENT",
        "_ENDPOINT_CAPABILITIES",
        "_CLIENT_CAPABILITIES",
        "endpoint_detected",
        "client_detected",
        "credentials_detected",
        "network_detected",

        "endpoint_material_present",
        "endpoint_material_allowed",
        "requested_endpoint_material",
        "provider_client_material_present",
        "provider_client_material_allowed",
        "requested_provider_client_material",
        "secret_values_present",
        "secret_references_present",
        "secret_material_allowed",
        "secret_reference_allowed",
        "secret_resolution_allowed",
        "env_access_allowed",
        "file_access_allowed",
        "vault_access_allowed",
        "keychain_access_allowed",
        "cloud_secret_access_allowed",
        "network_access_allowed",
        "provider_send_allowed",
        "socket_allowed",
        "http_allowed",
        "provider_sdk_allowed",
        "semantic_generation_allowed",
        "credential_runtime_authority",
        "linked_capability_manifest_id",
        "linked_capability_digest",
        "capability_manifest_id",
        "capability_digest",
        "registration_preflight_id",
        "registration_preflight_digest",

        "CREDENTIAL_CUSTODY_ENDPOINT_DETECTED",
        "CREDENTIAL_CUSTODY_CLIENT_DETECTED",
        "CREDENTIAL_PREFLIGHT_ENDPOINT_DETECTED",
        "CREDENTIAL_PREFLIGHT_CLIENT_DETECTED",
        "requested_registration",

        "endpoint_values_present",
        "endpoint_references_present",
        "endpoint_reference_allowed",
        "endpoint_resolution_allowed",
        "dns_resolution_allowed",
        "config_store_access_allowed",
        "credential_material_present",
        "credential_material_allowed",
        "endpoint_runtime_authority",
        "linked_credential_custody_manifest_id",
        "linked_credential_custody_digest",
        "credential_custody_manifest_id",
        "credential_custody_digest",
        "credential_custody_preflight_id",
        "credential_custody_preflight_digest",
        "requested_endpoint_resolution",
        "requested_dns_resolution",
        "requested_env_access",
        "requested_file_access",
        "requested_config_store_access",
        "requested_credential_material",
        "ENDPOINT_CUSTODY_ENDPOINT_REFERENCE_DETECTED",
        "ENDPOINT_CUSTODY_DNS_RESOLUTION_DETECTED",
        "ENDPOINT_CUSTODY_CLIENT_DETECTED",
        "ENDPOINT_PREFLIGHT_FORBIDDEN_ENDPOINT_DETECTED",
        "ENDPOINT_PREFLIGHT_DNS_RESOLUTION_DETECTED",
        "ENDPOINT_PREFLIGHT_CLIENT_DETECTED",

        "ENDPOINT_CUSTODY_NO_ENDPOINTS",
        "ENDPOINT_CUSTODY_ENV_ACCESS_DETECTED",
        "ENDPOINT_CUSTODY_FILE_ACCESS_DETECTED",
        "ENDPOINT_CUSTODY_CONFIG_STORE_ACCESS_DETECTED",
        "ENDPOINT_CUSTODY_CREDENTIALS_DETECTED",
        "ENDPOINT_CUSTODY_NETWORK_DETECTED",
        "ENDPOINT_CUSTODY_INCOMPLETE",
        "ENDPOINT_CUSTODY_INVALID",
        "ENDPOINT_CUSTODY_RUNTIME_AUTHORITY_DETECTED",
        "ENDPOINT_PREFLIGHT_DENIED",
        "ENDPOINT_PREFLIGHT_NO_ENDPOINTS_ALLOWED",
        "ENDPOINT_PREFLIGHT_ENV_ACCESS_DETECTED",
        "ENDPOINT_PREFLIGHT_FILE_ACCESS_DETECTED",
        "ENDPOINT_PREFLIGHT_CONFIG_STORE_ACCESS_DETECTED",
        "ENDPOINT_PREFLIGHT_CREDENTIALS_DETECTED",
        "ENDPOINT_PREFLIGHT_NETWORK_DETECTED",
        "ENDPOINT_PREFLIGHT_INCOMPLETE_EVIDENCE",
        "ENDPOINT_PREFLIGHT_INVALID_INPUT",
        "ENDPOINT_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED",
        "ENDPOINT_CUSTODY_NONE",
        "ENDPOINT_CUSTODY_NO_ENDPOINT_PLACEHOLDER",
        "ENDPOINT_CUSTODY_FUTURE_ENDPOINT_CONTRACT_PLACEHOLDER",
        "endpoint_manifest_id",
        "endpoint_digest",
        "endpoint_status",
        "endpoint_custody_kind",
        "declared_endpoint_properties",
        "endpoint_gaps",
        "endpoint_preflight_id",
        "endpoint_preflight_status",
        "endpoint_preflight_digest",
        "provider_endpoint_custody_manifest_only",
        "provider_endpoint_custody_preflight_only",
        "requested_endpoint_custody_kind",
        "_ENDPOINT_PATTERNS",
        "invocation_allowed",
        "provider_send_allowed",
        "credentials_allowed",
        "endpoints_allowed",
        "clients_allowed",
        "network_allowed",
        "socket_allowed",
        "http_allowed",
        "dns_allowed",
        "credential_use_allowed",
        "endpoint_use_allowed",
        "client_use_allowed",
        "credential_use_forbidden",
        "endpoint_use_forbidden",
        "provider_client_use_forbidden",
        "provider_invocation_forbidden",
        "provider_invocation_readiness_manifest_only",
        "provider_invocation_readiness_preflight_only",
        "provider_sdk_allowed",
        "provider_sdk_forbidden",
        "requested_invocation",
        "requested_provider_send",
        "requested_network",
        "requested_credentials",
        "requested_endpoints",
        "requested_clients",
        "requested_provider_sdk",
        "requested_dns",
        "requested_http",
        "requested_socket",
        "requested_semantic_generation",
        "does_not_import_provider_sdks",
        "does_not_create_clients",
        "does_not_create_sessions",
        "does_not_create_transports",
        "does_not_open_streams",
        "does_not_resolve_dns",
        "does_not_read_environment",
        "does_not_read_files",
        "does_not_access_config_stores",
        "does_not_access_vaults",
        "does_not_access_keychains",
        "does_not_access_cloud_secrets",
        "does_not_make_network_calls",
        "does_not_send_to_provider",
        "does_not_open_sockets",
        "does_not_make_http_requests",
        "does_not_retrieve_memory",
        "does_not_write_memory",
        "does_not_trigger_feedback",
        "does_not_commit_retention",
        "does_not_execute_or_route_work",
        "does_not_admit_work",
        "capability_manifest_id",
        "capability_digest",
        "credential_custody_manifest_id",
        "credential_custody_digest",
        "credential_custody_preflight_id",
        "credential_custody_preflight_digest",
        "endpoint_custody_manifest_id",
        "endpoint_custody_digest",
        "endpoint_custody_preflight_id",
        "endpoint_custody_preflight_digest",
        "client_custody_manifest_id",
        "client_custody_digest",
        "client_custody_preflight_id",
        "client_custody_preflight_digest",
        "null_transport_id",
        "null_transport_digest",
        "readiness_digest",
        "invocation_readiness_id",
        "invocation_preflight_id",
        "invocation_preflight_digest",
    }
)

MODULE_SPECIFIC_METADATA_FIELD_ALLOWLIST: Mapping[str, frozenset[str]] = {
    "sentientos/context_hygiene/prompt_external_security_review.py": frozenset(
        {
            "ExternalSecurityReviewPacket",
            "ExternalSecurityReviewPacketStatus",
            "ExternalSecurityReviewScope",
            "ExternalSecurityReviewFindingSummary",
            "ExternalSecurityReviewConstraintSummary",
            "ExternalSecurityReviewGapSummary",
            "ExternalSecurityReviewEvidenceLink",
            "ExternalSecurityReviewRedactionSummary",
            "ExternalSecurityReviewAuditChain",
            "EXTERNAL_SECURITY_REVIEW_PACKET_READY",
            "EXTERNAL_SECURITY_REVIEW_PACKET_READY_WITH_CONDITIONS",
            "EXTERNAL_SECURITY_REVIEW_PACKET_BLOCKED",
            "EXTERNAL_SECURITY_REVIEW_PACKET_INVALID_INPUT",
            "EXTERNAL_SECURITY_REVIEW_PACKET_MISSING_DENIAL_REVIEW",
            "EXTERNAL_SECURITY_REVIEW_PACKET_DENIAL_NOT_AFFIRMED",
            "EXTERNAL_SECURITY_REVIEW_PACKET_SENSITIVE_MATERIAL_DETECTED",
            "EXTERNAL_SECURITY_REVIEW_PACKET_RUNTIME_AUTHORITY_DETECTED",
            "EXTERNAL_SECURITY_REVIEW_PACKET_INVOCATION_OVERRIDE_DETECTED",
            "EXTERNAL_SECURITY_REVIEW_METADATA_PACKET",
            "INVOCATION_DENIAL_AUDIT_PACKET",
            "INTERNAL_SECURITY_REVIEW_PACKET",
            "EXTERNAL_USER_VISIBLE_FORBIDDEN",
            "PROVIDER_SUBMISSION_FORBIDDEN",
            "NETWORK_EGRESS_FORBIDDEN",
            "TOOL_OR_ACTION_FORBIDDEN",
            "external_review_packet_id",
            "external_review_packet_digest",
            "packet_status",
            "review_scope",
            "reviewer_packet_ref",
            "invocation_denial_review_receipt_id",
            "invocation_denial_review_status",
            "invocation_denial_review_digest",
            "evidence_links",
            "artifact_kind",
            "artifact_id",
            "artifact_status",
            "artifact_digest",
            "audit_chain",
            "digest_chain_complete",
            "finding_summaries",
            "constraint_summaries",
            "gap_summaries",
            "redaction_summary",
            "prompt_text_removed",
            "raw_payloads_removed",
            "secrets_removed",
            "endpoints_removed",
            "clients_removed",
            "network_handles_removed",
            "runtime_handles_removed",
            "provider_params_removed",
            "tool_schemas_removed",
            "hidden_chain_of_thought_removed",
            "sensitive_material_included",
            "prompt_text_included",
            "raw_payloads_included",
            "secrets_included",
            "secret_references_included",
            "endpoints_included",
            "endpoint_references_included",
            "clients_included",
            "client_references_included",
            "network_handles_included",
            "runtime_handles_included",
            "provider_params_included",
            "tool_schemas_included",
            "hidden_chain_of_thought_included",
            "no_raw_payloads",
            "no_secret_material",
            "no_endpoint_material",
            "no_client_material",
            "no_network_handles",
            "no_runtime_handles",
            "no_provider_params",
            "no_tool_schemas",
            "no_hidden_chain_of_thought",
            "network_allowed",
            "external_security_review_packet_only",
            "invocation_denial_preserved",
            "actual_provider_invocation_forbidden",
            "live_provider_transport_forbidden",
            "live_prompt_assembly_forbidden",
            "live_model_call_forbidden",
            "endpoint_custody_manifest_digest",
            "endpoint_custody_manifest_status",
            "client_custody_manifest_digest",
            "client_custody_manifest_status",
            "prompt_text",
            "endpoints",
            "clients",
            "provider_params",
            "endpoint_data",
            "client_data",
            "client_digest",
        }
    ),

    "sentientos/context_hygiene/prompt_external_audit_export.py": frozenset(
        {
            "ExternalAuditExportReceipt",
            "ExternalAuditExportStatus",
            "ExternalAuditExportScope",
            "ExternalAuditExportDecision",
            "ExternalAuditExportFinding",
            "ExternalAuditExportConstraint",
            "ExternalAuditExportRedactionSummary",
            "ExternalAuditExportEvidenceSummary",
            "ExternalAuditExportExpiration",
            "EXTERNAL_AUDIT_EXPORT_READY",
            "EXTERNAL_AUDIT_EXPORT_READY_WITH_CONDITIONS",
            "EXTERNAL_AUDIT_EXPORT_REJECTED",
            "EXTERNAL_AUDIT_EXPORT_EXPIRED",
            "EXTERNAL_AUDIT_EXPORT_INVALID",
            "EXTERNAL_AUDIT_EXPORT_PACKET_MISSING",
            "EXTERNAL_AUDIT_EXPORT_PACKET_NOT_READY",
            "EXTERNAL_AUDIT_EXPORT_SENSITIVE_MATERIAL_DETECTED",
            "EXTERNAL_AUDIT_EXPORT_RUNTIME_AUTHORITY_DETECTED",
            "EXTERNAL_AUDIT_EXPORT_INVOCATION_OVERRIDE_DETECTED",
            "EXTERNAL_AUDIT_EXPORT_IO_ATTEMPT_DETECTED",
            "EXTERNAL_AUDIT_METADATA_EXPORT_RECEIPT",
            "INTERNAL_AUDIT_METADATA_EXPORT_RECEIPT",
            "SECURITY_REVIEW_EXPORT_RECEIPT",
            "INVOCATION_DENIAL_AUDIT_EXPORT_RECEIPT",
            "LIVE_EXTERNAL_DELIVERY_FORBIDDEN",
            "PROVIDER_SUBMISSION_FORBIDDEN",
            "NETWORK_UPLOAD_FORBIDDEN",
            "EMAIL_DELIVERY_FORBIDDEN",
            "WEBHOOK_DELIVERY_FORBIDDEN",
            "FILE_WRITE_FORBIDDEN",
            "OBJECT_STORAGE_FORBIDDEN",
            "TOOL_OR_ACTION_FORBIDDEN",
            "export_receipt_id",
            "export_status",
            "export_scope",
            "exporter_ref",
            "export_label",
            "external_review_packet_id",
            "external_review_packet_status",
            "external_review_packet_digest",
            "expected_packet_digest",
            "packet_digest_match",
            "evidence_summary",
            "redaction_summary",
            "evidence_link_count",
            "included_evidence_link_count",
            "redacted_evidence_link_count",
            "finding_summary_count",
            "constraint_summary_count",
            "gap_summary_count",
            "digest_chain_complete",
            "packet_ready_for_review",
            "prompt_text_removed",
            "raw_payloads_removed",
            "secrets_removed",
            "endpoints_removed",
            "clients_removed",
            "network_handles_removed",
            "runtime_handles_removed",
            "provider_params_removed",
            "tool_schemas_removed",
            "hidden_chain_of_thought_removed",
            "required_redaction_rejected",
            "exported_body_included",
            "export_io_performed",
            "external_delivery_performed",
            "network_upload_performed",
            "email_delivery_performed",
            "webhook_delivery_performed",
            "file_write_performed",
            "object_storage_write_performed",
            "packet_body_included",
            "artifact_bodies_included",
            "prompt_text_included",
            "raw_payloads_included",
            "secrets_included",
            "secret_references_included",
            "endpoints_included",
            "endpoint_references_included",
            "clients_included",
            "client_references_included",
            "network_handles_included",
            "runtime_handles_included",
            "provider_params_included",
            "tool_schemas_included",
            "hidden_chain_of_thought_included",
            "no_raw_payloads",
            "no_secret_material",
            "no_endpoint_material",
            "no_client_material",
            "no_network_handles",
            "no_runtime_handles",
            "no_provider_params",
            "no_tool_schemas",
            "no_hidden_chain_of_thought",
            "external_audit_export_receipt_only",
            "export_io_not_performed",
            "external_delivery_not_performed",
            "invocation_denial_preserved",
            "actual_provider_invocation_forbidden",
            "live_provider_transport_forbidden",
            "live_prompt_assembly_forbidden",
            "live_model_call_forbidden",
            "network_allowed",
            "client_use_allowed",
            "endpoint_use_allowed",
            "credential_use_allowed",
            "provider_send_allowed",
            "provider_sdk_allowed",
            "accepted_redaction_codes",
            "rejected_redaction_codes",
            "accepted_evidence_codes",
            "rejected_evidence_codes",
            "approved_constraint_codes",
            "rejected_constraint_codes",
            "export_receipt_digest",
            "redaction_removed_total",
            "external_review_packet",
        }
    ),

    "sentientos/context_hygiene/prompt_provider_invocation_denial_closure.py": frozenset(
        {
            "ProviderInvocationDenialClosureManifest",
            "ProviderInvocationDenialClosureStatus",
            "ProviderInvocationReleaseBlockerStatus",
            "ProviderInvocationDenialClosureScope",
            "ProviderInvocationDenialClosureFinding",
            "ProviderInvocationDenialClosureConstraint",
            "ProviderInvocationDenialClosureEvidenceSummary",
            "ProviderInvocationDenialClosureGuardrailSummary",
            "ProviderInvocationDenialClosureRequirement",
            "endpoint_custody_no_endpoint",
            "client_custody_no_client",
            "prompt_text_included",
            "hidden_chain_of_thought_included",
            "raw_payloads_included",
            "endpoints_included",
            "endpoint_references_included",
            "clients_included",
            "client_references_included",
            "provider_params_included",
            "model_params_included",
            "provider_invocation_release_blocked",
            "provider_invocation_release_blocker",
            "provider_invocation_denial_closure_manifest_only",
            "phase100_closure_manifest",
            "closure_not_release_approval",
            "actual_provider_invocation_forbidden",
            "no_prompt_text",
            "no_hidden_chain_of_thought",
            "no_raw_payloads",
            "no_secret_material",
            "no_endpoint_material",
            "no_client_material",
            "no_provider_params",
            "no_model_params",
            "endpoint_data",
            "client_data",
            "prompt_text",
            "endpoints",
            "clients",
            "release_blocker_codes",
            "future_clearance_requirement_codes",
            "external_audit_export_receipt_id",
            "external_security_review_packet_id",
            "invocation_denial_review_receipt_id",
            "invocation_readiness_id",
            "registry_id",
            "transport_capability_manifest_id",
            "credential_custody_manifest_id",
            "endpoint_custody_manifest_id",
            "client_custody_manifest_id",
            "external_audit_export_digest",
            "external_security_review_packet_digest",
            "invocation_denial_review_digest",
            "invocation_readiness_digest",
            "registry_digest",
            "transport_capability_digest",
            "credential_custody_digest",
            "endpoint_custody_digest",
            "client_custody_digest",
        }
    ),

    "sentientos/context_hygiene/prompt_provider_invocation_denial_attestation.py": frozenset(
        {
            "ProviderInvocationDenialAttestation",
            "ProviderInvocationDenialAttestationStatus",
            "ProviderInvocationDenialAttestationScope",
            "ProviderInvocationDenialAttestationDecision",
            "ProviderInvocationDenialAttestationFinding",
            "ProviderInvocationDenialAttestationConstraint",
            "ProviderInvocationDenialAttestationEvidenceSummary",
            "ProviderInvocationDenialAttestationExpiration",
            "PROVIDER_INVOCATION_DENIAL_ATTESTED",
            "PROVIDER_INVOCATION_DENIAL_ATTESTED_WITH_CONDITIONS",
            "PROVIDER_INVOCATION_DENIAL_REJECTED",
            "PROVIDER_INVOCATION_DENIAL_EXPIRED",
            "PROVIDER_INVOCATION_DENIAL_INVALID",
            "PROVIDER_INVOCATION_DENIAL_MISSING_EVIDENCE",
            "PROVIDER_INVOCATION_DENIAL_EXPORT_NOT_READY",
            "PROVIDER_INVOCATION_DENIAL_SENSITIVE_MATERIAL_DETECTED",
            "PROVIDER_INVOCATION_DENIAL_RUNTIME_AUTHORITY_DETECTED",
            "PROVIDER_INVOCATION_DENIAL_OVERRIDE_DETECTED",
            "PROVIDER_INVOCATION_DENIAL_ATTESTATION",
            "EXTERNAL_AUDIT_DENIAL_ATTESTATION",
            "INTERNAL_SECURITY_DENIAL_ATTESTATION",
            "INVOCATION_DENIAL_CHAIN_ATTESTATION",
            "PROVIDER_INVOCATION_APPROVAL_FORBIDDEN",
            "PROVIDER_SUBMISSION_FORBIDDEN",
            "NETWORK_EGRESS_FORBIDDEN",
            "EXPORT_DELIVERY_FORBIDDEN",
            "TOOL_OR_ACTION_FORBIDDEN",
            "EXTERNAL_USER_VISIBLE_FORBIDDEN",
            "attestation_id",
            "attestation_status",
            "attestation_scope",
            "attestor_ref",
            "attestation_label",
            "formal_denial_statement_code",
            "expected_export_receipt_digest",
            "export_receipt_digest_match",
            "export_receipt_id",
            "export_receipt_status",
            "export_receipt_digest",
            "external_review_packet_id",
            "external_review_packet_digest",
            "invocation_denial_review_receipt_id",
            "invocation_denial_review_digest",
            "readiness_id",
            "readiness_digest",
            "evidence_summary",
            "linked_artifact_count",
            "export_receipt_ready",
            "external_review_packet_ready",
            "denial_review_affirmed",
            "readiness_metadata_only",
            "digest_chain_complete",
            "constraint_count",
            "warning_count",
            "finding_count",
            "approved_constraint_codes",
            "rejected_constraint_codes",
            "accepted_evidence_codes",
            "rejected_evidence_codes",
            "accepted_denial_codes",
            "rejected_denial_codes",
            "export_io_performed",
            "external_delivery_performed",
            "network_upload_performed",
            "email_delivery_performed",
            "webhook_delivery_performed",
            "file_write_performed",
            "object_storage_write_performed",
            "prompt_text_included",
            "raw_payloads_included",
            "secrets_included",
            "secret_references_included",
            "endpoints_included",
            "endpoint_references_included",
            "clients_included",
            "client_references_included",
            "network_handles_included",
            "runtime_handles_included",
            "provider_params_included",
            "model_params_included",
            "tool_schemas_included",
            "hidden_chain_of_thought_included",
            "no_raw_payloads",
            "no_secret_material",
            "no_endpoint_material",
            "no_client_material",
            "no_network_handles",
            "no_runtime_handles",
            "no_provider_params",
            "no_model_params",
            "no_tool_schemas",
            "no_hidden_chain_of_thought",
            "provider_invocation_denial_attestation_only",
            "formal_denial_attestation",
            "export_io_not_performed",
            "external_delivery_not_performed",
            "invocation_denial_preserved",
            "actual_provider_invocation_forbidden",
            "live_provider_transport_forbidden",
            "live_prompt_assembly_forbidden",
            "live_model_call_forbidden",
            "network_allowed",
            "client_use_allowed",
            "endpoint_use_allowed",
            "credential_use_allowed",
            "provider_send_allowed",
            "provider_sdk_allowed",
            "model_params",
            "attestation_digest",
            "external_audit_export_receipt",
        }
    ),
    "sentientos/context_hygiene/prompt_provider_invocation_readiness.py": frozenset(
        {
            "INVOCATION_READINESS_ENDPOINT_DETECTED",
            "INVOCATION_READINESS_CLIENT_DETECTED",
            "INVOCATION_PREFLIGHT_ENDPOINT_DETECTED",
            "INVOCATION_PREFLIGHT_CLIENT_DETECTED",
            "endpoint",
            "endpoint_preflight",
            "endpoint_id",
            "endpoint_digest",
            "endpoint_clean",
            "endpoint_preflight_clean",
            "client",
            "client_preflight",
            "client_id",
            "client_digest",
            "client_preflight_id",
            "client_preflight_digest",
            "client_clean",
            "client_preflight_clean",
            "endpoint_custody_manifest",
            "endpoint_custody_preflight",
            "client_custody_manifest",
            "client_custody_preflight",
        }
    )
}

SHADOW_ALLOWLIST_NAMES: frozenset[str] = frozenset(
    {
        "preview_context_hygiene_adapter_payload_for_prompt_assembly",
        "build_context_hygiene_shadow_prompt_adapter_preview",
        "build_context_hygiene_shadow_prompt_blueprint",
        "build_shadow_prompt_blueprint_from_adapter_payload",
        "PromptAssemblerShadowAdapterPreview",
        "PromptAssemblerShadowBlueprint",
        "PromptMaterializationAuditReceipt",
        "audit_receipt_allows_shadow_materializer",
        "PromptMaterializationPolicyDecision",
        "PromptMaterializationPolicyInput",
        "PromptMaterializationPolicyStatus",
        "PromptMaterializationPolicyRing",
        "policy_decision_allows_shadow_only",
        "policy_decision_allows_synthetic_materializer",
        "policy_decision_allows_internal_candidate_no_llm",
    }
)

PROMPT_ASSEMBLER_ALLOWED_CONTEXT_HYGIENE_IMPORTS: frozenset[str] = frozenset(
    {
        "sentientos.context_hygiene.prompt_adapter_contract",
        "sentientos.context_hygiene.prompt_assembler_compliance",
    }
)
PROMPT_ASSEMBLER_FORBIDDEN_CONTEXT_HYGIENE_IMPORTS: tuple[str, ...] = (
    "sentientos.context_hygiene.selector",
    "sentientos.context_hygiene.prompt_preflight",
    "sentientos.context_hygiene.prompt_handoff_manifest",
    "sentientos.context_hygiene.prompt_dry_run_envelope",
    "sentientos.context_hygiene.prompt_constraint_verifier",
    "sentientos.context_hygiene.prompt_materialization_audit",
    "sentientos.context_hygiene.context_packet",
    "sentientos.context_hygiene.safety_metadata",
    "sentientos.context_hygiene.source_kind_contracts",
)

FORBIDDEN_IMPORT_PATTERNS: tuple[str, ...] = (
    "memory_manager",
    "openai",
    "requests",
    "httpx",
    "browser",
    "pyautogui",
    "mouse",
    "keyboard",
    "task_admission",
    "task_executor",
    "orchestrator",
    "orchestration",
    "router",
    "routing",
    "executor",
    "execution",
    "action_router",
    "action_executor",
    "action_dispatch",
    "retention",
    "feedback",
    "screen_awareness",
    "vision_tracker",
    "mic_bridge",
    "multimodal_tracker",
    "embodiment_runtime",
    "raw_screen",
    "raw_audio",
    "raw_vision",
    "raw_multimodal",
)

FORBIDDEN_CALL_NAMES: tuple[str, ...] = (
    "assemble_prompt",
    "create",
    "chat.completions.create",
    "responses.create",
    "complete",
    "completion",
    "retrieve_memory",
    "retrieve_memories",
    "search_memory",
    "query_memory",
    "write_memory",
    "save_memory",
    "append_memory",
    "commit_retention",
    "commit",
    "trigger_feedback",
    "execute_action",
    "dispatch_action",
    "route_task",
    "route_work",
    "admit_task",
    "admit_work",
    "execute_task",
    "execute_work",
    "orchestrate",
    "browser",
    "click",
    "typewrite",
    "press",
)

FORBIDDEN_PROVIDER_CALL_OWNERS: tuple[str, ...] = ("openai", "client", "provider", "llm", "model")
FORBIDDEN_CONTEXT_PAYLOAD_TYPES: tuple[str, ...] = (
    "ContextPacket",
    "PromptAssemblyAdapterPayload",
    "PromptAssemblerShadowBlueprint",
    "PromptMaterializationAuditReceipt",
)
MATERIALIZER_FUNCTION_PREFIXES: tuple[str, ...] = ("materialize", "render", "assemble")


class ContextHygienePromptBoundaryStatus(str, Enum):
    BOUNDARY_CLEAN = "boundary_clean"
    BOUNDARY_CLEAN_WITH_WARNINGS = "boundary_clean_with_warnings"
    BOUNDARY_FAILED = "boundary_failed"
    BOUNDARY_SCAN_ERROR = "boundary_scan_error"


@dataclass(frozen=True, order=True)
class ContextHygienePromptBoundaryFinding:
    path: str
    line: int
    column: int
    code: str
    detail: str
    severity: str = "blocker"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ContextHygienePromptBoundaryReport:
    status: ContextHygienePromptBoundaryStatus
    scanned_paths: tuple[str, ...]
    findings: tuple[ContextHygienePromptBoundaryFinding, ...] = field(default_factory=tuple)
    warnings: tuple[ContextHygienePromptBoundaryFinding, ...] = field(default_factory=tuple)
    shadow_allowlist: tuple[str, ...] = field(default_factory=lambda: tuple(sorted(SHADOW_ALLOWLIST_NAMES)))

    @property
    def ok(self) -> bool:
        return self.status in {
            ContextHygienePromptBoundaryStatus.BOUNDARY_CLEAN,
            ContextHygienePromptBoundaryStatus.BOUNDARY_CLEAN_WITH_WARNINGS,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "scanned_paths": list(self.scanned_paths),
            "findings": [finding.to_dict() for finding in self.findings],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "shadow_allowlist": list(self.shadow_allowlist),
        }


def _display_path(path: Path, repo_root: Path = REPO_ROOT) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _module_name_from_import(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        return tuple(module + (f".{alias.name}" if module else alias.name) for alias in node.names)
    return ()


def _name_is_negative_marker(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered.startswith(NEGATIVE_MARKER_PREFIXES)
        or lowered.startswith(("forbidden_", "_forbidden_"))
        or lowered.endswith("_forbidden")
        or "_forbidden_" in lowered
        or "_not_" in lowered
        or "does_not" in lowered
        or "must_not" in lowered
        or "without" in lowered
        or lowered.endswith("_absent")
        or "_absent" in lowered
    )


def _identifier_contains_forbidden_field(name: str, path: Path | None = None, repo_root: Path = REPO_ROOT) -> str | None:
    lowered = name.lower()
    rel = _display_path(path, repo_root) if path is not None else ""
    if rel in PROMPT_TEXT_ALLOWLIST_PATHS and name in PROMPT_TEXT_ALLOWLIST_NAMES:
        return None
    if rel == "sentientos/context_hygiene/prompt_provider_client_custody.py" and any(
        token in lowered
        for token in (
            "client",
            "session",
            "endpoint",
            "credential",
            "sdk",
            "transport",
            "stream",
            "request_builder",
            "retry_executor",
            "http",
            "socket",
        )
    ):
        return None
    rel = _display_path(path, repo_root)
    if name in MODULE_SPECIFIC_METADATA_FIELD_ALLOWLIST.get(rel, frozenset()):
        return None
    if name in METADATA_ONLY_FIELD_ALLOWLIST_NAMES or name in SHADOW_ALLOWLIST_NAMES or _name_is_negative_marker(name):
        return None
    for pattern in FORBIDDEN_FIELD_PATTERNS:
        if pattern == "auth" and ("authority" in lowered or "authoritative" in lowered):
            continue
        if pattern in lowered:
            return pattern
    return None


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    if isinstance(node, ast.Subscript):
        return _call_name(node.value)
    return ""


def _target_names(node: ast.AST) -> Iterable[tuple[str, int, int]]:
    if isinstance(node, ast.Name):
        yield node.id, node.lineno, node.col_offset
    elif isinstance(node, ast.Attribute):
        yield node.attr, node.lineno, node.col_offset
    elif isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            yield from _target_names(elt)


def _string_dict_keys(node: ast.AST) -> Iterable[tuple[str, int, int]]:
    if isinstance(node, ast.Dict):
        for key in node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                yield key.value, key.lineno, key.col_offset


def _annotation_mentions_context_payload(node: ast.AST | None) -> bool:
    if node is None:
        return False
    return any(payload_type in ast.unparse(node) for payload_type in FORBIDDEN_CONTEXT_PAYLOAD_TYPES)


def _is_prompt_assembler(path: Path) -> bool:
    return path.name == "prompt_assembler.py"


def _is_context_hygiene_module(path: Path) -> bool:
    parts = path.as_posix().split("/")
    return "sentientos" in parts and "context_hygiene" in parts


def _finding(path: Path, line: int, col: int, code: str, detail: str, repo_root: Path) -> ContextHygienePromptBoundaryFinding:
    return ContextHygienePromptBoundaryFinding(
        path=_display_path(path, repo_root),
        line=line,
        column=col,
        code=code,
        detail=detail,
    )


def scan_file_for_prompt_boundary_violations(path: str | Path, *, repo_root: str | Path = REPO_ROOT) -> tuple[ContextHygienePromptBoundaryFinding, ...]:
    """Scan one Python source file for prompt-boundary violations.

    The scan is purely textual/AST-based; the target module is never imported.
    """
    root = Path(repo_root)
    source_path = Path(path)
    if not source_path.is_absolute():
        source_path = root / source_path
    findings: list[ContextHygienePromptBoundaryFinding] = []
    try:
        text = source_path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(source_path))
    except Exception as exc:  # pragma: no cover - exact parse errors vary by Python.
        return (_finding(source_path, 1, 0, "boundary_scan_error", f"could not parse source: {exc}", root),)

    prompt_assembler = _is_prompt_assembler(source_path)
    context_hygiene = _is_context_hygiene_module(source_path) or not prompt_assembler

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for module_name in _module_name_from_import(node):
                lowered = module_name.lower()
                if prompt_assembler and module_name.startswith("sentientos.context_hygiene"):
                    base = module_name.rsplit(".", 1)[0]
                    if any(module_name.startswith(forbidden) for forbidden in PROMPT_ASSEMBLER_FORBIDDEN_CONTEXT_HYGIENE_IMPORTS):
                        findings.append(_finding(source_path, node.lineno, node.col_offset, "prompt_assembler_context_hygiene_bypass_import", f"prompt_assembler.py must not directly import {module_name}; use the Phase 70/71 shadow-only boundary", root))
                    elif base not in PROMPT_ASSEMBLER_ALLOWED_CONTEXT_HYGIENE_IMPORTS and module_name not in PROMPT_ASSEMBLER_ALLOWED_CONTEXT_HYGIENE_IMPORTS:
                        findings.append(_finding(source_path, node.lineno, node.col_offset, "prompt_assembler_unapproved_context_hygiene_import", f"prompt_assembler.py imports unapproved context hygiene surface {module_name}", root))
                elif context_hygiene:
                    for pattern in FORBIDDEN_IMPORT_PATTERNS:
                        if pattern in lowered:
                            findings.append(_finding(source_path, node.lineno, node.col_offset, "forbidden_runtime_import", f"prompt-boundary code must not import runtime/provider surface {module_name}", root))
                            break
                    if lowered.startswith("prompt_assembler") or lowered.startswith("sentientos.prompt_assembler"):
                        findings.append(_finding(source_path, node.lineno, node.col_offset, "forbidden_prompt_assembler_import", f"context hygiene code must not import {module_name}", root))

        if context_hygiene and isinstance(node, ast.AnnAssign):
            for name, line, col in _target_names(node.target):
                forbidden = _identifier_contains_forbidden_field(name, source_path, root)
                if forbidden:
                    findings.append(_finding(source_path, line, col, "forbidden_materialization_field", f"identifier {name!r} contains forbidden prompt/runtime field pattern {forbidden!r}", root))

        if context_hygiene and isinstance(node, (ast.Assign, ast.AugAssign, ast.NamedExpr)):
            targets: Sequence[ast.AST]
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AugAssign):
                targets = (node.target,)
            else:
                targets = (node.target,)
            for target in targets:
                for name, line, col in _target_names(target):
                    forbidden = _identifier_contains_forbidden_field(name, source_path, root)
                    if forbidden:
                        findings.append(_finding(source_path, line, col, "forbidden_materialization_assignment", f"assignment target {name!r} contains forbidden prompt/runtime field pattern {forbidden!r}", root))

        if context_hygiene and isinstance(node, ast.Dict):
            for name, line, col in _string_dict_keys(node):
                forbidden = _identifier_contains_forbidden_field(name, source_path, root)
                if forbidden:
                    findings.append(_finding(source_path, line, col, "forbidden_materialization_mapping_key", f"mapping key {name!r} contains forbidden prompt/runtime field pattern {forbidden!r}", root))

        if context_hygiene and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lowered_name = node.name.lower()
            if any(lowered_name.startswith(prefix) for prefix in MATERIALIZER_FUNCTION_PREFIXES):
                annotations = [arg.annotation for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)] + [node.returns]
                if any(_annotation_mentions_context_payload(annotation) for annotation in annotations):
                    findings.append(_finding(source_path, node.lineno, node.col_offset, "forbidden_context_payload_materializer", f"function {node.name!r} appears to materialize/render/assemble a context hygiene payload type", root))

        if context_hygiene and isinstance(node, ast.Call):
            call = _call_name(node.func)
            lowered_call = call.lower()
            if call == "assemble_prompt" or lowered_call.endswith(".assemble_prompt"):
                findings.append(_finding(source_path, node.lineno, node.col_offset, "forbidden_assemble_prompt_call", "context hygiene prompt-boundary code must not call assemble_prompt(...) directly", root))
            elif any(lowered_call == forbidden or lowered_call.endswith(f".{forbidden}") for forbidden in FORBIDDEN_CALL_NAMES):
                if lowered_call == "commit" and not any(owner in lowered_call for owner in ("retention", "memory")):
                    continue
                findings.append(_finding(source_path, node.lineno, node.col_offset, "forbidden_runtime_call", f"forbidden runtime/provider call pattern {call!r}", root))
            elif not (
                lowered_call.startswith("provider_dry_run_")
                or lowered_call.startswith("provider_network_egress_preflight_")
                or lowered_call.startswith("provider_invocation_readiness_")
                or lowered_call.startswith("provider_invocation_preflight_")
                or lowered_call.startswith("provider_invocation_denial_review_")
            ) and any(owner in lowered_call for owner in FORBIDDEN_PROVIDER_CALL_OWNERS) and any(verb in lowered_call for verb in ("create", "complete", "invoke", "generate", "send")):
                findings.append(_finding(source_path, node.lineno, node.col_offset, "forbidden_provider_call", f"forbidden LLM/provider call pattern {call!r}", root))
            elif any(term in lowered_call for term in ("retrieve_memory", "write_memory", "save_memory", "search_memory", "commit_retention", "execute_action", "route_work", "admit_work")):
                findings.append(_finding(source_path, node.lineno, node.col_offset, "forbidden_runtime_call", f"forbidden context side-effect call pattern {call!r}", root))

    return tuple(sorted(findings))


def scan_prompt_assembler_shadow_boundary(path: str | Path = "prompt_assembler.py", *, repo_root: str | Path = REPO_ROOT) -> tuple[ContextHygienePromptBoundaryFinding, ...]:
    return scan_file_for_prompt_boundary_violations(path, repo_root=repo_root)


def _resolve_scan_targets(paths: Sequence[str | Path] | None, repo_root: Path) -> tuple[Path, ...]:
    selected = paths if paths else DEFAULT_SCAN_TARGETS
    return tuple((Path(p) if Path(p).is_absolute() else repo_root / Path(p)) for p in selected)


def scan_context_hygiene_prompt_boundaries(paths: Sequence[str | Path] | None = None, *, repo_root: str | Path = REPO_ROOT) -> ContextHygienePromptBoundaryReport:
    root = Path(repo_root)
    targets = _resolve_scan_targets(paths, root)
    findings: list[ContextHygienePromptBoundaryFinding] = []
    scanned: list[str] = []
    for target in targets:
        scanned.append(_display_path(target, root))
        findings.extend(scan_file_for_prompt_boundary_violations(target, repo_root=root))
    unique_findings = tuple(sorted({finding: None for finding in findings}.keys()))
    status = (
        ContextHygienePromptBoundaryStatus.BOUNDARY_FAILED
        if unique_findings
        else ContextHygienePromptBoundaryStatus.BOUNDARY_CLEAN
    )
    return ContextHygienePromptBoundaryReport(status=status, scanned_paths=tuple(scanned), findings=unique_findings)


def summarize_context_hygiene_prompt_boundary_scan(report: ContextHygienePromptBoundaryReport) -> str:
    lines = [
        f"Context hygiene prompt boundary scan: {report.status.value}",
        f"Scanned files: {len(report.scanned_paths)}",
        f"Findings: {len(report.findings)}",
    ]
    for finding in report.findings:
        lines.append(f"- {finding.path}:{finding.line}:{finding.column} [{finding.code}] {finding.detail}")
    if not report.findings:
        lines.append("No prompt materialization, forbidden runtime import/call, or context-hygiene bypass findings detected.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify context-hygiene prompt boundary static guardrails.")
    parser.add_argument("paths", nargs="*", help="Optional Python files to scan instead of the default Phase 75 target set.")
    parser.add_argument("--json", action="store_true", help="Emit deterministic JSON report.")
    args = parser.parse_args(argv)
    report = scan_context_hygiene_prompt_boundaries(args.paths or None)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(summarize_context_hygiene_prompt_boundary_scan(report))
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover - exercised by CLI tests.
    raise SystemExit(main())
