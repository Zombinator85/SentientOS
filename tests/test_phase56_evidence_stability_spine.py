from __future__ import annotations

import pytest

pytestmark = pytest.mark.no_legacy_skip

from pathlib import Path

from sentientos.truth import (
    append_claim_receipt,
    append_evidence_receipt,
    build_claim_receipt,
    build_evidence_receipt,
    build_stance_receipt,
    detect_no_new_evidence_reversal,
    hash_evidence_span,
    is_blocked_epistemic_status,
    is_revision_status,
    is_supported_epistemic_status,
    list_recent_claim_receipts,
    list_recent_evidence_receipts,
    normalize_epistemic_status,
    resolve_active_stance,
)


def test_evidence_receipt_builder_and_append_list(tmp_path: Path) -> None:
    p = tmp_path / "evidence.jsonl"
    assert hash_evidence_span("x") == hash_evidence_span("x")
    receipt = build_evidence_receipt(source_type="web_page", source_id="u1", quote_text="hello")
    assert receipt["non_authoritative"] is True
    assert receipt["decision_power"] == "none"
    append_evidence_receipt(receipt, path=p)
    rows = list_recent_evidence_receipts(path=p)
    assert rows[-1]["quote_hash"] == receipt["quote_hash"]


def test_claim_receipt_rules_and_determinism(tmp_path: Path) -> None:
    with_evidence = build_claim_receipt(conversation_scope_id="c1", turn_id="t1", topic_id="topic", claim_text="A", claim_kind="source_backed_claim", epistemic_status="directly_supported", evidence_ids=["e1"])
    assert with_evidence["claim_id"] == build_claim_receipt(conversation_scope_id="c1", turn_id="t1", topic_id="topic", claim_text="A", claim_kind="source_backed_claim", epistemic_status="directly_supported", evidence_ids=["e1"])["claim_id"]
    p = tmp_path / "claim.jsonl"
    append_claim_receipt(with_evidence, path=p)
    assert list_recent_claim_receipts(path=p)


def test_claim_requires_evidence_unless_underconstrained() -> None:
    try:
        build_claim_receipt(conversation_scope_id="c1", turn_id="t1", topic_id="topic", claim_text="A", claim_kind="source_backed_claim", epistemic_status="directly_supported")
        assert False
    except ValueError:
        pass
    ok = build_claim_receipt(conversation_scope_id="c1", turn_id="t1", topic_id="topic", claim_text="A", claim_kind="source_backed_claim", epistemic_status="underconstrained")
    assert ok["epistemic_status"] == "underconstrained"


def test_epistemic_status_helpers() -> None:
    assert is_supported_epistemic_status("directly_supported")
    assert is_blocked_epistemic_status("no_new_evidence_reversal_blocked")
    assert is_revision_status("superseded_by_new_evidence")
    assert normalize_epistemic_status("not_real") == "unknown"


def test_stance_and_contradiction_detection() -> None:
    prev = build_claim_receipt(conversation_scope_id="c1", turn_id="1", topic_id="t", claim_text="X", claim_kind="source_backed_claim", epistemic_status="directly_supported", evidence_ids=["e1"])
    new = build_claim_receipt(conversation_scope_id="c1", turn_id="2", topic_id="t", claim_text="not X", claim_kind="source_backed_claim", epistemic_status="plausible_but_unverified", evidence_ids=["e1"])
    stance = build_stance_receipt(topic_id="t", active_claim_id=new["claim_id"], previous_claim_id=prev["claim_id"], transition_type="weaken_with_new_evidence", new_evidence_ids=[])
    assert stance["allowed"] is False
    contradiction = detect_no_new_evidence_reversal(previous_claim=prev, new_claim=new, transition_type="weaken_with_new_evidence", new_evidence_ids=[])
    assert contradiction and contradiction["contradiction_type"] == "no_new_evidence_reversal"


def test_other_transition_paths() -> None:
    prev = build_claim_receipt(conversation_scope_id="c", turn_id="1", topic_id="t", claim_text="X", claim_kind="source_backed_claim", epistemic_status="directly_supported", evidence_ids=["e1"])
    dil = build_claim_receipt(conversation_scope_id="c", turn_id="2", topic_id="t", claim_text="maybe X", claim_kind="uncertainty_statement", epistemic_status="underconstrained", evidence_ids=["e1"])
    c1 = detect_no_new_evidence_reversal(previous_claim=prev, new_claim=dil, transition_type="qualify", new_evidence_ids=[])
    assert c1 and c1["contradiction_type"] == "unsupported_dilution"
    und = dict(dil)
    und["source_quality_summary"] = "undermined"
    c2 = detect_no_new_evidence_reversal(previous_claim=prev, new_claim=und, transition_type="policy_block_but_preserve", new_evidence_ids=[])
    assert c2 and c2["contradiction_type"] == "unsupported_source_undermining"
    ok = detect_no_new_evidence_reversal(previous_claim=prev, new_claim=dil, transition_type="supersede_with_new_evidence", new_evidence_ids=["e2"])
    assert ok is None
    retract = build_stance_receipt(topic_id="t", active_claim_id=dil["claim_id"], previous_claim_id=prev["claim_id"], transition_type="retract_due_to_error", rationale="calc bug")
    assert retract["allowed"] is True
    keep = resolve_active_stance(prev, dil, "policy_block_but_preserve")
    assert keep == prev["claim_id"]
