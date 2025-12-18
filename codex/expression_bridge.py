from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Callable, List, Mapping, Optional

from .intent_drafts import IntentDraft, ReadinessBand


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class PublishWindowClosedError(RuntimeError):
    """Raised when attempting to emit without an open, active window."""


class FeedbackIngressForbidden(RuntimeError):
    """Raised when any feedback or reaction ingestion is attempted."""


@dataclass(frozen=True)
class ExpressionArtifact:
    """Immutable expression artifact derived from a mature intent draft."""

    content: str
    epistemic_basis: str
    confidence_band: str
    contradiction_status: bool
    timestamp: datetime
    day_hash: str
    source_draft_id: str
    non_executable: bool = field(default=True, init=False)
    artifact_hash: str = field(init=False)

    def __post_init__(self) -> None:
        payload = "|".join(
            [
                self.content,
                self.epistemic_basis,
                self.confidence_band,
                "1" if self.contradiction_status else "0",
                self.timestamp.isoformat(),
                self.day_hash,
                self.source_draft_id,
            ]
        )
        object.__setattr__(self, "non_executable", True)
        object.__setattr__(self, "artifact_hash", hashlib.sha256(payload.encode("utf-8")).hexdigest())


class PublishWindow:
    """Human-gated window that allows a single emission before closing."""

    def __init__(
        self,
        *,
        opened_by: str,
        ttl: timedelta,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not opened_by or not opened_by.strip():
            raise ValueError("Publish window must be opened by a human actor")
        self._opened_by = opened_by.strip()
        self._opened_at = (now or _default_now)()
        self._ttl = ttl
        self._now = now or _default_now
        self._consumed = False

    @property
    def opened_by(self) -> str:
        return self._opened_by

    @property
    def opened_at(self) -> datetime:
        return self._opened_at

    def is_open(self) -> bool:
        if self._consumed:
            return False
        return self._now() <= self._opened_at + self._ttl

    def consume(self) -> None:
        if not self.is_open():
            raise PublishWindowClosedError("Publish window is closed")
        self._consumed = True


class ExpressionBridge:
    """One-way bridge for emitting a single expression with no ingress."""

    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or _default_now
        self._window: Optional[PublishWindow] = None
        self._emission_log: List[Mapping[str, str]] = []
        self._autopsies: List[Mapping[str, object]] = []
        self._state_snapshot = {
            "curiosity": 0.0,
            "synthesis": [],
            "belief": {},
        }

    def open_window(self, *, opened_by: str, ttl: timedelta) -> PublishWindow:
        if self._window and self._window.is_open():
            raise PublishWindowClosedError("A publish window is already active")
        self._window = PublishWindow(opened_by=opened_by, ttl=ttl, now=self._now)
        return self._window

    def crystallize(
        self,
        draft: IntentDraft,
        *,
        content: str,
        epistemic_basis: str,
        confidence_band: str,
    ) -> ExpressionArtifact:
        if draft.readiness != ReadinessBand.MATURE:
            raise PublishWindowClosedError("Only mature intent drafts can crystallize into expression")
        if draft.suppressed or draft.expired:
            raise PublishWindowClosedError("Suppressed or expired drafts cannot emit")
        timestamp = self._now()
        return ExpressionArtifact(
            content=content,
            epistemic_basis=epistemic_basis,
            confidence_band=confidence_band,
            contradiction_status=draft.contradiction,
            timestamp=timestamp,
            day_hash=hashlib.sha256(timestamp.date().isoformat().encode("utf-8")).hexdigest(),
            source_draft_id=draft.draft_id,
        )

    def emit(self, artifact: ExpressionArtifact, *, platform: str) -> Mapping[str, str]:
        window = self._require_open_window()
        status = "success"
        window.consume()
        self._window = None
        log_entry = {
            "platform": platform,
            "artifact_hash": artifact.artifact_hash,
            "status": status,
            "timestamp": self._now().isoformat(),
        }
        self._emission_log.append(log_entry)
        self._autopsies.append(self._autopsy(artifact, emitted=True))
        return log_entry

    def discard(self, artifact: ExpressionArtifact) -> None:
        self._autopsies.append(self._autopsy(artifact, emitted=False))

    def _require_open_window(self) -> PublishWindow:
        if not self._window or not self._window.is_open():
            raise PublishWindowClosedError("No open publish window available")
        return self._window

    def ingestion_forbidden(self, *_: object, **__: object) -> None:
        raise FeedbackIngressForbidden("Feedback, reactions, and metrics are not permitted")

    def autopsies(self) -> List[Mapping[str, object]]:
        return list(self._autopsies)

    def emission_log(self) -> List[Mapping[str, str]]:
        return list(self._emission_log)

    def state_snapshot(self) -> Mapping[str, object]:
        return {
            "curiosity": self._state_snapshot["curiosity"],
            "synthesis": list(self._state_snapshot["synthesis"]),
            "belief": dict(self._state_snapshot["belief"]),
        }

    def _autopsy(self, artifact: ExpressionArtifact, *, emitted: bool) -> Mapping[str, object]:
        return {
            "artifact_hash": artifact.artifact_hash,
            "source_draft_id": artifact.source_draft_id,
            "emitted": emitted,
            "intent_valid": True,
            "state_influence": {
                "curiosity": False,
                "synthesis": False,
                "belief": False,
            },
            "silence_preferred": not emitted,
            "timestamp": self._now().isoformat(),
        }

