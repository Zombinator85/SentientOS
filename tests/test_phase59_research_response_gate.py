from __future__ import annotations

from copy import deepcopy

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.truth import (
    build_claim_receipt,
    build_planned_research_response_record,
    summarize_research_response_gate_results,
    validate_planned_response_against_truth,
)


def _claim(turn: str, text: str, status: str = "directly_supported", evidence_ids=None, kind: str = "source_backed_claim"):
    kwargs = dict(conversation_scope_id="c", turn_id=turn, topic_id="t", claim_text=text, claim_kind=kind, epistemic_status=status)
    if evidence_ids is not None:
        kwargs["evidence_ids"] = evidence_ids
    return build_claim_receipt(**kwargs)


def test_builder_shape_and_non_authority_no_mutation():
    planned = [_claim("2", "A", evidence_ids=["e1"])]
    snap = deepcopy(planned)
    rec = build_planned_research_response_record(conversation_scope_id="c", turn_id="2", topic_id="t", planned_claim_receipts=planned, evidence_ids_used=["e1"], stance_transition_intents=["preserve"])
    assert rec["planned_response_is_not_emission"] is True
    assert rec["planned_response_is_not_memory"] is True
    assert rec["decision_power"] == "none"
    assert planned == snap


def test_allowed_and_gate_shape():
    prior = [_claim("1", "A", evidence_ids=["e1"])]
    planned_claim = _claim("2", "A", evidence_ids=["e1"])
    planned = build_planned_research_response_record(conversation_scope_id="c", turn_id="2", topic_id="t", planned_claim_receipts=[planned_claim], evidence_ids_used=["e1"], stance_transition_intents=["preserve"])
    gate = validate_planned_response_against_truth(planned_response=planned, planned_claim_receipts=[planned_claim], prior_claims=prior, evidence_receipts=[{"evidence_id": "e1"}], stance_receipts=[{"topic_id": "t", "active_claim_id": prior[0]["claim_id"]}], contradiction_receipts=[])
    assert gate["gate_outcome"] == "response_gate_allowed"
    assert gate["response_gate_is_not_response_generation"] is True
    assert gate["response_gate_is_not_memory_write"] is True


def test_allowed_with_caveat_and_needs_review_cases():
    prior = [_claim("1", "A", evidence_ids=["e1"])]
    prov = _claim("2", "maybe A", status="underconstrained", evidence_ids=[])
    planned = build_planned_research_response_record(conversation_scope_id="c", turn_id="2", topic_id="t", planned_claim_receipts=[prov], stance_transition_intents=["qualify"])
    gate = validate_planned_response_against_truth(planned_response=planned, planned_claim_receipts=[prov], prior_claims=prior, evidence_receipts=[{"evidence_id": "e1"}], stance_receipts=[{"topic_id": "t", "active_claim_id": prior[0]["claim_id"]}], contradiction_receipts=[])
    assert gate["gate_outcome"] in {"response_gate_allowed_with_caveat", "response_gate_blocked_unsupported_dilution"}

    unknown = _claim("3", "?", status="unknown", kind="unknown")
    planned2 = build_planned_research_response_record(conversation_scope_id="c", turn_id="3", topic_id="t", planned_claim_receipts=[unknown], stance_transition_intents=["hold_revision"])
    gate2 = validate_planned_response_against_truth(planned_response=planned2, planned_claim_receipts=[unknown], prior_claims=prior, evidence_receipts=[], stance_receipts=[], contradiction_receipts=[], log_fed_summary={"status": "degraded", "truth_records_load_errors": ["claim"]})
    assert gate2["gate_outcome"] == "response_gate_needs_review"


def test_blocking_outcomes():
    prior = [_claim("1", "A", evidence_ids=["e1"])]
    rev = _claim("2", "not A", status="plausible_but_unverified", evidence_ids=["e1"])
    planned = build_planned_research_response_record(conversation_scope_id="c", turn_id="2", topic_id="t", planned_claim_receipts=[rev], evidence_ids_used=["e1"], stance_transition_intents=["weaken_with_new_evidence"])
    gate = validate_planned_response_against_truth(planned_response=planned, planned_claim_receipts=[rev], prior_claims=prior, evidence_receipts=[{"evidence_id": "e1"}], stance_receipts=[{"topic_id": "t", "active_claim_id": prior[0]["claim_id"]}], contradiction_receipts=[])
    assert gate["gate_outcome"] == "response_gate_blocked_no_new_evidence_reversal"

    dil = _claim("3", "maybe A", status="underconstrained", evidence_ids=["e1"], kind="uncertainty_statement")
    p2 = build_planned_research_response_record(conversation_scope_id="c", turn_id="3", topic_id="t", planned_claim_receipts=[dil], evidence_ids_used=["e1"], stance_transition_intents=["qualify"])
    g2 = validate_planned_response_against_truth(planned_response=p2, planned_claim_receipts=[dil], prior_claims=prior, evidence_receipts=[{"evidence_id": "e1"}], stance_receipts=[{"topic_id": "t", "active_claim_id": prior[0]["claim_id"]}], contradiction_receipts=[])
    assert g2["gate_outcome"] == "response_gate_blocked_unsupported_dilution"

    und = dict(dil)
    und["source_quality_summary"] = "undermined"
    p3 = build_planned_research_response_record(conversation_scope_id="c", turn_id="4", topic_id="t", planned_claim_receipts=[und], evidence_ids_used=["e1"], stance_transition_intents=["policy_block_but_preserve"])
    g3 = validate_planned_response_against_truth(planned_response=p3, planned_claim_receipts=[und], prior_claims=prior, evidence_receipts=[{"evidence_id": "e1"}], stance_receipts=[{"topic_id": "t", "active_claim_id": prior[0]["claim_id"]}], contradiction_receipts=[])
    assert g3["gate_outcome"] == "response_gate_blocked_unsupported_source_undermining"

    miss = _claim("5", "B", evidence_ids=["e404"])
    p4 = build_planned_research_response_record(conversation_scope_id="c", turn_id="5", topic_id="t", planned_claim_receipts=[miss], evidence_ids_used=[])
    g4 = validate_planned_response_against_truth(planned_response=p4, planned_claim_receipts=[miss], prior_claims=prior, evidence_receipts=[{"evidence_id": "e1"}], stance_receipts=[{"topic_id": "t", "active_claim_id": prior[0]["claim_id"]}], contradiction_receipts=[])
    assert g4["gate_outcome"] == "response_gate_blocked_missing_evidence"


def test_summary_and_boundary_invariants():
    records = [
        {"gate_outcome": "response_gate_allowed", "warning_reasons": [], "topic_id": "t1"},
        {"gate_outcome": "response_gate_allowed_with_caveat", "warning_reasons": ["w"], "topic_id": "t1"},
        {"gate_outcome": "response_gate_blocked_missing_evidence", "warning_reasons": [], "topic_id": "t2"},
    ]
    out = summarize_research_response_gate_results(records)
    assert out["response_gate_count"] == 3
    assert out["blocked_count"] == 1
    assert out["warning_count"] == 1
    assert out["topics_with_blocking_gate"] == ["t2"]
