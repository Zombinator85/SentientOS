from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from sentientos.context_hygiene.context_packet import ContextMode, validate_context_packet
from sentientos.context_hygiene.receipts import append_context_assembly_receipt, build_context_assembly_receipt
from sentientos.context_hygiene.selector import ContextCandidate, build_context_packet_from_candidates


def _candidate(ref_id: str = "c1", ref_type: str = "claim", **kwargs):
    base = ContextCandidate(
        ref_id=ref_id,
        ref_type=ref_type,
        packet_scope="turn",
        conversation_scope_id="conv1",
        task_scope_id="task1",
        summary="s",
        provenance_refs=("prov1",),
        freshness_status="fresh",
        contradiction_status="none",
        truth_ingress_status="allowed",
    )
    return replace(base, **kwargs)


def test_phase62_selector_contracts_and_rules(tmp_path):
    now = datetime.now(timezone.utc)
    candidates = [
        _candidate(ref_id="claim_ok", ref_type="claim", metadata={"source_backed": True}, evidence_refs=("e1",)),
        _candidate(ref_id="claim_no_evidence", ref_type="claim", metadata={"source_backed": True}, evidence_refs=()),
        _candidate(ref_id="", ref_type="memory"),
        _candidate(ref_id="missing_prov", provenance_refs=()),
        _candidate(ref_id="expired", valid_until=now - timedelta(seconds=1)),
        _candidate(ref_id="blocked_contra", contradiction_status="blocked"),
        _candidate(ref_id="warn_contra", contradiction_status="warning"),
        _candidate(ref_id="truth_blocked", truth_ingress_status="blocked"),
        _candidate(ref_id="stale", freshness_status="stale"),
        _candidate(ref_id="unknown_type", ref_type="unknown"),
        _candidate(ref_id="mem_ok", ref_type="memory", truth_ingress_status="allowed"),
        _candidate(ref_id="mem_blocked", ref_type="memory", truth_ingress_status="unsupported"),
        _candidate(ref_id="dialogue_ok", ref_type="dialogue"),
        _candidate(ref_id="dialogue_unscoped", ref_type="dialogue", packet_scope=None, conversation_scope_id=None, task_scope_id=None),
        _candidate(ref_id="emb_raw", ref_type="embodiment", already_sanitized_context_summary=False),
        _candidate(ref_id="emb_sanitized", ref_type="embodiment", already_sanitized_context_summary=True),
        _candidate(ref_id="scope_mismatch", conversation_scope_id="other"),
        _candidate(ref_id="stance_missing", ref_type="stance", stance_refs=()),
        _candidate(ref_id="stance_ok", ref_type="stance", stance_refs=("st1",)),
        _candidate(ref_id="evidence_ok", ref_type="evidence", source_priority="high"),
    ]
    packet = build_context_packet_from_candidates(
        candidates,
        packet_scope="turn",
        conversation_scope_id="conv1",
        task_scope_id="task1",
        context_mode=ContextMode.RESPONSE,
        now=now,
    )

    assert validate_context_packet(packet) == []
    assert any(i.ref_id == "claim_ok" for i in packet.included_claim_refs)
    assert any(i.ref_id == "evidence_ok" for i in packet.included_evidence_refs)
    assert any(i.ref_id == "mem_ok" for i in packet.included_memory_refs)
    assert any(i.ref_id == "stance_ok" for i in packet.included_stance_refs)
    assert any(i.ref_id == "dialogue_ok" for i in packet.included_diagnostic_refs)
    assert any(i.ref_id == "emb_sanitized" for i in packet.included_embodiment_refs)

    excluded_ids = {r.ref_id for r in packet.excluded_refs}
    for ref in ["claim_no_evidence", "(missing)", "missing_prov", "expired", "blocked_contra", "truth_blocked", "unknown_type", "mem_blocked", "dialogue_unscoped", "emb_raw", "scope_mismatch", "stance_missing"]:
        assert ref in excluded_ids

    assert any("contested" in reason for reason in packet.inclusion_reasons)
    assert packet.contradiction_status.value in {"suspected", "none"}
    assert packet.provenance_complete is False
    assert packet.pollution_risk.value == "blocked"
    assert packet.exclusion_reasons and packet.inclusion_reasons
    assert candidates[0].ref_id == "claim_ok"
    assert packet.does_not_admit_work is True and packet.does_not_execute_or_route_work is True

    receipt = build_context_assembly_receipt(packet)
    assert receipt["context_packet_id"] == packet.context_packet_id
    ledger = tmp_path / "r.jsonl"
    append_context_assembly_receipt(packet, ledger)
    append_context_assembly_receipt(packet, ledger)
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 2


def test_selector_import_purity_and_no_runtime_hooks():
    import sentientos.context_hygiene.selector as selector

    text = open(selector.__file__, encoding="utf-8").read()
    for forbidden in [
        "prompt_assembler",
        "memory_manager",
        "task_executor",
        "retention",
        "embodiment_ingress",
    ]:
        assert forbidden not in text
