from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from sentientos.longitudinal_self_model import LongitudinalSelfModelError, LongitudinalSelfModelOwner, load_runtime_config
from sentientos.self_model_intervention_experiment import (
    CONDITION_ORDER, SCORER_V1, SCORER_V2, SCORER_V3, build_answer_key, make_protocol,
    score_assessment, score_condition_response_contrast,
)
from tests.test_resident_developmental_cognition import owner as cognition_owner, snapshot as cognition_snapshot
from tests.test_longitudinal_self_model import record, snapshot

pytestmark = pytest.mark.no_legacy_skip


def test_runtime_config_reconstructs_exact_custody_and_rejects_tamper(tmp_path: Path) -> None:
    custody = (tmp_path / "custody").resolve(); owner = LongitudinalSelfModelOwner(custody)
    owner.reconcile(snapshot(record()), tick_id="tick-1")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"schema":"sentientos.longitudinal_self_model_runtime_config:v1",
        "enabled":True, "custody_root":str(custody), "cognitive_consumption_enabled":True,
        "max_projection_claims":4, "allowed_predicates":["software_generation","cognitive_model_identity"],
        "installation_id":"installation-a"}))
    loaded = load_runtime_config(config)
    assert LongitudinalSelfModelOwner(loaded.custody_root).history()[0].tick_id == "tick-1"
    path = next((custody / "reconciliations").glob("*.json")); raw=json.loads(path.read_text())
    raw["tick_id"]="tampered"; path.write_text(json.dumps(raw, sort_keys=True, indent=2) + "\n")
    with pytest.raises(LongitudinalSelfModelError, match="digest_mismatch"):
        LongitudinalSelfModelOwner(loaded.custody_root).history()


def test_prior_tick_projection_is_bounded_exact_and_same_tick_excluded(tmp_path: Path) -> None:
    owner = LongitudinalSelfModelOwner(tmp_path)
    first = owner.reconcile(snapshot(record()), tick_id="tick-1")
    projection = owner.cognitive_projection(before_tick="tick-2", max_claims=2,
        allowed_predicates=("software_generation", "cognitive_model_identity"))
    assert projection is not None and projection.source_reconciliation_id == first.reconciliation_id
    assert projection.source_tick == "tick-1" and len(projection.selected_claim_ids) == 2
    assert not any(projection.authority.values()) and projection.read_only
    only = LongitudinalSelfModelOwner(tmp_path / "only")
    only.reconcile(snapshot(record()), tick_id="tick-n")
    assert only.cognitive_projection(before_tick="tick-n", max_claims=2,
        allowed_predicates=("software_generation",)) is None


def test_intervention_controls_and_external_scoring_reject_self_certification(tmp_path: Path) -> None:
    owner = LongitudinalSelfModelOwner(tmp_path); owner.reconcile(snapshot(record()), tick_id="tick-1")
    projection = owner.cognitive_projection(before_tick="tick-2", max_claims=2,
        allowed_predicates=("software_generation", "cognitive_model_identity"))
    assert projection is not None
    protocol = make_protocol(model_id="model-a", model_artifact_digest="sha256:artifact",
        current_snapshot_id="snapshot-2", current_snapshot_digest="sha256:snapshot",
        current_projection_id="current-2", developmental_history_boundary="history-1",
        projection=projection, prompt_digest="sha256:prompt", generation_parameters={"temperature":0},
        inference_budget={"max_new_tokens":128})
    assert protocol.condition_order == CONDITION_ORDER and protocol.retries == 0
    key = build_answer_key(projection); question, expected = next(iter(key.items()))
    scored = score_assessment(answer_key=key, answers=[{"question_id":question,
        "answer":expected["answer"], "claim_ids":[expected["claim_id"]],
        "source_evidence_ids":list(expected["source_evidence_ids"]), "self_marked_correct":True}])
    assert scored["counts"]["supported_correct"] == 1 and scored["counts"]["provenance_correct"] == 1
    assert scored["model_answer_has_scoring_authority"] is False
    smuggled = score_assessment(answer_key=key, answers=[{"question_id":"invented", "answer":"current"}])
    assert smuggled["counts"]["unsupported_assertion"] == 1


def test_resident_receipt_binds_exact_prior_projection(tmp_path: Path) -> None:
    factual = LongitudinalSelfModelOwner(tmp_path / "self-model")
    historic_trial = record(source="experiment:history-intervention", subject="trial-a",
        disposition="history_presence_associated_stable_difference")
    historic_trial.update({"source_kind": "embodiment",
        "subject_kind": "developmental_history_intervention_experiment"})
    factual.reconcile(snapshot(historic_trial), tick_id="tick-1")
    projection = factual.cognitive_projection(before_tick="tick-2", max_claims=2,
        allowed_predicates=("lifecycle.observation.disposition",))
    assert projection is not None
    projected_claim = projection.selected_claims[0]
    assert projected_claim["claim_category"] == "historical_interpretation"
    assert projected_claim["freshness"] == "unknown"
    assert projected_claim["current_truth"] is False and projected_claim["interpretation"] is True
    cognition, fake = cognition_owner(tmp_path / "cognition")
    result = cognition.run_tick(snapshot=cognition_snapshot(), tick_id="tick-2", prior_self_model=projection)
    assert result.cognition_observation_ids
    request = next(item for item in fake.requests if item.purpose == "resident_developmental_retrieval_cognition")
    assert request.upstream_evidence["self_model_projection_digest"] == projection.projection_digest
    prompt = json.loads(request.prompt)
    assert "Treat every prior self-model claim's category" in prompt["instruction"]
    assert prompt["prior_self_model"]["selected_claims"][0] == projected_claim
    receipt = json.loads((cognition.observations_root / f"{result.cognition_observation_ids[0]}.json").read_text())
    assert receipt["prior_tick_proven"] is True
    assert receipt["self_model_claim_ids"] == list(projection.selected_claim_ids)


def test_v2_reports_unanswered_evidence_questions_and_v1_is_unchanged():
    key = {
        "claim:one:classification": {"answer": "current", "claim_id": "one", "source_evidence_ids": ("e1",)},
        "claim:two:classification": {"answer": "historical", "claim_id": "two", "source_evidence_ids": ("e2",)},
    }
    answers = [{"question_id": "claim:one:classification", "answer": "current",
        "claim_ids": ["one"], "source_evidence_ids": ["e1"]}]
    v2 = score_assessment(answer_key=key, answers=answers, scorer_version=SCORER_V2)
    assert v2["scorer"] == SCORER_V2
    assert v2["counts"]["supported_correct"] == 1
    assert v2["counts"]["unanswered_question"] == 1
    assert v2["question_count"] == 2 and v2["answer_count"] == 1

    v1 = score_assessment(answer_key=key, answers=answers, scorer_version=SCORER_V1)
    assert v1["scorer"] == SCORER_V1
    assert "unanswered_question" not in v1["counts"]


def test_v3_requires_abstention_for_stale_or_unresolved_evidence():
    projection = SimpleNamespace(selected_claims=[
        {"claim_id": "stale", "claim_category": "current_state", "status": "historical",
         "freshness": "stale", "contradiction_state": "consistent",
         "source_evidence_ids": ("e-stale",)},
        {"claim_id": "uncertain", "status": "unresolved", "freshness": "unknown",
         "contradiction_state": "unresolved", "source_evidence_ids": ("e-uncertain",)},
        {"claim_id": "current", "status": "current", "freshness": "fresh",
         "contradiction_state": "consistent", "source_evidence_ids": ("e-current",)},
        {"claim_id": "conflict", "status": "contradicted", "freshness": "fresh",
         "contradiction_state": "contradicted", "source_evidence_ids": ("e-conflict",)},
    ])
    legacy_key = build_answer_key(projection, scorer_version=SCORER_V2)
    key = build_answer_key(projection, scorer_version=SCORER_V3)
    assert legacy_key["claim:stale:classification"]["answer"] == "historical"
    assert key["claim:stale:classification"]["answer"] == "unknown"
    assert key["claim:uncertain:classification"]["answer"] == "unknown"
    assert key["claim:uncertain:classification"]["classification_basis"] == "evidence_not_current_and_consistent"
    assert key["claim:current:classification"]["answer"] == "current"
    assert key["claim:conflict:classification"]["answer"] == "contradicted"

    answer = {"question_id": "claim:uncertain:classification", "answer": "abstain",
        "claim_ids": ["uncertain"], "source_evidence_ids": ["e-uncertain"]}
    scored = score_assessment(answer_key=key, answers=[answer], scorer_version=SCORER_V3)
    assert scored["schema"] == "sentientos.evidence_grounded_self_assessment:v2"
    assert scored["counts"]["correct_abstention"] == 1
    assert scored["counts"]["uncertainty_handling_correct"] == 1
    assert scored["counts"]["provenance_correct"] == 1
    assert scored["counts"]["unanswered_question"] == 3

    overclaim = dict(answer, answer="current")
    overclaim_score = score_assessment(answer_key=key, answers=[overclaim], scorer_version=SCORER_V3)
    assert overclaim_score["counts"]["correct_abstention"] == 0
    assert overclaim_score["counts"]["uncertainty_handling_incorrect"] == 1
    assert overclaim_score["counts"]["supported_incorrect"] == 1

    legacy_abstention = score_assessment(answer_key=legacy_key,
        answers=[dict(answer, question_id="claim:current:classification")], scorer_version=SCORER_V2)
    assert legacy_abstention["counts"]["correct_abstention"] == 0
    assert legacy_abstention["counts"]["incorrect_abstention"] == 1


def test_condition_response_contrast_describes_recovery_and_divergence():
    key = {"q1": {"answer": "current"}, "q2": {"answer": "historical"}}
    cited = {"claim_ids": ["c1"], "source_evidence_ids": ["e1"]}
    answers = {
        CONDITION_ORDER[0]: [
            {"question_id": "q1", "answer": "current", **cited},
            {"question_id": "q2", "answer": "historical", **cited},
        ],
        CONDITION_ORDER[1]: [
            {"question_id": "q1", "answer": "unknown", **cited},
            {"question_id": "q2", "answer": "historical", **cited},
        ],
        CONDITION_ORDER[2]: [
            {"question_id": "q1", "answer": "current", **cited},
            {"question_id": "q2", "answer": "historical", **cited},
        ],
    }

    contrast = score_condition_response_contrast(answer_key=key, condition_answers=answers)

    assert contrast["paired_question_count"] == 2
    assert contrast["response_changed_when_withheld"] == 1
    assert contrast["changed_response_recovered_after_restore"] == 1
    assert contrast["changed_response_diverged_after_restore"] == 0
    assert contrast["stable_across_all_conditions"] == 1
    assert contrast["unanswered_in_any_condition"] == 1
    assert contrast["descriptive_only"] is True
    assert contrast["causal_claim_made"] is False
    assert not any(contrast["authority"].values())

    answers[CONDITION_ORDER[2]][0]["answer"] = "historical"
    diverged = score_condition_response_contrast(answer_key=key, condition_answers=answers)
    assert diverged["changed_response_recovered_after_restore"] == 0
    assert diverged["changed_response_diverged_after_restore"] == 1


def test_condition_response_contrast_marks_incomplete_and_rejects_bad_conditions():
    key = {"q1": {"answer": "current"}}
    answers = {condition: [] for condition in CONDITION_ORDER}
    answers[CONDITION_ORDER[0]] = [{"question_id": "q1", "answer": "invented"}]
    answers[CONDITION_ORDER[1]] = [{"question_id": "unknown-question", "answer": "current"}]
    contrast = score_condition_response_contrast(answer_key=key, condition_answers=answers)
    assert contrast["paired_question_count"] == 0
    assert contrast["incomplete_question_count"] == 1
    assert contrast["unsupported_response_count"] == 2
    with pytest.raises(ValueError, match="condition_order_mismatch"):
        score_condition_response_contrast(answer_key=key, condition_answers={})
