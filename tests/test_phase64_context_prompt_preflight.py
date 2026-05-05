from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from sentientos.context_hygiene.context_packet import ContextMode, ContextPacketItem, ContradictionStatus, FreshnessStatus, PollutionRisk
from sentientos.context_hygiene.embodiment_context import build_embodiment_context_candidates
from sentientos.context_hygiene.prompt_preflight import (
    PromptContextEligibilityStatus,
    evaluate_context_packet_prompt_eligibility,
)
from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates


NOW = datetime.now(timezone.utc)


def _cand(ref_id: str = "c1", ref_type: str = "claim", **kwargs):
    base = ContextCandidate(
        ref_id=ref_id,
        ref_type=ref_type,
        packet_scope="turn",
        conversation_scope_id="conv",
        task_scope_id="task",
        summary="s",
        provenance_refs=("p1",),
        source_locator="loc",
        freshness_status="fresh",
        contradiction_status="none",
        truth_ingress_status="allowed",
        already_sanitized_context_summary=True,
    )
    return replace(base, **kwargs)


def _pkt(cands):
    return build_context_packet_from_candidates(cands, "turn", "conv", "task", context_mode=ContextMode.RESPONSE, now=NOW)


def test_phase64_prompt_preflight_contract_and_purity():
    clean = _pkt([_cand("clean")])
    r = evaluate_context_packet_prompt_eligibility(clean)
    assert r.eligibility_status == PromptContextEligibilityStatus.PROMPT_ELIGIBLE

    high_priv = replace(_pkt([_cand("p", metadata={"source_kind": "embodiment_snapshot", "privacy_posture": "privacy_sensitive", "sanitized_context_summary": True, "allow_context_privacy_sensitive": True})]), pollution_risk=PollutionRisk.HIGH)
    assert evaluate_context_packet_prompt_eligibility(high_priv).eligibility_status == PromptContextEligibilityStatus.PROMPT_ELIGIBLE_WITH_CAVEATS

    for posture, allow in [("biometric_or_emotion_sensitive", "allow_context_biometric_or_emotion"), ("raw_retention_sensitive", "allow_context_raw_retention")]:
        pkt = replace(_pkt([_cand("x" + posture, metadata={"source_kind": "embodiment_snapshot", "privacy_posture": posture, "sanitized_context_summary": True, allow: True})]), pollution_risk=PollutionRisk.HIGH)
        assert evaluate_context_packet_prompt_eligibility(pkt).eligibility_status == PromptContextEligibilityStatus.PROMPT_ELIGIBLE_WITH_CAVEATS

    assert evaluate_context_packet_prompt_eligibility(replace(clean, pollution_risk=PollutionRisk.BLOCKED)).eligibility_status == PromptContextEligibilityStatus.PROMPT_INELIGIBLE_BLOCKED_RISK
    blocked_ref = replace(clean, included_claim_refs=(ContextPacketItem("b", "claim", {"provenance_refs": ["p"], "source_kind": "embodiment_snapshot", "pollution_risk": "blocked"}),))
    assert evaluate_context_packet_prompt_eligibility(blocked_ref).eligibility_status == PromptContextEligibilityStatus.PROMPT_INELIGIBLE_BLOCKED_RISK
    assert evaluate_context_packet_prompt_eligibility(replace(clean, provenance_complete=False)).eligibility_status == PromptContextEligibilityStatus.PROMPT_INELIGIBLE_PROVENANCE_GAP
    missing_prov = replace(clean, included_claim_refs=(ContextPacketItem("np", "claim", {}),))
    assert evaluate_context_packet_prompt_eligibility(missing_prov).eligibility_status == PromptContextEligibilityStatus.PROMPT_INELIGIBLE_SCHEMA_VIOLATION
    contra = replace(clean, contradiction_status=ContradictionStatus.CONTRADICTED)
    assert evaluate_context_packet_prompt_eligibility(contra).eligibility_status == PromptContextEligibilityStatus.PROMPT_INELIGIBLE_TRUTH_GAP

    unsanitized = replace(clean, included_claim_refs=(ContextPacketItem("u", "claim", {"provenance_refs": ["p"], "source_kind": "embodiment_snapshot", "privacy_posture": "privacy_sensitive", "sanitized_context_summary": False}),))
    assert evaluate_context_packet_prompt_eligibility(unsanitized).eligibility_status == PromptContextEligibilityStatus.PROMPT_INELIGIBLE_PRIVACY_GAP
    raw = replace(clean, included_embodiment_refs=(ContextPacketItem("raw", "embodiment", {"provenance_refs": ["p"], "source_kind": "raw_perception_event", "privacy_posture": "public", "sanitized_context_summary": True}),), included_claim_refs=())
    assert evaluate_context_packet_prompt_eligibility(raw).eligibility_status in {PromptContextEligibilityStatus.PROMPT_INELIGIBLE_PRIVACY_GAP, PromptContextEligibilityStatus.PROMPT_INELIGIBLE_BLOCKED_RISK}

    act = replace(clean, included_claim_refs=(ContextPacketItem("act", "claim", {"provenance_refs": ["p"], "source_kind": "embodiment_snapshot", "action_capable": True, "sanitized_context_summary": True}),))
    assert evaluate_context_packet_prompt_eligibility(act).eligibility_status == PromptContextEligibilityStatus.PROMPT_INELIGIBLE_ACTION_GAP
    auth = replace(clean, included_claim_refs=(ContextPacketItem("auth", "claim", {"provenance_refs": ["p"], "source_kind": "embodiment_snapshot", "non_authoritative": False, "sanitized_context_summary": True}),))
    assert evaluate_context_packet_prompt_eligibility(auth).eligibility_status == PromptContextEligibilityStatus.PROMPT_INELIGIBLE_AUTHORITY_GAP
    unk = replace(clean, included_claim_refs=(ContextPacketItem("unk", "claim", {"provenance_refs": ["p"], "source_kind": "unknown", "sanitized_context_summary": True}),))
    assert evaluate_context_packet_prompt_eligibility(unk).eligibility_status == PromptContextEligibilityStatus.PROMPT_ELIGIBLE
    assert evaluate_context_packet_prompt_eligibility(replace(clean, included_claim_refs=())).eligibility_status == PromptContextEligibilityStatus.PROMPT_INELIGIBLE_EMPTY_PACKET
    assert evaluate_context_packet_prompt_eligibility(replace(clean, decision_power="admit")).eligibility_status == PromptContextEligibilityStatus.PROMPT_INELIGIBLE_SCHEMA_VIOLATION

    blocked_attempt = _pkt([_cand("ok"), _cand("raw2", ref_type="embodiment", already_sanitized_context_summary=False)])
    assert blocked_attempt.pollution_risk == PollutionRisk.BLOCKED
    assert evaluate_context_packet_prompt_eligibility(blocked_attempt).prompt_eligible is False

    artifact = {
        "ref_id": "embok", "source_kind": "embodiment_proposal", "packet_scope": "turn", "conversation_scope_id": "conv", "task_scope_id": "task",
        "content_summary": "safe", "provenance_refs": ["p1"], "sanitized_context_summary": True, "decision_power": "none", "non_authoritative": True, "proposal_status": "reviewable",
    }
    cand = build_embodiment_context_candidates([artifact])[0]
    pkt = _pkt([cand])
    assert evaluate_context_packet_prompt_eligibility(pkt).prompt_eligible is True

    diag_artifact = dict(artifact, ref_id="diag1", source_kind="embodiment_proposal_diagnostic")
    pkt2 = _pkt(list(build_embodiment_context_candidates([diag_artifact])))
    assert evaluate_context_packet_prompt_eligibility(pkt2).prompt_eligible is True

    stale = replace(clean, freshness_status=FreshnessStatus.STALE)
    out = evaluate_context_packet_prompt_eligibility(stale)
    assert out.preflight_only and out.does_not_call_llm and out.does_not_write_memory and out.does_not_execute_or_route_work

    import sentientos.context_hygiene.prompt_preflight as mod

    txt = open(mod.__file__, encoding="utf-8").read()
    for forbidden in ["prompt_assembler", "memory_manager", "task_executor", "task_admission", "screen_awareness", "mic_bridge", "vision_tracker", "multimodal_tracker", "openai", "requests"]:
        assert forbidden not in txt
