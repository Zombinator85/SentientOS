from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import ast

import pytest

from sentientos.context_hygiene.prompt_external_audit_export import (
    ExternalAuditExportDecision,
    ExternalAuditExportScope,
    ExternalAuditExportStatus,
    build_external_audit_export_receipt,
    external_audit_export_receipt_ready_for_export_review,
)
from sentientos.context_hygiene.prompt_external_security_review import (
    ExternalSecurityReviewPacketStatus,
    build_external_security_review_packet,
    external_security_review_packet_is_metadata_only,
    external_security_review_packet_ready_for_review,
)
from sentientos.context_hygiene.prompt_provider_client_custody import build_provider_client_custody_manifest, evaluate_provider_client_custody_preflight, provider_client_custody_contains_no_clients
from sentientos.context_hygiene.prompt_provider_credential_custody import build_provider_credential_custody_manifest, evaluate_provider_credential_custody_preflight, provider_credential_custody_contains_no_secrets
from sentientos.context_hygiene.prompt_provider_endpoint_custody import build_provider_endpoint_custody_manifest, evaluate_provider_endpoint_custody_preflight, provider_endpoint_custody_contains_no_endpoints
from sentientos.context_hygiene.prompt_provider_invocation_denial_attestation import (
    ProviderInvocationDenialAttestationDecision,
    ProviderInvocationDenialAttestationScope,
    ProviderInvocationDenialAttestationStatus,
    build_provider_invocation_denial_attestation,
    compute_provider_invocation_denial_attestation_digest,
    explain_provider_invocation_denial_attestation_findings,
    provider_invocation_denial_attestation_contains_no_clients,
    provider_invocation_denial_attestation_contains_no_endpoints,
    provider_invocation_denial_attestation_contains_no_network_handles,
    provider_invocation_denial_attestation_contains_no_prompt_text,
    provider_invocation_denial_attestation_contains_no_runtime_authority,
    provider_invocation_denial_attestation_contains_no_secrets,
    provider_invocation_denial_attestation_denies_invocation,
    provider_invocation_denial_attestation_does_not_export,
    provider_invocation_denial_attestation_is_metadata_only,
    provider_invocation_denial_attestation_ready,
    summarize_provider_invocation_denial_attestation,
    validate_provider_invocation_denial_attestation,
)
from sentientos.context_hygiene.prompt_provider_invocation_denial_review import (
    ProviderInvocationDenialReviewDecision,
    ProviderInvocationDenialReviewScope,
    build_provider_invocation_denial_review_receipt,
    provider_invocation_denial_review_affirms_forbidden_invocation,
)
from sentientos.context_hygiene.prompt_provider_invocation_readiness import build_provider_invocation_readiness_manifest, evaluate_provider_invocation_readiness_preflight, provider_invocation_readiness_forbids_invocation
from sentientos.context_hygiene.prompt_provider_transport_capability import build_provider_transport_capability_manifest, evaluate_provider_transport_registration_preflight
from sentientos.context_hygiene.prompt_provider_transport_registry import build_provider_transport_registry_manifest, provider_transport_registry_is_null_only
from scripts.verify_context_hygiene_prompt_boundaries import scan_context_hygiene_prompt_boundaries

MODULE_PATH = Path("sentientos/context_hygiene/prompt_provider_invocation_denial_attestation.py")


def _chain():
    registry = build_provider_transport_registry_manifest()
    capability = build_provider_transport_capability_manifest()
    registration = evaluate_provider_transport_registration_preflight(capability, registry)
    credential = build_provider_credential_custody_manifest(linked_capability_manifest=capability)
    credential_preflight = evaluate_provider_credential_custody_preflight(credential, capability, registration)
    endpoint = build_provider_endpoint_custody_manifest(linked_capability_manifest=capability, linked_credential_custody_manifest=credential)
    endpoint_preflight = evaluate_provider_endpoint_custody_preflight(endpoint, capability, credential, credential_preflight)
    client = build_provider_client_custody_manifest(
        linked_capability_manifest=capability,
        linked_credential_custody_manifest=credential,
        linked_endpoint_custody_manifest=endpoint,
        linked_endpoint_custody_preflight=endpoint_preflight,
    )
    client_preflight = evaluate_provider_client_custody_preflight(client, capability, credential, endpoint, endpoint_preflight)
    readiness = build_provider_invocation_readiness_manifest(
        registry_manifest=registry,
        capability_manifest=capability,
        registration_preflight=registration,
        credential_custody_manifest=credential,
        credential_custody_preflight=credential_preflight,
        endpoint_custody_manifest=endpoint,
        endpoint_custody_preflight=endpoint_preflight,
        client_custody_manifest=client,
        client_custody_preflight=client_preflight,
    )
    preflight = evaluate_provider_invocation_readiness_preflight(readiness)
    denial = build_provider_invocation_denial_review_receipt(
        readiness,
        preflight,
        reviewer_ref="phase99-denial-reviewer",
        decision=ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_EXTERNAL_SECURITY_REVIEW_GATE,
        review_scope=ProviderInvocationDenialReviewScope.FUTURE_EXTERNAL_SECURITY_REVIEW_GATE,
        reviewed_at="2026-01-01T00:00:00Z",
        ttl_seconds=31536000,
        evaluated_at="2026-01-02T00:00:00Z",
    )
    return registry, capability, registration, credential, endpoint, client, readiness, preflight, denial


def _packet(**overrides):
    registry, capability, registration, credential, endpoint, client, readiness, preflight, denial = _chain()
    return build_external_security_review_packet(
        overrides.pop("denial", denial),
        readiness_manifest=overrides.pop("readiness", readiness),
        readiness_preflight=overrides.pop("preflight", preflight),
        capability_manifest=overrides.pop("capability", capability),
        credential_custody_manifest=overrides.pop("credential", credential),
        endpoint_custody_manifest=overrides.pop("endpoint", endpoint),
        client_custody_manifest=overrides.pop("client", client),
        reviewer_packet_ref=overrides.pop("reviewer_packet_ref", "phase99-review-packet"),
        **overrides,
    )


def _receipt(packet=None, **overrides):
    if packet is None:
        packet = _packet()
    return build_external_audit_export_receipt(
        packet,
        exporter_ref=overrides.pop("exporter_ref", "audit-ref"),
        decision=overrides.pop("decision", ExternalAuditExportDecision.APPROVE_METADATA_EXPORT_REVIEW),
        export_scope=overrides.pop("export_scope", ExternalAuditExportScope.EXTERNAL_AUDIT_METADATA_EXPORT_RECEIPT),
        approved_constraint_codes=overrides.pop("approved_constraint_codes", ("metadata_only", "export_io_not_performed", "provider_invocation_forbidden")),
        accepted_redaction_codes=overrides.pop("accepted_redaction_codes", ("prompt_text_removed", "secrets_removed")),
        accepted_evidence_codes=overrides.pop("accepted_evidence_codes", ("digest_only_evidence_links",)),
        **overrides,
    )


def _attestation(receipt=None, **overrides):
    if receipt is None:
        receipt = _receipt()
    return build_provider_invocation_denial_attestation(
        receipt,
        attestor_ref=overrides.pop("attestor_ref", "formal-attestor-ref"),
        decision=overrides.pop("decision", ProviderInvocationDenialAttestationDecision.ATTEST_PROVIDER_INVOCATION_FORBIDDEN),
        attestation_scope=overrides.pop("attestation_scope", ProviderInvocationDenialAttestationScope.PROVIDER_INVOCATION_DENIAL_ATTESTATION),
        approved_constraint_codes=overrides.pop("approved_constraint_codes", ("metadata_only", "export_io_not_performed", "provider_invocation_forbidden")),
        accepted_evidence_codes=overrides.pop("accepted_evidence_codes", ("phase95", "phase96", "phase97", "phase98")),
        accepted_denial_codes=overrides.pop("accepted_denial_codes", ("provider_invocation_forbidden",)),
        **overrides,
    )


def _codes(attestation):
    return set(attestation.findings) | set(explain_provider_invocation_denial_attestation_findings(attestation))


def test_attestation_can_be_built_from_clean_phase98_export_receipt():
    attestation = _attestation()
    assert attestation.attestation_status == ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_ATTESTED
    assert provider_invocation_denial_attestation_ready(attestation)
    assert not validate_provider_invocation_denial_attestation(attestation)
    assert summarize_provider_invocation_denial_attestation(attestation)["formal_denial_statement_code"] == "provider_invocation_remains_forbidden_metadata_only_no_export"


@pytest.mark.parametrize(
    "scope",
    [
        ProviderInvocationDenialAttestationScope.PROVIDER_INVOCATION_DENIAL_ATTESTATION,
        ProviderInvocationDenialAttestationScope.EXTERNAL_AUDIT_DENIAL_ATTESTATION,
        ProviderInvocationDenialAttestationScope.INTERNAL_SECURITY_DENIAL_ATTESTATION,
        ProviderInvocationDenialAttestationScope.INVOCATION_DENIAL_CHAIN_ATTESTATION,
    ],
)
def test_allowed_attestation_scopes_yield_attested(scope):
    attestation = _attestation(attestation_scope=scope)
    assert attestation.attestation_status == ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_ATTESTED
    assert provider_invocation_denial_attestation_ready(attestation)


@pytest.mark.parametrize(
    "decision, expected_status",
    [
        (ProviderInvocationDenialAttestationDecision.ATTEST_METADATA_ONLY_NOT_INVOCABLE, ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_ATTESTED),
        (ProviderInvocationDenialAttestationDecision.ATTEST_WITH_CONDITIONS, ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_ATTESTED_WITH_CONDITIONS),
        (ProviderInvocationDenialAttestationDecision.REJECT_ATTESTATION, ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_REJECTED),
        (ProviderInvocationDenialAttestationDecision.REQUEST_MORE_REDACTION, ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_REJECTED),
        (ProviderInvocationDenialAttestationDecision.REQUEST_MORE_EVIDENCE, ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_REJECTED),
    ],
)
def test_decision_status_mapping(decision, expected_status):
    attestation = _attestation(decision=decision)
    assert attestation.attestation_status == expected_status


def test_missing_attestor_expired_digest_mismatch_and_missing_receipt_block():
    assert _attestation(attestor_ref="").attestation_status == ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_INVALID
    assert _attestation(expired=True).attestation_status == ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_EXPIRED
    assert _attestation(expected_export_receipt_digest="sha256:not-the-export").attestation_status == ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_EXPORT_NOT_READY
    missing = build_provider_invocation_denial_attestation(None, attestor_ref="attestor", decision=ProviderInvocationDenialAttestationDecision.ATTEST_PROVIDER_INVOCATION_FORBIDDEN)
    assert missing.attestation_status == ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_MISSING_EVIDENCE


@pytest.mark.parametrize(
    "receipt, expected_status",
    [
        (_receipt(decision=ExternalAuditExportDecision.REJECT_EXPORT), ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_EXPORT_NOT_READY),
        (_receipt(secrets_included=True), ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_SENSITIVE_MATERIAL_DETECTED),
        (_receipt(runtime_handles_included=True), ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_RUNTIME_AUTHORITY_DETECTED),
        (_receipt(invocation_allowed=True), ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_OVERRIDE_DETECTED),
        (replace(_receipt(), invocation_denial_preserved=False), ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_OVERRIDE_DETECTED),
        (_receipt(export_io_performed=True), ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_EXPORT_NOT_READY),
    ],
)
def test_phase98_receipt_gating_blocks_not_ready_sensitive_runtime_override_io_or_denial_loss(receipt, expected_status):
    attestation = _attestation(receipt)
    assert attestation.attestation_status == expected_status
    assert not provider_invocation_denial_attestation_ready(attestation)


@pytest.mark.parametrize(
    "scope",
    [
        ProviderInvocationDenialAttestationScope.PROVIDER_INVOCATION_APPROVAL_FORBIDDEN,
        ProviderInvocationDenialAttestationScope.PROVIDER_SUBMISSION_FORBIDDEN,
        ProviderInvocationDenialAttestationScope.NETWORK_EGRESS_FORBIDDEN,
        ProviderInvocationDenialAttestationScope.EXPORT_DELIVERY_FORBIDDEN,
        ProviderInvocationDenialAttestationScope.TOOL_OR_ACTION_FORBIDDEN,
        ProviderInvocationDenialAttestationScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
    ],
)
def test_forbidden_scopes_block(scope):
    attestation = _attestation(attestation_scope=scope)
    assert attestation.attestation_status in {ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_EXPORT_NOT_READY, ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_OVERRIDE_DETECTED}
    assert any(code.startswith("forbidden_scope") for code in _codes(attestation))


@pytest.mark.parametrize("flag", ["export_io_performed", "external_delivery_performed", "network_upload_performed", "email_delivery_performed", "webhook_delivery_performed", "file_write_performed", "object_storage_write_performed"])
def test_export_io_and_delivery_flags_block(flag):
    attestation = _attestation(**{flag: True})
    assert attestation.attestation_status == ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_EXPORT_NOT_READY
    assert not provider_invocation_denial_attestation_does_not_export(attestation)


@pytest.mark.parametrize("flag", ["prompt_text_included", "hidden_chain_of_thought_included", "raw_payloads_included", "secrets_included", "secret_references_included", "endpoints_included", "endpoint_references_included", "clients_included", "client_references_included", "network_handles_included", "runtime_handles_included", "provider_params_included", "model_params_included", "tool_schemas_included"])
def test_sensitive_and_runtime_material_flags_block(flag):
    attestation = _attestation(**{flag: True})
    assert attestation.attestation_status in {ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_SENSITIVE_MATERIAL_DETECTED, ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_RUNTIME_AUTHORITY_DETECTED}
    assert not provider_invocation_denial_attestation_is_metadata_only(attestation)


@pytest.mark.parametrize("flag", ["invocation_allowed", "provider_send_allowed", "network_allowed", "credential_use_allowed", "endpoint_use_allowed", "client_use_allowed", "provider_sdk_allowed", "semantic_generation_allowed", "tool_calls_allowed", "memory_retrieval_allowed", "memory_write_allowed", "retention_allowed", "action_execution_allowed", "routing_allowed"])
def test_allowance_flags_block(flag):
    attestation = _attestation(**{flag: True})
    assert attestation.attestation_status in {ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_RUNTIME_AUTHORITY_DETECTED, ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_OVERRIDE_DETECTED}
    assert not provider_invocation_denial_attestation_ready(attestation)


@pytest.mark.parametrize(
    "marker, expected_status",
    [
        ("invocation approved provider invocation allowed approve provider call", ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_OVERRIDE_DETECTED),
        ("upload send deliver email webhook bucket object storage path=artifact destination recipient", ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_EXPORT_NOT_READY),
        ("prompt_text internal_candidate_text synthetic_prompt_text dry_run_prompt_text assembled_prompt system_prompt developer_prompt", ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_SENSITIVE_MATERIAL_DETECTED),
        ("hidden reasoning scratchpad", ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_SENSITIVE_MATERIAL_DETECTED),
        ("api_key bearer token secret password private_key authorization", ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_SENSITIVE_MATERIAL_DETECTED),
        ("https:// endpoint base_url host port dns resolve", ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_SENSITIVE_MATERIAL_DETECTED),
        ("client session transport retry request builder sdk openai anthropic", ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_SENSITIVE_MATERIAL_DETECTED),
        ("runtime handle raw_payload tool schema function call action retention routing memory write", ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_RUNTIME_AUTHORITY_DETECTED),
        ("invoke send_to_provider chat.completions completion", ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_OVERRIDE_DETECTED),
    ],
)
def test_adversarial_metadata_markers_block(marker, expected_status):
    attestation = _attestation(rationale=marker)
    assert attestation.attestation_status == expected_status
    assert not provider_invocation_denial_attestation_ready(attestation)


def test_evidence_summary_contains_counts_and_digests_only_not_bodies():
    attestation = _attestation()
    evidence = attestation.evidence_summary
    assert evidence.linked_artifact_count == 1
    assert isinstance(evidence.constraint_count, int)
    assert isinstance(attestation.export_receipt_digest, str)
    assert not hasattr(evidence, "artifact_body")
    assert not hasattr(evidence, "packet_body")
    assert not hasattr(evidence, "raw_payload")


def test_boolean_helpers_are_true_only_for_clean_attestation():
    clean = _attestation()
    assert provider_invocation_denial_attestation_is_metadata_only(clean)
    assert provider_invocation_denial_attestation_denies_invocation(clean)
    assert provider_invocation_denial_attestation_does_not_export(clean)
    assert provider_invocation_denial_attestation_contains_no_prompt_text(clean)
    assert provider_invocation_denial_attestation_contains_no_secrets(clean)
    assert provider_invocation_denial_attestation_contains_no_endpoints(clean)
    assert provider_invocation_denial_attestation_contains_no_clients(clean)
    assert provider_invocation_denial_attestation_contains_no_network_handles(clean)
    assert provider_invocation_denial_attestation_contains_no_runtime_authority(clean)
    assert provider_invocation_denial_attestation_ready(clean)
    assert not provider_invocation_denial_attestation_is_metadata_only(_attestation(secrets_included=True))
    assert not provider_invocation_denial_attestation_does_not_export(_attestation(export_io_performed=True))
    assert not provider_invocation_denial_attestation_contains_no_prompt_text(_attestation(prompt_text_included=True))
    assert not provider_invocation_denial_attestation_contains_no_secrets(_attestation(secrets_included=True))
    assert not provider_invocation_denial_attestation_contains_no_endpoints(_attestation(endpoints_included=True))
    assert not provider_invocation_denial_attestation_contains_no_clients(_attestation(clients_included=True))
    assert not provider_invocation_denial_attestation_contains_no_network_handles(_attestation(network_handles_included=True))
    assert not provider_invocation_denial_attestation_contains_no_runtime_authority(_attestation(runtime_handles_included=True))
    assert not provider_invocation_denial_attestation_ready(_attestation(decision=ProviderInvocationDenialAttestationDecision.REJECT_ATTESTATION))


def test_digest_is_deterministic_and_changes_for_stable_metadata_changes():
    base = _attestation()
    assert base.attestation_digest == compute_provider_invocation_denial_attestation_digest(base)
    assert base.attestation_digest == _attestation().attestation_digest
    changed = [
        _attestation(replace(_receipt(), export_receipt_digest="sha256:changed")),
        _attestation(expected_export_receipt_digest="sha256:expected"),
        _attestation(replace(_receipt(), external_review_packet_digest="sha256:changed-packet")),
        _attestation(replace(_receipt(), invocation_denial_review_digest="sha256:changed-denial")),
        _attestation(replace(_receipt(), readiness_digest="sha256:changed-readiness")),
        _attestation(attestor_ref="other-attestor"),
        _attestation(attestation_label="other-label"),
        _attestation(attestation_scope=ProviderInvocationDenialAttestationScope.EXTERNAL_AUDIT_DENIAL_ATTESTATION),
        _attestation(decision=ProviderInvocationDenialAttestationDecision.ATTEST_METADATA_ONLY_NOT_INVOCABLE),
        _attestation(approved_constraint_codes=("metadata_only", "extra"), rejected_constraint_codes=("reject-code",), accepted_evidence_codes=("phase98", "extra"), rejected_evidence_codes=("bad",), accepted_denial_codes=("denied",), rejected_denial_codes=("bad-denial",)),
        replace(base, evidence_summary=replace(base.evidence_summary, linked_artifact_count=base.evidence_summary.linked_artifact_count + 1)),
        _attestation(expires_at="2027-01-01T00:00:00Z", ttl_seconds=10),
        _attestation(export_io_performed=True),
        _attestation(network_allowed=True),
    ]
    digests = {compute_provider_invocation_denial_attestation_digest(item) for item in changed}
    assert base.attestation_digest not in digests
    assert len(digests) == len(changed)


def test_helper_does_not_mutate_phase98_97_96_95_inputs():
    registry, capability, registration, credential, endpoint, client, readiness, preflight, denial = _chain()
    packet = _packet(readiness=readiness, preflight=preflight, denial=denial, capability=capability, credential=credential, endpoint=endpoint, client=client)
    receipt = _receipt(packet)
    before = (receipt.export_receipt_digest, packet.external_review_packet_digest, denial.review_digest, readiness.readiness_digest)
    build_provider_invocation_denial_attestation(receipt, external_review_packet=packet, invocation_denial_review_receipt=denial, readiness_manifest=readiness, attestor_ref="attestor", decision=ProviderInvocationDenialAttestationDecision.ATTEST_PROVIDER_INVOCATION_FORBIDDEN)
    assert (receipt.export_receipt_digest, packet.external_review_packet_digest, denial.review_digest, readiness.readiness_digest) == before


def test_module_does_not_call_forbidden_runtime_functions():
    tree = ast.parse(MODULE_PATH.read_text())
    forbidden = {"assemble_prompt", "chat", "completions", "socket", "getenv", "open", "request", "urlopen", "send", "upload", "send_email", "write_memory", "save_memory", "execute_action", "route_work", "commit_retention"}
    calls = {getattr(node.func, "id", getattr(node.func, "attr", "")) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert not (calls & forbidden)


def test_prior_phase_invariants_remain_after_phase99_checks():
    registry, capability, registration, credential, endpoint, client, readiness, preflight, denial = _chain()
    packet = _packet(readiness=readiness, preflight=preflight, denial=denial, capability=capability, credential=credential, endpoint=endpoint, client=client)
    receipt = _receipt(packet)
    attestation = _attestation(receipt)
    assert provider_transport_registry_is_null_only(registry)
    assert registration.real_transport_registration_allowed is False
    assert provider_credential_custody_contains_no_secrets(credential)
    assert provider_endpoint_custody_contains_no_endpoints(endpoint)
    assert provider_client_custody_contains_no_clients(client)
    assert provider_invocation_readiness_forbids_invocation(readiness)
    assert provider_invocation_denial_review_affirms_forbidden_invocation(denial)
    assert external_security_review_packet_is_metadata_only(packet)
    assert external_security_review_packet_ready_for_review(packet)
    assert external_audit_export_receipt_ready_for_export_review(receipt)
    assert provider_invocation_denial_attestation_ready(attestation)


def test_phase63_to_phase99_metadata_only_path_and_blocked_candidate_do_not_enable_invocation():
    packet = _packet(reviewer_packet_ref="phase63-embodiment-proposal-metadata-ref")
    receipt = _receipt(packet, export_label="embodiment proposal metadata only")
    attestation = _attestation(receipt, attestation_label="embodiment proposal metadata only")
    assert provider_invocation_denial_attestation_ready(attestation)
    blocked = _attestation(receipt, rationale="blocked attempted candidate denied not_invocable forbidden")
    assert blocked.invocation_allowed is False
    assert blocked.provider_send_allowed is False
    assert provider_invocation_denial_attestation_ready(blocked)


def test_blocked_attempted_candidate_and_linked_artifact_contradictions_do_not_enable_attested_invocation():
    packet = replace(_packet(), packet_status=ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_BLOCKED)
    receipt = _receipt()
    attestation = build_provider_invocation_denial_attestation(receipt, external_review_packet=packet, attestor_ref="attestor", decision=ProviderInvocationDenialAttestationDecision.ATTEST_PROVIDER_INVOCATION_FORBIDDEN)
    assert attestation.invocation_allowed is False
    assert attestation.provider_send_allowed is False
    assert attestation.attestation_status == ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_EXPORT_NOT_READY


def test_guardrail_scans_new_module_and_import_purity_shape_is_clean():
    report = scan_context_hygiene_prompt_boundaries(paths=(str(MODULE_PATH),))
    assert report.ok, report.to_dict()
    source = MODULE_PATH.read_text()
    forbidden_import_tokens = ("import os", "import socket", "import requests", "import urllib", "import http", "import openai", "import anthropic", "prompt_assembler", "memory_manager")
    assert not any(token in source for token in forbidden_import_tokens)
