from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Mapping, Optional

from sentientos.council.governance_council import GovernanceCouncil

from .amendment import Amendment
from .invariants import evaluate_invariants
from .quarantine import quarantine_amendment


@dataclass
class AmendmentIntercept:
    amendment_id: str
    status: str
    quorum_met: bool
    lineage_recorded: bool
    reasons: List[str]
    council_vote: Mapping[str, object] | None = None
    quarantine_path: Optional[str] = None


class AmendmentSentinel:
    """Intercept self-modification attempts and enforce council oversight."""

    def __init__(
        self,
        *,
        council: Optional[GovernanceCouncil] = None,
        lineage_log: Optional[Path] = None,
        holds_log: Optional[Path] = None,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.council = council or GovernanceCouncil()
        self.lineage_log = lineage_log or repo_root / "council" / "lineage_justifications.jsonl"
        self.holds_log = holds_log or repo_root / "council" / "held_amendments.jsonl"
        self.lineage_log.parent.mkdir(parents=True, exist_ok=True)
        self.holds_log.parent.mkdir(parents=True, exist_ok=True)
        self.lineage_log.touch(exist_ok=True)
        self.holds_log.touch(exist_ok=True)

    def intercept(
        self,
        amendment: Amendment,
        *,
        lineage: str,
        justification: str,
        proposal_type: str = "doctrine_update",
    ) -> AmendmentIntercept:
        """Validate doctrine, call the council, and gate merge approval."""

        violations = evaluate_invariants(amendment)
        if violations:
            quarantine_path = quarantine_amendment(amendment, violations)
            return AmendmentIntercept(
                amendment_id=amendment.id,
                status="quarantined",
                quorum_met=False,
                lineage_recorded=False,
                reasons=violations,
                quarantine_path=quarantine_path,
            )

        vote = self.council.submit_proposal(
            amendment.id,
            proposal_type,
            origin=amendment.proposer,
            summary=amendment.summary,
            proposed_by=amendment.proposer,
        )
        vote = self.council.conduct_vote(vote)
        quorum_met = vote.status == "approved"

        lineage_recorded = self._record_lineage(amendment, lineage, justification)
        approved = quorum_met and lineage_recorded
        reasons: List[str] = []
        if not quorum_met:
            reasons.append("insufficient quorum")
        if not lineage_recorded:
            reasons.append("missing lineage justification")

        status = "approved" if approved else "delayed"
        if status == "delayed":
            self._record_hold(amendment, reasons, vote)

        return AmendmentIntercept(
            amendment_id=amendment.id,
            status=status,
            quorum_met=quorum_met,
            lineage_recorded=lineage_recorded,
            reasons=reasons,
            council_vote=vote.to_dict(),
        )

    def _record_lineage(self, amendment: Amendment, lineage: str, justification: str) -> bool:
        clean_lineage = (lineage or "").strip()
        clean_justification = (justification or "").strip()
        if not clean_lineage or not clean_justification:
            return False

        payload = {
            "amendment_id": amendment.id,
            "lineage": clean_lineage,
            "justification": clean_justification,
            "summary": amendment.summary,
        }
        with self.lineage_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return True

    def _record_hold(self, amendment: Amendment, reasons: Iterable[str], vote: Mapping[str, object]) -> None:
        payload = {
            "amendment_id": amendment.id,
            "reasons": list(reasons),
            "vote": vote,
            "summary": amendment.summary,
        }
        with self.holds_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


__all__ = ["AmendmentSentinel", "AmendmentIntercept"]
