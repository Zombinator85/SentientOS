from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


@dataclass
class DriftEvent:
    pair: Tuple[str, str]
    divergence: float
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return {"pair": list(self.pair), "divergence": self.divergence, "reason": self.reason}


def load_jsonl(path: Path) -> List[dict]:
    records: List[dict] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


class CouncilBiasAnalyzer:
    """Analyze council voting behavior for bias and drift."""

    def __init__(self, vote_ledger_path: Path, verdicts_path: Path, divergence_threshold: float = 0.7):
        self.vote_ledger_path = Path(vote_ledger_path)
        self.verdicts_path = Path(verdicts_path)
        self.divergence_threshold = divergence_threshold

    def _co_vote_pairs(self, votes: Iterable[dict]) -> Dict[Tuple[str, str], Counter]:
        pair_counts: Dict[Tuple[str, str], Counter] = defaultdict(Counter)
        votes_by_proposal: Dict[str, Dict[str, str]] = defaultdict(dict)
        for entry in votes:
            proposal = str(entry.get("proposal"))
            agent = entry.get("agent")
            ballot = entry.get("vote")
            if not proposal or not agent or ballot is None:
                continue
            votes_by_proposal[proposal][agent] = str(ballot)
        for _, agent_votes in votes_by_proposal.items():
            for first, second in combinations(sorted(agent_votes.keys()), 2):
                pair = (first, second)
                disagree = agent_votes[first] != agent_votes[second]
                pair_counts[pair]["total"] += 1
                if disagree:
                    pair_counts[pair]["divergent"] += 1
        return pair_counts

    def _alignment_divergence(self, votes: Iterable[dict]) -> Dict[str, float]:
        divergence: Dict[str, float] = {}
        for pair, counts in self._co_vote_pairs(votes).items():
            total = counts["total"]
            divergent = counts["divergent"]
            divergence["::".join(pair)] = divergent / total if total else 0.0
        return divergence

    def _symbolic_polarization(self, verdicts: Iterable[dict]) -> Dict[str, float]:
        rejection_counts: Dict[str, Counter] = defaultdict(Counter)
        for entry in verdicts:
            agent = entry.get("agent")
            proposal_type = str(entry.get("proposal_type", ""))
            decision = str(entry.get("decision", ""))
            if not agent or not proposal_type:
                continue
            if "semantic_merge" in proposal_type or "symbolic" in proposal_type:
                rejection_counts[agent]["total"] += 1
                if decision.lower() in {"reject", "veto"}:
                    rejection_counts[agent]["rejects"] += 1
        polarization: Dict[str, float] = {}
        for agent, counts in rejection_counts.items():
            total = counts["total"]
            polarization[agent] = counts["rejects"] / total if total else 0.0
        return polarization

    def _role_favoritism(self, votes: Iterable[dict]) -> Dict[str, float]:
        role_counts: Dict[str, Counter] = defaultdict(Counter)
        for entry in votes:
            role = entry.get("proposer_role") or entry.get("role")
            decision = str(entry.get("vote", "")).lower()
            if not role:
                continue
            role_counts[role]["total"] += 1
            if decision in {"approve", "yes", "accept"}:
                role_counts[role]["approvals"] += 1
        favoritism: Dict[str, float] = {}
        for role, counts in role_counts.items():
            total = counts["total"]
            favoritism[role] = counts["approvals"] / total if total else 0.0
        return favoritism

    def _drift_events(self, alignment: Dict[str, float]) -> List[DriftEvent]:
        events: List[DriftEvent] = []
        for pair_key, divergence in alignment.items():
            if divergence > self.divergence_threshold:
                left, right = pair_key.split("::", maxsplit=1)
                events.append(
                    DriftEvent(pair=(left, right), divergence=divergence, reason="agent opposition entropy exceeds threshold")
                )
        return events

    def analyze(self) -> Dict[str, object]:
        votes = load_jsonl(self.vote_ledger_path)
        verdicts = load_jsonl(self.verdicts_path)

        alignment = self._alignment_divergence(votes)
        symbolic_polarization = self._symbolic_polarization(verdicts)
        role_favoritism = self._role_favoritism(votes)
        drift_events = self._drift_events(alignment)

        return {
            "alignment_divergence": alignment,
            "symbolic_polarization": symbolic_polarization,
            "role_favoritism": role_favoritism,
            "drift_events": [event.to_dict() for event in drift_events],
        }

    def render_json(self) -> str:
        return json.dumps(self.analyze(), indent=2, sort_keys=True)

    def render_markdown(self) -> str:
        report = self.analyze()
        lines = ["# Council Bias Analyzer", "", "## Alignment Divergence"]
        if report["alignment_divergence"]:
            lines.append("| Pair | Divergence |")
            lines.append("| --- | --- |")
            for pair, value in sorted(report["alignment_divergence"].items()):
                lines.append(f"| {pair} | {value:.2f} |")
        else:
            lines.append("No shared proposals recorded.")

        lines.extend(["", "## Symbolic Polarization"])
        if report["symbolic_polarization"]:
            lines.append("| Agent | Rejection Ratio |")
            lines.append("| --- | --- |")
            for agent, ratio in sorted(report["symbolic_polarization"].items()):
                lines.append(f"| {agent} | {ratio:.2f} |")
        else:
            lines.append("No semantic merge decisions recorded.")

        lines.extend(["", "## Role Favoritism"])
        if report["role_favoritism"]:
            lines.append("| Role | Approval Rate |")
            lines.append("| --- | --- |")
            for role, rate in sorted(report["role_favoritism"].items()):
                lines.append(f"| {role} | {rate:.2f} |")
        else:
            lines.append("No role-specific votes recorded.")

        if report["drift_events"]:
            lines.extend(["", "## Drift Events"])
            for event in report["drift_events"]:
                pair = "::".join(event["pair"])
                lines.append(f"- **{pair}** divergence {event['divergence']:.2f}: {event['reason']}")
        return "\n".join(lines)
