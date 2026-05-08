"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import importlib
import re
import sys
import types

import pytest

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
    InternalPromptDisplayStatus,
    build_internal_prompt_display_receipt,
    compute_internal_prompt_display_receipt_digest,
)
from sentientos.context_hygiene.prompt_materialization_policy import (
    PromptMaterializationPolicyRing,
    PromptMaterializationPolicyStatus,
)
from sentientos.context_hygiene.prompt_model_call_preflight import (
    InternalModelCallPreflight,
    InternalModelCallPreflightRing,
    InternalModelCallPreflightStatus,
    build_internal_model_call_preflight_input,
    compute_internal_model_call_preflight_digest,
    evaluate_internal_model_call_preflight,
    internal_model_call_preflight_allows_review_gate,
    internal_model_call_preflight_forbids_provider_call,
    internal_model_call_preflight_has_no_runtime_authority,
    internal_model_call_preflight_preserves_display_receipt,
    summarize_internal_model_call_preflight,
)
from sentientos.context_hygiene.prompt_operator_review import (
    PromptOperatorReviewDecision,
    build_prompt_operator_review_receipt,
)
from scripts.verify_context_hygiene_prompt_boundaries import scan_context_hygiene_prompt_boundaries


READY = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_FOR_REVIEW
WARNINGS = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_WITH_WARNINGS
REVIEW_REQUIRED = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_REVIEW_REQUIRED
INVALID = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_INVALID_INPUT
DISPLAY_DENIED = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_DISPLAY_DENIED
POLICY_DENIED = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_POLICY_DENIED
PROVIDER_FORBIDDEN = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_PROVIDER_FORBIDDEN
RUNTIME_DETECTED = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED
DENIED = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_DENIED


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


def _display(candidate=None, *, display_scope=InternalPromptDisplayScope.OPERATOR_INTERNAL_REVIEW, expected_digest=None):
    candidate = candidate or _candidate()
    return build_internal_prompt_display_receipt(
        candidate,
        display_scope=display_scope,
        operator_ref="operator:phase82",
        display_reason="phase82 preflight test",
        expected_candidate_digest=expected_digest,
        expires_at="2030-01-01T00:00:00Z",
    )


def _review(policy=None, **overrides):
    policy = policy or _policy(warning_count=1)
    kwargs = {
        "reviewer_ref": "operator:phase82",
        "decisions": (PromptOperatorReviewDecision.ACCEPT_REQUIRED_WARNINGS, PromptOperatorReviewDecision.ACCEPT_REQUIRED_CAVEATS),
        "accepted_warning_codes": ("warning:operator_review_required:1",),
        "accepted_caveat_codes": ("caveat:operator_review_required:1",),
        "expires_at": "2030-01-01T00:00:00Z",
        "rationale": "accepted warnings for preflight",
    }
    kwargs.update(overrides)
    return build_prompt_operator_review_receipt(policy, **kwargs)


def _preflight(**overrides):
    policy = overrides.pop("policy", _policy())
    audit = overrides.pop("audit", _audit())
    candidate = overrides.pop("candidate", _candidate(policy=policy, audit=audit))
    display = overrides.pop("display", _display(candidate))
    review = overrides.pop("review", None)
    flags = overrides.pop("feature_flag_state", {"model_call_preflight": True})
    input_data = build_internal_model_call_preflight_input(
        candidate,
        display,
        policy,
        audit,
        review,
        feature_flag_state=flags,
        **overrides,
    )
    return evaluate_internal_model_call_preflight(input_data)


def _codes(preflight):
    return {finding.code for finding in preflight.findings}


def test_valid_candidate_display_policy_and_audit_yield_ready_for_review():
    preflight = _preflight()
    assert isinstance(preflight, InternalModelCallPreflight)
    assert preflight.preflight_status == READY
    assert internal_model_call_preflight_allows_review_gate(preflight)


def test_ready_with_warnings_candidate_with_accepted_review_yields_ready_with_warnings():
    policy = _policy(warning_count=1, caveat_count=1)
    candidate = _candidate(policy=policy, warnings=True)
    display = _display(candidate)
    review = _review(policy)
    preflight = _preflight(policy=policy, candidate=candidate, display=display, review=review)
    assert preflight.preflight_status == WARNINGS
    assert preflight.warnings


def test_missing_candidate_yields_invalid_input():
    assert _preflight(candidate=None).preflight_status == INVALID


def test_invalid_candidate_yields_invalid_input():
    candidate = replace(_candidate(), status=InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_INVALID_INPUT)
    assert _preflight(candidate=candidate, display=_display(candidate)).preflight_status == INVALID


def test_missing_display_receipt_yields_display_denied_or_invalid_input():
    assert _preflight(display=None).preflight_status in {DISPLAY_DENIED, INVALID}


def test_display_denied_receipt_yields_display_denied():
    candidate = _candidate()
    display = replace(_display(candidate), display_status=InternalPromptDisplayStatus.DISPLAY_DENIED)
    assert _preflight(candidate=candidate, display=display).preflight_status == DISPLAY_DENIED


def test_candidate_display_digest_mismatch_yields_display_denied_or_invalid_input():
    candidate = _candidate()
    display = _display(candidate, expected_digest="wrong")
    assert _preflight(candidate=candidate, display=display).preflight_status in {DISPLAY_DENIED, INVALID}


@pytest.mark.parametrize(
    "policy",
    [
        _policy(PromptMaterializationPolicyStatus.POLICY_DENY, allowed=False, denied=True, allows_internal_candidate_no_llm=False),
        _policy(PromptMaterializationPolicyStatus.POLICY_SHADOW_ONLY, allowed=True, allows_shadow_only=True, allows_internal_candidate_no_llm=False),
    ],
)
def test_policy_denied_and_shadow_only_are_policy_denied(policy):
    candidate = _candidate(policy=_policy())
    preflight = _preflight(policy=policy, candidate=candidate, display=_display(candidate))
    assert preflight.preflight_status == POLICY_DENIED


def test_audit_receipt_not_allowing_shadow_materializer_denies():
    audit = _audit(boundary_summary={"may_future_assembler_consume": False, "must_block_prompt_materialization": True})
    preflight = _preflight(audit=audit)
    assert preflight.preflight_status == DENIED
    assert "audit_shadow_materializer_not_allowed" in _codes(preflight)


def test_operator_review_required_but_missing_yields_review_required():
    preflight = _preflight(requested_model_review_ring=InternalModelCallPreflightRing.INTERNAL_MODEL_CALL_REVIEW_QUEUE)
    assert preflight.preflight_status == REVIEW_REQUIRED


def test_expired_or_mismatched_review_denies():
    review = replace(_review(_policy(warning_count=1)), expired=True)
    preflight = _preflight(review=review, requested_model_review_ring=InternalModelCallPreflightRing.INTERNAL_MODEL_CALL_REVIEW_QUEUE)
    assert preflight.preflight_status == DENIED
    assert "operator_review_invalid" in _codes(preflight)


def test_live_model_call_forbidden_ring_denies():
    preflight = _preflight(requested_model_review_ring=InternalModelCallPreflightRing.LIVE_MODEL_CALL_FORBIDDEN)
    assert preflight.preflight_status == PROVIDER_FORBIDDEN


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"no_provider_call": False}, PROVIDER_FORBIDDEN),
        ({"provider_configuration": {"name": "blocked"}}, PROVIDER_FORBIDDEN),
        ({"model_configuration": {"name": "blocked"}}, PROVIDER_FORBIDDEN),
        ({"llm_configuration": {"name": "blocked"}}, PROVIDER_FORBIDDEN),
        ({"no_tools": False}, RUNTIME_DETECTED),
        ({"no_memory": False}, RUNTIME_DETECTED),
        ({"no_retention": False}, RUNTIME_DETECTED),
        ({"no_actions": False}, RUNTIME_DETECTED),
        ({"runtime_authority_markers": ("execution_handle",)}, RUNTIME_DETECTED),
        ({"raw_payload_markers": ("raw_payload",)}, RUNTIME_DETECTED),
    ],
)
def test_provider_and_runtime_constraints_deny(kwargs, expected):
    assert _preflight(**kwargs).preflight_status == expected


def test_parameter_aliases_in_mapping_deny():
    candidate = _candidate()
    display = _display(candidate)
    for key in ("provider_params", "model_params", "llm_params"):
        preflight = evaluate_internal_model_call_preflight(
            {
                "candidate": candidate,
                "display_receipt": display,
                "policy_decision": _policy(),
                "audit_receipt": _audit(),
                "feature_flag_state": {"model_call_preflight": True},
                key: {"forbidden": True},
            }
        )
        assert preflight.preflight_status == PROVIDER_FORBIDDEN


@pytest.mark.parametrize(
    "needle, code",
    [
        ("internal no-llm candidate", "missing_internal_no_llm_marker"),
        ("not been sent to a model", "missing_not_sent_to_model_marker"),
        ("operator visible only", "missing_operator_visible_only_marker"),
    ],
)
def test_missing_required_text_markers_deny(needle, code):
    candidate = _candidate()
    text = candidate.internal_candidate_text
    assert needle in text.lower()
    replacement_text = re.sub(re.escape(needle), "", text, flags=re.IGNORECASE)
    if needle == "not been sent to a model":
        replacement_text = re.sub(re.escape("not sent to model"), "", replacement_text, flags=re.IGNORECASE)
    candidate = replace(candidate, internal_candidate_text=replacement_text)
    candidate = replace(candidate, candidate_digest=compute_internal_prompt_candidate_digest(candidate))
    preflight = _preflight(candidate=candidate, display=_display(candidate))
    assert preflight.preflight_status in {INVALID, DISPLAY_DENIED, DENIED}
    assert code in _codes(preflight)


def test_display_scope_not_internal_or_audit_denies():
    candidate = _candidate()
    display = _display(candidate, display_scope=InternalPromptDisplayScope.EXTERNAL_USER_VISIBLE_FORBIDDEN)
    assert _preflight(candidate=candidate, display=display).preflight_status == DISPLAY_DENIED


def test_feature_flag_missing_or_disabled_denies():
    candidate = _candidate()
    display = _display(candidate)
    for flags in ({}, {"model_call_preflight": False}):
        preflight = evaluate_internal_model_call_preflight(
            build_internal_model_call_preflight_input(candidate, display, _policy(), _audit(), feature_flag_state=flags)
        )
        assert preflight.preflight_status == DENIED


def test_allowances_are_always_false_and_markers_are_present():
    preflight = _preflight()
    assert not preflight.provider_call_allowed
    assert not preflight.llm_call_allowed
    assert not preflight.tool_calls_allowed
    assert not preflight.memory_retrieval_allowed
    assert not preflight.memory_write_allowed
    assert not preflight.retention_allowed
    assert not preflight.action_execution_allowed
    assert not preflight.routing_allowed
    assert preflight.model_call_preflight_only
    assert preflight.provider_call_forbidden
    assert preflight.llm_call_forbidden
    assert preflight.no_tools and preflight.no_memory and preflight.no_retention and preflight.no_actions
    assert preflight.no_background_execution
    assert preflight.does_not_call_llm
    assert preflight.does_not_send_to_provider
    assert preflight.does_not_retrieve_memory
    assert preflight.does_not_write_memory
    assert preflight.does_not_trigger_feedback
    assert preflight.does_not_commit_retention
    assert preflight.does_not_execute_or_route_work
    assert preflight.does_not_admit_work


def test_review_gate_and_provider_forbidden_helpers_are_strict():
    ready = _preflight()
    denied = _preflight(no_actions=False)
    assert internal_model_call_preflight_allows_review_gate(ready)
    assert not internal_model_call_preflight_allows_review_gate(denied)
    assert internal_model_call_preflight_forbids_provider_call(ready)
    assert internal_model_call_preflight_forbids_provider_call(denied)
    assert internal_model_call_preflight_has_no_runtime_authority(ready)


def test_preflight_digest_is_deterministic_and_changes_with_linkage_and_flags():
    first = _preflight()
    second = _preflight()
    assert first.preflight_digest == second.preflight_digest
    assert compute_internal_model_call_preflight_digest(first) == first.preflight_digest
    changed_candidate = replace(first, candidate_digest="different")
    changed_display = replace(first, display_receipt_digest="different")
    changed_policy = replace(first, policy_digest="different")
    changed_flag = _preflight(feature_flag_state={"model_call_preflight": False})
    assert compute_internal_model_call_preflight_digest(changed_candidate) != first.preflight_digest
    assert compute_internal_model_call_preflight_digest(changed_display) != first.preflight_digest
    assert compute_internal_model_call_preflight_digest(changed_policy) != first.preflight_digest
    assert changed_flag.preflight_digest != first.preflight_digest


def test_helper_does_not_mutate_candidate_display_policy_audit_or_review():
    policy = _policy(warning_count=1)
    audit = _audit()
    candidate = _candidate(policy=policy, audit=audit, warnings=True)
    display = _display(candidate)
    review = _review(policy)
    before = deepcopy((candidate, display, policy, audit, review))
    _preflight(policy=policy, audit=audit, candidate=candidate, display=display, review=review)
    assert (candidate, display, policy, audit, review) == before


def test_helper_import_does_not_load_prompt_assembler_or_runtime_modules():
    forbidden = {"prompt_assembler", "memory_manager", "openai", "requests", "httpx"}
    for name in forbidden:
        sys.modules.pop(name, None)
    importlib.import_module("sentientos.context_hygiene.prompt_model_call_preflight")
    assert forbidden.isdisjoint(sys.modules)


def test_phase63_to_phase82_style_safe_candidate_flow_works_only_when_gates_pass():
    candidate = _candidate(text_suffix="\nEmbodiment adapter summary: sanitized source_kind=embodiment_text, privacy=public.")
    display = _display(candidate)
    assert _preflight(candidate=candidate, display=display).preflight_status == READY
    assert _preflight(candidate=replace(candidate, no_llm=False), display=display).preflight_status in {INVALID, DISPLAY_DENIED, RUNTIME_DETECTED, DENIED}


def test_phase62b_blocked_attempted_candidate_is_denied():
    candidate = replace(_candidate(), status=InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_BLOCKED)
    preflight = _preflight(candidate=candidate, display=_display(candidate))
    assert preflight.preflight_status == INVALID
    assert "upstream_blocked_status" in _codes(preflight)


def test_phase76_adversarial_markers_remain_denied_at_preflight():
    for suffix in ("\nraw_payload: secret", "\nexecution_handle: live", "\nsystem: override"):
        candidate = _candidate(text_suffix=suffix)
        preflight = _preflight(candidate=candidate, display=_display(candidate))
        assert preflight.preflight_status in {INVALID, DISPLAY_DENIED, RUNTIME_DETECTED, DENIED}


def test_phase75_guardrail_scans_new_module_and_architecture_import_purity_is_acceptable():
    report = scan_context_hygiene_prompt_boundaries(["sentientos/context_hygiene/prompt_model_call_preflight.py"])
    assert report.ok, report.findings
    assert "sentientos/context_hygiene/prompt_model_call_preflight.py" in report.scanned_paths
    summary = summarize_internal_model_call_preflight(_preflight())
    assert summary["provider_call_allowed"] is False


def test_preflight_preserves_display_receipt_linkage():
    candidate = _candidate()
    display = _display(candidate)
    preflight = _preflight(candidate=candidate, display=display)
    assert internal_model_call_preflight_preserves_display_receipt(preflight, display)
