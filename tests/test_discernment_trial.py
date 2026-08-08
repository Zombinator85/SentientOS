from __future__ import annotations

import json

import pytest

from sentientos.discernment_trial import BlindTrialCustody

pytestmark = pytest.mark.no_legacy_skip
T0 = "2026-08-08T10:00:00+00:00"
T1 = "2026-08-08T11:00:00+00:00"
T2 = "2026-08-08T12:00:00+00:00"


def manifest():
    return {"trial_id": "trial-1", "question": "Which architecture is warranted?", "subject_id": "architecture-x",
        "created_at": T0, "initial_evidence_snapshot": [{"ref": "sha256:initial"}], "expected_participant_count": 3,
        "opaque_participant_slots": ["p-a", "p-b", "p-c"], "trial_nonce": "nonce-123",
        "evaluation_horizon": {"ends_at": "2026-08-10T00:00:00+00:00"},
        "allowed_observation_namespace": "architecture", "custody_root_identity": "repository:test-root"}


def judgment(stance="support", expected=(), disconfirming=(), confidence=.9, change=()):
    return {"proposition": "adopt design X", "interpretation": "X is warranted" if stance != "oppose" else "X is not warranted",
        "stance": stance, "confidence": None if stance == "suspend" else confidence, "strongest_objection": "sample may be biased",
        "alternate_interpretations": ["wait"], "missing_evidence": list(change), "what_would_change_judgment": list(change),
        "expected_observation_keys": list(expected), "disconfirming_observation_keys": list(disconfirming),
        "predicted_consequences": list(expected), "preferred_next_move": None if stance == "suspend" else "observe",
        "rejected_next_moves": ["deploy"], "unresolved_contradictions": ["measurements disagree"], "sealed_at": T1}


def observation(key):
    return {"observation_key": key, "observation_id": "obs-" + key, "observed_at": T2, "value": True,
        "evidence_references": [{"digest": "sha256:" + key}], "provenance": {"collector": "canonical-test"}, "ambiguity": False}


def prepared(tmp_path):
    custody = BlindTrialCustody(tmp_path); trial = custody.create_trial(manifest())
    for slot, identity in (("p-a", "Allen/operator"), ("p-b", "SentientOS"), ("p-c", "external peer GPT")):
        receipt = custody.register_participant(slot, identity)
        assert receipt["question_digest"] == trial["question_digest"]
        assert receipt["evidence_snapshot_digest"] == trial["initial_evidence_snapshot_digest"]
    return custody


def test_early_custody_redacts_peers_and_enforces_phase_order(tmp_path):
    custody = prepared(tmp_path)
    custody.submit("p-a", judgment(disconfirming=("architecture.x_failed",)))
    receipt = custody.submit("p-b", judgment(stance="suspend", expected=("architecture.calibrated_sample",), change=("architecture.calibrated_sample",)))
    assert set(receipt) == {"opaque_participant_id", "participant_judgment_digest", "sealed_count", "expected_participant_count", "judgment_set_frozen"}
    state = custody.trial_state(); assert state["sealed_count"] == 2 and "proposition" not in json.dumps(state)
    with pytest.raises(ValueError, match="peer judgments"): custody.inspect("judgment", "p-a")
    with pytest.raises(ValueError, match="frozen before evidence"): custody.record_evidence({"observations": [], "evaluation_horizon_elapsed": True})
    with pytest.raises(ValueError): custody.compare()
    with pytest.raises(ValueError): custody.reveal()


def test_three_participant_blind_trial_derives_hits_then_reveals(tmp_path):
    custody = prepared(tmp_path)
    custody.submit("p-a", judgment(expected=("architecture.x_succeeds",), disconfirming=("architecture.x_failed",)))
    custody.submit("p-b", judgment(stance="suspend", expected=("architecture.calibrated_sample",), change=("architecture.calibrated_sample",)))
    custody.submit("p-c", judgment(stance="oppose", expected=("architecture.unique_c",), disconfirming=("architecture.x_succeeds",), confidence=.7))
    assert custody.trial_state()["judgment_set_frozen"] is True
    with pytest.raises(ValueError, match="frozen"): custody.submit("p-a", judgment())
    evidence = custody.record_evidence({"observations": [observation("architecture.x_failed"), observation("architecture.calibrated_sample"),
        observation("architecture.unique_c"), observation("architecture.undeclared_later_fact")], "evaluation_horizon_elapsed": True})
    evidence_bytes = (tmp_path / "evidence.json").read_bytes()
    reviews = custody.review()["reviews"]
    by_id = {row["opaque_participant_id"]: row for row in reviews}
    assert by_id["p-a"]["outcome_classification"] == "contradicted"
    assert by_id["p-b"]["suspension_behavior"]["resolved_by_requested_evidence"] is True
    assert by_id["p-c"]["derived_expected_hits"] == ["architecture.unique_c"]
    assert all("architecture.undeclared_later_fact" not in row["derived_expected_hits"] for row in reviews)
    comparison = custody.compare(); comparison_bytes = (tmp_path / "comparison.json").read_bytes()
    assert comparison["identity_inputs_consumed"] is False and comparison["composite_scores_and_rankings_prohibited"] is True
    assert not any(name in json.dumps(comparison) for name in ("Allen", "SentientOS", "GPT"))
    review_bytes = {slot: (tmp_path / f"review.{slot}.json").read_bytes() for slot in ("p-a", "p-b", "p-c")}
    reveal = custody.reveal(); assert reveal["identities"]["p-b"] == "SentientOS"
    assert evidence_bytes == (tmp_path / "evidence.json").read_bytes() and comparison_bytes == (tmp_path / "comparison.json").read_bytes()
    assert all(data == (tmp_path / f"review.{slot}.json").read_bytes() for slot, data in review_bytes.items())
    assert evidence["observations"][-1]["observation_key"] == "architecture.x_failed"


def test_source_identity_cannot_change_classification_and_manual_hit_labels_are_rejected(tmp_path):
    custody = prepared(tmp_path)
    same = judgment(expected=("architecture.same",))
    for slot in ("p-a", "p-b", "p-c"): custody.submit(slot, same)
    with pytest.raises(TypeError):
        custody.record_evidence({"observations": [observation("architecture.same")], "evaluation_horizon_elapsed": True}, expected_observations_witnessed=["architecture.fake"])  # type: ignore[call-arg]
    custody.record_evidence({"observations": [observation("architecture.same")], "evaluation_horizon_elapsed": True})
    reviews = custody.review()["reviews"]
    assert {row["outcome_classification"] for row in reviews} == {"supported"}
    blind_text = "".join(path.read_text() for path in tmp_path.glob("*.json") if not path.name.startswith("identity.") and path.name != "reveal.json")
    assert not any(name in blind_text for name in ("Allen/operator", "SentientOS", "external peer GPT"))
