"""Sensor provenance and band-pass calibration contract.

This module defines a mandatory provenance schema for all pressure and affective
signals and provides a bounded, reversible band-pass calibration ledger. The
contract is intentionally explicit: pressure without provenance is invalid, and
calibration changes must emit telemetry rather than silently mutating sensing
behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
import uuid
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Tuple


PROVENANCE_SCHEMA_VERSION = "1.0"
CALIBRATION_SCHEMA_VERSION = "1.0"
SENSOR_FAULT_SCHEMA_VERSION = "1.0"

ALLOWED_ORIGIN_CLASSES = {"environmental", "constraint", "internal_process", "sensor_self"}
ALLOWED_CALIBRATION_STATES = {"nominal", "suspected", "degraded"}
ALLOWED_CLASSIFICATIONS = {"external", "constraint", "sensor"}


@dataclass(frozen=True)
class SensorProvenance:
    sensor_id: str
    origin_class: str
    sensitivity_parameters: Mapping[str, float]
    expected_noise_profile: Mapping[str, float]
    known_failure_modes: Tuple[str, ...]
    calibration_state: str
    schema_version: str = field(default=PROVENANCE_SCHEMA_VERSION)

    def __post_init__(self) -> None:
        if self.origin_class not in ALLOWED_ORIGIN_CLASSES:
            raise ValueError(f"origin_class must be one of {sorted(ALLOWED_ORIGIN_CLASSES)}")
        if self.calibration_state not in ALLOWED_CALIBRATION_STATES:
            raise ValueError(f"calibration_state must be one of {sorted(ALLOWED_CALIBRATION_STATES)}")
        if not isinstance(self.sensor_id, str) or not self.sensor_id.strip():
            raise ValueError("sensor_id is required")
        if not isinstance(self.sensitivity_parameters, Mapping):
            raise ValueError("sensitivity_parameters must be a mapping")
        if not isinstance(self.expected_noise_profile, Mapping):
            raise ValueError("expected_noise_profile must be a mapping")
        if not self.known_failure_modes or not all(isinstance(item, str) for item in self.known_failure_modes):
            raise ValueError("known_failure_modes must be a non-empty collection of strings")

    def to_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sensor_id": self.sensor_id,
            "origin_class": self.origin_class,
            "sensitivity_parameters": dict(self.sensitivity_parameters),
            "expected_noise_profile": dict(self.expected_noise_profile),
            "known_failure_modes": list(self.known_failure_modes),
            "calibration_state": self.calibration_state,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "SensorProvenance":
        if not isinstance(payload, Mapping):
            raise ValueError("sensor provenance payload must be a mapping")
        known_failure_modes = payload.get("known_failure_modes")
        if isinstance(known_failure_modes, str):
            known_failure_modes = (known_failure_modes,)
        elif isinstance(known_failure_modes, Iterable):
            known_failure_modes = tuple(str(item) for item in known_failure_modes)
        else:
            known_failure_modes = ()
        return cls(
            sensor_id=str(payload.get("sensor_id", "")).strip(),
            origin_class=str(payload.get("origin_class", "")).strip(),
            sensitivity_parameters=dict(payload.get("sensitivity_parameters") or {}),
            expected_noise_profile=dict(payload.get("expected_noise_profile") or {}),
            known_failure_modes=known_failure_modes,
            calibration_state=str(payload.get("calibration_state", "")).strip(),
            schema_version=str(payload.get("schema_version", PROVENANCE_SCHEMA_VERSION)),
        )


@dataclass(frozen=True)
class CalibrationAdjustment:
    sensor_id: str
    parameter: str
    new_value: Any
    reason: str
    timestamp: float = field(default_factory=lambda: time.time())
    previous_value: Any | None = None
    reversible_to: Any | None = None
    telemetry: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = field(default=CALIBRATION_SCHEMA_VERSION)

    def __post_init__(self) -> None:
        if not self.telemetry:
            raise ValueError("calibration changes must emit telemetry; none provided")
        if not isinstance(self.parameter, str) or not self.parameter.strip():
            raise ValueError("parameter is required for calibration adjustments")
        if not isinstance(self.sensor_id, str) or not self.sensor_id.strip():
            raise ValueError("sensor_id is required for calibration adjustments")

    def to_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sensor_id": self.sensor_id,
            "parameter": self.parameter,
            "new_value": self.new_value,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "previous_value": self.previous_value,
            "reversible_to": self.reversible_to,
            "telemetry": dict(self.telemetry),
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CalibrationAdjustment":
        if not isinstance(payload, Mapping):
            raise ValueError("calibration adjustment payload must be a mapping")
        return cls(
            sensor_id=str(payload.get("sensor_id", "")).strip(),
            parameter=str(payload.get("parameter", "")).strip(),
            new_value=payload.get("new_value"),
            reason=str(payload.get("reason", "")).strip(),
            timestamp=float(payload.get("timestamp", time.time())),
            previous_value=payload.get("previous_value"),
            reversible_to=payload.get("reversible_to"),
            telemetry=dict(payload.get("telemetry") or {}),
            schema_version=str(payload.get("schema_version", CALIBRATION_SCHEMA_VERSION)),
        )


class BandPassCalibrationEngine:
    """Ledger for reversible band-pass self-calibration.

    The ledger does not change authority or constraint decisions; it only tracks
    sensor hygiene adjustments with explicit telemetry.
    """

    def __init__(self) -> None:
        self._history: Dict[str, list[CalibrationAdjustment]] = {}

    def log_adjustment(
        self,
        provenance: SensorProvenance,
        parameter: str,
        new_value: Any,
        *,
        reason: str,
        telemetry: Mapping[str, Any],
        previous_value: Any | None = None,
    ) -> CalibrationAdjustment:
        adjustment = CalibrationAdjustment(
            sensor_id=provenance.sensor_id,
            parameter=parameter,
            new_value=new_value,
            reason=reason,
            previous_value=previous_value,
            telemetry=dict(telemetry),
        )
        self._history.setdefault(provenance.sensor_id, []).append(adjustment)
        return adjustment

    def revert_last(self, sensor_id: str, *, telemetry: Mapping[str, Any]) -> CalibrationAdjustment:
        history = self._history.get(sensor_id) or []
        if not history:
            raise ValueError("no calibration history to revert")
        last = history[-1]
        reversal = CalibrationAdjustment(
            sensor_id=sensor_id,
            parameter=last.parameter,
            new_value=last.previous_value,
            reason="revert",
            previous_value=last.new_value,
            reversible_to=last.previous_value,
            telemetry=dict(telemetry),
        )
        self._history.setdefault(sensor_id, []).append(reversal)
        return reversal

    def history(self, sensor_id: str) -> Tuple[CalibrationAdjustment, ...]:
        return tuple(self._history.get(sensor_id, ()))


@dataclass(frozen=True)
class SensorFaultRecord:
    fault_id: str
    constraint_id: str
    sensor_id: str
    classification: str
    reason: str
    telemetry: Mapping[str, Any]
    created_at: float = field(default_factory=lambda: time.time())
    schema_version: str = field(default=SENSOR_FAULT_SCHEMA_VERSION)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "fault_id": self.fault_id,
            "constraint_id": self.constraint_id,
            "sensor_id": self.sensor_id,
            "classification": self.classification,
            "reason": self.reason,
            "telemetry": dict(self.telemetry),
            "created_at": self.created_at,
        }

    @classmethod
    def from_signal(cls, constraint_id: str, *, signal: Any, cause: str) -> "SensorFaultRecord":
        provenance = getattr(signal, "provenance", None)
        sensor_id = getattr(provenance, "sensor_id", None) if provenance is not None else None
        classification = getattr(signal, "classification", "sensor")
        telemetry = {
            "magnitude": getattr(signal, "magnitude", None),
            "calibration_notes": getattr(signal, "calibration_notes", {}),
            "timestamp": getattr(signal, "timestamp", time.time()),
        }
        return cls(
            fault_id=uuid.uuid4().hex,
            constraint_id=constraint_id,
            sensor_id=sensor_id or "unknown-sensor",
            classification=str(classification),
            reason=cause,
            telemetry=telemetry,
        )


def require_sensor_provenance(payload: Mapping[str, Any] | SensorProvenance) -> SensorProvenance:
    if isinstance(payload, SensorProvenance):
        return payload
    return SensorProvenance.from_mapping(payload)


def classify_pressure(provenance: SensorProvenance, *, classification: str | None = None) -> str:
    if classification is not None:
        if classification not in ALLOWED_CLASSIFICATIONS:
            raise ValueError(f"classification must be one of {sorted(ALLOWED_CLASSIFICATIONS)}")
        return classification
    mapping = {
        "environmental": "external",
        "constraint": "constraint",
        "internal_process": "sensor",
        "sensor_self": "sensor",
    }
    derived = mapping.get(provenance.origin_class)
    if derived is None:
        raise ValueError("unable to derive classification from provenance")
    return derived


def default_provenance_for_constraint(constraint_id: str) -> SensorProvenance:
    return SensorProvenance(
        sensor_id=f"{constraint_id}-constraint-sensor",
        origin_class="constraint",
        sensitivity_parameters={"gain": 1.0},
        expected_noise_profile={"variance": 0.0},
        known_failure_modes=("duplication",),
        calibration_state="nominal",
    )
