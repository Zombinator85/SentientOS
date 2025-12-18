from __future__ import annotations

"""Governance signal reducer.

This utility does not mutate any source ledgers. It consumes previously emitted
records from the council, Concord daemon, sanction engine, and amendment
sentinel and produces a consolidated, auditable summary for a single proposal
cycle. The reducer focuses on compression (eliminating redundant signals) and
confidence deltas while retaining the full fidelity of every upstream record.
"""

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class GovernanceOutcome:
    proposal_id: str
    proposal_type: str
    summary: str
    confidence_delta: float
    signals: tuple[str, ...]


class GovernanceReducer:
    """Aggregate governance signals without altering source material."""

    def __init__(self, quorum_penalty: float = 0.15, dissent_penalty: float = 0.1) -> None:
        self.quorum_penalty = quorum_penalty
        self.dissent_penalty = dissent_penalty

    def reduce(
        self,
        council_records: Sequence[Mapping[str, object]],
        concord_outputs: Sequence[Mapping[str, object]],
        sanction_reports: Sequence[Mapping[str, object]],
        amendment_intercepts: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        """Return a consolidated view of governance outcomes.

        The reducer only reads the provided sequences; callers retain complete
        copies of the original ledgers. Confidence deltas are derived from
        overlapping signals such as repeated quorum failures or identical
        dissent patterns.
        """

        council_snapshot = deepcopy(list(council_records))
        concord_snapshot = deepcopy(list(concord_outputs))
        sanction_snapshot = deepcopy(list(sanction_reports))
        amendment_snapshot = deepcopy(list(amendment_intercepts))

        quorum_failures = [record for record in council_snapshot if str(record.get("status")) == "no_quorum"]
        quorum_penalty = self._quorum_penalty(quorum_failures)

        dissent_penalty = self._dissent_penalty(sanction_snapshot)

        outcomes: list[GovernanceOutcome] = []
        grouped = self._group_by_proposal(council_snapshot, amendment_snapshot)
        concord_terms = {entry.get("term") for entry in concord_snapshot if entry.get("term")}

        for proposal_id, payload in grouped.items():
            council_entry = payload.get("council") or {}
            amendment_entry = payload.get("amendment") or {}
            signals: list[str] = []
            if council_entry:
                signals.append(f"council:{council_entry.get('status', 'unknown')}")
            if amendment_entry:
                signals.append(f"amendment:{amendment_entry.get('disposition', 'observed')}")
            if proposal_id in concord_terms:
                signals.append("concord:term_alignment")

            delta = 0.0 - quorum_penalty - dissent_penalty
            outcomes.append(
                GovernanceOutcome(
                    proposal_id=proposal_id,
                    proposal_type=str(council_entry.get("proposal_type", "unknown")),
                    summary=str(council_entry.get("summary") or amendment_entry.get("summary") or ""),
                    confidence_delta=round(delta, 3),
                    signals=tuple(sorted(set(signals))),
                )
            )

        return {
            "outcomes": outcomes,
            "confidence": {outcome.proposal_id: outcome.confidence_delta for outcome in outcomes},
            "source_records": {
                "council": council_snapshot,
                "concord": concord_snapshot,
                "sanctions": sanction_snapshot,
                "amendments": amendment_snapshot,
            },
            "quorum_overlap": len(quorum_failures) > 1,
            "dissent_overlap": self._has_repeated_dissent(sanction_snapshot),
        }

    def _quorum_penalty(self, quorum_failures: Iterable[Mapping[str, object]]) -> float:
        failures = list(quorum_failures)
        if len(failures) <= 1:
            return 0.0
        return round(self.quorum_penalty * min(len(failures) - 1, 3), 3)

    def _dissent_penalty(self, sanction_reports: Iterable[Mapping[str, object]]) -> float:
        if not self._has_repeated_dissent(sanction_reports):
            return 0.0
        return round(self.dissent_penalty, 3)

    def _has_repeated_dissent(self, sanction_reports: Iterable[Mapping[str, object]]) -> bool:
        dissent_patterns: Counter[tuple[str, int]] = Counter()
        for entry in sanction_reports:
            agent = str(entry.get("agent") or "")
            dissent = int(entry.get("dissent", entry.get("dissent_count", 0)) or 0)
            if agent:
                dissent_patterns[(agent, dissent)] += 1
        return any(count > 1 for count in dissent_patterns.values())

    def _group_by_proposal(
        self,
        council_records: Sequence[Mapping[str, object]],
        amendment_intercepts: Sequence[Mapping[str, object]],
    ) -> dict[str, dict[str, Mapping[str, object]]]:
        grouped: dict[str, dict[str, Mapping[str, object]]] = defaultdict(dict)
        for entry in council_records:
            proposal_id = str(entry.get("proposal_id") or entry.get("id") or "")
            if not proposal_id:
                continue
            grouped[proposal_id]["council"] = entry
        for entry in amendment_intercepts:
            proposal_id = str(entry.get("proposal_id") or entry.get("id") or "")
            if not proposal_id:
                continue
            grouped[proposal_id]["amendment"] = entry
        return grouped


__all__ = ["GovernanceReducer", "GovernanceOutcome"]
