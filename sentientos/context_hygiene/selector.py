from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.context_packet import (
    ContextMode,
    ContextPacket,
    ContextPacketItem,
    ContradictionStatus,
    ExcludedContextRef,
    FreshnessStatus,
    PollutionRisk,
    ProvenanceStatus,
    make_context_packet,
)
from sentientos.context_hygiene.pollution_guard import (
    BLOCKING_TRUTH_INGRESS,
    candidate_is_expired,
    classify_pollution_risk,
    combine_contradiction_status,
    combine_freshness_status,
    combine_pollution_risk,
    provenance_is_complete,
)


@dataclass(frozen=True)
class ContextCandidate:
    ref_id: str
    ref_type: str
    packet_scope: str | None = None
    conversation_scope_id: str | None = None
    task_scope_id: str | None = None
    summary: str | None = None
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)
    source_locator: str | None = None
    created_at: datetime | None = None
    observed_at: datetime | None = None
    valid_until: datetime | None = None
    expires_at: datetime | None = None
    freshness_status: str = "unknown"
    contradiction_status: str = "unknown"
    provenance_status: str = "partial"
    epistemic_status: str | None = None
    truth_ingress_status: str | None = None
    stance_status: str | None = None
    source_priority: str | None = None
    pollution_risk: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    stance_refs: tuple[str, ...] = field(default_factory=tuple)
    already_sanitized_context_summary: bool = False


@dataclass(frozen=True)
class ContextSelectionDecision:
    candidate: ContextCandidate
    included: bool
    lane: str
    reason: str


def _scope_conflicts(candidate: ContextCandidate, packet_scope: str, conversation_scope_id: str, task_scope_id: str) -> bool:
    if candidate.packet_scope and candidate.packet_scope != packet_scope:
        return True
    if candidate.conversation_scope_id and candidate.conversation_scope_id != conversation_scope_id:
        return True
    if candidate.task_scope_id and candidate.task_scope_id != task_scope_id:
        return True
    return False


def explain_candidate_exclusion(candidate: ContextCandidate, packet_scope: str, conversation_scope_id: str, task_scope_id: str, now: datetime) -> str | None:
    if not candidate.ref_id:
        return "excluded: missing ref_id"
    if not provenance_is_complete(candidate):
        return "excluded: missing provenance"
    if _scope_conflicts(candidate, packet_scope, conversation_scope_id, task_scope_id):
        return "excluded: scope mismatch"
    if candidate_is_expired(candidate, now=now):
        return "excluded: expired candidate"
    if candidate.ref_type == "unknown":
        return "excluded: unknown ref_type"
    if candidate.ref_type == "claim" and candidate.metadata.get("source_backed") and not candidate.evidence_refs:
        return "excluded: source-backed claim missing evidence refs"
    if str(candidate.truth_ingress_status or "").lower() in BLOCKING_TRUTH_INGRESS:
        return f"excluded: truth ingress blocked ({candidate.truth_ingress_status})"
    if str(candidate.contradiction_status).lower() == "blocked":
        return "excluded: contradiction blocked"
    if candidate.ref_type == "stance" and (not candidate.stance_refs):
        return "excluded: stance candidate missing stance refs"
    if candidate.ref_type == "dialogue" and (not candidate.packet_scope and not candidate.conversation_scope_id and not candidate.task_scope_id):
        return "excluded: dialogue candidate requires scope"
    if candidate.ref_type == "embodiment" and not candidate.already_sanitized_context_summary:
        return "excluded: embodiment candidate not sanitized (Phase 63)"
    return None


def candidate_is_context_eligible(candidate: ContextCandidate, packet_scope: str, conversation_scope_id: str, task_scope_id: str, now: datetime) -> bool:
    return explain_candidate_exclusion(candidate, packet_scope, conversation_scope_id, task_scope_id, now) is None


def select_context_candidates(candidates: Sequence[ContextCandidate], packet_scope: str, conversation_scope_id: str, task_scope_id: str, now: datetime | None = None) -> tuple[ContextSelectionDecision, ...]:
    current = now or datetime.now(timezone.utc)
    decisions: list[ContextSelectionDecision] = []
    for candidate in candidates:
        reason = explain_candidate_exclusion(candidate, packet_scope, conversation_scope_id, task_scope_id, current)
        lane = candidate.ref_type if candidate.ref_type in {"memory", "claim", "evidence", "stance", "diagnostic", "embodiment"} else "diagnostic"
        if reason:
            decisions.append(ContextSelectionDecision(candidate, False, lane, reason))
            continue
        include_reason = "included: provenance-complete and scope-compatible"
        if str(candidate.contradiction_status).lower() in {"warning", "suspected"}:
            include_reason = "included with caveat: contested/contradiction warning"
        decisions.append(ContextSelectionDecision(candidate, True, lane, include_reason))
    return tuple(decisions)


def build_context_packet_from_candidates(candidates: Sequence[ContextCandidate], packet_scope: str, conversation_scope_id: str, task_scope_id: str, context_mode: ContextMode = ContextMode.RESPONSE, now: datetime | None = None, valid_until: datetime | None = None, budget: int | None = None) -> ContextPacket:
    current = now or datetime.now(timezone.utc)
    decisions = list(select_context_candidates(candidates, packet_scope, conversation_scope_id, task_scope_id, now=current))
    if budget is not None:
        included = [d for d in decisions if d.included][:budget]
        excluded = [d for d in decisions if not d.included] + [
            ContextSelectionDecision(d.candidate, False, d.lane, "excluded: budget exceeded")
            for d in decisions
            if d.included and d not in included
        ]
        decisions = included + excluded

    def mk_item(d: ContextSelectionDecision) -> ContextPacketItem:
        return ContextPacketItem(d.candidate.ref_id, d.candidate.ref_type, {"provenance_refs": list(d.candidate.provenance_refs), "source_locator": d.candidate.source_locator})

    def lane_items(lane: str) -> tuple[ContextPacketItem, ...]:
        return tuple(mk_item(d) for d in decisions if d.included and d.lane == lane)

    excluded_refs = tuple(
        ExcludedContextRef(d.candidate.ref_id or "(missing)", d.lane, d.reason, d.candidate.source_locator, {"provenance_refs": list(d.candidate.provenance_refs)})
        for d in decisions
        if not d.included
    )
    included_candidates = [d.candidate for d in decisions if d.included]
    attempted_candidates = [d.candidate for d in decisions]
    pollution = combine_pollution_risk(attempted_candidates, now=current)
    packet_pollution = PollutionRisk(pollution)
    contradiction = combine_contradiction_status(included_candidates)
    freshness = combine_freshness_status(included_candidates)
    provenance_complete = all(provenance_is_complete(c) for c in candidates)
    provenance_status = ProvenanceStatus.COMPLETE if provenance_complete else ProvenanceStatus.PARTIAL
    return make_context_packet(
        packet_scope=packet_scope,
        conversation_scope_id=conversation_scope_id,
        task_scope_id=task_scope_id,
        context_mode=context_mode,
        valid_until=valid_until or (current + timedelta(minutes=5)),
        included_memory_refs=lane_items("memory"),
        included_claim_refs=lane_items("claim"),
        included_evidence_refs=lane_items("evidence"),
        included_stance_refs=lane_items("stance"),
        included_diagnostic_refs=lane_items("diagnostic"),
        included_embodiment_refs=lane_items("embodiment"),
        excluded_refs=excluded_refs,
        inclusion_reasons=tuple(d.reason for d in decisions if d.included),
        exclusion_reasons=tuple(d.reason for d in decisions if not d.included),
        freshness_status=freshness,
        contradiction_status=contradiction,
        provenance_complete=provenance_complete,
        provenance_status=provenance_status,
        source_priority=tuple(c.source_priority for c in included_candidates if c.source_priority),
        pollution_risk=packet_pollution,
    )
