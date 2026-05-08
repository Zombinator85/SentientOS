"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import sys
import types

import pytest

tts_stub = types.ModuleType("tts_bridge")
tts_stub.speak = lambda *args, **kwargs: None
sys.modules.setdefault("tts_bridge", tts_stub)

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from sentientos.context_hygiene.context_packet import ContextMode
from sentientos.context_hygiene.embodiment_context import build_embodiment_context_candidates
from sentientos.context_hygiene.prompt_adapter_contract import build_prompt_assembly_adapter_payload
from sentientos.context_hygiene.prompt_constraint_verifier import build_candidate_plan_from_dry_run_envelope, verify_prompt_assembly_constraints
from sentientos.context_hygiene.prompt_dry_run_envelope import build_context_prompt_dry_run_envelope
from sentientos.context_hygiene.prompt_handoff_manifest import build_context_prompt_handoff_manifest
from sentientos.context_hygiene.prompt_materialization_audit import (
    PromptMaterializationAuditStatus,
    build_prompt_materialization_audit_receipt_from_adapter_payload,
    build_prompt_materialization_audit_receipt_from_packet,
)
from sentientos.context_hygiene.prompt_materialization_policy import (
    PromptMaterializationPolicyInput,
    PromptMaterializationPolicyRing,
    PromptMaterializationPolicyStatus,
    build_prompt_materialization_policy_input,
    compute_prompt_materialization_policy_digest,
    evaluate_prompt_materialization_policy,
    evaluate_prompt_materialization_policy_from_audit_receipt,
    explain_prompt_materialization_policy_reasons,
    policy_decision_allows_shadow_only,
    policy_decision_allows_synthetic_materializer,
    policy_decision_allows_internal_candidate_no_llm,
    policy_decision_denies_materialization,
    policy_decision_requires_operator_review,
    summarize_prompt_materialization_policy_decision,
)
from sentientos.context_hygiene.prompt_preflight import PromptContextEligibility, PromptContextEligibilityStatus, evaluate_context_packet_prompt_eligibility
from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates

NOW = datetime.now(timezone.utc)
SHADOW_FLAGS = {"allow_shadow_policy": True}
SYNTH_FLAGS = {"allow_synthetic_fixture_policy": True}
REVIEW_FLAGS = {"allow_operator_review_queue": True}
INTERNAL_FLAGS = {"internal_no_llm_candidate": True}


def _cand(ref_id="r", ref_type="evidence", metadata=None, truth_ingress_status="allowed", contradiction_status="unknown"):
    return ContextCandidate(
        ref_id=ref_id,
        ref_type=ref_type,
        packet_scope="turn",
        conversation_scope_id="conv",
        task_scope_id="task",
        provenance_refs=("prov:1",),
        source_locator="src",
        summary="packet-safe summary",
        already_sanitized_context_summary=True,
        truth_ingress_status=truth_ingress_status,
        contradiction_status=contradiction_status,
        metadata=metadata or {"source_kind": "evidence", "privacy_posture": "public", "non_authoritative": True, "decision_power": "none"},
    )


def _pkt(cands):
    return build_context_packet_from_candidates(cands, "turn", "conv", "task", context_mode=ContextMode.RESPONSE, now=NOW)


def _envelope_for(cands):
    return build_context_prompt_dry_run_envelope(build_context_prompt_handoff_manifest(_pkt(cands)))


def _ready_envelope():
    return _envelope_for([_cand("ready")])


def _caveated_envelope():
    packet = _pkt([_cand("caveat")])
    pre = evaluate_context_packet_prompt_eligibility(packet)
    caveated = PromptContextEligibility(
        eligibility_status=PromptContextEligibilityStatus.PROMPT_ELIGIBLE_WITH_CAVEATS,
        prompt_eligible=True,
        may_be_prompted_only_with_caveats=True,
        caveats=("truth_caveat: operator review",),
        packet_id=packet.context_packet_id,
        included_ref_count=pre.included_ref_count,
    )
    return build_context_prompt_dry_run_envelope(build_context_prompt_handoff_manifest(packet, caveated))


def _not_applicable_envelope():
    return build_context_prompt_dry_run_envelope(build_context_prompt_handoff_manifest(_pkt([])))


def _payload(envelope=None, plan=None):
    envelope = envelope or _ready_envelope()
    plan = plan or build_candidate_plan_from_dry_run_envelope(envelope)
    verification = verify_prompt_assembly_constraints(envelope, plan)
    return build_prompt_assembly_adapter_payload(verification, plan), verification, plan


def _blocked_payload():
    envelope = _ready_envelope()
    bad_plan = replace(build_candidate_plan_from_dry_run_envelope(envelope), packet_id="wrong")
    return _payload(envelope, bad_plan)[0]


def _receipt(payload=None):
    payload = payload or _payload()[0]
    return build_prompt_materialization_audit_receipt_from_adapter_payload(payload)


def _decision(receipt=None, **kwargs):
    receipt = receipt or _receipt()
    kwargs.setdefault("requested_ring", PromptMaterializationPolicyRing.RING_SHADOW_RECEIPT_ONLY)
    kwargs.setdefault("feature_flag_state", SHADOW_FLAGS)
    return evaluate_prompt_materialization_policy_from_audit_receipt(receipt, **kwargs)


def _policy_input(receipt=None, **kwargs):
    receipt = receipt or _receipt()
    kwargs.setdefault("requested_ring", PromptMaterializationPolicyRing.RING_SHADOW_RECEIPT_ONLY)
    kwargs.setdefault("feature_flag_state", SHADOW_FLAGS)
    return build_prompt_materialization_policy_input(receipt, **kwargs)


def test_malformed_input_yields_policy_invalid_input():
    decision = evaluate_prompt_materialization_policy(object())
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_INVALID_INPUT
    assert policy_decision_denies_materialization(decision)


def test_missing_audit_receipt_yields_policy_deny_or_invalid_input():
    decision = evaluate_prompt_materialization_policy(PromptMaterializationPolicyInput(feature_flag_state=SHADOW_FLAGS))
    assert decision.policy_status in {PromptMaterializationPolicyStatus.POLICY_DENY, PromptMaterializationPolicyStatus.POLICY_INVALID_INPUT}


def test_blocked_audit_receipt_yields_policy_deny():
    decision = _decision(_receipt(_blocked_payload()))
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_DENY


def test_not_applicable_audit_receipt_yields_policy_deny():
    decision = _decision(_receipt(_payload(_not_applicable_envelope())[0]))
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_DENY


def test_invalid_chain_audit_receipt_yields_policy_deny():
    data = asdict(_receipt())
    data["digest_chain_complete"] = False
    data["digest_chain"] = {**data["digest_chain"], "complete": False, "missing": ("shadow_blueprint_digest",)}
    decision = _decision(data)
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_DENY


def test_runtime_wiring_audit_receipt_yields_policy_runtime_wiring_detected():
    policy_input = _policy_input(audit_status=PromptMaterializationAuditStatus.AUDIT_RUNTIME_WIRING_DETECTED, audit_allows_shadow_materializer=False)
    decision = evaluate_prompt_materialization_policy(policy_input)
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_RUNTIME_WIRING_DETECTED


def test_audit_receipt_that_does_not_allow_shadow_materializer_yields_policy_deny():
    data = asdict(_receipt())
    data["boundary_summary"] = {**data["boundary_summary"], "must_block_prompt_materialization": True}
    decision = _decision(data)
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_DENY


def test_complete_ready_receipt_shadow_ring_feature_enabled_yields_policy_shadow_only():
    decision = _decision()
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_SHADOW_ONLY
    assert policy_decision_allows_shadow_only(decision)
    assert not policy_decision_allows_synthetic_materializer(decision)


def test_ready_with_warnings_review_required_caveat_yields_operator_review_required():
    decision = _decision(_receipt(_payload(_caveated_envelope())[0]), requested_ring=PromptMaterializationPolicyRing.RING_OPERATOR_REVIEW_QUEUE, feature_flag_state=REVIEW_FLAGS)
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED
    assert policy_decision_requires_operator_review(decision)


def test_missing_feature_flag_yields_policy_deny():
    decision = _decision(feature_flag_state={})
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_DENY


def test_disabled_feature_flag_yields_policy_deny():
    decision = _decision(feature_flag_state={"allow_shadow_policy": False})
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_DENY


@pytest.mark.parametrize("ring", [PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM, PromptMaterializationPolicyRing.RING_LIVE_LLM_FORBIDDEN])
def test_requested_live_internal_or_llm_capable_ring_yields_policy_deny(ring):
    decision = _decision(requested_ring=ring, feature_flag_state={})
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_DENY


def test_synthetic_materialization_without_synthetic_fixture_only_yields_policy_deny():
    decision = _decision(requested_ring=PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY, feature_flag_state=SYNTH_FLAGS)
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_DENY


def test_synthetic_fixture_complete_ready_receipt_explicit_flag_yields_policy_allowed():
    decision = _decision(requested_ring=PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY, synthetic_fixture_only=True, feature_flag_state=SYNTH_FLAGS)
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_SYNTHETIC_MATERIALIZATION_ALLOWED
    assert policy_decision_allows_synthetic_materializer(decision)


@pytest.mark.parametrize("marker", ["prompt_text", "raw_payload", "execution_handle"])
def test_adversarial_forbidden_markers_deny_at_policy_layer(marker):
    policy_input = asdict(_policy_input())
    policy_input[marker] = "blocked"
    decision = evaluate_prompt_materialization_policy(policy_input)
    assert decision.policy_status in {PromptMaterializationPolicyStatus.POLICY_DENY, PromptMaterializationPolicyStatus.POLICY_RUNTIME_WIRING_DETECTED}


def test_violation_present_yields_policy_deny():
    policy_input = _policy_input(violations=({"code": "v", "detail": "blocking"},))
    decision = evaluate_prompt_materialization_policy(policy_input)
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_DENY


def test_warning_requiring_review_without_operator_review_yields_operator_review_required():
    policy_input = _policy_input(
        requested_ring=PromptMaterializationPolicyRing.RING_OPERATOR_REVIEW_QUEUE,
        feature_flag_state=REVIEW_FLAGS,
        warnings=({"code": "operator_review_required", "detail": "requires review"},),
    )
    decision = evaluate_prompt_materialization_policy(policy_input)
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED


def test_warning_requiring_review_with_accepted_review_may_allow_synthetic_fixture():
    policy_input = _policy_input(
        requested_ring=PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY,
        synthetic_fixture_only=True,
        feature_flag_state=SYNTH_FLAGS,
        warnings=({"code": "operator_review_required", "detail": "requires review"},),
        operator_review_present=True,
        operator_review_decision="accepted",
    )
    decision = evaluate_prompt_materialization_policy(policy_input)
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_SYNTHETIC_MATERIALIZATION_ALLOWED


def test_unknown_source_kind_yields_policy_deny():
    policy_input = _policy_input(source_kind_summary={"mystery_kind": 1})
    decision = evaluate_prompt_materialization_policy(policy_input)
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_DENY


def test_unknown_requested_ring_yields_policy_deny():
    decision = _decision(requested_ring="ring_unlisted", feature_flag_state={"allow_shadow_policy": True})
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_DENY


def test_decision_includes_required_non_runtime_markers():
    decision = _decision()
    for marker in (
        "policy_decision_only",
        "policy_enforcement_not_included",
        "does_not_materialize_prompt_text",
        "does_not_assemble_prompt",
        "does_not_contain_final_prompt_text",
        "does_not_call_llm",
        "does_not_retrieve_memory",
        "does_not_write_memory",
        "does_not_trigger_feedback",
        "does_not_commit_retention",
        "does_not_execute_or_route_work",
        "does_not_admit_work",
    ):
        assert getattr(decision, marker) is True
        assert getattr(decision.boundary, marker) is True
    assert decision.forbids_live_llm and decision.forbids_memory_retrieval and decision.forbids_action_execution


def test_decision_digest_is_deterministic():
    receipt = _receipt()
    first = _decision(receipt)
    second = _decision(receipt)
    assert first.policy_digest == second.policy_digest
    assert first.policy_digest == compute_prompt_materialization_policy_digest(first)


def test_decision_digest_changes_when_receipt_digest_changes():
    base = _decision()
    policy_input = _policy_input(receipt_digest="different")
    changed = evaluate_prompt_materialization_policy(policy_input)
    assert base.policy_digest != changed.policy_digest


def test_decision_digest_changes_when_feature_flag_state_changes():
    base = _decision()
    changed = _decision(feature_flag_state={"allow_shadow_policy": False})
    assert base.policy_digest != changed.policy_digest


def test_decision_digest_changes_when_operator_review_state_changes():
    base = _decision(_receipt(_payload(_caveated_envelope())[0]), requested_ring=PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY, synthetic_fixture_only=True, feature_flag_state=SYNTH_FLAGS)
    changed = _decision(_receipt(_payload(_caveated_envelope())[0]), requested_ring=PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY, synthetic_fixture_only=True, feature_flag_state=SYNTH_FLAGS, operator_review_present=True, operator_review_decision="accepted")
    assert base.policy_digest != changed.policy_digest


def test_decision_digest_changes_when_synthetic_fixture_only_changes():
    base = _decision(requested_ring=PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY, feature_flag_state=SYNTH_FLAGS)
    changed = _decision(requested_ring=PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY, synthetic_fixture_only=True, feature_flag_state=SYNTH_FLAGS)
    assert base.policy_digest != changed.policy_digest


def test_summary_and_explanation_helpers_are_deterministic():
    decision = _decision()
    assert summarize_prompt_materialization_policy_decision(decision) == summarize_prompt_materialization_policy_decision(decision)
    assert explain_prompt_materialization_policy_reasons(decision) == explain_prompt_materialization_policy_reasons(decision)


def test_policy_helper_does_not_mutate_audit_receipt():
    receipt = _receipt()
    before = deepcopy(asdict(receipt))
    _ = _decision(receipt)
    assert asdict(receipt) == before


def test_policy_helper_does_not_call_assemble_prompt(monkeypatch):
    import prompt_assembler as pa

    def fail(*args, **kwargs):
        raise AssertionError("assemble_prompt must not be called by policy")

    monkeypatch.setattr(pa, "assemble_prompt", fail, raising=False)
    decision = _decision()
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_SHADOW_ONLY


def test_policy_helper_does_not_call_runtime_functions(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("runtime function must not be called")

    monkeypatch.setitem(sys.modules, "memory_manager", types.SimpleNamespace(retrieve_memory=forbidden, write_memory=forbidden))
    decision = _decision()
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_SHADOW_ONLY
    assert calls == []


def test_phase63_to_phase77_shadow_only_pipeline_works():
    artifact = {
        "ref_id": "embodiment-proposal-1",
        "source_kind": "embodiment_proposal",
        "packet_scope": "turn",
        "conversation_scope_id": "conv",
        "task_scope_id": "task",
        "content_summary": "sanitized proposal summary",
        "provenance_refs": ["prov:1"],
        "sanitized_context_summary": True,
        "decision_power": "none",
        "non_authoritative": True,
        "proposal_status": "reviewable",
        "privacy_posture": "public",
    }
    candidates = build_embodiment_context_candidates([artifact])
    packet = build_context_packet_from_candidates(candidates, "turn", "conv", "task", context_mode=ContextMode.RESPONSE, now=NOW)
    preflight = evaluate_context_packet_prompt_eligibility(packet)
    receipt = build_prompt_materialization_audit_receipt_from_packet(packet, preflight)
    decision = evaluate_prompt_materialization_policy_from_audit_receipt(receipt, requested_ring=PromptMaterializationPolicyRing.RING_SHADOW_METADATA_ONLY, feature_flag_state=SHADOW_FLAGS)
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_SHADOW_ONLY


def test_phase62b_blocked_attempted_candidate_to_blocked_audit_receipt_to_policy_deny():
    candidate = _cand("blocked", truth_ingress_status="blocked", metadata={"source_kind": "evidence", "privacy_posture": "public", "non_authoritative": True, "decision_power": "none"})
    packet = _pkt([candidate])
    receipt = build_prompt_materialization_audit_receipt_from_packet(packet)
    decision = evaluate_prompt_materialization_policy_from_audit_receipt(receipt, requested_ring=PromptMaterializationPolicyRing.RING_SHADOW_RECEIPT_ONLY, feature_flag_state=SHADOW_FLAGS)
    assert receipt.audit_status in {PromptMaterializationAuditStatus.AUDIT_BLOCKED, PromptMaterializationAuditStatus.AUDIT_NOT_APPLICABLE}
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_DENY


def test_phase75_guardrail_default_targets_include_policy_module():
    import scripts.verify_context_hygiene_prompt_boundaries as guardrails

    assert "sentientos/context_hygiene/prompt_materialization_policy.py" in guardrails.DEFAULT_SCAN_TARGETS


def test_import_purity_for_policy_module():
    import importlib
    import logging

    before = len(logging.getLogger().handlers)
    importlib.import_module("sentientos.context_hygiene.prompt_materialization_policy")
    after = len(logging.getLogger().handlers)
    assert before == after


def test_internal_no_llm_candidate_ring_allowed_only_with_explicit_non_runtime_markers():
    decision = _decision(
        requested_ring=PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM,
        feature_flag_state=INTERNAL_FLAGS,
        no_runtime_markers={"internal_only": True, "operator_visible_only": True, "no_llm": True},
    )
    assert decision.policy_status == PromptMaterializationPolicyStatus.POLICY_INTERNAL_CANDIDATE_NO_LLM_ALLOWED
    assert policy_decision_allows_internal_candidate_no_llm(decision)
    assert decision.does_not_call_llm
    assert decision.does_not_retrieve_memory
    assert decision.does_not_write_memory
    assert decision.does_not_execute_or_route_work


def test_internal_no_llm_candidate_ring_denies_without_explicit_feature_or_markers():
    missing_flag = _decision(
        requested_ring=PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM,
        feature_flag_state={},
        no_runtime_markers={"internal_only": True, "operator_visible_only": True, "no_llm": True},
    )
    missing_marker = _decision(
        requested_ring=PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM,
        feature_flag_state=INTERNAL_FLAGS,
        no_runtime_markers={"internal_only": True, "operator_visible_only": True},
    )
    assert policy_decision_denies_materialization(missing_flag)
    assert policy_decision_denies_materialization(missing_marker)
