from __future__ import annotations

"""Read-only persona boundary evaluator.

The enforcer consumes persona lint results, decay audits, and continuity checks
and emits boundary violation notices without enqueuing remediation, votes, or
retraining jobs.
"""

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class PersonaBoundaryViolation:
    persona: str
    category: str
    detail: str


class PersonaBoundaryEnforcer:
    """Detect persona boundary violations without side effects."""

    def evaluate(
        self,
        persona_lint: Sequence[Mapping[str, object]],
        decay_audits: Sequence[Mapping[str, object]],
        continuity_checks: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        violations: list[PersonaBoundaryViolation] = []
        violations.extend(self._lint_violations(persona_lint))
        violations.extend(self._decay_violations(decay_audits))
        violations.extend(self._continuity_flags(continuity_checks))
        return {
            "violations": violations,
            "can_enqueue_actions": False,
            "can_vote": False,
            "can_patch": False,
        }

    def _lint_violations(self, lint_entries: Iterable[Mapping[str, object]]) -> list[PersonaBoundaryViolation]:
        violations: list[PersonaBoundaryViolation] = []
        for entry in lint_entries:
            persona = str(entry.get("persona") or "").strip()
            issue = str(entry.get("issue") or "").lower()
            if not persona or not issue:
                continue
            if "self-justify" in issue or "self reinforcement" in issue:
                violations.append(
                    PersonaBoundaryViolation(persona=persona, category="narrative_loop", detail=issue)
                )
        return violations

    def _decay_violations(self, audits: Iterable[Mapping[str, object]]) -> list[PersonaBoundaryViolation]:
        violations: list[PersonaBoundaryViolation] = []
        for entry in audits:
            persona = str(entry.get("persona") or "").strip()
            decay_score = float(entry.get("decay_score", 0.0))
            if persona and decay_score > 0.6:
                violations.append(
                    PersonaBoundaryViolation(
                        persona=persona,
                        category="decay_drift",
                        detail=f"decay_score={decay_score}",
                    )
                )
        return violations

    def _continuity_flags(self, checks: Iterable[Mapping[str, object]]) -> list[PersonaBoundaryViolation]:
        violations: list[PersonaBoundaryViolation] = []
        for entry in checks:
            persona = str(entry.get("persona") or "").strip()
            if not persona:
                continue
            continuity_gaps = int(entry.get("gaps", 0))
            if continuity_gaps > 0:
                violations.append(
                    PersonaBoundaryViolation(
                        persona=persona,
                        category="continuity_gap",
                        detail=f"gaps={continuity_gaps}",
                    )
                )
        return violations


__all__ = ["PersonaBoundaryViolation", "PersonaBoundaryEnforcer"]
