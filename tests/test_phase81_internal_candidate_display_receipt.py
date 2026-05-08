"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import importlib
import sys
import types

import pytest

tts_stub = types.ModuleType("tts_bridge")
tts_stub.speak = lambda *args, **kwargs: None
sys.modules.setdefault("tts_bridge", tts_stub)

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from sentientos.context_hygiene.prompt_internal_candidate import (
    InternalPromptCandidateRef,
    InternalPromptCandidateSection,
    InternalPromptCandidateStatus,
    build_internal_prompt_candidate_input,
    materialize_internal_no_llm_prompt_candidate,
)
from sentientos.context_hygiene.prompt_internal_display import (
    InternalPromptDisplayReceipt,
    InternalPromptDisplayScope,
    InternalPromptDisplayStatus,
    build_internal_prompt_display_receipt,
    compute_internal_prompt_display_receipt_digest,
    internal_prompt_candidate_may_be_displayed,
    internal_prompt_display_has_no_model_egress,
    internal_prompt_display_has_no_runtime_authority,
    summarize_internal_prompt_display_receipt,
)
from sentientos.context_hygiene.prompt_materialization_policy import (
    PromptMaterializationPolicyRing,
    PromptMaterializationPolicyStatus,
)
from sentientos.context_hygiene.prompt_operator_review import PromptOperatorReviewDecision, build_prompt_operator_review_receipt


def _policy(status=PromptMaterializationPolicyStatus.POLICY_INTERNAL_CANDIDATE_NO_LLM_ALLOWED, **overrides):
    data = {
        "decision_id": "policy:packet:1",
        "policy_status": status,
        "requested_ring": PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM,
        "effective_ring": PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM,
        "allowed": status == PromptMaterializationPolicyStatus.POLICY_INTERNAL_CANDIDATE_NO_LLM_ALLOWED,
        "denied": status == PromptMaterializationPolicyStatus.POLICY_DENY,
        "requires_operator_review": status == PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED,
        "allows_shadow_only": False,
        "allows_synthetic_materializer": False,
        "allows_internal_candidate_no_llm": status == PromptMaterializationPolicyStatus.POLICY_INTERNAL_CANDIDATE_NO_LLM_ALLOWED,
        "forbids_live_llm": True,
        "forbids_memory_retrieval": True,
        "forbids_memory_write": True,
        "forbids_action_execution": True,
        "forbids_retention_commit": True,
        "reasons": (),
        "required_mitigations": (),
        "receipt_id": "audit:1",
        "receipt_digest": "digest:audit:1",
        "packet_id": "packet:1",
        "packet_scope": "turn",
        "source_kind_summary": {"evidence": 1},
        "caveat_count": 0,
        "warning_count": 0,
        "violation_count": 0,
        "finding_count": 0,
        "rationale": "test policy",
        "policy_digest": "digest:policy:1",
        "does_not_call_llm": True,
        "does_not_retrieve_memory": True,
        "does_not_write_memory": True,
        "does_not_trigger_feedback": True,
        "does_not_commit_retention": True,
        "does_not_execute_or_route_work": True,
        "does_not_admit_work": True,
    }
    data.update(overrides)
    return data


def _audit(**overrides):
    data = {
        "receipt_id": "audit:1",
        "audit_status": "audit_ready_for_shadow_materialization",
        "blueprint_id": "blueprint:1",
        "blueprint_digest": "digest:blueprint:1",
        "adapter_payload_id": "adapter:1",
        "adapter_status": "adapter_ready",
        "compliance_status": "compliance_ready",
        "preview_status": "preview_ready",
        "blueprint_status": "blueprint_ready",
        "packet_id": "packet:1",
        "packet_scope": "turn",
        "adapter_payload_digest": "digest:adapter:1",
        "receipt_digest": "digest:audit:1",
        "digest_chain_complete": True,
        "preserved_caveats": (),
        "warnings": (),
        "violations": (),
        "findings": (),
    }
    data.update(overrides)
    return data


def _review(policy=None, *, decisions=(PromptOperatorReviewDecision.ACCEPT_REQUIRED_WARNINGS,), **kwargs):
    policy = policy or _policy(PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED, warning_count=1)
    kwargs.setdefault("reviewer_ref", "operator:phase81")
    kwargs.setdefault("decisions", decisions)
    kwargs.setdefault("accepted_warning_codes", ("warning:operator_review_required:1",))
    return build_prompt_operator_review_receipt(policy, **kwargs)


def _ref(**overrides):
    data = {
        "ref_id": "ref:1",
        "ref_kind": "adapter_ref",
        "summary": "approved packet-safe context summary",
        "provenance_summary": "prov:1",
        "source_kind": "evidence",
        "caveats": ("caveat one",),
        "boundary_notes": ("boundary one",),
    }
    data.update(overrides)
    return InternalPromptCandidateRef(**data)


def _section(**overrides):
    data = {
        "section_id": "section:1",
        "section_kind": "adapter_context_refs",
        "summary": "approved section summary",
        "ref_ids": ("ref:1",),
        "caveats": ("caveat one",),
        "boundary_notes": ("boundary one",),
    }
    data.update(overrides)
    return InternalPromptCandidateSection(**data)


def _input(**overrides):
    kwargs = {
        "policy_decision": _policy(),
        "audit_receipt": _audit(),
        "adapter_payload": {"adapter_payload_id": "adapter:1", "digest": "digest:adapter:1", "adapter_status": "adapter_ready"},
        "blueprint": {"blueprint_id": "blueprint:1", "blueprint_digest": "digest:blueprint:1", "blueprint_status": "blueprint_ready"},
        "candidate_refs": (_ref(),),
        "candidate_sections": (_section(),),
        "preserved_caveats": ("caveat one",),
        "preserved_boundary_notes": ("boundary one",),
        "feature_flag_state": {"internal_no_llm_candidate": True},
    }
    kwargs.update(overrides)
    return build_internal_prompt_candidate_input(**kwargs)


def _candidate(**overrides):
    return materialize_internal_no_llm_prompt_candidate(_input(**overrides))


def _receipt(candidate=None, **kwargs):
    candidate = candidate or _candidate()
    kwargs.setdefault("display_scope", InternalPromptDisplayScope.OPERATOR_INTERNAL_REVIEW)
    kwargs.setdefault("operator_ref", "operator:ada")
    return build_internal_prompt_display_receipt(candidate, **kwargs)


def test_ready_internal_candidate_operator_review_scope_yields_display_allowed():
    receipt = _receipt()
    assert receipt.display_status == InternalPromptDisplayStatus.DISPLAY_ALLOWED
    assert internal_prompt_candidate_may_be_displayed(receipt)


def test_ready_with_warnings_candidate_yields_display_allowed_with_warnings():
    policy = _policy(PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED, warning_count=1, allows_internal_candidate_no_llm=False, requires_operator_review=True)
    candidate = _candidate(policy_decision=policy, operator_review_receipt=_review(policy), audit_receipt=_audit(warnings=({"code": "needs_review"},)))
    receipt = _receipt(candidate)
    assert candidate.status == InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_READY_WITH_WARNINGS
    assert receipt.display_status == InternalPromptDisplayStatus.DISPLAY_ALLOWED_WITH_WARNINGS


def test_blocked_invalid_policy_denied_and_review_required_candidates_deny_display():
    blocked = _candidate(audit_receipt=_audit(audit_status="audit_blocked"))
    invalid = materialize_internal_no_llm_prompt_candidate({})
    denied = _candidate(policy_decision=_policy(PromptMaterializationPolicyStatus.POLICY_DENY, denied=True, allowed=False, allows_internal_candidate_no_llm=False))
    review_required = _candidate(policy_decision=_policy(PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED, requires_operator_review=True, allows_internal_candidate_no_llm=False, warning_count=1))
    assert _receipt(blocked).display_status == InternalPromptDisplayStatus.DISPLAY_DENIED
    assert _receipt(invalid).display_status == InternalPromptDisplayStatus.DISPLAY_INVALID_CANDIDATE
    assert _receipt(denied).display_status == InternalPromptDisplayStatus.DISPLAY_DENIED
    assert _receipt(review_required).display_status == InternalPromptDisplayStatus.DISPLAY_DENIED


def test_digest_mismatch_forbidden_scopes_missing_operator_and_expired_receipt_deny():
    candidate = _candidate()
    assert _receipt(candidate, expected_candidate_digest="wrong").display_status == InternalPromptDisplayStatus.DISPLAY_DIGEST_MISMATCH
    assert _receipt(candidate, display_scope=InternalPromptDisplayScope.EXTERNAL_USER_VISIBLE_FORBIDDEN).display_status == InternalPromptDisplayStatus.DISPLAY_SCOPE_FORBIDDEN
    assert _receipt(candidate, display_scope=InternalPromptDisplayScope.MODEL_PROVIDER_FORBIDDEN).display_status == InternalPromptDisplayStatus.DISPLAY_MODEL_EGRESS_FORBIDDEN
    assert _receipt(candidate, display_scope=InternalPromptDisplayScope.TOOL_OR_ACTION_FORBIDDEN).display_status == InternalPromptDisplayStatus.DISPLAY_RUNTIME_AUTHORITY_DETECTED
    assert _receipt(candidate, operator_ref="").display_status == InternalPromptDisplayStatus.DISPLAY_DENIED
    assert _receipt(candidate, expires_at="2000-01-01T00:00:00Z").display_status == InternalPromptDisplayStatus.DISPLAY_DENIED


def test_text_digest_only_and_no_duplicate_candidate_text_by_default():
    candidate = _candidate()
    receipt = _receipt(candidate, include_text_digest_only=True)
    assert receipt.candidate_text_length == len(candidate.internal_candidate_text)
    assert receipt.candidate_text_digest == _receipt(candidate).candidate_text_digest
    assert receipt.text_included is False
    assert receipt.text_redacted is True
    assert candidate.internal_candidate_text not in repr(receipt)
    assert not hasattr(receipt, "internal_candidate_text")


def test_display_receipt_digest_is_deterministic_and_changes_for_inputs():
    candidate = _candidate()
    one = _receipt(candidate, expected_candidate_digest=candidate.candidate_digest, display_reason="review")
    two = _receipt(candidate, expected_candidate_digest=candidate.candidate_digest, display_reason="review")
    assert one.display_receipt_digest == two.display_receipt_digest == compute_internal_prompt_display_receipt_digest(one)
    changed_candidate = _candidate(candidate_refs=(_ref(summary="changed summary"),))
    variants = {
        one.display_receipt_digest,
        _receipt(changed_candidate, expected_candidate_digest=changed_candidate.candidate_digest, display_reason="review").display_receipt_digest,
        _receipt(candidate, display_scope=InternalPromptDisplayScope.OPERATOR_INTERNAL_DEBUG, expected_candidate_digest=candidate.candidate_digest, display_reason="review").display_receipt_digest,
        _receipt(candidate, operator_ref="operator:grace", expected_candidate_digest=candidate.candidate_digest, display_reason="review").display_receipt_digest,
        _receipt(candidate, expected_candidate_digest=candidate.candidate_digest, display_reason="changed").display_receipt_digest,
        _receipt(candidate, expected_candidate_digest=candidate.candidate_digest, expires_at="2030-01-01T00:00:00Z", display_reason="review").display_receipt_digest,
    }
    assert len(variants) == 6
    denied = _receipt(replace(candidate, internal_candidate_text=candidate.internal_candidate_text + " raw" + "_payload"), display_reason="review")
    assert denied.display_receipt_digest != one.display_receipt_digest


@pytest.mark.parametrize(
    ("edit", "code"),
    [
        (lambda text: text + " raw" + "_payload", "candidate_text_raw_payload_marker"),
        (lambda text: text + " execution" + "_handle", "candidate_text_runtime_handle_marker"),
        (lambda text: text + " provider" + "_params", "candidate_text_provider_marker"),
        (lambda text: text.replace("INTERNAL NO-LLM CANDIDATE", "INTERNAL CANDIDATE"), "missing_internal_no_llm_marker"),
        (lambda text: text.replace("not been sent to a model", "held locally").replace("not sent to model", "held locally"), "missing_not_sent_to_model_marker"),
        (lambda text: text.replace("OPERATOR VISIBLE ONLY", "OPERATOR REVIEW"), "missing_operator_visible_only_marker"),
    ],
)
def test_candidate_text_adversarial_marker_gates(edit, code):
    candidate = _candidate()
    bad = replace(candidate, internal_candidate_text=edit(candidate.internal_candidate_text))
    receipt = _receipt(bad)
    assert receipt.display_status in {InternalPromptDisplayStatus.DISPLAY_DENIED, InternalPromptDisplayStatus.DISPLAY_DIGEST_MISMATCH}
    assert code in {finding.code for finding in receipt.findings}
    assert not internal_prompt_candidate_may_be_displayed(receipt, bad)


def test_receipt_links_evidence_and_no_runtime_markers():
    policy = _policy(PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED, warning_count=1, requires_operator_review=True, allows_internal_candidate_no_llm=False)
    review = _review(policy)
    candidate = _candidate(policy_decision=policy, operator_review_receipt=review, audit_receipt=_audit(warnings=({"code": "needs_review"},)))
    receipt = _receipt(candidate)
    assert receipt.policy_decision_id == candidate.policy_decision_id
    assert receipt.policy_digest == candidate.policy_digest
    assert receipt.audit_receipt_id == candidate.audit_receipt_id
    assert receipt.audit_receipt_digest == candidate.audit_receipt_digest
    assert receipt.review_receipt_id == candidate.review_receipt_id
    assert receipt.review_digest == candidate.review_digest
    assert receipt.packet_id == candidate.packet_id
    assert receipt.internal_display_receipt_only is True
    assert internal_prompt_display_has_no_model_egress(receipt)
    assert internal_prompt_display_has_no_runtime_authority(receipt)


def test_helper_does_not_mutate_candidate_or_import_runtime_modules(monkeypatch):
    candidate = _candidate()
    before = deepcopy(candidate)
    for module_name in ("prompt_assembler", "memory_manager", "openai"):
        if module_name in sys.modules:
            monkeypatch.delitem(sys.modules, module_name, raising=False)
    receipt = _receipt(candidate)
    assert candidate == before
    assert receipt.display_status == InternalPromptDisplayStatus.DISPLAY_ALLOWED
    assert all(module_name not in sys.modules for module_name in ("prompt_assembler", "memory_manager", "openai"))


def test_phase63_through_phase81_smoke_path_from_adapter_payload():
    from datetime import datetime, timezone
    from sentientos.context_hygiene.context_packet import ContextMode
    from sentientos.context_hygiene.prompt_adapter_contract import build_prompt_assembly_adapter_payload
    from sentientos.context_hygiene.prompt_constraint_verifier import build_candidate_plan_from_dry_run_envelope, verify_prompt_assembly_constraints
    from sentientos.context_hygiene.prompt_dry_run_envelope import build_context_prompt_dry_run_envelope
    from sentientos.context_hygiene.prompt_handoff_manifest import build_context_prompt_handoff_manifest
    from sentientos.context_hygiene.prompt_materialization_audit import build_prompt_materialization_audit_receipt_from_adapter_payload
    from sentientos.context_hygiene.prompt_materialization_policy import evaluate_prompt_materialization_policy_from_audit_receipt
    from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates

    context_candidate = ContextCandidate(
        ref_id="real-summary-ref",
        ref_type="evidence",
        packet_scope="turn",
        conversation_scope_id="conv",
        task_scope_id="task",
        provenance_refs=("prov:phase81",),
        source_locator="source-summary",
        summary="already-approved packet-safe summary",
        already_sanitized_context_summary=True,
        truth_ingress_status="allowed",
        contradiction_status="unknown",
        metadata={"source_kind": "evidence", "privacy_posture": "public", "non_authoritative": True, "decision_power": "none"},
    )
    packet = build_context_packet_from_candidates([context_candidate], "turn", "conv", "task", context_mode=ContextMode.RESPONSE, now=datetime.now(timezone.utc))
    envelope = build_context_prompt_dry_run_envelope(build_context_prompt_handoff_manifest(packet))
    plan = build_candidate_plan_from_dry_run_envelope(envelope)
    verification = verify_prompt_assembly_constraints(envelope, plan)
    adapter = build_prompt_assembly_adapter_payload(verification, plan)
    audit = build_prompt_materialization_audit_receipt_from_adapter_payload(adapter)
    policy = evaluate_prompt_materialization_policy_from_audit_receipt(
        audit,
        requested_ring=PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM,
        feature_flag_state={"internal_no_llm_candidate": True},
        no_runtime_markers={"internal_only": True, "operator_visible_only": True, "no_llm": True},
    )
    candidate = materialize_internal_no_llm_prompt_candidate(
        build_internal_prompt_candidate_input(policy_decision=policy, audit_receipt=audit, adapter_payload=adapter.__dict__, feature_flag_state={"internal_no_llm_candidate": True})
    )
    receipt = _receipt(candidate, expected_candidate_digest=candidate.candidate_digest)
    assert receipt.display_status == InternalPromptDisplayStatus.DISPLAY_ALLOWED
    assert internal_prompt_candidate_may_be_displayed(receipt, candidate)


def test_phase62b_blocked_attempt_and_phase76_adversarial_markers_remain_denied():
    policy = _policy(PromptMaterializationPolicyStatus.POLICY_DENY, denied=True, allowed=False, allows_internal_candidate_no_llm=False, reasons=({"code": "blocked_attempted_candidate"},))
    assert _receipt(_candidate(policy_decision=policy)).display_status == InternalPromptDisplayStatus.DISPLAY_DENIED
    bad = replace(_candidate(), internal_candidate_text=_candidate().internal_candidate_text + " runtime" + "_authority provider" + "_params")
    receipt = _receipt(bad)
    assert receipt.display_status in {InternalPromptDisplayStatus.DISPLAY_DENIED, InternalPromptDisplayStatus.DISPLAY_DIGEST_MISMATCH}


def test_guardrail_scans_new_module_and_import_purity_static_contract():
    guard = importlib.import_module("scripts.verify_context_hygiene_prompt_boundaries")
    assert "sentientos/context_hygiene/prompt_internal_display.py" in guard.DEFAULT_SCAN_TARGETS
    assert not guard.scan_file_for_prompt_boundary_violations("sentientos/context_hygiene/prompt_internal_display.py")
    source = open("sentientos/context_hygiene/prompt_internal_display.py", encoding="utf-8").read()
    forbidden = ("prompt_assembler", "memory_manager", "openai", "requests", "httpx", "action_router", "task_executor")
    assert all(token not in source for token in forbidden)


def test_summary_exposes_receipt_without_text():
    receipt = _receipt()
    summary = summarize_internal_prompt_display_receipt(receipt)
    assert summary["display_status"] == InternalPromptDisplayStatus.DISPLAY_ALLOWED
    assert summary["candidate_text_digest"] == receipt.candidate_text_digest
    assert summary["candidate_text_length"] == receipt.candidate_text_length
    assert summary["text_included"] is False
    assert isinstance(receipt, InternalPromptDisplayReceipt)
