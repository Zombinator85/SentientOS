from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from sentientos.context_hygiene.context_packet import (
    ContextMode,
    ContextPacketItem,
    ContradictionStatus,
    ExcludedContextRef,
    FreshnessStatus,
    PollutionRisk,
    make_context_packet,
    packet_is_expired,
    summarize_packet_for_diagnostics,
    validate_context_packet,
)
from sentientos.context_hygiene.receipts import (
    append_context_assembly_receipt,
    build_context_assembly_receipt,
)


def _valid_packet():
    return make_context_packet(
        packet_scope="conversation_turn",
        conversation_scope_id="conv-1",
        task_scope_id="task-1",
        context_mode=ContextMode.RESPONSE,
        valid_until=datetime.now(timezone.utc) + timedelta(minutes=5),
        included_memory_refs=(ContextPacketItem("m1", "memory", {"source_id": "s1"}),),
        included_claim_refs=(ContextPacketItem("c1", "claim", {"source_id": "s2"}),),
        included_evidence_refs=(ContextPacketItem("e1", "evidence", {"source_id": "s3"}),),
        included_stance_refs=(ContextPacketItem("s1", "stance", {"source_id": "s4"}),),
        included_diagnostic_refs=(ContextPacketItem("d1", "diagnostic", {"source_id": "s5"}),),
        included_embodiment_refs=(ContextPacketItem("b1", "embodiment", {"source_id": "s6"}),),
        excluded_refs=(ExcludedContextRef("x1", "memory", "no provenance"),),
        inclusion_reasons=("scoped relevance",),
        exclusion_reasons=("missing provenance",),
        freshness_status=FreshnessStatus.FRESH,
        contradiction_status=ContradictionStatus.NONE,
        provenance_complete=True,
        pollution_risk=PollutionRisk.LOW,
    )


def test_valid_packet_validates_successfully():
    assert validate_context_packet(_valid_packet()) == []


def test_defaults_non_authoritative_and_none_decision_power():
    packet = _valid_packet()
    assert packet.non_authoritative is True
    assert packet.decision_power == "none"


def test_packet_cannot_claim_truth_memory_write_or_work_control():
    packet = _valid_packet()
    assert "packet cannot claim truth" in validate_context_packet(replace(packet, context_packet_is_not_truth=False))
    assert "packet cannot write memory" in validate_context_packet(replace(packet, context_packet_is_not_memory_write=False))
    assert "packet cannot admit work" in validate_context_packet(replace(packet, does_not_admit_work=False))
    assert "packet cannot execute or route work" in validate_context_packet(replace(packet, does_not_execute_or_route_work=False))


def test_missing_expiry_fails_validation():
    packet = replace(_valid_packet(), valid_until=None)  # type: ignore[arg-type]
    assert "missing expiry" in validate_context_packet(packet)


def test_missing_provenance_fails_validation():
    bad = replace(_valid_packet(), included_memory_refs=(ContextPacketItem("m1", "memory", {}),))
    errors = validate_context_packet(bad)
    assert any("included ref without provenance" in e for e in errors)


def test_excluded_refs_keep_reasons_and_expiry_detection():
    packet = _valid_packet()
    assert packet.excluded_refs[0].reason == "no provenance"
    expired = replace(packet, valid_until=datetime.now(timezone.utc) - timedelta(seconds=1))
    assert packet_is_expired(expired)


def test_receipt_mirrors_packet_and_append_only(tmp_path):
    packet = _valid_packet()
    receipt = build_context_assembly_receipt(packet)
    assert receipt["context_packet_id"] == packet.context_packet_id
    assert receipt["decision_power"] == "none"
    assert receipt["non_authoritative"] is True
    ledger = tmp_path / "receipts.jsonl"
    first = append_context_assembly_receipt(packet, ledger)
    second = append_context_assembly_receipt(packet, ledger)
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["receipt_id"] == first["receipt_id"]
    assert rows[1]["receipt_id"] == second["receipt_id"]


def test_import_purity_and_immutability_and_summary():
    import sentientos.context_hygiene.context_packet as cp

    source = cp.__dict__.get("__file__")
    assert source
    text = open(source, encoding="utf-8").read()
    for forbidden in ["prompt_assembler", "memory_manager", "task_admission", "task_executor"]:
        assert forbidden not in text

    packet = _valid_packet()
    before = packet.context_packet_id
    summary = summarize_packet_for_diagnostics(packet)
    assert summary["context_packet_id"] == before
    with pytest.raises(FrozenInstanceError):
        packet.context_packet_id = "mutated"  # type: ignore[misc]


def test_schema_lanes_and_explicit_statuses_and_no_raw_dump():
    packet = _valid_packet()
    assert packet.included_memory_refs and packet.included_claim_refs and packet.included_evidence_refs
    assert packet.included_stance_refs and packet.included_diagnostic_refs and packet.included_embodiment_refs
    assert packet.pollution_risk in PollutionRisk
    assert packet.contradiction_status in ContradictionStatus
    assert packet.freshness_status in FreshnessStatus
    assert not hasattr(packet, "raw_memory_dump")
