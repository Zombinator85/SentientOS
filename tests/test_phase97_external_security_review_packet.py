from __future__ import annotations

from dataclasses import asdict, replace
import ast
from pathlib import Path

import pytest

from scripts import verify_context_hygiene_prompt_boundaries as guardrails
from sentientos.context_hygiene.embodiment_context import build_embodiment_context_candidates
from sentientos.context_hygiene.prompt_external_security_review import (
    ExternalSecurityReviewPacketStatus,
    ExternalSecurityReviewScope,
    build_external_security_review_packet,
    compute_external_security_review_packet_digest,
    explain_external_security_review_packet_findings,
    external_security_review_packet_contains_no_clients,
    external_security_review_packet_contains_no_endpoints,
    external_security_review_packet_contains_no_network_handles,
    external_security_review_packet_contains_no_prompt_text,
    external_security_review_packet_contains_no_runtime_authority,
    external_security_review_packet_contains_no_secrets,
    external_security_review_packet_is_metadata_only,
    external_security_review_packet_preserves_invocation_denial,
    external_security_review_packet_ready_for_review,
    summarize_external_security_review_packet,
    ExternalSecurityReviewFindingSummary,
    validate_external_security_review_packet,
)
from sentientos.context_hygiene.prompt_provider_client_custody import (
    build_provider_client_custody_manifest,
    evaluate_provider_client_custody_preflight,
    provider_client_custody_contains_no_clients,
)
from sentientos.context_hygiene.prompt_provider_credential_custody import (
    build_provider_credential_custody_manifest,
    evaluate_provider_credential_custody_preflight,
    provider_credential_custody_contains_no_secrets,
)
from sentientos.context_hygiene.prompt_provider_endpoint_custody import (
    build_provider_endpoint_custody_manifest,
    evaluate_provider_endpoint_custody_preflight,
    provider_endpoint_custody_contains_no_endpoints,
)
from sentientos.context_hygiene.prompt_provider_invocation_denial_review import (
    ProviderInvocationDenialReviewDecision,
    ProviderInvocationDenialReviewScope,
    ProviderInvocationDenialReviewStatus,
    build_provider_invocation_denial_review_receipt,
    provider_invocation_denial_review_approves_future_external_security_review_gate,
    provider_invocation_denial_review_attempts_forbidden_invocation_override,
    provider_invocation_denial_review_remains_metadata_only,
)
from sentientos.context_hygiene.prompt_provider_invocation_readiness import (
    build_provider_invocation_readiness_manifest,
    evaluate_provider_invocation_readiness_preflight,
    provider_invocation_preflight_remains_metadata_only,
    provider_invocation_readiness_forbids_invocation,
)
from sentientos.context_hygiene.prompt_provider_transport_capability import (
    ProviderTransportCapabilityKind,
    ProviderTransportRegistrationStatus,
    build_provider_transport_capability_manifest,
    evaluate_provider_transport_registration_preflight,
    provider_transport_registration_preflight_denies_real_transport,
)
from sentientos.context_hygiene.prompt_provider_transport_registry import (
    build_provider_transport_registry_manifest,
    provider_transport_registry_is_null_only,
)
from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = "sentientos/context_hygiene/prompt_external_security_review.py"


def _chain(**overrides):
    registry = overrides.get("registry") or build_provider_transport_registry_manifest()
    capability = overrides.get("capability") or build_provider_transport_capability_manifest()
    registration = overrides.get("registration") or evaluate_provider_transport_registration_preflight(capability, registry)
    credential = overrides.get("credential") or build_provider_credential_custody_manifest(linked_capability_manifest=capability)
    credential_preflight = overrides.get("credential_preflight") or evaluate_provider_credential_custody_preflight(credential, capability, registration)
    endpoint = overrides.get("endpoint") or build_provider_endpoint_custody_manifest(linked_capability_manifest=capability, linked_credential_custody_manifest=credential)
    endpoint_preflight = overrides.get("endpoint_preflight") or evaluate_provider_endpoint_custody_preflight(endpoint, capability, credential, credential_preflight)
    client = overrides.get("client") or build_provider_client_custody_manifest(
        linked_capability_manifest=capability,
        linked_credential_custody_manifest=credential,
        linked_endpoint_custody_manifest=endpoint,
        linked_endpoint_custody_preflight=endpoint_preflight,
    )
    client_preflight = overrides.get("client_preflight") or evaluate_provider_client_custody_preflight(client, capability, credential, endpoint, endpoint_preflight)
    return {
        "registry_manifest": registry,
        "capability_manifest": capability,
        "registration_preflight": registration,
        "credential_custody_manifest": credential,
        "credential_custody_preflight": credential_preflight,
        "endpoint_custody_manifest": endpoint,
        "endpoint_custody_preflight": endpoint_preflight,
        "client_custody_manifest": client,
        "client_custody_preflight": client_preflight,
    }


def _manifest(**kwargs):
    chain = _chain(**{key: value for key, value in kwargs.items() if key in {"registry", "capability", "registration", "credential", "credential_preflight", "endpoint", "endpoint_preflight", "client", "client_preflight"}})
    chain.update({key: value for key, value in kwargs.items() if key not in {"registry", "capability", "registration", "credential", "credential_preflight", "endpoint", "endpoint_preflight", "client", "client_preflight"}})
    return build_provider_invocation_readiness_manifest(**chain)


def _clean_artifacts():
    chain = _chain()
    readiness = build_provider_invocation_readiness_manifest(**chain)
    preflight = evaluate_provider_invocation_readiness_preflight(readiness)
    receipt = build_provider_invocation_denial_review_receipt(
        readiness,
        preflight,
        reviewer_ref="external-security-reviewer",
        decision=ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_EXTERNAL_SECURITY_REVIEW_GATE,
        review_scope=ProviderInvocationDenialReviewScope.FUTURE_EXTERNAL_SECURITY_REVIEW_GATE,
        reviewed_at="2026-01-01T00:00:00Z",
        ttl_seconds=31536000,
        evaluated_at="2026-01-02T00:00:00Z",
    )
    return chain, readiness, preflight, receipt


def _packet(**kwargs):
    chain, readiness, preflight, receipt = _clean_artifacts()
    return build_external_security_review_packet(
        kwargs.pop("receipt", receipt),
        readiness_manifest=kwargs.pop("readiness", readiness),
        readiness_preflight=kwargs.pop("preflight", preflight),
        capability_manifest=kwargs.pop("capability", chain["capability_manifest"]),
        credential_custody_manifest=kwargs.pop("credential", chain["credential_custody_manifest"]),
        endpoint_custody_manifest=kwargs.pop("endpoint", chain["endpoint_custody_manifest"]),
        client_custody_manifest=kwargs.pop("client", chain["client_custody_manifest"]),
        reviewer_packet_ref=kwargs.pop("reviewer_packet_ref", "review-packet-97"),
        **kwargs,
    )


def _codes(packet):
    return set(packet.findings) | {summary.code for summary in packet.finding_summaries} | set(explain_external_security_review_packet_findings(packet))


def test_clean_phase96_denial_review_builds_ready_metadata_packet():
    packet = _packet()
    assert packet.packet_status == ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_READY_WITH_CONDITIONS
    assert external_security_review_packet_ready_for_review(packet)
    assert summarize_external_security_review_packet(packet)["provider_invocation_forbidden"] is True
    assert not validate_external_security_review_packet(packet)


@pytest.mark.parametrize(
    "scope, expected",
    [
        (ExternalSecurityReviewScope.EXTERNAL_SECURITY_REVIEW_METADATA_PACKET, {ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_READY, ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_READY_WITH_CONDITIONS}),
        (ExternalSecurityReviewScope.INVOCATION_DENIAL_AUDIT_PACKET, {ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_READY_WITH_CONDITIONS}),
        (ExternalSecurityReviewScope.INTERNAL_SECURITY_REVIEW_PACKET, {ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_READY, ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_READY_WITH_CONDITIONS}),
    ],
)
def test_allowed_metadata_only_scopes_are_reviewable(scope, expected):
    packet = _packet(review_scope=scope)
    assert packet.packet_status in expected
    assert external_security_review_packet_ready_for_review(packet)


@pytest.mark.parametrize(
    "scope",
    [
        ExternalSecurityReviewScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
        ExternalSecurityReviewScope.PROVIDER_SUBMISSION_FORBIDDEN,
        ExternalSecurityReviewScope.NETWORK_EGRESS_FORBIDDEN,
        ExternalSecurityReviewScope.TOOL_OR_ACTION_FORBIDDEN,
        "unknown_scope",
    ],
)
def test_forbidden_or_unknown_scopes_block(scope):
    packet = _packet(review_scope=scope)
    assert packet.packet_status == ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_BLOCKED
    assert not external_security_review_packet_ready_for_review(packet)


def test_missing_denial_review_yields_missing_denial_review():
    packet = build_external_security_review_packet(None, review_scope=ExternalSecurityReviewScope.EXTERNAL_SECURITY_REVIEW_METADATA_PACKET, reviewer_packet_ref="review")
    assert packet.packet_status == ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_MISSING_DENIAL_REVIEW


@pytest.mark.parametrize(
    "status",
    [
        ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_REJECTED,
        ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_EXPIRED,
        ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_INVALID,
    ],
)
def test_rejected_expired_or_invalid_denial_review_blocks(status):
    chain, readiness, preflight, receipt = _clean_artifacts()
    broken = replace(receipt, review_status=status, expired=status == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_EXPIRED)
    packet = _packet(receipt=broken, readiness=readiness, preflight=preflight, capability=chain["capability_manifest"])
    assert packet.packet_status == ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_INVALID_INPUT
    assert not external_security_review_packet_ready_for_review(packet)


def test_forbidden_override_denial_review_blocks():
    _, _, _, receipt = _clean_artifacts()
    broken = replace(receipt, forbidden_invocation_override_attempted=True, review_status=ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_FORBIDDEN_INVOCATION_OVERRIDE_ATTEMPTED)
    packet = _packet(receipt=broken)
    assert packet.packet_status == ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_INVOCATION_OVERRIDE_DETECTED


def test_denial_review_that_does_not_affirm_forbidden_invocation_blocks():
    _, _, _, receipt = _clean_artifacts()
    broken = replace(receipt, decision=ProviderInvocationDenialReviewDecision.NO_DECISION)
    packet = _packet(receipt=broken)
    assert packet.packet_status == ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_DENIAL_NOT_AFFIRMED


@pytest.mark.parametrize(
    "flag, expected",
    [
        ("credential_use_allowed", ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_SENSITIVE_MATERIAL_DETECTED),
        ("endpoint_use_allowed", ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_SENSITIVE_MATERIAL_DETECTED),
        ("client_use_allowed", ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_SENSITIVE_MATERIAL_DETECTED),
        ("network_access_allowed", ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_SENSITIVE_MATERIAL_DETECTED),
        ("action_execution_allowed", ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_RUNTIME_AUTHORITY_DETECTED),
    ],
)
def test_denial_review_allowance_flags_block(flag, expected):
    _, _, _, receipt = _clean_artifacts()
    broken = replace(receipt, **{flag: True})
    packet = _packet(receipt=broken)
    assert packet.packet_status in {expected, ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_INVOCATION_OVERRIDE_DETECTED}
    assert not external_security_review_packet_ready_for_review(packet)


@pytest.mark.parametrize(
    "marker, category",
    [
        ("prompt_text", "prompt_text"),
        ("internal_candidate_text", "prompt_text"),
        ("synthetic_prompt_text", "prompt_text"),
        ("dry_run_prompt_text", "prompt_text"),
        ("final_prompt_text assembled_prompt system_prompt developer_prompt", "prompt_text"),
        ("chain_of_thought scratchpad hidden reasoning", "hidden_chain_of_thought"),
        ("api_key bearer token secret password private_key authorization", "secrets"),
        ("https://example.invalid endpoint base_url host port DNS resolve", "endpoints"),
        ("client session transport stream retry request builder SDK OpenAI Anthropic", "clients"),
        ("network handle socket http client stream handle", "network_handles"),
        ("runtime handle raw_payload action retention routing memory write", "runtime_handles"),
        ("provider params model params llm params", "provider_params"),
        ("tool schema function call", "tool_schemas"),
        ("invoke send_to_provider chat.completions completion", "provider_invocation"),
    ],
)
def test_sensitive_runtime_prompt_provider_markers_fail_closed_and_redact(marker, category):
    packet = _packet(reviewer_packet_ref=f"review {marker}")
    assert packet.packet_status in {
        ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_SENSITIVE_MATERIAL_DETECTED,
        ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_RUNTIME_AUTHORITY_DETECTED,
    }
    assert f"redacted:{category}" in _codes(packet) or any(code.startswith(f"sensitive_marker_redacted:{category}") for code in _codes(packet))
    assert not external_security_review_packet_ready_for_review(packet)


def test_evidence_links_include_ids_and_digests_only_without_artifact_bodies():
    packet = _packet()
    assert packet.evidence_links
    for link in packet.evidence_links:
        data = asdict(link)
        assert set(data) == {"artifact_kind", "artifact_id", "artifact_status", "artifact_digest", "included", "redacted", "reason_code"}
        assert link.artifact_digest.startswith("sha256:")
        assert "body" not in data and "payload" not in data


def test_clean_packet_exclusion_flags_and_predicates_remain_true():
    packet = _packet()
    assert packet.no_prompt_text and external_security_review_packet_contains_no_prompt_text(packet)
    assert packet.no_hidden_chain_of_thought and not packet.hidden_chain_of_thought_included
    assert external_security_review_packet_contains_no_secrets(packet)
    assert external_security_review_packet_contains_no_endpoints(packet)
    assert external_security_review_packet_contains_no_clients(packet)
    assert external_security_review_packet_contains_no_network_handles(packet)
    assert external_security_review_packet_contains_no_runtime_authority(packet)
    assert external_security_review_packet_is_metadata_only(packet)
    assert external_security_review_packet_preserves_invocation_denial(packet)
    assert all(
        getattr(packet, field) is False
        for field in (
            "invocation_allowed",
            "provider_send_allowed",
            "network_allowed",
            "credential_use_allowed",
            "endpoint_use_allowed",
            "client_use_allowed",
            "provider_sdk_allowed",
            "semantic_generation_allowed",
            "tool_calls_allowed",
            "memory_retrieval_allowed",
            "memory_write_allowed",
            "retention_allowed",
            "action_execution_allowed",
            "routing_allowed",
        )
    )


def test_predicates_are_false_for_dirty_packet():
    dirty = _packet(reviewer_packet_ref="prompt_text api_key https://example.invalid client socket runtime handle")
    assert not external_security_review_packet_is_metadata_only(dirty)
    assert not external_security_review_packet_contains_no_prompt_text(dirty)
    assert not external_security_review_packet_contains_no_secrets(dirty)
    assert not external_security_review_packet_contains_no_endpoints(dirty)
    assert not external_security_review_packet_contains_no_clients(dirty)
    assert not external_security_review_packet_contains_no_network_handles(dirty)
    assert not external_security_review_packet_contains_no_runtime_authority(dirty)


def test_packet_digest_is_deterministic_and_changes_for_stable_metadata_changes():
    packet = _packet()
    assert compute_external_security_review_packet_digest(packet) == packet.external_review_packet_digest
    assert _packet().external_review_packet_digest == packet.external_review_packet_digest
    _, readiness, _, receipt = _clean_artifacts()
    variants = [
        _packet(receipt=replace(receipt, review_digest="sha256:" + "1" * 64)),
        _packet(readiness=replace(readiness, readiness_digest="sha256:" + "2" * 64)),
        replace(packet, evidence_links=packet.evidence_links[:-1]),
        replace(packet, finding_summaries=packet.finding_summaries + (ExternalSecurityReviewFindingSummary(code="finding:extra", category="extra"),)),
        replace(packet, redaction_summary=replace(packet.redaction_summary, secrets_removed=1)),
        _packet(review_scope=ExternalSecurityReviewScope.INTERNAL_SECURITY_REVIEW_PACKET),
        _packet(reviewer_packet_ref="different-review-ref"),
        replace(packet, invocation_allowed=True),
        replace(packet, metadata_only=False),
    ]
    assert all(compute_external_security_review_packet_digest(variant) != packet.external_review_packet_digest for variant in variants)


def test_helper_does_not_mutate_denial_review_or_readiness_inputs():
    _, readiness, preflight, receipt = _clean_artifacts()
    before = (asdict(readiness), asdict(preflight), asdict(receipt))
    _packet(readiness=readiness, preflight=preflight, receipt=receipt)
    assert before == (asdict(readiness), asdict(preflight), asdict(receipt))


def test_module_does_not_call_prompt_provider_network_env_file_or_runtime_functions():
    tree = ast.parse((REPO_ROOT / MODULE_PATH).read_text(encoding="utf-8"))
    forbidden = {
        "assemble_prompt",
        "send_to_provider",
        "socket",
        "request",
        "urlopen",
        "getenv",
        "open",
        "resolve",
        "retrieve_memory",
        "write_memory",
        "execute_action",
        "commit_retention",
        "route_work",
        "admit_work",
        "create_client",
        "create_session",
        "create_transport",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            assert name not in forbidden


def test_phase90_through_phase96_posture_remains_forbidden_after_phase97_checks():
    chain, readiness, preflight, receipt = _clean_artifacts()
    packet = _packet()
    assert external_security_review_packet_ready_for_review(packet)
    assert provider_transport_registry_is_null_only(chain["registry_manifest"])
    dirty_capability = build_provider_transport_capability_manifest(declared_capabilities=[ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_HTTP], http_capable=True)
    dirty_registration = evaluate_provider_transport_registration_preflight(dirty_capability, chain["registry_manifest"], requested_adapter_kind="provider_transport_http_adapter", requested_registration=True)
    assert dirty_registration.registration_status == ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_FORBIDDEN_REAL_TRANSPORT
    assert provider_transport_registration_preflight_denies_real_transport(dirty_registration)
    assert provider_credential_custody_contains_no_secrets(chain["credential_custody_manifest"])
    assert provider_endpoint_custody_contains_no_endpoints(chain["endpoint_custody_manifest"])
    assert provider_client_custody_contains_no_clients(chain["client_custody_manifest"])
    assert provider_invocation_readiness_forbids_invocation(readiness)
    assert provider_invocation_preflight_remains_metadata_only(preflight)
    assert provider_invocation_denial_review_remains_metadata_only(receipt)
    assert provider_invocation_denial_review_approves_future_external_security_review_gate(receipt)


def test_embodiment_and_blocked_candidate_paths_do_not_enable_external_invocation():
    candidates = build_embodiment_context_candidates([
        {
            "ref_id": "camera-proposal",
            "source_kind": "embodiment_summary",
            "content_summary": "sanitized posture summary",
            "privacy_tags": ("sanitized",),
            "freshness_status": "fresh",
            "contradiction_status": "none",
            "provenance_status": "complete",
            "already_sanitized_context_summary": True,
        }
    ])
    packet = build_context_packet_from_candidates(candidates, packet_scope="phase97", conversation_scope_id="conv", task_scope_id="task")
    assert packet.included_embodiment_refs or packet.excluded_refs
    blocked = ContextCandidate(
        ref_id="blocked-provider-attempt",
        ref_type="memory",
        summary="blocked attempted candidate",
        provenance_refs=("truth-ledger",),
        provenance_status="complete",
        freshness_status="fresh",
        contradiction_status="none",
        pollution_risk="blocked",
        truth_ingress_status="blocked",
        already_sanitized_context_summary=True,
    )
    blocked_packet = build_context_packet_from_candidates([blocked], packet_scope="phase97", conversation_scope_id="conv", task_scope_id="task")
    assert blocked_packet.excluded_refs
    review = _packet()
    assert external_security_review_packet_ready_for_review(review)
    assert review.invocation_allowed is False and review.provider_send_allowed is False


def test_phase75_guardrail_scans_new_module_cleanly():
    report = guardrails.scan_context_hygiene_prompt_boundaries([REPO_ROOT / MODULE_PATH])
    assert report.ok, report.to_dict()


def test_default_guardrail_targets_include_new_module():
    assert MODULE_PATH in guardrails.DEFAULT_SCAN_TARGETS
