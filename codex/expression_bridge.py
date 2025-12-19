from __future__ import annotations

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import uuid
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Deque, Dict, List, Mapping, Optional, Set

try:  # pragma: no cover - platform dependent
    import fcntl
except ImportError:  # pragma: no cover - fallback for non-posix systems
    fcntl = None  # type: ignore[assignment]

from .intent_drafts import IntentDraft, ReadinessBand


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class PublishWindowClosedError(RuntimeError):
    """Raised when attempting to emit without an open, active window."""


class FeedbackIngressForbidden(RuntimeError):
    """Raised when any feedback or reaction ingestion is attempted."""


class ExpressionReplayError(RuntimeError):
    """Raised when replay or duplication of an expression is attempted."""


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
        self._window_id = uuid.uuid4().hex

    @property
    def opened_by(self) -> str:
        return self._opened_by

    @property
    def opened_at(self) -> datetime:
        return self._opened_at

    @property
    def window_id(self) -> str:
        return self._window_id

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
        self._autopsies: Deque[Mapping[str, object]] = deque(maxlen=32)
        self._emitted_hashes: Set[str] = set()
        self._emission_counter = 0
        self._lock = threading.Lock()
        self._lock_path = Path(tempfile.gettempdir()) / "expression_bridge.lock"
        self._kill_switch_flag = "EXPRESSION_DISABLED"
        self._restart_token = uuid.uuid4().hex
        self._compressed_autopsies: Dict[str, Mapping[str, object]] = {}
        self._fingerprint_store = Path(tempfile.gettempdir()) / "expression_bridge_fingerprints.log"
        self._state_snapshot = {
            "curiosity": 0.0,
            "synthesis": [],
            "belief": {},
        }

    def open_window(self, *, opened_by: str, ttl: timedelta) -> PublishWindow:
        self._assert_not_disabled(open_requester=opened_by)
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
        if not isinstance(artifact, ExpressionArtifact):
            raise TypeError("Emission requires a crystallized ExpressionArtifact")
        window = self._require_open_window()
        with self._acquire_fork_guard():
            stored_hashes, latest_counter = self._load_fingerprints()
            if artifact.artifact_hash in self._emitted_hashes or artifact.artifact_hash in stored_hashes:
                raise ExpressionReplayError("Artifact emission already recorded")
            status = "success"
            window.consume()
            self._window = None
            self._emitted_hashes.add(artifact.artifact_hash)
            self._emission_counter = max(self._emission_counter, latest_counter) + 1
            fingerprint = {
                "platform": platform,
                "artifact_hash": artifact.artifact_hash,
                "status": status,
                "timestamp": self._now().isoformat(),
                "window_id": window.window_id,
                "emission_counter": str(self._emission_counter),
            }
            self._emission_log.append(fingerprint)
            self._persist_fingerprint(fingerprint)
            self._record_autopsy(artifact, emitted=True)
            return fingerprint

    def discard(self, artifact: ExpressionArtifact) -> None:
        self._record_autopsy(artifact, emitted=False)

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

    def _record_autopsy(self, artifact: ExpressionArtifact, *, emitted: bool) -> None:
        summary = self._autopsy(artifact, emitted=emitted)
        compressed = self._compressed_autopsies.get(artifact.artifact_hash, {
            "artifact_hash": artifact.artifact_hash,
            "source_draft_id": artifact.source_draft_id,
            "emitted_count": 0,
            "discarded_count": 0,
            "state_influence": summary["state_influence"],
            "intent_valid": summary["intent_valid"],
        })
        if emitted:
            compressed["emitted_count"] = compressed.get("emitted_count", 0) + 1
        else:
            compressed["discarded_count"] = compressed.get("discarded_count", 0) + 1
        compressed["last_timestamp"] = summary["timestamp"]
        compressed["silence_preferred"] = not emitted
        compressed["emitted"] = emitted
        self._compressed_autopsies[artifact.artifact_hash] = compressed
        self._autopsies.append(compressed)

    def _load_fingerprints(self) -> tuple[Set[str], int]:
        if not self._fingerprint_store.exists():
            return set(), 0
        hashes: Set[str] = set()
        latest_counter = 0
        with open(self._fingerprint_store, "r", encoding="utf-8") as handle:
            for line in handle:
                parts = line.strip().split(",")
                if len(parts) < 3:
                    continue
                hashes.add(parts[0])
                try:
                    latest_counter = max(latest_counter, int(parts[2]))
                except ValueError:
                    continue
        return hashes, latest_counter

    def _persist_fingerprint(self, fingerprint: Mapping[str, str]) -> None:
        self._fingerprint_store.parent.mkdir(parents=True, exist_ok=True)
        line = ",".join(
            [
                fingerprint.get("artifact_hash", ""),
                fingerprint.get("window_id", ""),
                fingerprint.get("emission_counter", ""),
            ]
        )
        with open(self._fingerprint_store, "a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")

    @contextmanager
    def _acquire_fork_guard(self):
        with self._lock:
            if fcntl is None:
                yield
                return
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._lock_path, "w", encoding="utf-8") as lock_file:
                fcntl.lockf(lock_file, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.lockf(lock_file, fcntl.LOCK_UN)

    def _assert_not_disabled(self, *, open_requester: str) -> None:
        if os.getenv(self._kill_switch_flag, "").lower() == "true":
            timestamp = self._now().isoformat()
            self._emission_log.append(
                {
                    "platform": "expression-bridge",
                    "artifact_hash": "",
                    "status": "disabled",
                    "timestamp": timestamp,
                    "window_id": "",
                    "emission_counter": str(self._emission_counter),
                    "attempted_by": open_requester,
                }
            )
            raise PublishWindowClosedError("Expression bridge is disabled by operator")

