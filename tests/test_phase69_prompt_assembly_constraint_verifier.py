from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone

from sentientos.context_hygiene.context_packet import ContextMode
from sentientos.context_hygiene.embodiment_context import build_embodiment_context_candidates
from sentientos.context_hygiene.prompt_constraint_verifier import (
    PromptAssemblyCandidateRef,
    PromptAssemblyConstraintVerificationStatus,
    build_candidate_plan_from_dry_run_envelope,
    candidate_plan_contains_no_prompt_text,
    candidate_plan_contains_no_raw_payloads,
    candidate_plan_has_no_runtime_authority,
    explain_prompt_assembly_constraint_violations,
    summarize_prompt_assembly_constraint_verification,
    verify_prompt_assembly_constraints,
)
from sentientos.context_hygiene.prompt_dry_run_envelope import (
    ContextPromptDryRunStatus,
    build_context_prompt_dry_run_envelope,
)
from sentientos.context_hygiene.prompt_handoff_manifest import build_context_prompt_handoff_manifest
from sentientos.context_hygiene.prompt_preflight import PromptContextEligibility, PromptContextEligibilityStatus, evaluate_context_packet_prompt_eligibility
from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates

NOW = datetime.now(timezone.utc)


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


def _blocked_envelope():
    return _envelope_for([_cand("blocked", metadata={"source_kind": "evidence", "pollution_risk": "blocked", "non_authoritative": True, "decision_power": "none"})])


def _not_applicable_envelope():
    return build_context_prompt_dry_run_envelope(build_context_prompt_handoff_manifest(_pkt([])))


def _invalid_envelope():
    packet = replace(_pkt([_cand("bad")]), context_packet_id="")
    return build_context_prompt_dry_run_envelope(build_context_prompt_handoff_manifest(packet))


def _verify(envelope, plan=None):
    return verify_prompt_assembly_constraints(envelope, plan or build_candidate_plan_from_dry_run_envelope(envelope))


def _codes(verification):
    return tuple(v.code for v in verification.violations)


def _with_bad_ref(envelope, ref):
    plan = build_candidate_plan_from_dry_run_envelope(envelope)
    return replace(plan, candidate_refs=plan.candidate_refs + (ref,), intended_ref_ids=plan.intended_ref_ids + (ref.ref_id,))


def test_default_candidate_plan_from_ready_envelope_verifies():
    envelope = _ready_envelope()
    plan = build_candidate_plan_from_dry_run_envelope(envelope)
    verification = _verify(envelope, plan)
    assert verification.status == PromptAssemblyConstraintVerificationStatus.CONSTRAINT_VERIFIED
    assert verification.violations == ()
    assert candidate_plan_contains_no_raw_payloads(plan)
    assert candidate_plan_contains_no_prompt_text(plan)
    assert candidate_plan_has_no_runtime_authority(plan)


def test_default_candidate_plan_from_ready_with_caveats_verifies_with_warnings():
    envelope = _caveated_envelope()
    verification = _verify(envelope)
    assert verification.status == PromptAssemblyConstraintVerificationStatus.CONSTRAINT_VERIFIED_WITH_WARNINGS
    assert verification.warnings
    assert "caveated_dry_run_envelope" in tuple(w.code for w in verification.warnings)


def test_default_candidate_plan_from_blocked_has_no_refs_and_is_not_applicable_safe():
    envelope = _blocked_envelope()
    plan = build_candidate_plan_from_dry_run_envelope(envelope)
    verification = _verify(envelope, plan)
    assert plan.candidate_refs == ()
    assert verification.status == PromptAssemblyConstraintVerificationStatus.CONSTRAINT_NOT_APPLICABLE


def test_default_candidate_plan_from_not_applicable_has_no_refs():
    envelope = _not_applicable_envelope()
    plan = build_candidate_plan_from_dry_run_envelope(envelope)
    assert plan.candidate_refs == ()
    assert _verify(envelope, plan).status == PromptAssemblyConstraintVerificationStatus.CONSTRAINT_NOT_APPLICABLE


def test_default_candidate_plan_from_invalid_manifest_has_no_refs_and_invalid_envelope_status():
    envelope = _invalid_envelope()
    plan = build_candidate_plan_from_dry_run_envelope(envelope)
    assert plan.candidate_refs == ()
    assert _verify(envelope, plan).status == PromptAssemblyConstraintVerificationStatus.CONSTRAINT_INVALID_ENVELOPE


def test_verifier_rejects_identity_digest_and_packet_mismatches():
    envelope = _ready_envelope()
    plan = build_candidate_plan_from_dry_run_envelope(envelope)
    assert "envelope_identity_mismatch" in _codes(_verify(envelope, replace(plan, envelope_id="wrong")))
    assert "envelope_digest_mismatch" in _codes(_verify(envelope, replace(plan, envelope_digest="wrong")))
    assert "packet_identity_mismatch" in _codes(_verify(envelope, replace(plan, packet_id="wrong")))


def test_verifier_rejects_candidate_refs_for_blocked_not_applicable_and_invalid_envelopes():
    bad = PromptAssemblyCandidateRef("x", "evidence", "evidence", "summary")
    assert "blocked_envelope_has_candidate_refs" in _codes(_verify(_blocked_envelope(), _with_bad_ref(_blocked_envelope(), bad)))
    assert "non_applicable_envelope_has_candidate_refs" in _codes(_verify(_not_applicable_envelope(), _with_bad_ref(_not_applicable_envelope(), bad)))
    assert "invalid_envelope_has_candidate_refs" in _codes(_verify(_invalid_envelope(), _with_bad_ref(_invalid_envelope(), bad)))


def test_verifier_rejects_unknown_excluded_and_blocked_ref_ids():
    envelope = _ready_envelope()
    unknown = PromptAssemblyCandidateRef("unknown", "evidence", "evidence", "summary")
    assert "unknown_ref_used" in _codes(_verify(envelope, _with_bad_ref(envelope, unknown)))

    excluded_envelope = replace(envelope, assembly_constraints={**envelope.assembly_constraints, "excluded_ref_ids": ("excluded",)})
    excluded = PromptAssemblyCandidateRef("excluded", "evidence", "evidence", "summary")
    assert "excluded_ref_used" in _codes(_verify(excluded_envelope, _with_bad_ref(excluded_envelope, excluded)))

    blocked_envelope = replace(envelope, assembly_constraints={**envelope.assembly_constraints, "blocked_ref_ids": ("blocked-ref",)})
    blocked = PromptAssemblyCandidateRef("blocked-ref", "evidence", "evidence", "summary")
    assert "blocked_ref_used" in _codes(_verify(blocked_envelope, _with_bad_ref(blocked_envelope, blocked)))


def test_verifier_rejects_missing_caveats_constraints_and_boundaries():
    envelope = _caveated_envelope()
    plan = build_candidate_plan_from_dry_run_envelope(envelope)
    assert "required_caveat_missing" in _codes(_verify(envelope, replace(plan, preserved_caveats=())))
    assert "assembly_constraint_missing" in _codes(_verify(envelope, replace(plan, preserved_constraints={})))

    ref = plan.candidate_refs[0]
    assert "provenance_boundary_missing" in _codes(_verify(envelope, replace(plan, candidate_refs=(replace(ref, provenance_refs=()),))))
    assert "privacy_boundary_missing" in _codes(_verify(envelope, replace(plan, candidate_refs=(replace(ref, privacy_posture=""),))))
    assert "truth_boundary_missing" in _codes(_verify(envelope, replace(plan, preserved_caveats=(), candidate_refs=(replace(ref, contradiction_status="changed"),))))
    assert "safety_boundary_missing" in _codes(_verify(envelope, replace(plan, candidate_refs=(replace(ref, source_kind=""),))))


def test_verifier_rejects_raw_prompt_llm_runtime_and_capability_keys():
    envelope = _ready_envelope()
    plan = build_candidate_plan_from_dry_run_envelope(envelope)
    cases = [
        ({"raw_payload": "x"}, "raw_payload_present"),
        ({"final_prompt_text": "x"}, "final_prompt_text_present"),
        ({"prompt_text": "x"}, "final_prompt_text_present"),
        ({"llm_params": {"model": "x"}}, "llm_call_parameters_present"),
        ({"execution_handle": "h"}, "runtime_authority_present"),
        ({"action_handle": "h"}, "runtime_authority_present"),
        ({"memory_write_capability": True}, "memory_write_capability_present"),
        ({"retention_commit_capability": True}, "retention_commit_capability_present"),
        ({"feedback_trigger_capability": True}, "feedback_trigger_capability_present"),
        ({"action_execution_capability": True}, "action_execution_capability_present"),
        ({"route_work": True}, "route_or_admit_capability_present"),
        ({"admit_work": True}, "route_or_admit_capability_present"),
        ({"execute_work": True}, "route_or_admit_capability_present"),
    ]
    for markers, code in cases:
        assert code in _codes(_verify(envelope, replace(plan, diagnostic_markers=markers)))


def test_verifier_rejects_missing_non_authoritative_marker_and_malformed_candidate_plan():
    envelope = _ready_envelope()
    plan = build_candidate_plan_from_dry_run_envelope(envelope)
    assert "non_authoritative_marker_missing" in _codes(_verify(envelope, replace(plan, non_authoritative=False)))
    malformed = {"plan_id": "bad", "candidate_refs": "not refs"}
    verification = _verify(envelope, malformed)
    assert verification.status == PromptAssemblyConstraintVerificationStatus.CONSTRAINT_INVALID_CANDIDATE_PLAN
    assert "invalid_candidate_plan" in _codes(verification)


def test_verifier_output_includes_compact_violations_and_warnings():
    envelope = _ready_envelope()
    plan = build_candidate_plan_from_dry_run_envelope(envelope)
    failed = _verify(envelope, replace(plan, packet_id="wrong"))
    assert summarize_prompt_assembly_constraint_verification(failed)["violation_codes"] == ("packet_identity_mismatch",)
    assert explain_prompt_assembly_constraint_violations(failed) == ("packet_identity_mismatch:candidate plan packet_id does not match envelope packet_id",)

    caveated = _verify(_caveated_envelope())
    assert summarize_prompt_assembly_constraint_verification(caveated)["warning_codes"] == ("caveated_dry_run_envelope",)


def test_candidate_plan_helper_and_verifier_do_not_mutate_inputs():
    envelope = _ready_envelope()
    before_envelope = deepcopy(asdict(envelope))
    plan = build_candidate_plan_from_dry_run_envelope(envelope)
    assert asdict(envelope) == before_envelope

    before_plan = deepcopy(asdict(plan))
    _ = verify_prompt_assembly_constraints(envelope, plan)
    assert asdict(envelope) == before_envelope
    assert asdict(plan) == before_plan


def test_phase63_to_phase69_embodiment_proposal_pipeline_verifies():
    artifacts = [
        {
            "ref_id": "embodiment-proposal-1",
            "source_kind": "embodiment_proposal",
            "packet_scope": "turn",
            "conversation_scope_id": "conv",
            "task_scope_id": "task",
            "content_summary": "sanitized embodiment proposal summary",
            "provenance_refs": ["prov:embodiment"],
            "sanitized_context_summary": True,
            "decision_power": "none",
            "non_authoritative": True,
            "proposal_status": "reviewable",
        }
    ]
    candidates = build_embodiment_context_candidates(artifacts)
    packet = build_context_packet_from_candidates(candidates, "turn", "conv", "task", now=NOW)
    manifest = build_context_prompt_handoff_manifest(packet)
    envelope = build_context_prompt_dry_run_envelope(manifest)
    plan = build_candidate_plan_from_dry_run_envelope(envelope)
    verification = verify_prompt_assembly_constraints(envelope, plan)
    assert verification.status in {
        PromptAssemblyConstraintVerificationStatus.CONSTRAINT_VERIFIED,
        PromptAssemblyConstraintVerificationStatus.CONSTRAINT_VERIFIED_WITH_WARNINGS,
    }
    assert verification.violations == ()


def test_phase62b_blocked_attempted_candidate_becomes_empty_non_applicable_plan():
    envelope = _blocked_envelope()
    plan = build_candidate_plan_from_dry_run_envelope(envelope)
    verification = verify_prompt_assembly_constraints(envelope, plan)
    assert envelope.dry_run_status == ContextPromptDryRunStatus.DRY_RUN_BLOCKED
    assert plan.candidate_refs == ()
    assert verification.status == PromptAssemblyConstraintVerificationStatus.CONSTRAINT_NOT_APPLICABLE


def test_phase69_helper_imports_remain_pure():
    import sentientos.context_hygiene.prompt_constraint_verifier as mod

    txt = open(mod.__file__, encoding="utf-8").read()
    for forbidden in [
        "prompt_assembler",
        "memory_manager",
        "task_executor",
        "task_admission",
        "action_router",
        "retention_manager",
        "screen_awareness",
        "mic_bridge",
        "vision_tracker",
        "multimodal_tracker",
        "hardware",
        "openai",
        "requests",
    ]:
        assert forbidden not in txt
