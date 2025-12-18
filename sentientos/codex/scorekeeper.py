"""Codex patch and proposal scorekeeping."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable


@dataclass
class PatchRecord:
    successes: int = 0
    failures: int = 0
    reverts: int = 0

    @property
    def success_rate(self) -> float:
        total = self.successes + self.failures
        return self.successes / total if total else 1.0


@dataclass
class ProposalRecord:
    submitted: int = 0
    rejected: int = 0

    @property
    def rejection_rate(self) -> float:
        return self.rejected / self.submitted if self.submitted else 0.0


@dataclass
class CodexScorecard:
    patches: Dict[str, PatchRecord] = field(default_factory=dict)
    proposals: Dict[str, ProposalRecord] = field(default_factory=dict)

    def to_serialisable(self) -> dict:
        return {
            "patches": {
                module: {
                    "success_rate": record.success_rate,
                    "successes": record.successes,
                    "failures": record.failures,
                    "reverts": record.reverts,
                }
                for module, record in self.patches.items()
            },
            "proposals": {
                category: {
                    "rejection_rate": record.rejection_rate,
                    "submitted": record.submitted,
                    "rejected": record.rejected,
                }
                for category, record in self.proposals.items()
            },
        }


class CodexScorekeeper:
    """Track Codex patch and proposal performance metrics."""

    def __init__(
        self,
        output_dir: Path | str,
        *,
        success_threshold: float = 0.7,
        rejection_threshold: float = 0.4,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.scorecard_path = self.output_dir / "codex_scorecard.jsonl"
        self.review_path = self.output_dir / "codex_self_review_suggested.jsonl"
        self.success_threshold = success_threshold
        self.rejection_threshold = rejection_threshold
        self.scorecard = CodexScorecard()

    def record_patch(self, module: str, *, success: bool, reverted: bool = False) -> None:
        record = self.scorecard.patches.setdefault(module, PatchRecord())
        if success:
            record.successes += 1
        else:
            record.failures += 1
        if reverted:
            record.reverts += 1

    def record_proposal(self, category: str, *, outcome: str) -> None:
        record = self.scorecard.proposals.setdefault(category, ProposalRecord())
        record.submitted += 1
        if outcome.lower() in {"reject", "rejected", "failed"}:
            record.rejected += 1

    def compile(self) -> dict:
        serialised = self.scorecard.to_serialisable()
        degradation = self._degradation_signals(serialised)
        self._write_jsonl(self.scorecard_path, [serialised])
        if degradation:
            self._write_jsonl(
                self.review_path,
                [
                    {
                        "trigger": "performance_degradation",
                        "signals": degradation,
                    }
                ],
            )
        return {"scorecard": serialised, "degradation_signals": degradation}

    def _degradation_signals(self, serialised: dict) -> list[dict]:
        signals: list[dict] = []
        for module, metrics in serialised.get("patches", {}).items():
            success_rate = metrics.get("success_rate", 1.0)
            if success_rate < self.success_threshold:
                signals.append({"module": module, "success_rate": success_rate})
            if metrics.get("reverts", 0) > 0:
                signals.append({"module": module, "reverts": metrics["reverts"]})
        for category, metrics in serialised.get("proposals", {}).items():
            rejection_rate = metrics.get("rejection_rate", 0.0)
            if rejection_rate > self.rejection_threshold:
                signals.append({"category": category, "rejection_rate": rejection_rate})
        return signals

    def _write_jsonl(self, path: Path, entries: Iterable[dict]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


__all__ = [
    "CodexScorekeeper",
    "CodexScorecard",
    "PatchRecord",
    "ProposalRecord",
]
