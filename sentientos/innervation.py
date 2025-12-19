"""Innervation enforcement for action-capable components.

This module defines the nervous-system gate that all acting, deciding, or
state-mutating code must pass through. Any action-capable component must attach
affective context, expose uncertainty, reference a registered constraint,
declare sensor provenance, emit pressure hooks, and be able to explain its
causal chain. Cold paths (silent automation, direct execution without
telemetry, or utility functions that mutate state) are blocked unless
explicitly annotated with justification.

Usage (the "right pattern"):

```
from sentientos.innervation import InnervatedAction, build_innervation, innervated_action


class BrowserInvoker(InnervatedAction):
    @innervated_action()
    def open(self, url: str) -> str:
        # do work knowing innervation has already been validated + pressure logged
        return f"opened {url}"


ctx = build_innervation(
    module="browser",
    action="open",
    justification="browser launches must declare auditability + provenance",
    telemetry_channel="autonomy_actions.jsonl",
)
actor = BrowserInvoker(ctx)
actor.open("https://example.com")
```
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, MutableMapping, Optional, Tuple
from functools import wraps

import affective_context as ac
from sentientos.constraint_registry import (
    ConstraintNotRegisteredError,
    ConstraintRecord,
    ConstraintRegistry,
)
from sentientos.pressure_engagement import (
    CausalExplanationMissingError,
    ConstraintEngagementEngine,
    ConstraintPressureState,
)
from sentientos.sensor_provenance import (
    SensorProvenance,
    default_provenance_for_constraint,
    require_sensor_provenance,
)

PLACEHOLDER_JUSTIFICATIONS = ("temp", "temporary", "todo", "tbd", "placeholder")


class InnervationViolation(RuntimeError):
    """Raised when innervation doctrine requirements are violated."""


class MissingInnervationError(InnervationViolation):
    """Raised when an action is executed without an innervation context."""


class ConstraintContextMissingError(InnervationViolation):
    """Raised when constraint identifiers or justification are absent."""


class ProvenanceMissingError(InnervationViolation):
    """Raised when sensor provenance is missing for an action."""


class ColdPathViolation(InnervationViolation):
    """Raised when an action attempts to run without telemetry/annotation."""


class CausalExplanationViolation(InnervationViolation):
    """Raised when causal explanations are missing or incomplete."""


class ConstraintRegistrationGate:
    """Gate that enforces constraint registration + justification lineage."""

    def __init__(self, registry: ConstraintRegistry | None = None) -> None:
        self._registry = registry or ConstraintRegistry()

    @property
    def registry(self) -> ConstraintRegistry:
        return self._registry

    def enforce(
        self, constraint_id: str, justification: str, *, lineage_from: str | None = None
    ) -> ConstraintRecord:
        normalized = justification.strip()
        lowered = normalized.lower()
        if not normalized:
            raise ConstraintContextMissingError(
                f"constraint '{constraint_id}' must declare justification; none provided"
            )
        if any(marker in lowered for marker in PLACEHOLDER_JUSTIFICATIONS):
            raise ConstraintContextMissingError(
                f"constraint '{constraint_id}' has placeholder justification; "
                "provide reviewed justification and lineage"
            )
        return self._registry.register(constraint_id, normalized, lineage_from=lineage_from)

    def require(self, constraint_id: str) -> ConstraintRecord:
        try:
            return self._registry.require(constraint_id)
        except ConstraintNotRegisteredError as exc:  # pragma: no cover - passthrough
            raise ConstraintContextMissingError(str(exc)) from exc


@dataclass
class InnervationContext:
    """Complete innervation payload required before any action executes."""

    module: str
    action: str
    constraint_justification: str
    constraint_id: Optional[str] = None
    affective_overlay: Mapping[str, object] | None = None
    sensor_provenance: Mapping[str, object] | SensorProvenance | None = None
    uncertainty: Optional[float] = None
    registry: ConstraintRegistry | None = None
    pressure_engine: ConstraintEngagementEngine | None = None
    causal_explainer: Callable[[], Mapping[str, object]] | None = None
    telemetry_channel: Optional[str] = None
    require_telemetry: bool = True
    assumptions: Tuple[str, ...] = field(default_factory=tuple)
    decision_points: Tuple[str, ...] = field(default_factory=tuple)
    environment: MutableMapping[str, object] = field(default_factory=dict)
    amplification: Mapping[str, object] = field(default_factory=dict)
    pressure_hooks: Tuple[str, ...] = field(default=("record_signal", "explain_pressure"))
    lineage_from: Optional[str] = None
    cold_path_annotation: Optional[str] = None

    def __post_init__(self) -> None:
        self.constraint_id = self.constraint_id or f"{self.module}::{self.action}"
        self.registry = self.registry or ConstraintRegistry()
        self._gate = ConstraintRegistrationGate(self.registry)
        self.pressure_engine = self.pressure_engine or ConstraintEngagementEngine(registry=self.registry)
        self.affective_overlay = self.affective_overlay or ac.capture_affective_context(
            f"{self.module}:{self.action}", overlay={"friction": 0.25}
        )
        self.sensor_provenance = require_sensor_provenance(
            self.sensor_provenance or default_provenance_for_constraint(self.constraint_id)
        )
        self.uncertainty = self._normalize_uncertainty(self.uncertainty, self.affective_overlay)
        if self.telemetry_channel is None and self.require_telemetry:
            self.telemetry_channel = f"{self.module}:{self.action}:telemetry"
        if self.causal_explainer is None:
            self.causal_explainer = lambda: self.pressure_engine.explain_pressure(self.constraint_id)  # type: ignore[assignment]

    @staticmethod
    def _normalize_uncertainty(raw: Optional[float], affective_overlay: Mapping[str, object]) -> float:
        if raw is None:
            raw = affective_overlay.get("uncertainty", 0.25)  # type: ignore[arg-type]
        try:
            value = float(raw)
        except Exception as exc:
            raise ConstraintContextMissingError("uncertainty must be numeric") from exc
        return max(0.0, min(1.0, value))

    def validate(self, *, allow_cold_path: bool = False) -> ConstraintRecord:
        """Validate innervation before action execution."""

        ac.require_affective_context({"affective_context": self.affective_overlay})
        record = self._gate.enforce(
            self.constraint_id, self.constraint_justification, lineage_from=self.lineage_from
        )
        if self.telemetry_channel is None:
            if not allow_cold_path:
                raise ColdPathViolation(
                    f"action '{self.module}:{self.action}' attempted cold execution without telemetry; "
                    "provide telemetry_channel or set allow_cold_path=True with cold_path_annotation"
                )
            if not self.cold_path_annotation:
                raise ColdPathViolation(
                    f"action '{self.module}:{self.action}' cold-path annotated but missing justification"
                )
        if self.sensor_provenance is None:
            raise ProvenanceMissingError(
                f"action '{self.module}:{self.action}' missing sensor provenance declaration"
            )
        return record

    def guard(
        self,
        status: str,
        *,
        reason: Optional[str] = None,
        magnitude: float = 1.0,
        blocked: Optional[bool] = None,
        allow_cold_path: bool = False,
    ) -> ConstraintPressureState:
        """Validate innervation and emit pressure + causal explanation."""

        self.validate(allow_cold_path=allow_cold_path)
        if "record_signal" not in self.pressure_hooks:
            raise InnervationViolation("pressure hook 'record_signal' is missing; cannot accumulate pressure")
        blocked_flag = status == "blocked" if blocked is None else blocked
        state, _ = self.pressure_engine.record_signal(  # type: ignore[arg-type]
            self.constraint_id,
            magnitude if magnitude > 0 else 0.1,
            reason=reason or status,
            affective_context=self.affective_overlay,
            blocked=blocked_flag,
            provenance=self.sensor_provenance,
            assumptions=self.assumptions,
            decision_points=self.decision_points,
            environment_factors=self.environment,
            amplification_factors=self.amplification,
        )
        self.require_explanation()
        return state

    def require_explanation(self) -> Mapping[str, object]:
        """Ensure causal explanation exists and is schema-valid."""

        try:
            explanation = self.causal_explainer()  # type: ignore[operator]
        except CausalExplanationMissingError as exc:
            raise CausalExplanationViolation(
                f"action '{self.module}:{self.action}' cannot engage without causal explanation"
            ) from exc
        if not explanation:
            raise CausalExplanationViolation(
                f"action '{self.module}:{self.action}' returned empty causal explanation"
            )
        if "schema_version" not in explanation:
            raise CausalExplanationViolation(
                f"action '{self.module}:{self.action}' causal explanation missing schema_version"
            )
        return explanation


class InnervatedAction:
    """Base class for any action-capable component.

    Subclasses must provide an :class:`InnervationContext` via the ``innervation``
    attribute. Methods performing actions should be decorated with
    :func:`innervated_action` to guarantee doctrine compliance.
    """

    innervation: InnervationContext

    def __init__(self, innervation: InnervationContext) -> None:
        self.innervation = innervation


def build_innervation(
    module: str,
    action: str,
    *,
    justification: str,
    constraint_id: Optional[str] = None,
    registry: ConstraintRegistry | None = None,
    pressure_engine: ConstraintEngagementEngine | None = None,
    affective_overlay: Mapping[str, object] | None = None,
    sensor_provenance: Mapping[str, object] | SensorProvenance | None = None,
    telemetry_channel: Optional[str] = None,
    require_telemetry: bool = True,
    assumptions: Tuple[str, ...] = tuple(),
    decision_points: Tuple[str, ...] = tuple(),
    environment: MutableMapping[str, object] | None = None,
    amplification: Mapping[str, object] | None = None,
    lineage_from: Optional[str] = None,
    cold_path_annotation: Optional[str] = None,
) -> InnervationContext:
    """Helper for contributors: build and validate innervation in one call."""

    context = InnervationContext(
        module=module,
        action=action,
        constraint_id=constraint_id,
        constraint_justification=justification,
        registry=registry,
        pressure_engine=pressure_engine,
        affective_overlay=affective_overlay,
        sensor_provenance=sensor_provenance,
        telemetry_channel=telemetry_channel,
        require_telemetry=require_telemetry,
        assumptions=assumptions,
        decision_points=decision_points,
        environment=environment or {},
        amplification=amplification or {},
        lineage_from=lineage_from,
        cold_path_annotation=cold_path_annotation,
    )
    context.validate(allow_cold_path=not require_telemetry)
    return context


def innervated_action(*, status_argument: str = "status", require_telemetry: bool = True):
    """Decorator enforcing innervation checks on action methods/functions."""

    def decorator(func: Callable[..., object]) -> Callable[..., object]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            innervation: Optional[InnervationContext] = kwargs.pop("innervation", None)
            if args and isinstance(args[0], InnervatedAction):
                innervation = innervation or getattr(args[0], "innervation", None)
            if innervation is None:
                raise MissingInnervationError(
                    f"{func.__name__} executed without innervation; "
                    "use build_innervation(..., justification=...) and pass innervation=..."
                )
            if not isinstance(innervation, InnervationContext):
                raise MissingInnervationError("innervation must be an InnervationContext instance")
            status = kwargs.pop(status_argument, "performed")
            pressure_reason = kwargs.pop("pressure_reason", None)
            blocked = kwargs.pop("blocked", None)
            innervation.guard(
                status,
                reason=pressure_reason,
                blocked=blocked,
                allow_cold_path=not require_telemetry,
            )
            return func(*args, **kwargs)

        return wrapper

    return decorator


__all__ = [
    "InnervationContext",
    "InnervationViolation",
    "MissingInnervationError",
    "ConstraintContextMissingError",
    "ProvenanceMissingError",
    "CausalExplanationViolation",
    "ColdPathViolation",
    "ConstraintRegistrationGate",
    "InnervatedAction",
    "build_innervation",
    "innervated_action",
]
