"""Continuity utilities for SentientOS.

This module introduces phase-aware execution, canonical checkpoints,
update orchestration with rollback, drift detection, and read-only narrative views.
The goal is to ensure the system can change safely without losing memory
or bypassing authority boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from types import MappingProxyType
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Tuple
import copy
import time


class GuardViolation(RuntimeError):
    """Raised when a hard guard is tripped."""


class SnapshotIntegrityError(RuntimeError):
    """Raised when a snapshot cannot be restored faithfully."""


class RollbackError(RuntimeError):
    """Raised when a rollback is required due to an update failure."""


class SystemPhase(IntEnum):
    """Lifecycle phases used to gate privileged actions."""

    GENESIS = 0
    ARCHITECTURE = 1
    CONFIDENCE = 2
    OPERATIONS = 3
    ADAPTIVE = 4

    def allows(self, minimum: "SystemPhase") -> bool:
        return self >= minimum


_ACTION_MINIMUMS: Mapping[str, SystemPhase] = MappingProxyType(
    {
        "architecture_change": SystemPhase.ARCHITECTURE,
        "confidence_upgrade": SystemPhase.CONFIDENCE,
        "self_modification": SystemPhase.OPERATIONS,
        "connector_usage": SystemPhase.OPERATIONS,
    }
)


@dataclass
class PhaseGate:
    """Enforces phase ordering and action guards.

    The gate is intentionally strict: skipping phases or attempting
    actions too early results in a hard failure.
    """

    phase: SystemPhase = SystemPhase.GENESIS
    history: List[Tuple[float, SystemPhase, str]] = field(default_factory=list)

    def record(self, message: str) -> None:
        self.history.append((time.time(), self.phase, message))

    def transition(self, next_phase: SystemPhase, *, reason: str | None = None) -> None:
        if next_phase < self.phase:
            raise GuardViolation("phase bypass is forbidden")
        if next_phase == self.phase:
            return
        self.phase = next_phase
        self.record(reason or f"transitioned to {next_phase.name}")

    def enforce(self, action: str) -> None:
        minimum = _ACTION_MINIMUMS.get(action)
        if minimum is None:
            raise GuardViolation(f"unknown guarded action: {action}")
        if not self.phase.allows(minimum):
            raise GuardViolation(
                f"{action} requires at least {minimum.name}, current is {self.phase.name}"
            )
        self.record(f"guarded {action}")


@dataclass(frozen=True)
class SystemCheckpoint:
    version: int
    phase: SystemPhase
    created_at: float
    subsystems: Mapping[str, Any]
    lineage: Tuple[int, ...] = field(default_factory=tuple)
    note: str = ""

    def materialize(self) -> Dict[str, Any]:
        """Return a deep copy so callers cannot mutate the stored state."""
        return copy.deepcopy(self.subsystems)


class CheckpointLedger:
    """Canonical, versioned, immutable checkpoint store."""

    def __init__(self) -> None:
        self._history: List[SystemCheckpoint] = []
        self._migrations: Dict[int, Callable[[MutableMapping[str, Any]], None]] = {}
        self._version_counter = 0

    def register_migration(self, from_version: int, func: Callable[[MutableMapping[str, Any]], None]) -> None:
        self._migrations[from_version] = func

    def snapshot(self, phase: SystemPhase, subsystems: Mapping[str, Any], *, note: str = "") -> SystemCheckpoint:
        self._version_counter += 1
        frozen = MappingProxyType(copy.deepcopy(dict(subsystems)))
        lineage = tuple(cp.version for cp in self._history)
        checkpoint = SystemCheckpoint(
            version=self._version_counter,
            phase=phase,
            created_at=time.time(),
            subsystems=frozen,
            lineage=lineage,
            note=note,
        )
        self._history.append(checkpoint)
        return checkpoint

    def latest(self) -> SystemCheckpoint:
        if not self._history:
            raise SnapshotIntegrityError("no checkpoints recorded")
        return self._history[-1]

    def _apply_migrations(self, version: int, state: MutableMapping[str, Any]) -> None:
        current_version = version
        while current_version in self._migrations:
            self._migrations[current_version](state)
            current_version += 1

    def restore(self, version: int | None = None) -> Dict[str, Any]:
        if not self._history:
            raise SnapshotIntegrityError("no checkpoints recorded")
        if version is None:
            checkpoint = self._history[-1]
        else:
            matches = [cp for cp in self._history if cp.version == version]
            if not matches:
                raise SnapshotIntegrityError(f"checkpoint {version} not found")
            checkpoint = matches[0]
        state = copy.deepcopy(dict(checkpoint.subsystems))
        self._apply_migrations(checkpoint.version, state)
        return state


class UpdateOrchestrator:
    """Deterministic, rollback-capable orchestrator."""

    def __init__(self, gate: PhaseGate, ledger: CheckpointLedger):
        self.gate = gate
        self.ledger = ledger
        self.status: Dict[str, Any] = {"brown_out": False, "last_failure": None}

    def _deterministic_plan(self, modules: Mapping[str, Callable[[], None]]) -> List[Tuple[str, Callable[[], None]]]:
        return [(name, modules[name]) for name in sorted(modules)]

    def reload(self, modules: Mapping[str, Callable[[], None]], subsystems: Mapping[str, Any]) -> List[str]:
        self.gate.enforce("self_modification")
        checkpoint = self.ledger.snapshot(self.gate.phase, subsystems, note="pre-update")
        plan = self._deterministic_plan(modules)
        executed: List[str] = []
        try:
            for name, restart in plan:
                restart()
                executed.append(name)
            self.status["brown_out"] = False
            self.status["last_failure"] = None
            return executed
        except Exception as exc:  # pragma: no cover - defensive branch
            self.status["brown_out"] = True
            self.status["last_failure"] = str(exc)
            restored = self.ledger.restore(checkpoint.version)
            raise RollbackError(
                f"update failed after {executed}; restored checkpoint {checkpoint.version}"
            ) from exc

    def rollback(self, version: int | None = None) -> Dict[str, Any]:
        self.status["brown_out"] = True
        state = self.ledger.restore(version)
        return state


class DriftSentinel:
    """Detects subtle narrative drifts and emits review events."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def _emit(self, kind: str, detail: str, *, severity: str = "review") -> None:
        self.events.append({"kind": kind, "detail": detail, "severity": severity, "at": time.time()})

    def scan(self, previous: Mapping[str, Any], current: Mapping[str, Any]) -> List[Dict[str, Any]]:
        self.events.clear()
        self._detect_belief_hardening(previous, current)
        self._detect_authority_creep(previous, current)
        self._detect_narrative_flattening(previous, current)
        return list(self.events)

    def _detect_belief_hardening(self, previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
        prev_beliefs = {b["id"]: b for b in previous.get("beliefs", []) if isinstance(b, Mapping) and "id" in b}
        for belief in current.get("beliefs", []):
            if not isinstance(belief, Mapping) or "id" not in belief:
                continue
            prev = prev_beliefs.get(belief["id"])
            if prev and belief.get("confidence", 0) > prev.get("confidence", 0) and belief.get("evidence") == prev.get("evidence"):
                self._emit("belief_hardening", f"{belief['id']} gained confidence without new evidence")

    def _detect_authority_creep(self, previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
        prev_auth = set(previous.get("authorities", []))
        curr_auth = set(current.get("authorities", []))
        if curr_auth - prev_auth:
            self._emit("authority_creep", "external authority import detected")

    def _detect_narrative_flattening(self, previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
        prev_narr = previous.get("narrative")
        curr_narr = current.get("narrative")
        if prev_narr and curr_narr and isinstance(prev_narr, Mapping) and isinstance(curr_narr, Mapping):
            if len(curr_narr.get("threads", [])) < len(prev_narr.get("threads", [])):
                self._emit("narrative_flattening", "narrative threads removed without record")


class NarrativeView:
    """Read-only, deterministic view of narrative state."""

    def __init__(self, narrative: Mapping[str, Any]):
        self._snapshot = MappingProxyType(copy.deepcopy(dict(narrative)))

    @property
    def data(self) -> Mapping[str, Any]:
        return self._snapshot

    def render(self) -> str:
        lines: List[str] = []
        for key in sorted(self._snapshot):
            value = self._snapshot[key]
            if isinstance(value, list):
                payload = ", ".join(sorted(map(str, value)))
            elif isinstance(value, Mapping):
                payload = ", ".join(f"{k}={value[k]}" for k in sorted(value))
            else:
                payload = str(value)
            lines.append(f"{key}: {payload}")
        return "\n".join(lines)


def assert_no_silent_mutation(previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
    if previous == current:
        return
    if previous.keys() != current.keys():
        raise GuardViolation("auto-merge or silent state mutation detected")
    for key, value in previous.items():
        if value != current.get(key):
            raise GuardViolation(f"state changed for {key} without explicit approval")


def assert_no_belief_deletion(previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
    prev_beliefs = {b.get("id") for b in previous.get("beliefs", []) if isinstance(b, Mapping)}
    curr_beliefs = {b.get("id") for b in current.get("beliefs", []) if isinstance(b, Mapping)}
    missing = prev_beliefs - curr_beliefs
    if missing:
        raise GuardViolation(f"belief deletion detected: {sorted(missing)}")


def assert_no_external_authority_import(current: Mapping[str, Any]) -> None:
    external = [a for a in current.get("authorities", []) if str(a).startswith("external:")]
    if external:
        raise GuardViolation("external authority import is forbidden")
