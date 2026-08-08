from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.delegated_judgment_fabric import synthesize_delegated_judgment
from sentientos.discernment_synthesis import (DiscernmentCustody, SurfaceContribution,
    compare_packets, contribution_from_delegated_judgment, contribution_from_epistemic_entry,
    local_model_contribution, synthesize_packet)
from sentientos.truth.epistemic_orientation import EpistemicLedger

NOW = "2026-08-08T12:00:00+00:00"
pytestmark = pytest.mark.no_legacy_skip


def contribution(surface: str, position: str, confidence: float, evidence: tuple[str, ...], kind: str = "deterministic_subsystem_inference", **extra):
    return SurfaceContribution(surface_id=surface, source_kind=kind, component=f"canonical.{surface}",
        component_version="v1", position=position, interpretation=position, confidence=confidence,
        evidence_refs=evidence, provenance={"decision_class": "response"}, **extra)


def packet(rows, **overrides):
    values = dict(subject_id="subject-1", question="Which interpretation is warranted?", contributions=rows,
        evaluation_context={"mode": "evaluation"}, observed_at=NOW, current_interpretation=None,
        epistemic_status="suspended", suspended_conclusions=[{"conclusion": "A", "reason": "conflicting_data"}],
        unresolved_decision_classes=["response"])
    values.update(overrides)
    return synthesize_packet(**values)


def test_real_epistemic_and_delegated_surfaces_preserve_unresolved_disagreement():
    ledger = EpistemicLedger()
    observed = ledger.record_observation("obs-A", "interpretation A", source_class="external_witness",
        confidence=.82, volatility=.2, metadata={"evidence_refs": ["evidence-A"]})
    delegated = synthesize_delegated_judgment({"records_considered": 0, "contract_drifted_domains": 0,
        "contract_baseline_missing_domains": 0, "slice_health_status": "unknown"})
    a = replace(contribution_from_epistemic_entry(observed), provenance={"decision_class": "response"})
    b = replace(contribution_from_delegated_judgment(delegated), position="interpretation B",
        interpretation="interpretation B", confidence=.7, evidence_refs=("evidence-B",),
        would_change_position=("independent measurement",), provenance={"decision_class": "response"})
    result = packet([a, b])
    assert {p["position"] for p in result["disagreements"][0]["positions"]} == {"interpretation A", "interpretation B"}
    assert result["disagreements"][0]["unresolved_reason"] == "no_reconciliation_law"
    assert result["what_would_change_judgment"] == ["independent measurement"]
    assert result["current_interpretation"] is None and result["consensus_required"] is False


def test_high_confidence_operator_and_model_disagreement_and_round_trip(tmp_path):
    class Model:
        def discern(self, request):
            return {"interpretation": "B", "confidence": .88, "strongest_objection": "A ignores sensor drift",
                "would_change_position": ["calibrated sensor evidence"], "proposed_next_move": "inspect calibration",
                "proposed_non_moves": ["do not execute"], "component_version": "model-v1",
                "evidence_refs": ["model-e1"], "provenance": {"invocation_receipt_digest": "receipt-1", "decision_class": "response"}}
    model, status = local_model_contribution(Model(), {"question": "q"})
    operator = contribution("operator", "A", .91, ("operator-e1",), kind="operator_position")
    result = packet([operator, model], local_model_status=status)
    custody = DiscernmentCustody(tmp_path); custody.append(result)
    loaded = custody.inspect(result["packet_digest"])
    assert loaded["strongest_objection"] == "A ignores sensor drift"
    assert loaded["what_would_change_judgment"] == ["calibrated sensor evidence"]
    assert len(loaded["disagreements"]) == 1


def test_deterministic_non_model_and_absent_model_never_fabricates():
    row = contribution("truth", "A", .75, ("e1",))
    first = packet([row]); second = packet([row])
    assert first == second
    model, status = local_model_contribution(None, {})
    absent = packet([row], local_model_status=status)
    assert model is None and absent["local_model_contribution"] == {
        "fabricated": False, "reason": "governed_local_model_source_not_configured", "status": "unavailable"}


def test_compare_uses_stance_logic_for_unsupported_and_evidence_backed_revisions():
    earlier = packet([contribution("truth", "A", .8, ("e1",))], current_interpretation="A",
        epistemic_status="supported", confidence=.8)
    unsupported = packet([contribution("truth", "B", .6, ("e1",))], current_interpretation="B",
        epistemic_status="supported", confidence=.6, prior_packet_digest=earlier["packet_digest"])
    report = compare_packets(earlier, unsupported)
    assert report["reversal_had_new_evidence"] is False
    assert report["stance_preflight"]["contradiction_receipt"]["contradiction_type"] == "no_new_evidence_reversal"
    later = packet([contribution("truth", "B", .86, ("e1", "e2"))], current_interpretation="B",
        epistemic_status="supported", confidence=.86, prior_packet_digest=earlier["packet_digest"])
    backed = compare_packets(earlier, later)
    assert backed["evidence_added"] == ["e2"] and backed["reversal_had_new_evidence"] is True
    assert backed["stance_preflight"]["preflight_outcome"] == "stance_preflight_allowed_with_new_evidence"


def test_packet_authority_posture_is_entirely_false():
    result = packet([contribution("truth", "A", .7, ("e1",))])
    assert not any(result["authority_posture"].values())
    assert result["judgment_record_not_memory_truth"] is True
