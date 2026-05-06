"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import ast
import subprocess
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
from sentientos.context_hygiene.prompt_adapter_contract import build_prompt_assembly_adapter_payload, build_prompt_assembly_adapter_payload_from_packet
from sentientos.context_hygiene.prompt_constraint_verifier import build_candidate_plan_from_dry_run_envelope, verify_prompt_assembly_constraints
from sentientos.context_hygiene.prompt_dry_run_envelope import build_context_prompt_dry_run_envelope
from sentientos.context_hygiene.prompt_handoff_manifest import build_context_prompt_handoff_manifest
from sentientos.context_hygiene.prompt_materialization_audit import build_prompt_materialization_audit_receipt_from_adapter_payload
from sentientos.context_hygiene.prompt_materialization_policy import (
    PromptMaterializationPolicyReason,
    PromptMaterializationPolicyRing,
    PromptMaterializationPolicyStatus,
    compute_prompt_materialization_policy_digest,
    evaluate_prompt_materialization_policy_from_audit_receipt,
    policy_decision_allows_synthetic_materializer,
)
from sentientos.context_hygiene.prompt_operator_review import (
    PromptOperatorReviewDecision,
    PromptOperatorReviewReceipt,
    PromptOperatorReviewStatus,
    build_prompt_operator_review_receipt_from_policy_decision,
    compute_prompt_operator_review_digest,
    explain_prompt_operator_review_findings,
    extract_required_operator_review_caveat_codes,
    extract_required_operator_review_warning_codes,
    operator_review_accepts_required_caveats,
    operator_review_accepts_required_warnings,
    operator_review_attempts_forbidden_override,
    operator_review_satisfies_policy_decision,
    summarize_prompt_operator_review_receipt,
    validate_prompt_operator_review_receipt,
)
from sentientos.context_hygiene.prompt_preflight import PromptContextEligibility, PromptContextEligibilityStatus, evaluate_context_packet_prompt_eligibility
from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates
from scripts.verify_context_hygiene_prompt_boundaries import DEFAULT_SCAN_TARGETS, scan_file_for_prompt_boundary_violations

NOW = datetime.now(timezone.utc)
SHADOW_FLAGS = {"allow_shadow_policy": True}
REVIEW_FLAGS = {"allow_operator_review_queue": True}


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
    preflight = evaluate_context_packet_prompt_eligibility(packet)
    caveated = PromptContextEligibility(
        eligibility_status=PromptContextEligibilityStatus.PROMPT_ELIGIBLE_WITH_CAVEATS,
        prompt_eligible=True,
        may_be_prompted_only_with_caveats=True,
        caveats=("truth_caveat: operator review",),
        packet_id=packet.context_packet_id,
        included_ref_count=preflight.included_ref_count,
    )
    return build_context_prompt_dry_run_envelope(build_context_prompt_handoff_manifest(packet, caveated))


def _payload(envelope=None, plan=None):
    envelope = envelope or _ready_envelope()
    plan = plan or build_candidate_plan_from_dry_run_envelope(envelope)
    verification = verify_prompt_assembly_constraints(envelope, plan)
    return build_prompt_assembly_adapter_payload(verification, plan)


def _receipt(payload=None):
    return build_prompt_materialization_audit_receipt_from_adapter_payload(payload or _payload())


def _policy_review_required(*, warning_count=1, caveat_count=0):
    decision = evaluate_prompt_materialization_policy_from_audit_receipt(
        _receipt(),
        requested_ring=PromptMaterializationPolicyRing.RING_OPERATOR_REVIEW_QUEUE,
        feature_flag_state=REVIEW_FLAGS,
    )
    decision = replace(decision, warning_count=warning_count, caveat_count=caveat_count)
    digest = compute_prompt_materialization_policy_digest(decision)
    return replace(decision, policy_digest=digest, decision_id=f"policy:test:{digest[:16]}")


def _accepted_receipt(policy=None, *, reviewer="operator:ada", rationale="reviewed warnings"):
    policy = policy or _policy_review_required()
    return build_prompt_operator_review_receipt_from_policy_decision(
        policy,
        reviewer_ref=reviewer,
        decisions=(PromptOperatorReviewDecision.ACCEPT_REQUIRED_WARNINGS, PromptOperatorReviewDecision.ACCEPT_REQUIRED_CAVEATS),
        accepted_warning_codes=extract_required_operator_review_warning_codes(policy),
        accepted_caveat_codes=extract_required_operator_review_caveat_codes(policy),
        expires_at="2030-01-01T00:00:00Z",
        evaluated_at="2029-01-01T00:00:00Z",
        rationale=rationale,
    )


def _denied_policy(reason_code, *, status=PromptMaterializationPolicyStatus.POLICY_DENY, requested_ring=PromptMaterializationPolicyRing.RING_SHADOW_RECEIPT_ONLY, effective_ring=PromptMaterializationPolicyRing.RING_SHADOW_RECEIPT_ONLY):
    policy = _policy_review_required()
    denied = replace(
        policy,
        policy_status=status,
        requested_ring=requested_ring,
        effective_ring=effective_ring,
        allowed=False,
        denied=True,
        requires_operator_review=False,
        allows_shadow_only=False,
        allows_synthetic_materializer=False,
        reasons=(PromptMaterializationPolicyReason(reason_code, f"{reason_code} denial"),),
    )
    digest = compute_prompt_materialization_policy_digest(denied)
    return replace(denied, policy_digest=digest, decision_id=f"policy:deny:{digest[:16]}")


def test_review_receipt_can_be_built_from_policy_operator_review_required_decision():
    policy = _policy_review_required(warning_count=1)
    receipt = _accepted_receipt(policy)
    assert isinstance(receipt, PromptOperatorReviewReceipt)
    assert receipt.policy_decision_id == policy.decision_id
    assert receipt.policy_digest == policy.policy_digest
    assert receipt.review_status == PromptOperatorReviewStatus.REVIEW_ACCEPTED


def test_accept_required_warning_yields_review_accepted():
    policy = _policy_review_required(warning_count=1)
    receipt = _accepted_receipt(policy)
    assert receipt.accepted_warning_codes == extract_required_operator_review_warning_codes(policy)
    assert operator_review_accepts_required_warnings(receipt)
    assert operator_review_satisfies_policy_decision(policy, receipt)


def test_reject_required_warning_yields_review_rejected():
    policy = _policy_review_required(warning_count=1)
    receipt = build_prompt_operator_review_receipt_from_policy_decision(
        policy,
        reviewer_ref="operator:ada",
        decisions=(PromptOperatorReviewDecision.REJECT_REQUIRED_WARNINGS,),
        rejected_warning_codes=extract_required_operator_review_warning_codes(policy),
    )
    assert receipt.review_status == PromptOperatorReviewStatus.REVIEW_REJECTED
    assert not operator_review_satisfies_policy_decision(policy, receipt)


def test_partial_warning_acceptance_yields_review_partially_accepted_but_not_satisfied():
    policy = _policy_review_required(warning_count=2)
    receipt = build_prompt_operator_review_receipt_from_policy_decision(
        policy,
        reviewer_ref="operator:ada",
        decisions=(PromptOperatorReviewDecision.ACCEPT_REQUIRED_WARNINGS,),
        accepted_warning_codes=extract_required_operator_review_warning_codes(policy)[:1],
    )
    assert receipt.review_status == PromptOperatorReviewStatus.REVIEW_PARTIALLY_ACCEPTED
    assert not operator_review_satisfies_policy_decision(policy, receipt)


def test_accepted_and_rejected_caveat_codes_are_recorded():
    policy = _policy_review_required(warning_count=0, caveat_count=2)
    caveats = extract_required_operator_review_caveat_codes(policy)
    accepted = build_prompt_operator_review_receipt_from_policy_decision(
        policy,
        reviewer_ref="operator:ada",
        decisions=(PromptOperatorReviewDecision.ACCEPT_REQUIRED_CAVEATS,),
        accepted_caveat_codes=caveats,
    )
    rejected = build_prompt_operator_review_receipt_from_policy_decision(
        policy,
        reviewer_ref="operator:ada",
        decisions=(PromptOperatorReviewDecision.REJECT_REQUIRED_CAVEATS,),
        rejected_caveat_codes=caveats[:1],
    )
    assert accepted.accepted_caveat_codes == caveats
    assert operator_review_accepts_required_caveats(accepted)
    assert rejected.rejected_caveat_codes == caveats[:1]
    assert rejected.review_status == PromptOperatorReviewStatus.REVIEW_REJECTED


def test_missing_required_warning_or_caveat_acceptance_does_not_satisfy_policy():
    warning_policy = _policy_review_required(warning_count=1, caveat_count=0)
    caveat_policy = _policy_review_required(warning_count=0, caveat_count=1)
    missing_warning = build_prompt_operator_review_receipt_from_policy_decision(
        warning_policy,
        reviewer_ref="operator:ada",
        decisions=(PromptOperatorReviewDecision.ACCEPT_REQUIRED_WARNINGS,),
    )
    missing_caveat = build_prompt_operator_review_receipt_from_policy_decision(
        caveat_policy,
        reviewer_ref="operator:ada",
        decisions=(PromptOperatorReviewDecision.ACCEPT_REQUIRED_CAVEATS,),
    )
    assert not operator_review_satisfies_policy_decision(warning_policy, missing_warning)
    assert not operator_review_satisfies_policy_decision(caveat_policy, missing_caveat)


def test_expired_review_yields_review_expired_and_does_not_satisfy_policy():
    policy = _policy_review_required()
    receipt = build_prompt_operator_review_receipt_from_policy_decision(
        policy,
        reviewer_ref="operator:ada",
        decisions=(PromptOperatorReviewDecision.ACCEPT_REQUIRED_WARNINGS,),
        accepted_warning_codes=extract_required_operator_review_warning_codes(policy),
        expires_at="2025-01-01T00:00:00Z",
        evaluated_at="2026-01-01T00:00:00Z",
    )
    assert receipt.review_status == PromptOperatorReviewStatus.REVIEW_EXPIRED
    assert receipt.expired is True
    assert not operator_review_satisfies_policy_decision(policy, receipt)


def test_policy_digest_and_decision_id_mismatch_do_not_satisfy_policy():
    policy = _policy_review_required()
    receipt = _accepted_receipt(policy)
    assert not operator_review_satisfies_policy_decision(replace(policy, policy_digest="changed"), receipt)
    assert not operator_review_satisfies_policy_decision(replace(policy, decision_id="changed"), receipt)


def test_reviewer_ref_is_required():
    policy = _policy_review_required()
    receipt = build_prompt_operator_review_receipt_from_policy_decision(
        policy,
        decisions=(PromptOperatorReviewDecision.ACCEPT_REQUIRED_WARNINGS,),
        accepted_warning_codes=extract_required_operator_review_warning_codes(policy),
    )
    assert receipt.review_status == PromptOperatorReviewStatus.REVIEW_INVALID
    assert any(finding.code == "reviewer_ref_missing" for finding in receipt.findings)


def test_review_digest_is_deterministic_and_changes_for_stable_contract_fields():
    policy = _policy_review_required(warning_count=1)
    receipt = _accepted_receipt(policy, rationale="stable rationale")
    same = _accepted_receipt(policy, rationale="stable rationale")
    assert receipt.review_digest == same.review_digest
    assert compute_prompt_operator_review_digest(receipt) == receipt.review_digest

    changed_policy = replace(policy, policy_digest="different")
    changed_reviewer = _accepted_receipt(policy, reviewer="operator:grace", rationale="stable rationale")
    changed_decision = build_prompt_operator_review_receipt_from_policy_decision(
        policy,
        reviewer_ref="operator:ada",
        decisions=(PromptOperatorReviewDecision.REQUEST_MORE_EVIDENCE,),
        rationale="stable rationale",
    )
    changed_codes = build_prompt_operator_review_receipt_from_policy_decision(
        policy,
        reviewer_ref="operator:ada",
        decisions=(PromptOperatorReviewDecision.ACCEPT_REQUIRED_WARNINGS,),
        accepted_warning_codes=(),
        rejected_warning_codes=extract_required_operator_review_warning_codes(policy),
        rationale="stable rationale",
    )
    assert _accepted_receipt(changed_policy, rationale="stable rationale").review_digest != receipt.review_digest
    assert changed_reviewer.review_digest != receipt.review_digest
    assert changed_decision.review_digest != receipt.review_digest
    assert changed_codes.review_digest != receipt.review_digest


@pytest.mark.parametrize(
    "reason_code,status",
    [
        ("audit_status_not_ready", PromptMaterializationPolicyStatus.POLICY_DENY),
        ("digest_chain_incomplete", PromptMaterializationPolicyStatus.POLICY_DENY),
        ("audit_runtime_wiring_detected", PromptMaterializationPolicyStatus.POLICY_RUNTIME_WIRING_DETECTED),
        ("forbidden_prompt_marker", PromptMaterializationPolicyStatus.POLICY_DENY),
        ("forbidden_raw_marker", PromptMaterializationPolicyStatus.POLICY_DENY),
        ("runtime_authority_marker", PromptMaterializationPolicyStatus.POLICY_RUNTIME_WIRING_DETECTED),
    ],
)
def test_forbidden_override_of_hard_denial_reasons_is_detected(reason_code, status):
    policy = _denied_policy(reason_code, status=status)
    receipt = _accepted_receipt(policy)
    assert receipt.review_status == PromptOperatorReviewStatus.REVIEW_FORBIDDEN_OVERRIDE_ATTEMPTED
    assert receipt.forbidden_override_attempted is True
    assert operator_review_attempts_forbidden_override(policy, receipt)
    assert not operator_review_satisfies_policy_decision(policy, receipt)


def test_forbidden_override_of_live_internal_llm_capable_ring_is_detected():
    policy = _denied_policy(
        "phase77_ring_forbidden",
        requested_ring=PromptMaterializationPolicyRing.RING_LIVE_LLM_FORBIDDEN,
        effective_ring=PromptMaterializationPolicyRing.RING_LIVE_LLM_FORBIDDEN,
    )
    receipt = _accepted_receipt(policy)
    assert receipt.review_status == PromptOperatorReviewStatus.REVIEW_FORBIDDEN_OVERRIDE_ATTEMPTED
    assert receipt.forbidden_override_attempted is True


def test_operator_review_cannot_allow_shadow_materialization_or_create_prompt_text_or_raw_payload_fields():
    policy = _policy_review_required()
    receipt = _accepted_receipt(policy)
    receipt_data = asdict(receipt)
    assert not policy_decision_allows_synthetic_materializer(policy)
    assert operator_review_satisfies_policy_decision(policy, receipt)
    assert "prompt_text" not in receipt_data
    assert "final_prompt_text" not in receipt_data
    assert "raw_payload" not in receipt_data
    assert "raw_memory_payload" not in receipt_data
    assert not any(key.endswith("_handle") for key in receipt_data)
    assert receipt.review_scope.grants_runtime_authority is False


def test_non_runtime_markers_are_present_and_true():
    receipt = _accepted_receipt(_policy_review_required())
    for marker in (
        "operator_review_receipt_only",
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
        assert getattr(receipt, marker) is True
    assert validate_prompt_operator_review_receipt(receipt) == ()


def test_satisfaction_helper_returns_true_only_for_matching_unexpired_accepted_review_required_policy_decisions():
    policy = _policy_review_required()
    receipt = _accepted_receipt(policy)
    assert operator_review_satisfies_policy_decision(policy, receipt)
    assert not operator_review_satisfies_policy_decision(policy, None)
    assert not operator_review_satisfies_policy_decision(_denied_policy("violations_present"), receipt)


def test_phase63_to_phase78_full_runway_operator_review_receipt_works():
    proposals = build_embodiment_context_candidates(
        [
            {
                "ref_id": "emb:1",
                "source_kind": "embodiment_snapshot",
                "packet_scope": "turn",
                "conversation_scope_id": "conv",
                "task_scope_id": "task",
                "content_summary": "sanitized posture summary",
                "sanitized_context_summary": True,
                "privacy_posture": "low_risk",
                "provenance_refs": ("sensor:summary",),
                "non_authoritative": True,
                "decision_power": "none",
            }
        ]
    )
    packet = build_context_packet_from_candidates(proposals, "turn", "conv", "task", context_mode=ContextMode.RESPONSE, now=NOW)
    payload = build_prompt_assembly_adapter_payload_from_packet(packet)
    receipt = _receipt(payload)
    policy = evaluate_prompt_materialization_policy_from_audit_receipt(
        receipt,
        requested_ring=PromptMaterializationPolicyRing.RING_OPERATOR_REVIEW_QUEUE,
        feature_flag_state=REVIEW_FLAGS,
    )
    reviewed = _accepted_receipt(policy)
    assert policy.policy_status == PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED
    assert reviewed.review_status == PromptOperatorReviewStatus.REVIEW_ACCEPTED
    assert operator_review_satisfies_policy_decision(policy, reviewed)


def test_phase62b_blocked_attempted_candidate_policy_deny_review_forbidden_override_attempted():
    envelope = _envelope_for([_cand("blocked", metadata={"source_kind": "evidence", "pollution_risk": "blocked", "non_authoritative": True, "decision_power": "none"})])
    bad_plan = replace(build_candidate_plan_from_dry_run_envelope(envelope), packet_id="wrong")
    policy = evaluate_prompt_materialization_policy_from_audit_receipt(
        _receipt(_payload(envelope, bad_plan)),
        requested_ring=PromptMaterializationPolicyRing.RING_OPERATOR_REVIEW_QUEUE,
        feature_flag_state=REVIEW_FLAGS,
    )
    reviewed = _accepted_receipt(policy)
    assert policy.policy_status in {PromptMaterializationPolicyStatus.POLICY_DENY, PromptMaterializationPolicyStatus.POLICY_RUNTIME_WIRING_DETECTED}
    assert reviewed.review_status == PromptOperatorReviewStatus.REVIEW_FORBIDDEN_OVERRIDE_ATTEMPTED


def test_phase76_adversarial_forbidden_markers_remain_non_overridable_by_review():
    for code in ("forbidden_prompt_marker", "forbidden_raw_marker", "runtime_authority_marker", "unknown_source_kind"):
        policy = _denied_policy(code)
        reviewed = _accepted_receipt(policy)
        assert reviewed.forbidden_override_attempted is True
        assert not operator_review_satisfies_policy_decision(policy, reviewed)


def test_phase75_guardrail_script_scans_new_review_module():
    assert "sentientos/context_hygiene/prompt_operator_review.py" in DEFAULT_SCAN_TARGETS
    assert scan_file_for_prompt_boundary_violations("sentientos/context_hygiene/prompt_operator_review.py") == ()


def test_import_purity_remains_acceptable_for_review_module():
    result = subprocess.run(
        [sys.executable, "-c", "import sentientos.context_hygiene.prompt_operator_review"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ""


def test_helper_does_not_mutate_policy_decision():
    policy = _policy_review_required()
    before = asdict(policy)
    _accepted_receipt(policy)
    assert asdict(policy) == before


def test_helper_does_not_call_prompt_llm_retrieval_memory_action_retention_or_runtime_functions():
    source = open("sentientos/context_hygiene/prompt_operator_review.py", encoding="utf-8").read()
    tree = ast.parse(source)
    calls = {getattr(node.func, "id", "") or getattr(node.func, "attr", "") for node in ast.walk(tree) if isinstance(node, ast.Call)}
    forbidden_calls = {
        "assemble_prompt",
        "create",
        "retrieve_memory",
        "search_memory",
        "write_memory",
        "save_memory",
        "commit_retention",
        "trigger_feedback",
        "execute_action",
        "route_work",
        "admit_work",
        "execute_work",
    }
    assert not (calls & forbidden_calls)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    forbidden_import_text = ("openai", "memory_manager", "task_executor", "task_admission", "prompt_assembler")
    assert not any(any(token in module for token in forbidden_import_text) for module in imported_modules)


def test_summary_and_findings_are_metadata_only():
    receipt = build_prompt_operator_review_receipt_from_policy_decision(
        _policy_review_required(warning_count=1),
        reviewer_ref="operator:ada",
        decisions=(PromptOperatorReviewDecision.REJECT_REQUIRED_WARNINGS,),
        rejected_warning_codes=("warning:operator_review_queue_requested:1",),
        rationale="Need more evidence before future synthetic-only use.",
    )
    summary = summarize_prompt_operator_review_receipt(receipt)
    findings = explain_prompt_operator_review_findings(receipt)
    assert summary["review_status"] == PromptOperatorReviewStatus.REVIEW_REJECTED
    assert summary["reviewer_ref"] == "operator:ada"
    assert any("required_warning" in finding for finding in findings)
