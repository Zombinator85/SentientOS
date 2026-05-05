from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from sentientos.context_hygiene.context_packet import ContextMode, PollutionRisk, validate_context_packet
from sentientos.context_hygiene.pollution_guard import combine_pollution_risk
from sentientos.context_hygiene.receipts import append_context_assembly_receipt, build_context_assembly_receipt
from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates


def _c(ref_id: str = "c1", ref_type: str = "claim", **kwargs):
    base = ContextCandidate(
        ref_id=ref_id,
        ref_type=ref_type,
        packet_scope="turn",
        conversation_scope_id="conv",
        task_scope_id="task",
        summary="s",
        provenance_refs=("p1",),
        freshness_status="fresh",
        contradiction_status="none",
        truth_ingress_status="allowed",
        already_sanitized_context_summary=True,
    )
    return replace(base, **kwargs)


def _build(candidates):
    return build_context_packet_from_candidates(candidates, "turn", "conv", "task", context_mode=ContextMode.RESPONSE, now=datetime.now(timezone.utc))


def test_phase62b_contract_alignment(tmp_path):
    assert PollutionRisk.BLOCKED.value == "blocked"
    p = _build([_c(ref_id="ok")])
    assert validate_context_packet(replace(p, pollution_risk=PollutionRisk.BLOCKED)) == []
    assert any("invalid pollution risk" in e for e in validate_context_packet(replace(p, pollution_risk="nope")))

    blocked = _build([_c(ref_id="raw", ref_type="embodiment", already_sanitized_context_summary=False)])
    assert blocked.pollution_risk == PollutionRisk.BLOCKED
    assert not blocked.included_embodiment_refs and any(r.ref_id == "raw" for r in blocked.excluded_refs)

    highish = _build([_c(ref_id="warn", contradiction_status="warning")])
    assert highish.pollution_risk == PollutionRisk.MEDIUM
    assert combine_pollution_risk([_c(), _c(ref_id="b", truth_ingress_status="blocked")]) == PollutionRisk.BLOCKED.value
    assert combine_pollution_risk([_c()]) == PollutionRisk.LOW.value
    assert combine_pollution_risk([_c(freshness_status="stale")]) == PollutionRisk.MEDIUM.value

    missing_prov = _build([_c(ref_id="ok2"), _c(ref_id="np", provenance_refs=())])
    assert missing_prov.provenance_complete is False
    assert any(r.ref_id == "np" for r in missing_prov.excluded_refs)
    included = list(missing_prov.included_claim_refs) + list(missing_prov.included_memory_refs) + list(missing_prov.included_evidence_refs) + list(missing_prov.included_stance_refs) + list(missing_prov.included_diagnostic_refs) + list(missing_prov.included_embodiment_refs)
    assert all(i.provenance for i in included)

    receipt = build_context_assembly_receipt(missing_prov)
    assert receipt["pollution_risk"] == PollutionRisk.BLOCKED.value
    assert receipt["provenance_complete"] is False
    ledger = tmp_path / "r.jsonl"
    append_context_assembly_receipt(missing_prov, ledger)
    append_context_assembly_receipt(missing_prov, ledger)
    assert len(ledger.read_text().splitlines()) == 2

    contra_warn = _build([_c(ref_id="cw", contradiction_status="warning")])
    assert contra_warn.pollution_risk != PollutionRisk.BLOCKED
    contra_blocked = _build([_c(ref_id="cb", contradiction_status="blocked")])
    assert contra_blocked.pollution_risk == PollutionRisk.BLOCKED and not contra_blocked.included_claim_refs

    sanitized = _build([_c(ref_id="embok", ref_type="embodiment", already_sanitized_context_summary=True)])
    assert any(i.ref_id == "embok" for i in sanitized.included_embodiment_refs)

    orig = _c(ref_id="immut")
    _build([orig])
    assert orig.ref_id == "immut"

    import sentientos.context_hygiene.selector as sel
    txt = open(sel.__file__, encoding="utf-8").read()
    for forbidden in ["prompt_assembler", "memory_manager", "retention", "task_executor", "embodiment_ingress"]:
        assert forbidden not in txt

    assert p.decision_power == "none"
    assert p.context_packet_is_not_memory_write and p.does_not_execute_or_route_work and p.does_not_admit_work
