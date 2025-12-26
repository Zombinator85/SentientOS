"""Continuous Observation & Reflective Context (COR) subsystem.

COR is strictly non-authoritative and non-executing. It never triggers actions,
tasks, or repairs. Observation is passive; reflection is internal; proposals are
logged for operator review only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Deque, Dict, Iterable, List, Optional, Protocol

import hashlib
import json
import os
import time

from logging_config import get_log_path
from sentientos.governance.routine_delegation import RoutineProposal, RoutineSpec, make_routine_proposal


LOG_PATH = get_log_path("cor_events.jsonl", "COR_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


_SOURCE_TYPES = {"screen", "window", "audio", "camera", "os_event"}
_CONTENT_TYPES = {"raw", "symbolic"}


@dataclass(frozen=True)
class ObservationEvent:
    source: str
    timestamp: str
    content_type: str
    authority: str
    payload: Dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        source: str,
        content_type: str,
        payload: Optional[Dict[str, object]] = None,
        timestamp: Optional[str] = None,
    ) -> "ObservationEvent":
        if source not in _SOURCE_TYPES:
            raise ValueError(f"Unsupported source: {source}")
        if content_type not in _CONTENT_TYPES:
            raise ValueError(f"Unsupported content_type: {content_type}")
        return cls(
            source=source,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            content_type=content_type,
            authority="none",
            payload=payload or {},
        )


@dataclass(frozen=True)
class Hypothesis:
    hypothesis: str
    confidence: float
    actionability: str = "proposal_only"
    evidence: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ProposalArtifact:
    summary: str
    confidence: float
    hypothesis: str
    created_at: str
    actionability: str = "proposal_only"
    status: str = "pending_review"
    evidence: Dict[str, object] = field(default_factory=dict)


@dataclass
class ContextModel:
    current_activity: Optional[str] = None
    focus_level: Optional[float] = None
    environmental_state: Dict[str, object] = field(default_factory=dict)
    recent_transitions: Deque[Dict[str, object]] = field(default_factory=lambda: deque(maxlen=50))
    friction_signals: Deque[Dict[str, object]] = field(default_factory=lambda: deque(maxlen=50))

    def to_dict(self) -> Dict[str, object]:
        return {
            "current_activity": self.current_activity,
            "focus_level": self.focus_level,
            "environmental_state": dict(self.environmental_state),
            "recent_transitions": list(self.recent_transitions),
            "friction_signals": list(self.friction_signals),
        }


class ObservationAdapter(Protocol):
    def read(self) -> Optional[ObservationEvent]:
        """Return the next observation event, or None if no data is available."""


@dataclass
class CORConfig:
    enabled_sources: List[str] = field(default_factory=list)
    raw_retention_seconds: int = 0
    max_raw_events: int = 50
    proposal_confidence_threshold: float = 0.85
    hypothesis_decay_window_seconds: int = 900
    hypothesis_expiry_seconds: int = 1800
    hypothesis_stale_confidence_threshold: float = 0.5
    proposal_suppression_seconds: int = 1800

    @classmethod
    def from_env(cls) -> "CORConfig":
        enabled_sources = [
            s.strip()
            for s in os.getenv("COR_ENABLED_SOURCES", "").split(",")
            if s.strip()
        ]
        raw_retention_seconds = int(os.getenv("COR_RAW_RETENTION_SECONDS", "0"), 10)
        max_raw_events = int(os.getenv("COR_MAX_RAW_EVENTS", "50"), 10)
        proposal_confidence_threshold = float(
            os.getenv("COR_PROPOSAL_CONFIDENCE_THRESHOLD", "0.85")
        )
        hypothesis_decay_window_seconds = int(
            os.getenv("COR_HYPOTHESIS_DECAY_WINDOW_SECONDS", "900"),
            10,
        )
        hypothesis_expiry_seconds = int(
            os.getenv("COR_HYPOTHESIS_EXPIRY_SECONDS", "1800"),
            10,
        )
        hypothesis_stale_confidence_threshold = float(
            os.getenv("COR_HYPOTHESIS_STALE_CONFIDENCE", "0.5")
        )
        proposal_suppression_seconds = int(
            os.getenv("COR_PROPOSAL_SUPPRESSION_SECONDS", "1800"),
            10,
        )
        return cls(
            enabled_sources=enabled_sources,
            raw_retention_seconds=raw_retention_seconds,
            max_raw_events=max_raw_events,
            proposal_confidence_threshold=proposal_confidence_threshold,
            hypothesis_decay_window_seconds=hypothesis_decay_window_seconds,
            hypothesis_expiry_seconds=hypothesis_expiry_seconds,
            hypothesis_stale_confidence_threshold=hypothesis_stale_confidence_threshold,
            proposal_suppression_seconds=proposal_suppression_seconds,
        )


@dataclass
class HypothesisRecord:
    hypothesis: str
    confidence: float
    last_seen: float
    evidence: Dict[str, object]
    peak_confidence: float


@dataclass
class ProposalSuppression:
    suppressed_until: float
    last_evidence_hash: str
    peak_confidence: float
    rejected_at: float


class CORSubsystem:
    """Always-on, passive observation and reflection subsystem."""

    def __init__(
        self,
        config: Optional[CORConfig] = None,
        adapters: Optional[Iterable[ObservationAdapter]] = None,
        now_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        self.config = config or CORConfig.from_env()
        self.context = ContextModel()
        self._raw_events: Deque[ObservationEvent] = deque(maxlen=self.config.max_raw_events)
        self._hypothesis_history: Deque[Hypothesis] = deque(maxlen=200)
        self._hypothesis_records: Dict[str, HypothesisRecord] = {}
        self._proposal_suppression: Dict[str, ProposalSuppression] = {}
        self._archived_proposals: Deque[ProposalArtifact] = deque(maxlen=200)
        self._adapters = list(adapters or [])
        self._now = now_fn or time.time
        self._global_silence_until = 0.0

    def register_adapter(self, adapter: ObservationAdapter) -> None:
        self._adapters.append(adapter)

    def ingest_observation(self, event: ObservationEvent) -> None:
        if self.config.enabled_sources and event.source not in self.config.enabled_sources:
            return
        if event.content_type == "raw":
            self._retain_raw_event(event)
        self._update_context(event)
        self._log_event("observation", event.__dict__)

    def ingest_hypothesis(self, hypothesis: Hypothesis) -> Optional[ProposalArtifact]:
        now = self._now()
        self._prune_hypotheses(now)
        self._prune_suppression(now)
        self._hypothesis_history.append(hypothesis)
        self._record_hypothesis(hypothesis, now)
        self._log_event("reflection", hypothesis.__dict__)
        decayed_confidence = self._decayed_confidence(hypothesis.confidence, now, hypothesis.hypothesis)
        if decayed_confidence < self.config.proposal_confidence_threshold:
            return None
        if self._is_suppressed(hypothesis.hypothesis, hypothesis.evidence, decayed_confidence, now):
            return None
        proposal = ProposalArtifact(
            summary=hypothesis.hypothesis,
            confidence=decayed_confidence,
            hypothesis=hypothesis.hypothesis,
            created_at=datetime.now(timezone.utc).isoformat(),
            evidence=dict(hypothesis.evidence),
        )
        self._log_event("proposal", proposal.__dict__)
        return proposal

    def run_observation_cycle(self) -> None:
        for adapter in self._adapters:
            event = adapter.read()
            if event is None:
                continue
            self.ingest_observation(event)

    def current_context_snapshot(self) -> Dict[str, object]:
        snapshot = self.context.to_dict()
        self._log_event("reflection", {"context_snapshot": snapshot})
        return snapshot

    def suppress_proposal(self, hypothesis: str) -> None:
        self.record_proposal_rejection(hypothesis=hypothesis, evidence={}, confidence=0.0, reason="operator_suppress")

    def record_proposal_rejection(
        self,
        *,
        hypothesis: str,
        evidence: Dict[str, object],
        confidence: float,
        reason: str,
    ) -> None:
        now = self._now()
        evidence_hash = self._evidence_hash(evidence)
        suppression = self._proposal_suppression.get(hypothesis)
        peak_confidence = max(confidence, suppression.peak_confidence) if suppression else confidence
        self._proposal_suppression[hypothesis] = ProposalSuppression(
            suppressed_until=now + self.config.proposal_suppression_seconds,
            last_evidence_hash=evidence_hash,
            peak_confidence=peak_confidence,
            rejected_at=now,
        )
        archived = ProposalArtifact(
            summary=hypothesis,
            confidence=confidence,
            hypothesis=hypothesis,
            created_at=datetime.now(timezone.utc).isoformat(),
            actionability="proposal_only",
            status="rejected",
            evidence=dict(evidence),
        )
        self._archived_proposals.append(archived)
        self._log_event(
            "proposal_rejected",
            {
                "hypothesis": hypothesis,
                "confidence": confidence,
                "reason": reason,
                "suppressed_until": self._proposal_suppression[hypothesis].suppressed_until,
            },
        )

    def reset_context(self, *, reason: str) -> None:
        self.context = ContextModel()
        self._hypothesis_history.clear()
        self._hypothesis_records.clear()
        self._proposal_suppression.clear()
        self._raw_events.clear()
        self._log_event("context_reset", {"reason": reason})

    def handle_context_boundary(self, boundary: str) -> None:
        if boundary not in {"screen_lock", "screen_unlock", "user_switch", "long_idle", "system_restart"}:
            return
        self.reset_context(reason=boundary)

    def silence_proposals(self, *, duration_seconds: int) -> None:
        self._global_silence_until = max(self._global_silence_until, self._now() + duration_seconds)
        self._log_event("proposal_silence", {"until": self._global_silence_until})

    def forget_hypothesis(self, hypothesis: str, *, reason: str = "operator_forget") -> bool:
        record = self._hypothesis_records.pop(hypothesis, None)
        if record is None:
            return False
        self._log_event(
            "hypothesis_forget",
            {"hypothesis": hypothesis, "reason": reason, "last_seen": record.last_seen},
        )
        return True

    def forget_all_context(self, *, reason: str = "operator_forget_all") -> None:
        self.reset_context(reason=reason)

    def diagnostics_snapshot(self) -> Dict[str, object]:
        now = self._now()
        self._prune_hypotheses(now)
        self._prune_suppression(now)
        beliefs: List[Dict[str, object]] = []
        for record in self._hypothesis_records.values():
            age = now - record.last_seen
            decayed = self._decay_confidence(record.confidence, age)
            beliefs.append(
                {
                    "hypothesis": record.hypothesis,
                    "confidence": record.confidence,
                    "decayed_confidence": decayed,
                    "last_seen": record.last_seen,
                    "stale": decayed < self.config.hypothesis_stale_confidence_threshold,
                    "expires_at": record.last_seen + self.config.hypothesis_expiry_seconds,
                }
            )
        suppressions = {
            key: {
                "suppressed_until": suppression.suppressed_until,
                "peak_confidence": suppression.peak_confidence,
                "rejected_at": suppression.rejected_at,
            }
            for key, suppression in self._proposal_suppression.items()
        }
        snapshot = {
            "beliefs": sorted(beliefs, key=lambda item: item["hypothesis"]),
            "suppressed": suppressions,
            "global_silence_until": self._global_silence_until,
        }
        self._log_event("diagnostics", snapshot)
        return snapshot

    def propose_routine(self, summary: str, spec: RoutineSpec, *, proposed_by: str = "cor") -> RoutineProposal:
        proposal = make_routine_proposal(summary=summary, spec=spec, proposed_by=proposed_by)
        self._log_event("routine_proposal", proposal.to_dict())
        return proposal

    def _retain_raw_event(self, event: ObservationEvent) -> None:
        if self.config.raw_retention_seconds <= 0:
            return
        self._raw_events.append(event)
        cutoff = time.time() - self.config.raw_retention_seconds
        while self._raw_events and self._event_time(self._raw_events[0]) < cutoff:
            self._raw_events.popleft()

    def _event_time(self, event: ObservationEvent) -> float:
        try:
            return datetime.fromisoformat(event.timestamp).timestamp()
        except ValueError:
            return time.time()

    def _update_context(self, event: ObservationEvent) -> None:
        if event.content_type != "symbolic":
            return
        activity = event.payload.get("activity")
        if isinstance(activity, str) and activity != self.context.current_activity:
            transition = {
                "from": self.context.current_activity,
                "to": activity,
                "timestamp": event.timestamp,
            }
            self.context.recent_transitions.append(transition)
            self.context.current_activity = activity
        focus = event.payload.get("focus_level")
        if isinstance(focus, (int, float)):
            self.context.focus_level = max(0.0, min(1.0, float(focus)))
        environment = event.payload.get("environment")
        if isinstance(environment, dict):
            self.context.environmental_state.update(environment)
        friction = event.payload.get("friction_signal")
        if isinstance(friction, dict):
            self.context.friction_signals.append(friction)

    def _record_hypothesis(self, hypothesis: Hypothesis, now: float) -> None:
        existing = self._hypothesis_records.get(hypothesis.hypothesis)
        peak_confidence = max(hypothesis.confidence, existing.peak_confidence) if existing else hypothesis.confidence
        self._hypothesis_records[hypothesis.hypothesis] = HypothesisRecord(
            hypothesis=hypothesis.hypothesis,
            confidence=hypothesis.confidence,
            last_seen=now,
            evidence=dict(hypothesis.evidence),
            peak_confidence=peak_confidence,
        )

    def _decayed_confidence(self, confidence: float, now: float, hypothesis: str) -> float:
        record = self._hypothesis_records.get(hypothesis)
        if not record:
            return confidence
        age = now - record.last_seen
        return self._decay_confidence(record.confidence, age)

    def _decay_confidence(self, confidence: float, age_seconds: float) -> float:
        if age_seconds <= 0 or self.config.hypothesis_decay_window_seconds <= 0:
            return confidence
        decay_window = self.config.hypothesis_decay_window_seconds
        factor = max(0.0, 1.0 - (age_seconds / decay_window))
        return max(0.0, min(1.0, confidence * factor))

    def _is_suppressed(
        self,
        hypothesis: str,
        evidence: Dict[str, object],
        confidence: float,
        now: float,
    ) -> bool:
        if now < self._global_silence_until:
            return True
        suppression = self._proposal_suppression.get(hypothesis)
        if suppression is None:
            return False
        if now >= suppression.suppressed_until:
            return False
        evidence_hash = self._evidence_hash(evidence)
        evidence_changed = evidence_hash != suppression.last_evidence_hash
        confidence_surpassed = confidence > suppression.peak_confidence
        return not (evidence_changed or confidence_surpassed)

    def _prune_hypotheses(self, now: float) -> None:
        if self.config.hypothesis_expiry_seconds <= 0:
            return
        expired = [
            key
            for key, record in self._hypothesis_records.items()
            if now - record.last_seen >= self.config.hypothesis_expiry_seconds
        ]
        for key in expired:
            record = self._hypothesis_records.pop(key)
            self._log_event(
                "hypothesis_expired",
                {"hypothesis": record.hypothesis, "reason": "expired_due_to_inactivity"},
            )

    def _prune_suppression(self, now: float) -> None:
        expired = [
            key
            for key, suppression in self._proposal_suppression.items()
            if now >= suppression.suppressed_until
        ]
        for key in expired:
            self._proposal_suppression.pop(key, None)

    def _evidence_hash(self, evidence: Dict[str, object]) -> str:
        payload = json.dumps(evidence, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _log_event(self, kind: str, payload: Dict[str, object]) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "non_authoritative": True,
            "non_executing": True,
            "payload": payload,
        }
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
