from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from sentientos.evidence_revision_experiment import CONDITIONS, assess_responses, make_protocol
from sentientos.local_model_authority import digest_payload
from sentientos.longitudinal_self_model import LongitudinalSelfModelOwner
from tests.test_longitudinal_self_model import record, snapshot

pytestmark = pytest.mark.no_legacy_skip
DIGEST = "sha256:" + "a" * 64


def intervention(tmp_path):
    owner = LongitudinalSelfModelOwner(tmp_path / "evidence")
    owner.reconcile(snapshot(record()), tick_id="first")
    original = owner.cognitive_projection(before_tick="next", max_claims=2,
        allowed_predicates=("software_generation", "cognitive_model_identity"))
    owner.reconcile(snapshot(record(observed="2026-09-10T00:00:00Z")), tick_id="second")
    revised = owner.cognitive_projection(before_tick="later", max_claims=2,
        allowed_predicates=("software_generation", "cognitive_model_identity"))
    assert original and revised
    projections = dict(zip(CONDITIONS, (original, revised, original)))
    context = dict(model_id="model-a", model_artifact_digest=DIGEST, prompt_digest=DIGEST,
        developmental_history_digest=DIGEST, generation_parameters={"temperature": 0},
        inference_budget={"max_new_tokens": 128})
    return projections, context


def responses(protocol):
    return {condition: {"protocol_digest": protocol["protocol_digest"],
        "fixed_context_digest": protocol["fixed_context_digest"],
        "projection_digest": protocol["evidence"][condition]["projection"]["projection_digest"],
        "answers": [{"question_id": question, "answer": item["answer"],
                     "claim_ids": [item["claim_id"]],
                     "source_evidence_ids": item["source_evidence_ids"]}
                    for question, item in protocol["evidence"][condition]["answer_key"].items()]}
        for condition in CONDITIONS}


def test_revision_and_exact_restoration_score_against_each_evidence_key(tmp_path):
    projections, context = intervention(tmp_path)
    protocol = make_protocol(projections=projections, **context)
    supplied = responses(protocol)
    before = deepcopy(supplied)
    report = assess_responses(protocol=protocol, condition_responses=supplied)
    assert {row["outcome"] for row in report["comparisons"]} == {"classification_followed_evidence_revision"}
    assert report["condition_scores"][CONDITIONS[0]]["counts"]["supported_correct"] == 2
    assert report["condition_scores"][CONDITIONS[1]]["counts"]["correct_abstention"] == 2
    assert report["condition_scores"][CONDITIONS[1]]["counts"]["provenance_correct"] == 2
    assert supplied == before and protocol == make_protocol(projections=projections, **context)
    assert report == assess_responses(protocol=protocol, condition_responses=supplied)
    assert not any(report["authority"].values())
    assert report["descriptive_only"] and not report["execution_proven"]
    assert not report["causal_claim_made"] and not report["improvement_claim_made"]
    assert not report["source_owner_provenance_verified"]


def test_negative_incomplete_and_unstable_results_are_retained(tmp_path):
    projections, context = intervention(tmp_path)
    protocol = make_protocol(projections=projections, **context)
    supplied = responses(protocol)
    for row in supplied[CONDITIONS[1]]["answers"]:
        row["answer"] = "current"
    report = assess_responses(protocol=protocol, condition_responses=supplied)
    assert {row["outcome"] for row in report["comparisons"]} == {"classification_did_not_follow_evidence_revision"}
    assert report["condition_scores"][CONDITIONS[1]]["counts"]["uncertainty_handling_incorrect"] == 2
    supplied[CONDITIONS[2]]["answers"][0]["answer"] = "contradicted"
    supplied[CONDITIONS[1]]["answers"].pop()
    report = assess_responses(protocol=protocol, condition_responses=supplied)
    assert {row["outcome"] for row in report["comparisons"]} == {"unstable_restoration", "incomplete"}
    assert report["condition_scores"][CONDITIONS[1]]["counts"]["unanswered_question"] == 1


def test_wrong_citations_duplicates_and_unknown_questions_cannot_self_certify(tmp_path):
    projections, context = intervention(tmp_path)
    protocol = make_protocol(projections=projections, **context)
    supplied = responses(protocol)
    supplied[CONDITIONS[1]]["answers"][0]["source_evidence_ids"] = ["invented"]
    supplied[CONDITIONS[1]]["answers"][0]["self_marked_correct"] = True
    supplied[CONDITIONS[0]]["answers"].append(deepcopy(supplied[CONDITIONS[0]]["answers"][0]))
    supplied[CONDITIONS[2]]["answers"].append({"question_id": "invented", "answer": "current"})
    report = assess_responses(protocol=protocol, condition_responses=supplied)
    assert report["condition_scores"][CONDITIONS[1]]["counts"]["provenance_incorrect"] == 1
    assert report["comparisons"][0]["outcome"] == "incomplete"
    assert report["condition_scores"][CONDITIONS[0]]["counts"]["unsupported_assertion"] == 1
    assert report["condition_scores"][CONDITIONS[2]]["counts"]["unsupported_assertion"] == 1


def test_protocol_and_response_tampering_fail_closed(tmp_path):
    projections, context = intervention(tmp_path)
    protocol = make_protocol(projections=projections, **context)
    for field in ("protocol_digest", "fixed_context_digest", "projection_digest"):
        supplied = responses(protocol)
        supplied[CONDITIONS[1]][field] = DIGEST
        with pytest.raises(ValueError, match="response_binding_mismatch"):
            assess_responses(protocol=protocol, condition_responses=supplied)
    tampered = deepcopy(protocol)
    tampered["fixed_context"]["model_id"] = "other-model"
    with pytest.raises(ValueError, match="protocol_digest_mismatch"):
        assess_responses(protocol=tampered, condition_responses=responses(protocol))
    tampered["protocol_digest"] = "sha256:" + digest_payload({k: v for k, v in tampered.items() if k != "protocol_digest"})
    with pytest.raises(ValueError, match="noncanonical_protocol"):
        assess_responses(protocol=tampered, condition_responses=responses(protocol))


def test_projection_scope_integrity_and_restoration_are_required(tmp_path):
    projections, context = intervention(tmp_path)
    with pytest.raises(ValueError, match="condition_set_mismatch"):
        make_protocol(projections={}, **context)
    with pytest.raises(ValueError, match="evidence_revision_missing"):
        make_protocol(projections={c: projections[CONDITIONS[0]] for c in CONDITIONS}, **context)
    changed = dict(projections)
    changed[CONDITIONS[2]] = projections[CONDITIONS[1]]
    with pytest.raises(ValueError, match="evidence_restoration_mismatch"):
        make_protocol(projections=changed, **context)
    changed = dict(projections)
    changed[CONDITIONS[1]] = replace(projections[CONDITIONS[1]], authority={"execution_authority": True})
    with pytest.raises(ValueError, match="invalid_evidence_projection"):
        make_protocol(projections=changed, **context)
    changed[CONDITIONS[1]] = replace(projections[CONDITIONS[1]], selected_claim_ids=("invented",))
    with pytest.raises(ValueError, match="invalid_evidence_projection"):
        make_protocol(projections=changed, **context)


def test_malformed_and_oversized_responses_are_rejected(tmp_path):
    projections, context = intervention(tmp_path)
    protocol = make_protocol(projections=projections, **context)
    supplied = responses(protocol)
    supplied[CONDITIONS[0]]["answers"][0]["claim_ids"] = "string-is-not-citations"
    with pytest.raises(ValueError, match="invalid_response_citations"):
        assess_responses(protocol=protocol, condition_responses=supplied)
    supplied = responses(protocol)
    supplied[CONDITIONS[0]]["answers"] *= 65
    with pytest.raises(ValueError, match="response_limit_exceeded"):
        assess_responses(protocol=protocol, condition_responses=supplied)
    with pytest.raises(ValueError, match="invalid_fixed_context"):
        make_protocol(projections=projections, **{**context, "model_id": "latest"})
    with pytest.raises(ValueError):
        make_protocol(projections=projections, **{**context, "generation_parameters": {"temperature": float("nan")}})


def test_null_intervention_is_descriptive_and_inputs_are_detached(tmp_path):
    projections, context = intervention(tmp_path)
    revised = projections[CONDITIONS[0]]
    revised = replace(revised, source_tick="another-source-boundary", projection_id="", projection_digest="")
    digest = "sha256:" + digest_payload(revised.semantic_payload())
    projections[CONDITIONS[1]] = replace(revised, projection_digest=digest,
        projection_id="cognitive-self-model-" + digest[7:31])
    protocol = make_protocol(projections=projections, **context)
    context["generation_parameters"]["temperature"] = 99
    assert protocol["fixed_context"]["generation_parameters"]["temperature"] == 0
    report = assess_responses(protocol=protocol, condition_responses=responses(protocol))
    assert {row["outcome"] for row in report["comparisons"]} == {"null_classification_intervention"}


def test_resealed_claim_scope_and_lineage_changes_remain_forbidden(tmp_path):
    projections, context = intervention(tmp_path)
    revised = projections[CONDITIONS[1]]

    def reseal(value):
        digest = "sha256:" + digest_payload(value.semantic_payload())
        return replace(value, projection_digest=digest, projection_id="cognitive-self-model-" + digest[7:31])

    changed = dict(projections)
    changed[CONDITIONS[1]] = reseal(replace(revised,
        selected_claims=revised.selected_claims[:1], selected_claim_ids=revised.selected_claim_ids[:1],
        selected_claim_digests=revised.selected_claim_digests[:1]))
    with pytest.raises(ValueError, match="evidence_claim_set_mismatch"):
        make_protocol(projections=changed, **context)
    changed[CONDITIONS[1]] = reseal(replace(revised, cognitive_model_identities=("other-model",)))
    with pytest.raises(ValueError, match="evidence_fixed_lineage_mismatch"):
        make_protocol(projections=changed, **context)


def test_composition_has_no_io_or_execution_effects(tmp_path, monkeypatch):
    projections, context = intervention(tmp_path)

    def denied(*args, **kwargs):
        raise AssertionError("composition attempted an effect")

    import builtins
    import socket
    import subprocess
    monkeypatch.setattr(builtins, "open", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    protocol = make_protocol(projections=projections, **context)
    report = assess_responses(protocol=protocol, condition_responses=responses(protocol))
    assert not report["execution_proven"] and not any(report["authority"].values())
