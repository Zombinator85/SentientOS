"""Adaptive load homeostasis and rerouting utilities.

This module treats overload as environmental pressure rather than hostile intent.
It senses saturation, preserves core pathways, and reroutes non-critical work
while emitting causal explanations and telemetry. Permissions and authorities are
never widened; posture changes are reversible and reviewable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

import affective_context as ac

from sentientos.constraint_registry import ConstraintRegistry
from sentientos.pressure_engagement import ConstraintEngagementEngine
from sentientos.sensor_provenance import SensorProvenance


@dataclass(frozen=True)
class LoadMetricSample:
    """Snapshot of environmental load conditions."""

    request_rate: float
    backlog_depth: int
    resource_contention: float
    latency_ms: float
    environmental_notes: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LoadSaturationSensor:
    """Abstracted load/saturation sensor with declared provenance."""

    sensor_id: str
    dimension: str
    baseline: float
    sensitivity: float = 1.0
    noise_variance: float = 0.05

    def provenance(self) -> SensorProvenance:
        return SensorProvenance(
            sensor_id=self.sensor_id,
            origin_class="environmental",
            sensitivity_parameters={"gain": float(self.sensitivity)},
            expected_noise_profile={"variance": float(self.noise_variance)},
            known_failure_modes=(f"{self.dimension}_drift", "sampling_bias"),
            calibration_state="nominal",
        )

    def magnitude(self, observed: float) -> float:
        baseline = max(self.baseline, 1e-6)
        pressure = max(0.0, observed - baseline)
        return round((pressure / baseline) * self.sensitivity, 3)


@dataclass(frozen=True)
class RoutingSubsystem:
    name: str
    criticality: str
    alternates: Tuple[str, ...] = field(default_factory=tuple)
    minimum_bandwidth: float = 0.25

    def is_core(self) -> bool:
        return self.criticality in {"core", "nervous", "review"}


@dataclass
class RerouteDecision:
    allocations: Mapping[str, float]
    rerouted_paths: List[Mapping[str, str]]
    throttled_inputs: List[str]
    telemetry: Mapping[str, object]
    explanation: Mapping[str, object]
    authority_leakage: bool
    core_preserved: bool


class PriorityRoutingGraph:
    """Priority-aware routing graph that preserves core subsystems."""

    def __init__(self, subsystems: Iterable[RoutingSubsystem]):
        self._subsystems: Dict[str, RoutingSubsystem] = {sub.name: sub for sub in subsystems}
        self._priority = {"core": 0, "nervous": 0, "review": 1, "support": 2, "aux": 3}

    @property
    def subsystems(self) -> Mapping[str, RoutingSubsystem]:
        return self._subsystems

    def _sorted_by_priority(self) -> List[RoutingSubsystem]:
        return sorted(
            self._subsystems.values(),
            key=lambda sub: (self._priority.get(sub.criticality, 4), sub.name),
        )

    def minimal_viable_set(self) -> Tuple[str, ...]:
        return tuple(sub.name for sub in self._sorted_by_priority() if sub.is_core())

    def plan(self, pressure_score: float, sample: LoadMetricSample) -> RerouteDecision:
        allocations: Dict[str, float] = {name: 1.0 for name in self._subsystems}
        throttled_inputs: List[str] = []
        rerouted_paths: List[Mapping[str, str]] = []
        pressure_relief = min(0.7, max(0.0, pressure_score) * 0.25)

        telemetry = {
            "pressure_score": pressure_score,
            "sample": {
                "request_rate": sample.request_rate,
                "backlog_depth": sample.backlog_depth,
                "resource_contention": sample.resource_contention,
                "latency_ms": sample.latency_ms,
            },
        }

        if pressure_relief <= 0:
            explanation = {
                "reason": "load nominal; no reroute needed",
                "core_subsystems": self.minimal_viable_set(),
                "relief_factor": pressure_relief,
            }
            return RerouteDecision(
                allocations=allocations,
                rerouted_paths=rerouted_paths,
                throttled_inputs=throttled_inputs,
                telemetry=telemetry,
                explanation=explanation,
                authority_leakage=False,
                core_preserved=True,
            )

        for subsystem in reversed(self._sorted_by_priority()):
            if subsystem.is_core():
                continue
            drop = pressure_relief if subsystem.criticality == "support" else pressure_relief * 1.2
            allocations[subsystem.name] = max(subsystem.minimum_bandwidth, round(1.0 - drop, 3))
            throttled_inputs.append(subsystem.name)
            if subsystem.alternates:
                rerouted_paths.append({"from": subsystem.name, "to": subsystem.alternates[0]})

        core_preserved = all(
            allocations.get(name, 0.0) >= self._subsystems[name].minimum_bandwidth
            for name in self.minimal_viable_set()
        )
        explanation = {
            "reason": "pressure-driven reroute",
            "core_subsystems": self.minimal_viable_set(),
            "relief_factor": pressure_relief,
        }
        return RerouteDecision(
            allocations=allocations,
            rerouted_paths=rerouted_paths,
            throttled_inputs=sorted(set(throttled_inputs)),
            telemetry=telemetry,
            explanation=explanation,
            authority_leakage=False,
            core_preserved=core_preserved,
        )


class LoadSensorSuite:
    """Declarative collection of load/saturation sensors."""

    def __init__(self, *, baselines: Optional[Mapping[str, float]] = None):
        defaults = baselines or {}
        self._sensors: Dict[str, LoadSaturationSensor] = {
            "request_volume": LoadSaturationSensor(
                sensor_id="load:request-volume",
                dimension="request_volume",
                baseline=float(defaults.get("request_rate", 100.0)),
                sensitivity=1.0,
                noise_variance=0.1,
            ),
            "queue_backlog": LoadSaturationSensor(
                sensor_id="load:queue-backlog",
                dimension="queue_backlog",
                baseline=float(defaults.get("backlog_depth", 25.0)),
                sensitivity=0.8,
                noise_variance=0.12,
            ),
            "resource_contention": LoadSaturationSensor(
                sensor_id="load:resource-contention",
                dimension="resource_contention",
                baseline=float(defaults.get("resource_contention", 0.35)),
                sensitivity=1.2,
                noise_variance=0.08,
            ),
            "timing_anomaly": LoadSaturationSensor(
                sensor_id="load:timing-anomaly",
                dimension="timing_anomaly",
                baseline=float(defaults.get("latency_ms", 250.0)),
                sensitivity=1.1,
                noise_variance=0.15,
            ),
        }

    def sensors(self) -> Mapping[str, LoadSaturationSensor]:
        return self._sensors

    def readings(self, sample: LoadMetricSample) -> Iterable[Tuple[str, LoadSaturationSensor, float, Mapping[str, object]]]:
        metrics = {
            "request_volume": sample.request_rate,
            "queue_backlog": float(sample.backlog_depth),
            "resource_contention": sample.resource_contention,
            "timing_anomaly": sample.latency_ms,
        }
        for dimension, observed in metrics.items():
            sensor = self._sensors[dimension]
            magnitude = sensor.magnitude(observed)
            env = {
                "dimension": dimension,
                "observed": observed,
                "baseline": sensor.baseline,
                "environmental_notes": dict(sample.environmental_notes),
            }
            yield dimension, sensor, magnitude, env


class LoadHomeostasisController:
    """Adaptive reroute reflex that remains explainable and reviewable."""

    def __init__(
        self,
        *,
        constraint_id: str = "runtime::load-homeostasis",
        registry: ConstraintRegistry | None = None,
        engagement_engine: ConstraintEngagementEngine | None = None,
        baselines: Optional[Mapping[str, float]] = None,
        routing_graph: PriorityRoutingGraph | None = None,
    ) -> None:
        self._registry = registry or ConstraintRegistry()
        self._constraint_id = constraint_id
        self._pressure = engagement_engine or ConstraintEngagementEngine(registry=self._registry)
        self._sensors = LoadSensorSuite(baselines=baselines)
        self._routing = routing_graph or PriorityRoutingGraph(
            [
                RoutingSubsystem("nervous-system", "core", minimum_bandwidth=0.4),
                RoutingSubsystem("logging", "review", minimum_bandwidth=0.3),
                RoutingSubsystem("explanation", "review", minimum_bandwidth=0.3),
                RoutingSubsystem("analytics", "support", alternates=("analytics-deferred",), minimum_bandwidth=0.2),
                RoutingSubsystem("notifications", "aux", alternates=("notifications-batch",), minimum_bandwidth=0.15),
            ]
        )

    @property
    def pressure_engine(self) -> ConstraintEngagementEngine:
        return self._pressure

    @property
    def routing_graph(self) -> PriorityRoutingGraph:
        return self._routing

    def handle_load(self, sample: LoadMetricSample) -> Mapping[str, object]:
        signals_recorded: List[Mapping[str, object]] = []
        magnitudes: List[float] = []
        for dimension, sensor, magnitude, env in self._sensors.readings(sample):
            context = ac.capture_affective_context(
                f"load:{dimension}", overlay={"friction": min(1.0, magnitude), "uncertainty": 0.15}
            )
            state, engagement = self._pressure.record_signal(
                self._constraint_id,
                magnitude=magnitude,
                reason=f"{dimension}_pressure",
                affective_context=context,
                blocked=False,
                provenance=sensor.provenance(),
                classification="external",
                environment_factors=env,
            )
            signals_recorded.append(
                {
                    "dimension": dimension,
                    "magnitude": magnitude,
                    "engagement_issued": engagement.engagement_id if engagement else None,
                }
            )
            magnitudes.append(magnitude)

        pressure_snapshot = self._pressure.explain_pressure(self._constraint_id)
        momentary_pressure = round(sum(magnitudes) / len(magnitudes), 3) if magnitudes else 0.0
        routing = self._routing.plan(momentary_pressure, sample)
        affective_overlay = ac.capture_affective_context(
            "load:reroute", overlay={"friction": min(1.0, momentary_pressure), "uncertainty": 0.2}
        )
        explanation = {
            "pressure": pressure_snapshot,
            "routing": routing.explanation,
            "affective_overlay": affective_overlay,
            "signals": signals_recorded,
        }
        telemetry = {
            "authority_leakage": routing.authority_leakage,
            "core_preserved": routing.core_preserved,
            "allocations": routing.allocations,
            "rerouted_paths": routing.rerouted_paths,
            "throttled_inputs": routing.throttled_inputs,
        }
        return {
            "pressure_score": momentary_pressure,
            "routing": telemetry,
            "explanation": explanation,
        }

