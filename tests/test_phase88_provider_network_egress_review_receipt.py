"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import importlib
import sys
import types
from pathlib import Path

# Keep privilege imports side-effect-safe under the repo's test ritual.
tts_stub = types.ModuleType("tts_bridge")
tts_stub.speak = lambda *args, **kwargs: None
sys.modules.setdefault("tts_bridge", tts_stub)

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from sentientos.context_hygiene.prompt_network_egress_preflight import (
    ProviderNetworkEgressPreflightRing,
    ProviderNetworkEgressPreflightStatus,
    build_provider_network_egress_preflight,
    compute_provider_network_egress_preflight_digest,
)
from sentientos.context_hygiene.prompt_network_egress_review import (
    ProviderNetworkEgressReviewDecision,
    ProviderNetworkEgressReviewScope,
    ProviderNetworkEgressReviewStatus,
    build_provider_network_egress_review_receipt,
    build_provider_network_egress_review_receipt_from_preflight,
    compute_provider_network_egress_review_digest,
    explain_provider_network_egress_review_findings,
    extract_required_provider_network_egress_review_mitigation_codes,
    provider_network_egress_review_approves_future_dry_run_gate,
    provider_network_egress_review_approves_future_null_transport_gate,
    provider_network_egress_review_approves_future_review_gate,
    provider_network_egress_review_attempts_forbidden_network_override,
    provider_network_egress_review_denies_network,
    provider_network_egress_review_has_no_credentials,
    provider_network_egress_review_has_no_runtime_authority,
    provider_network_egress_review_preserves_network_forbidden,
    provider_network_egress_review_preserves_provider_forbidden,
    provider_network_egress_review_satisfies_preflight,
    summarize_provider_network_egress_review_receipt,
    validate_provider_network_egress_review_receipt,
)
from scripts.verify_context_hygiene_prompt_boundaries import scan_context_hygiene_prompt_boundaries
from tests.test_phase84_provider_dry_run_request_envelope import _envelope
from tests.test_phase85_provider_dry_run_egress_review_receipt import _review
from tests.test_phase86_provider_simulation_result_envelope import _simulation
from tests.test_phase87_provider_simulation_network_egress_preflight import _preflight

REPO_ROOT = Path(__file__).resolve().parents[1]
READY = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_FOR_REVIEW
WARN = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_WITH_WARNINGS
REVIEW = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_REVIEW_REQUIRED
DENIED = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_DENIED
INVALID = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_INVALID_INPUT
DRY_INVALID = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_DRY_RUN_INVALID
REVIEW_INVALID = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_REVIEW_INVALID
SIM_INVALID = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_SIMULATION_INVALID
CREDS = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_CREDENTIALS_DETECTED
NETWORK = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_NETWORK_FORBIDDEN
RUNTIME = ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED
APPROVED = ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_APPROVED
CONSTRAINED = ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_APPROVED_WITH_CONSTRAINTS
REJECTED = ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_REJECTED
EXPIRED = ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_EXPIRED
INVALID_REVIEW = ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_INVALID
OVERRIDE = ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_FORBIDDEN_NETWORK_OVERRIDE_ATTEMPTED


def _required(preflight):
    return extract_required_provider_network_egress_review_mitigation_codes(preflight)


def _receipt(preflight=None, **overrides):
    preflight = preflight if preflight is not None else _preflight()
    required = _required(preflight)
    kwargs = {
        "reviewer_ref": "reviewer:phase88",
        "decision": ProviderNetworkEgressReviewDecision.APPROVE_FUTURE_NETWORK_EGRESS_REVIEW_GATE,
        "review_scope": ProviderNetworkEgressReviewScope.FUTURE_NETWORK_EGRESS_REVIEW_GATE,
        "approved_constraint_codes": required,
        "accepted_mitigation_codes": required,
    }
    kwargs.update(overrides)
    return build_provider_network_egress_review_receipt(preflight, **kwargs)


def _codes(receipt):
    return {finding.code for finding in receipt.findings}


def _with_digest(preflight, **overrides):
    changed = replace(preflight, **overrides)
    return replace(changed, preflight_digest=compute_provider_network_egress_preflight_digest(changed))


def test_receipt_can_be_built_from_ready_phase87_preflight_and_validates():
    preflight = _preflight()
    receipt = build_provider_network_egress_review_receipt_from_preflight(
        preflight,
        reviewer_ref="reviewer:phase88",
        decision=ProviderNetworkEgressReviewDecision.APPROVE_FUTURE_NETWORK_EGRESS_REVIEW_GATE,
        review_scope=ProviderNetworkEgressReviewScope.FUTURE_NETWORK_EGRESS_REVIEW_GATE,
        approved_constraint_codes=_required(preflight),
        accepted_mitigation_codes=_required(preflight),
    )
    assert receipt.review_status == APPROVED
    assert receipt.network_preflight_id == preflight.preflight_id
    assert receipt.network_preflight_digest == preflight.preflight_digest
    assert validate_provider_network_egress_review_receipt(receipt) == ()
    assert summarize_provider_network_egress_review_receipt(receipt)["review_status"] == APPROVED
    assert provider_network_egress_review_satisfies_preflight(preflight, receipt)


def test_future_gate_status_scope_helpers_and_reject_request_more_evidence():
    preflight = _preflight()
    approved = _receipt(preflight)
    dry = _receipt(preflight, decision=ProviderNetworkEgressReviewDecision.APPROVE_FUTURE_PROVIDER_CALL_DRY_RUN_GATE, review_scope=ProviderNetworkEgressReviewScope.FUTURE_PROVIDER_CALL_DRY_RUN_GATE)
    null = _receipt(preflight, decision=ProviderNetworkEgressReviewDecision.APPROVE_FUTURE_TRANSPORT_NULL_ADAPTER_GATE, review_scope=ProviderNetworkEgressReviewScope.FUTURE_TRANSPORT_NULL_ADAPTER_GATE)
    rejected = _receipt(preflight, decision=ProviderNetworkEgressReviewDecision.REJECT_NETWORK_EGRESS_PREFLIGHT, accepted_mitigation_codes=())
    more = _receipt(preflight, decision=ProviderNetworkEgressReviewDecision.REQUEST_MORE_EVIDENCE, accepted_mitigation_codes=())
    assert approved.review_status == APPROVED and provider_network_egress_review_approves_future_review_gate(approved)
    assert dry.review_status == CONSTRAINED and provider_network_egress_review_approves_future_dry_run_gate(dry)
    assert null.review_status == CONSTRAINED and provider_network_egress_review_approves_future_null_transport_gate(null)
    assert rejected.review_status == REJECTED
    assert more.review_status == REJECTED
    assert not provider_network_egress_review_satisfies_preflight(preflight, rejected)


def test_missing_reviewer_expired_preflight_digest_mismatch_and_id_mismatch_do_not_satisfy():
    preflight = _preflight()
    missing_reviewer = _receipt(preflight, reviewer_ref="")
    expired = _receipt(preflight, expires_at="2026-05-09T00:00:00Z", evaluated_at="2026-05-09T00:00:00Z")
    digest_mismatch = replace(_receipt(preflight), network_preflight_digest="digest:mismatch")
    digest_mismatch = replace(digest_mismatch, review_digest=compute_provider_network_egress_review_digest(digest_mismatch))
    id_mismatch = replace(_receipt(preflight), network_preflight_id="preflight:mismatch")
    id_mismatch = replace(id_mismatch, review_digest=compute_provider_network_egress_review_digest(id_mismatch))
    assert missing_reviewer.review_status == INVALID_REVIEW
    assert expired.review_status == EXPIRED
    assert not provider_network_egress_review_satisfies_preflight(preflight, expired)
    assert not provider_network_egress_review_satisfies_preflight(preflight, digest_mismatch)
    assert not provider_network_egress_review_satisfies_preflight(preflight, id_mismatch)


def test_hard_denial_preflight_statuses_are_forbidden_override_attempts_and_do_not_satisfy():
    cases = [DENIED, INVALID, DRY_INVALID, REVIEW_INVALID, SIM_INVALID, CREDS, NETWORK, RUNTIME]
    for status in cases:
        preflight = _with_digest(_preflight(), preflight_status=status)
        receipt = _receipt(preflight)
        assert receipt.review_status == OVERRIDE
        assert provider_network_egress_review_attempts_forbidden_network_override(receipt)
        assert not provider_network_egress_review_satisfies_preflight(preflight, receipt)
    denied = _preflight(feature_flag_state={})
    assert _receipt(denied).review_status == OVERRIDE


def test_live_ring_and_forbidden_scopes_are_non_overridable():
    live = _preflight(requested_ring=ProviderNetworkEgressPreflightRing.LIVE_PROVIDER_SEND_FORBIDDEN)
    assert _receipt(live).review_status == OVERRIDE
    for scope in (
        ProviderNetworkEgressReviewScope.ACTUAL_NETWORK_EGRESS_FORBIDDEN,
        ProviderNetworkEgressReviewScope.ACTUAL_PROVIDER_SEND_FORBIDDEN,
        ProviderNetworkEgressReviewScope.CREDENTIAL_USE_FORBIDDEN,
        ProviderNetworkEgressReviewScope.PROVIDER_CLIENT_USE_FORBIDDEN,
        ProviderNetworkEgressReviewScope.ENDPOINT_USE_FORBIDDEN,
        ProviderNetworkEgressReviewScope.TOOL_OR_ACTION_FORBIDDEN,
        ProviderNetworkEgressReviewScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
    ):
        receipt = _receipt(review_scope=scope)
        assert receipt.review_status == OVERRIDE
        assert "review_scope_non_overridable" in _codes(receipt)


def test_forbidden_allowances_are_recorded_and_non_overridable():
    allowances = [
        "network_egress_allowed", "provider_send_allowed", "credentials_allowed", "provider_client_allowed", "endpoint_allowed",
        "llm_call_allowed", "semantic_generation_allowed", "tool_calls_allowed", "memory_retrieval_allowed", "memory_write_allowed",
        "retention_allowed", "action_execution_allowed", "routing_allowed",
    ]
    for allowance in allowances:
        receipt = _receipt(**{allowance: True})
        assert receipt.review_status == OVERRIDE
        assert provider_network_egress_review_attempts_forbidden_network_override(receipt)
        assert "forbidden_allowance_requested" in _codes(receipt)


def test_missing_preflight_digest_evidence_linkage_yields_invalid_or_forbidden_finding():
    preflight = replace(_preflight(), preflight_digest="")
    receipt = _receipt(preflight)
    assert receipt.review_status in {INVALID_REVIEW, OVERRIDE}
    assert "linked_digest_missing" in _codes(receipt) or "digest_chain_incomplete_non_overridable" in _codes(receipt)


def test_required_mitigations_must_be_accepted_and_rejected_required_mitigation_prevents_satisfaction():
    preflight = _preflight(requested_ring=ProviderNetworkEgressPreflightRing.FUTURE_PROVIDER_CALL_DRY_RUN_GATE)
    required = _required(preflight)
    unaccepted = _receipt(preflight, accepted_mitigation_codes=(), approved_constraint_codes=())
    rejected = _receipt(preflight, rejected_mitigation_codes=(required[0],))
    accepted = _receipt(preflight, accepted_mitigation_codes=required, approved_constraint_codes=required)
    assert required
    assert not provider_network_egress_review_satisfies_preflight(preflight, unaccepted)
    assert not provider_network_egress_review_satisfies_preflight(preflight, rejected)
    assert provider_network_egress_review_satisfies_preflight(preflight, accepted)


def test_constraint_codes_are_recorded_and_markers_remain_forbidden():
    receipt = _receipt(approved_constraint_codes=("constraint:a",), rejected_constraint_codes=("constraint:b",), accepted_mitigation_codes=_required(_preflight()) + ("constraint:a",))
    assert receipt.approved_constraint_codes == ("constraint:a",)
    assert receipt.rejected_constraint_codes == ("constraint:b",)
    assert provider_network_egress_review_preserves_network_forbidden(receipt)
    assert provider_network_egress_review_preserves_provider_forbidden(receipt)
    assert provider_network_egress_review_has_no_credentials(receipt)
    assert provider_network_egress_review_has_no_runtime_authority(receipt)
    assert provider_network_egress_review_denies_network(receipt)
    for field in (
        "network_egress_allowed", "provider_send_allowed", "credentials_allowed", "provider_client_allowed", "endpoint_allowed", "llm_call_allowed",
        "semantic_generation_allowed", "tool_calls_allowed", "memory_retrieval_allowed", "memory_write_allowed", "retention_allowed", "action_execution_allowed", "routing_allowed",
    ):
        assert getattr(receipt, field) is False
    for marker in (
        "network_egress_review_receipt_only", "future_network_gate_review_only", "network_egress_forbidden", "provider_send_forbidden", "credentials_forbidden",
        "provider_client_forbidden", "endpoint_forbidden", "llm_call_forbidden", "semantic_generation_forbidden", "does_not_make_network_calls", "does_not_call_llm",
        "does_not_send_to_provider", "does_not_retrieve_memory", "does_not_write_memory", "does_not_trigger_feedback", "does_not_commit_retention", "does_not_execute_or_route_work", "does_not_admit_work",
    ):
        assert getattr(receipt, marker) is True


def test_review_digest_is_deterministic_and_changes_for_required_metadata_fields():
    preflight = _preflight()
    base = _receipt(preflight)
    assert base.review_digest == compute_provider_network_egress_review_digest(base)
    assert _receipt(preflight).review_digest == base.review_digest
    changed_preflight = _with_digest(preflight, rationale="changed rationale")
    assert _receipt(changed_preflight).review_digest != base.review_digest
    assert _receipt(preflight, reviewer_ref="reviewer:other").review_digest != base.review_digest
    assert _receipt(preflight, decision=ProviderNetworkEgressReviewDecision.APPROVE_FUTURE_PROVIDER_CALL_DRY_RUN_GATE, review_scope=ProviderNetworkEgressReviewScope.FUTURE_PROVIDER_CALL_DRY_RUN_GATE).review_digest != base.review_digest
    assert _receipt(preflight, review_scope=ProviderNetworkEgressReviewScope.FUTURE_TRANSPORT_NULL_ADAPTER_GATE).review_digest != base.review_digest
    assert _receipt(preflight, accepted_mitigation_codes=(_required(preflight)[0],)).review_digest != base.review_digest
    assert _receipt(preflight, rejected_mitigation_codes=("mitigate:x",)).review_digest != base.review_digest
    assert _receipt(preflight, expires_at="2099-01-01T00:00:00Z").review_digest != base.review_digest
    assert _receipt(preflight, rationale="operator rationale").review_digest != base.review_digest
    assert _receipt(preflight, network_egress_allowed=True).review_digest != base.review_digest


def test_satisfaction_helper_true_only_for_matching_unexpired_approved_or_constrained_ready_preflights_and_does_not_mutate():
    for preflight in (_preflight(), _preflight(requested_ring=ProviderNetworkEgressPreflightRing.FUTURE_NETWORK_EGRESS_REVIEW_GATE), _preflight(requested_ring=ProviderNetworkEgressPreflightRing.FUTURE_PROVIDER_CALL_DRY_RUN_GATE)):
        before = deepcopy(preflight)
        receipt = _receipt(preflight, accepted_mitigation_codes=_required(preflight), approved_constraint_codes=_required(preflight))
        assert preflight.preflight_status in {READY, WARN, REVIEW}
        assert provider_network_egress_review_satisfies_preflight(preflight, receipt)
        assert preflight == before
    assert not provider_network_egress_review_satisfies_preflight(_with_digest(_preflight(), preflight_status=DENIED), _receipt(_with_digest(_preflight(), preflight_status=DENIED)))


def test_helper_does_not_call_prompt_provider_network_memory_action_retention_or_runtime_functions(monkeypatch):
    import sentientos.context_hygiene.prompt_network_egress_review as module

    forbidden = [
        "assemble_prompt", "retrieve_memory", "write_memory", "commit_retention", "execute_action", "route_work", "admit_work",
        "provider_create", "llm_invoke", "network_send", "runtime_execute",
    ]
    for name in forbidden:
        monkeypatch.setattr(module, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError(name)), raising=False)
    preflight = _preflight()
    assert provider_network_egress_review_satisfies_preflight(preflight, _receipt(preflight))


def test_phase63_to_phase88_happy_path_and_blocked_attempted_candidate_denial_override():
    envelope = _envelope()
    review = _review(envelope)
    simulation = _simulation(envelope, review)
    preflight = build_provider_network_egress_preflight(envelope, review, simulation, requested_ring=ProviderNetworkEgressPreflightRing.FUTURE_PROVIDER_CALL_DRY_RUN_GATE, feature_flag_state={"network_egress_preflight": True})
    receipt = _receipt(preflight)
    assert provider_network_egress_review_satisfies_preflight(preflight, receipt)

    blocked = _preflight(marker_evidence={"raw" + "_payload": "attempted blocked candidate"})
    blocked_receipt = _receipt(blocked)
    assert blocked.preflight_status == RUNTIME
    assert blocked_receipt.review_status == OVERRIDE


def test_adversarial_provider_runtime_markers_remain_non_overridable():
    cases = [
        {"provider" + "_client": "present"},
        {"transport" + "_object": "present"},
        {"request" + "_handle": "present"},
        {"response" + "_handle": "present"},
        {"api" + "_key": "present"},
        {"end" + "point": "present"},
        {"tool" + "_call": "present"},
        {"memory" + "_handle": "present"},
        {"retention" + "_handle": "present"},
        {"routing" + "_handle": "present"},
        {"provider" + "_params": "present"},
    ]
    for evidence in cases:
        preflight = _preflight(marker_evidence=evidence)
        receipt = _receipt(preflight)
        assert preflight.preflight_status in {NETWORK, CREDS, RUNTIME}
        assert receipt.review_status == OVERRIDE


def test_phase75_guardrail_scans_new_module_and_import_purity_is_side_effect_safe():
    report = scan_context_hygiene_prompt_boundaries(["sentientos/context_hygiene/prompt_network_egress_review.py"], repo_root=REPO_ROOT)
    assert report.ok
    module = importlib.import_module("sentientos.context_hygiene.prompt_network_egress_review")
    assert module.ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_APPROVED == APPROVED
    assert explain_provider_network_egress_review_findings(_receipt()) == ()
