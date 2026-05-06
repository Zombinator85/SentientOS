from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.context_packet import ContextPacket
from sentientos.context_hygiene.prompt_constraint_verifier import (
    PromptAssemblyCandidatePlan,
    PromptAssemblyCandidateRef,
    PromptAssemblyConstraintVerification,
    PromptAssemblyConstraintVerificationStatus,
    build_candidate_plan_from_dry_run_envelope,
    verify_prompt_assembly_constraints,
)
from sentientos.context_hygiene.prompt_dry_run_envelope import ContextPromptDryRunEnvelope, build_context_prompt_dry_run_envelope
from sentientos.context_hygiene.prompt_handoff_manifest import build_context_prompt_handoff_manifest
from sentientos.context_hygiene.prompt_preflight import PromptContextEligibility


class PromptAssemblyAdapterStatus:
    ADAPTER_READY = "adapter_ready"
    ADAPTER_READY_WITH_WARNINGS = "adapter_ready_with_warnings"
    ADAPTER_BLOCKED = "adapter_blocked"
    ADAPTER_NOT_APPLICABLE = "adapter_not_applicable"
    ADAPTER_INVALID_VERIFICATION = "adapter_invalid_verification"
    ADAPTER_INVALID_CANDIDATE_PLAN = "adapter_invalid_candidate_plan"


@dataclass(frozen=True)
class PromptAssemblyAdapterRef:
    ref_id: str
    ref_type: str
    lane: str
    content_summary: str
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)
    source_kind: str = ""
    privacy_posture: str = ""
    pollution_risk: str = ""
    caveats: tuple[str, ...] = field(default_factory=tuple)
    safety_summary: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptAssemblyAdapterSection:
    section_id: str
    section_kind: str
    ref_ids: tuple[str, ...] = field(default_factory=tuple)
    summary: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptAssemblyAdapterBoundary:
    non_authoritative: bool = True
    adapter_contract_only: bool = True
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
class PromptAssemblyAdapterConstraint:
    name: str
    value: Any


@dataclass(frozen=True)
class PromptAssemblyAdapterPayload:
    adapter_payload_id: str
    candidate_plan_id: str
    envelope_id: str
    envelope_digest: str
    packet_id: str
    packet_scope: str
    adapter_status: str
    verification_status: str
    verified: bool
    warnings: tuple[Mapping[str, str], ...]
    violations: tuple[Mapping[str, str], ...]
    assembly_constraints: Mapping[str, Any]
    adapter_sections: tuple[PromptAssemblyAdapterSection, ...]
    adapter_refs: tuple[PromptAssemblyAdapterRef, ...]
    preserved_caveats: tuple[str, ...]
    provenance_notes: Mapping[str, Any]
    privacy_notes: Mapping[str, Any]
    truth_notes: Mapping[str, Any]
    safety_notes: Mapping[str, Any]
    non_authoritative: bool
    rationale: str
    boundary: PromptAssemblyAdapterBoundary = field(default_factory=PromptAssemblyAdapterBoundary)
    adapter_contract_only: bool = True
    does_not_assemble_prompt: bool = True
    does_not_contain_final_prompt_text: bool = True
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True
    digest: str = ""


_STATUS_MAP = {
    PromptAssemblyConstraintVerificationStatus.CONSTRAINT_VERIFIED: PromptAssemblyAdapterStatus.ADAPTER_READY,
    PromptAssemblyConstraintVerificationStatus.CONSTRAINT_VERIFIED_WITH_WARNINGS: PromptAssemblyAdapterStatus.ADAPTER_READY_WITH_WARNINGS,
    PromptAssemblyConstraintVerificationStatus.CONSTRAINT_FAILED: PromptAssemblyAdapterStatus.ADAPTER_BLOCKED,
    PromptAssemblyConstraintVerificationStatus.CONSTRAINT_NOT_APPLICABLE: PromptAssemblyAdapterStatus.ADAPTER_NOT_APPLICABLE,
    PromptAssemblyConstraintVerificationStatus.CONSTRAINT_INVALID_ENVELOPE: PromptAssemblyAdapterStatus.ADAPTER_INVALID_VERIFICATION,
    PromptAssemblyConstraintVerificationStatus.CONSTRAINT_INVALID_CANDIDATE_PLAN: PromptAssemblyAdapterStatus.ADAPTER_INVALID_CANDIDATE_PLAN,
}
_READY_VERIFICATION_STATUSES = {
    PromptAssemblyConstraintVerificationStatus.CONSTRAINT_VERIFIED,
    PromptAssemblyConstraintVerificationStatus.CONSTRAINT_VERIFIED_WITH_WARNINGS,
}
_ALLOWED_SECTION_KINDS = (
    "adapter_context_refs",
    "adapter_diagnostic_refs",
    "adapter_evidence_refs",
    "adapter_embodiment_refs",
    "adapter_caveat_requirements",
    "adapter_provenance_boundaries",
    "adapter_privacy_boundaries",
    "adapter_truth_boundaries",
    "adapter_safety_boundaries",
    "adapter_constraint_summary",
)
_FORBIDDEN_RAW_KEYS = frozenset(
    {
        "raw_payload",
        "raw_memory_payload",
        "raw_screen_payload",
        "raw_audio_payload",
        "raw_vision_payload",
        "raw_multimodal_payload",
        "screen_frame",
        "mic_audio",
        "audio_payload",
        "vision_frame",
        "multimodal_raw_data",
        "browser_control_data",
        "mouse_control_data",
        "keyboard_control_data",
        "hidden_chain_of_thought",
        "chain_of_thought",
    }
)
_FORBIDDEN_PROMPT_TEXT_KEYS = frozenset({"prompt_text", "final_prompt_text", "assembled_prompt", "rendered_prompt", "system_prompt", "developer_prompt"})
_RUNTIME_AUTHORITY_KEYS = frozenset(
    {
        "execution_handle",
        "action_handle",
        "retention_handle",
        "retrieval_handle",
        "browser_handle",
        "mouse_handle",
        "keyboard_handle",
        "memory_write",
        "can_write_memory",
        "write_memory",
        "memory_write_capability",
        "retention_commit",
        "can_commit_retention",
        "commit_retention",
        "retention_commit_capability",
        "feedback_trigger",
        "can_trigger_feedback",
        "trigger_feedback",
        "feedback_trigger_capability",
        "execute_action",
        "action_execution",
        "can_execute_action",
        "action_execution_capability",
        "route_work",
        "admit_work",
        "execute_work",
        "can_route_work",
        "can_admit_work",
        "can_execute_work",
        "can_fulfill_work",
        "can_route",
        "can_admit",
        "can_execute",
        "llm_params",
        "llm_parameters",
        "model_params",
        "provider_params",
    }
)


def _is_dataclass_instance(value: Any) -> bool:
    return is_dataclass(value) and not isinstance(value, type)


def _stable(value: Any) -> Any:
    if _is_dataclass_instance(value):
        return {k: _stable(v) for k, v in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(k): _stable(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_stable(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_stable(v) for v in value)
    return value


def _walk(value: Any) -> Sequence[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []

    def rec(child: Any) -> None:
        if _is_dataclass_instance(child):
            rec(asdict(child))
        elif isinstance(child, Mapping):
            for key, nested in child.items():
                found.append((str(key), nested))
                rec(nested)
        elif isinstance(child, (tuple, list, set, frozenset)):
            for nested in child:
                rec(nested)

    rec(value)
    return tuple(found)


def _issue_dict(issue: Any) -> Mapping[str, str]:
    return {"code": str(issue.code), "detail": str(issue.detail), "ref_id": str(issue.ref_id)}


def _candidate_refs(candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any]) -> tuple[Any, ...]:
    refs = candidate_plan.candidate_refs if isinstance(candidate_plan, PromptAssemblyCandidatePlan) else candidate_plan.get("candidate_refs", ())
    return tuple(refs) if isinstance(refs, (tuple, list)) else ()


def _mapping(value: Any) -> Mapping[str, Any]:
    if _is_dataclass_instance(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return value
    return {}


def map_prompt_verification_status_to_adapter_status(status: str) -> str:
    return _STATUS_MAP.get(status, PromptAssemblyAdapterStatus.ADAPTER_INVALID_VERIFICATION)


def summarize_adapter_ref(ref: PromptAssemblyCandidateRef | Mapping[str, Any]) -> PromptAssemblyAdapterRef:
    data = _mapping(ref)
    safety_summary = data.get("safety_summary", {})
    return PromptAssemblyAdapterRef(
        ref_id=str(data.get("ref_id", "")),
        ref_type=str(data.get("ref_type", "")),
        lane=str(data.get("lane", "")),
        content_summary=str(data.get("content_summary", "")),
        provenance_refs=tuple(str(v) for v in data.get("provenance_refs", ())),
        source_kind=str(data.get("source_kind", "")),
        privacy_posture=str(data.get("privacy_posture", "")),
        pollution_risk=str(data.get("pollution_risk", "")),
        caveats=tuple(str(v) for v in data.get("caveats", ())),
        safety_summary=dict(safety_summary) if isinstance(safety_summary, Mapping) else {},
    )


def _adapter_refs_allowed(verification: PromptAssemblyConstraintVerification) -> bool:
    return verification.status in _READY_VERIFICATION_STATUSES


def _section(section_kind: str, ref_ids: tuple[str, ...] = (), **summary: Any) -> PromptAssemblyAdapterSection:
    return PromptAssemblyAdapterSection(section_id=f"section:{section_kind}", section_kind=section_kind, ref_ids=ref_ids, summary=summary)


def _build_sections(candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any], adapter_refs: tuple[PromptAssemblyAdapterRef, ...]) -> tuple[PromptAssemblyAdapterSection, ...]:
    plan = _mapping(candidate_plan)
    ref_ids = tuple(ref.ref_id for ref in adapter_refs)
    sections: list[PromptAssemblyAdapterSection] = [
        _section("adapter_context_refs", ref_ids, ref_count=len(adapter_refs)),
        _section("adapter_diagnostic_refs", (), diagnostic_markers=plan.get("diagnostic_markers", {})),
        _section("adapter_evidence_refs", tuple(ref.ref_id for ref in adapter_refs if ref.lane == "evidence" or ref.ref_type == "evidence")),
        _section("adapter_embodiment_refs", tuple(ref.ref_id for ref in adapter_refs if ref.lane == "embodiment" or ref.ref_type == "embodiment")),
        _section("adapter_caveat_requirements", (), preserved_caveats=tuple(plan.get("preserved_caveats", ()))),
        _section("adapter_provenance_boundaries", ref_ids, provenance_notes=plan.get("provenance_notes", {})),
        _section("adapter_privacy_boundaries", ref_ids, privacy_notes=plan.get("privacy_notes", {})),
        _section("adapter_truth_boundaries", ref_ids, truth_notes=plan.get("truth_notes", {})),
        _section("adapter_safety_boundaries", ref_ids, safety_notes=plan.get("safety_notes", {})),
        _section("adapter_constraint_summary", (), assembly_constraints=plan.get("preserved_constraints", {})),
    ]
    return tuple(s for s in sections if s.section_kind in _ALLOWED_SECTION_KINDS)


def summarize_verified_candidate_plan_for_adapter(
    verification: PromptAssemblyConstraintVerification,
    candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any],
) -> dict[str, Any]:
    refs = tuple(summarize_adapter_ref(ref) for ref in _candidate_refs(candidate_plan)) if _adapter_refs_allowed(verification) else ()
    plan = _mapping(candidate_plan)
    return {
        "plan_id": str(plan.get("plan_id", "")),
        "envelope_id": str(plan.get("envelope_id", "")),
        "packet_id": str(plan.get("packet_id", "")),
        "adapter_ref_count": len(refs),
        "adapter_status": map_prompt_verification_status_to_adapter_status(verification.status),
        "verification_status": verification.status,
    }


def compute_prompt_adapter_payload_digest(payload: PromptAssemblyAdapterPayload | Mapping[str, Any]) -> str:
    stable = _stable(payload)
    if isinstance(stable, dict):
        stable.pop("digest", None)
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _with_digest(payload: PromptAssemblyAdapterPayload) -> PromptAssemblyAdapterPayload:
    data = asdict(payload)
    data["digest"] = compute_prompt_adapter_payload_digest(payload)
    data["adapter_sections"] = tuple(PromptAssemblyAdapterSection(**item) for item in data["adapter_sections"])
    data["adapter_refs"] = tuple(PromptAssemblyAdapterRef(**item) for item in data["adapter_refs"])
    data["boundary"] = PromptAssemblyAdapterBoundary(**data["boundary"])
    return PromptAssemblyAdapterPayload(**data)


def build_prompt_assembly_adapter_payload(
    verification: PromptAssemblyConstraintVerification,
    candidate_plan: PromptAssemblyCandidatePlan | Mapping[str, Any],
) -> PromptAssemblyAdapterPayload:
    plan = _mapping(candidate_plan)
    adapter_status = map_prompt_verification_status_to_adapter_status(verification.status)
    adapter_refs = tuple(summarize_adapter_ref(ref) for ref in _candidate_refs(candidate_plan)) if _adapter_refs_allowed(verification) else ()
    payload = PromptAssemblyAdapterPayload(
        adapter_payload_id=f"adapter-payload:{verification.plan_id or plan.get('plan_id', '')}",
        candidate_plan_id=str(plan.get("plan_id", verification.plan_id)),
        envelope_id=str(plan.get("envelope_id", verification.envelope_id)),
        envelope_digest=str(plan.get("envelope_digest", "")),
        packet_id=str(plan.get("packet_id", "")),
        packet_scope=str(plan.get("packet_scope", "")),
        adapter_status=adapter_status,
        verification_status=verification.status,
        verified=verification.status in _READY_VERIFICATION_STATUSES,
        warnings=tuple(_issue_dict(w) for w in verification.warnings),
        violations=tuple(_issue_dict(v) for v in verification.violations),
        assembly_constraints=dict(plan.get("preserved_constraints", {})),
        adapter_sections=(),
        adapter_refs=adapter_refs,
        preserved_caveats=tuple(plan.get("preserved_caveats", ())),
        provenance_notes=dict(plan.get("provenance_notes", {})),
        privacy_notes=dict(plan.get("privacy_notes", {})),
        truth_notes=dict(plan.get("truth_notes", {})),
        safety_notes=dict(plan.get("safety_notes", {})),
        non_authoritative=bool(plan.get("non_authoritative", False)),
        rationale=verification.rationale or adapter_status,
    )
    payload = _with_digest(
        PromptAssemblyAdapterPayload(
            **{**asdict(payload), "adapter_sections": _build_sections(candidate_plan, adapter_refs), "boundary": payload.boundary, "adapter_refs": adapter_refs}
        )
    )
    return payload


def build_prompt_assembly_adapter_payload_from_envelope(envelope: ContextPromptDryRunEnvelope) -> PromptAssemblyAdapterPayload:
    candidate_plan = build_candidate_plan_from_dry_run_envelope(envelope)
    verification = verify_prompt_assembly_constraints(envelope, candidate_plan)
    return build_prompt_assembly_adapter_payload(verification, candidate_plan)


def build_prompt_assembly_adapter_payload_from_packet(packet: ContextPacket, preflight: PromptContextEligibility | None = None) -> PromptAssemblyAdapterPayload:
    manifest = build_context_prompt_handoff_manifest(packet, preflight)
    envelope = build_context_prompt_dry_run_envelope(manifest)
    return build_prompt_assembly_adapter_payload_from_envelope(envelope)


def adapter_payload_contains_no_prompt_text(payload: PromptAssemblyAdapterPayload | Mapping[str, Any]) -> bool:
    return not any(key in _FORBIDDEN_PROMPT_TEXT_KEYS for key, _ in _walk(payload))


def adapter_payload_contains_no_raw_payloads(payload: PromptAssemblyAdapterPayload | Mapping[str, Any]) -> bool:
    return not any(key in _FORBIDDEN_RAW_KEYS for key, _ in _walk(payload))


def adapter_payload_has_no_runtime_authority(payload: PromptAssemblyAdapterPayload | Mapping[str, Any]) -> bool:
    markers = _mapping(payload)
    marker_names = tuple(PromptAssemblyAdapterBoundary.__dataclass_fields__.keys())
    if any(markers.get(name) is not True for name in marker_names if name != "non_authoritative"):
        return False
    return not any(key in _RUNTIME_AUTHORITY_KEYS and bool(value) for key, value in _walk(payload))


def adapter_payload_is_safe_for_future_prompt_assembler(payload: PromptAssemblyAdapterPayload | Mapping[str, Any]) -> bool:
    return (
        adapter_payload_contains_no_prompt_text(payload)
        and adapter_payload_contains_no_raw_payloads(payload)
        and adapter_payload_has_no_runtime_authority(payload)
        and bool(_mapping(payload).get("adapter_contract_only", False))
    )


def explain_prompt_adapter_block(payload: PromptAssemblyAdapterPayload) -> tuple[str, ...]:
    if payload.violations:
        return tuple(f"{v['code']}:{v['ref_id']}:{v['detail']}" if v.get("ref_id") else f"{v['code']}:{v['detail']}" for v in payload.violations)
    if payload.adapter_status not in {PromptAssemblyAdapterStatus.ADAPTER_READY, PromptAssemblyAdapterStatus.ADAPTER_READY_WITH_WARNINGS}:
        return (payload.adapter_status,)
    return ()


def summarize_prompt_adapter_payload(payload: PromptAssemblyAdapterPayload) -> dict[str, Any]:
    return {
        "adapter_payload_id": payload.adapter_payload_id,
        "candidate_plan_id": payload.candidate_plan_id,
        "envelope_id": payload.envelope_id,
        "packet_id": payload.packet_id,
        "adapter_status": payload.adapter_status,
        "verification_status": payload.verification_status,
        "adapter_ref_count": len(payload.adapter_refs),
        "warning_count": len(payload.warnings),
        "violation_count": len(payload.violations),
        "digest": payload.digest,
    }
