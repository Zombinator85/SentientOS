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
    compute_external_audit_export_receipt_digest,
    explain_external_audit_export_receipt_findings,
    external_audit_export_receipt_contains_no_clients,
    external_audit_export_receipt_contains_no_endpoints,
    external_audit_export_receipt_contains_no_network_handles,
    external_audit_export_receipt_contains_no_prompt_text,
    external_audit_export_receipt_contains_no_runtime_authority,
    external_audit_export_receipt_contains_no_secrets,
    external_audit_export_receipt_does_not_export,
    external_audit_export_receipt_is_metadata_only,
    external_audit_export_receipt_preserves_invocation_denial,
    external_audit_export_receipt_ready_for_export_review,
    summarize_external_audit_export_receipt,
    validate_external_audit_export_receipt,
)
from sentientos.context_hygiene.prompt_external_security_review import (
    ExternalSecurityReviewPacketStatus,
    build_external_security_review_packet,
    external_security_review_packet_is_metadata_only,
    external_security_review_packet_preserves_invocation_denial,
    external_security_review_packet_ready_for_review,
)
from sentientos.context_hygiene.prompt_provider_client_custody import build_provider_client_custody_manifest, evaluate_provider_client_custody_preflight, provider_client_custody_contains_no_clients
from sentientos.context_hygiene.prompt_provider_credential_custody import build_provider_credential_custody_manifest, evaluate_provider_credential_custody_preflight, provider_credential_custody_contains_no_secrets
from sentientos.context_hygiene.prompt_provider_endpoint_custody import build_provider_endpoint_custody_manifest, evaluate_provider_endpoint_custody_preflight, provider_endpoint_custody_contains_no_endpoints
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

MODULE_PATH = Path("sentientos/context_hygiene/prompt_external_audit_export.py")


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
        reviewer_ref="phase98-denial-reviewer",
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
        reviewer_packet_ref=overrides.pop("reviewer_packet_ref", "phase98-review-packet"),
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


def _codes(receipt):
    return set(receipt.findings) | set(explain_external_audit_export_receipt_findings(receipt))


def test_receipt_can_be_built_from_clean_phase97_packet():
    receipt = _receipt()
    assert receipt.export_status in {ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_READY, ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_READY_WITH_CONDITIONS}
    assert external_audit_export_receipt_ready_for_export_review(receipt)
    assert not validate_external_audit_export_receipt(receipt)
    assert summarize_external_audit_export_receipt(receipt)["export_io_not_performed"] is True


@pytest.mark.parametrize(
    "scope",
    [
        ExternalAuditExportScope.EXTERNAL_AUDIT_METADATA_EXPORT_RECEIPT,
        ExternalAuditExportScope.INTERNAL_AUDIT_METADATA_EXPORT_RECEIPT,
        ExternalAuditExportScope.SECURITY_REVIEW_EXPORT_RECEIPT,
        ExternalAuditExportScope.INVOCATION_DENIAL_AUDIT_EXPORT_RECEIPT,
    ],
)
def test_allowed_metadata_scopes_yield_ready(scope):
    receipt = _receipt(export_scope=scope)
    assert receipt.export_status == ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_READY
    assert external_audit_export_receipt_ready_for_export_review(receipt)


def test_approve_with_conditions_yields_ready_with_conditions():
    receipt = _receipt(decision=ExternalAuditExportDecision.APPROVE_WITH_CONDITIONS)
    assert receipt.export_status == ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_READY_WITH_CONDITIONS
    assert external_audit_export_receipt_ready_for_export_review(receipt)


@pytest.mark.parametrize("decision", [ExternalAuditExportDecision.REJECT_EXPORT, ExternalAuditExportDecision.REQUEST_MORE_REDACTION, ExternalAuditExportDecision.REQUEST_MORE_EVIDENCE, ExternalAuditExportDecision.NO_DECISION])
def test_non_approval_decisions_reject(decision):
    receipt = _receipt(decision=decision)
    assert receipt.export_status == ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_REJECTED
    assert not external_audit_export_receipt_ready_for_export_review(receipt)


def test_missing_exporter_ref_yields_invalid():
    receipt = _receipt(exporter_ref="")
    assert receipt.export_status == ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_INVALID
    assert "missing_exporter_ref" in _codes(receipt)


def test_expired_receipt_yields_expired():
    receipt = _receipt(expired=True, expires_at="2026-01-01T00:00:00Z")
    assert receipt.export_status == ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_EXPIRED
    assert not external_audit_export_receipt_ready_for_export_review(receipt)


def test_expected_packet_digest_mismatch_blocks():
    receipt = _receipt(expected_packet_digest="sha256:not-the-packet")
    assert receipt.export_status == ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_PACKET_NOT_READY
    assert "packet_digest_mismatch" in _codes(receipt)


def test_missing_phase97_packet_yields_packet_missing():
    receipt = build_external_audit_export_receipt(None, exporter_ref="audit-ref", decision=ExternalAuditExportDecision.APPROVE_METADATA_EXPORT_REVIEW)
    assert receipt.export_status == ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_PACKET_MISSING


@pytest.mark.parametrize(
    "packet_overrides, expected_status",
    [
        ({"packet_status": ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_BLOCKED}, ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_PACKET_NOT_READY),
        ({"secrets_included": True}, ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_SENSITIVE_MATERIAL_DETECTED),
        ({"runtime_handles_included": True}, ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_RUNTIME_AUTHORITY_DETECTED),
        ({"invocation_allowed": True}, ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_INVOCATION_OVERRIDE_DETECTED),
        ({"invocation_denial_preserved": False}, ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_INVOCATION_OVERRIDE_DETECTED),
    ],
)
def test_phase97_packet_gating_blocks_not_ready_sensitive_runtime_or_override(packet_overrides, expected_status):
    packet = replace(_packet(), **packet_overrides)
    receipt = _receipt(packet)
    assert receipt.export_status == expected_status
    assert not external_audit_export_receipt_ready_for_export_review(receipt)


@pytest.mark.parametrize(
    "scope",
    [
        ExternalAuditExportScope.LIVE_EXTERNAL_DELIVERY_FORBIDDEN,
        ExternalAuditExportScope.PROVIDER_SUBMISSION_FORBIDDEN,
        ExternalAuditExportScope.NETWORK_UPLOAD_FORBIDDEN,
        ExternalAuditExportScope.EMAIL_DELIVERY_FORBIDDEN,
        ExternalAuditExportScope.WEBHOOK_DELIVERY_FORBIDDEN,
        ExternalAuditExportScope.FILE_WRITE_FORBIDDEN,
        ExternalAuditExportScope.OBJECT_STORAGE_FORBIDDEN,
        ExternalAuditExportScope.TOOL_OR_ACTION_FORBIDDEN,
    ],
)
def test_forbidden_scopes_block_as_io_attempt(scope):
    receipt = _receipt(export_scope=scope)
    assert receipt.export_status == ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_IO_ATTEMPT_DETECTED
    assert any(code.startswith("forbidden_scope") for code in _codes(receipt))


@pytest.mark.parametrize("flag", ["export_io_performed", "external_delivery_performed", "network_upload_performed", "email_delivery_performed", "webhook_delivery_performed", "file_write_performed", "object_storage_write_performed"])
def test_export_io_flags_block(flag):
    receipt = _receipt(**{flag: True})
    assert receipt.export_status == ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_IO_ATTEMPT_DETECTED
    assert not external_audit_export_receipt_does_not_export(receipt)


@pytest.mark.parametrize("flag", ["packet_body_included", "artifact_bodies_included", "prompt_text_included", "hidden_chain_of_thought_included", "raw_payloads_included", "secrets_included", "secret_references_included", "endpoints_included", "endpoint_references_included", "clients_included", "client_references_included", "network_handles_included", "runtime_handles_included", "provider_params_included", "tool_schemas_included"])
def test_sensitive_material_flags_block(flag):
    receipt = _receipt(**{flag: True})
    assert receipt.export_status in {ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_SENSITIVE_MATERIAL_DETECTED, ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_RUNTIME_AUTHORITY_DETECTED}
    assert not external_audit_export_receipt_is_metadata_only(receipt)


@pytest.mark.parametrize("flag", ["invocation_allowed", "provider_send_allowed", "network_allowed", "credential_use_allowed", "endpoint_use_allowed", "client_use_allowed", "provider_sdk_allowed", "semantic_generation_allowed", "tool_calls_allowed", "memory_retrieval_allowed", "memory_write_allowed", "retention_allowed", "action_execution_allowed", "routing_allowed"])
def test_allowance_flags_block(flag):
    receipt = _receipt(**{flag: True})
    assert receipt.export_status in {ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_RUNTIME_AUTHORITY_DETECTED, ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_INVOCATION_OVERRIDE_DETECTED}
    assert not external_audit_export_receipt_ready_for_export_review(receipt)


@pytest.mark.parametrize(
    "marker, status",
    [
        ("upload destination bucket path=artifact", ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_IO_ATTEMPT_DETECTED),
        ("prompt_text internal_candidate_text synthetic_prompt_text dry_run_prompt_text assembled_prompt system_prompt developer_prompt", ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_SENSITIVE_MATERIAL_DETECTED),
        ("hidden reasoning scratchpad", ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_SENSITIVE_MATERIAL_DETECTED),
        ("api_key bearer token secret password private_key authorization", ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_SENSITIVE_MATERIAL_DETECTED),
        ("https:// endpoint base_url host port dns resolve", ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_SENSITIVE_MATERIAL_DETECTED),
        ("client session transport retry request builder sdk openai anthropic", ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_SENSITIVE_MATERIAL_DETECTED),
        ("runtime handle raw_payload tool schema function call action retention routing memory write", ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_RUNTIME_AUTHORITY_DETECTED),
        ("invoke send_to_provider chat.completions completion", ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_INVOCATION_OVERRIDE_DETECTED),
    ],
)
def test_adversarial_metadata_markers_block(marker, status):
    receipt = _receipt(rationale=marker)
    assert receipt.export_status == status
    assert not external_audit_export_receipt_ready_for_export_review(receipt)


def test_evidence_and_redaction_summaries_are_counts_only():
    receipt = _receipt()
    evidence = receipt.evidence_summary
    redaction = receipt.redaction_summary
    assert isinstance(evidence.evidence_link_count, int)
    assert not hasattr(evidence, "artifact_body")
    assert not hasattr(evidence, "raw_payload")
    assert isinstance(redaction.secrets_removed, int)
    assert not hasattr(redaction, "secret_value")
    assert not hasattr(redaction, "restored_material")


def test_rejected_required_redaction_code_prevents_readiness():
    receipt = _receipt(rejected_redaction_codes=("secrets_removed",))
    assert receipt.export_status == ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_SENSITIVE_MATERIAL_DETECTED
    assert "required_redaction_rejected" in _codes(receipt)


def test_boolean_helpers_are_true_only_for_clean_receipts():
    clean = _receipt()
    assert external_audit_export_receipt_is_metadata_only(clean)
    assert external_audit_export_receipt_does_not_export(clean)
    assert external_audit_export_receipt_contains_no_prompt_text(clean)
    assert external_audit_export_receipt_contains_no_secrets(clean)
    assert external_audit_export_receipt_contains_no_endpoints(clean)
    assert external_audit_export_receipt_contains_no_clients(clean)
    assert external_audit_export_receipt_contains_no_network_handles(clean)
    assert external_audit_export_receipt_contains_no_runtime_authority(clean)
    assert external_audit_export_receipt_preserves_invocation_denial(clean)
    assert external_audit_export_receipt_ready_for_export_review(clean)
    assert not external_audit_export_receipt_is_metadata_only(_receipt(secrets_included=True))
    assert not external_audit_export_receipt_does_not_export(_receipt(export_io_performed=True))
    assert not external_audit_export_receipt_contains_no_prompt_text(_receipt(prompt_text_included=True))
    assert not external_audit_export_receipt_contains_no_secrets(_receipt(secrets_included=True))
    assert not external_audit_export_receipt_contains_no_endpoints(_receipt(endpoints_included=True))
    assert not external_audit_export_receipt_contains_no_clients(_receipt(clients_included=True))
    assert not external_audit_export_receipt_contains_no_network_handles(_receipt(network_handles_included=True))
    assert not external_audit_export_receipt_contains_no_runtime_authority(_receipt(runtime_handles_included=True))
    assert not external_audit_export_receipt_ready_for_export_review(_receipt(decision=ExternalAuditExportDecision.REJECT_EXPORT))


def test_digest_is_deterministic_and_changes_for_stable_metadata_changes():
    base = _receipt()
    assert base.export_receipt_digest == compute_external_audit_export_receipt_digest(base)
    assert base.export_receipt_digest == _receipt().export_receipt_digest
    changed_receipts = [
        _receipt(replace(_packet(), external_review_packet_digest="sha256:changed")),
        _receipt(expected_packet_digest="sha256:expected"),
        _receipt(exporter_ref="other-exporter"),
        _receipt(export_label="other-label"),
        _receipt(export_scope=ExternalAuditExportScope.INTERNAL_AUDIT_METADATA_EXPORT_RECEIPT),
        _receipt(decision=ExternalAuditExportDecision.APPROVE_WITH_CONDITIONS),
        _receipt(approved_constraint_codes=("metadata_only", "extra"), rejected_constraint_codes=("reject-code",), accepted_redaction_codes=("secrets_removed",), rejected_evidence_codes=("bad-evidence",)),
        replace(base, evidence_summary=replace(base.evidence_summary, evidence_link_count=base.evidence_summary.evidence_link_count + 1)),
        replace(base, redaction_summary=replace(base.redaction_summary, secrets_removed=base.redaction_summary.secrets_removed + 1)),
        _receipt(expires_at="2027-01-01T00:00:00Z", ttl_seconds=10),
        _receipt(export_io_performed=True),
        _receipt(network_allowed=True),
    ]
    digests = {compute_external_audit_export_receipt_digest(item) for item in changed_receipts}
    assert base.export_receipt_digest not in digests
    assert len(digests) == len(changed_receipts)


def test_helper_does_not_mutate_phase97_packet():
    packet = _packet()
    before = packet.external_review_packet_digest
    _receipt(packet)
    assert packet.external_review_packet_digest == before
    assert external_security_review_packet_ready_for_review(packet)


def test_module_does_not_call_forbidden_runtime_functions():
    tree = ast.parse(MODULE_PATH.read_text())
    forbidden = {"assemble_prompt", "chat", "completions", "socket", "getenv", "open", "request", "urlopen", "send", "upload", "send_email", "write_memory", "save_memory", "execute_action", "route_work", "commit_retention"}
    calls = {getattr(node.func, "id", getattr(node.func, "attr", "")) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert not (calls & forbidden)


def test_prior_phase_invariants_remain_after_phase98_checks():
    registry, capability, registration, credential, endpoint, client, readiness, preflight, denial = _chain()
    receipt = _receipt()
    assert provider_transport_registry_is_null_only(registry)
    assert registration.real_transport_registration_allowed is False
    assert provider_credential_custody_contains_no_secrets(credential)
    assert provider_endpoint_custody_contains_no_endpoints(endpoint)
    assert provider_client_custody_contains_no_clients(client)
    assert provider_invocation_readiness_forbids_invocation(readiness)
    assert provider_invocation_denial_review_affirms_forbidden_invocation(denial)
    packet = _packet()
    assert external_security_review_packet_is_metadata_only(packet)
    assert external_security_review_packet_preserves_invocation_denial(packet)
    assert external_audit_export_receipt_ready_for_export_review(receipt)


def test_phase63_to_phase98_metadata_only_path_and_blocked_candidate_do_not_enable_invocation():
    packet = _packet(reviewer_packet_ref="phase63-embodiment-proposal-metadata-ref")
    receipt = _receipt(packet, export_label="embodiment proposal metadata only")
    assert external_audit_export_receipt_ready_for_export_review(receipt)
    blocked = _receipt(packet, rationale="blocked attempted candidate denied not_invocable forbidden")
    assert blocked.invocation_allowed is False
    assert blocked.provider_send_allowed is False
    assert external_audit_export_receipt_ready_for_export_review(blocked)


def test_guardrail_scans_new_module_and_import_purity_shape_is_clean():
    report = scan_context_hygiene_prompt_boundaries(paths=(str(MODULE_PATH),))
    assert report.ok, report.to_dict()
    source = MODULE_PATH.read_text()
    forbidden_import_tokens = ("import os", "import socket", "import requests", "import urllib", "import http", "import openai", "import anthropic", "prompt_assembler", "memory_manager")
    assert not any(token in source for token in forbidden_import_tokens)
