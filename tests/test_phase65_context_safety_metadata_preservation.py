from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

from sentientos.context_hygiene.context_packet import ContextMode, ContextPacketItem, PollutionRisk, validate_context_packet
from sentientos.context_hygiene.prompt_preflight import PromptContextEligibilityStatus, evaluate_context_packet_prompt_eligibility
from sentientos.context_hygiene.safety_metadata import (
    CONTEXT_SAFETY_METADATA_KEY,
    attach_context_safety_metadata_to_packet_ref,
    explain_missing_context_safety_metadata,
    extract_context_safety_metadata,
    normalize_context_safety_metadata,
)
from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates


NOW = datetime.now(timezone.utc)


def _cand(ref_id: str = "c1", ref_type: str = "claim", metadata=None, **kwargs):
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
        metadata=metadata or {},
    )
    return replace(base, **kwargs)


def _pkt(cands):
    return build_context_packet_from_candidates(cands, "turn", "conv", "task", context_mode=ContextMode.RESPONSE, now=NOW)


def test_phase65_preservation_and_preflight_contract():
    meta = {
        "source_kind": "embodiment_snapshot",
        "privacy_posture": "privacy_sensitive",
        "sanitized_context_summary": True,
        "context_eligible": True,
        "non_authoritative": True,
        "decision_power": "none",
        "risk_flags": ["r1"],
        "safety_flags": ["s1"],
        "handoff_is_not_fulfillment": True,
        "runtime_handle": object(),
        "raw_payload": {"x": 1},
    }
    c = _cand("emb-ok", "embodiment", meta)
    pkt = _pkt([c])
    item = pkt.included_embodiment_refs[0]
    sm = item.provenance[CONTEXT_SAFETY_METADATA_KEY]
    assert sm["source_kind"] == "embodiment_snapshot"
    assert sm["privacy_posture"] == "privacy_sensitive"
    assert sm["sanitized_context_summary"] is True
    assert sm["context_eligible"] is True
    assert sm["non_authoritative"] is True
    assert sm["decision_power"] == "none"
    assert sm["risk_flags"] == ["r1"] and sm["safety_flags"] == ["s1"]
    assert "raw_payload" not in sm and "runtime_handle" not in sm

    act = replace(pkt, included_embodiment_refs=(ContextPacketItem("a", "embodiment", attach_context_safety_metadata_to_packet_ref({"provenance_refs": ["p"]}, {"source_kind": "embodiment_snapshot", "action_capable": True})),))
    assert evaluate_context_packet_prompt_eligibility(act).eligibility_status == PromptContextEligibilityStatus.PROMPT_INELIGIBLE_SCHEMA_VIOLATION

    privacy_gap = replace(pkt, included_embodiment_refs=(ContextPacketItem("p", "embodiment", attach_context_safety_metadata_to_packet_ref({"provenance_refs": ["p"]}, {"source_kind": "embodiment_snapshot", "privacy_posture": "privacy_sensitive", "sanitized_context_summary": False})),))
    assert evaluate_context_packet_prompt_eligibility(privacy_gap).eligibility_status == PromptContextEligibilityStatus.PROMPT_INELIGIBLE_SCHEMA_VIOLATION

    auth_gap = replace(pkt, included_embodiment_refs=(ContextPacketItem("u", "embodiment", attach_context_safety_metadata_to_packet_ref({"provenance_refs": ["p"]}, {"source_kind": "embodiment_snapshot", "non_authoritative": False})),))
    assert evaluate_context_packet_prompt_eligibility(auth_gap).eligibility_status == PromptContextEligibilityStatus.PROMPT_INELIGIBLE_SCHEMA_VIOLATION

    caveat = replace(pkt, pollution_risk=PollutionRisk.HIGH, included_embodiment_refs=(ContextPacketItem("c", "embodiment", attach_context_safety_metadata_to_packet_ref({"provenance_refs": ["p"]}, {"source_kind": "embodiment_snapshot", "privacy_posture": "privacy_sensitive", "sanitized_context_summary": True, "allow_context_privacy_sensitive": True, "non_authoritative": True, "decision_power": "none"})),))
    assert evaluate_context_packet_prompt_eligibility(caveat).eligibility_status == PromptContextEligibilityStatus.PROMPT_ELIGIBLE_WITH_CAVEATS

    clean = _pkt([_cand("cl", metadata={})])
    assert evaluate_context_packet_prompt_eligibility(clean).eligibility_status == PromptContextEligibilityStatus.PROMPT_ELIGIBLE


def test_phase65_validation_and_helper_purity():
    assert explain_missing_context_safety_metadata("embodiment", {}) is None
    assert explain_missing_context_safety_metadata("embodiment", {"source_kind": "unknown"})

    unknown = _pkt([_cand("u", "embodiment", {"source_kind": "unknown"})])
    assert not unknown.included_embodiment_refs

    ok = _pkt([_cand("ok", "embodiment", {"source_kind": "embodiment_snapshot", "sanitized_context_summary": True, "non_authoritative": True, "decision_power": "none"})])
    assert validate_context_packet(ok) == []

    raw_perc = replace(ok, included_embodiment_refs=(ContextPacketItem("rp", "embodiment", attach_context_safety_metadata_to_packet_ref({"provenance_refs": ["p"]}, {"source_kind": "embodiment_snapshot", "raw_perception": True})),))
    assert any("raw-source" in e for e in validate_context_packet(raw_perc))

    retention = replace(ok, included_embodiment_refs=(ContextPacketItem("rc", "embodiment", attach_context_safety_metadata_to_packet_ref({"provenance_refs": ["p"]}, {"source_kind": "embodiment_snapshot", "retention_commit_capable": True})),))
    assert any("action-capable" in e for e in validate_context_packet(retention))

    orig_meta = {"source_kind": "embodiment_snapshot", "risk_flags": ["a"]}
    cp = _cand("immut", "embodiment", metadata=orig_meta)
    cp_copy = deepcopy(cp)
    _ = extract_context_safety_metadata(cp)
    assert cp == cp_copy

    prov = {"provenance_refs": ["p"]}
    prov_copy = deepcopy(prov)
    _ = attach_context_safety_metadata_to_packet_ref(prov, normalize_context_safety_metadata(orig_meta))
    assert prov == prov_copy

    import sentientos.context_hygiene.safety_metadata as mod

    txt = open(mod.__file__, encoding="utf-8").read()
    for forbidden in ["prompt_assembler", "memory_manager", "task_executor", "task_admission", "screen_awareness", "mic_bridge", "vision_tracker", "multimodal_tracker", "openai", "requests"]:
        assert forbidden not in txt
