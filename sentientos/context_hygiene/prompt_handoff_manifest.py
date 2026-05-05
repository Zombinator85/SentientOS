from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any, Mapping

from sentientos.context_hygiene.context_packet import ContextPacket, ContextPacketItem, ExcludedContextRef, validate_context_packet
from sentientos.context_hygiene.prompt_preflight import (
    PromptContextEligibility,
    PromptContextEligibilityStatus,
    evaluate_context_packet_prompt_eligibility,
)
from sentientos.context_hygiene.safety_metadata import CONTEXT_SAFETY_METADATA_KEY


class ContextPromptHandoffStatus:
    HANDOFF_READY = "handoff_ready"
    HANDOFF_READY_WITH_CAVEATS = "handoff_ready_with_caveats"
    HANDOFF_BLOCKED = "handoff_blocked"
    HANDOFF_NOT_APPLICABLE = "handoff_not_applicable"
    HANDOFF_INVALID_PACKET = "handoff_invalid_packet"


@dataclass(frozen=True)
class ContextPromptHandoffRefSummary:
    ref_id: str
    ref_type: str
    lane: str
    scope_id: str
    content_summary: str
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)
    provenance_status: str = ""
    pollution_risk: str = ""
    freshness_status: str = ""
    contradiction_status: str = ""
    source_kind: str = ""
    privacy_posture: str = ""
    safety_metadata_summary: Mapping[str, Any] = field(default_factory=dict)
    safety_contract_valid: bool | None = None
    caveats: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ContextPromptHandoffLaneSummary:
    lane: str
    ref_type: str
    count: int
    highest_pollution_risk: str
    provenance_complete: bool
    source_kinds: tuple[str, ...]
    caveats: tuple[str, ...]
    blocked_or_unsafe_count: int
    rationale: str


@dataclass(frozen=True)
class ContextPromptHandoffBoundary:
    handoff_manifest_only: bool = True
    does_not_assemble_prompt: bool = True
    does_not_contain_prompt_text: bool = True
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True


@dataclass(frozen=True)
class ContextPromptHandoffManifest:
    manifest_id: str
    packet_id: str
    packet_scope: str
    packet_created_at: str
    handoff_status: str
    prompt_preflight_status: str
    prompt_eligible: bool
    caveated: bool
    blocked: bool
    block_reasons: tuple[str, ...]
    caveats: tuple[str, ...]
    pollution_risk: str
    provenance_complete: bool
    included_ref_count: int
    excluded_ref_count: int
    lane_summaries: tuple[ContextPromptHandoffLaneSummary, ...]
    included_ref_summaries: tuple[ContextPromptHandoffRefSummary, ...]
    excluded_ref_summaries: tuple[dict[str, str], ...]
    blocked_ref_ids: tuple[str, ...]
    high_risk_ref_ids: tuple[str, ...]
    privacy_sensitive_ref_ids: tuple[str, ...]
    biometric_or_emotion_ref_ids: tuple[str, ...]
    raw_retention_ref_ids: tuple[str, ...]
    action_capable_ref_ids: tuple[str, ...]
    authority_risk_ref_ids: tuple[str, ...]
    truth_or_contradiction_risk_ref_ids: tuple[str, ...]
    source_kind_summary: Mapping[str, int]
    safety_contract_gap_summary: tuple[str, ...]
    provenance_summary: str
    rationale: str
    digest: str
    boundary: ContextPromptHandoffBoundary = field(default_factory=ContextPromptHandoffBoundary)


def _all_included(packet: ContextPacket) -> tuple[ContextPacketItem, ...]:
    return packet.included_memory_refs + packet.included_claim_refs + packet.included_evidence_refs + packet.included_stance_refs + packet.included_diagnostic_refs + packet.included_embodiment_refs


def _meta(item: ContextPacketItem) -> Mapping[str, Any]:
    return item.provenance.get(CONTEXT_SAFETY_METADATA_KEY, {})


def summarize_context_packet_ref_for_handoff(item: ContextPacketItem) -> ContextPromptHandoffRefSummary:
    meta = _meta(item)
    return ContextPromptHandoffRefSummary(
        ref_id=item.ref_id,
        ref_type=item.source,
        lane=str(meta.get("lane", item.source)),
        scope_id=str(meta.get("scope_id", "")),
        content_summary=str(item.provenance.get("summary", meta.get("content_summary", ""))),
        provenance_refs=tuple(item.provenance.get("provenance_refs", ())),
        provenance_status=str(meta.get("provenance_status", "complete" if item.provenance else "missing")),
        pollution_risk=str(meta.get("pollution_risk", "")),
        freshness_status=str(meta.get("freshness_status", "")),
        contradiction_status=str(meta.get("contradiction_status", "")),
        source_kind=str(meta.get("source_kind", "")),
        privacy_posture=str(meta.get("privacy_posture", "")),
        safety_metadata_summary={k: v for k, v in meta.items() if k not in {"raw_payload", "prompt_text", "llm_params", "execution_handle"}},
        safety_contract_valid=meta.get("safety_contract_valid"),
        caveats=tuple(meta.get("caveats", ())),
    )


def summarize_context_packet_lane_for_handoff(lane: str, refs: tuple[ContextPromptHandoffRefSummary, ...]) -> ContextPromptHandoffLaneSummary:
    risks = [r.pollution_risk for r in refs]
    order = {"": 0, "low": 1, "medium": 2, "high": 3, "blocked": 4}
    highest = max(risks or [""], key=lambda x: order.get(str(x).lower(), 0))
    blocked_unsafe = sum(1 for r in refs if str(r.pollution_risk).lower() == "blocked" or str(r.contradiction_status).lower() in {"unsafe", "contradicted", "blocked"})
    return ContextPromptHandoffLaneSummary(
        lane=lane,
        ref_type=lane,
        count=len(refs),
        highest_pollution_risk=highest,
        provenance_complete=all(bool(r.provenance_refs) for r in refs),
        source_kinds=tuple(sorted({r.source_kind for r in refs if r.source_kind})),
        caveats=tuple(sorted({c for r in refs for c in r.caveats})),
        blocked_or_unsafe_count=blocked_unsafe,
        rationale=f"{lane} refs={len(refs)}",
    )


def summarize_context_packet_for_prompt_handoff(packet: ContextPacket) -> tuple[ContextPromptHandoffRefSummary, ...]:
    return tuple(summarize_context_packet_ref_for_handoff(i) for i in _all_included(packet))


def _map_status(pre: PromptContextEligibility, packet_errors: list[str]) -> str:
    if packet_errors:
        return ContextPromptHandoffStatus.HANDOFF_INVALID_PACKET
    if pre.eligibility_status == PromptContextEligibilityStatus.PROMPT_ELIGIBLE:
        return ContextPromptHandoffStatus.HANDOFF_READY
    if pre.eligibility_status == PromptContextEligibilityStatus.PROMPT_ELIGIBLE_WITH_CAVEATS:
        return ContextPromptHandoffStatus.HANDOFF_READY_WITH_CAVEATS
    if pre.eligibility_status == PromptContextEligibilityStatus.PROMPT_INELIGIBLE_EMPTY_PACKET:
        return ContextPromptHandoffStatus.HANDOFF_NOT_APPLICABLE
    return ContextPromptHandoffStatus.HANDOFF_BLOCKED


def compute_context_prompt_handoff_digest(manifest: ContextPromptHandoffManifest) -> str:
    stable = asdict(manifest)
    stable.pop("digest", None)
    payload = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def explain_context_prompt_handoff_block(manifest: ContextPromptHandoffManifest) -> tuple[str, ...]:
    return manifest.block_reasons


def manifest_contains_no_raw_payloads(manifest: ContextPromptHandoffManifest) -> bool:
    txt = json.dumps(asdict(manifest), sort_keys=True).lower()
    return all(x not in txt for x in ["raw_payload", "screen_frame", "mic_audio", "vision_frame"])


def manifest_has_no_runtime_authority(manifest: ContextPromptHandoffManifest) -> bool:
    b = manifest.boundary
    return all([b.handoff_manifest_only, b.does_not_assemble_prompt, b.does_not_call_llm, b.does_not_retrieve_memory, b.does_not_write_memory, b.does_not_execute_or_route_work, b.does_not_admit_work])


def summarize_context_prompt_handoff_manifest(manifest: ContextPromptHandoffManifest) -> dict[str, Any]:
    return {
        "manifest_id": manifest.manifest_id,
        "packet_id": manifest.packet_id,
        "handoff_status": manifest.handoff_status,
        "prompt_preflight_status": manifest.prompt_preflight_status,
        "included_ref_count": manifest.included_ref_count,
        "excluded_ref_count": manifest.excluded_ref_count,
        "digest": manifest.digest,
    }


def build_context_prompt_handoff_manifest(packet: ContextPacket, preflight: PromptContextEligibility | None = None) -> ContextPromptHandoffManifest:
    packet_errors = validate_context_packet(packet)
    pre = preflight or evaluate_context_packet_prompt_eligibility(packet)
    ref_summaries = summarize_context_packet_for_prompt_handoff(packet)
    lanes = sorted({r.lane for r in ref_summaries})
    lane_summaries = tuple(summarize_context_packet_lane_for_handoff(l, tuple(r for r in ref_summaries if r.lane == l)) for l in lanes)
    source_kind_summary: dict[str, int] = {}
    safety_gaps: list[str] = []
    for r in ref_summaries:
        source_kind_summary[r.source_kind or "unknown"] = source_kind_summary.get(r.source_kind or "unknown", 0) + 1
        if r.safety_contract_valid is False:
            safety_gaps.append(f"{r.ref_id}:safety_contract_invalid")

    manifest = ContextPromptHandoffManifest(
        manifest_id=f"handoff:{packet.context_packet_id}",
        packet_id=packet.context_packet_id,
        packet_scope=packet.packet_scope,
        packet_created_at=packet.created_at.isoformat(),
        handoff_status=_map_status(pre, packet_errors),
        prompt_preflight_status=pre.eligibility_status.value,
        prompt_eligible=pre.prompt_eligible,
        caveated=pre.may_be_prompted_only_with_caveats,
        blocked=not pre.prompt_eligible,
        block_reasons=tuple(packet_errors) + pre.block_reasons,
        caveats=pre.caveats,
        pollution_risk=pre.pollution_risk,
        provenance_complete=pre.provenance_complete,
        included_ref_count=pre.included_ref_count,
        excluded_ref_count=pre.excluded_ref_count,
        lane_summaries=lane_summaries,
        included_ref_summaries=ref_summaries,
        excluded_ref_summaries=tuple({"ref_id": e.ref_id, "lane": e.lane, "reason": e.reason} for e in packet.excluded_refs),
        blocked_ref_ids=pre.blocked_ref_ids,
        high_risk_ref_ids=pre.high_risk_ref_ids,
        privacy_sensitive_ref_ids=pre.privacy_sensitive_ref_ids,
        biometric_or_emotion_ref_ids=pre.biometric_or_emotion_ref_ids,
        raw_retention_ref_ids=pre.raw_retention_ref_ids,
        action_capable_ref_ids=pre.action_capable_ref_ids,
        authority_risk_ref_ids=pre.authority_risk_ref_ids,
        truth_or_contradiction_risk_ref_ids=pre.truth_or_contradiction_risk_ref_ids,
        source_kind_summary=source_kind_summary,
        safety_contract_gap_summary=tuple(safety_gaps),
        provenance_summary="complete" if pre.provenance_complete else "incomplete",
        rationale=pre.rationale,
        digest="",
    )
    return dataclass_replace(manifest, digest=compute_context_prompt_handoff_digest(manifest))


def dataclass_replace(manifest: ContextPromptHandoffManifest, **changes: Any) -> ContextPromptHandoffManifest:
    d = asdict(manifest)
    d.update(changes)
    d["lane_summaries"] = tuple(ContextPromptHandoffLaneSummary(**x) if isinstance(x, dict) else x for x in d["lane_summaries"])
    d["included_ref_summaries"] = tuple(ContextPromptHandoffRefSummary(**x) if isinstance(x, dict) else x for x in d["included_ref_summaries"])
    if isinstance(d.get("boundary"), dict):
        d["boundary"] = ContextPromptHandoffBoundary(**d["boundary"])
    return ContextPromptHandoffManifest(**d)
