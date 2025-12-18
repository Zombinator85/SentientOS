from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Mapping


@dataclass
class CodexGradientCalibrator:
    """Reweight prompt templates based on covenant violation motifs."""

    template_weights: dict[str, float] = field(default_factory=dict)

    def calibrate(
        self,
        templates: Iterable[str] | Mapping[str, float],
        violations: Iterable[Mapping[str, object]] | None = None,
        *,
        penalty: float = 0.2,
    ) -> dict[str, float]:
        weights = dict(self.template_weights)
        if isinstance(templates, Mapping):
            weights.update({str(k): float(v) for k, v in templates.items()})
        else:
            for template in templates:
                weights.setdefault(str(template), 1.0)

        violation_counter: Counter[str] = Counter()
        for violation in violations or []:
            motifs = violation.get("motifs") or violation.get("tokens") or []
            if isinstance(motifs, str):
                motifs = motifs.split()
            for motif in motifs:
                violation_counter[str(motif).lower()] += 1

        for template, current_weight in list(weights.items()):
            lowered = template.lower()
            penalty_total = 0.0
            for motif, count in violation_counter.items():
                if motif and motif in lowered:
                    penalty_total += penalty * count
            weights[template] = max(0.0, round(current_weight - penalty_total, 3))

        self.template_weights = weights
        return weights


__all__ = ["CodexGradientCalibrator"]
