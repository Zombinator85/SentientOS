from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any, Mapping

from sentientos.context_hygiene.prompt_handoff_manifest import (
    ContextPromptHandoffLaneSummary,
    ContextPromptHandoffManifest,
    ContextPromptHandoffRefSummary,
    ContextPromptHandoffStatus,
)


class ContextPromptDryRunStatus:
    DRY_RUN_READY = "dry_run_ready"
    DRY_RUN_READY_WITH_CAVEATS = "dry_run_ready_with_caveats"
    DRY_RUN_BLOCKED = "dry_run_blocked"
    DRY_RUN_NOT_APPLICABLE = "dry_run_not_applicable"
    DRY_RUN_INVALID_MANIFEST = "dry_run_invalid_manifest"


@dataclass(frozen=True)
class ContextPromptDryRunNoRuntimeMarkers:
    does_not_assemble_prompt: bool = True
    does_not_contain_final_prompt_text: bool = True
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True


@dataclass(frozen=True)
class ContextPromptDryRunSectionSummary:
    section_id: str
    lane: str
    ref_type: str
    admissible_ref_count: int
    highest_pollution_risk: str
    provenance_complete: bool
    source_kinds: tuple[str, ...]
    caveats: tuple[str, ...]
    blocked_or_unsafe_count: int
    rationale: str


@dataclass(frozen=True)
class ContextPromptDryRunRefSummary:
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
class ContextPromptDryRunEnvelope:
    envelope_id: str
    manifest_id: str
    manifest_digest: str
    packet_id: str
    packet_scope: str
    handoff_status: str
    dry_run_status: str
    assembly_constraints: Mapping[str, Any]
    section_summaries: tuple[ContextPromptDryRunSectionSummary, ...]
    admissible_ref_summaries: tuple[ContextPromptDryRunRefSummary, ...]
    block_reasons: tuple[str, ...]
    caveats: tuple[str, ...]
    source_kind_summary: Mapping[str, int]
    safety_contract_gap_summary: tuple[str, ...]
    provenance_summary: str
    rationale: str
    no_runtime_markers: ContextPromptDryRunNoRuntimeMarkers = field(default_factory=ContextPromptDryRunNoRuntimeMarkers)
    digest: str = ""


_STATUS_MAP = {
    ContextPromptHandoffStatus.HANDOFF_READY: ContextPromptDryRunStatus.DRY_RUN_READY,
    ContextPromptHandoffStatus.HANDOFF_READY_WITH_CAVEATS: ContextPromptDryRunStatus.DRY_RUN_READY_WITH_CAVEATS,
    ContextPromptHandoffStatus.HANDOFF_BLOCKED: ContextPromptDryRunStatus.DRY_RUN_BLOCKED,
    ContextPromptHandoffStatus.HANDOFF_NOT_APPLICABLE: ContextPromptDryRunStatus.DRY_RUN_NOT_APPLICABLE,
    ContextPromptHandoffStatus.HANDOFF_INVALID_PACKET: ContextPromptDryRunStatus.DRY_RUN_INVALID_MANIFEST,
}

_RUNTIME_MARKER_NAMES = tuple(ContextPromptDryRunNoRuntimeMarkers.__dataclass_fields__.keys())
_ADMISSIBLE_STATUSES = {
    ContextPromptDryRunStatus.DRY_RUN_READY,
    ContextPromptDryRunStatus.DRY_RUN_READY_WITH_CAVEATS,
}
_FORBIDDEN_PAYLOAD_KEYS = frozenset({"raw_payload", "prompt_text", "final_prompt_text", "llm_params", "execution_handle"})


def map_handoff_status_to_prompt_dry_run_status(handoff_status: str) -> str:
    return _STATUS_MAP.get(handoff_status, ContextPromptDryRunStatus.DRY_RUN_INVALID_MANIFEST)


def _clean_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {str(k): v for k, v in mapping.items() if str(k) not in _FORBIDDEN_PAYLOAD_KEYS}


def summarize_handoff_lane_for_prompt_dry_run(lane: ContextPromptHandoffLaneSummary) -> ContextPromptDryRunSectionSummary:
    return ContextPromptDryRunSectionSummary(
        section_id=f"section:{lane.lane}",
        lane=lane.lane,
        ref_type=lane.ref_type,
        admissible_ref_count=lane.count,
        highest_pollution_risk=lane.highest_pollution_risk,
        provenance_complete=lane.provenance_complete,
        source_kinds=lane.source_kinds,
        caveats=lane.caveats,
        blocked_or_unsafe_count=lane.blocked_or_unsafe_count,
        rationale=lane.rationale,
    )


def summarize_handoff_ref_for_prompt_dry_run(ref: ContextPromptHandoffRefSummary) -> ContextPromptDryRunRefSummary:
    return ContextPromptDryRunRefSummary(
        ref_id=ref.ref_id,
        ref_type=ref.ref_type,
        lane=ref.lane,
        scope_id=ref.scope_id,
        content_summary=ref.content_summary,
        provenance_refs=ref.provenance_refs,
        provenance_status=ref.provenance_status,
        pollution_risk=ref.pollution_risk,
        freshness_status=ref.freshness_status,
        contradiction_status=ref.contradiction_status,
        source_kind=ref.source_kind,
        privacy_posture=ref.privacy_posture,
        safety_metadata_summary=_clean_mapping(ref.safety_metadata_summary),
        safety_contract_valid=ref.safety_contract_valid,
        caveats=ref.caveats,
    )


def _assembly_constraints(manifest: ContextPromptHandoffManifest, dry_run_status: str) -> dict[str, Any]:
    return {
        "source_artifact": "phase67_context_prompt_handoff_manifest",
        "source_manifest_id": manifest.manifest_id,
        "source_manifest_digest": manifest.digest,
        "dry_run_status": dry_run_status,
        "pure": True,
        "non_authoritative": True,
        "non_executing": True,
        "uses_handoff_manifest_only": True,
        "does_not_assemble_prompt": True,
        "does_not_contain_final_prompt_text": True,
        "admissible_refs_available_only_when_ready_or_caveated": True,
        "blocked_not_applicable_or_invalid_refs_are_withheld": True,
    }


def compute_context_prompt_dry_run_envelope_digest(envelope: ContextPromptDryRunEnvelope) -> str:
    stable = asdict(envelope)
    stable.pop("digest", None)
    payload = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dry_run_envelope_has_no_runtime_authority(envelope: ContextPromptDryRunEnvelope) -> bool:
    markers = envelope.no_runtime_markers
    return all(bool(getattr(markers, name)) for name in _RUNTIME_MARKER_NAMES)


def dry_run_envelope_contains_no_prompt_text(envelope: ContextPromptDryRunEnvelope) -> bool:
    def walk(value: Any) -> bool:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if str(key) in _FORBIDDEN_PAYLOAD_KEYS:
                    return False
                if not walk(child):
                    return False
        elif isinstance(value, (tuple, list)):
            return all(walk(child) for child in value)
        return True

    return walk(asdict(envelope))


def summarize_context_prompt_dry_run_envelope(envelope: ContextPromptDryRunEnvelope) -> dict[str, Any]:
    return {
        "envelope_id": envelope.envelope_id,
        "manifest_id": envelope.manifest_id,
        "manifest_digest": envelope.manifest_digest,
        "packet_id": envelope.packet_id,
        "packet_scope": envelope.packet_scope,
        "handoff_status": envelope.handoff_status,
        "dry_run_status": envelope.dry_run_status,
        "admissible_ref_count": len(envelope.admissible_ref_summaries),
        "digest": envelope.digest,
    }


def build_context_prompt_dry_run_envelope(manifest: ContextPromptHandoffManifest) -> ContextPromptDryRunEnvelope:
    dry_run_status = map_handoff_status_to_prompt_dry_run_status(manifest.handoff_status)
    ref_summaries: tuple[ContextPromptDryRunRefSummary, ...] = ()
    if dry_run_status in _ADMISSIBLE_STATUSES:
        ref_summaries = tuple(summarize_handoff_ref_for_prompt_dry_run(ref) for ref in manifest.included_ref_summaries)

    envelope = ContextPromptDryRunEnvelope(
        envelope_id=f"dry-run:{manifest.manifest_id}",
        manifest_id=manifest.manifest_id,
        manifest_digest=manifest.digest,
        packet_id=manifest.packet_id,
        packet_scope=manifest.packet_scope,
        handoff_status=manifest.handoff_status,
        dry_run_status=dry_run_status,
        assembly_constraints=_assembly_constraints(manifest, dry_run_status),
        section_summaries=tuple(summarize_handoff_lane_for_prompt_dry_run(lane) for lane in manifest.lane_summaries),
        admissible_ref_summaries=ref_summaries,
        block_reasons=manifest.block_reasons,
        caveats=manifest.caveats,
        source_kind_summary=dict(manifest.source_kind_summary),
        safety_contract_gap_summary=manifest.safety_contract_gap_summary,
        provenance_summary=manifest.provenance_summary,
        rationale=manifest.rationale,
        digest="",
    )
    return _replace_envelope(envelope, digest=compute_context_prompt_dry_run_envelope_digest(envelope))


def _replace_envelope(envelope: ContextPromptDryRunEnvelope, **changes: Any) -> ContextPromptDryRunEnvelope:
    data = asdict(envelope)
    data.update(changes)
    data["section_summaries"] = tuple(
        ContextPromptDryRunSectionSummary(**item) if isinstance(item, dict) else item
        for item in data["section_summaries"]
    )
    data["admissible_ref_summaries"] = tuple(
        ContextPromptDryRunRefSummary(**item) if isinstance(item, dict) else item
        for item in data["admissible_ref_summaries"]
    )
    if isinstance(data.get("no_runtime_markers"), dict):
        data["no_runtime_markers"] = ContextPromptDryRunNoRuntimeMarkers(**data["no_runtime_markers"])
    return ContextPromptDryRunEnvelope(**data)
