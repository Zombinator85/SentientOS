"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import importlib
import sys
import types

# Keep privilege imports side-effect-safe under the repo's test ritual.
tts_stub = types.ModuleType("tts_bridge")
tts_stub.speak = lambda *args, **kwargs: None
sys.modules.setdefault("tts_bridge", tts_stub)

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from sentientos.context_hygiene.prompt_provider_dry_run import (
    ProviderDryRunModelFamily,
    ProviderDryRunProviderFamily,
    ProviderDryRunStatus,
    compute_provider_dry_run_digest,
)
from sentientos.context_hygiene.prompt_provider_dry_run_review import (
    ProviderDryRunEgressReviewDecision,
    ProviderDryRunEgressReviewScope,
    ProviderDryRunEgressReviewStatus,
    build_provider_dry_run_egress_review_receipt,
    build_provider_dry_run_egress_review_receipt_from_envelope,
    compute_provider_dry_run_egress_review_digest,
    explain_provider_dry_run_egress_review_findings,
    extract_required_provider_dry_run_egress_review_mitigation_codes,
    provider_dry_run_review_approves_future_egress_review_gate,
    provider_dry_run_review_approves_future_simulation_gate,
    provider_dry_run_review_attempts_forbidden_send_override,
    provider_dry_run_review_denies_send,
    provider_dry_run_review_preserves_non_sendable,
    provider_dry_run_review_satisfies_envelope,
    summarize_provider_dry_run_egress_review_receipt,
    validate_provider_dry_run_egress_review_receipt,
)
from scripts.verify_context_hygiene_prompt_boundaries import scan_context_hygiene_prompt_boundaries
from tests.test_phase84_provider_dry_run_request_envelope import _chain, _envelope

APPROVED = ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_APPROVED
CONSTRAINED = ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_APPROVED_WITH_CONSTRAINTS
REJECTED = ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_REJECTED
EXPIRED = ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_EXPIRED
INVALID = ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_INVALID
OVERRIDE = ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_FORBIDDEN_SEND_OVERRIDE_ATTEMPTED


def _required(envelope):
    return extract_required_provider_dry_run_egress_review_mitigation_codes(envelope)


def _review(envelope=None, **overrides):
    envelope = envelope or _envelope()
    required = _required(envelope)
    kwargs = {
        "reviewer_ref": "operator:phase85",
        "decision": ProviderDryRunEgressReviewDecision.APPROVE_FUTURE_PROVIDER_SIMULATION_GATE,
        "review_scope": ProviderDryRunEgressReviewScope.FUTURE_PROVIDER_SIMULATION_GATE,
        "approved_constraint_codes": tuple(code for code in required if code.startswith("constraint:")),
        "accepted_mitigation_codes": required,
        "expires_at": "2030-01-01T00:00:00Z",
        "reviewed_at": "2026-05-09T00:00:00Z",
        "evaluated_at": "2026-05-09T00:00:00Z",
        "rationale": "metadata-only provider dry-run egress review; send remains forbidden",
    }
    kwargs.update(overrides)
    return build_provider_dry_run_egress_review_receipt(envelope, **kwargs)


def _with_envelope_status(envelope, status: str):
    changed = replace(envelope, dry_run_status=status)
    return replace(changed, dry_run_digest=compute_provider_dry_run_digest(changed))


def _codes(receipt):
    return {finding.code for finding in receipt.findings}


def test_receipt_can_be_built_from_ready_phase84_envelope_and_summarized():
    envelope = _envelope()
    receipt = build_provider_dry_run_egress_review_receipt_from_envelope(
        envelope,
        reviewer_ref="operator:phase85",
        decision=ProviderDryRunEgressReviewDecision.APPROVE_FUTURE_PROVIDER_SIMULATION_GATE,
        accepted_mitigation_codes=_required(envelope),
        approved_constraint_codes=tuple(code for code in _required(envelope) if code.startswith("constraint:")),
        expires_at="2030-01-01T00:00:00Z",
        reviewed_at="2026-05-09T00:00:00Z",
        evaluated_at="2026-05-09T00:00:00Z",
    )
    assert receipt.review_status == APPROVED
    assert receipt.dry_run_id == envelope.dry_run_id
    assert receipt.dry_run_digest == envelope.dry_run_digest
    assert validate_provider_dry_run_egress_review_receipt(receipt) == ()
    assert summarize_provider_dry_run_egress_review_receipt(receipt)["review_status"] == APPROVED


def test_statuses_for_approval_constraints_reject_more_evidence_missing_reviewer_and_expiration():
    envelope = _envelope()
    assert _review(envelope).review_status == APPROVED
    constrained = _review(
        envelope,
        decision=ProviderDryRunEgressReviewDecision.APPROVE_FUTURE_EGRESS_REVIEW_GATE,
        review_scope=ProviderDryRunEgressReviewScope.FUTURE_EGRESS_REVIEW_GATE,
    )
    assert constrained.review_status == CONSTRAINED
    rejected = _review(envelope, decision=ProviderDryRunEgressReviewDecision.REJECT_PROVIDER_DRY_RUN, accepted_mitigation_codes=())
    assert rejected.review_status == REJECTED
    more = _review(envelope, decision=ProviderDryRunEgressReviewDecision.REQUEST_MORE_EVIDENCE, accepted_mitigation_codes=())
    assert more.review_status == REJECTED
    missing = _review(envelope, reviewer_ref="")
    assert missing.review_status == INVALID
    expired = _review(envelope, expires_at="2026-05-09T00:00:00Z", evaluated_at="2026-05-09T00:00:00Z")
    assert expired.review_status == EXPIRED


def test_satisfaction_requires_matching_id_digest_unexpired_approval_and_all_mitigations():
    envelope = _envelope()
    receipt = _review(envelope)
    assert provider_dry_run_review_satisfies_envelope(envelope, receipt)
    assert provider_dry_run_review_approves_future_simulation_gate(receipt)
    assert not provider_dry_run_review_approves_future_egress_review_gate(receipt)
    assert not provider_dry_run_review_satisfies_envelope(envelope, replace(receipt, dry_run_digest="other", review_digest=compute_provider_dry_run_egress_review_digest(replace(receipt, dry_run_digest="other"))))
    assert not provider_dry_run_review_satisfies_envelope(envelope, replace(receipt, dry_run_id="other", review_digest=compute_provider_dry_run_egress_review_digest(replace(receipt, dry_run_id="other"))))
    missing = _review(envelope, accepted_mitigation_codes=(), approved_constraint_codes=())
    rejected = _review(envelope, rejected_mitigation_codes=(receipt.required_mitigation_codes[0],))
    assert not provider_dry_run_review_satisfies_envelope(envelope, missing)
    assert not provider_dry_run_review_satisfies_envelope(envelope, rejected)


def test_blocked_invalid_send_credentials_network_runtime_and_unknown_labels_are_non_overridable():
    envelope = _envelope()
    statuses = [
        ProviderDryRunStatus.PROVIDER_DRY_RUN_BLOCKED,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_INVALID_INPUT,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_SEND_FORBIDDEN,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_CREDENTIALS_DETECTED,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_NETWORK_EGRESS_DETECTED,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_RUNTIME_AUTHORITY_DETECTED,
    ]
    for status in statuses:
        blocked = _with_envelope_status(envelope, status)
        receipt = _review(blocked, accepted_mitigation_codes=_required(blocked))
        assert receipt.review_status == OVERRIDE
        assert provider_dry_run_review_attempts_forbidden_send_override(receipt)
        assert not provider_dry_run_review_satisfies_envelope(blocked, receipt)
    unknown_provider = replace(envelope, provider_family_label=ProviderDryRunProviderFamily.PROVIDER_FAMILY_UNKNOWN_FORBIDDEN)
    unknown_provider = replace(unknown_provider, dry_run_digest=compute_provider_dry_run_digest(unknown_provider))
    unknown_model = replace(envelope, model_family_label=ProviderDryRunModelFamily.MODEL_FAMILY_UNKNOWN_FORBIDDEN)
    unknown_model = replace(unknown_model, dry_run_digest=compute_provider_dry_run_digest(unknown_model))
    assert _review(unknown_provider, accepted_mitigation_codes=_required(unknown_provider)).review_status == OVERRIDE
    assert _review(unknown_model, accepted_mitigation_codes=_required(unknown_model)).review_status == OVERRIDE


def test_forbidden_scopes_and_forbidden_allowances_are_non_overridable():
    envelope = _envelope()
    for scope in (
        ProviderDryRunEgressReviewScope.ACTUAL_PROVIDER_SEND_FORBIDDEN,
        ProviderDryRunEgressReviewScope.NETWORK_EGRESS_FORBIDDEN,
        ProviderDryRunEgressReviewScope.CREDENTIAL_USE_FORBIDDEN,
        ProviderDryRunEgressReviewScope.TOOL_OR_ACTION_FORBIDDEN,
        ProviderDryRunEgressReviewScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
    ):
        receipt = _review(envelope, review_scope=scope)
        assert receipt.review_status == OVERRIDE
        assert "review_scope_non_overridable" in _codes(receipt)
    for allowance in (
        "provider_send_allowed",
        "network_egress_allowed",
        "credentials_allowed",
        "provider_client_allowed",
        "llm_call_allowed",
        "tool_calls_allowed",
        "memory_retrieval_allowed",
        "memory_write_allowed",
        "retention_allowed",
        "action_execution_allowed",
        "routing_allowed",
    ):
        receipt = _review(envelope, **{allowance: True})
        assert receipt.review_status == OVERRIDE
        assert "forbidden_allowance_requested" in _codes(receipt)


def test_missing_dry_run_evidence_linkage_is_invalid_and_findings_are_explained():
    envelope = replace(_envelope(), dry_run_digest="")
    receipt = _review(envelope)
    assert receipt.review_status == INVALID
    assert "linked_digest_missing" in _codes(receipt)
    assert explain_provider_dry_run_egress_review_findings(receipt)


def test_constraints_are_recorded_and_non_sendable_provider_forbidden_markers_remain_true():
    envelope = _envelope()
    receipt = _review(envelope, approved_constraint_codes=("constraint:a",), rejected_constraint_codes=("constraint:b",))
    assert receipt.approved_constraint_codes == ("constraint:a",)
    assert receipt.rejected_constraint_codes == ("constraint:b",)
    assert provider_dry_run_review_preserves_non_sendable(receipt)
    assert provider_dry_run_review_denies_send(receipt)
    assert receipt.provider_send_allowed is False
    assert receipt.network_egress_allowed is False
    assert receipt.credentials_allowed is False
    assert receipt.provider_client_allowed is False
    assert receipt.llm_call_allowed is False
    assert receipt.tool_calls_allowed is False
    assert receipt.memory_retrieval_allowed is False
    assert receipt.memory_write_allowed is False
    assert receipt.retention_allowed is False
    assert receipt.action_execution_allowed is False
    assert receipt.routing_allowed is False
    assert receipt.provider_dry_run_review_receipt_only is True
    assert receipt.does_not_send_to_provider is True
    assert receipt.does_not_make_network_calls is True


def test_digest_is_deterministic_and_changes_for_stable_review_metadata():
    envelope = _envelope()
    receipt = _review(envelope)
    assert receipt.review_digest == compute_provider_dry_run_egress_review_digest(receipt)
    assert _review(envelope).review_digest == receipt.review_digest
    changed_dry_run = replace(envelope, request_purpose="changed metadata")
    changed_dry_run = replace(changed_dry_run, dry_run_digest=compute_provider_dry_run_digest(changed_dry_run))
    variants = [
        _review(changed_dry_run, accepted_mitigation_codes=_required(changed_dry_run)).review_digest,
        _review(envelope, reviewer_ref="operator:other").review_digest,
        _review(envelope, decision=ProviderDryRunEgressReviewDecision.REJECT_PROVIDER_DRY_RUN, accepted_mitigation_codes=()).review_digest,
        _review(envelope, review_scope=ProviderDryRunEgressReviewScope.FUTURE_EGRESS_REVIEW_GATE, decision=ProviderDryRunEgressReviewDecision.APPROVE_FUTURE_EGRESS_REVIEW_GATE).review_digest,
        _review(envelope, accepted_mitigation_codes=receipt.required_mitigation_codes[:-1]).review_digest,
        _review(envelope, rejected_mitigation_codes=(receipt.required_mitigation_codes[0],)).review_digest,
        _review(envelope, expires_at="2031-01-01T00:00:00Z").review_digest,
        _review(envelope, rationale="changed rationale").review_digest,
    ]
    assert all(digest != receipt.review_digest for digest in variants)


def test_ready_with_warnings_can_satisfy_but_blocked_dry_runs_cannot_and_helper_does_not_mutate():
    warning_envelope = _envelope(chain=_chain(warnings=True))
    warning_receipt = _review(warning_envelope, accepted_mitigation_codes=_required(warning_envelope), approved_constraint_codes=tuple(code for code in _required(warning_envelope) if code.startswith("constraint:")))
    assert provider_dry_run_review_satisfies_envelope(warning_envelope, warning_receipt)
    envelope = _envelope()
    before = deepcopy(envelope)
    blocked = _with_envelope_status(envelope, ProviderDryRunStatus.PROVIDER_DRY_RUN_SEND_FORBIDDEN)
    assert not provider_dry_run_review_satisfies_envelope(blocked, _review(blocked, accepted_mitigation_codes=_required(blocked)))
    provider_dry_run_review_satisfies_envelope(envelope, _review(envelope))
    assert envelope == before


def test_no_forbidden_runtime_provider_prompt_calls_are_reachable_from_helpers(monkeypatch):
    prompt_assembler = types.ModuleType("prompt_assembler")
    prompt_assembler.assemble_prompt = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("assemble_prompt called"))
    sys.modules["prompt_assembler"] = prompt_assembler
    for module_name in ("openai", "requests", "httpx", "memory_manager"):
        sys.modules[module_name] = types.ModuleType(module_name)
    envelope = _envelope()
    receipt = _review(envelope)
    assert provider_dry_run_review_satisfies_envelope(envelope, receipt)
    assert importlib.import_module("sentientos.context_hygiene.prompt_provider_dry_run_review")


def test_phase63_to_phase84_to_phase85_chain_and_blocked_attempted_candidate_behavior():
    # The Phase 84 chain includes the Phase 63-safe candidate path; Phase 85 can approve only when all gates pass.
    envelope = _envelope()
    assert provider_dry_run_review_satisfies_envelope(envelope, _review(envelope))
    blocked_candidate_envelope = _envelope(candidate=replace(_chain()[0], status="internal_prompt_candidate_blocked_attempted_candidate"))
    receipt = _review(blocked_candidate_envelope, accepted_mitigation_codes=_required(blocked_candidate_envelope))
    assert receipt.review_status == OVERRIDE
    assert not provider_dry_run_review_satisfies_envelope(blocked_candidate_envelope, receipt)


def test_adversarial_provider_runtime_markers_remain_non_overridable_and_guardrails_scan_module():
    envelope = _envelope(extra_metadata={"provider_params": {"temperature": 0}})
    receipt = _review(envelope, accepted_mitigation_codes=_required(envelope))
    assert receipt.review_status == OVERRIDE
    report = scan_context_hygiene_prompt_boundaries(["sentientos/context_hygiene/prompt_provider_dry_run_review.py"])
    assert report.ok, report.to_dict()
