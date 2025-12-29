from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping, Sequence

from sentientos.diagnostics import (
    DiagnosticError,
    ErrorClass,
    FailedPhase,
    build_error_frame,
)
from sentientos.introspection.spine import EventType, emit_introspection_event
from sentientos.memory_economics import MemoryClass, MemoryEconomicPlan, simulate_memory_economics

from .contracts import (
    EmbodimentContract,
    SignalDefinition,
    SignalDirection,
    SignalType,
    get_embodiment_contract,
    get_signal_definition,
    redact_payload,
    validate_payload_fields,
)


@dataclass(frozen=True)
class SimulationResult:
    simulation_id: str
    contract: EmbodimentContract
    definition: SignalDefinition
    direction: SignalDirection
    signal_type: SignalType
    payload: Mapping[str, object]
    context: str
    memory_plan: MemoryEconomicPlan
    memory_cost: float
    pressure_tier: str
    simulation_only: bool
    mutation_allowed: bool
    introspection_event_id: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "simulation_id": self.simulation_id,
            "contract": self.contract.to_dict(),
            "definition": self.definition.to_dict(),
            "direction": self.direction.value,
            "signal_type": self.signal_type.value,
            "payload": dict(self.payload),
            "context": self.context,
            "simulation_only": self.simulation_only,
            "mutation_allowed": self.mutation_allowed,
            "memory_cost": self.memory_cost,
            "pressure_tier": self.pressure_tier,
            "memory_plan": self.memory_plan.to_dict(),
            "introspection_event_id": self.introspection_event_id,
        }


def simulate_signal(
    direction: SignalDirection,
    signal_type: SignalType,
    payload: Mapping[str, object],
    *,
    context: str,
    cognition_cycle_id: str | None = None,
    introspection_path: str | None = None,
) -> SimulationResult:
    try:
        contract = get_embodiment_contract(direction, signal_type)
    except KeyError as exc:
        frame = build_error_frame(
            error_code="EMBODIMENT_CONTRACT_UNKNOWN",
            error_class=ErrorClass.CONFIG,
            failed_phase=FailedPhase.CLI,
            suppressed_actions=["auto_recovery", "retry", "state_mutation"],
            human_summary="Embodiment signal type is not registered for this direction.",
            technical_details={
                "direction": direction.value,
                "signal_type": signal_type.value,
            },
        )
        raise DiagnosticError(frame) from exc
    definition = get_signal_definition(signal_type)
    violations = _validate_contract(contract, definition, payload, context)
    if violations:
        raise _violation_error(
            contract=contract,
            definition=definition,
            payload=payload,
            context=context,
            violations=violations,
        )

    sanitized_payload = redact_payload(payload, definition.redaction_rules)
    simulation_id = _simulation_hash(contract.contract_id, sanitized_payload)
    entry = _memory_entry(
        simulation_id,
        sanitized_payload,
        definition.memory_class,
        direction,
        signal_type,
    )
    memory_plan = simulate_memory_economics(
        [entry],
        emit_introspection=True,
        introspection_path=introspection_path,
    )
    memory_cost = _memory_cost(definition.budget_cost, memory_plan)
    introspection_event_id = _emit_simulation_introspection(
        simulation_id=simulation_id,
        contract=contract,
        direction=direction,
        signal_type=signal_type,
        context=context,
        memory_plan=memory_plan,
        memory_cost=memory_cost,
        cognition_cycle_id=cognition_cycle_id,
        introspection_path=introspection_path,
    )
    return SimulationResult(
        simulation_id=simulation_id,
        contract=contract,
        definition=definition,
        direction=direction,
        signal_type=signal_type,
        payload=sanitized_payload,
        context=context,
        memory_plan=memory_plan,
        memory_cost=memory_cost,
        pressure_tier=memory_plan.pressure_tier.name,
        simulation_only=True,
        mutation_allowed=False,
        introspection_event_id=introspection_event_id,
    )


def _validate_contract(
    contract: EmbodimentContract,
    definition: SignalDefinition,
    payload: Mapping[str, object],
    context: str,
) -> list[str]:
    violations: list[str] = []
    if not contract.simulation_only:
        violations.append("contract_not_simulation_only")
    normalized_context = context.strip().lower()
    if normalized_context in {item.lower() for item in contract.forbidden_contexts}:
        violations.append("context_forbidden")
    allowed = {item.lower() for item in contract.allowed_contexts}
    if allowed and normalized_context not in allowed:
        violations.append("context_not_allowed")
    violations.extend(validate_payload_fields(payload, definition))
    return violations


def _violation_error(
    *,
    contract: EmbodimentContract,
    definition: SignalDefinition,
    payload: Mapping[str, object],
    context: str,
    violations: Sequence[str],
) -> DiagnosticError:
    frame = build_error_frame(
        error_code="EMBODIMENT_CONTRACT_VIOLATION",
        error_class=ErrorClass.INTEGRITY,
        failed_phase=FailedPhase.CLI,
        violated_invariant="EMBODIMENT_SIMULATION_CONTRACT",
        suppressed_actions=["auto_recovery", "retry", "state_mutation"],
        human_summary="Embodiment simulation request violated contract constraints.",
        technical_details={
            "contract_id": contract.contract_id,
            "direction": contract.direction.value,
            "signal_type": contract.signal_type.value,
            "context": context,
            "violations": list(violations),
            "allowed_fields": list(definition.allowed_fields),
        },
    )
    return DiagnosticError(frame)


def _simulation_hash(contract_id: str, payload: Mapping[str, object]) -> str:
    encoded = json.dumps({"contract_id": contract_id, "payload": payload}, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _memory_entry(
    simulation_id: str,
    payload: Mapping[str, object],
    memory_class: MemoryClass,
    direction: SignalDirection,
    signal_type: SignalType,
) -> dict[str, object]:
    entry = {
        "id": simulation_id,
        "category": "event",
        "source": f"embodiment:{direction.value.lower()}",
        "summary": f"{direction.value} {signal_type.value} simulated",
        "payload": dict(payload),
        "tags": ["embodiment", signal_type.value.lower(), memory_class.value.lower()],
    }
    entry["tags"] = _tags_for_memory_class(memory_class, entry["tags"])
    return entry


def _tags_for_memory_class(memory_class: MemoryClass, tags: Sequence[str]) -> list[str]:
    mapping = {
        MemoryClass.EPHEMERAL: "ephemeral",
        MemoryClass.WORKING: "working",
        MemoryClass.CONTEXTUAL: "contextual",
        MemoryClass.STRUCTURAL: "policy",
        MemoryClass.AUDIT: "audit",
        MemoryClass.PROOF: "proof",
    }
    tag = mapping.get(memory_class, "contextual")
    combined = list(tags)
    if tag not in combined:
        combined.append(tag)
    return combined


def _memory_cost(base_cost: int, plan: MemoryEconomicPlan) -> float:
    return round(base_cost * plan.pressure_tier.retention_cost_multiplier, 3)


def _emit_simulation_introspection(
    *,
    simulation_id: str,
    contract: EmbodimentContract,
    direction: SignalDirection,
    signal_type: SignalType,
    context: str,
    memory_plan: MemoryEconomicPlan,
    memory_cost: float,
    cognition_cycle_id: str | None,
    introspection_path: str | None,
) -> str | None:
    metadata = {
        "contract_id": contract.contract_id,
        "direction": direction.value,
        "signal_type": signal_type.value,
        "context": context,
        "simulation_only": True,
        "memory_cost": memory_cost,
        "pressure_tier": memory_plan.pressure_tier.name,
        "memory_plan_hash": memory_plan.plan_hash,
        "cognition_cycle_id": cognition_cycle_id,
    }
    emit_introspection_event(
        event_type=EventType.CLI_ACTION,
        phase="embodiment_simulation",
        summary=f"Simulated embodiment {direction.value.lower()} {signal_type.value.lower()} signal.",
        metadata=metadata,
        linked_artifact_ids=[simulation_id, memory_plan.plan_hash],
        path=introspection_path or "logs/introspection_spine.jsonl",
    )
    return _introspection_event_id(metadata, simulation_id)


def _introspection_event_id(metadata: Mapping[str, object], simulation_id: str) -> str:
    encoded = json.dumps({"simulation_id": simulation_id, "metadata": metadata}, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = ["SimulationResult", "simulate_signal"]
