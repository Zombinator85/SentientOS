from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import hashlib
import importlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.context_packet import ContextPacket
from sentientos.context_hygiene.prompt_adapter_contract import (
    PromptAssemblyAdapterPayload,
    build_prompt_assembly_adapter_payload,
    build_prompt_assembly_adapter_payload_from_packet,
    compute_prompt_adapter_payload_digest,
)
from sentientos.context_hygiene.prompt_constraint_verifier import (
    PromptAssemblyCandidatePlan,
    PromptAssemblyConstraintVerification,
    build_candidate_plan_from_dry_run_envelope,
    verify_prompt_assembly_constraints,
)
from sentientos.context_hygiene.prompt_dry_run_envelope import build_context_prompt_dry_run_envelope
from sentientos.context_hygiene.prompt_handoff_manifest import build_context_prompt_handoff_manifest
from sentientos.context_hygiene.prompt_preflight import PromptContextEligibility


class PromptMaterializationAuditStatus:
    AUDIT_READY_FOR_SHADOW_MATERIALIZATION = "audit_ready_for_shadow_materialization"
    AUDIT_READY_WITH_WARNINGS = "audit_ready_with_warnings"
    AUDIT_BLOCKED = "audit_blocked"
    AUDIT_NOT_APPLICABLE = "audit_not_applicable"
    AUDIT_INVALID_BLUEPRINT = "audit_invalid_blueprint"
    AUDIT_INVALID_CHAIN = "audit_invalid_chain"
    AUDIT_RUNTIME_WIRING_DETECTED = "audit_runtime_wiring_detected"


@dataclass(frozen=True)
class PromptMaterializationAuditFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class PromptMaterializationAuditBoundary:
    non_authoritative: bool = True
    audit_receipt_only: bool = True
    attestation_only: bool = True
    prompt_materialization_precondition_only: bool = True
    does_not_materialize_prompt_text: bool = True
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
class PromptMaterializationAuditDigestChain:
    packet_id: str = ""
    packet_scope: str = ""
    manifest_id: str = ""
    manifest_digest: str = ""
    envelope_id: str = ""
    envelope_digest: str = ""
    candidate_plan_id: str = ""
    candidate_plan_digest: str = ""
    verification_status: str = ""
    verification_digest: str = ""
    adapter_payload_id: str = ""
    adapter_payload_digest: str = ""
    shadow_preview_id: str = ""
    shadow_preview_digest: str = ""
    shadow_blueprint_id: str = ""
    shadow_blueprint_digest: str = ""
    complete: bool = False
    missing: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PromptMaterializationAuditReceipt:
    receipt_id: str
    audit_status: str
    blueprint_id: str
    blueprint_digest: str
    adapter_payload_id: str
    adapter_status: str
    compliance_status: str
    preview_status: str
    blueprint_status: str
    packet_id: str
    packet_scope: str
    manifest_id: str
    manifest_digest: str
    envelope_id: str
    envelope_digest: str
    candidate_plan_id: str
    candidate_plan_digest: str
    adapter_payload_digest: str
    verification_digest: str
    shadow_preview_digest: str
    shadow_blueprint_digest: str
    digest_chain_complete: bool
    digest_chain: PromptMaterializationAuditDigestChain
    boundary_summary: Mapping[str, Any]
    preserved_caveats: tuple[str, ...]
    warnings: tuple[Mapping[str, str], ...]
    violations: tuple[Mapping[str, str], ...]
    findings: tuple[PromptMaterializationAuditFinding, ...]
    provenance_summary: Mapping[str, Any]
    privacy_summary: Mapping[str, Any]
    truth_summary: Mapping[str, Any]
    safety_summary: Mapping[str, Any]
    source_kind_summary: Mapping[str, int]
    ref_counts: Mapping[str, int]
    section_counts: Mapping[str, int]
    rationale: str
    receipt_digest: str
    boundary: PromptMaterializationAuditBoundary = field(default_factory=PromptMaterializationAuditBoundary)
    audit_receipt_only: bool = True
    attestation_only: bool = True
    does_not_materialize_prompt_text: bool = True
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
class PromptMaterializationAuditReceiptSummary:
    receipt_id: str
    audit_status: str
    blueprint_id: str
    adapter_payload_id: str
    packet_id: str
    digest_chain_complete: bool
    finding_count: int
    warning_count: int
    violation_count: int
    allows_shadow_materializer: bool
    receipt_digest: str


_BLUEPRINT_STATUS_MAP = {
    "shadow_blueprint_ready": PromptMaterializationAuditStatus.AUDIT_READY_FOR_SHADOW_MATERIALIZATION,
    "shadow_blueprint_ready_with_warnings": PromptMaterializationAuditStatus.AUDIT_READY_WITH_WARNINGS,
    "shadow_blueprint_blocked": PromptMaterializationAuditStatus.AUDIT_BLOCKED,
    "shadow_blueprint_not_applicable": PromptMaterializationAuditStatus.AUDIT_NOT_APPLICABLE,
    "shadow_blueprint_invalid_adapter_payload": PromptMaterializationAuditStatus.AUDIT_INVALID_BLUEPRINT,
    "shadow_blueprint_runtime_wiring_detected": PromptMaterializationAuditStatus.AUDIT_RUNTIME_WIRING_DETECTED,
}
_READY_AUDIT_STATUSES = {
    PromptMaterializationAuditStatus.AUDIT_READY_FOR_SHADOW_MATERIALIZATION,
    PromptMaterializationAuditStatus.AUDIT_READY_WITH_WARNINGS,
}
_REQUIRED_NON_RUNTIME_MARKERS = (
    "audit_receipt_only",
    "attestation_only",
    "does_not_materialize_prompt_text",
    "does_not_assemble_prompt",
    "does_not_contain_final_prompt_text",
    "does_not_call_llm",
    "does_not_retrieve_memory",
    "does_not_write_memory",
    "does_not_trigger_feedback",
    "does_not_commit_retention",
    "does_not_execute_or_route_work",
    "does_not_admit_work",
)
_FORBIDDEN_RAW_KEYS = frozenset(
    {
        "raw_payload",
        "raw_memory_payload",
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
_FORBIDDEN_PROMPT_TEXT_KEYS = frozenset(
    {"prompt_text", "final_prompt_text", "assembled_prompt", "system_prompt", "developer_prompt"}
)
_RUNTIME_AUTHORITY_KEYS = frozenset(
    {
        "execution_handle",
        "action_handle",
        "retention_handle",
        "retrieval_handle",
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
        "can_route",
        "can_admit",
        "can_execute",
        "llm_params",
        "llm_parameters",
    }
)


def _is_dataclass_instance(value: Any) -> bool:
    return is_dataclass(value) and not isinstance(value, type)


def _mapping(value: Any) -> Mapping[str, Any]:
    if _is_dataclass_instance(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return value
    return {}


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


def _truthy_forbidden(value: Any) -> bool:
    return bool(value)


def _finding(code: str, detail: str, severity: str = "blocker") -> PromptMaterializationAuditFinding:
    return PromptMaterializationAuditFinding(code=code, detail=detail, severity=severity)


def _issue_tuple(value: Any) -> tuple[Mapping[str, str], ...]:
    out: list[Mapping[str, str]] = []
    raw = value if isinstance(value, (tuple, list)) else ()
    for issue in raw:
        data = _mapping(issue)
        if data:
            out.append({"code": str(data.get("code", "")), "detail": str(data.get("detail", "")), "ref_id": str(data.get("ref_id", ""))})
        else:
            out.append({"code": str(issue), "detail": "", "ref_id": ""})
    return tuple(out)


def _as_tuple_str(value: Any) -> tuple[str, ...]:
    return tuple(str(v) for v in value) if isinstance(value, (tuple, list)) else ()


def _module_prompt_assembler() -> Any:
    return importlib.import_module("prompt_assembler")


def _get_adapter_digest(adapter_payload: PromptAssemblyAdapterPayload | Mapping[str, Any] | None) -> str:
    if adapter_payload is None:
        return ""
    data = _mapping(adapter_payload)
    digest = str(data.get("digest", ""))
    return digest or compute_prompt_adapter_payload_digest(adapter_payload)


def _source_kind_counts(blueprint_data: Mapping[str, Any], adapter_data: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    refs = blueprint_data.get("blueprint_refs", ()) or adapter_data.get("adapter_refs", ()) or ()
    if not isinstance(refs, (tuple, list)):
        return counts
    for ref in refs:
        source_kind = str(_mapping(ref).get("source_kind", "") or "unknown")
        counts[source_kind] = counts.get(source_kind, 0) + 1
    return counts


def _note_summary(adapter_data: Mapping[str, Any], blueprint_data: Mapping[str, Any], note_name: str, present_name: str) -> Mapping[str, Any]:
    notes = adapter_data.get(note_name, {})
    if isinstance(notes, Mapping) and notes:
        return dict(notes)
    return {"notes_present": bool(blueprint_data.get(present_name, False))}


def _boundary_summary(blueprint_data: Mapping[str, Any], preview_data: Mapping[str, Any], adapter_data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "non_authoritative": bool(adapter_data.get("non_authoritative", True)),
        "shadow_blueprint_only": bool(blueprint_data.get("shadow_blueprint_only", True)),
        "shadow_hook_only": bool(preview_data.get("shadow_hook_only", True)) if preview_data else True,
        "may_future_assembler_consume": bool(blueprint_data.get("may_future_assembler_consume", False)),
        "must_block_prompt_materialization": bool(blueprint_data.get("must_block_prompt_materialization", True)),
        "provenance_notes_present": bool(blueprint_data.get("provenance_notes_present", False)),
        "privacy_notes_present": bool(blueprint_data.get("privacy_notes_present", False)),
        "truth_notes_present": bool(blueprint_data.get("truth_notes_present", False)),
        "safety_notes_present": bool(blueprint_data.get("safety_notes_present", False)),
        "does_not_materialize_prompt_text": True,
        "does_not_assemble_prompt": bool(blueprint_data.get("does_not_assemble_prompt", True)),
        "does_not_contain_final_prompt_text": bool(blueprint_data.get("does_not_contain_final_prompt_text", True)),
        "does_not_call_llm": bool(blueprint_data.get("does_not_call_llm", True)),
        "does_not_retrieve_memory": bool(blueprint_data.get("does_not_retrieve_memory", True)),
        "does_not_write_memory": bool(blueprint_data.get("does_not_write_memory", True)),
        "does_not_trigger_feedback": bool(blueprint_data.get("does_not_trigger_feedback", True)),
        "does_not_commit_retention": bool(blueprint_data.get("does_not_commit_retention", True)),
        "does_not_execute_or_route_work": bool(blueprint_data.get("does_not_execute_or_route_work", True)),
        "does_not_admit_work": bool(blueprint_data.get("does_not_admit_work", True)),
    }


def _chain_and_findings(
    blueprint_data: Mapping[str, Any],
    adapter_data: Mapping[str, Any],
    preview_data: Mapping[str, Any],
    verification_data: Mapping[str, Any],
) -> tuple[PromptMaterializationAuditDigestChain, tuple[PromptMaterializationAuditFinding, ...]]:
    constraints = adapter_data.get("assembly_constraints", {}) if adapter_data else blueprint_data.get("assembly_constraints", {})
    constraint_map = dict(constraints) if isinstance(constraints, Mapping) else {}
    missing: list[str] = []
    findings: list[PromptMaterializationAuditFinding] = []

    blueprint_id = str(blueprint_data.get("blueprint_id", ""))
    blueprint_digest = str(blueprint_data.get("digest", ""))
    adapter_payload_id = str(adapter_data.get("adapter_payload_id", blueprint_data.get("adapter_payload_id", "")))
    adapter_digest = _get_adapter_digest(adapter_data) if adapter_data else ""
    packet_id = str(adapter_data.get("packet_id", constraint_map.get("packet_id", "")))
    packet_scope = str(adapter_data.get("packet_scope", constraint_map.get("packet_scope", "")))
    envelope_id = str(adapter_data.get("envelope_id", constraint_map.get("envelope_id", "")))
    envelope_digest = str(adapter_data.get("envelope_digest", constraint_map.get("envelope_digest", "")))
    manifest_id = str(constraint_map.get("source_manifest_id", ""))
    manifest_digest = str(constraint_map.get("source_manifest_digest", ""))
    candidate_plan_id = str(adapter_data.get("candidate_plan_id", ""))
    verification_status = str(adapter_data.get("verification_status", verification_data.get("status", "")))
    preview_id = str(preview_data.get("preview_id", ""))

    required = {
        "blueprint_id": blueprint_id,
        "blueprint_digest": blueprint_digest,
        "adapter_payload_id": adapter_payload_id,
        "packet_id": packet_id,
        "packet_scope": packet_scope,
        "envelope_digest": envelope_digest,
        "adapter_payload_digest": adapter_digest,
    }
    code_map = {
        "blueprint_id": "missing_blueprint_id",
        "blueprint_digest": "missing_blueprint_digest",
        "adapter_payload_id": "missing_adapter_payload_id",
        "packet_id": "missing_packet_id",
        "packet_scope": "missing_packet_scope",
        "envelope_digest": "missing_envelope_digest",
        "adapter_payload_digest": "missing_adapter_payload_digest",
    }
    for name, value in required.items():
        if not value:
            missing.append(name)
            findings.append(_finding(code_map[name], f"required audit chain field {name} is missing"))

    if adapter_data and blueprint_data.get("adapter_payload_id") and adapter_payload_id != str(blueprint_data.get("adapter_payload_id", "")):
        missing.append("adapter_payload_id_mismatch")
        findings.append(_finding("digest_chain_mismatch", "adapter payload id differs from blueprint adapter payload id"))
    if adapter_data and adapter_data.get("digest") and adapter_digest != str(adapter_data.get("digest", "")):
        missing.append("adapter_payload_digest_mismatch")
        findings.append(_finding("digest_chain_mismatch", "computed adapter payload digest differs from stored adapter payload digest"))

    chain = PromptMaterializationAuditDigestChain(
        packet_id=packet_id,
        packet_scope=packet_scope,
        manifest_id=manifest_id,
        manifest_digest=manifest_digest,
        envelope_id=envelope_id,
        envelope_digest=envelope_digest,
        candidate_plan_id=candidate_plan_id,
        candidate_plan_digest="",
        verification_status=verification_status,
        verification_digest="",
        adapter_payload_id=adapter_payload_id,
        adapter_payload_digest=adapter_digest,
        shadow_preview_id=preview_id,
        shadow_preview_digest="",
        shadow_blueprint_id=blueprint_id,
        shadow_blueprint_digest=blueprint_digest,
        complete=not missing,
        missing=tuple(missing),
    )
    if missing:
        findings.append(_finding("digest_chain_incomplete", "required current-contract audit chain fields are missing or inconsistent"))
    return chain, tuple(findings)


def _status_for_blueprint(blueprint_status: str, chain_complete: bool) -> str:
    if not chain_complete:
        return PromptMaterializationAuditStatus.AUDIT_INVALID_CHAIN
    return _BLUEPRINT_STATUS_MAP.get(blueprint_status, PromptMaterializationAuditStatus.AUDIT_INVALID_BLUEPRINT)


def _status_findings(status: str, blueprint_status: str) -> tuple[PromptMaterializationAuditFinding, ...]:
    if status == PromptMaterializationAuditStatus.AUDIT_BLOCKED:
        return (_finding("blocked_blueprint", "shadow blueprint blocks prompt materialization"), _finding("materialization_not_allowed", "audit receipt does not allow shadow materializer"))
    if status == PromptMaterializationAuditStatus.AUDIT_NOT_APPLICABLE:
        return (_finding("not_applicable_blueprint", "shadow blueprint is not applicable for prompt materialization", "warning"), _finding("materialization_not_allowed", "audit receipt does not allow shadow materializer"))
    if status == PromptMaterializationAuditStatus.AUDIT_INVALID_BLUEPRINT:
        return (_finding("invalid_blueprint", f"shadow blueprint status is invalid: {blueprint_status}"), _finding("materialization_not_allowed", "audit receipt does not allow shadow materializer"))
    if status == PromptMaterializationAuditStatus.AUDIT_RUNTIME_WIRING_DETECTED:
        return (_finding("runtime_wiring_detected", "shadow blueprint reports runtime wiring detected"), _finding("materialization_not_allowed", "audit receipt does not allow shadow materializer"))
    if status == PromptMaterializationAuditStatus.AUDIT_INVALID_CHAIN:
        return (_finding("materialization_not_allowed", "audit receipt has an invalid digest chain"),)
    return ()


def compute_prompt_materialization_audit_digest(receipt: PromptMaterializationAuditReceipt | Mapping[str, Any]) -> str:
    stable = _stable(receipt)
    if isinstance(stable, dict):
        stable.pop("receipt_digest", None)
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _with_digest(receipt: PromptMaterializationAuditReceipt) -> PromptMaterializationAuditReceipt:
    data = asdict(receipt)
    data["receipt_digest"] = compute_prompt_materialization_audit_digest(receipt)
    data["digest_chain"] = PromptMaterializationAuditDigestChain(**data["digest_chain"])
    data["boundary"] = PromptMaterializationAuditBoundary(**data["boundary"])
    data["findings"] = tuple(PromptMaterializationAuditFinding(**item) for item in data["findings"])
    return PromptMaterializationAuditReceipt(**data)


def build_prompt_materialization_audit_receipt(
    blueprint: Any,
    *,
    preview: Any | None = None,
    adapter_payload: PromptAssemblyAdapterPayload | Mapping[str, Any] | None = None,
    verification: PromptAssemblyConstraintVerification | Mapping[str, Any] | None = None,
) -> PromptMaterializationAuditReceipt:
    blueprint_data = _mapping(blueprint)
    preview_data = _mapping(preview)
    adapter_data = _mapping(adapter_payload)
    verification_data = _mapping(verification)
    chain, chain_findings = _chain_and_findings(blueprint_data, adapter_data, preview_data, verification_data)
    blueprint_status = str(blueprint_data.get("blueprint_status", ""))
    audit_status = _status_for_blueprint(blueprint_status, chain.complete)
    warnings = _issue_tuple(blueprint_data.get("warnings", ()))
    violations = _issue_tuple(blueprint_data.get("violations", ()))
    findings = list(chain_findings)
    findings.extend(_status_findings(audit_status, blueprint_status))
    if audit_status == PromptMaterializationAuditStatus.AUDIT_READY_WITH_WARNINGS:
        findings.extend(_finding("warning_requires_review", str(w.get("code", "warning")), "warning") for w in warnings)
    findings.extend(_finding("caveat_requires_review", caveat, "warning") for caveat in _as_tuple_str(blueprint_data.get("preserved_caveats", ())))

    boundary_summary = _boundary_summary(blueprint_data, preview_data, adapter_data)
    for marker in _REQUIRED_NON_RUNTIME_MARKERS[2:]:
        if boundary_summary.get(marker) is not True:
            findings.append(_finding("missing_required_non_runtime_marker", f"required non-runtime marker {marker} is missing or false"))
    upstream_evidence = {"blueprint": blueprint_data, "preview": preview_data, "adapter_payload": adapter_data, "verification": verification_data}
    if any(key in _FORBIDDEN_PROMPT_TEXT_KEYS for key, _ in _walk(upstream_evidence)):
        findings.append(_finding("prompt_text_present", "upstream audit evidence contains forbidden prompt text field"))
    if any(key in _FORBIDDEN_RAW_KEYS for key, _ in _walk(upstream_evidence)):
        findings.append(_finding("raw_payload_present", "upstream audit evidence contains forbidden raw payload field"))
    if any(key in _RUNTIME_AUTHORITY_KEYS and _truthy_forbidden(value) for key, value in _walk(upstream_evidence)):
        findings.append(_finding("runtime_authority_present", "upstream audit evidence contains runtime authority"))
    ref_counts = {
        "adapter_ref_count": int(blueprint_data.get("adapter_ref_count", 0) or 0),
        "blueprint_ref_count": int(blueprint_data.get("blueprint_ref_count", 0) or 0),
    }
    section_counts = {"blueprint_section_count": int(blueprint_data.get("section_count", 0) or 0)}
    receipt = PromptMaterializationAuditReceipt(
        receipt_id=f"prompt-materialization-audit:{blueprint_data.get('blueprint_id', 'unknown')}:{audit_status}",
        audit_status=audit_status,
        blueprint_id=chain.shadow_blueprint_id,
        blueprint_digest=chain.shadow_blueprint_digest,
        adapter_payload_id=chain.adapter_payload_id,
        adapter_status=str(blueprint_data.get("adapter_status", adapter_data.get("adapter_status", ""))),
        compliance_status=str(blueprint_data.get("compliance_status", preview_data.get("compliance_status", ""))),
        preview_status=str(blueprint_data.get("preview_status", "")),
        blueprint_status=blueprint_status,
        packet_id=chain.packet_id,
        packet_scope=chain.packet_scope,
        manifest_id=chain.manifest_id,
        manifest_digest=chain.manifest_digest,
        envelope_id=chain.envelope_id,
        envelope_digest=chain.envelope_digest,
        candidate_plan_id=chain.candidate_plan_id,
        candidate_plan_digest=chain.candidate_plan_digest,
        adapter_payload_digest=chain.adapter_payload_digest,
        verification_digest=chain.verification_digest,
        shadow_preview_digest=chain.shadow_preview_digest,
        shadow_blueprint_digest=chain.shadow_blueprint_digest,
        digest_chain_complete=chain.complete,
        digest_chain=chain,
        boundary_summary=boundary_summary,
        preserved_caveats=_as_tuple_str(blueprint_data.get("preserved_caveats", ())),
        warnings=warnings,
        violations=violations,
        findings=tuple(findings),
        provenance_summary=_note_summary(adapter_data, blueprint_data, "provenance_notes", "provenance_notes_present"),
        privacy_summary=_note_summary(adapter_data, blueprint_data, "privacy_notes", "privacy_notes_present"),
        truth_summary=_note_summary(adapter_data, blueprint_data, "truth_notes", "truth_notes_present"),
        safety_summary=_note_summary(adapter_data, blueprint_data, "safety_notes", "safety_notes_present"),
        source_kind_summary=_source_kind_counts(blueprint_data, adapter_data),
        ref_counts=ref_counts,
        section_counts=section_counts,
        rationale=f"{audit_status}: receipt binds shadow blueprint evidence only; no prompt materialization",
        receipt_digest="",
    )
    return _with_digest(receipt)


def build_prompt_materialization_audit_receipt_from_adapter_payload(
    adapter_payload: PromptAssemblyAdapterPayload | Mapping[str, Any],
    *,
    verification: PromptAssemblyConstraintVerification | Mapping[str, Any] | None = None,
) -> PromptMaterializationAuditReceipt:
    pa = _module_prompt_assembler()
    preview = pa.preview_context_hygiene_adapter_payload_for_prompt_assembly(adapter_payload)
    blueprint = pa.build_context_hygiene_shadow_prompt_blueprint(adapter_payload)
    return build_prompt_materialization_audit_receipt(
        blueprint,
        preview=preview,
        adapter_payload=adapter_payload,
        verification=verification,
    )


def build_prompt_materialization_audit_receipt_from_packet(
    packet: ContextPacket,
    preflight: PromptContextEligibility | None = None,
) -> PromptMaterializationAuditReceipt:
    manifest = build_context_prompt_handoff_manifest(packet, preflight)
    envelope = build_context_prompt_dry_run_envelope(manifest)
    candidate_plan: PromptAssemblyCandidatePlan = build_candidate_plan_from_dry_run_envelope(envelope)
    verification = verify_prompt_assembly_constraints(envelope, candidate_plan)
    adapter_payload = build_prompt_assembly_adapter_payload(verification, candidate_plan)
    return build_prompt_materialization_audit_receipt_from_adapter_payload(adapter_payload, verification=verification)


def audit_receipt_contains_no_prompt_text(receipt: PromptMaterializationAuditReceipt | Mapping[str, Any]) -> bool:
    return not any(key in _FORBIDDEN_PROMPT_TEXT_KEYS for key, _ in _walk(receipt))


def audit_receipt_contains_no_raw_payloads(receipt: PromptMaterializationAuditReceipt | Mapping[str, Any]) -> bool:
    return not any(key in _FORBIDDEN_RAW_KEYS for key, _ in _walk(receipt))


def audit_receipt_has_no_runtime_authority(receipt: PromptMaterializationAuditReceipt | Mapping[str, Any]) -> bool:
    return not any(key in _RUNTIME_AUTHORITY_KEYS and _truthy_forbidden(value) for key, value in _walk(receipt))


def audit_receipt_chain_is_complete(receipt: PromptMaterializationAuditReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    chain = data.get("digest_chain", {})
    chain_data = _mapping(chain)
    return bool(data.get("digest_chain_complete") and chain_data.get("complete") and not chain_data.get("missing"))


def _required_markers_present(receipt: PromptMaterializationAuditReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return all(data.get(marker) is True for marker in _REQUIRED_NON_RUNTIME_MARKERS)


def audit_receipt_allows_shadow_materializer(receipt: PromptMaterializationAuditReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    boundary = dict(data.get("boundary_summary", {})) if isinstance(data.get("boundary_summary", {}), Mapping) else {}
    return all(
        (
            data.get("audit_status") in _READY_AUDIT_STATUSES,
            audit_receipt_chain_is_complete(receipt),
            audit_receipt_contains_no_raw_payloads(receipt),
            audit_receipt_contains_no_prompt_text(receipt),
            audit_receipt_has_no_runtime_authority(receipt),
            _required_markers_present(receipt),
            boundary.get("may_future_assembler_consume") is True,
            boundary.get("must_block_prompt_materialization") is False,
        )
    )


def explain_prompt_materialization_audit_findings(receipt: PromptMaterializationAuditReceipt | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(receipt)
    return tuple(
        f"{item.get('severity', '')}:{item.get('code', '')}:{item.get('detail', '')}"
        for item in (_mapping(finding) for finding in data.get("findings", ()) or ())
    )


def summarize_prompt_materialization_audit_receipt(
    receipt: PromptMaterializationAuditReceipt | Mapping[str, Any],
) -> PromptMaterializationAuditReceiptSummary:
    data = _mapping(receipt)
    return PromptMaterializationAuditReceiptSummary(
        receipt_id=str(data.get("receipt_id", "")),
        audit_status=str(data.get("audit_status", "")),
        blueprint_id=str(data.get("blueprint_id", "")),
        adapter_payload_id=str(data.get("adapter_payload_id", "")),
        packet_id=str(data.get("packet_id", "")),
        digest_chain_complete=bool(data.get("digest_chain_complete", False)),
        finding_count=len(tuple(data.get("findings", ()) or ())),
        warning_count=len(tuple(data.get("warnings", ()) or ())),
        violation_count=len(tuple(data.get("violations", ()) or ())),
        allows_shadow_materializer=audit_receipt_allows_shadow_materializer(receipt),
        receipt_digest=str(data.get("receipt_digest", "")),
    )
