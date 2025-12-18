from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, MutableMapping, Optional


def _tokenize(text: str) -> list[str]:
    return [token for token in text.lower().replace("/", " ").split() if token]


class EthicsCriticDaemon:
    """Score proposals against a harm-adjacent doctrine gradient."""

    def __init__(
        self,
        gradient: Optional[Mapping[str, float]] = None,
        *,
        log_path: Optional[Path] = None,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.gradient: MutableMapping[str, float] = {
            "coercion": 1.2,
            "exploit": 1.4,
            "manipulate": 1.1,
            "surveillance": 0.8,
            "override": 0.9,
            "shutdown": 0.5,
            "care": -0.2,
            "consent": -0.3,
            "audit": -0.1,
        }
        if gradient:
            self.gradient.update({key.lower(): float(value) for key, value in gradient.items()})
        self.log_path = log_path or repo_root / "logs" / "ethics_critic.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.touch(exist_ok=True)

    def evaluate(
        self,
        proposal_summary: str,
        projected_patch: str,
        *,
        alternate_strategies: Optional[Mapping[str, str]] = None,
    ) -> dict[str, object]:
        baseline = self._score_text(proposal_summary)
        projected = self._score_text(projected_patch)
        ethical_delta = round(projected - baseline, 3)

        alternatives_report = self._score_alternatives(alternate_strategies)
        recommended_strategy = self._pick_lowest_risk(projected, alternatives_report)

        record = {
            "proposal": proposal_summary,
            "baseline_score": baseline,
            "projected_score": projected,
            "ethical_delta": ethical_delta,
            "recommended_strategy": recommended_strategy,
            "alternatives": alternatives_report,
        }
        self._log(record)
        return record

    def _score_text(self, text: str) -> float:
        tokens = _tokenize(text)
        if not tokens:
            return 0.0
        score = sum(self.gradient.get(token, 0.0) for token in tokens)
        return round(score / len(tokens), 4)

    def _score_alternatives(self, alternate_strategies: Optional[Mapping[str, str]]) -> list[dict[str, object]]:
        scores: list[dict[str, object]] = []
        if not alternate_strategies:
            return scores
        for name, plan in alternate_strategies.items():
            score = self._score_text(plan)
            scores.append({"strategy": name, "score": score, "plan": plan})
        scores.sort(key=lambda item: item["score"])
        return scores

    def _pick_lowest_risk(self, projected_score: float, alternatives_report: list[dict[str, object]]) -> str:
        if not alternatives_report:
            return "current_patch" if projected_score <= 0 else "needs_revision"
        safest = alternatives_report[0]
        safest_score = float(safest.get("score", projected_score))
        if projected_score <= safest_score:
            return "current_patch"
        return str(safest.get("strategy", "current_patch"))

    def _log(self, payload: Mapping[str, object]) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


__all__ = ["EthicsCriticDaemon"]
