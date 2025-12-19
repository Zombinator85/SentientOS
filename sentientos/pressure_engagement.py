"""Pressure-to-stitch engagement engine.

This module accumulates pressure signals against constraints and forces explicit
engagement records ("stitches") once thresholds are crossed. It is intentionally
deterministic and does not alter policy or permission outcomes; it only
annotates review flow and telemetry.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import time
import uuid
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Set, Tuple

import affective_context as ac
from sentientos.constraint_registry import ConstraintRegistry
from sentientos.sensor_provenance import (
    BandPassCalibrationEngine,
    CalibrationAdjustment,
    SensorFaultRecord,
    SensorProvenance,
    classify_pressure,
    default_provenance_for_constraint,
    require_sensor_provenance,
)

PRESSURE_SCHEMA_VERSION = "2.0"
ENGAGEMENT_SCHEMA_VERSION = "1.1"
CAUSAL_GRAPH_SCHEMA_VERSION = "1.0"
CAUSAL_EXPLANATION_SCHEMA_VERSION = "1.0"


class PressureDecayError(RuntimeError):
    """Raised when decay is attempted without review."""


class EngagementRequiredError(RuntimeError):
    """Raised when chronic pressure is vented without an engagement."""


class CausalExplanationMissingError(RuntimeError):
    """Raised when a causal explanation cannot be produced for pressure."""


@dataclass(frozen=True)
class CausalNode:
    node_id: str
    kind: str
    label: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, object]:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "label": self.label,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CausalEdge:
    source: str
    target: str
    relation: str

    def to_payload(self) -> Dict[str, object]:
        return {"source": self.source, "target": self.target, "relation": self.relation}


@dataclass
class PressureCausalGraph:
    schema_version: str = CAUSAL_GRAPH_SCHEMA_VERSION
    nodes: Dict[str, CausalNode] = field(default_factory=dict)
    edges: List[CausalEdge] = field(default_factory=list)

    def ensure_node(self, node: CausalNode) -> None:
        self.nodes.setdefault(node.node_id, node)

    def connect(self, source: str, target: str, relation: str) -> None:
        if source not in self.nodes or target not in self.nodes:
            raise ValueError("source and target must exist before creating an edge")
        edge = CausalEdge(source=source, target=target, relation=relation)
        if edge not in self.edges:
            self.edges.append(edge)

    def root_nodes(self) -> Tuple[str, ...]:
        targets = {edge.target for edge in self.edges}
        return tuple(sorted(node_id for node_id in self.nodes if node_id not in targets))

    def to_payload(self) -> Dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "nodes": [node.to_payload() for node in sorted(self.nodes.values(), key=lambda n: n.node_id)],
            "edges": [edge.to_payload() for edge in sorted(self.edges, key=lambda e: (e.source, e.target, e.relation))],
            "root_nodes": list(self.root_nodes()),
        }


@dataclass(frozen=True)
class PressureSignal:
    signal_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    constraint_id: str
    magnitude: float
    reason: str
    affective_context: Mapping[str, float]
    blocked: bool
    classification: str
    provenance: SensorProvenance
    calibration_notes: Mapping[str, object]
    calibration_adjustments: Tuple[CalibrationAdjustment, ...]
    assumptions: Tuple[str, ...] = field(default_factory=tuple)
    decision_points: Tuple[str, ...] = field(default_factory=tuple)
    environment_factors: Mapping[str, object] = field(default_factory=dict)
    amplification_factors: Mapping[str, object] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: time.time())

    def to_payload(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["schema_version"] = PRESSURE_SCHEMA_VERSION
        payload["affective_context"] = dict(self.affective_context)
        payload["provenance"] = self.provenance.to_payload()
        payload["calibration_notes"] = dict(self.calibration_notes)
        payload["calibration_adjustments"] = [adj.to_payload() for adj in self.calibration_adjustments]
        return payload


@dataclass
class ConstraintPressureState:
    constraint_id: str
    signals: List[PressureSignal] = field(default_factory=list)
    total_pressure: float = 0.0
    sensor_pressure: float = 0.0
    blocked_count: int = 0
    pending_engagement_id: Optional[str] = None
    defer_until: Optional[float] = None
    last_reviewed_at: Optional[float] = None
    ignored_reason: Optional[str] = None
    classification_tally: Dict[str, int] = field(default_factory=dict)
    last_decision: Optional[str] = None
    meta_pressure_flags: Set[str] = field(default_factory=set)
    causal_graph: PressureCausalGraph = field(default_factory=PressureCausalGraph)
    signal_counter: int = 0
    last_explanation_signature: Optional[str] = None
    last_explanation_node_count: int = 0
    explanation_repeat_count: int = 0
    modeling_debt_flags: Set[str] = field(default_factory=set)

    def record(self, signal: PressureSignal, *, max_signals: int) -> None:
        self.signals.append(signal)
        if len(self.signals) > max_signals:
            del self.signals[:-max_signals]
        if signal.classification == "sensor":
            self.sensor_pressure += max(0.0, float(signal.magnitude))
        else:
            self.total_pressure += max(0.0, float(signal.magnitude))
        if signal.blocked:
            self.blocked_count += 1
        self.classification_tally[signal.classification] = self.classification_tally.get(
            signal.classification, 0
        ) + 1

    def status(self, *, chronic_threshold: float, blockage_threshold: int) -> str:
        if self.ignored_reason:
            return "ignored"
        if self.total_pressure <= 0:
            return "resolved"
        if self.total_pressure >= chronic_threshold or self.blocked_count >= blockage_threshold:
            return "chronic"
        return "transient"

    def reset(self) -> None:
        self.signals.clear()
        self.total_pressure = 0.0
        self.sensor_pressure = 0.0
        self.blocked_count = 0
        self.pending_engagement_id = None
        self.defer_until = None
        self.last_reviewed_at = time.time()
        self.ignored_reason = None
        self.classification_tally.clear()
        self.meta_pressure_flags.clear()
        self.causal_graph = PressureCausalGraph()
        self.signal_counter = 0
        self.last_explanation_signature = None
        self.last_explanation_node_count = 0
        self.explanation_repeat_count = 0
        self.modeling_debt_flags.clear()

    def require_review(self, *, now: float, chronic_threshold: float, blockage_threshold: int) -> bool:
        if self.status(chronic_threshold=chronic_threshold, blockage_threshold=blockage_threshold) != "chronic":
            return False
        if self.pending_engagement_id is None:
            return True
        if self.defer_until is None:
            return False
        return self.defer_until <= now


@dataclass(frozen=True)
class ConstraintEngagementRecord:
    engagement_id: str
    constraint_id: str
    decision: str
    justification: str
    created_at: float
    signals: Tuple[PressureSignal, ...]
    affective_context_summary: Mapping[str, float]
    reviewer: Optional[str] = None
    defer_until: Optional[float] = None
    lineage_from: Optional[str] = None
    provenance_summary: Mapping[str, object] = field(default_factory=dict)
    causal_explanation: Mapping[str, object] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, object]:
        payload = {
            "schema_version": ENGAGEMENT_SCHEMA_VERSION,
            "engagement_id": self.engagement_id,
            "constraint_id": self.constraint_id,
            "decision": self.decision,
            "justification": self.justification,
            "created_at": self.created_at,
            "signals": [signal.to_payload() for signal in self.signals],
            "affective_context_summary": dict(self.affective_context_summary),
            "reviewer": self.reviewer,
            "defer_until": self.defer_until,
            "lineage_from": self.lineage_from,
            "provenance_summary": dict(self.provenance_summary),
            "causal_explanation": dict(self.causal_explanation),
        }
        payload["pressure_score"] = self.pressure_score
        return payload

    @property
    def pressure_score(self) -> float:
        if not self.signals:
            return 0.0
        return round(sum(sig.magnitude for sig in self.signals) / len(self.signals), 3)


class ConstraintEngagementEngine:
    """Accumulate pressure and require engagements when limits are crossed."""

    def __init__(
        self,
        *,
        chronic_threshold: float = 1.5,
        blockage_threshold: int = 3,
        max_signals: int = 25,
        default_defer_seconds: float = 90.0,
        registry: Optional[ConstraintRegistry] = None,
    ) -> None:
        self._states: Dict[str, ConstraintPressureState] = {}
        self._engagements: Dict[str, List[ConstraintEngagementRecord]] = {}
        self._chronic_threshold = max(0.1, float(chronic_threshold))
        self._blockage_threshold = max(1, int(blockage_threshold))
        self._max_signals = max(1, int(max_signals))
        self._default_defer_seconds = float(default_defer_seconds)
        self._registry = registry
        self._calibration = BandPassCalibrationEngine()
        self._sensor_faults: List[SensorFaultRecord] = []

    def pressure_state(self, constraint_id: str) -> ConstraintPressureState:
        return self._states.setdefault(constraint_id, ConstraintPressureState(constraint_id))

    def record_signal(
        self,
        constraint_id: str,
        magnitude: float,
        *,
        reason: str,
        affective_context: Mapping[str, object],
        blocked: bool = True,
        provenance: Mapping[str, object] | SensorProvenance | None = None,
        classification: Optional[str] = None,
        calibration_notes: Optional[Mapping[str, object]] = None,
        calibration_adjustments: Tuple[CalibrationAdjustment, ...] | None = None,
        assumptions: Iterable[Mapping[str, object] | str] | None = None,
        decision_points: Iterable[str] | None = None,
        environment_factors: Mapping[str, object] | None = None,
        amplification_factors: Mapping[str, object] | None = None,
    ) -> Tuple[ConstraintPressureState, Optional[ConstraintEngagementRecord]]:
        if provenance is None:
            raise ValueError("sensor provenance is required for pressure signals")
        normalized_context = self._normalize_affective_context(affective_context)
        self._require_registered(constraint_id)
        ac.require_affective_context({"affective_context": normalized_context})
        vector = normalized_context.get("vector", {}) if isinstance(normalized_context, Mapping) else {}
        resolved_provenance = require_sensor_provenance(provenance)
        resolved_classification = classify_pressure(resolved_provenance, classification=classification)
        bandpass_notes, adjusted_magnitude = self._apply_bandpass(
            resolved_provenance, magnitude=magnitude, calibration_notes=calibration_notes or {}
        )
        state = self.pressure_state(constraint_id)
        state.signal_counter += 1
        signal = PressureSignal(
            signal_id=f"{constraint_id}#signal-{state.signal_counter}",
            constraint_id=constraint_id,
            magnitude=max(0.0, float(adjusted_magnitude)),
            reason=reason,
            affective_context=vector,
            blocked=blocked,
            classification=resolved_classification,
            provenance=resolved_provenance,
            calibration_notes=bandpass_notes,
            calibration_adjustments=calibration_adjustments or tuple(),
            assumptions=self._normalize_assumptions(assumptions),
            decision_points=tuple(decision_points or ()),
            environment_factors=self._normalize_environment_factors(environment_factors),
            amplification_factors=self._normalize_amplification(amplification_factors, resolved_classification),
        )
        state.record(signal, max_signals=self._max_signals)
        self._detect_meta_pressure(state, signal)
        self._update_causal_graph(
            state,
            signal=signal,
            assumptions=signal.assumptions,
            decision_points=signal.decision_points,
            environment_factors=signal.environment_factors,
            amplification_factors=signal.amplification_factors,
        )
        if resolved_classification == "sensor" or state.meta_pressure_flags:
            self._register_sensor_fault(constraint_id, signal, cause="sensor_pressure")
            return state, None

        now = time.time()
        engagement: Optional[ConstraintEngagementRecord] = None
        if state.require_review(
            now=now, chronic_threshold=self._chronic_threshold, blockage_threshold=self._blockage_threshold
        ):
            engagement = self._defer_engagement(state, now=now)
            self._register_engagement(engagement)
        return state, engagement

    def mark_ignored(self, constraint_id: str, *, reason: str) -> ConstraintPressureState:
        self._require_registered(constraint_id)
        state = self.pressure_state(constraint_id)
        state.ignored_reason = reason
        return state

    def record_policy_event(
        self,
        event: Mapping[str, object],
        actions: Iterable[Mapping[str, object]],
        affective_overlay: Mapping[str, object],
    ) -> List[ConstraintEngagementRecord]:
        normalized_overlay = self._normalize_affective_context(affective_overlay)
        ac.require_affective_context({"affective_context": normalized_overlay})
        signals = list(self._extract_policy_signals(event, actions))
        engagements: List[ConstraintEngagementRecord] = []
        for signal in signals:
            _, engagement = self.record_signal(
                signal["constraint_id"],
                signal.get("magnitude", 1.0),
                reason=signal.get("reason", "constraint blocked"),
                affective_context=normalized_overlay,
                blocked=signal.get("blocked", True),
                provenance=signal.get("provenance")
                or default_provenance_for_constraint(signal["constraint_id"]),
                classification=signal.get("classification"),
            )
            if engagement is not None:
                engagements.append(engagement)
        return engagements

    def reaffirm(
        self,
        constraint_id: str,
        *,
        decision: str,
        justification: str,
        reviewer: Optional[str] = None,
        defer_seconds: Optional[float] = None,
        lineage_from: Optional[str] = None,
    ) -> ConstraintEngagementRecord:
        if decision not in {"reaffirm", "modify", "sunset", "defer"}:
            raise ValueError("decision must be reaffirm|modify|sunset|defer")
        if decision == "defer" and defer_seconds is None:
            raise ValueError("defer requires an expiry")

        state = self.pressure_state(constraint_id)
        now = time.time()
        defer_until = None
        if decision == "defer":
            defer_until = now + float(defer_seconds)
        record = self._create_engagement_record(
            constraint_id=constraint_id,
            decision=decision,
            justification=justification,
            reviewer=reviewer,
            signals=tuple(state.signals),
            defer_until=defer_until,
            lineage_from=lineage_from or state.pending_engagement_id,
        )
        self._engagements.setdefault(constraint_id, []).append(record)
        self._register_engagement(record)
        if decision == "defer":
            state.pending_engagement_id = record.engagement_id
            state.defer_until = defer_until
        else:
            state.reset()
        state.last_reviewed_at = now
        state.last_decision = decision
        return record

    def decay_pressure(self, constraint_id: str) -> None:
        state = self.pressure_state(constraint_id)
        if not state.last_reviewed_at:
            raise PressureDecayError("pressure cannot decay without review")
        state.reset()

    def _extract_policy_signals(
        self, event: Mapping[str, object], actions: Iterable[Mapping[str, object]]
    ) -> Iterable[MutableMapping[str, object]]:
        pressure_signals = event.get("pressure_signals")
        if isinstance(pressure_signals, list):
            for entry in pressure_signals:
                if isinstance(entry, Mapping) and entry.get("constraint_id"):
                    yield dict(entry)

        blocked = event.get("blocked_constraint")
        if isinstance(blocked, str):
            yield {"constraint_id": blocked, "blocked": True, "reason": "blocked", "magnitude": 1.0}

        blocked_constraints = event.get("blocked_constraints")
        if isinstance(blocked_constraints, list):
            for constraint in blocked_constraints:
                if isinstance(constraint, str):
                    yield {"constraint_id": constraint, "blocked": True, "reason": "blocked", "magnitude": 1.0}

        if not any(actions) and event.get("constraint_id"):
            yield {
                "constraint_id": str(event.get("constraint_id")),
                "blocked": True,
                "reason": "policy denied actions",
                "magnitude": 1.0,
            }

    def _defer_engagement(
        self, state: ConstraintPressureState, *, now: float
    ) -> ConstraintEngagementRecord:
        record = self._create_engagement_record(
            constraint_id=state.constraint_id,
            decision="defer",
            justification="pressure threshold reached; review required",
            reviewer=None,
            signals=tuple(state.signals),
            defer_until=now + self._default_defer_seconds,
            lineage_from=state.pending_engagement_id,
        )
        self._engagements.setdefault(state.constraint_id, []).append(record)
        self._register_engagement(record)
        state.pending_engagement_id = record.engagement_id
        state.defer_until = record.defer_until
        return record

    def _create_engagement_record(
        self,
        *,
        constraint_id: str,
        decision: str,
        justification: str,
        reviewer: Optional[str],
        signals: Tuple[PressureSignal, ...],
        defer_until: Optional[float],
        lineage_from: Optional[str],
    ) -> ConstraintEngagementRecord:
        summary = self._summarize_affective_context(signals)
        engagement_id = uuid.uuid4().hex
        provenance_summary = self._summarize_provenance(signals)
        causal_explanation = self.explain_pressure(constraint_id)
        return ConstraintEngagementRecord(
            engagement_id=engagement_id,
            constraint_id=constraint_id,
            decision=decision,
            justification=justification,
            created_at=time.time(),
            signals=signals,
            affective_context_summary=summary,
            reviewer=reviewer,
            defer_until=defer_until,
            lineage_from=lineage_from,
            provenance_summary=provenance_summary,
            causal_explanation=causal_explanation,
        )

    def _summarize_affective_context(self, signals: Tuple[PressureSignal, ...]) -> Mapping[str, float]:
        if not signals:
            return {}
        accumulator: Dict[str, float] = {}
        for signal in signals:
            for key, value in signal.affective_context.items():
                accumulator[key] = accumulator.get(key, 0.0) + float(value)
        return {key: round(value / len(signals), 3) for key, value in accumulator.items()}

    def _summarize_provenance(self, signals: Tuple[PressureSignal, ...]) -> Mapping[str, object]:
        if not signals:
            return {}
        classification_counts: Dict[str, int] = {}
        sensors: Set[str] = set()
        calibration_events = 0
        for signal in signals:
            classification_counts[signal.classification] = classification_counts.get(signal.classification, 0) + 1
            sensors.add(signal.provenance.sensor_id)
            calibration_events += len(signal.calibration_adjustments)
        return {
            "classifications": classification_counts,
            "sensors": sorted(sensors),
            "calibration_events": calibration_events,
        }

    @property
    def engagements(self) -> Tuple[ConstraintEngagementRecord, ...]:
        return tuple(record for records in self._engagements.values() for record in records)

    @property
    def sensor_faults(self) -> Tuple[SensorFaultRecord, ...]:
        return tuple(self._sensor_faults)

    def _require_registered(self, constraint_id: str) -> None:
        if self._registry is None:
            return
        self._registry.require(constraint_id)

    def _register_engagement(self, engagement: ConstraintEngagementRecord) -> None:
        if self._registry is None:
            return
        self._registry.record_engagement(engagement)

    def _normalize_affective_context(self, context: Mapping[str, object]) -> Mapping[str, object]:
        if isinstance(context, Mapping) and "version" in context and "vector" in context:
            return context
        overlay = context if isinstance(context, Mapping) else {}
        return ac.capture_affective_context("constraint-pressure", overlay=overlay)

    def _apply_bandpass(
        self,
        provenance: SensorProvenance,
        *,
        magnitude: float,
        calibration_notes: Mapping[str, object],
    ) -> Tuple[Mapping[str, object], float]:
        notes: Dict[str, object] = dict(calibration_notes)
        gain = float(provenance.sensitivity_parameters.get("gain", 1.0))
        bounded_gain = max(0.5, min(gain, 3.0))
        if bounded_gain != gain:
            notes["gain_clamped"] = {"requested": gain, "applied": bounded_gain}
        adjusted_magnitude = magnitude * bounded_gain
        expected_variance = float(provenance.expected_noise_profile.get("variance", 0.0))
        if adjusted_magnitude > 0 and expected_variance and adjusted_magnitude > expected_variance * 4:
            notes.setdefault("variance_flags", []).append("high_variance")
        return notes, adjusted_magnitude

    def _detect_meta_pressure(self, state: ConstraintPressureState, signal: PressureSignal) -> None:
        if state.last_decision == "reaffirm":
            state.meta_pressure_flags.add("meta_pressure_reaffirmed_constraint")
        if signal.magnitude < 0.5 and not signal.blocked:
            state.meta_pressure_flags.add("meta_pressure_low_impact")
        if signal.classification == "sensor" and signal.magnitude > 0:
            state.meta_pressure_flags.add("meta_pressure_sensor_only")
        if signal.assumptions:
            deprecated = [item for item in signal.assumptions if item.endswith("[deprecated]")]
            if deprecated:
                state.modeling_debt_flags.add("deprecated_assumptions_in_causal_chain")
                state.meta_pressure_flags.add("meta_pressure_deprecated_assumption")

    def _register_sensor_fault(self, constraint_id: str, signal: PressureSignal, *, cause: str) -> None:
        fault = SensorFaultRecord.from_signal(constraint_id, signal=signal, cause=cause)
        self._sensor_faults.append(fault)

    def adjust_bandpass(
        self,
        provenance: SensorProvenance,
        parameter: str,
        new_value: object,
        *,
        reason: str,
        telemetry: Mapping[str, object],
        previous_value: object | None = None,
    ) -> CalibrationAdjustment:
        adjustment = self._calibration.log_adjustment(
            provenance=provenance,
            parameter=parameter,
            new_value=new_value,
            reason=reason,
            telemetry=telemetry,
            previous_value=previous_value,
        )
        return adjustment

    def _normalize_assumptions(self, assumptions: Iterable[Mapping[str, object] | str] | None) -> Tuple[str, ...]:
        normalized: List[str] = []
        if assumptions is None:
            return tuple()
        for item in assumptions:
            if isinstance(item, Mapping):
                desc = str(item.get("description") or item.get("assumption") or "").strip()
                deprecated = item.get("deprecated") is True
                label = f"{desc} [deprecated]" if deprecated else desc
                if label:
                    normalized.append(label)
            else:
                label = str(item).strip()
                if label:
                    normalized.append(label)
        return tuple(normalized)

    def _normalize_environment_factors(self, environment_factors: Mapping[str, object] | None) -> Mapping[str, object]:
        if environment_factors is None:
            return {}
        return {str(key): value for key, value in environment_factors.items()}

    def _normalize_amplification(
        self, amplification_factors: Mapping[str, object] | None, classification: str
    ) -> Mapping[str, object]:
        factors: Dict[str, object] = {"classification_origin": classification}
        if amplification_factors:
            for key, value in amplification_factors.items():
                factors[str(key)] = value
        return factors

    def _update_causal_graph(
        self,
        state: ConstraintPressureState,
        *,
        signal: PressureSignal,
        assumptions: Tuple[str, ...],
        decision_points: Tuple[str, ...],
        environment_factors: Mapping[str, object],
        amplification_factors: Mapping[str, object],
    ) -> None:
        graph = state.causal_graph
        constraint_node = CausalNode(node_id=f"constraint:{state.constraint_id}", kind="constraint", label=state.constraint_id)
        signal_node = CausalNode(
            node_id=f"signal:{signal.signal_id}",
            kind="signal",
            label=signal.reason,
            metadata={
                "magnitude": signal.magnitude,
                "classification": signal.classification,
                "blocked": signal.blocked,
                "sensor_id": signal.provenance.sensor_id,
                "calibration_state": signal.provenance.calibration_state,
                "calibration_notes": dict(signal.calibration_notes),
            },
        )
        graph.ensure_node(constraint_node)
        graph.ensure_node(signal_node)
        graph.connect(signal_node.node_id, constraint_node.node_id, "pressurizes")

        sensor_node = CausalNode(
            node_id=f"sensor:{signal.provenance.sensor_id}",
            kind="sensor",
            label=signal.provenance.sensor_id,
            metadata={
                "origin_class": signal.provenance.origin_class,
                "calibration_state": signal.provenance.calibration_state,
                "expected_noise_profile": dict(signal.provenance.expected_noise_profile),
            },
        )
        graph.ensure_node(sensor_node)
        graph.connect(sensor_node.node_id, signal_node.node_id, "originates")

        for assumption in assumptions:
            node = CausalNode(
                node_id=f"assumption:{assumption}",
                kind="assumption",
                label=assumption,
            )
            graph.ensure_node(node)
            graph.connect(node.node_id, signal_node.node_id, "assumes")

        for point in decision_points:
            node = CausalNode(node_id=f"decision:{point}", kind="decision", label=point)
            graph.ensure_node(node)
            graph.connect(node.node_id, signal_node.node_id, "decision-block")

        for key, value in environment_factors.items():
            node = CausalNode(
                node_id=f"environment:{key}",
                kind="environment",
                label=key,
                metadata={"value": value},
            )
            graph.ensure_node(node)
            graph.connect(node.node_id, signal_node.node_id, "environmental-pressure")

        for key, value in amplification_factors.items():
            node = CausalNode(
                node_id=f"amplification:{key}",
                kind="amplification",
                label=key,
                metadata={"factor": value},
            )
            graph.ensure_node(node)
            graph.connect(node.node_id, signal_node.node_id, "amplifies")

    def explain_pressure(self, constraint_id: str) -> Mapping[str, object]:
        state = self.pressure_state(constraint_id)
        if not state.signals or not state.causal_graph.nodes:
            raise CausalExplanationMissingError("pressure cannot be engaged without causal explanation")
        graph_payload = state.causal_graph.to_payload()
        sensor_states = {
            signal.provenance.sensor_id: signal.provenance.calibration_state for signal in state.signals
        }
        multiple_chains = len(set(signal.signal_id for signal in state.signals)) > 1
        uncertainty_flags = set()
        if multiple_chains:
            uncertainty_flags.add("multiple_signal_chains")
        if any(signal.classification == "external" for signal in state.signals):
            uncertainty_flags.add("environmental_uncertainty")
        narrative_signals = [
            {
                "signal_id": signal.signal_id,
                "reason": signal.reason,
                "magnitude": signal.magnitude,
                "classification": signal.classification,
                "assumptions": list(signal.assumptions),
                "decision_points": list(signal.decision_points),
                "environment_factors": dict(signal.environment_factors),
                "amplification_factors": dict(signal.amplification_factors),
                "sensor_calibration_state": signal.provenance.calibration_state,
            }
            for signal in state.signals
        ]
        explanation = {
            "schema_version": CAUSAL_EXPLANATION_SCHEMA_VERSION,
            "constraint_id": constraint_id,
            "status": state.status(chronic_threshold=self._chronic_threshold, blockage_threshold=self._blockage_threshold),
            "pressure_score": state.total_pressure,
            "causal_graph": graph_payload,
            "narrative": {
                "constraints": [constraint_id],
                "assumptions": sorted({assumption for signal in state.signals for assumption in signal.assumptions}),
                "decision_points": sorted({point for signal in state.signals for point in signal.decision_points}),
                "environmental_factors": sorted(
                    {key for signal in state.signals for key in signal.environment_factors.keys()}
                ),
                "amplification_factors": {
                    "sensor": [key for key, value in state.signals[-1].amplification_factors.items() if key != "classification_origin"],
                    "classification_origin": state.signals[-1].amplification_factors.get("classification_origin"),
                },
                "triggering_signals": narrative_signals,
                "sensor_states": sensor_states,
                "uncertainty_flags": sorted(uncertainty_flags),
                "multiple_chains": multiple_chains,
            },
            "meta_pressure_flags": sorted(state.meta_pressure_flags),
        }
        signature = self._explanation_signature(explanation)
        if state.last_explanation_signature == signature:
            state.explanation_repeat_count += 1
            state.modeling_debt_flags.add("explanation_repeat_without_new_structure")
            state.meta_pressure_flags.add("meta_pressure_modeling_debt_repeat")
        elif state.last_explanation_signature:
            if len(graph_payload["nodes"]) > state.last_explanation_node_count:
                state.modeling_debt_flags.add("explanation_growth_without_resolution")
                state.meta_pressure_flags.add("meta_pressure_explanation_growth")
        if any(node["label"].endswith("[deprecated]") for node in graph_payload["nodes"] if node["kind"] == "assumption"):
            state.modeling_debt_flags.add("deprecated_assumptions_in_causal_chain")
        explanation["modeling_debt_flags"] = sorted(state.modeling_debt_flags)
        explanation["explanation_signature"] = signature
        state.last_explanation_signature = signature
        state.last_explanation_node_count = len(graph_payload["nodes"])
        return explanation

    def _explanation_signature(self, payload: Mapping[str, object]) -> str:
        stable = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]
