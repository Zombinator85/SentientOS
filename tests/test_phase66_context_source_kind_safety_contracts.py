from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from sentientos.context_hygiene.context_packet import ContextMode, ContextPacketItem, validate_context_packet
from sentientos.context_hygiene.prompt_preflight import PromptContextEligibilityStatus, evaluate_context_packet_prompt_eligibility
from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates
from sentientos.context_hygiene.source_kind_contracts import (
    get_context_source_kind_safety_contract,
    summarize_source_kind_contract_matrix,
    validate_context_safety_metadata_against_source_kind,
)

NOW = datetime.now(timezone.utc)


def _cand(ref_id="c", ref_type="embodiment", metadata=None):
    return ContextCandidate(ref_id=ref_id, ref_type=ref_type, packet_scope="turn", conversation_scope_id="conv", task_scope_id="task", provenance_refs=("p1",), source_locator="loc", summary="s", already_sanitized_context_summary=True, truth_ingress_status="allowed", metadata=metadata or {})


def _pkt(cands):
    return build_context_packet_from_candidates(cands, "turn", "conv", "task", context_mode=ContextMode.RESPONSE, now=NOW)


def test_phase66_contract_matrix_basics_and_unknown_fail_closed():
    matrix = summarize_source_kind_contract_matrix()
    for k in ["raw_perception_event", "embodiment_snapshot", "embodiment_proposal", "unknown", "diagnostic", "evidence", "truth", "research"]:
        assert k in matrix
        assert get_context_source_kind_safety_contract(k).source_kind == k
    ok, reasons = validate_context_safety_metadata_against_source_kind({"source_kind": "unknown"})
    assert not ok and reasons


def test_phase66_selector_packet_preflight_contract_enforcement():
    bad = _cand("bad", metadata={"source_kind": "embodiment_snapshot", "non_authoritative": True, "decision_power": "none"})
    pkt = _pkt([bad])
    assert not pkt.included_embodiment_refs

    good_meta = {"source_kind": "embodiment_snapshot", "sanitized_context_summary": True, "privacy_posture": "public", "non_authoritative": True, "decision_power": "none"}
    good = _cand("good", metadata=good_meta)
    pkt2 = _pkt([good])
    assert pkt2.included_embodiment_refs
    assert validate_context_packet(pkt2) == []
    assert evaluate_context_packet_prompt_eligibility(pkt2).eligibility_status == PromptContextEligibilityStatus.PROMPT_ELIGIBLE

    legacy = _pkt([_cand("legacy", ref_type="claim", metadata={})])
    assert legacy.included_claim_refs

    unknown = replace(pkt2, included_embodiment_refs=(ContextPacketItem("u", "embodiment", {"provenance_refs": ["p"], "context_safety_metadata": {"source_kind": "unknown"}}),))
    assert any("source-kind safety contract" in e for e in validate_context_packet(unknown))
    assert evaluate_context_packet_prompt_eligibility(unknown).eligibility_status == PromptContextEligibilityStatus.PROMPT_INELIGIBLE_SCHEMA_VIOLATION


def test_phase66_no_forbidden_runtime_imports():
    import sentientos.context_hygiene.source_kind_contracts as mod

    txt = open(mod.__file__, encoding="utf-8").read()
    for forbidden in ["prompt_assembler", "memory_manager", "task_executor", "task_admission", "openai", "requests"]:
        assert forbidden not in txt
