"""Governance drift response utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


@dataclass
class AgentStatus:
    weight: float = 1.0
    suppressed: bool = False
    aligned_verdicts: int = 0


class SanctionEngine:
    """Monitor divergence and adjust council privileges accordingly."""

    def __init__(
        self,
        *,
        divergence_threshold: float = 0.6,
        dissent_threshold: int = 3,
        quorum_failure_threshold: int = 2,
        trust_tolerance: float = 0.5,
        restore_after: int = 3,
        output_dir: Path | str | None = None,
    ) -> None:
        self.divergence_threshold = divergence_threshold
        self.dissent_threshold = dissent_threshold
        self.quorum_failure_threshold = quorum_failure_threshold
        self.trust_tolerance = trust_tolerance
        self.restore_after = restore_after
        self.output_dir = Path(output_dir) if output_dir else Path("governance")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._state: dict[str, AgentStatus] = {}

    def evaluate(
        self,
        bias_scores: Mapping[str, float],
        dissent_logs: Iterable[Mapping[str, object]],
        failed_quorums: int,
        aligned_verdicts: Mapping[str, int] | None = None,
    ) -> dict:
        aligned_verdicts = aligned_verdicts or {}
        dissent_counts = self._count_dissent(dissent_logs)
        report_entries: list[dict] = []
        trust_entries: list[dict] = []

        for agent, bias in bias_scores.items():
            status = self._state.setdefault(agent, AgentStatus())
            status.aligned_verdicts = aligned_verdicts.get(agent, status.aligned_verdicts)
            agent_dissent = dissent_counts.get(agent, 0)
            diverged = bias >= self.divergence_threshold or agent_dissent >= self.dissent_threshold

            action = None
            if diverged:
                status.weight = 0.5
                status.suppressed = failed_quorums >= self.quorum_failure_threshold
                action = "suppressed" if status.suppressed else "reduced_weight"
            elif status.suppressed or status.weight < 1.0:
                if status.aligned_verdicts >= self.restore_after:
                    status.weight = 1.0
                    status.suppressed = False
                    action = "restored"

            trust_score = self._compute_trust(bias, agent_dissent, failed_quorums)
            degraded = trust_score < self.trust_tolerance

            trust_entries.append(
                {"agent": agent, "trust_score": round(trust_score, 3), "degraded": degraded}
            )

            if action:
                report_entries.append(
                    {
                        "agent": agent,
                        "action": action,
                        "bias": bias,
                        "dissent": agent_dissent,
                        "failed_quorums": failed_quorums,
                        "weight": status.weight,
                        "suppressed": status.suppressed,
                    }
                )
            if degraded:
                report_entries.append(
                    {
                        "agent": agent,
                        "action": "trust_degradation",
                        "trust_score": round(trust_score, 3),
                        "note": "confidence below tolerance",
                    }
                )

        report_path = self.output_dir / "sanction_report.jsonl"
        trust_path = self.output_dir / "trust_index.jsonl"
        self._write_jsonl(report_path, report_entries)
        self._write_jsonl(trust_path, trust_entries)

        escalation = any(entry.get("degraded") for entry in trust_entries)
        return {
            "report_path": report_path,
            "trust_index": trust_path,
            "report_entries": report_entries,
            "trust_entries": trust_entries,
            "escalate_to_stewards": escalation,
        }

    def _count_dissent(self, dissent_logs: Iterable[Mapping[str, object]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in dissent_logs:
            agent = entry.get("agent")
            if not agent:
                continue
            counts[str(agent)] = counts.get(str(agent), 0) + 1
        return counts

    def _compute_trust(self, bias: float, dissent: int, failed_quorums: int) -> float:
        trust = 1.0 - (bias * 0.6) - (dissent * 0.1) - (failed_quorums * 0.1)
        return max(0.0, min(1.0, trust))

    def _write_jsonl(self, path: Path, entries: Iterable[Mapping[str, object]]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


__all__ = ["SanctionEngine", "AgentStatus"]
