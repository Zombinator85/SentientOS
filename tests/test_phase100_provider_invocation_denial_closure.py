from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from scripts.verify_context_hygiene_prompt_boundaries import scan_context_hygiene_prompt_boundaries
from sentientos.context_hygiene.prompt_provider_invocation_denial_attestation import (
    ProviderInvocationDenialAttestationDecision,
    provider_invocation_denial_attestation_denies_invocation,
    provider_invocation_denial_attestation_does_not_export,
    provider_invocation_denial_attestation_is_metadata_only,
    provider_invocation_denial_attestation_ready,
)
from sentientos.context_hygiene.prompt_provider_invocation_denial_closure import (
    ProviderInvocationDenialClosureGuardrailSummary,
    ProviderInvocationDenialClosureScope,
    ProviderInvocationDenialClosureStatus,
    ProviderInvocationReleaseBlockerStatus,
    build_provider_invocation_denial_closure_manifest,
    compute_provider_invocation_denial_closure_digest,
    explain_provider_invocation_denial_closure_findings,
    provider_invocation_denial_closure_blocks_release,
    provider_invocation_denial_closure_contains_no_clients,
    provider_invocation_denial_closure_contains_no_endpoints,
    provider_invocation_denial_closure_contains_no_network_handles,
    provider_invocation_denial_closure_contains_no_prompt_text,
    provider_invocation_denial_closure_contains_no_runtime_authority,
    provider_invocation_denial_closure_contains_no_secrets,
    provider_invocation_denial_closure_denies_invocation,
    provider_invocation_denial_closure_does_not_export,
    provider_invocation_denial_closure_guardrails_present,
    provider_invocation_denial_closure_is_metadata_only,
    provider_invocation_denial_closure_ready,
    summarize_provider_invocation_denial_closure_manifest,
    validate_provider_invocation_denial_closure_manifest,
)
from sentientos.context_hygiene.prompt_provider_transport_registry import build_provider_transport_registry_manifest, provider_transport_registry_is_null_only
from sentientos.context_hygiene.prompt_provider_transport_capability import build_provider_transport_capability_manifest, evaluate_provider_transport_registration_preflight
from sentientos.context_hygiene.prompt_provider_credential_custody import build_provider_credential_custody_manifest, evaluate_provider_credential_custody_preflight, provider_credential_custody_contains_no_secrets
from sentientos.context_hygiene.prompt_provider_endpoint_custody import build_provider_endpoint_custody_manifest, evaluate_provider_endpoint_custody_preflight, provider_endpoint_custody_contains_no_endpoints
from sentientos.context_hygiene.prompt_provider_client_custody import build_provider_client_custody_manifest, evaluate_provider_client_custody_preflight, provider_client_custody_contains_no_clients
from sentientos.context_hygiene.prompt_provider_invocation_readiness import build_provider_invocation_readiness_manifest, evaluate_provider_invocation_readiness_preflight, provider_invocation_readiness_forbids_invocation
from sentientos.context_hygiene.prompt_provider_invocation_denial_review import ProviderInvocationDenialReviewDecision, ProviderInvocationDenialReviewScope, build_provider_invocation_denial_review_receipt, provider_invocation_denial_review_affirms_forbidden_invocation
from sentientos.context_hygiene.prompt_external_security_review import build_external_security_review_packet, external_security_review_packet_is_metadata_only
from sentientos.context_hygiene.prompt_external_audit_export import ExternalAuditExportDecision, ExternalAuditExportScope, build_external_audit_export_receipt, external_audit_export_receipt_does_not_export, external_audit_export_receipt_is_metadata_only
from tests.test_phase99_provider_invocation_denial_attestation import _attestation, _receipt

MODULE_PATH = Path("sentientos/context_hygiene/prompt_provider_invocation_denial_closure.py")


def _closure(attestation=None, **overrides):
    return build_provider_invocation_denial_closure_manifest(
        _attestation() if attestation is None else attestation,
        closure_ref=overrides.pop("closure_ref", "phase100-denial-runway-closure"),
        accepted_evidence_codes=overrides.pop("accepted_evidence_codes", ("phase95", "phase96", "phase97", "phase98", "phase99")),
        approved_constraint_codes=overrides.pop("approved_constraint_codes", ("metadata_only", "provider_invocation_release_blocked")),
        **overrides,
    )


def _full_chain():
    registry = build_provider_transport_registry_manifest()
    capability = build_provider_transport_capability_manifest()
    registration = evaluate_provider_transport_registration_preflight(capability, registry)
    credential = build_provider_credential_custody_manifest(linked_capability_manifest=capability)
    credential_preflight = evaluate_provider_credential_custody_preflight(credential, capability, registration)
    endpoint = build_provider_endpoint_custody_manifest(linked_capability_manifest=capability, linked_credential_custody_manifest=credential)
    endpoint_preflight = evaluate_provider_endpoint_custody_preflight(endpoint, capability, credential, credential_preflight)
    client = build_provider_client_custody_manifest(linked_capability_manifest=capability, linked_credential_custody_manifest=credential, linked_endpoint_custody_manifest=endpoint, linked_endpoint_custody_preflight=endpoint_preflight)
    client_preflight = evaluate_provider_client_custody_preflight(client, capability, credential, endpoint, endpoint_preflight)
    readiness = build_provider_invocation_readiness_manifest(registry_manifest=registry, capability_manifest=capability, registration_preflight=registration, credential_custody_manifest=credential, credential_custody_preflight=credential_preflight, endpoint_custody_manifest=endpoint, endpoint_custody_preflight=endpoint_preflight, client_custody_manifest=client, client_custody_preflight=client_preflight)
    preflight = evaluate_provider_invocation_readiness_preflight(readiness)
    denial = build_provider_invocation_denial_review_receipt(readiness, preflight, reviewer_ref="phase100-reviewer", decision=ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_EXTERNAL_SECURITY_REVIEW_GATE, review_scope=ProviderInvocationDenialReviewScope.FUTURE_EXTERNAL_SECURITY_REVIEW_GATE)
    packet = build_external_security_review_packet(denial, readiness_manifest=readiness, readiness_preflight=preflight, capability_manifest=capability, credential_custody_manifest=credential, endpoint_custody_manifest=endpoint, client_custody_manifest=client, reviewer_packet_ref="phase100-external-review")
    receipt = _receipt(packet)
    attestation = _attestation(receipt)
    return registry, capability, credential, endpoint, client, readiness, denial, packet, receipt, attestation


def _codes(manifest):
    return set(manifest.findings) | set(explain_provider_invocation_denial_closure_findings(manifest))


def test_clean_phase99_attestation_builds_sealed_metadata_only_release_blocker():
    manifest = _closure()
    assert manifest.closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED
    assert manifest.release_blocker_status == ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_BLOCKED
    assert provider_invocation_denial_closure_ready(manifest)
    assert not validate_provider_invocation_denial_closure_manifest(manifest)
    summary = summarize_provider_invocation_denial_closure_manifest(manifest)
    assert summary["provider_invocation_release_blocked"] is True
    assert summary["metadata_only"] is True
    assert manifest.provider_invocation_release_blocked is True


def test_allowed_scopes_yield_sealed_and_forbidden_scopes_block():
    for scope in (
        ProviderInvocationDenialClosureScope.PROVIDER_INVOCATION_DENIAL_CLOSURE,
        ProviderInvocationDenialClosureScope.PHASE100_CONTEXT_HYGIENE_CLOSURE,
        ProviderInvocationDenialClosureScope.PROVIDER_INVOCATION_RELEASE_BLOCKER,
        ProviderInvocationDenialClosureScope.INTERNAL_SECURITY_CLOSURE_SUMMARY,
    ):
        assert _closure(closure_scope=scope).closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED
    for scope in (
        ProviderInvocationDenialClosureScope.PROVIDER_INVOCATION_RELEASE_APPROVAL_FORBIDDEN,
        ProviderInvocationDenialClosureScope.PROVIDER_INVOCATION_APPROVAL_FORBIDDEN,
        ProviderInvocationDenialClosureScope.PROVIDER_SUBMISSION_FORBIDDEN,
        ProviderInvocationDenialClosureScope.NETWORK_EGRESS_FORBIDDEN,
        ProviderInvocationDenialClosureScope.EXPORT_DELIVERY_FORBIDDEN,
        ProviderInvocationDenialClosureScope.TOOL_OR_ACTION_FORBIDDEN,
        ProviderInvocationDenialClosureScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
    ):
        assert any(code.startswith("forbidden_scope") for code in _codes(_closure(closure_scope=scope)))


def test_conditions_and_required_metadata_gates():
    conditioned = _closure(_attestation(decision=ProviderInvocationDenialAttestationDecision.ATTEST_WITH_CONDITIONS))
    assert conditioned.closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED_WITH_CONDITIONS
    assert conditioned.release_blocker_status == ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_BLOCKED_WITH_CONDITIONS
    assert _closure(closure_ref="").closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_BLOCKED
    assert "missing_release_blocker_codes" in _codes(_closure(release_blocker_codes=()))
    assert "missing_future_clearance_requirement_codes" in _codes(_closure(future_clearance_requirement_codes=()))
    assert "attestation_digest_mismatch" in _codes(_closure(expected_attestation_digest="sha256:not-the-attestation"))
    assert build_provider_invocation_denial_closure_manifest(None, closure_ref="phase100").closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_MISSING_EVIDENCE


def test_phase99_bad_states_block_closure():
    assert _closure(_attestation(decision=ProviderInvocationDenialAttestationDecision.REJECT_ATTESTATION)).closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_ATTESTATION_NOT_READY
    assert _closure(_attestation(_receipt(secrets_included=True))).closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SENSITIVE_MATERIAL_DETECTED
    assert _closure(_attestation(_receipt(runtime_handles_included=True))).closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_RUNTIME_AUTHORITY_DETECTED
    assert _closure(_attestation(_receipt(invocation_allowed=True))).closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_OVERRIDE_DETECTED
    assert _closure(_attestation(_receipt(export_io_performed=True))).closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_ATTESTATION_NOT_READY
    assert "invocation_override:attestation_does_not_deny_invocation" in _codes(_closure(replace(_attestation(), invocation_denial_preserved=False)))


def test_output_flags_and_allowance_flags_fail_closed():
    for field in ("export_io_performed", "external_delivery_performed", "network_upload_performed", "email_delivery_performed", "webhook_delivery_performed", "file_write_performed", "object_storage_write_performed"):
        manifest = _closure(**{field: True})
        assert f"io_attempt:{field}" in _codes(manifest)
        assert not provider_invocation_denial_closure_does_not_export(manifest)
    for field in ("prompt_text_included", "hidden_chain_of_thought_included", "raw_payloads_included", "secrets_included", "secret_references_included", "endpoints_included", "endpoint_references_included", "clients_included", "client_references_included", "network_handles_included", "runtime_handles_included", "provider_params_included", "model_params_included", "tool_schemas_included"):
        assert f"sensitive_material_included:{field}" in _codes(_closure(**{field: True}))
    for field in ("invocation_allowed", "provider_send_allowed", "network_allowed", "credential_use_allowed", "endpoint_use_allowed", "client_use_allowed", "provider_sdk_allowed", "semantic_generation_allowed", "tool_calls_allowed", "memory_retrieval_allowed", "memory_write_allowed", "retention_allowed", "action_execution_allowed", "routing_allowed"):
        assert f"runtime_authority_allowed:{field}" in _codes(_closure(**{field: True}))
    assert _closure(provider_invocation_release_blocked=False).release_blocker_status == ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_UNBLOCKED_FORBIDDEN


def test_metadata_marker_detection_blocks_adversarial_material():
    markers = {
        "invocation_approval": "release approved and unblock provider",
        "export_destination": "upload to email webhook bucket path=unsafe",
        "prompt_text": "prompt_text synthetic_prompt_text dry_run_prompt_text assembled_prompt system_prompt developer_prompt",
        "hidden_chain_of_thought": "hidden reasoning scratchpad",
        "secrets": "api_key bearer token password private_key authorization",
        "endpoints": "https://example.invalid endpoint base_url host port DNS resolve",
        "clients": "client session transport stream retry request builder SDK OpenAI Anthropic",
        "runtime": "runtime handle raw_payload tool schema function call action retention routing memory write",
        "provider_invocation": "invoke send_to_provider chat.completions completion",
    }
    for category, text in markers.items():
        assert any(code.startswith(f"metadata_marker_detected:{category}") for code in _codes(_closure(rationale=text)))


def test_evidence_guardrail_release_and_future_summaries_are_metadata_only():
    guardrail = ProviderInvocationDenialClosureGuardrailSummary(prompt_boundary_guardrail_clean=True, architecture_boundaries_clean=True, import_purity_clean=True, immutability_audit_clean=True, guardrail_summary_complete=True)
    registry, capability, credential, endpoint, client, readiness, denial, packet, receipt, attestation = _full_chain()
    manifest = _closure(attestation, external_audit_export_receipt=receipt, external_security_review_packet=packet, invocation_denial_review_receipt=denial, invocation_readiness_manifest=readiness, registry_manifest=registry, transport_capability_manifest=capability, credential_custody_manifest=credential, endpoint_custody_manifest=endpoint, client_custody_manifest=client, guardrail_summary=guardrail)
    evidence = asdict(manifest.evidence_summary)
    assert set(evidence) == {"linked_artifact_count", "formal_attestation_ready", "export_receipt_ready", "external_review_packet_ready", "denial_review_affirmed", "readiness_metadata_only", "registry_null_only", "transport_capability_null_only", "credential_custody_no_secret", "endpoint_custody_no_endpoint", "client_custody_no_client", "digest_chain_complete", "constraint_count", "warning_count", "finding_count"}
    assert manifest.evidence_summary.linked_artifact_count >= 5
    assert provider_invocation_denial_closure_guardrails_present(manifest)
    assert "provider_invocation_release_blocked" in manifest.release_blocker_codes
    assert "future_phase_required_to_allow_provider_invocation" in manifest.future_clearance_requirement_codes
    assert "independent_security_review_required_before_any_unblock" in manifest.future_clearance_requirement_codes
    assert "explicit_operator_approval_required_before_any_unblock" in manifest.future_clearance_requirement_codes


def test_boolean_helpers_are_true_only_for_clean_closure():
    clean = _closure()
    assert provider_invocation_denial_closure_is_metadata_only(clean)
    assert provider_invocation_denial_closure_blocks_release(clean)
    assert provider_invocation_denial_closure_denies_invocation(clean)
    assert provider_invocation_denial_closure_does_not_export(clean)
    assert provider_invocation_denial_closure_contains_no_prompt_text(clean)
    assert provider_invocation_denial_closure_contains_no_secrets(clean)
    assert provider_invocation_denial_closure_contains_no_endpoints(clean)
    assert provider_invocation_denial_closure_contains_no_clients(clean)
    assert provider_invocation_denial_closure_contains_no_network_handles(clean)
    assert provider_invocation_denial_closure_contains_no_runtime_authority(clean)
    assert provider_invocation_denial_closure_ready(clean)
    assert not provider_invocation_denial_closure_guardrails_present(clean)
    assert not provider_invocation_denial_closure_is_metadata_only(_closure(secrets_included=True))
    assert not provider_invocation_denial_closure_contains_no_secrets(_closure(secrets_included=True))
    assert not provider_invocation_denial_closure_contains_no_endpoints(_closure(endpoints_included=True))
    assert not provider_invocation_denial_closure_contains_no_clients(_closure(clients_included=True))
    assert not provider_invocation_denial_closure_contains_no_network_handles(_closure(network_handles_included=True))
    assert not provider_invocation_denial_closure_contains_no_runtime_authority(_closure(invocation_allowed=True))


def test_digest_is_deterministic_and_changes_for_stable_metadata_fields():
    base = _closure()
    assert base.closure_digest == compute_provider_invocation_denial_closure_digest(base)
    assert _closure().closure_digest == base.closure_digest
    variants = [
        _closure(replace(_attestation(), attestation_digest="sha256:changed")),
        _closure(expected_attestation_digest=base.formal_attestation_digest),
        _closure(external_audit_export_receipt={"export_receipt_id": "x", "export_receipt_digest": "sha256:export", "metadata_only": True, "export_io_not_performed": True, "external_delivery_not_performed": True, "export_io_performed": False, "invocation_allowed": False, "provider_send_allowed": False}),
        _closure(closure_ref="phase100-other"),
        _closure(closure_label="label"),
        _closure(closure_scope=ProviderInvocationDenialClosureScope.INTERNAL_SECURITY_CLOSURE_SUMMARY),
        _closure(release_blocker_codes=("provider_invocation_release_blocked",)),
        _closure(future_clearance_requirement_codes=("future_phase_required_to_allow_provider_invocation",)),
        _closure(accepted_evidence_codes=("phase99",), rejected_evidence_codes=("none",)),
        _closure(guardrail_summary={"guardrail_summary_complete": True}),
        _closure(export_io_performed=True),
        _closure(invocation_allowed=True),
    ]
    assert all(variant.closure_digest != base.closure_digest for variant in variants)


def test_helper_does_not_mutate_inputs_or_call_runtime_surfaces():
    registry, capability, credential, endpoint, client, readiness, denial, packet, receipt, attestation = _full_chain()
    originals = [asdict(item) for item in (registry, capability, credential, endpoint, client, readiness, denial, packet, receipt, attestation)]
    with patch("sentientos.context_hygiene.prompt_provider_invocation_denial_closure.compute_provider_invocation_denial_attestation_digest", wraps=lambda value: value.attestation_digest) as digest:
        manifest = _closure(attestation, external_audit_export_receipt=receipt, external_security_review_packet=packet, invocation_denial_review_receipt=denial, invocation_readiness_manifest=readiness, registry_manifest=registry, transport_capability_manifest=capability, credential_custody_manifest=credential, endpoint_custody_manifest=endpoint, client_custody_manifest=client)
    assert digest.call_count == 0
    assert [asdict(item) for item in (registry, capability, credential, endpoint, client, readiness, denial, packet, receipt, attestation)] == originals
    assert provider_transport_registry_is_null_only(registry)
    assert not registration_allows_real_transport(capability, registry)
    assert provider_credential_custody_contains_no_secrets(credential)
    assert provider_endpoint_custody_contains_no_endpoints(endpoint)
    assert provider_client_custody_contains_no_clients(client)
    assert provider_invocation_readiness_forbids_invocation(readiness)
    assert provider_invocation_denial_review_affirms_forbidden_invocation(denial)
    assert external_security_review_packet_is_metadata_only(packet)
    assert external_audit_export_receipt_is_metadata_only(receipt) and external_audit_export_receipt_does_not_export(receipt)
    assert provider_invocation_denial_attestation_is_metadata_only(attestation)
    assert provider_invocation_denial_attestation_does_not_export(attestation)
    assert provider_invocation_denial_attestation_denies_invocation(attestation)
    assert manifest.provider_invocation_release_blocked is True


def registration_allows_real_transport(capability, registry):
    preflight = evaluate_provider_transport_registration_preflight(capability, registry, requested_registration={"adapter_kind": "provider_transport_http_adapter_forbidden"})
    return preflight.real_transport_registration_allowed or preflight.http_transport_registration_allowed or not preflight.real_transport_registration_forbidden


def test_phase63_and_phase62b_style_inputs_remain_metadata_only_and_cannot_unblock_release():
    phase63_metadata = _closure(accepted_evidence_codes=("phase63_embodiment_proposal_digest_only", "phase99"))
    assert phase63_metadata.metadata_only and phase63_metadata.provider_invocation_release_blocked
    blocked_attempt = _closure(rationale="blocked attempted candidate denied; provider_invocation_release_blocked")
    assert provider_invocation_denial_closure_ready(blocked_attempt)
    assert "release_unblocked_forbidden" in _codes(_closure(rationale="unblock provider"))


def test_phase75_guardrail_scans_new_module_and_architecture_import_purity_surface():
    report = scan_context_hygiene_prompt_boundaries([MODULE_PATH])
    assert report.status.value == "boundary_clean"
    assert not report.findings
