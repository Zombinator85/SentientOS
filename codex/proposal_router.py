"""Verifier-driven candidate routing helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Sequence, Tuple

from .integrity_daemon import IntegrityEvaluation


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
