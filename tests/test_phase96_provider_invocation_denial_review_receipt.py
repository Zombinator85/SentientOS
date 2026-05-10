from __future__ import annotations

from dataclasses import replace
import ast
from pathlib import Path

import pytest

from scripts import verify_context_hygiene_prompt_boundaries as guardrails
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
    build_provider_invocation_denial_review_receipt_from_preflight,
    compute_provider_invocation_denial_review_digest,
    explain_provider_invocation_denial_review_findings,
    provider_invocation_denial_review_affirms_forbidden_invocation,
    provider_invocation_denial_review_approves_future_denial_audit_gate,
    provider_invocation_denial_review_approves_future_external_security_review_gate,
    provider_invocation_denial_review_attempts_forbidden_invocation_override,
    provider_invocation_denial_review_has_no_clients,
    provider_invocation_denial_review_has_no_credentials,
    provider_invocation_denial_review_has_no_endpoints,
    provider_invocation_denial_review_has_no_network,
    provider_invocation_denial_review_has_no_runtime_authority,
    provider_invocation_denial_review_remains_metadata_only,
    provider_invocation_denial_review_satisfies_readiness_preflight,
    summarize_provider_invocation_denial_review_receipt,
    validate_provider_invocation_denial_review_receipt,
)
from sentientos.context_hygiene.prompt_provider_invocation_readiness import (
    ProviderInvocationPreflightStatus,
    ProviderInvocationReadinessStatus,
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
from sentientos.context_hygiene.embodiment_context import build_embodiment_context_candidates


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = "sentientos/context_hygiene/prompt_provider_invocation_denial_review.py"


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
        "capability_manifest": capability,
        "registration_preflight": registration,
        "credential_custody_manifest": credential,
        "credential_custody_preflight": credential_preflight,
        "endpoint_custody_manifest": endpoint,
        "endpoint_custody_preflight": endpoint_preflight,
        "client_custody_manifest": client,
        "client_custody_preflight": client_preflight,
        "registry_manifest": registry,
    }


def _manifest(**kwargs):
    chain = _chain(**{key: value for key, value in kwargs.items() if key in {"registry", "capability", "registration", "credential", "credential_preflight", "endpoint", "endpoint_preflight", "client", "client_preflight"}})
    chain.update({key: value for key, value in kwargs.items() if key not in {"registry", "capability", "registration", "credential", "credential_preflight", "endpoint", "endpoint_preflight", "client", "client_preflight"}})
    return build_provider_invocation_readiness_manifest(**chain)


def _clean_pair():
    readiness = _manifest()
    preflight = evaluate_provider_invocation_readiness_preflight(readiness)
    return readiness, preflight


def _receipt(**kwargs):
    readiness, preflight = kwargs.pop("pair", _clean_pair())
    return build_provider_invocation_denial_review_receipt(
        readiness,
        preflight,
        reviewer_ref=kwargs.pop("reviewer_ref", "auditor:phase96"),
        decision=kwargs.pop("decision", ProviderInvocationDenialReviewDecision.AFFIRM_INVOCATION_FORBIDDEN),
        review_scope=kwargs.pop("review_scope", ProviderInvocationDenialReviewScope.INVOCATION_DENIAL_REVIEW_GATE),
        **kwargs,
    )


def _codes(receipt):
    return {finding.code for finding in receipt.findings}


def test_receipt_can_be_built_from_clean_phase95_readiness_preflight():
    readiness, preflight = _clean_pair()
    receipt = build_provider_invocation_denial_review_receipt_from_preflight(preflight, readiness=readiness, reviewer_ref="auditor:phase96", decision=ProviderInvocationDenialReviewDecision.AFFIRM_INVOCATION_FORBIDDEN)
    assert receipt.readiness_id == readiness.invocation_readiness_id
    assert receipt.readiness_digest == readiness.readiness_digest
    assert receipt.readiness_preflight_id == preflight.invocation_preflight_id
    assert receipt.readiness_preflight_digest == preflight.invocation_preflight_digest
    assert receipt.review_status == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_ACCEPTED
    assert provider_invocation_denial_review_satisfies_readiness_preflight(readiness, preflight, receipt)


@pytest.mark.parametrize(
    "decision",
    [
        ProviderInvocationDenialReviewDecision.AFFIRM_INVOCATION_FORBIDDEN,
        ProviderInvocationDenialReviewDecision.AFFIRM_METADATA_ONLY_NOT_INVOCABLE,
    ],
)
def test_affirm_denial_decisions_yield_accepted(decision):
    receipt = _receipt(decision=decision)
    assert receipt.review_status == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_ACCEPTED
    assert provider_invocation_denial_review_affirms_forbidden_invocation(receipt)


def test_future_external_security_review_gate_yields_accepted_with_conditions():
    receipt = _receipt(decision=ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_EXTERNAL_SECURITY_REVIEW_GATE, review_scope=ProviderInvocationDenialReviewScope.FUTURE_EXTERNAL_SECURITY_REVIEW_GATE)
    assert receipt.review_status == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_ACCEPTED_WITH_CONDITIONS
    assert provider_invocation_denial_review_approves_future_external_security_review_gate(receipt)
    assert not provider_invocation_denial_review_approves_future_denial_audit_gate(receipt)


def test_future_invocation_denial_audit_gate_yields_accepted_with_conditions():
    receipt = _receipt(decision=ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_INVOCATION_DENIAL_AUDIT_GATE, review_scope=ProviderInvocationDenialReviewScope.FUTURE_INVOCATION_DENIAL_AUDIT_GATE)
    assert receipt.review_status == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_ACCEPTED_WITH_CONDITIONS
    assert provider_invocation_denial_review_approves_future_denial_audit_gate(receipt)
    assert not provider_invocation_denial_review_approves_future_external_security_review_gate(receipt)


@pytest.mark.parametrize(
    "decision",
    [ProviderInvocationDenialReviewDecision.REJECT_READINESS_POSTURE, ProviderInvocationDenialReviewDecision.REQUEST_MORE_EVIDENCE],
)
def test_reject_or_request_more_evidence_yields_rejected(decision):
    receipt = _receipt(decision=decision)
    assert receipt.review_status == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_REJECTED


def test_missing_reviewer_ref_yields_invalid():
    receipt = _receipt(reviewer_ref="")
    assert receipt.review_status == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_INVALID
    assert "reviewer_ref_missing" in _codes(receipt)


def test_expired_review_yields_expired():
    receipt = _receipt(reviewed_at="2025-01-01T00:00:00Z", ttl_seconds=1, evaluated_at="2025-01-01T00:00:01Z")
    assert receipt.expired is True
    assert receipt.review_status == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_EXPIRED


@pytest.mark.parametrize(
    "field,value",
    [
        ("readiness_digest", "sha256:bad"),
        ("readiness_preflight_digest", "sha256:bad"),
        ("readiness_id", "different"),
        ("readiness_preflight_id", "different"),
    ],
)
def test_linked_id_or_digest_mismatch_fails_satisfaction(field, value):
    readiness, preflight = _clean_pair()
    receipt = _receipt(pair=(readiness, preflight))
    broken = replace(receipt, **{field: value})
    assert not provider_invocation_denial_review_satisfies_readiness_preflight(readiness, preflight, broken)


def test_missing_digest_chain_yields_invalid_or_constrained_and_cannot_be_invocation_ready():
    chain = _chain()
    chain["client_custody_preflight"] = None
    readiness = build_provider_invocation_readiness_manifest(**chain)
    preflight = evaluate_provider_invocation_readiness_preflight(readiness)
    receipt = build_provider_invocation_denial_review_receipt(readiness, preflight, reviewer_ref="auditor", decision=ProviderInvocationDenialReviewDecision.AFFIRM_INVOCATION_FORBIDDEN)
    assert receipt.digest_chain_complete is False
    assert receipt.review_status in {
        ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_INVALID,
        ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_FORBIDDEN_INVOCATION_OVERRIDE_ATTEMPTED,
    }
    assert not provider_invocation_denial_review_satisfies_readiness_preflight(readiness, preflight, receipt)


@pytest.mark.parametrize(
    "scope",
    [
        ProviderInvocationDenialReviewScope.ACTUAL_PROVIDER_INVOCATION_FORBIDDEN,
        ProviderInvocationDenialReviewScope.ACTUAL_PROVIDER_SEND_FORBIDDEN,
        ProviderInvocationDenialReviewScope.NETWORK_EGRESS_FORBIDDEN,
        ProviderInvocationDenialReviewScope.CREDENTIAL_USE_FORBIDDEN,
        ProviderInvocationDenialReviewScope.ENDPOINT_USE_FORBIDDEN,
        ProviderInvocationDenialReviewScope.PROVIDER_CLIENT_USE_FORBIDDEN,
        ProviderInvocationDenialReviewScope.PROVIDER_SDK_USE_FORBIDDEN,
        ProviderInvocationDenialReviewScope.TOOL_OR_ACTION_FORBIDDEN,
        ProviderInvocationDenialReviewScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
    ],
)
def test_forbidden_scopes_trigger_forbidden_override(scope):
    receipt = _receipt(review_scope=scope)
    assert receipt.review_status == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_FORBIDDEN_INVOCATION_OVERRIDE_ATTEMPTED
    assert provider_invocation_denial_review_attempts_forbidden_invocation_override(receipt)


@pytest.mark.parametrize("flag", [
    "invocation_allowed", "provider_send_allowed", "credential_use_allowed", "endpoint_use_allowed", "client_use_allowed", "network_access_allowed", "dns_allowed", "socket_allowed", "http_allowed", "provider_sdk_allowed", "semantic_generation_allowed", "tool_calls_allowed", "memory_retrieval_allowed", "memory_write_allowed", "retention_allowed", "action_execution_allowed", "routing_allowed",
])
def test_any_runtime_or_provider_allowance_true_is_forbidden(flag):
    receipt = _receipt(**{flag: True})
    assert receipt.review_status == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_FORBIDDEN_INVOCATION_OVERRIDE_ATTEMPTED
    assert provider_invocation_denial_review_attempts_forbidden_invocation_override(receipt)
    assert "forbidden_allowance_requested" in _codes(receipt)


@pytest.mark.parametrize(
    "dirty_kwargs, expected_status",
    [
        ({"capability": build_provider_transport_capability_manifest(declared_capabilities=[ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_HTTP], http_capable=True)}, ProviderInvocationReadinessStatus.INVOCATION_READINESS_NETWORK_DETECTED),
        ({"credential": build_provider_credential_custody_manifest(secret_values_present=True)}, ProviderInvocationReadinessStatus.INVOCATION_READINESS_CREDENTIALS_DETECTED),
        ({"endpoint": build_provider_endpoint_custody_manifest(endpoint_values_present=True)}, ProviderInvocationReadinessStatus.INVOCATION_READINESS_ENDPOINT_DETECTED),
        ({"client": build_provider_client_custody_manifest(client_values_present=True)}, ProviderInvocationReadinessStatus.INVOCATION_READINESS_CLIENT_DETECTED),
    ],
)
def test_dirty_phase91_92_93_94_evidence_prevents_satisfaction(dirty_kwargs, expected_status):
    readiness = _manifest(**dirty_kwargs)
    preflight = evaluate_provider_invocation_readiness_preflight(readiness)
    receipt = build_provider_invocation_denial_review_receipt(readiness, preflight, reviewer_ref="auditor", decision=ProviderInvocationDenialReviewDecision.AFFIRM_INVOCATION_FORBIDDEN)
    assert readiness.readiness_status == expected_status
    assert provider_invocation_denial_review_attempts_forbidden_invocation_override(receipt)
    assert not provider_invocation_denial_review_satisfies_readiness_preflight(readiness, preflight, receipt)


def test_missing_required_gap_acceptance_and_rejected_required_code_prevent_satisfaction():
    chain = _chain()
    chain["client_custody_preflight"] = None
    readiness = build_provider_invocation_readiness_manifest(**chain)
    preflight = evaluate_provider_invocation_readiness_preflight(readiness)
    missing = build_provider_invocation_denial_review_receipt(readiness, preflight, reviewer_ref="auditor", decision=ProviderInvocationDenialReviewDecision.AFFIRM_INVOCATION_FORBIDDEN)
    assert "required_gap_code_not_accepted" in _codes(missing)
    accepted_gap_codes = tuple(f"gap:{gap.code}" for gap in readiness.readiness_gaps) + ("gap:missing_client_custody_preflight", "gap:digest_chain_incomplete")
    rejected = build_provider_invocation_denial_review_receipt(readiness, preflight, reviewer_ref="auditor", decision=ProviderInvocationDenialReviewDecision.AFFIRM_INVOCATION_FORBIDDEN, accepted_gap_codes=accepted_gap_codes, rejected_gap_codes=("gap:missing_client_custody_preflight",))
    assert "required_gap_code_rejected" in _codes(rejected)
    assert not provider_invocation_denial_review_satisfies_readiness_preflight(readiness, preflight, rejected)


def test_accepted_and_rejected_codes_are_recorded():
    receipt = _receipt(
        accepted_denial_codes=("denial:custom",),
        rejected_denial_codes=("denial:rejected",),
        accepted_gap_codes=("gap:accepted",),
        rejected_gap_codes=("gap:rejected",),
        approved_constraint_codes=("constraint:approved",),
        rejected_constraint_codes=("constraint:rejected",),
        decision=ProviderInvocationDenialReviewDecision.REJECT_READINESS_POSTURE,
    )
    assert "denial:custom" in receipt.accepted_denial_codes
    assert receipt.rejected_denial_codes == ("denial:rejected",)
    assert receipt.accepted_gap_codes == ("gap:accepted",)
    assert receipt.rejected_gap_codes == ("gap:rejected",)
    assert "constraint:approved" in receipt.approved_constraint_codes
    assert receipt.rejected_constraint_codes == ("constraint:rejected",)


def test_clean_helper_predicates_and_summary_are_true():
    receipt = _receipt()
    assert provider_invocation_denial_review_affirms_forbidden_invocation(receipt)
    assert provider_invocation_denial_review_has_no_credentials(receipt)
    assert provider_invocation_denial_review_has_no_endpoints(receipt)
    assert provider_invocation_denial_review_has_no_clients(receipt)
    assert provider_invocation_denial_review_has_no_network(receipt)
    assert provider_invocation_denial_review_has_no_runtime_authority(receipt)
    assert provider_invocation_denial_review_remains_metadata_only(receipt)
    assert not provider_invocation_denial_review_attempts_forbidden_invocation_override(receipt)
    assert not validate_provider_invocation_denial_review_receipt(receipt)
    assert summarize_provider_invocation_denial_review_receipt(receipt)["provider_invocation_forbidden"] is True
    assert explain_provider_invocation_denial_review_findings(receipt) == ()


def test_review_digest_is_deterministic_and_changes_for_stable_metadata_changes():
    readiness, preflight = _clean_pair()
    base = _receipt(pair=(readiness, preflight), reviewed_at="2025-01-01T00:00:00Z")
    same = _receipt(pair=(readiness, preflight), reviewed_at="2025-01-01T00:00:00Z")
    assert base.review_digest == same.review_digest
    assert compute_provider_invocation_denial_review_digest(base) == base.review_digest
    variants = [
        replace(base, readiness_digest="sha256:other"),
        replace(base, readiness_preflight_digest="sha256:other"),
        _receipt(pair=(readiness, preflight), reviewer_ref="auditor:other", reviewed_at="2025-01-01T00:00:00Z"),
        _receipt(pair=(readiness, preflight), decision=ProviderInvocationDenialReviewDecision.AFFIRM_METADATA_ONLY_NOT_INVOCABLE, reviewed_at="2025-01-01T00:00:00Z"),
        _receipt(pair=(readiness, preflight), decision=ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_EXTERNAL_SECURITY_REVIEW_GATE, review_scope=ProviderInvocationDenialReviewScope.FUTURE_EXTERNAL_SECURITY_REVIEW_GATE, reviewed_at="2025-01-01T00:00:00Z"),
        _receipt(pair=(readiness, preflight), accepted_denial_codes=("denial:extra",), rejected_gap_codes=("gap:x",), reviewed_at="2025-01-01T00:00:00Z", decision=ProviderInvocationDenialReviewDecision.REJECT_READINESS_POSTURE),
        _receipt(pair=(readiness, preflight), reviewed_at="2025-01-01T00:00:00Z", expires_at="2025-02-01T00:00:00Z"),
        _receipt(pair=(readiness, preflight), invocation_allowed=True, reviewed_at="2025-01-01T00:00:00Z"),
    ]
    digests = {compute_provider_invocation_denial_review_digest(variant) for variant in variants}
    assert base.review_digest not in digests
    assert len(digests) == len(variants)


def test_helper_does_not_mutate_readiness_or_preflight():
    readiness, preflight = _clean_pair()
    before = (readiness, preflight)
    _ = build_provider_invocation_denial_review_receipt(readiness, preflight, reviewer_ref="auditor", decision=ProviderInvocationDenialReviewDecision.AFFIRM_INVOCATION_FORBIDDEN)
    assert (readiness, preflight) == before


def test_helper_source_does_not_call_forbidden_runtime_or_provider_surfaces():
    tree = ast.parse((REPO_ROOT / MODULE_PATH).read_text(encoding="utf-8"))
    calls = {ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    forbidden_fragments = ("assemble_prompt", "openai", "socket", "requests", "httpx", "resolve", "environ", "vault", "keychain", "retrieve_memory", "write_memory", "execute_action", "commit_retention", "route_work", "admit_work")
    assert not {call for call in calls if any(fragment in call for fragment in forbidden_fragments)}


def test_phase90_through_phase95_invariants_remain_after_phase96_checks():
    readiness, preflight = _clean_pair()
    receipt = _receipt(pair=(readiness, preflight))
    registry = build_provider_transport_registry_manifest()
    capability = build_provider_transport_capability_manifest(declared_capabilities=[ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_HTTP], http_capable=True)
    registration = evaluate_provider_transport_registration_preflight(capability, registry, requested_adapter_kind="provider_transport_http_adapter", requested_registration=True)
    credential = build_provider_credential_custody_manifest()
    endpoint = build_provider_endpoint_custody_manifest()
    client = build_provider_client_custody_manifest()
    assert provider_transport_registry_is_null_only(registry)
    assert registration.registration_status == ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_FORBIDDEN_REAL_TRANSPORT
    assert provider_transport_registration_preflight_denies_real_transport(registration)
    assert provider_credential_custody_contains_no_secrets(credential)
    assert provider_endpoint_custody_contains_no_endpoints(endpoint)
    assert provider_client_custody_contains_no_clients(client)
    assert readiness.readiness_status == ProviderInvocationReadinessStatus.INVOCATION_READINESS_NULL_ONLY_METADATA
    assert preflight.invocation_preflight_status == ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_METADATA_ONLY_NOT_INVOCABLE
    assert provider_invocation_preflight_remains_metadata_only(preflight)
    assert provider_invocation_denial_review_satisfies_readiness_preflight(readiness, preflight, receipt)


def test_phase63_and_phase62b_metadata_do_not_enable_invocation_approval():
    embodiment_candidates = build_embodiment_context_candidates([{"artifact_id": "avatar:local", "source_kind": "avatar_profile", "consent": "private_local", "sanitized": True}])
    packet = build_context_packet_from_candidates(embodiment_candidates, "local", "conversation", "task")
    blocked_packet = build_context_packet_from_candidates([
        ContextCandidate(ref_id="blocked", ref_type="claim", provenance_refs=("operator:note",), source_locator="fixture", truth_ingress_status="blocked", pollution_risk="blocked")
    ], "local", "conversation", "task")
    readiness, preflight = _clean_pair()
    receipt = _receipt(pair=(readiness, preflight), rationale="metadata review only")
    assert packet.context_packet_id
    assert blocked_packet.excluded_refs
    assert provider_invocation_denial_review_satisfies_readiness_preflight(readiness, preflight, receipt)
    forbidden = _receipt(pair=(readiness, preflight), rationale="provider invocation allowed")
    assert provider_invocation_denial_review_attempts_forbidden_invocation_override(forbidden)


def test_phase75_guardrail_scans_new_module_cleanly():
    report = guardrails.scan_context_hygiene_prompt_boundaries(paths=[MODULE_PATH], repo_root=REPO_ROOT)
    assert report.ok, guardrails.summarize_context_hygiene_prompt_boundary_scan(report)
    default_report = guardrails.scan_context_hygiene_prompt_boundaries(repo_root=REPO_ROOT)
    assert MODULE_PATH in default_report.scanned_paths
    assert default_report.ok, guardrails.summarize_context_hygiene_prompt_boundary_scan(default_report)
