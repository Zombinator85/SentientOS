"""Intent prioritization utilities for Codex."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional

import json
from collections import Counter

from .anomalies import Anomaly
from .rewrites import RewritePatch


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


SeverityScale = Mapping[str, float]
ImpactScale = Mapping[str, float]


_DEFAULT_SEVERITY_SCALE: SeverityScale = {
    "critical": 1.0,
    "high": 0.9,
    "warning": 0.65,
    "medium": 0.65,
    "info": 0.35,
    "low": 0.35,
    "debug": 0.1,
}

_DEFAULT_IMPACT_SCALE: ImpactScale = {
    "system": 1.0,
    "daemon": 0.85,
    "service": 0.75,
    "module": 0.65,
    "local": 0.45,
    "component": 0.45,
    "unknown": 0.35,
}


@dataclass
class PriorityWeights:
    """Weighting applied to each prioritization factor."""

    severity: float = 0.4
    frequency: float = 0.2
    impact: float = 0.25
    confidence: float = 0.15

    def normalized(self) -> "PriorityWeights":
        total = self.severity + self.frequency + self.impact + self.confidence
        if not total:
            return PriorityWeights(0.25, 0.25, 0.25, 0.25)
        return PriorityWeights(
            severity=self.severity / total,
            frequency=self.frequency / total,
            impact=self.impact / total,
            confidence=self.confidence / total,
        )


@dataclass
class PriorityFactors:
    """Normalized factors used to compute a weighted priority score."""

    severity: float
    frequency: float
    impact: float
    confidence: float


@dataclass
class IntentCandidate:
    """Represents a prioritized item Codex may act on."""

    candidate_id: str
    label: str
    item_type: str
    score: float
    payload: Dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False


class PriorityScoringEngine:
    """Score anomalies, rewrites, and integration events."""

    def __init__(
        self,
        *,
        severity_scale: SeverityScale | None = None,
        impact_scale: ImpactScale | None = None,
        weights: PriorityWeights | None = None,
        frequency_ceiling: float = 5.0,
    ) -> None:
        self._severity_scale = dict(_DEFAULT_SEVERITY_SCALE)
        if severity_scale:
            self._severity_scale.update({k.lower(): float(v) for k, v in severity_scale.items()})
        self._impact_scale = dict(_DEFAULT_IMPACT_SCALE)
        if impact_scale:
            self._impact_scale.update({k.lower(): float(v) for k, v in impact_scale.items()})
        self._weights = (weights or PriorityWeights()).normalized()
        self._frequency_ceiling = max(1.0, float(frequency_ceiling))

    def score(self, factors: PriorityFactors) -> float:
        weights = self._weights
        score = (
            weights.severity * factors.severity
            + weights.frequency * factors.frequency
            + weights.impact * factors.impact
            + weights.confidence * factors.confidence
        )
        return max(0.0, min(1.0, score))

    def score_anomaly(
        self,
        anomaly: Anomaly,
        *,
        frequency: float = 1.0,
        impact: str | float | None = None,
        confidence: float | None = None,
    ) -> float:
        return self.score(
            PriorityFactors(
                severity=self._coerce_severity(anomaly.severity),
                frequency=self._normalize_frequency(frequency),
                impact=self._coerce_impact(impact or anomaly.metadata.get("impact")),
                confidence=self._coerce_confidence(
                    confidence if confidence is not None else anomaly.metadata.get("confidence", 0.5)
                ),
            )
        )

    def score_rewrite(
        self,
        patch: RewritePatch,
        *,
        frequency: float = 1.0,
        impact: str | float | None = None,
        severity: str | float | None = None,
        confidence: float | None = None,
    ) -> float:
        anomaly_metadata = patch.metadata.get("anomaly") if isinstance(patch.metadata, Mapping) else {}
        impact_value = impact
        if impact_value is None and isinstance(anomaly_metadata, Mapping):
            impact_value = anomaly_metadata.get("impact")
        severity_value = severity
        if severity_value is None and isinstance(anomaly_metadata, Mapping):
            severity_value = anomaly_metadata.get("severity")
        return self.score(
            PriorityFactors(
                severity=self._coerce_severity(
                    severity_value if severity_value is not None else patch.urgency
                ),
                frequency=self._normalize_frequency(
                    frequency
                    if frequency is not None
                    else (anomaly_metadata.get("count") if isinstance(anomaly_metadata, Mapping) else 1.0)
                ),
                impact=self._coerce_impact(impact_value),
                confidence=self._coerce_confidence(confidence if confidence is not None else patch.confidence),
            )
        )

    def score_integration(
        self,
        payload: Mapping[str, Any],
        *,
        frequency: float = 1.0,
    ) -> float:
        return self.score(
            PriorityFactors(
                severity=self._coerce_severity(payload.get("severity", "info")),
                frequency=self._normalize_frequency(frequency),
                impact=self._coerce_impact(payload.get("impact")),
                confidence=self._coerce_confidence(payload.get("confidence", 0.5)),
            )
        )

    def _coerce_severity(self, raw: str | float | None) -> float:
        if raw is None:
            return 0.0
        if isinstance(raw, (int, float)):
            return max(0.0, min(1.0, float(raw)))
        return self._severity_scale.get(str(raw).lower(), 0.3)

    def _coerce_impact(self, raw: str | float | None) -> float:
        if raw is None:
            return self._impact_scale["unknown"]
        if isinstance(raw, (int, float)):
            return max(0.0, min(1.0, float(raw)))
        return self._impact_scale.get(str(raw).lower(), self._impact_scale["unknown"])

    def _coerce_confidence(self, raw: Any) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = 0.5
        return max(0.0, min(1.0, value))

    def _normalize_frequency(self, raw: float | None) -> float:
        if raw is None:
            return 0.0
        value = max(0.0, float(raw))
        normalized = min(value / self._frequency_ceiling, 1.0)
        return normalized


class IntentEmitter:
    """Persist and broadcast Codex's current intent."""

    def __init__(self, root: Path | str = Path("/pulse/intent"), *, bus: Any | None = None, now: Callable[[], datetime] | None = None) -> None:
        self._root = Path(root)
        self._bus = bus
        self._now = now or _default_now

    def emit(self, candidate: IntentCandidate | None) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "timestamp": self._now().isoformat(),
            "intent": None,
        }
        if candidate is not None:
            payload["intent"] = {
                "id": candidate.candidate_id,
                "label": candidate.label,
                "score": round(candidate.score, 4),
                "item_type": candidate.item_type,
                "acknowledged": candidate.acknowledged,
            }
            payload["message"] = f"Codex intends to prioritize {candidate.label} (score: {candidate.score:.2f})."
        else:
            payload["message"] = "Codex has no active intent."

        intent_path = self._root / "current.json"
        intent_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")

        if self._bus is not None:
            self._bus.publish(payload)

        return intent_path


class IntentPrioritizer:
    """Rank Codex actions and expose operator controls."""

    def __init__(
        self,
        scoring_engine: PriorityScoringEngine,
        *,
        emitter: IntentEmitter | None = None,
        integration_log: Path | str = Path("/integration/intent_log.jsonl"),
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._scoring = scoring_engine
        self._emitter = emitter
        self._integration_log = Path(integration_log)
        self._now = now or _default_now

        self._override_id: str | None = None
        self._lock_id: str | None = None
        self._acknowledged: set[str] = set()
        self._override_bias: MutableMapping[str, int] = {}
        self._candidates: Dict[str, IntentCandidate] = {}
        self._current_intent: IntentCandidate | None = None

    @property
    def candidates(self) -> List[IntentCandidate]:
        return sorted(self._candidates.values(), key=lambda candidate: candidate.score, reverse=True)

    @property
    def current_intent(self) -> IntentCandidate | None:
        return self._current_intent

    def evaluate(
        self,
        anomalies: Iterable[Anomaly] = (),
        rewrites: Iterable[RewritePatch] = (),
        integrations: Iterable[Mapping[str, Any]] = (),
    ) -> IntentCandidate | None:
        candidates: Dict[str, IntentCandidate] = {}

        # Anomalies ranked by frequency of daemon/kind pair
        anomaly_groups: Dict[str, List[Anomaly]] = {}
        for anomaly in anomalies:
            key = self._anomaly_key(anomaly)
            anomaly_groups.setdefault(key, []).append(anomaly)

        for key, items in anomaly_groups.items():
            sample = items[-1]
            frequency = len(items)
            impact = sample.metadata.get("impact") or ("daemon" if sample.metadata.get("daemon") else "local")
            confidence = sample.metadata.get("confidence")
            score = self._apply_bias(
                f"anomaly:{key}",
                self._scoring.score_anomaly(sample, frequency=frequency, impact=impact, confidence=confidence),
            )
            candidates[f"anomaly:{key}"] = IntentCandidate(
                candidate_id=f"anomaly:{key}",
                label=sample.description,
                item_type="anomaly",
                score=score,
                payload={
                    "severity": sample.severity,
                    "frequency": frequency,
                    "impact": impact,
                    "confidence": confidence if confidence is not None else sample.metadata.get("confidence", 0.5),
                    "metadata": dict(sample.metadata),
                },
                acknowledged=f"anomaly:{key}" in self._acknowledged,
            )

        # Rewrite proposals
        for patch in rewrites:
            candidate_id = f"rewrite:{patch.patch_id}"
            anomaly_metadata = patch.metadata.get("anomaly") if isinstance(patch.metadata, Mapping) else {}
            if isinstance(anomaly_metadata, Mapping):
                impact = anomaly_metadata.get("impact") or (
                    "daemon" if anomaly_metadata.get("daemon") else "local"
                )
                frequency = anomaly_metadata.get("count", 1)
                severity = anomaly_metadata.get("severity") or patch.urgency
            else:
                impact = patch.metadata.get("impact") if isinstance(patch.metadata, Mapping) else "local"
                frequency = 1
                severity = patch.urgency
            score = self._apply_bias(
                candidate_id,
                self._scoring.score_rewrite(
                    patch,
                    frequency=float(frequency),
                    impact=impact,
                    severity=severity,
                    confidence=patch.confidence,
                ),
            )
            candidates[candidate_id] = IntentCandidate(
                candidate_id=candidate_id,
                label=f"Rewrite {patch.daemon} {Path(patch.target_path).name}",
                item_type="rewrite",
                score=score,
                payload={
                    "patch_id": patch.patch_id,
                    "severity": severity,
                    "frequency": frequency,
                    "impact": impact,
                    "confidence": patch.confidence,
                    "metadata": patch.metadata,
                },
                acknowledged=candidate_id in self._acknowledged,
            )

        # Integration events (json logs, etc.)
        integration_counts: Counter[str] = Counter()
        integration_snapshots: Dict[str, Mapping[str, Any]] = {}
        for payload in integrations:
            event_id = str(payload.get("id") or payload.get("event_id") or payload.get("name") or "integration")
            key = f"integration:{event_id}"
            integration_counts[key] += 1
            integration_snapshots[key] = payload

        for key, count in integration_counts.items():
            payload = integration_snapshots[key]
            score = self._apply_bias(
                key,
                self._scoring.score_integration(payload, frequency=float(count)),
            )
            label = str(payload.get("description") or payload.get("label") or payload.get("id") or key)
            candidates[key] = IntentCandidate(
                candidate_id=key,
                label=label,
                item_type="integration",
                score=score,
                payload={**payload, "frequency": count},
                acknowledged=key in self._acknowledged,
            )

        self._candidates = candidates
        intent = self._select_intent()
        self._current_intent = intent

        if self._emitter is not None:
            self._emitter.emit(intent)

        return intent

    def override(self, candidate_id: str | None) -> None:
        self._override_id = candidate_id
        if candidate_id is not None:
            self._override_bias[candidate_id] = self._override_bias.get(candidate_id, 0) + 1

    def clear_override(self) -> None:
        self._override_id = None

    def lock_current(self) -> None:
        if self._current_intent is not None:
            self._lock_id = self._current_intent.candidate_id

    def unlock(self) -> None:
        self._lock_id = None

    def acknowledge(self, candidate_id: str | None = None) -> None:
        if candidate_id is None and self._current_intent is not None:
            candidate_id = self._current_intent.candidate_id
        if candidate_id is None:
            return
        self._acknowledged.add(candidate_id)
        if candidate_id in self._candidates:
            self._candidates[candidate_id].acknowledged = True
        if self._current_intent and self._current_intent.candidate_id == candidate_id:
            self._current_intent.acknowledged = True

    def fulfill(self, candidate_id: str | None = None, *, result: str = "fulfilled") -> Path:
        if candidate_id is None and self._current_intent is not None:
            candidate_id = self._current_intent.candidate_id
        if candidate_id is None:
            raise ValueError("No intent available to fulfill")
        candidate = self._candidates.get(candidate_id) or self._current_intent
        if candidate is None or candidate.candidate_id != candidate_id:
            raise KeyError(f"Unknown intent {candidate_id}")
        record = {
            "timestamp": self._now().isoformat(),
            "intent_id": candidate.candidate_id,
            "label": candidate.label,
            "score": round(candidate.score, 4),
            "result": result,
            "payload": candidate.payload,
        }
        self._integration_log.parent.mkdir(parents=True, exist_ok=True)
        with self._integration_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return self._integration_log

    def get_candidate(self, candidate_id: str) -> IntentCandidate | None:
        return self._candidates.get(candidate_id)

    def is_locked(self, candidate_id: str | None = None) -> bool:
        target = candidate_id or (self._current_intent.candidate_id if self._current_intent else None)
        if target is None:
            return False
        return self._lock_id == target

    def _anomaly_key(self, anomaly: Anomaly) -> str:
        daemon = str(anomaly.metadata.get("daemon") or anomaly.metadata.get("source") or "unknown")
        return f"{anomaly.kind}:{daemon}"

    def _apply_bias(self, candidate_id: str, score: float) -> float:
        bias = self._override_bias.get(candidate_id, 0)
        if not bias:
            return score
        boost = 1.0 + min(bias, 5) * 0.05
        return max(0.0, min(1.0, score * boost))

    def _select_intent(self) -> IntentCandidate | None:
        if not self._candidates:
            return None
        ranked = sorted(self._candidates.values(), key=lambda candidate: candidate.score, reverse=True)

        # Locked intent takes precedence if still available
        locked = None
        if self._lock_id:
            locked = next((candidate for candidate in ranked if candidate.candidate_id == self._lock_id), None)
            if locked is None:
                self._lock_id = None

        override_candidate = None
        if self._override_id:
            override_candidate = next(
                (candidate for candidate in ranked if candidate.candidate_id == self._override_id),
                None,
            )
            if override_candidate is None:
                self._override_id = None

        chosen = override_candidate or locked or ranked[0]
        chosen.acknowledged = chosen.candidate_id in self._acknowledged
        return chosen
