"""Continuous Observation & Reflective Context (COR) subsystem.

COR is strictly non-authoritative and non-executing. It never triggers actions,
tasks, or repairs. Observation is passive; reflection is internal; proposals are
logged for operator review only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, Iterable, List, Optional, Protocol

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


@dataclass(frozen=True)
class ProposalArtifact:
    summary: str
    confidence: float
    hypothesis: str
    created_at: str
    actionability: str = "proposal_only"
    status: str = "pending_review"


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
        return cls(
            enabled_sources=enabled_sources,
            raw_retention_seconds=raw_retention_seconds,
            max_raw_events=max_raw_events,
            proposal_confidence_threshold=proposal_confidence_threshold,
        )


class CORSubsystem:
    """Always-on, passive observation and reflection subsystem."""

    def __init__(
        self,
        config: Optional[CORConfig] = None,
        adapters: Optional[Iterable[ObservationAdapter]] = None,
    ) -> None:
        self.config = config or CORConfig.from_env()
        self.context = ContextModel()
        self._raw_events: Deque[ObservationEvent] = deque(maxlen=self.config.max_raw_events)
        self._hypothesis_history: Deque[Hypothesis] = deque(maxlen=200)
        self._proposal_suppression: Dict[str, float] = {}
        self._adapters = list(adapters or [])

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
        self._hypothesis_history.append(hypothesis)
        self._log_event("reflection", hypothesis.__dict__)
        if hypothesis.confidence < self.config.proposal_confidence_threshold:
            return None
        if self._is_suppressed(hypothesis.hypothesis):
            return None
        proposal = ProposalArtifact(
            summary=hypothesis.hypothesis,
            confidence=hypothesis.confidence,
            hypothesis=hypothesis.hypothesis,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._proposal_suppression[hypothesis.hypothesis] = time.time()
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
        self._proposal_suppression[hypothesis] = time.time()

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

    def _is_suppressed(self, hypothesis: str) -> bool:
        if hypothesis not in self._proposal_suppression:
            return False
        return True

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
