from __future__ import annotations

from codex.integrity_daemon import IntegrityEvaluation
from codex.proposal_router import CandidateResult, choose_candidate, score_evaluation


def _evaluation(valid: bool, codes: list[str]) -> IntegrityEvaluation:
    violations = [{"code": code, "detail": code} for code in codes]
    return IntegrityEvaluation(
        valid=valid,
        reason_codes=codes,
        violations=violations,
        probe={},
        proof_report={},
        timestamp="2025-01-01T00:00:00+00:00",
        ledger_entry="ledger://test",
        quarantined=not valid,
    )


def test_choose_candidate_is_deterministic_for_same_inputs() -> None:
    results = [
        CandidateResult("cand-b", object(), _evaluation(False, ["entropy"]), score_evaluation(_evaluation(False, ["entropy"]))),
        CandidateResult("cand-a", object(), _evaluation(True, []), score_evaluation(_evaluation(True, []))),
        CandidateResult("cand-c", object(), _evaluation(False, ["tamper"]), score_evaluation(_evaluation(False, ["tamper"]))),
    ]
    one, status_one = choose_candidate(results)
    two, status_two = choose_candidate(results)
    assert (one.candidate_id, status_one) == (two.candidate_id, status_two)


def test_valid_candidate_beats_lower_invalid_score() -> None:
    valid_eval = _evaluation(True, [])
    invalid_eval = _evaluation(False, ["entropy"])
    selected, status = choose_candidate(
        [
            CandidateResult("invalid", object(), invalid_eval, -1),
            CandidateResult("valid", object(), valid_eval, 0),
        ]
    )
    assert status == "selected"
    assert selected.candidate_id == "valid"


def test_no_admissible_candidate_returns_best_failure() -> None:
    low = _evaluation(False, ["entropy"])
    high = _evaluation(False, ["tamper"])
    selected, status = choose_candidate(
        [
            CandidateResult("high", object(), high, score_evaluation(high)),
            CandidateResult("low", object(), low, score_evaluation(low)),
        ]
    )
    assert status == "no_admissible_candidate"
    assert selected.candidate_id == "low"
