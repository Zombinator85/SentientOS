from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from sentientos.memory_economics import MemoryClass


class SignalDirection(str, Enum):
    INGRESS = "INGRESS"
    EGRESS = "EGRESS"


class SignalType(str, Enum):
    SENSOR_EVENT = "SENSOR_EVENT"
    USER_INPUT = "USER_INPUT"
    ENVIRONMENTAL_STATE = "ENVIRONMENTAL_STATE"
    SYSTEM_FEEDBACK = "SYSTEM_FEEDBACK"
    ADVISORY_SIGNAL = "ADVISORY_SIGNAL"
    STATUS_REPORT = "STATUS_REPORT"
    REQUEST_FOR_ACTION = "REQUEST_FOR_ACTION"
    SIMULATED_ACTUATION = "SIMULATED_ACTUATION"


@dataclass(frozen=True)
class SignalDefinition:
    allowed_fields: tuple[str, ...]
    max_frequency_hz: float
    memory_class: MemoryClass
    budget_cost: int
    redaction_rules: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed_fields": list(self.allowed_fields),
            "max_frequency_hz": self.max_frequency_hz,
            "memory_class": self.memory_class.value,
            "budget_cost": self.budget_cost,
            "redaction_rules": list(self.redaction_rules),
        }


@dataclass(frozen=True)
class EmbodimentContract:
    contract_id: str
    direction: SignalDirection
    signal_type: SignalType
    allowed_contexts: tuple[str, ...]
    forbidden_contexts: tuple[str, ...]
    budget_cost: int
    simulation_only: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_id": self.contract_id,
            "direction": self.direction.value,
            "signal_type": self.signal_type.value,
            "allowed_contexts": list(self.allowed_contexts),
            "forbidden_contexts": list(self.forbidden_contexts),
            "budget_cost": self.budget_cost,
            "simulation_only": self.simulation_only,
        }


_DEFAULT_ALLOWED_CONTEXTS = ("simulation", "cli", "test")
_DEFAULT_FORBIDDEN_CONTEXTS = (
    "cognition",
    "recovery",
    "autonomy",
    "actuation",
    "control",
    "daemon",
)

_SIGNAL_DEFINITIONS: dict[SignalType, SignalDefinition] = {
    SignalType.SENSOR_EVENT: SignalDefinition(
        allowed_fields=(
            "sensor_id",
            "value",
            "unit",
            "confidence",
            "timestamp",
            "metadata",
            "frequency_hz",
            "tags",
        ),
        max_frequency_hz=5.0,
        memory_class=MemoryClass.EPHEMERAL,
        budget_cost=1,
        redaction_rules=("sensor_id",),
    ),
    SignalType.USER_INPUT: SignalDefinition(
        allowed_fields=(
            "user_id",
            "input",
            "modality",
            "confidence",
            "timestamp",
            "metadata",
            "frequency_hz",
            "tags",
        ),
        max_frequency_hz=2.0,
        memory_class=MemoryClass.WORKING,
        budget_cost=2,
        redaction_rules=("user_id", "input"),
    ),
    SignalType.ENVIRONMENTAL_STATE: SignalDefinition(
        allowed_fields=(
            "source",
            "state",
            "confidence",
            "timestamp",
            "metadata",
            "frequency_hz",
            "tags",
        ),
        max_frequency_hz=1.0,
        memory_class=MemoryClass.CONTEXTUAL,
        budget_cost=2,
        redaction_rules=("state",),
    ),
    SignalType.SYSTEM_FEEDBACK: SignalDefinition(
        allowed_fields=(
            "component",
            "status",
            "details",
            "confidence",
            "timestamp",
            "metadata",
            "frequency_hz",
            "tags",
        ),
        max_frequency_hz=1.0,
        memory_class=MemoryClass.AUDIT,
        budget_cost=3,
        redaction_rules=("details",),
    ),
    SignalType.ADVISORY_SIGNAL: SignalDefinition(
        allowed_fields=(
            "advice",
            "severity",
            "summary",
            "confidence",
            "timestamp",
            "metadata",
            "frequency_hz",
            "tags",
        ),
        max_frequency_hz=1.0,
        memory_class=MemoryClass.CONTEXTUAL,
        budget_cost=2,
        redaction_rules=("advice", "summary"),
    ),
    SignalType.STATUS_REPORT: SignalDefinition(
        allowed_fields=(
            "component",
            "status",
            "summary",
            "confidence",
            "timestamp",
            "metadata",
            "frequency_hz",
            "tags",
        ),
        max_frequency_hz=1.0,
        memory_class=MemoryClass.STRUCTURAL,
        budget_cost=3,
        redaction_rules=("summary",),
    ),
    SignalType.REQUEST_FOR_ACTION: SignalDefinition(
        allowed_fields=(
            "request",
            "justification",
            "urgency",
            "confidence",
            "timestamp",
            "metadata",
            "frequency_hz",
            "tags",
        ),
        max_frequency_hz=0.5,
        memory_class=MemoryClass.AUDIT,
        budget_cost=3,
        redaction_rules=("justification",),
    ),
    SignalType.SIMULATED_ACTUATION: SignalDefinition(
        allowed_fields=(
            "action",
            "target",
            "expected_effect",
            "confidence",
            "timestamp",
            "metadata",
            "frequency_hz",
            "tags",
        ),
        max_frequency_hz=0.5,
        memory_class=MemoryClass.EPHEMERAL,
        budget_cost=1,
        redaction_rules=("target",),
    ),
}


def _contract_id(direction: SignalDirection, signal_type: SignalType) -> str:
    return f"embodiment:{direction.value.lower()}:{signal_type.value.lower()}:v1"


def _build_contract(direction: SignalDirection, signal_type: SignalType) -> EmbodimentContract:
    definition = _SIGNAL_DEFINITIONS[signal_type]
    return EmbodimentContract(
        contract_id=_contract_id(direction, signal_type),
        direction=direction,
        signal_type=signal_type,
        allowed_contexts=_DEFAULT_ALLOWED_CONTEXTS,
        forbidden_contexts=_DEFAULT_FORBIDDEN_CONTEXTS,
        budget_cost=definition.budget_cost,
        simulation_only=True,
    )


_CONTRACTS: dict[tuple[SignalDirection, SignalType], EmbodimentContract] = {
    (SignalDirection.INGRESS, SignalType.SENSOR_EVENT): _build_contract(
        SignalDirection.INGRESS, SignalType.SENSOR_EVENT
    ),
    (SignalDirection.INGRESS, SignalType.USER_INPUT): _build_contract(
        SignalDirection.INGRESS, SignalType.USER_INPUT
    ),
    (SignalDirection.INGRESS, SignalType.ENVIRONMENTAL_STATE): _build_contract(
        SignalDirection.INGRESS, SignalType.ENVIRONMENTAL_STATE
    ),
    (SignalDirection.INGRESS, SignalType.SYSTEM_FEEDBACK): _build_contract(
        SignalDirection.INGRESS, SignalType.SYSTEM_FEEDBACK
    ),
    (SignalDirection.EGRESS, SignalType.ADVISORY_SIGNAL): _build_contract(
        SignalDirection.EGRESS, SignalType.ADVISORY_SIGNAL
    ),
    (SignalDirection.EGRESS, SignalType.STATUS_REPORT): _build_contract(
        SignalDirection.EGRESS, SignalType.STATUS_REPORT
    ),
    (SignalDirection.EGRESS, SignalType.REQUEST_FOR_ACTION): _build_contract(
        SignalDirection.EGRESS, SignalType.REQUEST_FOR_ACTION
    ),
    (SignalDirection.EGRESS, SignalType.SIMULATED_ACTUATION): _build_contract(
        SignalDirection.EGRESS, SignalType.SIMULATED_ACTUATION
    ),
}


def get_signal_definition(signal_type: SignalType) -> SignalDefinition:
    return _SIGNAL_DEFINITIONS[signal_type]


def get_embodiment_contract(direction: SignalDirection, signal_type: SignalType) -> EmbodimentContract:
    return _CONTRACTS[(direction, signal_type)]


def list_embodiment_contracts() -> Sequence[EmbodimentContract]:
    ordered = sorted(_CONTRACTS.values(), key=lambda item: item.contract_id)
    return tuple(ordered)


def validate_payload_fields(payload: Mapping[str, object], definition: SignalDefinition) -> list[str]:
    violations: list[str] = []
    for key in payload.keys():
        if str(key) not in definition.allowed_fields:
            violations.append(f"field_not_allowed:{key}")
    frequency = payload.get("frequency_hz")
    if frequency is not None:
        try:
            freq_value = float(frequency)
        except (TypeError, ValueError):
            violations.append("frequency_invalid")
        else:
            if freq_value < 0:
                violations.append("frequency_negative")
            if freq_value > definition.max_frequency_hz:
                violations.append("frequency_exceeds_max")
    return violations


def redact_payload(payload: Mapping[str, object], redaction_rules: Sequence[str]) -> dict[str, object]:
    redaction_keys = {rule for rule in redaction_rules}
    sanitized: dict[str, object] = {}
    for key, value in payload.items():
        if str(key) in redaction_keys:
            sanitized[str(key)] = "***"
        else:
            sanitized[str(key)] = value
    return sanitized


__all__ = [
    "EmbodimentContract",
    "SignalDefinition",
    "SignalDirection",
    "SignalType",
    "get_embodiment_contract",
    "get_signal_definition",
    "list_embodiment_contracts",
    "redact_payload",
    "validate_payload_fields",
]
