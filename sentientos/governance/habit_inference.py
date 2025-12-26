from __future__ import annotations

import hashlib
import json
import os
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Mapping, MutableMapping, Sequence

from logging_config import get_log_path
from log_utils import append_json
from sentientos.governance.routine_delegation import (
    RoutineApproval,
    RoutineDefinition,
    RoutineRegistry,
    RoutineSpec,
)


DEFAULT_LOG_PATH = get_log_path("habit_inference.jsonl", "HABIT_INFERENCE_LOG")


@dataclass(frozen=True)
class HabitPolicy:
    allows_task_spawn: bool = False
    allows_epr: bool = False
    allows_privilege_escalation: bool = False
    allows_governance_change: bool = False
    allows_config_change: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "allows_task_spawn": self.allows_task_spawn,
            "allows_epr": self.allows_epr,
            "allows_privilege_escalation": self.allows_privilege_escalation,
            "allows_governance_change": self.allows_governance_change,
            "allows_config_change": self.allows_config_change,
        }

    def is_authority_bounded(self) -> bool:
        return not any(self.to_dict().values())


@dataclass(frozen=True)
class HabitObservation:
    action_id: str
    action_description: str
    trigger_id: str
    trigger_description: str
    scope: tuple[str, ...]
    reversibility: str
    authority_impact: str
    timestamp: str
    context: Mapping[str, object] = field(default_factory=dict)
    outcome: Mapping[str, object] = field(default_factory=dict)
    policy: HabitPolicy = field(default_factory=HabitPolicy)


@dataclass(frozen=True)
class HabitEvidence:
    occurrences: int
    first_seen: str
    last_seen: str
    mean_interval_seconds: float
    stddev_interval_seconds: float
    context_signature: str
    outcome_signature: str
    conflicting_context: bool


@dataclass(frozen=True)
class HabitProposal:
    habit_id: str
    summary: str
    confidence: float
    prompt: str
    evidence: HabitEvidence
    options: tuple[str, str]


@dataclass(frozen=True)
class HabitReviewAlert:
    habit_id: str
    routine_id: str
    reason: str
    observed_at: str


@dataclass
class HabitConfig:
    min_occurrences: int = 3
    max_interval_stddev_seconds: float = 300.0
    max_mean_interval_seconds: float = 7200.0
    proposal_confidence_threshold: float = 0.9

    @classmethod
    def from_env(cls) -> "HabitConfig":
        return cls(
            min_occurrences=int(os.getenv("HABIT_MIN_OCCURRENCES", "3"), 10),
            max_interval_stddev_seconds=float(
                os.getenv("HABIT_MAX_INTERVAL_STDDEV_SECONDS", "300")
            ),
            max_mean_interval_seconds=float(
                os.getenv("HABIT_MAX_MEAN_INTERVAL_SECONDS", "7200")
            ),
            proposal_confidence_threshold=float(
                os.getenv("HABIT_PROPOSAL_CONFIDENCE_THRESHOLD", "0.9")
            ),
        )


@dataclass
class HabitRecord:
    habit_id: str
    action_id: str
    action_description: str
    trigger_id: str
    trigger_description: str
    scope: tuple[str, ...]
    reversibility: str
    authority_impact: str
    policy: HabitPolicy
    context_signature: str
    outcome_signature: str
    timestamps: list[float] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""


class HabitInferenceEngine:
    def __init__(self, *, config: HabitConfig | None = None) -> None:
        self.config = config or HabitConfig.from_env()
        self._habits: MutableMapping[str, HabitRecord] = {}
        self._proposal_status: MutableMapping[str, str] = {}
        self._declined_habits: MutableMapping[str, str] = {}
        self._approved_habits: MutableMapping[str, RoutineDefinition] = {}
        self._context_actions: MutableMapping[str, set[str]] = {}
        self._context_outcomes: MutableMapping[str, set[str]] = {}
        self._review_alerts: list[HabitReviewAlert] = []

    def record_observation(self, observation: HabitObservation) -> HabitProposal | None:
        context_signature = _signature_for_payload(observation.context)
        outcome_signature = _signature_for_payload(observation.outcome)
        habit_id = _habit_id_for(observation, context_signature, outcome_signature)
        observed_at = _to_epoch(observation.timestamp)

        self._register_context_activity(context_signature, observation.action_id, outcome_signature)
        record = self._habits.get(habit_id)
        if record is None:
            record = HabitRecord(
                habit_id=habit_id,
                action_id=observation.action_id,
                action_description=observation.action_description,
                trigger_id=observation.trigger_id,
                trigger_description=observation.trigger_description,
                scope=observation.scope,
                reversibility=observation.reversibility,
                authority_impact=observation.authority_impact,
                policy=observation.policy,
                context_signature=context_signature,
                outcome_signature=outcome_signature,
                timestamps=[],
                first_seen=observation.timestamp,
                last_seen=observation.timestamp,
            )
            self._habits[habit_id] = record
        record.timestamps.append(observed_at)
        record.last_seen = observation.timestamp
        if not record.first_seen:
            record.first_seen = observation.timestamp

        self._log_event(
            "habit_observation",
            {
                "habit_id": habit_id,
                "action_id": observation.action_id,
                "trigger_id": observation.trigger_id,
                "timestamp": observation.timestamp,
                "context_signature": context_signature,
                "outcome_signature": outcome_signature,
            },
        )

        if habit_id in self._approved_habits:
            self._evaluate_invalidation(habit_id, context_signature, outcome_signature)
            return None

        if habit_id in self._proposal_status:
            return None
        if habit_id in self._declined_habits:
            return None

        evidence = self._build_evidence(record)
        confidence = self._compute_confidence(record, evidence)
        qualifies = confidence >= self.config.proposal_confidence_threshold
        self._log_event(
            "habit_inference",
            {
                "habit_id": habit_id,
                "confidence": confidence,
                "qualifies": qualifies,
                "evidence": _evidence_payload(evidence),
            },
        )
        if not qualifies:
            return None

        summary = _habit_summary(record)
        prompt = (
            f"Observed habit: {summary}\n"
            f"Evidence: {evidence.occurrences} occurrences, mean interval {evidence.mean_interval_seconds:.1f}s, "
            f"stddev {evidence.stddev_interval_seconds:.1f}s, context {evidence.context_signature}.\n"
            "Approval will make this automatic. Decline will suppress future prompts."
        )
        proposal = HabitProposal(
            habit_id=habit_id,
            summary=summary,
            confidence=confidence,
            prompt=prompt,
            evidence=evidence,
            options=("Approve & Automate", "Decline (Do Not Ask Again)"),
        )
        self._proposal_status[habit_id] = "proposed"
        self._log_event(
            "habit_proposal",
            {
                "habit_id": habit_id,
                "summary": summary,
                "confidence": confidence,
                "prompt": prompt,
                "evidence": _evidence_payload(evidence),
                "options": proposal.options,
            },
        )
        return proposal

    def decline_habit(self, habit_id: str, *, declined_by: str, reason: str) -> None:
        if habit_id in self._declined_habits:
            return
        self._proposal_status.pop(habit_id, None)
        self._declined_habits[habit_id] = reason
        self._log_event(
            "habit_declined",
            {
                "habit_id": habit_id,
                "declined_by": declined_by,
                "reason": reason,
            },
        )

    def approve_habit(
        self,
        habit_id: str,
        *,
        approved_by: str,
        approval_summary: str,
        registry: RoutineRegistry,
        approved_at: str | None = None,
    ) -> RoutineDefinition:
        record = self._habits.get(habit_id)
        if record is None:
            raise ValueError(f"Unknown habit: {habit_id}")
        approval = RoutineApproval(
            approval_id=f"approval-{habit_id}",
            approved_by=approved_by,
            approved_at=approved_at or _now(),
            summary=approval_summary,
            trigger_summary=record.trigger_description,
            scope_summary=record.scope,
            rationale="habit_inference_approval",
        )
        spec = RoutineSpec(
            routine_id=f"routine-{habit_id}",
            trigger_id=record.trigger_id,
            trigger_description=record.trigger_description,
            action_id=record.action_id,
            action_description=record.action_description,
            scope=record.scope,
            reversibility=record.reversibility,
            authority_impact=record.authority_impact,
            expiration=None,
            allows_task_spawn=record.policy.allows_task_spawn,
            allows_epr=record.policy.allows_epr,
            allows_privilege_escalation=record.policy.allows_privilege_escalation,
            allows_governance_change=record.policy.allows_governance_change,
            allows_config_change=record.policy.allows_config_change,
        )
        routine = registry.approve_routine(spec, approval)
        self._proposal_status.pop(habit_id, None)
        self._approved_habits[habit_id] = routine
        self._log_event(
            "habit_approved",
            {
                "habit_id": habit_id,
                "routine_id": routine.routine_id,
                "approved_by": approved_by,
                "approved_at": approval.approved_at,
            },
        )
        return routine

    def drain_review_alerts(self) -> tuple[HabitReviewAlert, ...]:
        alerts = tuple(self._review_alerts)
        self._review_alerts.clear()
        return alerts

    def list_habits(self) -> tuple[HabitRecord, ...]:
        return tuple(self._habits.values())

    def list_approved(self) -> tuple[RoutineDefinition, ...]:
        return tuple(self._approved_habits.values())

    def _build_evidence(self, record: HabitRecord) -> HabitEvidence:
        occurrences = len(record.timestamps)
        intervals = _intervals(record.timestamps)
        mean_interval = statistics.fmean(intervals) if intervals else 0.0
        stddev_interval = statistics.pstdev(intervals) if len(intervals) > 1 else 0.0
        context_conflict = self._has_context_conflict(record.context_signature)
        return HabitEvidence(
            occurrences=occurrences,
            first_seen=record.first_seen,
            last_seen=record.last_seen,
            mean_interval_seconds=mean_interval,
            stddev_interval_seconds=stddev_interval,
            context_signature=record.context_signature,
            outcome_signature=record.outcome_signature,
            conflicting_context=context_conflict,
        )

    def _compute_confidence(self, record: HabitRecord, evidence: HabitEvidence) -> float:
        if evidence.occurrences < self.config.min_occurrences:
            return 0.0
        if record.reversibility not in {"guaranteed", "bounded"}:
            return 0.0
        if record.authority_impact not in {"none", "local"}:
            return 0.0
        if not record.policy.is_authority_bounded():
            return 0.0
        if evidence.conflicting_context:
            return 0.0
        if evidence.mean_interval_seconds > self.config.max_mean_interval_seconds:
            return 0.0
        if evidence.stddev_interval_seconds > self.config.max_interval_stddev_seconds:
            return 0.0

        repetition_score = min(1.0, evidence.occurrences / float(self.config.min_occurrences))
        temporal_score = 1.0 - min(
            1.0,
            evidence.stddev_interval_seconds / max(self.config.max_interval_stddev_seconds, 1.0),
        )
        certainty = max(0.0, min(1.0, repetition_score * temporal_score))
        return certainty

    def _register_context_activity(
        self,
        context_signature: str,
        action_id: str,
        outcome_signature: str,
    ) -> None:
        self._context_actions.setdefault(context_signature, set()).add(action_id)
        self._context_outcomes.setdefault(context_signature, set()).add(outcome_signature)

    def _has_context_conflict(self, context_signature: str) -> bool:
        actions = self._context_actions.get(context_signature, set())
        outcomes = self._context_outcomes.get(context_signature, set())
        return len(actions) > 1 or len(outcomes) > 1

    def _evaluate_invalidation(
        self,
        habit_id: str,
        context_signature: str,
        outcome_signature: str,
    ) -> None:
        if not self._has_context_conflict(context_signature):
            return
        routine = self._approved_habits.get(habit_id)
        if routine is None:
            return
        alert = HabitReviewAlert(
            habit_id=habit_id,
            routine_id=routine.routine_id,
            reason="context_or_outcome_diverged",
            observed_at=_now(),
        )
        self._approved_habits.pop(habit_id, None)
        self._review_alerts.append(alert)
        self._log_event(
            "habit_paused",
            {
                "habit_id": habit_id,
                "routine_id": routine.routine_id,
                "reason": "context_or_outcome_diverged",
                "observed_at": _now(),
            },
        )

    def _log_event(self, kind: str, payload: Mapping[str, object]) -> None:
        append_json(
            DEFAULT_LOG_PATH,
            {
                "timestamp": _now(),
                "event": kind,
                "payload": dict(payload),
            },
        )


def _intervals(timestamps: Sequence[float]) -> list[float]:
    if len(timestamps) < 2:
        return []
    sorted_times = sorted(timestamps)
    return [b - a for a, b in zip(sorted_times, sorted_times[1:])]


def _habit_id_for(
    observation: HabitObservation,
    context_signature: str,
    outcome_signature: str,
) -> str:
    payload = {
        "action_id": observation.action_id,
        "trigger_id": observation.trigger_id,
        "context_signature": context_signature,
        "outcome_signature": outcome_signature,
        "scope": list(observation.scope),
        "reversibility": observation.reversibility,
        "authority_impact": observation.authority_impact,
        "policy": observation.policy.to_dict(),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"habit-{digest[:16]}"


def _signature_for_payload(payload: Mapping[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]


def _habit_summary(record: HabitRecord) -> str:
    return f"{record.action_description} when {record.trigger_description}"


def _evidence_payload(evidence: HabitEvidence) -> dict[str, object]:
    return {
        "occurrences": evidence.occurrences,
        "first_seen": evidence.first_seen,
        "last_seen": evidence.last_seen,
        "mean_interval_seconds": evidence.mean_interval_seconds,
        "stddev_interval_seconds": evidence.stddev_interval_seconds,
        "context_signature": evidence.context_signature,
        "outcome_signature": evidence.outcome_signature,
        "conflicting_context": evidence.conflicting_context,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_epoch(timestamp: str) -> float:
    try:
        return datetime.fromisoformat(timestamp).timestamp()
    except ValueError:
        return datetime.now(timezone.utc).timestamp()


__all__ = [
    "HabitConfig",
    "HabitEvidence",
    "HabitInferenceEngine",
    "HabitObservation",
    "HabitPolicy",
    "HabitProposal",
    "HabitReviewAlert",
]
