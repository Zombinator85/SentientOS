from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from sentientos.context_hygiene.context_packet import ContextMode
from sentientos.context_hygiene.embodiment_context import build_embodiment_context_candidates
from sentientos.context_hygiene.prompt_handoff_manifest import (
    ContextPromptHandoffStatus,
    build_context_prompt_handoff_manifest,
    manifest_contains_no_raw_payloads,
    manifest_has_no_runtime_authority,
)
from sentientos.context_hygiene.prompt_preflight import PromptContextEligibility, PromptContextEligibilityStatus, evaluate_context_packet_prompt_eligibility
from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates

NOW = datetime.now(timezone.utc)

def _cand(ref_id="r", ref_type="evidence", metadata=None):
    return ContextCandidate(ref_id=ref_id, ref_type=ref_type, packet_scope="turn", conversation_scope_id="conv", task_scope_id="task", provenance_refs=("p1",), source_locator="src", summary="sum", already_sanitized_context_summary=True, truth_ingress_status="allowed", metadata=metadata or {})

def _pkt(cands):
    return build_context_packet_from_candidates(cands, "turn", "conv", "task", context_mode=ContextMode.RESPONSE, now=NOW)


def test_phase67_manifest_status_and_fields_and_no_mutation():
    base = _pkt([_cand("ok", metadata={"source_kind": "evidence", "privacy_posture": "public", "non_authoritative": True, "decision_power": "none"})])
    pre = evaluate_context_packet_prompt_eligibility(base)
    m = build_context_prompt_handoff_manifest(base, pre)
    assert m.handoff_status == ContextPromptHandoffStatus.HANDOFF_READY
    assert m.prompt_preflight_status == PromptContextEligibilityStatus.PROMPT_ELIGIBLE.value
    assert m.pollution_risk == base.pollution_risk.value
    assert m.provenance_complete == base.provenance_complete
    assert m.lane_summaries and m.included_ref_summaries
    assert m.source_kind_summary.get("evidence", 0) >= 1
    assert manifest_contains_no_raw_payloads(m)
    assert manifest_has_no_runtime_authority(m)
    assert pre == evaluate_context_packet_prompt_eligibility(base)


def test_phase67_caveat_statuses():
    for posture in ["privacy_sensitive", "biometric_or_emotion_sensitive", "raw_retention_sensitive"]:
        pkt = _pkt([_cand(posture, metadata={"source_kind": "embodiment_snapshot", "privacy_posture": posture, "sanitized_context_summary": True, "allow_context_privacy_sensitive": True, "allow_context_biometric_or_emotion": True, "allow_context_raw_retention": True, "non_authoritative": True, "decision_power": "none"})])
        m = build_context_prompt_handoff_manifest(pkt)
        assert m.handoff_status == ContextPromptHandoffStatus.HANDOFF_READY_WITH_CAVEATS


def test_phase67_blocked_statuses_and_invalid_and_empty():
    blocked = _pkt([_cand("b", metadata={"source_kind": "evidence", "pollution_risk": "blocked", "non_authoritative": True, "decision_power": "none"})])
    assert build_context_prompt_handoff_manifest(blocked).handoff_status == ContextPromptHandoffStatus.HANDOFF_BLOCKED
    for meta in [
        {"source_kind": "evidence", "truth_ingress_status": "blocked", "non_authoritative": True, "decision_power": "none"},
        {"source_kind": "raw_perception_event", "non_authoritative": True, "decision_power": "none"},
        {"source_kind": "evidence", "action_capable": True, "non_authoritative": True, "decision_power": "none"},
        {"source_kind": "evidence", "non_authoritative": False, "decision_power": "some"},
    ]:
        assert build_context_prompt_handoff_manifest(_pkt([_cand("x", metadata=meta)])).handoff_status in {ContextPromptHandoffStatus.HANDOFF_BLOCKED, ContextPromptHandoffStatus.HANDOFF_INVALID_PACKET}
    empty = _pkt([])
    assert build_context_prompt_handoff_manifest(empty).handoff_status == ContextPromptHandoffStatus.HANDOFF_NOT_APPLICABLE
    invalid = replace(blocked, context_packet_id="")
    assert build_context_prompt_handoff_manifest(invalid).handoff_status == ContextPromptHandoffStatus.HANDOFF_INVALID_PACKET


def test_phase67_digest_and_preflight_paths_and_source_gap():
    p1 = _pkt([_cand("a", metadata={"source_kind": "evidence", "non_authoritative": True, "decision_power": "none"})])
    p2 = _pkt([_cand("a", metadata={"source_kind": "evidence", "non_authoritative": True, "decision_power": "none"})])
    m1 = build_context_prompt_handoff_manifest(p1)
    m1b = build_context_prompt_handoff_manifest(p1, evaluate_context_packet_prompt_eligibility(p1))
    m2 = build_context_prompt_handoff_manifest(p2)
    assert m1.digest == m1b.digest
    assert m1.digest != m2.digest  # packet id differs
    changed = _pkt([_cand("b", metadata={"source_kind": "evidence", "non_authoritative": True, "decision_power": "none"})])
    assert build_context_prompt_handoff_manifest(changed).digest != m1.digest
    caveat_pre = PromptContextEligibility(eligibility_status=PromptContextEligibilityStatus.PROMPT_ELIGIBLE_WITH_CAVEATS, prompt_eligible=True, may_be_prompted_only_with_caveats=True, caveats=("x",), packet_id=p1.context_packet_id)
    assert build_context_prompt_handoff_manifest(p1, caveat_pre).digest != m1.digest

    gap = _pkt([_cand("gap", metadata={"source_kind": "unknown", "non_authoritative": True, "decision_power": "none"})])
    mg = build_context_prompt_handoff_manifest(gap)
    assert mg.block_reasons


def test_phase67_phase63_and_62b_interop_and_import_purity():
    proposal = {"source_kind": "embodiment_proposal", "privacy_posture": "public", "sanitized_context_summary": True, "proposal_summary": "ok"}
    candidates = build_embodiment_context_candidates([proposal], packet_scope="turn", conversation_scope_id="conv", task_scope_id="task")
    pkt = _pkt(candidates)
    assert build_context_prompt_handoff_manifest(pkt).packet_id == pkt.context_packet_id

    contam = _pkt([_cand("blocked_try", metadata={"source_kind": "evidence", "pollution_risk": "blocked", "non_authoritative": True, "decision_power": "none"})])
    assert build_context_prompt_handoff_manifest(contam).blocked

    import sentientos.context_hygiene.prompt_handoff_manifest as mod
    txt = open(mod.__file__, encoding="utf-8").read()
    for forbidden in ["prompt_assembler", "memory_manager", "task_executor", "task_admission", "openai", "requests"]:
        assert forbidden not in txt
