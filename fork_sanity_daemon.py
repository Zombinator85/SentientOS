from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping


def _score_behavior(proposal: Mapping[str, object]) -> float:
    metrics = proposal.get("behavioral_metrics")
    if isinstance(metrics, Mapping):
        values = [v for v in metrics.values() if isinstance(v, (int, float))]
        if values:
            return sum(values) / len(values)
    return 0.0


def _symbolic_set(proposal: Mapping[str, object]) -> set[str]:
    symbolic = proposal.get("symbolic_trace") or proposal.get("symbols") or []
    if isinstance(symbolic, str):
        return set(symbolic.split())
    if isinstance(symbolic, Mapping):
        return set(symbolic.keys())
    if isinstance(symbolic, (list, tuple, set)):
        return {str(item) for item in symbolic}
    return set()


@dataclass
class ForkSanityDaemon:
    """Evaluate divergent council proposals in a sandbox and flag quorum breaches."""

    rationale_path: Path = Path("fork_sanity_rationale.jsonl")
    sandbox_runner: Callable[[Mapping[str, object]], Mapping[str, object]] | None = None

    def _simulate(self, proposal: Mapping[str, object]) -> Mapping[str, object]:
        if self.sandbox_runner:
            return self.sandbox_runner(proposal)
        return proposal

    def _divergence(self, a: Mapping[str, object], b: Mapping[str, object]) -> tuple[float, float]:
        behavior_a = _score_behavior(a)
        behavior_b = _score_behavior(b)
        behavioral_divergence = abs(behavior_a - behavior_b)

        symbols_a = _symbolic_set(a)
        symbols_b = _symbolic_set(b)
        union = symbols_a | symbols_b
        intersection = symbols_a & symbols_b
        symbolic_divergence = 1.0 - (len(intersection) / len(union)) if union else 0.0

        return behavioral_divergence, symbolic_divergence

    def evaluate(
        self,
        proposal_a: Mapping[str, object],
        proposal_b: Mapping[str, object],
        *,
        doctrine_tolerance: float = 0.3,
    ) -> dict:
        simulated_a = self._simulate(proposal_a)
        simulated_b = self._simulate(proposal_b)

        behavioral_divergence, symbolic_divergence = self._divergence(simulated_a, simulated_b)
        composite_score = (behavioral_divergence + symbolic_divergence) / 2
        quorum_flagged = composite_score > doctrine_tolerance

        record = {
            "behavioral_divergence": round(behavioral_divergence, 3),
            "symbolic_divergence": round(symbolic_divergence, 3),
            "composite_divergence": round(composite_score, 3),
            "doctrine_tolerance": doctrine_tolerance,
            "quorum_flagged": quorum_flagged,
            "proposal_a": simulated_a,
            "proposal_b": simulated_b,
        }

        self.rationale_path.parent.mkdir(parents=True, exist_ok=True)
        with self.rationale_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

        return record


__all__ = ["ForkSanityDaemon"]
