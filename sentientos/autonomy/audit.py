"""Audit helpers for autonomy action tracing.

This module centralises how GUI, browser and other embodied subsystems record
their activity while enforcing the nervous-system doctrine.  Every action must
be innervated (affective context + uncertainty), constraint-legible, pressure
aware, sensor-honest, and authority-isolated.  Log entries are persisted to
``logs/autonomy_actions.jsonl`` so that operators can inspect recent actions via
the admin dashboard or command line helpers.  The helper is intentionally
lightweight so it can be imported without pulling in FastAPI or other optional
dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

import affective_context as ac
from sentientos.constraint_registry import ConstraintRegistry
from sentientos.pressure_engagement import (
    ConstraintEngagementEngine,
    ConstraintEngagementRecord,
    ConstraintPressureState,
)
from sentientos.sensor_provenance import (
    SensorProvenance,
    default_provenance_for_constraint,
    require_sensor_provenance,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_log_path() -> Path:
    root = Path(os.getenv("SENTIENTOS_ACTION_LOG", "logs/autonomy_actions.jsonl"))
    root.parent.mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class AutonomyAction:
    """Structured representation of an autonomy action."""

    module: str
    action: str
    status: str
    timestamp: str = field(default_factory=_utcnow)
    affective_context: Mapping[str, object] = field(default_factory=dict)
    uncertainty: float = 0.0
    constraint_id: str = ""
    constraint_justification: str = ""
    sensor_provenance: Mapping[str, object] = field(default_factory=dict)
    pressure: Mapping[str, object] = field(default_factory=dict)
    assumptions: Tuple[str, ...] = field(default_factory=tuple)
    environment: Mapping[str, object] = field(default_factory=dict)
    authority_guard: Mapping[str, object] = field(default_factory=dict)
    details: MutableMapping[str, object] = field(default_factory=dict)

    def to_json(self) -> str:
        payload = {
            "timestamp": self.timestamp,
            "module": self.module,
            "action": self.action,
            "status": self.status,
            "affective_context": self.affective_context,
            "uncertainty": self.uncertainty,
            "constraint_id": self.constraint_id,
            "constraint_justification": self.constraint_justification,
            "sensor_provenance": self.sensor_provenance,
            "pressure": self.pressure,
            "assumptions": list(self.assumptions),
            "environment": dict(self.environment),
            "authority_guard": dict(self.authority_guard),
        }
        if self.details:
            payload.update(self.details)
        return json.dumps(payload, ensure_ascii=False)


class AutonomyActionLogger:
    """Persist and retrieve audit entries for embodied actions."""

    def __init__(
        self,
        *,
        path: Optional[Path] = None,
        history_size: int = 200,
        constraint_registry: ConstraintRegistry | None = None,
        pressure_engine: ConstraintEngagementEngine | None = None,
    ) -> None:
        self._path = path or _default_log_path()
        self._history_size = max(int(history_size), 1)
        self._lock = Lock()
        self._registry = constraint_registry or ConstraintRegistry()
        self._pressure = pressure_engine or ConstraintEngagementEngine(registry=self._registry)

    @property
    def path(self) -> Path:
        return self._path

    def log(
        self,
        module: str,
        action: str,
        status: str,
        *,
        affective_overlay: Optional[Mapping[str, object]] = None,
        uncertainty: float = 0.25,
        constraint_id: Optional[str] = None,
        constraint_justification: Optional[str] = None,
        sensor_provenance: Mapping[str, object] | SensorProvenance | None = None,
        assumptions: Sequence[str] | None = None,
        environment: Mapping[str, object] | None = None,
        decision_points: Sequence[str] | None = None,
        amplification: Mapping[str, object] | None = None,
        pressure_magnitude: float = 1.0,
        pressure_reason: Optional[str] = None,
        authority_metadata: Mapping[str, object] | None = None,
        **details: object,
    ) -> None:
        overlay, uncertainty_value = self._normalize_affective_context(affective_overlay, status=status)
        constraint = self._normalize_constraint(module, action, constraint_id, constraint_justification)
        provenance = self._normalize_sensor_provenance(sensor_provenance, constraint_id=constraint)
        pressure_state, explanation = self._record_pressure(
            constraint_id=constraint,
            magnitude=pressure_magnitude,
            reason=pressure_reason or status,
            affective_context=overlay,
            blocked=status == "blocked",
            provenance=provenance,
            assumptions=assumptions or (),
            decision_points=decision_points or (),
            environment=environment or {},
            amplification=amplification or {},
        )
        authority_guard = self._authority_guard(details, authority_metadata)
        entry = AutonomyAction(
            module=module,
            action=action,
            status=status,
            affective_context=overlay,
            uncertainty=uncertainty_value,
            constraint_id=constraint,
            constraint_justification=self._registry.require(constraint).justification,
            sensor_provenance=provenance.to_payload(),
            pressure=self._pressure_snapshot(pressure_state, explanation),
            assumptions=tuple(assumptions or ()),
            environment=dict(environment or {}),
            authority_guard=authority_guard,
            details=dict(details),
        )
        record = entry.to_json()
        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(record + "\n")
            self._trim_locked()

    def _trim_locked(self) -> None:
        if self._history_size <= 0 or not self._path.exists():
            return
        lines = self._path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= self._history_size:
            return
        keep = lines[-self._history_size :]
        self._path.write_text("\n".join(keep) + "\n", encoding="utf-8")

    def recent(self, limit: int = 50, *, modules: Iterable[str] | None = None) -> List[Mapping[str, object]]:
        limit = max(int(limit), 1)
        module_filter = {m for m in modules} if modules else None
        if not self._path.exists():
            return []
        with self._lock:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        items: List[Mapping[str, object]] = []
        for raw in reversed(lines):
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if module_filter and parsed.get("module") not in module_filter:
                continue
            items.append(parsed)
            if len(items) >= limit:
                break
        items.reverse()
        return items

    def summary(self) -> Mapping[str, object]:
        """Return a compact summary for dashboard consumption."""

        recent = self.recent(20)
        totals: Dict[str, int] = {}
        blocked = 0
        for entry in recent:
            module = str(entry.get("module", "unknown"))
            totals[module] = totals.get(module, 0) + 1
            if entry.get("status") == "blocked":
                blocked += 1
        return {
            "recent": recent,
            "totals": totals,
            "blocked_recent": blocked,
        }

    def _normalize_affective_context(
        self, overlay: Optional[Mapping[str, object]], *, status: str
    ) -> Tuple[Mapping[str, object], float]:
        resolved = overlay or ac.capture_affective_context(
            f"autonomy-{status}", overlay={"friction": 1.0 if status == "blocked" else 0.25}
        )
        ac.require_affective_context({"affective_context": resolved})
        uncertainty = resolved.get("bounds", {}).get("max", 1.0)
        try:
            uncertainty_value = min(1.0, max(0.0, float(resolved.get("uncertainty", 0.25))))
        except Exception:
            uncertainty_value = 0.25
        return resolved, uncertainty_value

    def _normalize_constraint(
        self,
        module: str,
        action: str,
        constraint_id: Optional[str],
        justification: Optional[str],
    ) -> str:
        resolved = constraint_id or f"autonomy::{module}::{action}"
        text = justification or "autonomy surfaces require declared constraint and reviewable justification"
        self._registry.register(resolved, text)
        return resolved

    def _normalize_sensor_provenance(
        self, provenance: Mapping[str, object] | SensorProvenance | None, *, constraint_id: str
    ) -> SensorProvenance:
        if provenance is None:
            provenance = default_provenance_for_constraint(constraint_id)
        return require_sensor_provenance(provenance)

    def _record_pressure(
        self,
        *,
        constraint_id: str,
        magnitude: float,
        reason: str,
        affective_context: Mapping[str, object],
        blocked: bool,
        provenance: SensorProvenance,
        assumptions: Sequence[str],
        decision_points: Sequence[str],
        environment: Mapping[str, object],
        amplification: Mapping[str, object],
    ) -> Tuple[ConstraintPressureState, Mapping[str, object]]:
        state, _ = self._pressure.record_signal(
            constraint_id,
            magnitude if magnitude > 0 else 0.1,
            reason=reason,
            affective_context=affective_context,
            blocked=blocked,
            provenance=provenance,
            classification="constraint",
            assumptions=assumptions,
            decision_points=decision_points,
            environment_factors=environment,
            amplification_factors=amplification,
        )
        explanation = self._pressure.explain_pressure(constraint_id)
        return state, explanation

    def _pressure_snapshot(
        self, state: ConstraintPressureState, explanation: Mapping[str, object]
    ) -> Mapping[str, object]:
        return {
            "status": state.status(chronic_threshold=1.5, blockage_threshold=3),
            "total_pressure": state.total_pressure,
            "blocked_count": state.blocked_count,
            "sensor_pressure": state.sensor_pressure,
            "pending_engagement": state.pending_engagement_id,
            "causal_explanation": explanation,
            "meta_pressure_flags": sorted(state.meta_pressure_flags),
        }

    def _authority_guard(
        self, details: Mapping[str, object], authority_metadata: Mapping[str, object] | None
    ) -> Mapping[str, object]:
        forbidden_keys = {key for key in details if "permission" in key or "role" in key}
        guard = {
            "status": "isolated" if not forbidden_keys else "blocked",
            "forbidden_keys": sorted(forbidden_keys),
        }
        if forbidden_keys:
            raise ValueError("authority isolation breached: permission-bearing keys in action log payload")
        if authority_metadata:
            guard["metadata"] = dict(authority_metadata)
        return guard


__all__ = ["AutonomyAction", "AutonomyActionLogger"]
