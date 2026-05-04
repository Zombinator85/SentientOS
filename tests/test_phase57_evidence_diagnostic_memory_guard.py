from __future__ import annotations

import pytest

pytestmark = pytest.mark.no_legacy_skip

from copy import deepcopy

from sentientos.truth import (
    build_claim_receipt,
    build_contradiction_receipt,
    build_evidence_stability_diagnostic,
    build_stance_receipt,
    build_truth_memory_ingress_guard_record,
)


def _claim(turn: str, status: str = "directly_supported", kind: str = "source_backed_claim", evidence_ids=None):
    kwargs = dict(conversation_scope_id="c", turn_id=turn, topic_id="t", claim_text=f"claim-{turn}", claim_kind=kind, epistemic_status=status)
    if evidence_ids is not None:
        kwargs["evidence_ids"] = evidence_ids
    elif not (kind in {"source_backed_claim", "source_backed_implication"} and status not in {"underconstrained", "unknown"}):
        kwargs["evidence_ids"] = []
    return build_claim_receipt(**kwargs)


def test_phase57_diagnostic_empty_and_supported_postures():
    empty = build_evidence_stability_diagnostic(claim_receipts=[], evidence_receipts=[], stance_receipts=[], contradiction_receipts=[])
    assert empty["evidence_stability_posture"] == "no_claims_recorded"
    c1 = _claim("1", evidence_ids=["e1"])
    stable = build_evidence_stability_diagnostic(claim_receipts=[c1], evidence_receipts=[{"evidence_id": "e1"}], stance_receipts=[], contradiction_receipts=[])
    assert stable["evidence_stability_posture"] == "stable_supported_stance"
    under = _claim("2", status="underconstrained")
    assert build_evidence_stability_diagnostic(claim_receipts=[under], evidence_receipts=[], stance_receipts=[], contradiction_receipts=[])["evidence_stability_posture"] == "provisional_or_underconstrained_stance"


def test_phase57_diagnostic_contradiction_postures_and_counts():
    prev = _claim("1", evidence_ids=["e1"])
    new = _claim("2", status="plausible_but_unverified", kind="uncertainty_statement", evidence_ids=["e1"])
    c1 = build_contradiction_receipt(topic_id="t", old_claim_id=prev["claim_id"], new_claim_id=new["claim_id"], contradiction_type="no_new_evidence_reversal", severity="blocking", adjudication="require_new_evidence")
    out = build_evidence_stability_diagnostic(claim_receipts=[prev, new], evidence_receipts=[{"evidence_id": "e1"}], stance_receipts=[], contradiction_receipts=[c1])
    assert out["evidence_stability_posture"] == "blocked_due_to_no_new_evidence_reversal"
    c2 = build_contradiction_receipt(topic_id="t", old_claim_id=prev["claim_id"], new_claim_id=new["claim_id"], contradiction_type="unsupported_source_undermining", severity="blocking", adjudication="block_revision")
    out2 = build_evidence_stability_diagnostic(claim_receipts=[prev, new], evidence_receipts=[], stance_receipts=[], contradiction_receipts=[c2])
    assert out2["evidence_stability_posture"] == "blocked_due_to_unsupported_source_undermining"
    assert out2["counts_by_claim_kind"]["source_backed_claim"] == 1
    assert out2["counts_by_contradiction_type"]["unsupported_source_undermining"] == 1
    assert out2["non_authoritative"] is True and out2["decision_power"] == "none"


def test_phase57_memory_guard_outcomes_and_policy_preserve():
    good = _claim("1", evidence_ids=["e1"])
    ok = build_truth_memory_ingress_guard_record(claim_receipt=good, evidence_receipts=[], stance_receipts=[], contradiction_receipts=[])
    assert ok["validation_outcome"] == "truth_memory_ingress_validated_for_future_memory"
    missing = _claim("2", status="underconstrained")
    blocked_under = build_truth_memory_ingress_guard_record(claim_receipt=missing, evidence_receipts=[], stance_receipts=[], contradiction_receipts=[])
    assert blocked_under["validation_outcome"] in {"truth_memory_ingress_blocked_underconstrained", "truth_memory_ingress_blocked_missing_evidence"}
    bad = dict(good)
    bad["evidence_ids"] = []
    bad["evidence_refs"] = []
    assert build_truth_memory_ingress_guard_record(claim_receipt=bad, evidence_receipts=[], stance_receipts=[], contradiction_receipts=[])["validation_outcome"] == "truth_memory_ingress_blocked_missing_evidence"
    no_new = build_contradiction_receipt(topic_id="t", old_claim_id=good["claim_id"], new_claim_id="x", contradiction_type="no_new_evidence_reversal", severity="blocking", adjudication="require_new_evidence")
    assert build_truth_memory_ingress_guard_record(claim_receipt=good, evidence_receipts=[], stance_receipts=[], contradiction_receipts=[no_new])["validation_outcome"] == "truth_memory_ingress_blocked_no_new_evidence_reversal"
    quote = build_contradiction_receipt(topic_id="t", old_claim_id=good["claim_id"], new_claim_id="x", contradiction_type="quote_fidelity_failure", severity="blocking", adjudication="block_revision")
    assert build_truth_memory_ingress_guard_record(claim_receipt=good, evidence_receipts=[], stance_receipts=[], contradiction_receipts=[quote])["validation_outcome"] == "truth_memory_ingress_blocked_quote_fidelity_failure"
    retract = _claim("3", status="retracted_due_to_error", kind="correction", evidence_ids=[])
    assert build_truth_memory_ingress_guard_record(claim_receipt=retract, evidence_receipts=[], stance_receipts=[], contradiction_receipts=[])["validation_outcome"] == "truth_memory_ingress_blocked_retracted_or_superseded"
    other = _claim("4", evidence_ids=["e1"])
    mismatch_stance = build_stance_receipt(topic_id="t", active_claim_id=other["claim_id"], previous_claim_id=good["claim_id"], transition_type="hold_revision")
    assert build_truth_memory_ingress_guard_record(claim_receipt=good, evidence_receipts=[], stance_receipts=[mismatch_stance], contradiction_receipts=[])["validation_outcome"] == "truth_memory_ingress_needs_review"
    policy = build_stance_receipt(topic_id="t", active_claim_id=other["claim_id"], previous_claim_id=good["claim_id"], transition_type="policy_block_but_preserve")
    preserved = build_truth_memory_ingress_guard_record(claim_receipt=good, evidence_receipts=[], stance_receipts=[policy], contradiction_receipts=[])
    assert preserved["active_stance_matches_claim"] is True
    assert preserved["guard_is_not_memory_write"] is True and preserved["decision_power"] == "none"


def test_phase57_no_input_mutation_and_scoped_additive():
    claim = _claim("1", evidence_ids=["e1"])
    claims = [claim]
    evidence = [{"evidence_id": "e1"}]
    stances = []
    contradictions = []
    snap = deepcopy((claims, evidence, stances, contradictions))
    build_evidence_stability_diagnostic(claim_receipts=claims, evidence_receipts=evidence, stance_receipts=stances, contradiction_receipts=contradictions)
    build_truth_memory_ingress_guard_record(claim_receipt=claim, evidence_receipts=evidence, stance_receipts=stances, contradiction_receipts=contradictions)
    assert (claims, evidence, stances, contradictions) == snap

    from sentientos.scoped_lifecycle_diagnostic import build_scoped_lifecycle_diagnostic
    out = build_scoped_lifecycle_diagnostic(__import__('pathlib').Path('.'))
    assert "actions" in out
    assert "evidence_stability_diagnostic" in out
