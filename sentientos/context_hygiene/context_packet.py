from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4


class ContextAssemblyStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class ContextMode(str, Enum):
    RESPONSE = "response"
    DIAGNOSTIC = "diagnostic"
    SAFETY = "safety"


class FreshnessStatus(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ContradictionStatus(str, Enum):
    NONE = "none"
    SUSPECTED = "suspected"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"


class ProvenanceStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"


class PollutionRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ContextPacketItem:
    ref_id: str
    source: str
    provenance: Mapping[str, Any]


@dataclass(frozen=True)
class ExcludedContextRef:
    ref_id: str
    lane: str
    reason: str
    source: str | None = None
    provenance: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ContextBudget:
    max_items: int
    max_tokens: int | None = None


@dataclass(frozen=True)
class ContextPacket:
    schema_version: str
    context_packet_id: str
    packet_scope: str
    conversation_scope_id: str
    task_scope_id: str
    context_mode: ContextMode
    created_at: datetime
    valid_until: datetime
    included_memory_refs: tuple[ContextPacketItem, ...] = field(default_factory=tuple)
    included_claim_refs: tuple[ContextPacketItem, ...] = field(default_factory=tuple)
    included_evidence_refs: tuple[ContextPacketItem, ...] = field(default_factory=tuple)
    included_stance_refs: tuple[ContextPacketItem, ...] = field(default_factory=tuple)
    included_diagnostic_refs: tuple[ContextPacketItem, ...] = field(default_factory=tuple)
    included_embodiment_refs: tuple[ContextPacketItem, ...] = field(default_factory=tuple)
    excluded_refs: tuple[ExcludedContextRef, ...] = field(default_factory=tuple)
    inclusion_reasons: tuple[str, ...] = field(default_factory=tuple)
    exclusion_reasons: tuple[str, ...] = field(default_factory=tuple)
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    contradiction_status: ContradictionStatus = ContradictionStatus.UNKNOWN
    provenance_complete: bool = False
    provenance_status: ProvenanceStatus = ProvenanceStatus.PARTIAL
    source_priority: tuple[str, ...] = field(default_factory=tuple)
    pollution_risk: PollutionRisk = PollutionRisk.MEDIUM
    non_authoritative: bool = True
    decision_power: str = "none"
    context_packet_is_not_truth: bool = True
    context_packet_is_not_memory_write: bool = True
    does_not_admit_work: bool = True
    does_not_execute_or_route_work: bool = True


def make_context_packet(*, packet_scope: str, conversation_scope_id: str, task_scope_id: str, context_mode: ContextMode, valid_until: datetime, schema_version: str = "phase61.v1", context_packet_id: str | None = None, **kwargs: Any) -> ContextPacket:
    return ContextPacket(
        schema_version=schema_version,
        context_packet_id=context_packet_id or str(uuid4()),
        packet_scope=packet_scope,
        conversation_scope_id=conversation_scope_id,
        task_scope_id=task_scope_id,
        context_mode=context_mode,
        created_at=datetime.now(timezone.utc),
        valid_until=valid_until,
        **kwargs,
    )


def _all_included_refs(packet: ContextPacket) -> tuple[ContextPacketItem, ...]:
    return (
        packet.included_memory_refs
        + packet.included_claim_refs
        + packet.included_evidence_refs
        + packet.included_stance_refs
        + packet.included_diagnostic_refs
        + packet.included_embodiment_refs
    )


def validate_context_packet(packet: ContextPacket) -> list[str]:
    errors: list[str] = []
    if not packet.context_packet_id:
        errors.append("missing packet id")
    if not packet.packet_scope:
        errors.append("missing scope")
    if not packet.valid_until:
        errors.append("missing expiry")
    for item in _all_included_refs(packet):
        if not item.provenance:
            errors.append(f"included ref without provenance: {item.ref_id}")
    if packet.decision_power != "none":
        errors.append("decision_power must be none")
    if not packet.non_authoritative:
        errors.append("packet must be non_authoritative")
    if not packet.context_packet_is_not_truth:
        errors.append("packet cannot claim truth")
    if not packet.context_packet_is_not_memory_write:
        errors.append("packet cannot write memory")
    if not packet.does_not_admit_work:
        errors.append("packet cannot admit work")
    if not packet.does_not_execute_or_route_work:
        errors.append("packet cannot execute or route work")
    try:
        PollutionRisk(packet.pollution_risk)
    except ValueError:
        errors.append(f"invalid pollution risk: {packet.pollution_risk}")
    return errors


def packet_is_expired(packet: ContextPacket, now: datetime | None = None) -> bool:
    current = now or datetime.now(timezone.utc)
    return current >= packet.valid_until


def packet_has_decision_power(packet: ContextPacket) -> bool:
    return packet.decision_power != "none"


def summarize_packet_for_diagnostics(packet: ContextPacket) -> dict[str, Any]:
    return {
        "context_packet_id": packet.context_packet_id,
        "packet_scope": packet.packet_scope,
        "context_mode": packet.context_mode.value,
        "created_at": packet.created_at.isoformat(),
        "valid_until": packet.valid_until.isoformat(),
        "included_ref_count": len(_all_included_refs(packet)),
        "excluded_ref_count": len(packet.excluded_refs),
        "provenance_complete": packet.provenance_complete,
        "freshness_status": packet.freshness_status.value,
        "contradiction_status": packet.contradiction_status.value,
        "pollution_risk": packet.pollution_risk.value,
    }
