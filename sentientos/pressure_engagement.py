"""Pressure-to-stitch engagement engine.

This module accumulates pressure signals against constraints and forces explicit
engagement records ("stitches") once thresholds are crossed. It is intentionally
deterministic and does not alter policy or permission outcomes; it only
annotates review flow and telemetry.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import time
import uuid
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

import affective_context as ac
from sentientos.constraint_registry import ConstraintRegistry

PRESSURE_SCHEMA_VERSION = "1.0"
ENGAGEMENT_SCHEMA_VERSION = "1.0"


class PressureDecayError(RuntimeError):
    """Raised when decay is attempted without review."""


class EngagementRequiredError(RuntimeError):
    """Raised when chronic pressure is vented without an engagement."""


@dataclass(frozen=True)
class PressureSignal:
    constraint_id: str
    magnitude: float
    reason: str
    affective_context: Mapping[str, float]
    blocked: bool
    timestamp: float = field(default_factory=lambda: time.time())

    def to_payload(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["schema_version"] = PRESSURE_SCHEMA_VERSION
        payload["affective_context"] = dict(self.affective_context)
        return payload


@dataclass
class ConstraintPressureState:
    constraint_id: str
    signals: List[PressureSignal] = field(default_factory=list)
    total_pressure: float = 0.0
    blocked_count: int = 0
    pending_engagement_id: Optional[str] = None
    defer_until: Optional[float] = None
    last_reviewed_at: Optional[float] = None
    ignored_reason: Optional[str] = None

    def record(self, signal: PressureSignal, *, max_signals: int) -> None:
        self.signals.append(signal)
        if len(self.signals) > max_signals:
            del self.signals[:-max_signals]
        self.total_pressure += max(0.0, float(signal.magnitude))
        if signal.blocked:
            self.blocked_count += 1

    def status(self, *, chronic_threshold: float, blockage_threshold: int) -> str:
        if self.ignored_reason:
            return "ignored"
        if self.total_pressure <= 0:
            return "resolved"
        if self.total_pressure >= chronic_threshold or self.blocked_count >= blockage_threshold:
            return "chronic"
        return "transient"

    def reset(self) -> None:
        self.signals.clear()
        self.total_pressure = 0.0
        self.blocked_count = 0
        self.pending_engagement_id = None
        self.defer_until = None
        self.last_reviewed_at = time.time()
        self.ignored_reason = None

    def require_review(self, *, now: float, chronic_threshold: float, blockage_threshold: int) -> bool:
        if self.status(chronic_threshold=chronic_threshold, blockage_threshold=blockage_threshold) != "chronic":
            return False
        if self.pending_engagement_id is None:
            return True
        if self.defer_until is None:
            return False
        return self.defer_until <= now


@dataclass(frozen=True)
class ConstraintEngagementRecord:
    engagement_id: str
    constraint_id: str
    decision: str
    justification: str
    created_at: float
    signals: Tuple[PressureSignal, ...]
    affective_context_summary: Mapping[str, float]
    reviewer: Optional[str] = None
    defer_until: Optional[float] = None
    lineage_from: Optional[str] = None

    def to_payload(self) -> Dict[str, object]:
        payload = {
            "schema_version": ENGAGEMENT_SCHEMA_VERSION,
            "engagement_id": self.engagement_id,
            "constraint_id": self.constraint_id,
            "decision": self.decision,
            "justification": self.justification,
            "created_at": self.created_at,
            "signals": [signal.to_payload() for signal in self.signals],
            "affective_context_summary": dict(self.affective_context_summary),
            "reviewer": self.reviewer,
            "defer_until": self.defer_until,
            "lineage_from": self.lineage_from,
        }
        payload["pressure_score"] = self.pressure_score
        return payload

    @property
    def pressure_score(self) -> float:
        if not self.signals:
            return 0.0
        return round(sum(sig.magnitude for sig in self.signals) / len(self.signals), 3)


class ConstraintEngagementEngine:
    """Accumulate pressure and require engagements when limits are crossed."""

    def __init__(
        self,
        *,
        chronic_threshold: float = 1.5,
        blockage_threshold: int = 3,
        max_signals: int = 25,
        default_defer_seconds: float = 90.0,
        registry: Optional[ConstraintRegistry] = None,
    ) -> None:
        self._states: Dict[str, ConstraintPressureState] = {}
        self._engagements: Dict[str, List[ConstraintEngagementRecord]] = {}
        self._chronic_threshold = max(0.1, float(chronic_threshold))
        self._blockage_threshold = max(1, int(blockage_threshold))
        self._max_signals = max(1, int(max_signals))
        self._default_defer_seconds = float(default_defer_seconds)
        self._registry = registry

    def pressure_state(self, constraint_id: str) -> ConstraintPressureState:
        return self._states.setdefault(constraint_id, ConstraintPressureState(constraint_id))

    def record_signal(
        self,
        constraint_id: str,
        magnitude: float,
        *,
        reason: str,
        affective_context: Mapping[str, object],
        blocked: bool = True,
    ) -> Tuple[ConstraintPressureState, Optional[ConstraintEngagementRecord]]:
        normalized_context = self._normalize_affective_context(affective_context)
        self._require_registered(constraint_id)
        ac.require_affective_context({"affective_context": normalized_context})
        vector = normalized_context.get("vector", {}) if isinstance(normalized_context, Mapping) else {}
        state = self.pressure_state(constraint_id)
        signal = PressureSignal(
            constraint_id=constraint_id,
            magnitude=max(0.0, float(magnitude)),
            reason=reason,
            affective_context=vector,
            blocked=blocked,
        )
        state.record(signal, max_signals=self._max_signals)

        now = time.time()
        engagement: Optional[ConstraintEngagementRecord] = None
        if state.require_review(
            now=now, chronic_threshold=self._chronic_threshold, blockage_threshold=self._blockage_threshold
        ):
            engagement = self._defer_engagement(state, now=now)
            self._register_engagement(engagement)
        return state, engagement

    def mark_ignored(self, constraint_id: str, *, reason: str) -> ConstraintPressureState:
        self._require_registered(constraint_id)
        state = self.pressure_state(constraint_id)
        state.ignored_reason = reason
        return state

    def record_policy_event(
        self,
        event: Mapping[str, object],
        actions: Iterable[Mapping[str, object]],
        affective_overlay: Mapping[str, object],
    ) -> List[ConstraintEngagementRecord]:
        normalized_overlay = self._normalize_affective_context(affective_overlay)
        ac.require_affective_context({"affective_context": normalized_overlay})
        signals = list(self._extract_policy_signals(event, actions))
        engagements: List[ConstraintEngagementRecord] = []
        for signal in signals:
            _, engagement = self.record_signal(
                signal["constraint_id"],
                signal.get("magnitude", 1.0),
                reason=signal.get("reason", "constraint blocked"),
                affective_context=normalized_overlay,
                blocked=signal.get("blocked", True),
            )
            if engagement is not None:
                engagements.append(engagement)
        return engagements

    def reaffirm(
        self,
        constraint_id: str,
        *,
        decision: str,
        justification: str,
        reviewer: Optional[str] = None,
        defer_seconds: Optional[float] = None,
        lineage_from: Optional[str] = None,
    ) -> ConstraintEngagementRecord:
        if decision not in {"reaffirm", "modify", "sunset", "defer"}:
            raise ValueError("decision must be reaffirm|modify|sunset|defer")
        if decision == "defer" and defer_seconds is None:
            raise ValueError("defer requires an expiry")

        state = self.pressure_state(constraint_id)
        now = time.time()
        defer_until = None
        if decision == "defer":
            defer_until = now + float(defer_seconds)
        record = self._create_engagement_record(
            constraint_id=constraint_id,
            decision=decision,
            justification=justification,
            reviewer=reviewer,
            signals=tuple(state.signals),
            defer_until=defer_until,
            lineage_from=lineage_from or state.pending_engagement_id,
        )
        self._engagements.setdefault(constraint_id, []).append(record)
        self._register_engagement(record)
        if decision == "defer":
            state.pending_engagement_id = record.engagement_id
            state.defer_until = defer_until
        else:
            state.reset()
        state.last_reviewed_at = now
        return record

    def decay_pressure(self, constraint_id: str) -> None:
        state = self.pressure_state(constraint_id)
        if not state.last_reviewed_at:
            raise PressureDecayError("pressure cannot decay without review")
        state.reset()

    def _extract_policy_signals(
        self, event: Mapping[str, object], actions: Iterable[Mapping[str, object]]
    ) -> Iterable[MutableMapping[str, object]]:
        pressure_signals = event.get("pressure_signals")
        if isinstance(pressure_signals, list):
            for entry in pressure_signals:
                if isinstance(entry, Mapping) and entry.get("constraint_id"):
                    yield dict(entry)

        blocked = event.get("blocked_constraint")
        if isinstance(blocked, str):
            yield {"constraint_id": blocked, "blocked": True, "reason": "blocked", "magnitude": 1.0}

        blocked_constraints = event.get("blocked_constraints")
        if isinstance(blocked_constraints, list):
            for constraint in blocked_constraints:
                if isinstance(constraint, str):
                    yield {"constraint_id": constraint, "blocked": True, "reason": "blocked", "magnitude": 1.0}

        if not any(actions) and event.get("constraint_id"):
            yield {
                "constraint_id": str(event.get("constraint_id")),
                "blocked": True,
                "reason": "policy denied actions",
                "magnitude": 1.0,
            }

    def _defer_engagement(
        self, state: ConstraintPressureState, *, now: float
    ) -> ConstraintEngagementRecord:
        record = self._create_engagement_record(
            constraint_id=state.constraint_id,
            decision="defer",
            justification="pressure threshold reached; review required",
            reviewer=None,
            signals=tuple(state.signals),
            defer_until=now + self._default_defer_seconds,
            lineage_from=state.pending_engagement_id,
        )
        self._engagements.setdefault(state.constraint_id, []).append(record)
        self._register_engagement(record)
        state.pending_engagement_id = record.engagement_id
        state.defer_until = record.defer_until
        return record

    def _create_engagement_record(
        self,
        *,
        constraint_id: str,
        decision: str,
        justification: str,
        reviewer: Optional[str],
        signals: Tuple[PressureSignal, ...],
        defer_until: Optional[float],
        lineage_from: Optional[str],
    ) -> ConstraintEngagementRecord:
        summary = self._summarize_affective_context(signals)
        engagement_id = uuid.uuid4().hex
        return ConstraintEngagementRecord(
            engagement_id=engagement_id,
            constraint_id=constraint_id,
            decision=decision,
            justification=justification,
            created_at=time.time(),
            signals=signals,
            affective_context_summary=summary,
            reviewer=reviewer,
            defer_until=defer_until,
            lineage_from=lineage_from,
        )

    def _summarize_affective_context(self, signals: Tuple[PressureSignal, ...]) -> Mapping[str, float]:
        if not signals:
            return {}
        accumulator: Dict[str, float] = {}
        for signal in signals:
            for key, value in signal.affective_context.items():
                accumulator[key] = accumulator.get(key, 0.0) + float(value)
        return {key: round(value / len(signals), 3) for key, value in accumulator.items()}

    @property
    def engagements(self) -> Tuple[ConstraintEngagementRecord, ...]:
        return tuple(record for records in self._engagements.values() for record in records)

    def _require_registered(self, constraint_id: str) -> None:
        if self._registry is None:
            return
        self._registry.require(constraint_id)

    def _register_engagement(self, engagement: ConstraintEngagementRecord) -> None:
        if self._registry is None:
            return
        self._registry.record_engagement(engagement)

    def _normalize_affective_context(self, context: Mapping[str, object]) -> Mapping[str, object]:
        if isinstance(context, Mapping) and "version" in context and "vector" in context:
            return context
        overlay = context if isinstance(context, Mapping) else {}
        return ac.capture_affective_context("constraint-pressure", overlay=overlay)

