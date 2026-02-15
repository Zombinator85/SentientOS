from __future__ import annotations

from codex.integrity_daemon import IntegrityEvaluation, IntegrityEvaluationA
from codex.proposal_router import (
    CandidateResult,
    choose_candidate,
    maybe_escalate_k,
    promote_candidates,
    score_evaluation,
)


def _stage_a(valid: bool, codes: list[str] | None = None) -> IntegrityEvaluationA:
    codes = codes or []
    return IntegrityEvaluationA(
        valid_a=valid,
        reason_codes_a=list(codes),
        violations_a=[{"code": code, "detail": code} for code in codes],
        probe={},
        timestamp="2025-01-01T00:00:00+00:00",
        ledger_entry="ledger",
    )


def test_promote_candidates_prefers_valid_and_caps_to_m() -> None:
    promoted = promote_candidates(
        [
            ("c3", _stage_a(False, ["tamper"])),
            ("c1", _stage_a(True)),
            ("c2", _stage_a(True)),
        ],
        m=1,
    )
    assert promoted == ["c1"]


def test_promote_candidates_uses_best_failures_when_all_invalid() -> None:
    promoted = promote_candidates(
        [
            ("c3", _stage_a(False, ["entropy"])),
            ("c2", _stage_a(False, ["violation_of_vow"])),
            ("c1", _stage_a(False, ["tamper"])),
        ],
        m=2,
    )
    assert promoted == ["c1", "c2"]


def test_escalate_k_only_when_all_fail_stage_a(monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_ROUTER_MAX_K", "9")
    monkeypatch.setenv("SENTIENTOS_ROUTER_ESCALATE_ON_ALL_FAIL_A", "1")
    k_same, escalated_same = maybe_escalate_k(
        k=3,
        stage_a_results=[("a", _stage_a(True)), ("b", _stage_a(False, ["entropy"]))],
    )
    assert (k_same, escalated_same) == (3, False)

    k_next_1, escalated_1 = maybe_escalate_k(
        k=3,
        stage_a_results=[("a", _stage_a(False, ["tamper"])), ("b", _stage_a(False, ["entropy"]))],
    )
    k_next_2, escalated_2 = maybe_escalate_k(
        k=3,
        stage_a_results=[("a", _stage_a(False, ["tamper"])), ("b", _stage_a(False, ["entropy"]))],
    )
    assert (k_next_1, escalated_1) == (6, True)
    assert (k_next_2, escalated_2) == (6, True)


def _stage_b(valid: bool, codes: list[str] | None = None) -> IntegrityEvaluation:
    codes = codes or []
    return IntegrityEvaluation(
        valid=valid,
        reason_codes=list(codes),
        violations=[{"code": code, "detail": code} for code in codes],
        probe={},
        proof_report={},
        timestamp="2025-01-01T00:00:00+00:00",
        ledger_entry="ledger",
        quarantined=not valid,
    )


def test_staged_selection_matches_full_proof_when_admissible_survives() -> None:
    stage_a = [
        ("c1", _stage_a(True)),
        ("c2", _stage_a(True)),
        ("c3", _stage_a(False, ["tamper"])),
    ]
    promoted = promote_candidates(stage_a, m=2)
    assert promoted == ["c1", "c2"]

    full_results = [
        CandidateResult("c1", None, _stage_b(False, ["proof_invalid"]), score_evaluation(_stage_b(False, ["proof_invalid"]))),
        CandidateResult("c2", None, _stage_b(True), score_evaluation(_stage_b(True))),
    ]
    staged_results = [item for item in full_results if item.candidate_id in set(promoted)]
    full_selected, _ = choose_candidate(full_results)
    staged_selected, _ = choose_candidate(staged_results)
    assert staged_selected.candidate_id == full_selected.candidate_id == "c2"
