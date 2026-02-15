"""Verifier-driven candidate routing helpers."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Iterable, List, Sequence, Tuple

from .integrity_daemon import IntegrityEvaluation, IntegrityEvaluationA


@dataclass(slots=True)
class CandidateResult:
    """Single evaluated candidate tracked by the router."""

    candidate_id: str
    proposal: Any
    evaluation: IntegrityEvaluation
    score: int
    rank: int = 0


def score_evaluation(evaluation: IntegrityEvaluation) -> int:
    """Return deterministic severity score from integrity violations."""

    if evaluation.valid:
        return 0
    weights = {
        "tamper": 1000,
        "proof_invalid": 500,
        "violation_of_vow": 200,
        "entropy": 100,
    }
    score = 0
    for violation in evaluation.violations:
        code = str(violation.get("code", "unknown"))
        score += int(weights.get(code, 150))
    score += len(evaluation.violations) * 5
    return score


def _sort_key(item: CandidateResult) -> Tuple[int, int, str]:
    return (0 if item.evaluation.valid else 1, int(item.score), item.candidate_id)


def rank_candidates(results: Sequence[CandidateResult]) -> List[CandidateResult]:
    """Return ranked candidates with deterministic ordering."""

    ranked = sorted(results, key=_sort_key)
    for index, item in enumerate(ranked, start=1):
        item.rank = index
    return ranked


def choose_candidate(results: Sequence[CandidateResult]) -> tuple[CandidateResult, str]:
    """Choose best admissible candidate or best failure diagnostics."""

    if not results:
        raise ValueError("results cannot be empty")
    ranked = rank_candidates(results)
    selected = ranked[0]
    status = "selected" if selected.evaluation.valid else "no_admissible_candidate"
    return selected, status


def top_violation_codes(violations: Iterable[dict[str, Any]], *, limit: int = 3) -> list[str]:
    counts: dict[str, int] = {}
    for violation in violations:
        code = str(violation.get("code", "unknown"))
        counts[code] = counts.get(code, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [code for code, _ in ranked[:limit]]


def score_evaluation_a(evaluation: IntegrityEvaluationA) -> int:
    """Return deterministic severity score from stage-A violations."""

    if evaluation.valid_a:
        return 0
    weights = {
        "tamper": 1000,
        "violation_of_vow": 200,
        "entropy": 100,
    }
    score = 0
    for violation in evaluation.violations_a:
        code = str(violation.get("code", "unknown"))
        score += int(weights.get(code, 150))
    score += len(evaluation.violations_a) * 5
    return score


def _severity_class_a(evaluation: IntegrityEvaluationA) -> int:
    if evaluation.valid_a:
        return 0
    codes = {str(item.get("code", "unknown")) for item in evaluation.violations_a}
    if "tamper" in codes:
        return 1
    if "violation_of_vow" in codes:
        return 2
    if "entropy" in codes:
        return 3
    return 4


def rank_stage_a(ea: IntegrityEvaluationA, *, candidate_id: str) -> tuple[int, int, int, str]:
    """Deterministic rank tuple for stage-A promotion ordering."""

    return (
        0 if ea.valid_a else 1,
        _severity_class_a(ea),
        len(ea.violations_a),
        candidate_id,
    )


def promote_candidates(
    stage_a_results: Sequence[tuple[str, IntegrityEvaluationA]],
    *,
    m: int,
) -> list[str]:
    """Select candidate ids to promote to stage B based on stage-A verdicts."""

    if m <= 0 or not stage_a_results:
        return []
    ranked = sorted(stage_a_results, key=lambda item: rank_stage_a(item[1], candidate_id=item[0]))
    valid_ids = [candidate_id for candidate_id, evaluation in ranked if evaluation.valid_a]
    if valid_ids:
        return valid_ids[:m]
    return [candidate_id for candidate_id, _ in ranked[:m]]


def maybe_escalate_k(
    *,
    k: int,
    stage_a_results: Sequence[tuple[str, IntegrityEvaluationA]],
) -> tuple[int, bool]:
    """Deterministically escalate K only when all stage-A candidates fail."""

    max_k = max(int(os.getenv("SENTIENTOS_ROUTER_MAX_K", "9")), 1)
    escalate_enabled = os.getenv("SENTIENTOS_ROUTER_ESCALATE_ON_ALL_FAIL_A", "1") not in {
        "0",
        "false",
        "False",
    }
    if not escalate_enabled:
        return k, False
    any_valid_a = any(evaluation.valid_a for _, evaluation in stage_a_results)
    if any_valid_a:
        return k, False
    next_k = min(max_k, max(k, 1) * 2)
    if next_k <= k:
        return k, False
    return next_k, True
