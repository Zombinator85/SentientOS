from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import time
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


class CapabilityExpiredError(RuntimeError):
    """Raised when a capability token is expired or exhausted."""


class CapabilityScopeError(RuntimeError):
    """Raised when a capability is missing or scoped incorrectly."""


class ExpressionSchemaError(RuntimeError):
    """Raised when an expression payload does not satisfy its schema."""


class BridgeState:
    QUIET = "QUIET"
    ARMED = "ARMED"
    KILLED = "KILLED"


@dataclass(frozen=True)
class EmissionCapability:
    """Ephemeral emission capability bounded by scope and monotonic expiry."""

    scope: str
    ttl: timedelta
    max_emissions: int
    issuer: str
    nonce: str
    issued_at_monotonic: float

    def is_expired(self, *, monotonic_now: float) -> bool:
        return monotonic_now > self.issued_at_monotonic + self.ttl.total_seconds()


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
    expression_type: str = "default"
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
                self.expression_type,
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

    def __init__(
        self,
        *,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        require_capability_for: Optional[Set[str]] = None,
        schema_registry: Optional[Mapping[str, Callable[[Mapping[str, object]], None]]] = None,
        ring_buffer_size: int = 64,
        wall_clock_drift_epsilon: timedelta | None = None,
    ) -> None:
        self._now = now or _default_now
        self._monotonic = monotonic or time.monotonic
        self._start_monotonic = self._monotonic()
        self._start_wall = self._now()
        self._drift_epsilon = wall_clock_drift_epsilon or timedelta(seconds=1)
        self._epoch_id = uuid.uuid4().hex
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
        self._ring_buffer: Deque[Mapping[str, str]] = deque(maxlen=ring_buffer_size)
        self._capability_requirements: Set[str] = set(require_capability_for or set())
        self._capability_usage: Dict[str, int] = {}
        self._schemas: Dict[str, Callable[[Mapping[str, object]], None]] = dict(schema_registry or {})
        self._state = BridgeState.QUIET
        self._state_transitions: List[Mapping[str, str]] = []
        self._record_state_transition(self._state, reason="init")

    def open_window(self, *, opened_by: str, ttl: timedelta) -> PublishWindow:
        self._assert_not_disabled(open_requester=opened_by)
        if self._window and self._window.is_open():
            raise PublishWindowClosedError("A publish window is already active")
        self._window = PublishWindow(opened_by=opened_by, ttl=ttl, now=self._now)
        return self._window

    def arm(self, *, reason: str = "operator") -> None:
        self._record_state_transition(BridgeState.ARMED, reason=reason)

    def quiet(self, *, reason: str = "operator") -> None:
        self._record_state_transition(BridgeState.QUIET, reason=reason)

    def kill(self, *, reason: str = "operator") -> None:
        self._record_state_transition(BridgeState.KILLED, reason=reason)

    def state(self) -> str:
        return self._state

    def state_log(self) -> List[Mapping[str, str]]:
        return list(self._state_transitions)

    def register_schema(self, *, expression_type: str, validator: Callable[[Mapping[str, object]], None]) -> None:
        self._schemas[expression_type] = validator

    def issue_capability(self, *, scope: str, ttl: timedelta, max_emissions: int = 1, issuer: str) -> EmissionCapability:
        if max_emissions <= 0:
            raise ValueError("max_emissions must be positive")
        nonce = uuid.uuid4().hex
        return EmissionCapability(
            scope=scope,
            ttl=ttl,
            max_emissions=max_emissions,
            issuer=issuer,
            nonce=nonce,
            issued_at_monotonic=self._monotonic(),
        )

    def crystallize(
        self,
        draft: IntentDraft,
        *,
        content: str,
        epistemic_basis: str,
        confidence_band: str,
        expression_type: str = "default",
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
            expression_type=expression_type,
        )

    def emit(
        self,
        artifact: ExpressionArtifact,
        *,
        platform: str,
        expression_type: Optional[str] = None,
        capability: Optional[EmissionCapability] = None,
        payload: Optional[Mapping[str, object]] = None,
    ) -> Mapping[str, str]:
        if not isinstance(artifact, ExpressionArtifact):
            suppression_reason = "invalid-artifact"
            self._record_ring_buffer(artifact_hash="invalid", platform=platform, reason=suppression_reason)
            raise TypeError("Emission requires a crystallized ExpressionArtifact")
        expression_scope = expression_type or artifact.expression_type
        suppression_reason = None
        self._assert_state_allows_emission(expression_scope=expression_scope, platform=platform)
        self._validate_schema(expression_scope, payload)
        self._assert_not_disabled(open_requester=platform)
        capability_nonce = self._consume_capability_if_required(
            expression_scope,
            capability,
            artifact_hash=artifact.artifact_hash,
            platform=platform,
        )
        window = self._require_open_window()
        timestamp, timestamp_source = self._timestamp_with_drift_guard()
        monotonic_window = self._monotonic_window()
        with self._acquire_fork_guard():
            stored_hashes, latest_counter = self._load_fingerprints()
            if artifact.artifact_hash in self._emitted_hashes or artifact.artifact_hash in stored_hashes:
                suppression_reason = "replay-detected"
                self._record_ring_buffer(
                    artifact_hash=artifact.artifact_hash,
                    platform=platform,
                    reason=suppression_reason,
                )
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
                "timestamp": timestamp,
                "timestamp_source": timestamp_source,
                "window_id": window.window_id,
                "emission_counter": str(self._emission_counter),
                "epoch_id": self._epoch_id,
                "monotonic_window": monotonic_window,
                "capability_nonce": capability_nonce or "",
                "state": self._state,
            }
            self._emission_log.append(fingerprint)
            self._persist_fingerprint(fingerprint)
            self._record_autopsy(artifact, emitted=True)
            self._record_ring_buffer(
                artifact_hash=artifact.artifact_hash,
                platform=platform,
                reason=None,
            )
            return fingerprint

    def discard(self, artifact: ExpressionArtifact) -> None:
        self._record_autopsy(artifact, emitted=False)

    def forensic_ring(self) -> List[Mapping[str, str]]:
        return list(self._ring_buffer)

    def _assert_state_allows_emission(self, *, expression_scope: str, platform: str) -> None:
        if self._state != BridgeState.ARMED:
            reason = f"state-{self._state.lower()}"
            self._record_ring_buffer(artifact_hash="pending", platform=platform, reason=reason)
            raise PublishWindowClosedError(f"Bridge is not armed for emission: {expression_scope}")

    def _validate_schema(self, expression_scope: str, payload: Optional[Mapping[str, object]]) -> None:
        validator = self._schemas.get(expression_scope)
        if validator is None:
            return
        if payload is None:
            self._record_ring_buffer(artifact_hash="pending", platform=expression_scope, reason="schema-missing")
            raise ExpressionSchemaError(f"Schema validation requires payload for {expression_scope}")
        try:
            validator(payload)
        except Exception as exc:  # noqa: BLE001
            self._record_ring_buffer(artifact_hash="pending", platform=expression_scope, reason="schema-invalid")
            raise ExpressionSchemaError(str(exc)) from exc

    def _consume_capability_if_required(
        self,
        expression_scope: str,
        capability: Optional[EmissionCapability],
        *,
        artifact_hash: str,
        platform: str,
    ) -> Optional[str]:
        if expression_scope not in self._capability_requirements:
            return None
        if capability is None:
            self._record_ring_buffer(artifact_hash=artifact_hash, platform=platform, reason="capability-missing")
            raise CapabilityScopeError(f"Capability required for expression scope {expression_scope}")
        if capability.scope != expression_scope:
            self._record_ring_buffer(artifact_hash=artifact_hash, platform=platform, reason="capability-scope")
            raise CapabilityScopeError(f"Capability scope mismatch: {capability.scope} != {expression_scope}")
        monotonic_now = self._monotonic()
        if capability.is_expired(monotonic_now=monotonic_now):
            self._record_ring_buffer(artifact_hash=artifact_hash, platform=platform, reason="capability-expired")
            raise CapabilityExpiredError("Capability expired")
        use_count = self._capability_usage.get(capability.nonce, 0)
        if use_count >= capability.max_emissions:
            self._record_ring_buffer(artifact_hash=artifact_hash, platform=platform, reason="capability-exhausted")
            raise CapabilityExpiredError("Capability emissions exhausted")
        self._capability_usage[capability.nonce] = use_count + 1
        return capability.nonce

    def _require_open_window(self) -> PublishWindow:
        if not self._window or not self._window.is_open():
            raise PublishWindowClosedError("No open publish window available")
        return self._window

    def _timestamp_with_drift_guard(self) -> tuple[str, str]:
        wall_now = self._now()
        monotonic_estimate = self._start_wall + timedelta(seconds=self._monotonic() - self._start_monotonic)
        drift_seconds = abs((wall_now - monotonic_estimate).total_seconds())
        if drift_seconds > self._drift_epsilon.total_seconds():
            return monotonic_estimate.isoformat(), "monotonic"
        return wall_now.isoformat(), "wall"

    def _monotonic_window(self) -> str:
        return str(int(self._monotonic()))

    def _record_ring_buffer(self, *, artifact_hash: str, platform: str, reason: Optional[str]) -> None:
        fingerprint_base = f"{artifact_hash}:{platform}:{self._epoch_id}:{self._monotonic_window()}"
        entry_hash = hashlib.sha256(fingerprint_base.encode("utf-8")).hexdigest()
        timestamp, source = self._timestamp_with_drift_guard()
        self._ring_buffer.append(
            {
                "fingerprint_hash": entry_hash,
                "timestamp": timestamp,
                "timestamp_source": source,
                "source": platform,
                "suppression_reason": reason or "",
            }
        )

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
                fingerprint.get("epoch_id", ""),
                fingerprint.get("monotonic_window", ""),
                fingerprint.get("timestamp_source", ""),
            ]
        )
        with open(self._fingerprint_store, "a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")

    def _record_state_transition(self, new_state: str, *, reason: str) -> None:
        if new_state not in {BridgeState.QUIET, BridgeState.ARMED, BridgeState.KILLED}:
            raise ValueError(f"Unsupported state: {new_state}")
        if self._state == BridgeState.KILLED and new_state != BridgeState.KILLED:
            return
        self._state = new_state
        timestamp, source = self._timestamp_with_drift_guard()
        self._state_transitions.append(
            {
                "state": new_state,
                "timestamp": timestamp,
                "timestamp_source": source,
                "reason": reason,
            }
        )

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
        if self._state == BridgeState.KILLED:
            self._record_ring_buffer(artifact_hash="pending", platform=open_requester, reason="killed")
            raise PublishWindowClosedError("Expression bridge is killed")
        if os.getenv(self._kill_switch_flag, "").lower() == "true":
            timestamp = self._now().isoformat()
            self._record_state_transition(BridgeState.KILLED, reason="kill-switch")
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
            self._record_ring_buffer(artifact_hash="pending", platform=open_requester, reason="kill-switch")
            raise PublishWindowClosedError("Expression bridge is disabled by operator")
