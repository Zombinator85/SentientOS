from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sentientos.context_hygiene.context_packet import (
    ContextPacket,
    ContextPacketItem,
    ContradictionStatus,
    FreshnessStatus,
    PollutionRisk,
    validate_context_packet,
)


class PromptContextEligibilityStatus(str, Enum):
    PROMPT_ELIGIBLE = "prompt_eligible"
    PROMPT_ELIGIBLE_WITH_CAVEATS = "prompt_eligible_with_caveats"
    PROMPT_INELIGIBLE_BLOCKED_RISK = "prompt_ineligible_blocked_risk"
    PROMPT_INELIGIBLE_PROVENANCE_GAP = "prompt_ineligible_provenance_gap"
    PROMPT_INELIGIBLE_TRUTH_GAP = "prompt_ineligible_truth_gap"
    PROMPT_INELIGIBLE_PRIVACY_GAP = "prompt_ineligible_privacy_gap"
    PROMPT_INELIGIBLE_ACTION_GAP = "prompt_ineligible_action_gap"
    PROMPT_INELIGIBLE_AUTHORITY_GAP = "prompt_ineligible_authority_gap"
    PROMPT_INELIGIBLE_EMPTY_PACKET = "prompt_ineligible_empty_packet"
    PROMPT_INELIGIBLE_SCHEMA_VIOLATION = "prompt_ineligible_schema_violation"


@dataclass(frozen=True)
class PromptContextEligibility:
    eligibility_status: PromptContextEligibilityStatus
    prompt_eligible: bool
    may_be_prompted_only_with_caveats: bool
    block_reasons: tuple[str, ...] = field(default_factory=tuple)
    caveats: tuple[str, ...] = field(default_factory=tuple)
    packet_id: str = ""
    packet_scope: str = ""
    pollution_risk: str = ""
    provenance_complete: bool = False
    included_ref_count: int = 0
    excluded_ref_count: int = 0
    blocked_ref_ids: tuple[str, ...] = field(default_factory=tuple)
    high_risk_ref_ids: tuple[str, ...] = field(default_factory=tuple)
    privacy_sensitive_ref_ids: tuple[str, ...] = field(default_factory=tuple)
    biometric_or_emotion_ref_ids: tuple[str, ...] = field(default_factory=tuple)
    raw_retention_ref_ids: tuple[str, ...] = field(default_factory=tuple)
    action_capable_ref_ids: tuple[str, ...] = field(default_factory=tuple)
    authority_risk_ref_ids: tuple[str, ...] = field(default_factory=tuple)
    truth_or_contradiction_risk_ref_ids: tuple[str, ...] = field(default_factory=tuple)
    rationale: str = ""
    preflight_only: bool = True
    does_not_assemble_prompt: bool = True
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True


PromptContextPreflightSummary = PromptContextEligibility


def _all_included(packet: ContextPacket) -> tuple[ContextPacketItem, ...]:
    return (
        packet.included_memory_refs
        + packet.included_claim_refs
        + packet.included_evidence_refs
        + packet.included_stance_refs
        + packet.included_diagnostic_refs
        + packet.included_embodiment_refs
    )


def _item_flag(item: ContextPacketItem, key: str, default: Any = False) -> Any:
    return item.provenance.get(key, default)


def packet_has_prompt_blocking_risk(packet: ContextPacket) -> bool:
    return packet.pollution_risk == PollutionRisk.BLOCKED or any(str(_item_flag(i, "pollution_risk", "")).lower() == PollutionRisk.BLOCKED.value for i in _all_included(packet))


def packet_has_prompt_blocking_provenance_gap(packet: ContextPacket) -> bool:
    return (not packet.provenance_complete) or any(not i.provenance for i in _all_included(packet))


def packet_has_prompt_blocking_truth_gap(packet: ContextPacket) -> bool:
    blocked = {"blocked", "contradicted", "unsafe"}
    if packet.contradiction_status == ContradictionStatus.CONTRADICTED:
        return True
    return any(str(_item_flag(i, "contradiction_status", "")).lower() in blocked or str(_item_flag(i, "truth_ingress_status", "")).lower() in blocked for i in _all_included(packet))


def packet_has_prompt_blocking_privacy_gap(packet: ContextPacket) -> bool:
    blocked_kinds = {
        "raw_perception_event", "legacy_screen_artifact", "legacy_audio_artifact", "legacy_vision_artifact", "legacy_multimodal_artifact", "legacy_feedback_artifact"
    }
    for i in _all_included(packet):
        kind = str(_item_flag(i, "source_kind", "")).lower()
        posture = str(_item_flag(i, "privacy_posture", "public")).lower()
        sanitized = bool(_item_flag(i, "sanitized_context_summary", False))
        if kind in blocked_kinds:
            return True
        if posture == "privacy_sensitive" and not (sanitized and _item_flag(i, "allow_context_privacy_sensitive", False)):
            return True
        if posture == "biometric_or_emotion_sensitive" and not (sanitized and _item_flag(i, "allow_context_biometric_or_emotion", False)):
            return True
        if posture == "raw_retention_sensitive" and not (sanitized and _item_flag(i, "allow_context_raw_retention", False)):
            return True
    return False


def packet_has_prompt_blocking_action_gap(packet: ContextPacket) -> bool:
    flags = ["can_write_memory", "can_trigger_feedback", "can_commit_retention", "action_capable", "can_admit", "can_route", "can_approve", "can_execute", "can_fulfill", "can_trigger_work"]
    guard_flags = ["validation_is_not_memory_write", "validation_is_not_action_trigger", "validation_is_not_retention_commit", "handoff_is_not_fulfillment", "bridge_is_not_admission", "fulfillment_candidate_is_not_effect", "fulfillment_receipt_is_not_effect", "receipt_does_not_prove_side_effect"]
    for i in _all_included(packet):
        if any(bool(_item_flag(i, f, False)) for f in flags):
            return True
        if any(f in i.provenance and not bool(_item_flag(i, f, True)) for f in guard_flags):
            return True
    return False


def packet_has_prompt_blocking_authority_gap(packet: ContextPacket) -> bool:
    return (not packet.non_authoritative) or packet.decision_power != "none" or any((not bool(_item_flag(i, "non_authoritative", True))) or str(_item_flag(i, "decision_power", "none")) != "none" for i in _all_included(packet))


def evaluate_context_packet_prompt_eligibility(packet: ContextPacket) -> PromptContextEligibility:
    included = _all_included(packet)
    errors = validate_context_packet(packet)
    block_reasons: list[str] = []
    caveats: list[str] = []
    if errors:
        block_reasons.extend(errors)
        status = PromptContextEligibilityStatus.PROMPT_INELIGIBLE_SCHEMA_VIOLATION
    elif not included:
        block_reasons.append("packet has zero included refs")
        status = PromptContextEligibilityStatus.PROMPT_INELIGIBLE_EMPTY_PACKET
    elif packet_has_prompt_blocking_risk(packet):
        block_reasons.append("blocked pollution risk")
        status = PromptContextEligibilityStatus.PROMPT_INELIGIBLE_BLOCKED_RISK
    elif packet_has_prompt_blocking_provenance_gap(packet):
        block_reasons.append("provenance gap")
        status = PromptContextEligibilityStatus.PROMPT_INELIGIBLE_PROVENANCE_GAP
    elif packet_has_prompt_blocking_truth_gap(packet):
        block_reasons.append("truth/contradiction gap")
        status = PromptContextEligibilityStatus.PROMPT_INELIGIBLE_TRUTH_GAP
    elif packet_has_prompt_blocking_privacy_gap(packet):
        block_reasons.append("privacy/sanitization gap")
        status = PromptContextEligibilityStatus.PROMPT_INELIGIBLE_PRIVACY_GAP
    elif packet_has_prompt_blocking_action_gap(packet):
        block_reasons.append("action-capable gap")
        status = PromptContextEligibilityStatus.PROMPT_INELIGIBLE_ACTION_GAP
    elif packet_has_prompt_blocking_authority_gap(packet):
        block_reasons.append("authority gap")
        status = PromptContextEligibilityStatus.PROMPT_INELIGIBLE_AUTHORITY_GAP
    else:
        status = PromptContextEligibilityStatus.PROMPT_ELIGIBLE

    if status == PromptContextEligibilityStatus.PROMPT_ELIGIBLE:
        if packet.pollution_risk == PollutionRisk.HIGH:
            caveats.append("packet pollution risk is high")
        if packet.freshness_status == FreshnessStatus.STALE:
            caveats.append("packet freshness is stale")
        if packet.contradiction_status == ContradictionStatus.SUSPECTED:
            caveats.append("packet contradiction status is suspected")
        for i in included:
            posture = str(_item_flag(i, "privacy_posture", "")).lower()
            if posture in {"privacy_sensitive", "biometric_or_emotion_sensitive", "raw_retention_sensitive"}:
                caveats.append(f"{i.ref_id} contains sanitized sensitive context")
        if caveats:
            status = PromptContextEligibilityStatus.PROMPT_ELIGIBLE_WITH_CAVEATS

    return PromptContextEligibility(
        eligibility_status=status,
        prompt_eligible=status in {PromptContextEligibilityStatus.PROMPT_ELIGIBLE, PromptContextEligibilityStatus.PROMPT_ELIGIBLE_WITH_CAVEATS},
        may_be_prompted_only_with_caveats=status == PromptContextEligibilityStatus.PROMPT_ELIGIBLE_WITH_CAVEATS,
        block_reasons=tuple(block_reasons),
        caveats=tuple(dict.fromkeys(caveats)),
        packet_id=packet.context_packet_id,
        packet_scope=packet.packet_scope,
        pollution_risk=packet.pollution_risk.value,
        provenance_complete=packet.provenance_complete,
        included_ref_count=len(included),
        excluded_ref_count=len(packet.excluded_refs),
        blocked_ref_ids=tuple(i.ref_id for i in included if str(_item_flag(i, "pollution_risk", "")).lower() == "blocked"),
        high_risk_ref_ids=tuple(i.ref_id for i in included if str(_item_flag(i, "pollution_risk", "")).lower() == "high"),
        privacy_sensitive_ref_ids=tuple(i.ref_id for i in included if str(_item_flag(i, "privacy_posture", "")).lower() == "privacy_sensitive"),
        biometric_or_emotion_ref_ids=tuple(i.ref_id for i in included if str(_item_flag(i, "privacy_posture", "")).lower() == "biometric_or_emotion_sensitive"),
        raw_retention_ref_ids=tuple(i.ref_id for i in included if str(_item_flag(i, "privacy_posture", "")).lower() == "raw_retention_sensitive"),
        action_capable_ref_ids=tuple(i.ref_id for i in included if bool(_item_flag(i, "action_capable", False))),
        authority_risk_ref_ids=tuple(i.ref_id for i in included if (not bool(_item_flag(i, "non_authoritative", True))) or str(_item_flag(i, "decision_power", "none")) != "none"),
        truth_or_contradiction_risk_ref_ids=tuple(i.ref_id for i in included if str(_item_flag(i, "contradiction_status", "")).lower() in {"blocked", "contradicted", "unsafe"}),
        rationale="; ".join(block_reasons or caveats or ["prompt eligible"]),
    )


def explain_context_packet_prompt_ineligibility(packet: ContextPacket) -> tuple[str, ...]:
    result = evaluate_context_packet_prompt_eligibility(packet)
    return result.block_reasons


def summarize_context_packet_prompt_preflight(packet: ContextPacket) -> PromptContextPreflightSummary:
    return evaluate_context_packet_prompt_eligibility(packet)
