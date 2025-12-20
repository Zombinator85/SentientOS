from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from types import MappingProxyType
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple
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

    VERSION = 0
    LOCAL_AUTONOMY = 1
    ADVISORY_WINDOW = 2
    BROWNOUT = 3


_CONFIDENCE_LEVELS: Mapping[str, int] = MappingProxyType({"LOW": 0, "MEDIUM": 1, "HIGH": 2})


@dataclass(frozen=True)
class _ActionRule:
    allowed_phases: Tuple[SystemPhase, ...]
    description: str


_ACTION_RULES: Mapping[str, _ActionRule] = MappingProxyType(
    {
        "architecture_change": _ActionRule(
            allowed_phases=(SystemPhase.ADVISORY_WINDOW,),
            description="architecture changes require advisory window",
        ),
        "confidence_upgrade": _ActionRule(
            allowed_phases=(SystemPhase.ADVISORY_WINDOW,),
            description="confidence upgrades require advisory window",
        ),
        "self_update_execution": _ActionRule(
            allowed_phases=(SystemPhase.ADVISORY_WINDOW,),
            description="self-updates must be orchestrated inside advisory window",
        ),
        "connector_usage": _ActionRule(
            allowed_phases=(SystemPhase.ADVISORY_WINDOW,),
            description="connectors are advisory-only",
        ),
        "state_preservation": _ActionRule(
            allowed_phases=(SystemPhase.BROWNOUT,),
            description="brownout permits state preservation only",
        ),
        "checkpoint_write": _ActionRule(
            allowed_phases=(SystemPhase.BROWNOUT, SystemPhase.ADVISORY_WINDOW, SystemPhase.LOCAL_AUTONOMY),
            description="checkpoints may be written in any explicit phase",
        ),
    }
)


@dataclass
class PhaseGate:
    """Enforces phase ordering and action guards."""

    phase: SystemPhase = SystemPhase.LOCAL_AUTONOMY
    history: List[Tuple[float, SystemPhase, str]] = field(default_factory=list)

    def record(self, message: str) -> None:
        self.history.append((time.time(), self.phase, message))

    def transition(self, next_phase: SystemPhase, *, reason: str | None = None) -> None:
        if self.phase is SystemPhase.BROWNOUT and next_phase in (
            SystemPhase.ADVISORY_WINDOW,
            SystemPhase.LOCAL_AUTONOMY,
        ):
            self.phase = next_phase
            self.record(reason or f"exited brownout to {next_phase.name}")
            return
        if next_phase < self.phase:
            self.record("phase rollback attempt")
            raise GuardViolation("phase bypass is forbidden")
        if next_phase == self.phase:
            return
        self.phase = next_phase
        self.record(reason or f"transitioned to {next_phase.name}")

    def enforce(self, action: str, **context: Any) -> None:
        orchestrated_brownout = self.phase is SystemPhase.BROWNOUT and action == "self_update_execution" and context.get("orchestrated")
        if self.phase is SystemPhase.BROWNOUT and action not in {"state_preservation", "checkpoint_write"} and not orchestrated_brownout:
            self.record(f"blocked {action} during brownout")
            raise GuardViolation("brownout forbids learning and self-modification")
        rule = _ACTION_RULES.get(action)
        if rule is None:
            self.record(f"unknown action: {action}")
            raise GuardViolation(f"unknown guarded action: {action}")
        if self.phase not in rule.allowed_phases and not orchestrated_brownout:
            self.record(f"violation: {action} at {self.phase.name}")
            allowed = ", ".join(p.name for p in rule.allowed_phases)
            raise GuardViolation(f"{action} requires phase(s) [{allowed}], current is {self.phase.name}")
        if action == "confidence_upgrade":
            target = str(context.get("target", "HIGH")).upper()
            target_level = _CONFIDENCE_LEVELS.get(target, _CONFIDENCE_LEVELS["HIGH"])
            if self.phase is SystemPhase.LOCAL_AUTONOMY and target_level > _CONFIDENCE_LEVELS["MEDIUM"]:
                self.record("confidence upgrade above MEDIUM blocked")
                raise GuardViolation("local autonomy forbids confidence upgrades above MEDIUM")
        if action == "self_update_execution" and context.get("unattended", False):
            self.record("unattended self-update blocked")
            raise GuardViolation("unattended self-update is forbidden")
        self.record(f"guarded {action}")


@dataclass(frozen=True)
class SystemCheckpoint:
    """Canonical, versioned, immutable checkpoint store."""

    checkpoint_version: int
    phase: SystemPhase
    created_at: float
    module_snapshots: Mapping[str, Any]
    volatility: Mapping[str, Any]
    assertions: Tuple[Mapping[str, Any], ...]
    inquiry_backlog: Tuple[Any, ...]
    narrative_synopses: Tuple[str, ...]
    constraint_registry: Mapping[str, Any]
    schema_versions: Mapping[str, str]
    note: str = ""
    lineage: Tuple[int, ...] = field(default_factory=tuple)

    def materialize(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "module_snapshots": copy.deepcopy(dict(self.module_snapshots)),
            "volatility": copy.deepcopy(dict(self.volatility)),
            "assertions": copy.deepcopy(list(self.assertions)),
            "inquiry_backlog": copy.deepcopy(list(self.inquiry_backlog)),
            "narrative_synopses": copy.deepcopy(list(self.narrative_synopses)),
            "constraint_registry": copy.deepcopy(dict(self.constraint_registry)),
            "schema_versions": copy.deepcopy(dict(self.schema_versions)),
            "checkpoint_version": self.checkpoint_version,
            "created_at": self.created_at,
            "note": self.note,
            "lineage": self.lineage,
        }


class CheckpointLedger:
    """Canonical, versioned, immutable checkpoint ledger with migration support."""

    def __init__(self) -> None:
        self._history: List[SystemCheckpoint] = []
        self._migrations: Dict[int, Callable[[MutableMapping[str, Any]], None]] = {}
        self._version_counter = 0

    def register_migration(
        self, from_version: int, func: Callable[[MutableMapping[str, Any]], None]
    ) -> None:
        self._migrations[from_version] = func

    def snapshot(
        self,
        *,
        phase: SystemPhase,
        module_snapshots: Mapping[str, Any],
        volatility: Mapping[str, Any],
        assertions: Iterable[Mapping[str, Any]],
        inquiry_backlog: Iterable[Any],
        narrative_synopses: Iterable[str],
        constraint_registry: Mapping[str, Any],
        schema_versions: Mapping[str, str],
        note: str = "",
    ) -> SystemCheckpoint:
        self._version_counter += 1
        frozen = SystemCheckpoint(
            checkpoint_version=self._version_counter,
            phase=phase,
            created_at=time.time(),
            module_snapshots=MappingProxyType(copy.deepcopy(dict(module_snapshots))),
            volatility=MappingProxyType(copy.deepcopy(dict(volatility))),
            assertions=tuple(copy.deepcopy(list(assertions))),
            inquiry_backlog=tuple(copy.deepcopy(list(inquiry_backlog))),
            narrative_synopses=tuple(copy.deepcopy(list(narrative_synopses))),
            constraint_registry=MappingProxyType(copy.deepcopy(dict(constraint_registry))),
            schema_versions=MappingProxyType(copy.deepcopy(dict(schema_versions))),
            note=note,
            lineage=tuple(cp.checkpoint_version for cp in self._history),
        )
        self._history.append(frozen)
        return frozen

    def latest(self) -> SystemCheckpoint:
        if not self._history:
            raise SnapshotIntegrityError("no checkpoints recorded")
        return self._history[-1]

    def _apply_migrations(self, version: int, state: MutableMapping[str, Any]) -> None:
        current = version
        while current in self._migrations:
            self._migrations[current](state)
            current += 1

    def restore(self, version: int | None = None) -> Dict[str, Any]:
        if not self._history:
            raise SnapshotIntegrityError("no checkpoints recorded")
        checkpoint = self.latest() if version is None else self._get_version(version)
        state = checkpoint.materialize()
        self._apply_migrations(checkpoint.checkpoint_version, state)
        return state

    def _get_version(self, version: int) -> SystemCheckpoint:
        for cp in self._history:
            if cp.checkpoint_version == version:
                return cp
        raise SnapshotIntegrityError(f"checkpoint {version} not found")


class SelfUpdateOrchestrator:
    """Authoritative self-update orchestrator with rollback."""

    def __init__(self, gate: PhaseGate, ledger: CheckpointLedger):
        self.gate = gate
        self.ledger = ledger
        self.status: Dict[str, Any] = {"brownout": False, "last_failure": None, "last_checkpoint": None}

    def _deterministic_plan(self, modules: Mapping[str, Callable[[], None]]) -> List[Tuple[str, Callable[[], None]]]:
        return [(name, modules[name]) for name in sorted(modules)]

    def perform_update(
        self,
        modules: Mapping[str, Callable[[], None]],
        module_snapshots: Mapping[str, Any],
        volatility: Mapping[str, Any],
        assertions: Sequence[Mapping[str, Any]],
        inquiry_backlog: Sequence[Any],
        narrative_synopses: Sequence[str],
        constraint_registry: Mapping[str, Any],
        schema_versions: Mapping[str, str],
        swapper: Callable[[], None],
        rehydrator: Callable[[Mapping[str, Any]], Mapping[str, Any]],
        validator: Callable[[Mapping[str, Any]], None],
        author: str,
        allow_auto_merge: bool = False,
        note: str = "",
    ) -> List[str]:
        if author == "self":
            raise GuardViolation("no self-authored execution")
        if allow_auto_merge:
            raise GuardViolation("auto-merge during self-update is forbidden")

        self.gate.transition(SystemPhase.BROWNOUT, reason="entering self-update brownout")
        self.status["brownout"] = True
        checkpoint = self.ledger.snapshot(
            phase=self.gate.phase,
            module_snapshots=module_snapshots,
            volatility=volatility,
            assertions=assertions,
            inquiry_backlog=inquiry_backlog,
            narrative_synopses=narrative_synopses,
            constraint_registry=constraint_registry,
            schema_versions=schema_versions,
            note=note or "pre-update checkpoint",
        )
        self.status["last_checkpoint"] = checkpoint.checkpoint_version
        plan = self._deterministic_plan(modules)
        executed: List[str] = []
        try:
            swapper()
            for name, restart in plan:
                self.gate.enforce("self_update_execution", unattended=False, orchestrated=True)
                restart()
                executed.append(name)
            restored_state = rehydrator(checkpoint.materialize())
            validator(restored_state)
            self.gate.transition(SystemPhase.ADVISORY_WINDOW, reason="update completed")
            self.status["brownout"] = False
            self.status["last_failure"] = None
            return executed
        except Exception as exc:  # pragma: no cover - defensive branch
            self.status["last_failure"] = str(exc)
            restored = self.ledger.restore(checkpoint.checkpoint_version)
            self.gate.transition(SystemPhase.ADVISORY_WINDOW, reason="rollback from failure")
            raise RollbackError(
                f"update failed after {executed}; restored checkpoint {checkpoint.checkpoint_version}"
            ) from exc

    def rollback(self, version: int | None = None) -> Dict[str, Any]:
        self.status["brownout"] = True
        state = self.ledger.restore(version)
        return state


UpdateOrchestrator = SelfUpdateOrchestrator


class DriftSentinel:
    """Detects subtle narrative drifts and emits review events."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def _emit(self, kind: str, detail: str, *, severity: str = "review") -> None:
        self.events.append(
            {
                "kind": kind,
                "detail": f"{detail}; this changed without explanation",
                "severity": severity,
                "at": time.time(),
            }
        )

    def scan(self, previous: Mapping[str, Any], current: Mapping[str, Any]) -> List[Dict[str, Any]]:
        self.events.clear()
        self._detect_belief_hardening(previous, current)
        self._detect_authority_expansion(previous, current)
        self._detect_constraint_changes(previous, current)
        self._detect_assertion_confidence(previous, current)
        self._detect_narrative_compression(previous, current)
        return list(self.events)

    def _detect_belief_hardening(self, previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
        prev_beliefs = {b["id"]: b for b in previous.get("beliefs", []) if isinstance(b, Mapping) and "id" in b}
        for belief in current.get("beliefs", []):
            if not isinstance(belief, Mapping) or "id" not in belief:
                continue
            prev = prev_beliefs.get(belief["id"])
            if prev and belief.get("confidence", 0) > prev.get("confidence", 0) and belief.get("evidence") == prev.get("evidence"):
                self._emit("belief_hardening", f"{belief['id']} gained confidence without new evidence")

    def _detect_authority_expansion(self, previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
        prev_auth = set(previous.get("authorities", []))
        curr_auth = set(current.get("authorities", []))
        if curr_auth - prev_auth:
            self._emit("authority_expansion", "authority surface expanded")

    def _detect_constraint_changes(self, previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
        prev_constraints = previous.get("constraint_registry", {}) or {}
        curr_constraints = current.get("constraint_registry", {}) or {}
        if prev_constraints != curr_constraints:
            self._emit("constraint_change", "constraint registry changed")

    def _detect_assertion_confidence(self, previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
        prev_assertions = {a.get("id"): a for a in previous.get("assertions", []) if isinstance(a, Mapping)}
        for assertion in current.get("assertions", []):
            ident = assertion.get("id")
            if ident is None:
                continue
            prev = prev_assertions.get(ident, {})
            if assertion.get("confidence") and assertion.get("confidence") != prev.get("confidence"):
                self._emit("assertion_confidence", f"assertion {ident} confidence moved")

    def _detect_narrative_compression(self, previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
        prev_synopsis = "".join(previous.get("narrative_synopses", []))
        curr_synopsis = "".join(current.get("narrative_synopses", []))
        if prev_synopsis and curr_synopsis and len(curr_synopsis) < len(prev_synopsis):
            self._emit("narrative_compression", "narrative synopsis compressed")


class HumanLens:
    """Read-only deterministic view for human operators."""

    def __init__(
        self,
        *,
        checkpoint: SystemCheckpoint,
        posture: str,
        open_questions: Sequence[str],
        recent_revisions: Sequence[str],
    ) -> None:
        self._view = MappingProxyType(
            {
                "current_phase": checkpoint.phase.name,
                "system_posture": posture,
                "story_so_far": tuple(checkpoint.narrative_synopses),
                "open_questions": tuple(open_questions),
                "recent_revisions": tuple(recent_revisions),
                "last_checkpoint": {
                    "version": checkpoint.checkpoint_version,
                    "created_at": checkpoint.created_at,
                    "note": checkpoint.note,
                },
            }
        )

    @property
    def data(self) -> Mapping[str, Any]:
        return self._view

    def render(self) -> str:
        lines: List[str] = []
        for key in sorted(self._view):
            value = self._view[key]
            if isinstance(value, Mapping):
                payload = ", ".join(f"{k}={value[k]}" for k in sorted(value))
            elif isinstance(value, (list, tuple)):
                payload = "; ".join(map(str, value))
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
