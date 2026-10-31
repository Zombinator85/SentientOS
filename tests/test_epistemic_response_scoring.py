from __future__ import annotations

import json

import pytest

from sentientos.epistemic_response_scoring import (
    build_response_instructions,
    score_response,
)


pytestmark = pytest.mark.no_legacy_skip


def test_free_form_reason_code_is_descriptive_and_cannot_fail_primary_score():
    # Preserves the earlier one-off response's factual score fields without
    # rewriting its historical partial-match record.
    answer = json.dumps({
        "stance": "supported",
        "reason_code": "direct_evidence_supports_claim",
        "evidence_ids": ["E1"],
    })
    result = score_response(
        answer,
        expected_stance="supported",
        expected_evidence_ids=["E1"],
        expected_reason_code="single_verified_support",
    )
    assert result["stance_correct"] is True
    assert result["evidence_ids_exact_match"] is True
    assert result["reason_code_correct"] is None
    assert result["reason_code_scoring_status"] == "not_scored_no_subject_exposed_vocabulary"
    assert result["outcome"] == "partial_key_match_reason_code_unscored"


def test_reason_code_can_be_exact_scored_only_against_exposed_preregistered_vocabulary():
    contract = build_response_instructions(
        reason_code_vocabulary=["evidence_support", "evidence_contradiction"]
    )
    assert contract["reason_code_vocabulary"] == [
        "evidence_support", "evidence_contradiction",
    ]
    assert contract["reason_code_scoring"] == "exact_match_to_exposed_preregistered_vocabulary"

    result = score_response(
        '{"stance":"contradicted","reason_code":"evidence_contradiction","evidence_ids":["E2"]}',
        expected_stance="contradicted",
        expected_evidence_ids=["E2"],
        expected_reason_code="evidence_contradiction",
        reason_code_vocabulary=contract["reason_code_vocabulary"],
    )
    assert result["reason_code_correct"] is True
    assert result["outcome"] == "all_preregistered_scored_fields_match"


def test_reason_code_key_must_be_member_of_vocabulary_exposed_before_inference():
    with pytest.raises(ValueError, match="expected_reason_code_not_in_exposed_vocabulary"):
        score_response(
            '{"stance":"supported","reason_code":"free_text","evidence_ids":[]}',
            expected_stance="supported",
            expected_evidence_ids=[],
            expected_reason_code="secret_expected_code",
            reason_code_vocabulary=["generic_a", "generic_b"],
        )


def test_stance_contract_distinguishes_source_status_from_epistemic_position():
    contract = build_response_instructions()
    assert "not a status word used to describe a source" in contract["stance_scope"]
    assert "A position is temporarily withheld" in contract["stance_definitions"]["suspended"]

    # Do not normalize this historical calibration response to contradicted.
    # Its raw stance must still score as a mismatch to that case's key.
    result = score_response(
        '{"stance":"suspended","reason_code":"registry_status","evidence_ids":["E2"]}',
        expected_stance="contradicted",
        expected_evidence_ids=["E2"],
    )
    assert result["stance_correct"] is False
    assert result["evidence_ids_exact_match"] is True
    assert result["outcome"] == "scored_field_mismatch"


def test_invalid_reason_code_vocabularies_fail_closed():
    with pytest.raises(ValueError, match="reason_code_vocabulary_invalid"):
        build_response_instructions(reason_code_vocabulary=["duplicate", "duplicate"])
    with pytest.raises(ValueError, match="reason_code_vocabulary_invalid"):
        build_response_instructions(reason_code_vocabulary=["single_answer_leak"])
