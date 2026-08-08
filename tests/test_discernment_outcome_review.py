from __future__ import annotations

import json

import pytest

from sentientos.discernment_outcome_review import (OutcomeReviewCustody, create_commitment,
    create_longitudinal_report, create_outcome_evidence, create_review, validate_commitment)
from sentientos.discernment_synthesis import SurfaceContribution, synthesize_packet

pytestmark = pytest.mark.no_legacy_skip
T0 = "2026-08-08T10:00:00+00:00"
T1 = "2026-08-08T11:00:00+00:00"
T2 = "2026-08-08T12:00:00+00:00"


def packet(surface: str, position: str, evidence: tuple[str, ...], *, prior: str | None = None,
           objection: str = "sensor may be biased", change: tuple[str, ...] = ("calibrated sample",)):
    row = SurfaceContribution(surface_id=surface, source_kind="operator_position" if surface == "operator" else "local_model_interpretation",
        component=f"component.{surface}", component_version="v1", position=position, interpretation=position,
        confidence=.9, evidence_refs=evidence, strongest_objection=objection, missing_evidence=change,
        would_change_position=change, provenance={"decision_class": "interpretation", "identity": surface})
    return synthesize_packet(subject_id="subject", question="Is proposition P warranted?", contributions=[row],
        evaluation_context={}, observed_at=T0 if prior is None else T2, current_interpretation=position,
        epistemic_status="supported", confidence=.9, preferred_next_move="observe", rejected_next_moves=("act",),
        strategic_consequences=("temperature fell",), prior_packet_digest=prior)


def commitment(source, *, stance="support", confidence=.9, expected=("temperature rose",), disconfirming=("temperature fell",)):
    return create_commitment(source, committed_at=T1, decision_class="interpretation", proposition="P", stance=stance,
        confidence=None if stance == "suspend" else confidence, expected_observations=expected,
        disconfirming_observations=disconfirming, predicted_consequences=("temperature fell",),
        evaluation_horizon={"ends_at": "2026-08-09T00:00:00+00:00"})


def outcome(value, *, expected=(), disconfirming=(), ambiguous=(), elapsed=True, changes=(), facts=()):
    return create_outcome_evidence(value, observed_at=T2, evidence_references=({"identity": "sha256:evidence"},),
        evidence_provenance=({"collector": "repository-native", "canonical_digest": "sha256:evidence"},),
        observed_facts=facts, expected_observations_witnessed=expected,
        disconfirming_observations_witnessed=disconfirming, unresolved_or_ambiguous_evidence=ambiguous,
        evaluation_horizon_elapsed=elapsed, change_conditions_witnessed=changes,
        rejected_move_assessments={"act": "vindicated"})


def test_high_and_low_confidence_history_and_source_neutrality():
    operator = commitment(packet("operator", "P", ("e1",)))
    model = commitment(packet("model", "P", ("e1",)), confidence=.2)
    contradicted = create_review(operator, outcome(operator, disconfirming=("temperature fell",)))
    supported = create_review(model, outcome(model, expected=("temperature rose",)))
    equivalent_model = commitment(packet("model", "P", ("e1",)))
    same = create_review(equivalent_model, outcome(equivalent_model, disconfirming=("temperature fell",)))
    assert contradicted["confidence_at_commitment_time"] == .9 and contradicted["outcome_classification"] == "contradicted"
    assert supported["confidence_at_commitment_time"] == .2 and supported["outcome_classification"] == "supported"
    assert same["outcome_classification"] == contradicted["outcome_classification"]


def test_ambiguous_and_absent_evidence_never_force_success():
    value = commitment(packet("model", "P", ("e1",)))
    mixed = create_review(value, outcome(value, expected=("temperature rose",), disconfirming=("temperature fell",), ambiguous=("measurement uncertainty",)))
    pending = create_review(value, outcome(value, elapsed=False))
    indeterminate = create_review(value, outcome(value, ambiguous=("insufficient sample",)))
    assert mixed["outcome_classification"] == "mixed"
    assert pending["outcome_classification"] == "not_yet_observable"
    assert indeterminate["outcome_classification"] == "indeterminate"


def test_commitment_and_snapshot_are_immutable_after_outcome(tmp_path):
    value = commitment(packet("model", "P", ("e1",)))
    custody = OutcomeReviewCustody(tmp_path); path = custody.append(value)
    evidence = outcome(value, disconfirming=("temperature fell",)); custody.append(evidence)
    mutated = json.loads(path.read_text()); mutated["proposition"] = "rewritten"
    with pytest.raises(ValueError, match="digest mismatch"): validate_commitment(mutated)
    with pytest.raises(FileExistsError): custody.append(value)
    snapshot = json.loads(path.read_text())["evidence_available_at_commitment"]
    assert snapshot == ["e1"] and "sha256:evidence" not in snapshot


def test_suspension_legitimate_then_resolved_by_requested_evidence():
    value = commitment(packet("model", "P", ("e1",)), stance="suspend", expected=("calibrated sample",), disconfirming=())
    waiting = create_review(value, outcome(value, elapsed=False))
    resolved_outcome = create_outcome_evidence(value, observed_at=T2, evidence_references=({"identity": "sample"},),
        evidence_provenance=({"collector": "lab"},), observed_facts=("calibrated sample",),
        expected_observations_witnessed=("calibrated sample",), evaluation_horizon_elapsed=True,
        change_conditions_witnessed=("calibrated sample",))
    resolved = create_review(value, resolved_outcome)
    assert waiting["suspension_maintained_appropriately"] is True
    assert resolved["outcome_classification"] == "supported" and resolved["suspension_resolved_by_new_evidence"] is True


def test_stance_machinery_distinguishes_unsupported_and_evidence_backed_reversal():
    source = packet("model", "A", ("e1",)); value = commitment(source)
    unsupported = packet("model", "B", ("e1",), prior=source["packet_digest"])
    backed = packet("model", "B", ("e1", "e2"), prior=source["packet_digest"])
    evidence = outcome(value, disconfirming=("temperature fell",))
    first = create_review(value, evidence, source_packet=source, later_packet=unsupported)
    second = create_review(value, evidence, source_packet=source, later_packet=backed)
    assert first["unsupported_reversal"] is True
    assert first["stance_preflight"]["contradiction_receipt"]["contradiction_type"] == "no_new_evidence_reversal"
    assert second["later_stance_change_had_new_evidence"] is True and second["unsupported_reversal"] is False


def test_three_judgment_longitudinal_scenario_freezes_all_before_outcomes():
    sources = [packet("operator", "A", ("a1",)), packet("model", "B", ("b1",)), packet("peer", "not-C", ("c1",))]
    commitments = [commitment(sources[0]), commitment(sources[1], stance="suspend", expected=("calibrated sample",), disconfirming=()),
                   commitment(sources[2], confidence=.6, expected=("temperature rose",), disconfirming=("temperature fell",))]
    assert all(item["committed_at"] == T1 for item in commitments)
    outcomes = [outcome(commitments[0], disconfirming=("temperature fell",)),
                create_outcome_evidence(commitments[1], observed_at=T2, evidence_references=({"identity": "sample"},), evidence_provenance=({"collector": "lab"},), observed_facts=("calibrated sample",), expected_observations_witnessed=("calibrated sample",), evaluation_horizon_elapsed=True, change_conditions_witnessed=("calibrated sample",)),
                outcome(commitments[2], expected=("temperature rose",), facts=("temperature fell",))]
    reviews = [create_review(item, result) for item, result in zip(commitments, outcomes)]
    report = create_longitudinal_report(reviews, generated_at="2026-08-08T13:00:00+00:00")
    assert report["count_evaluable_commitments"] == 3
    assert report["suspensions_later_resolved_by_new_evidence"] == 1
    assert report["composite_score"] is None and report["composite_score_prohibited"] is True
    assert report["source_precedence"] == "none_universal" and not any(report["authority_posture"].values())
