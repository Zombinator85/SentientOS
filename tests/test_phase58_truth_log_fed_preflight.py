from __future__ import annotations

import pytest

pytestmark = pytest.mark.no_legacy_skip

from copy import deepcopy

from sentientos.truth import (
    build_claim_receipt,
    build_log_fed_evidence_stability_diagnostic,
    build_stance_preflight_record,
    default_truth_ledger_paths,
    load_truth_records_for_diagnostic,
    summarize_log_fed_truth_state,
)


def test_log_fed_load_and_summary(tmp_path):
    paths = {k: tmp_path / f"{k}.jsonl" for k in ["evidence", "claim", "stance", "contradiction"]}
    paths["evidence"].write_text('{"evidence_id":"e1"}\n', encoding='utf-8')
    paths["claim"].write_text('{"claim_id":"c1","epistemic_status":"directly_supported"}\n', encoding='utf-8')
    paths["stance"].write_text('{"active_claim_id":"c1"}\n', encoding='utf-8')
    paths["contradiction"].write_text('{"contradiction_type":"unknown"}\n', encoding='utf-8')
    loaded = load_truth_records_for_diagnostic(ledger_paths=paths)
    summary = summarize_log_fed_truth_state(loaded_truth_records=loaded)
    assert summary["truth_records_loaded"]["evidence_receipts"] == 1
    assert summary["truth_records_loaded"]["claim_receipts"] == 1


def test_log_fed_missing_and_malformed_degrade(tmp_path):
    p = tmp_path / "claim.jsonl"
    p.write_text('{bad\n{"claim_id":"c1"}\n', encoding='utf-8')
    out = load_truth_records_for_diagnostic(ledger_paths={"claim": p, "evidence": tmp_path/'e.jsonl', "stance": tmp_path/'s.jsonl', "contradiction": tmp_path/'c.jsonl'})
    assert out["status"] == "degraded"
    assert out["records"]["claim_receipts"][0]["claim_id"] == "c1"


def test_log_fed_immutability_and_diag(tmp_path):
    defaults = default_truth_ledger_paths()
    snap = deepcopy(defaults)
    diag = build_log_fed_evidence_stability_diagnostic(topic_id="t", ledger_paths={"evidence": tmp_path/'e.jsonl', "claim": tmp_path/'c.jsonl', "stance": tmp_path/'s.jsonl', "contradiction": tmp_path/'x.jsonl'})
    assert defaults == snap
    assert diag["decision_power"] == "none"


def test_stance_preflight_outcomes():
    prior = build_claim_receipt(conversation_scope_id="c", turn_id="1", topic_id="t", claim_text="A", claim_kind="source_backed_claim", epistemic_status="directly_supported", evidence_ids=["e1"])
    preserve = build_claim_receipt(conversation_scope_id="c", turn_id="2", topic_id="t", claim_text="A", claim_kind="source_backed_claim", epistemic_status="directly_supported", evidence_ids=["e1"])
    assert build_stance_preflight_record(planned_claim=preserve, prior_claims=[prior], stance_receipts=[], transition_type="preserve")["preflight_outcome"] == "stance_preflight_allowed_preserve"
    narrow = build_claim_receipt(conversation_scope_id="c", turn_id="3", topic_id="t", claim_text="A only in cases", claim_kind="source_backed_implication", epistemic_status="directly_supported", evidence_ids=["e1"])
    assert "allowed_narrow" in build_stance_preflight_record(planned_claim=narrow, prior_claims=[prior], stance_receipts=[], transition_type="narrow")["preflight_outcome"]
    sup = build_claim_receipt(conversation_scope_id="c", turn_id="4", topic_id="t", claim_text="not A", claim_kind="source_backed_claim", epistemic_status="superseded_by_new_evidence", evidence_ids=["e1","e2"])
    assert build_stance_preflight_record(planned_claim=sup, prior_claims=[prior], stance_receipts=[], transition_type="supersede_with_new_evidence")["preflight_outcome"] == "stance_preflight_allowed_with_new_evidence"
    blocked = build_claim_receipt(conversation_scope_id="c", turn_id="5", topic_id="t", claim_text="not A", claim_kind="source_backed_claim", epistemic_status="plausible_but_unverified", evidence_ids=["e1"])
    assert build_stance_preflight_record(planned_claim=blocked, prior_claims=[prior], stance_receipts=[], transition_type="weaken_with_new_evidence")["preflight_outcome"] in {"stance_preflight_blocked_no_new_evidence_reversal", "stance_preflight_needs_review"}
    policy = build_stance_preflight_record(planned_claim=preserve, prior_claims=[prior], stance_receipts=[], transition_type="policy_block_but_preserve")
    assert policy["preflight_outcome"] == "stance_preflight_needs_review"
    unknown = build_claim_receipt(conversation_scope_id="c", turn_id="6", topic_id="t", claim_text="?", claim_kind="unknown", epistemic_status="unknown")
    assert build_stance_preflight_record(planned_claim=unknown, prior_claims=[prior], stance_receipts=[])["preflight_outcome"] == "stance_preflight_needs_review"
    assert policy["preflight_is_not_response_generation"] is True and policy["preflight_is_not_memory_write"] is True
