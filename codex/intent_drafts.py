from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping
from uuid import uuid4


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class ExpressionIntentBridgeError(RuntimeError):
    """Raised when attempting to externalize an internal-only draft."""


class ReadinessBand(str):
    PREMATURE = "premature"
    UNSTABLE = "unstable"
    MATURE = "mature"
    EXPIRED = "expired"
    SUPPRESSED = "suppressed"


@dataclass
class IntentDraft:
    """An internal-only representation of a potential intent."""

    label: str
    trigger: str
    confidence: float
    volatility: float
    created_at: datetime
    reaffirmed_at: datetime
    draft_id: str = field(default_factory=lambda: uuid4().hex)
    contradiction: bool = False
    dormant: bool = False
    readiness: str = ReadinessBand.PREMATURE
    expired: bool = False
    suppressed: bool = False
    non_executable: bool = True
    annotations: dict[str, Any] = field(default_factory=dict)

    def to_expression_intent(self) -> None:
        """Prevent conversion of drafts into any externalized intent."""

        raise ExpressionIntentBridgeError(
            "IntentDraft instances are sealed for internal reflection only; "
            "bridging to expression requires a dedicated approval system."
        )


class ExpressionThresholdEvaluator:
    """Passively assess whether an internal draft is epistemically stable."""

    def __init__(
        self,
        *,
        persistence_horizon: timedelta | None = None,
        dormancy_half_life: timedelta | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._persistence_horizon = persistence_horizon or timedelta(minutes=5)
        self._dormancy_half_life = dormancy_half_life or timedelta(minutes=2)
        self._now = now or _default_now

    def evaluate(self, draft: IntentDraft) -> str:
        current = self._now()
        if draft.suppressed:
            draft.readiness = ReadinessBand.SUPPRESSED
            draft.annotations["readiness_score"] = 0.0
            draft.annotations["notes"] = "Suppressed draft is treated as terminal silence."
            return draft.readiness
        if draft.expired:
            draft.readiness = ReadinessBand.EXPIRED
            draft.annotations["readiness_score"] = 0.0
            draft.annotations["notes"] = "Expired draft decays into silence."
            return draft.readiness

        age_seconds = max(0.0, (current - draft.created_at).total_seconds())
        reaffirm_seconds = max(0.0, (current - draft.reaffirmed_at).total_seconds())

        stability = max(0.0, min(1.0, 1.0 - draft.volatility))
        persistence = min(1.0, age_seconds / self._persistence_horizon.total_seconds())
        dormancy_penalty = 0.25 * min(1.0, reaffirm_seconds / self._dormancy_half_life.total_seconds())
        contradiction_penalty = 0.35 if draft.contradiction else 0.0

        readiness_score = (
            stability * 0.4
            + persistence * 0.35
            + (0.25 if not draft.dormant else 0.1)
            - dormancy_penalty
            - contradiction_penalty
        )
        readiness_score = max(0.0, min(1.0, readiness_score))

        if readiness_score >= 0.75:
            draft.readiness = ReadinessBand.MATURE
        elif readiness_score >= 0.45:
            draft.readiness = ReadinessBand.UNSTABLE
        else:
            draft.readiness = ReadinessBand.PREMATURE

        draft.annotations.update(
            {
                "readiness_score": round(readiness_score, 4),
                "stability": round(stability, 4),
                "persistence": round(persistence, 4),
                "dormancy_penalty": round(dormancy_penalty, 4),
                "contradiction_penalty": round(contradiction_penalty, 4),
            }
        )
        return draft.readiness


class IntentDraftLedger:
    """Append-only log of internal intent drafts with explicit silence accounting."""

    def __init__(
        self,
        *,
        expire_after: timedelta | None = None,
        decay_after: timedelta | None = None,
        evaluator: ExpressionThresholdEvaluator | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._expire_after = expire_after or timedelta(minutes=10)
        self._decay_after = decay_after or timedelta(minutes=3)
        self._now = now or _default_now
        self._evaluator = evaluator or ExpressionThresholdEvaluator(now=self._now)
        self._drafts: list[IntentDraft] = []
        self._silence_events: Counter[str] = Counter()
        self._expiry_reasons: dict[str, str] = {}

    @property
    def drafts(self) -> list[IntentDraft]:
        return list(self._drafts)

    def append(
        self,
        *,
        label: str,
        trigger: str,
        confidence: float,
        volatility: float,
        contradiction: bool = False,
        dormant: bool = False,
    ) -> IntentDraft:
        draft = IntentDraft(
            label=label,
            trigger=trigger,
            confidence=float(confidence),
            volatility=float(volatility),
            contradiction=contradiction,
            dormant=dormant,
            created_at=self._now(),
            reaffirmed_at=self._now(),
        )
        self._drafts.append(draft)
        self._evaluator.evaluate(draft)
        return draft

    def reaffirm(self, draft_id: str, *, contradiction: bool | None = None, dormant: bool | None = None) -> IntentDraft:
        draft = self._get_draft(draft_id)
        draft.reaffirmed_at = self._now()
        if contradiction is not None:
            draft.contradiction = contradiction
        if dormant is not None:
            draft.dormant = dormant
        self._evaluator.evaluate(draft)
        return draft

    def expire_stale(self) -> list[IntentDraft]:
        current = self._now()
        expired: list[IntentDraft] = []
        for draft in self._drafts:
            if draft.expired or draft.suppressed:
                continue
            time_since_reaffirm = current - draft.reaffirmed_at
            if time_since_reaffirm >= self._expire_after:
                draft.expired = True
                draft.non_executable = True
                draft.annotations["expired_at"] = current.isoformat()
                draft.annotations["lifetime_seconds"] = int((current - draft.created_at).total_seconds())
                self._expiry_reasons[draft.draft_id] = "intent expired"
                self.record_silence("intent expired")
                self._evaluator.evaluate(draft)
                expired.append(draft)
            elif time_since_reaffirm >= self._decay_after:
                draft.dormant = True
                self._evaluator.evaluate(draft)
        if not self._drafts:
            self.record_silence("no intent formed")
        return expired

    def suppress(self, draft_id: str, reason: str = "intent suppressed") -> IntentDraft:
        draft = self._get_draft(draft_id)
        draft.suppressed = True
        draft.non_executable = True
        self._expiry_reasons[draft_id] = reason
        self.record_silence("intent suppressed")
        self._evaluator.evaluate(draft)
        return draft

    def held_intents(self) -> list[IntentDraft]:
        return [draft for draft in self._drafts if not draft.expired and not draft.suppressed]

    def persistence_for(self, draft_id: str) -> float:
        draft = self._get_draft(draft_id)
        return max(0.0, (self._now() - draft.created_at).total_seconds())

    def introspect(self) -> Mapping[str, Any]:
        return {
            "held": [self._summarize(draft) for draft in self.held_intents()],
            "silence": self.silence_metrics(),
            "expired": [self._summarize(draft) for draft in self._drafts if draft.expired],
            "suppressed": [self._summarize(draft) for draft in self._drafts if draft.suppressed],
        }

    def silence_metrics(self) -> Mapping[str, Any]:
        total_events = sum(self._silence_events.values())
        success_rate = 0.0 if total_events == 0 else self._silence_events["no intent formed"] / total_events
        return {
            "events": dict(self._silence_events),
            "silence_success_rate": round(success_rate, 4),
        }

    def record_silence(self, reason: str) -> None:
        normalized = reason.strip().lower()
        if normalized not in {"no intent formed", "intent expired", "intent suppressed"}:
            normalized = "no intent formed"
        self._silence_events[normalized] += 1

    def readiness_report(self) -> list[Mapping[str, Any]]:
        return [
            {
                "draft_id": draft.draft_id,
                "label": draft.label,
                "trigger": draft.trigger,
                "readiness": draft.readiness,
                "non_executable": draft.non_executable,
                "annotations": dict(draft.annotations),
            }
            for draft in self._drafts
        ]

    def _summarize(self, draft: IntentDraft) -> Mapping[str, Any]:
        return {
            "draft_id": draft.draft_id,
            "label": draft.label,
            "readiness": draft.readiness,
            "non_executable": draft.non_executable,
            "created_at": draft.created_at.isoformat(),
            "reaffirmed_at": draft.reaffirmed_at.isoformat(),
            "expired": draft.expired,
            "suppressed": draft.suppressed,
            "annotations": dict(draft.annotations),
            "expiry_reason": self._expiry_reasons.get(draft.draft_id),
        }

    def _get_draft(self, draft_id: str) -> IntentDraft:
        for draft in self._drafts:
            if draft.draft_id == draft_id:
                return draft
        raise KeyError(f"Unknown intent draft: {draft_id}")
