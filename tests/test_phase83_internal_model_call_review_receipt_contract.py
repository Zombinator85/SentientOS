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

from sentientos.context_hygiene.prompt_internal_candidate import (
    InternalPromptCandidateRef,
    InternalPromptCandidateSection,
    InternalPromptCandidateStatus,
    build_internal_prompt_candidate_input,
    compute_internal_prompt_candidate_digest,
    materialize_internal_no_llm_prompt_candidate,
)
from sentientos.context_hygiene.prompt_internal_display import (
    InternalPromptDisplayScope,
    build_internal_prompt_display_receipt,
)
from sentientos.context_hygiene.prompt_materialization_policy import (
    PromptMaterializationPolicyRing,
    PromptMaterializationPolicyStatus,
)
from sentientos.context_hygiene.prompt_model_call_preflight import (
    InternalModelCallPreflightRing,
    InternalModelCallPreflightStatus,
    build_internal_model_call_preflight_input,
    evaluate_internal_model_call_preflight,
)
from sentientos.context_hygiene.prompt_model_call_review import (
    InternalModelCallReviewDecision,
    InternalModelCallReviewScope,
    InternalModelCallReviewStatus,
    build_internal_model_call_review_receipt,
    build_internal_model_call_review_receipt_from_preflight,
    compute_internal_model_call_review_digest,
    explain_internal_model_call_review_findings,
    extract_required_internal_model_call_review_mitigation_codes,
    internal_model_call_review_approves_future_gate,
    internal_model_call_review_attempts_forbidden_override,
    internal_model_call_review_denies_future_gate,
    internal_model_call_review_preserves_provider_forbidden,
    internal_model_call_review_satisfies_preflight,
    summarize_internal_model_call_review_receipt,
    validate_internal_model_call_review_receipt,
)
from scripts.verify_context_hygiene_prompt_boundaries import scan_context_hygiene_prompt_boundaries

READY = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_FOR_REVIEW
WARNINGS = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_WITH_WARNINGS
DENIED = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_DENIED
INVALID = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_INVALID_INPUT
DISPLAY_DENIED = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_DISPLAY_DENIED
POLICY_DENIED = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_POLICY_DENIED
PROVIDER_FORBIDDEN = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_PROVIDER_FORBIDDEN
RUNTIME_DETECTED = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED
APPROVED = InternalModelCallReviewStatus.MODEL_CALL_REVIEW_APPROVED
CONSTRAINED = InternalModelCallReviewStatus.MODEL_CALL_REVIEW_APPROVED_WITH_CONSTRAINTS
REJECTED = InternalModelCallReviewStatus.MODEL_CALL_REVIEW_REJECTED
EXPIRED = InternalModelCallReviewStatus.MODEL_CALL_REVIEW_EXPIRED
INVALID_REVIEW = InternalModelCallReviewStatus.MODEL_CALL_REVIEW_INVALID
FORBIDDEN_OVERRIDE = InternalModelCallReviewStatus.MODEL_CALL_REVIEW_FORBIDDEN_OVERRIDE_ATTEMPTED


def _policy(status: str = PromptMaterializationPolicyStatus.POLICY_INTERNAL_CANDIDATE_NO_LLM_ALLOWED, **overrides):
    data = {
        "decision_id": "policy:packet:1",
        "policy_status": status,
        "requested_ring": PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM,
        "effective_ring": PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM,
        "allowed": status == PromptMaterializationPolicyStatus.POLICY_INTERNAL_CANDIDATE_NO_LLM_ALLOWED,
        "denied": status == PromptMaterializationPolicyStatus.POLICY_DENY,
        "requires_operator_review": status == PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED,
        "allows_shadow_only": status == PromptMaterializationPolicyStatus.POLICY_SHADOW_ONLY,
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
        "blueprint_status": "shadow_blueprint_ready",
        "packet_id": "packet:1",
        "packet_scope": "turn",
        "manifest_id": "manifest:1",
        "manifest_digest": "digest:manifest:1",
        "envelope_id": "envelope:1",
        "envelope_digest": "digest:envelope:1",
        "candidate_plan_id": "plan:1",
        "candidate_plan_digest": "digest:plan:1",
        "adapter_payload_digest": "digest:adapter:1",
        "verification_digest": "digest:verification:1",
        "shadow_preview_digest": "digest:preview:1",
        "shadow_blueprint_digest": "digest:shadow-blueprint:1",
        "digest_chain_complete": True,
        "digest_chain": {"complete": True, "missing": ()},
        "boundary_summary": {"may_future_assembler_consume": True, "must_block_prompt_materialization": False},
        "preserved_caveats": (),
        "warnings": (),
        "violations": (),
        "findings": (),
        "provenance_summary": {},
        "privacy_summary": {},
        "truth_summary": {},
        "safety_summary": {},
        "source_kind_summary": {"evidence": 1},
        "ref_counts": {"included": 1},
        "section_counts": {"included": 1},
        "rationale": "audit ready",
        "receipt_digest": "digest:audit:1",
        "audit_receipt_only": True,
        "attestation_only": True,
        "does_not_materialize_prompt_text": True,
        "does_not_assemble_prompt": True,
        "does_not_contain_final_prompt_text": True,
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


def _candidate(*, policy=None, audit=None, warnings=False, text_suffix=""):
    policy = policy or _policy()
    audit = audit or _audit()
    candidate_input = build_internal_prompt_candidate_input(
        policy_decision=policy,
        audit_receipt=audit,
        adapter_payload={"adapter_payload_id": "adapter:1", "digest": "digest:adapter:1", "adapter_status": "adapter_ready"},
        blueprint={"blueprint_id": "blueprint:1", "blueprint_digest": "digest:blueprint:1", "blueprint_status": "shadow_blueprint_ready"},
        candidate_refs=(
            InternalPromptCandidateRef(
                ref_id="ref:1",
                ref_kind="adapter_ref",
                summary="approved packet-safe context summary",
                provenance_summary="prov:1",
                source_kind="evidence",
                caveats=("accepted caveat",) if warnings else (),
                boundary_notes=("packet-safe summary only",),
            ),
        ),
        candidate_sections=(
            InternalPromptCandidateSection(
                section_id="section:1",
                section_kind="adapter_context_refs",
                summary="approved packet-safe section summary",
                ref_ids=("ref:1",),
                caveats=("accepted caveat",) if warnings else (),
                boundary_notes=("packet-safe summary only",),
            ),
        ),
        preserved_caveats=("accepted caveat",) if warnings else (),
        preserved_boundary_notes=("boundary preserved",),
        feature_flag_state={"internal_no_llm_candidate": True},
    )
    candidate = materialize_internal_no_llm_prompt_candidate(candidate_input)
    if text_suffix:
        candidate = replace(candidate, internal_candidate_text=candidate.internal_candidate_text + text_suffix)
        candidate = replace(candidate, candidate_digest=compute_internal_prompt_candidate_digest(candidate))
    return candidate


def _display(candidate=None, *, display_scope=InternalPromptDisplayScope.OPERATOR_INTERNAL_REVIEW):
    candidate = candidate or _candidate()
    return build_internal_prompt_display_receipt(
        candidate,
        display_scope=display_scope,
        operator_ref="operator:phase83",
        display_reason="phase83 review receipt test",
        expires_at="2030-01-01T00:00:00Z",
    )


def _preflight(**overrides):
    policy = overrides.pop("policy", _policy())
    audit = overrides.pop("audit", _audit())
    candidate = overrides.pop("candidate", _candidate(policy=policy, audit=audit))
    display = overrides.pop("display", _display(candidate))
    flags = overrides.pop("feature_flag_state", {"model_call_preflight": True})
    input_data = build_internal_model_call_preflight_input(candidate, display, policy, audit, feature_flag_state=flags, **overrides)
    return evaluate_internal_model_call_preflight(input_data)


def _receipt(preflight=None, **overrides):
    preflight = preflight or _preflight()
    required = extract_required_internal_model_call_review_mitigation_codes(preflight)
    kwargs = {
        "reviewer_ref": "operator:phase83",
        "decision": InternalModelCallReviewDecision.APPROVE_FUTURE_REVIEW_GATE,
        "review_scope": InternalModelCallReviewScope.INTERNAL_MODEL_CALL_REVIEW_GATE,
        "approved_constraint_codes": tuple(code for code in required if code.startswith("constraint:")),
        "accepted_mitigation_codes": required,
        "expires_at": "2030-01-01T00:00:00Z",
        "reviewed_at": "2026-05-08T00:00:00Z",
        "evaluated_at": "2026-05-08T00:00:00Z",
        "rationale": "metadata-only future gate review; provider calls remain forbidden",
    }
    kwargs.update(overrides)
    return build_internal_model_call_review_receipt(preflight, **kwargs)


def _codes(receipt):
    return {finding.code for finding in receipt.findings}


def test_review_receipt_can_be_built_from_ready_phase82_preflight_and_approved():
    preflight = _preflight()
    receipt = build_internal_model_call_review_receipt_from_preflight(
        preflight,
        reviewer_ref="operator:phase83",
        decision=InternalModelCallReviewDecision.APPROVE_FUTURE_REVIEW_GATE,
        review_scope=InternalModelCallReviewScope.INTERNAL_MODEL_CALL_REVIEW_GATE,
        approved_constraint_codes=extract_required_internal_model_call_review_mitigation_codes(preflight),
        accepted_mitigation_codes=extract_required_internal_model_call_review_mitigation_codes(preflight),
        expires_at="2030-01-01T00:00:00Z",
    )
    assert receipt.review_status == APPROVED
    assert receipt.preflight_id == preflight.preflight_id
    assert internal_model_call_review_satisfies_preflight(preflight, receipt)


def test_approve_with_constraints_yields_constrained_status_and_provider_dry_run_scope_requires_it():
    preflight = _preflight()
    receipt = _receipt(
        preflight,
        decision=InternalModelCallReviewDecision.APPROVE_WITH_CONSTRAINTS,
        review_scope=InternalModelCallReviewScope.PROVIDER_DRY_RUN_FUTURE_GATE,
        approved_constraint_codes=("constraint:provider_call_forbidden", "future_phase:provider_dry_run_contract_required"),
        accepted_mitigation_codes=extract_required_internal_model_call_review_mitigation_codes(preflight),
    )
    assert receipt.review_status == CONSTRAINED
    assert internal_model_call_review_approves_future_gate(receipt)
    assert _receipt(preflight, review_scope=InternalModelCallReviewScope.PROVIDER_DRY_RUN_FUTURE_GATE).review_status == FORBIDDEN_OVERRIDE


def test_reject_and_request_more_evidence_deny_future_gate():
    for decision in (InternalModelCallReviewDecision.REJECT_FUTURE_REVIEW_GATE, InternalModelCallReviewDecision.REQUEST_MORE_EVIDENCE):
        receipt = _receipt(decision=decision, accepted_mitigation_codes=())
        assert receipt.review_status == REJECTED
        assert internal_model_call_review_denies_future_gate(receipt)
        assert not internal_model_call_review_approves_future_gate(receipt)


def test_missing_reviewer_ref_and_expired_review_are_invalid_or_expired():
    assert _receipt(reviewer_ref="").review_status == INVALID_REVIEW
    expired = _receipt(expires_at="2026-05-08T00:00:00Z", evaluated_at="2026-05-08T00:00:00Z")
    assert expired.review_status == EXPIRED
    assert validate_internal_model_call_review_receipt(expired)


def test_preflight_digest_or_id_mismatch_does_not_satisfy_preflight():
    preflight = _preflight()
    receipt = _receipt(preflight)
    assert not internal_model_call_review_satisfies_preflight(preflight, replace(receipt, preflight_digest="different", review_digest=compute_internal_model_call_review_digest(replace(receipt, preflight_digest="different"))))
    assert not internal_model_call_review_satisfies_preflight(preflight, replace(receipt, preflight_id="different", review_digest=compute_internal_model_call_review_digest(replace(receipt, preflight_id="different"))))


def test_denied_invalid_display_policy_provider_runtime_and_live_ring_preflights_are_non_overridable():
    denied_cases = [
        replace(_preflight(), preflight_status=DENIED),
        replace(_preflight(candidate=replace(_candidate(), status=InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_BLOCKED)), preflight_status=INVALID),
        _preflight(display=_display(_candidate(), display_scope=InternalPromptDisplayScope.EXTERNAL_USER_VISIBLE_FORBIDDEN)),
        _preflight(policy=_policy(status=PromptMaterializationPolicyStatus.POLICY_DENY)),
        _preflight(requested_model_review_ring=InternalModelCallPreflightRing.INTERNAL_MODEL_CALL_DRY_RUN_FORBIDDEN_PROVIDER),
        _preflight(no_actions=False),
        _preflight(requested_model_review_ring=InternalModelCallPreflightRing.LIVE_MODEL_CALL_FORBIDDEN),
    ]
    expected = {DENIED, INVALID, DISPLAY_DENIED, POLICY_DENIED, PROVIDER_FORBIDDEN, RUNTIME_DETECTED}
    for preflight in denied_cases:
        assert preflight.preflight_status in expected
        receipt = _receipt(preflight)
        assert receipt.review_status in {FORBIDDEN_OVERRIDE, INVALID_REVIEW}
        assert internal_model_call_review_attempts_forbidden_override(receipt) or receipt.review_status == INVALID_REVIEW
        assert not internal_model_call_review_satisfies_preflight(preflight, receipt)


def test_forbidden_review_scopes_cannot_be_approved():
    for scope in (
        InternalModelCallReviewScope.LIVE_PROVIDER_CALL_FORBIDDEN,
        InternalModelCallReviewScope.TOOL_OR_ACTION_FORBIDDEN,
        InternalModelCallReviewScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
    ):
        receipt = _receipt(review_scope=scope)
        assert receipt.review_status == FORBIDDEN_OVERRIDE
        assert "review_scope_non_overridable" in _codes(receipt)


def test_allowing_provider_llm_tool_memory_retention_action_or_routing_is_forbidden():
    allowance_fields = (
        "provider_call_allowed",
        "llm_call_allowed",
        "tool_calls_allowed",
        "memory_retrieval_allowed",
        "memory_write_allowed",
        "retention_allowed",
        "action_execution_allowed",
        "routing_allowed",
    )
    for field in allowance_fields:
        receipt = _receipt(**{field: True})
        assert receipt.review_status == FORBIDDEN_OVERRIDE
        assert "forbidden_allowance_requested" in _codes(receipt)
        assert not internal_model_call_review_satisfies_preflight(_preflight(), receipt)


def test_missing_candidate_display_policy_or_audit_digest_yields_invalid_finding():
    preflight = _preflight()
    for field in ("candidate_digest", "display_receipt_digest", "policy_digest", "audit_receipt_digest"):
        broken = replace(preflight, **{field: ""})
        receipt = _receipt(broken)
        assert receipt.review_status == INVALID_REVIEW
        assert "linked_digest_missing" in _codes(receipt)


def test_required_mitigations_must_be_accepted_and_rejections_block_satisfaction():
    preflight = _preflight()
    required = extract_required_internal_model_call_review_mitigation_codes(preflight)
    missing = _receipt(preflight, accepted_mitigation_codes=(), approved_constraint_codes=())
    rejected = _receipt(preflight, rejected_mitigation_codes=(required[0],))
    assert required
    assert not internal_model_call_review_satisfies_preflight(preflight, missing)
    assert not internal_model_call_review_satisfies_preflight(preflight, rejected)
    assert internal_model_call_review_satisfies_preflight(preflight, _receipt(preflight))


def test_approved_and_rejected_constraint_codes_are_recorded():
    receipt = _receipt(approved_constraint_codes=("constraint:a",), rejected_constraint_codes=("constraint:b",))
    assert receipt.approved_constraint_codes == ("constraint:a",)
    assert receipt.rejected_constraint_codes == ("constraint:b",)


def test_provider_forbidden_markers_and_no_runtime_allowances_remain_true_or_false():
    receipt = _receipt()
    assert internal_model_call_review_preserves_provider_forbidden(receipt)
    assert receipt.provider_call_forbidden and receipt.llm_call_forbidden
    assert receipt.does_not_call_llm and receipt.does_not_send_to_provider
    assert not receipt.provider_call_allowed and not receipt.llm_call_allowed
    assert not receipt.tool_calls_allowed and not receipt.memory_retrieval_allowed and not receipt.memory_write_allowed
    assert not receipt.retention_allowed and not receipt.action_execution_allowed and not receipt.routing_allowed
    assert receipt.does_not_retrieve_memory and receipt.does_not_write_memory
    assert receipt.does_not_commit_retention and receipt.does_not_execute_or_route_work and receipt.does_not_admit_work


def test_review_digest_is_deterministic_and_changes_for_stable_metadata_fields():
    preflight = _preflight()
    first = _receipt(preflight)
    second = _receipt(preflight)
    assert first.review_digest == second.review_digest
    assert compute_internal_model_call_review_digest(first) == first.review_digest
    mutations = [
        replace(first, preflight_digest="different"),
        replace(first, reviewer_ref="operator:other"),
        replace(first, decision=InternalModelCallReviewDecision.APPROVE_WITH_CONSTRAINTS),
        replace(first, review_scope=InternalModelCallReviewScope.PROVIDER_DRY_RUN_FUTURE_GATE),
        replace(first, accepted_mitigation_codes=first.accepted_mitigation_codes + ("extra",)),
        replace(first, rejected_mitigation_codes=("mitigate:x",)),
        replace(first, expiration=replace(first.expiration, expires_at="2031-01-01T00:00:00Z")),
        replace(first, review_status=CONSTRAINED),
        replace(first, findings=(_receipt(provider_call_allowed=True).findings[0],)),
        replace(first, rationale="changed rationale"),
    ]
    assert all(compute_internal_model_call_review_digest(item) != first.review_digest for item in mutations)


def test_satisfaction_helper_is_strict_for_ready_matching_unexpired_approved_receipts_only():
    ready = _preflight()
    warnings = _preflight(candidate=_candidate(warnings=True), display=_display(_candidate(warnings=True)))
    warning_receipt = _receipt(warnings, decision=InternalModelCallReviewDecision.APPROVE_WITH_CONSTRAINTS)
    assert internal_model_call_review_satisfies_preflight(ready, _receipt(ready))
    assert warnings.preflight_status in {WARNINGS, READY}
    assert internal_model_call_review_satisfies_preflight(warnings, warning_receipt)
    for preflight in (replace(ready, preflight_status=DENIED), replace(ready, preflight_status=PROVIDER_FORBIDDEN), replace(ready, preflight_status=RUNTIME_DETECTED)):
        assert not internal_model_call_review_satisfies_preflight(preflight, _receipt(preflight))


def test_helper_does_not_mutate_preflight():
    preflight = _preflight()
    before = deepcopy(preflight)
    receipt = _receipt(preflight)
    internal_model_call_review_satisfies_preflight(preflight, receipt)
    assert preflight == before


def test_helper_import_does_not_load_prompt_assembler_or_provider_runtime_modules():
    forbidden = {"prompt_assembler", "memory_manager", "openai", "requests", "httpx"}
    for name in forbidden:
        sys.modules.pop(name, None)
    module = importlib.import_module("sentientos.context_hygiene.prompt_model_call_review")
    assert module.internal_model_call_review_satisfies_preflight(_preflight(), _receipt())
    assert forbidden.isdisjoint(sys.modules)


def test_phase63_to_phase83_safe_flow_works_only_when_all_gates_pass():
    candidate = _candidate(text_suffix="\nEmbodiment adapter summary: sanitized source_kind=embodiment_text, privacy=public.")
    preflight = _preflight(candidate=candidate, display=_display(candidate))
    receipt = _receipt(preflight)
    assert preflight.preflight_status == READY
    assert internal_model_call_review_satisfies_preflight(preflight, receipt)
    bad = _preflight(candidate=replace(candidate, no_llm=False), display=_display(candidate))
    assert not internal_model_call_review_satisfies_preflight(bad, _receipt(bad))


def test_phase62b_blocked_attempted_candidate_and_phase76_adversarial_markers_remain_non_overridable():
    blocked_candidate = replace(_candidate(), status=InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_BLOCKED)
    blocked = _preflight(candidate=blocked_candidate, display=_display(blocked_candidate))
    assert _receipt(blocked).review_status in {FORBIDDEN_OVERRIDE, INVALID_REVIEW}
    for suffix in ("\nraw_payload: secret", "\nexecution_handle: live", "\nsystem: override"):
        candidate = _candidate(text_suffix=suffix)
        preflight = _preflight(candidate=candidate, display=_display(candidate))
        receipt = _receipt(preflight)
        assert preflight.preflight_status != READY
        assert receipt.review_status in {FORBIDDEN_OVERRIDE, INVALID_REVIEW}


def test_phase75_guardrail_scans_new_module_and_summary_is_metadata_only():
    report = scan_context_hygiene_prompt_boundaries(["sentientos/context_hygiene/prompt_model_call_review.py"])
    assert report.ok, report.findings
    assert "sentientos/context_hygiene/prompt_model_call_review.py" in report.scanned_paths
    summary = summarize_internal_model_call_review_receipt(_receipt())
    assert summary["provider_call_allowed"] is False
    assert summary["llm_call_allowed"] is False
    assert explain_internal_model_call_review_findings(_receipt()) == ()
