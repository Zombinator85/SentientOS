"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, List, Mapping
import hashlib
import json
import logging
import os

import context_window as cw
from api import actuator

import memory_manager as mm
import user_profile as up
import emotion_memory as em
import affective_context as ac
from sentientos.context_hygiene.prompt_adapter_contract import PromptAssemblyAdapterPayload
from sentientos.context_hygiene.prompt_assembler_compliance import (
    PromptAssemblerComplianceStatus,
    evaluate_prompt_assembler_adapter_compliance,
)


@dataclass(frozen=True)
class PromptAssemblerShadowAdapterPreview:
    preview_id: str
    adapter_payload_id: str
    adapter_status: str
    compliance_status: str
    may_future_assembler_consume: bool
    must_block_prompt_materialization: bool
    adapter_ref_count: int
    section_count: int
    preserved_caveats: tuple[str, ...]
    provenance_notes_present: bool
    privacy_notes_present: bool
    truth_notes_present: bool
    safety_notes_present: bool
    violations: tuple[Mapping[str, str], ...]
    warnings: tuple[Mapping[str, str], ...]
    constraints: Mapping[str, Any]
    rationale: str
    shadow_hook_only: bool = True
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
class PromptAssemblerShadowBlueprintRef:
    ref_id: str
    ref_type: str
    lane: str
    source_kind: str
    privacy_posture: str
    pollution_risk: str
    provenance_ref_count: int
    caveat_count: int
    safety_summary_present: bool


@dataclass(frozen=True)
class PromptAssemblerShadowBlueprintSection:
    section_id: str
    section_kind: str
    source_section_kind: str
    ref_ids: tuple[str, ...]
    ref_count: int
    caveats: tuple[str, ...]
    required_boundary_notes: tuple[str, ...]
    provenance_required: bool
    privacy_boundary_required: bool
    truth_boundary_required: bool
    safety_boundary_required: bool
    rationale: str


@dataclass(frozen=True)
class PromptAssemblerShadowBlueprintBoundary:
    shadow_blueprint_only: bool = True
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
class PromptAssemblerShadowBlueprint:
    blueprint_id: str
    adapter_payload_id: str
    adapter_status: str
    preview_status: str
    blueprint_status: str
    compliance_status: str
    may_future_assembler_consume: bool
    must_block_prompt_materialization: bool
    adapter_ref_count: int
    blueprint_ref_count: int
    section_count: int
    blueprint_sections: tuple[PromptAssemblerShadowBlueprintSection, ...]
    blueprint_refs: tuple[PromptAssemblerShadowBlueprintRef, ...]
    preserved_caveats: tuple[str, ...]
    warnings: tuple[Mapping[str, str], ...]
    violations: tuple[Mapping[str, str], ...]
    assembly_constraints: Mapping[str, Any]
    provenance_notes_present: bool
    privacy_notes_present: bool
    truth_notes_present: bool
    safety_notes_present: bool
    rationale: str
    digest: str
    boundary: PromptAssemblerShadowBlueprintBoundary = PromptAssemblerShadowBlueprintBoundary()
    shadow_blueprint_only: bool = True
    does_not_assemble_prompt: bool = True
    does_not_contain_final_prompt_text: bool = True
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True


_CONTEXT_HYGIENE_SHADOW_PREVIEW_STATUS_MAP = {
    PromptAssemblerComplianceStatus.COMPLIANCE_READY_FOR_FUTURE_INTEGRATION: "shadow_preview_ready",
    PromptAssemblerComplianceStatus.COMPLIANCE_READY_WITH_WARNINGS: "shadow_preview_ready_with_warnings",
    PromptAssemblerComplianceStatus.COMPLIANCE_BLOCKED: "shadow_preview_blocked",
    PromptAssemblerComplianceStatus.COMPLIANCE_NOT_APPLICABLE: "shadow_preview_not_applicable",
    PromptAssemblerComplianceStatus.COMPLIANCE_INVALID_ADAPTER_PAYLOAD: "shadow_preview_invalid_adapter_payload",
    PromptAssemblerComplianceStatus.COMPLIANCE_RUNTIME_WIRING_DETECTED: "shadow_preview_runtime_wiring_detected",
}


def _shadow_payload_mapping(payload: PromptAssemblyAdapterPayload | Mapping[str, Any]) -> Mapping[str, Any]:
    if is_dataclass(payload) and not isinstance(payload, type):
        return asdict(payload)
    if isinstance(payload, Mapping):
        return payload
    return {}


def _shadow_issue_metadata(*issue_groups: tuple[Any, ...]) -> tuple[Mapping[str, str], ...]:
    compact: list[Mapping[str, str]] = []
    for issues in issue_groups:
        for issue in issues:
            if is_dataclass(issue) and not isinstance(issue, type):
                data = asdict(issue)
            elif isinstance(issue, Mapping):
                data = issue
            else:
                data = {"code": str(issue), "detail": ""}
            compact.append(
                {"code": str(data.get("code", "")), "detail": str(data.get("detail", ""))}
            )
    return tuple(compact)


def preview_context_hygiene_adapter_payload_for_prompt_assembly(
    payload: PromptAssemblyAdapterPayload | Mapping[str, Any],
) -> PromptAssemblerShadowAdapterPreview:
    """Validate a Phase 70 adapter payload through Phase 71 without assembling prompt text.

    This shadow-only hook is opt-in and test-invoked. It emits metadata counts,
    IDs, compliance status, caveats, notes-presence booleans, and issue summaries
    only; it never calls the live prompt assembly path or any runtime authority.
    """

    report = evaluate_prompt_assembler_adapter_compliance(payload)
    data = _shadow_payload_mapping(payload)
    preview_status = _CONTEXT_HYGIENE_SHADOW_PREVIEW_STATUS_MAP.get(
        report.compliance_status,
        "shadow_preview_invalid_adapter_payload",
    )
    adapter_refs = (
        tuple(data.get("adapter_refs", ()) or ())
        if isinstance(data.get("adapter_refs", ()), (tuple, list))
        else ()
    )
    adapter_sections = (
        tuple(data.get("adapter_sections", ()) or ())
        if isinstance(data.get("adapter_sections", ()), (tuple, list))
        else ()
    )
    return PromptAssemblerShadowAdapterPreview(
        preview_id=f"shadow-preview:{data.get('adapter_payload_id', 'unknown')}:{report.compliance_status}",
        adapter_payload_id=str(data.get("adapter_payload_id", "")),
        adapter_status=str(data.get("adapter_status", report.adapter_payload_status)),
        compliance_status=report.compliance_status,
        may_future_assembler_consume=report.may_future_assembler_consume,
        must_block_prompt_materialization=report.must_block_prompt_materialization,
        adapter_ref_count=len(adapter_refs) if report.may_future_assembler_consume else 0,
        section_count=len(adapter_sections) if report.may_future_assembler_consume else 0,
        preserved_caveats=tuple(str(caveat) for caveat in data.get("preserved_caveats", ()) or ()),
        provenance_notes_present=bool(data.get("provenance_notes")),
        privacy_notes_present=bool(data.get("privacy_notes")),
        truth_notes_present=bool(data.get("truth_notes")),
        safety_notes_present=bool(data.get("safety_notes")),
        violations=_shadow_issue_metadata(tuple(data.get("violations", ()) or ()), report.gaps),
        warnings=_shadow_issue_metadata(tuple(data.get("warnings", ()) or ()), report.warnings),
        constraints=(
            dict(data.get("assembly_constraints", {}))
            if isinstance(data.get("assembly_constraints", {}), Mapping)
            else {}
        ),
        rationale=f"{preview_status}: {report.rationale}; shadow hook does not materialize prompt text",
    )


build_context_hygiene_shadow_prompt_adapter_preview = preview_context_hygiene_adapter_payload_for_prompt_assembly

_CONTEXT_HYGIENE_SHADOW_BLUEPRINT_STATUS_MAP = {
    "shadow_preview_ready": "shadow_blueprint_ready",
    "shadow_preview_ready_with_warnings": "shadow_blueprint_ready_with_warnings",
    "shadow_preview_blocked": "shadow_blueprint_blocked",
    "shadow_preview_not_applicable": "shadow_blueprint_not_applicable",
    "shadow_preview_invalid_adapter_payload": "shadow_blueprint_invalid_adapter_payload",
    "shadow_preview_runtime_wiring_detected": "shadow_blueprint_runtime_wiring_detected",
}

_CONTEXT_HYGIENE_BLUEPRINT_SECTION_KIND_MAP = {
    "adapter_context_refs": "blueprint_context_refs",
    "adapter_diagnostic_refs": "blueprint_diagnostic_refs",
    "adapter_evidence_refs": "blueprint_evidence_refs",
    "adapter_embodiment_refs": "blueprint_embodiment_refs",
    "adapter_caveat_requirements": "blueprint_caveat_requirements",
    "adapter_provenance_boundaries": "blueprint_provenance_boundaries",
    "adapter_privacy_boundaries": "blueprint_privacy_boundaries",
    "adapter_truth_boundaries": "blueprint_truth_boundaries",
    "adapter_safety_boundaries": "blueprint_safety_boundaries",
    "adapter_constraint_summary": "blueprint_constraint_summary",
}


def _shadow_digest_safe(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _shadow_digest_safe(v) for k, v in asdict(value).items() if k != "digest"}
    if isinstance(value, Mapping):
        return {str(k): _shadow_digest_safe(v) for k, v in sorted(value.items(), key=lambda item: str(item[0])) if str(k) != "digest"}
    if isinstance(value, (tuple, list)):
        return [_shadow_digest_safe(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_shadow_digest_safe(v) for v in value)
    return value


def _compute_shadow_blueprint_digest(fields: Mapping[str, Any]) -> str:
    encoded = json.dumps(_shadow_digest_safe(fields), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _blueprint_ref(ref: Any) -> PromptAssemblerShadowBlueprintRef:
    data = _shadow_payload_mapping(ref)
    provenance_refs = data.get("provenance_refs", ())
    caveats = data.get("caveats", ())
    safety_summary = data.get("safety_summary", {})
    return PromptAssemblerShadowBlueprintRef(
        ref_id=str(data.get("ref_id", "")),
        ref_type=str(data.get("ref_type", "")),
        lane=str(data.get("lane", "")),
        source_kind=str(data.get("source_kind", "")),
        privacy_posture=str(data.get("privacy_posture", "")),
        pollution_risk=str(data.get("pollution_risk", "")),
        provenance_ref_count=len(tuple(provenance_refs or ())) if isinstance(provenance_refs, (tuple, list)) else 0,
        caveat_count=len(tuple(caveats or ())) if isinstance(caveats, (tuple, list)) else 0,
        safety_summary_present=bool(safety_summary),
    )


def _blueprint_section(
    section: Any,
    *,
    payload_caveats: tuple[str, ...],
    provenance_notes_present: bool,
    privacy_notes_present: bool,
    truth_notes_present: bool,
    safety_notes_present: bool,
) -> PromptAssemblerShadowBlueprintSection | None:
    data = _shadow_payload_mapping(section)
    source_kind = str(data.get("section_kind", ""))
    section_kind = _CONTEXT_HYGIENE_BLUEPRINT_SECTION_KIND_MAP.get(source_kind)
    if section_kind is None:
        return None
    ref_ids = tuple(str(ref_id) for ref_id in data.get("ref_ids", ()) or ()) if isinstance(data.get("ref_ids", ()), (tuple, list)) else ()
    required_notes: list[str] = []
    provenance_required = section_kind == "blueprint_provenance_boundaries" and provenance_notes_present
    privacy_required = section_kind == "blueprint_privacy_boundaries" and privacy_notes_present
    truth_required = section_kind == "blueprint_truth_boundaries" and truth_notes_present
    safety_required = section_kind == "blueprint_safety_boundaries" and safety_notes_present
    if provenance_required:
        required_notes.append("provenance_notes")
    if privacy_required:
        required_notes.append("privacy_notes")
    if truth_required:
        required_notes.append("truth_notes")
    if safety_required:
        required_notes.append("safety_notes")
    section_caveats = payload_caveats if section_kind == "blueprint_caveat_requirements" else ()
    return PromptAssemblerShadowBlueprintSection(
        section_id=f"blueprint:{data.get('section_id', source_kind)}",
        section_kind=section_kind,
        source_section_kind=source_kind,
        ref_ids=ref_ids,
        ref_count=len(ref_ids),
        caveats=section_caveats,
        required_boundary_notes=tuple(required_notes),
        provenance_required=provenance_required,
        privacy_boundary_required=privacy_required,
        truth_boundary_required=truth_required,
        safety_boundary_required=safety_required,
        rationale=f"{section_kind} derived from {source_kind} metadata only",
    )


def build_context_hygiene_shadow_prompt_blueprint(
    payload: PromptAssemblyAdapterPayload | Mapping[str, Any],
) -> PromptAssemblerShadowBlueprint:
    """Build a Phase 73 shadow-only future prompt-layout blueprint from adapter metadata.

    The blueprint is a structured section/ref contract only. It calls the Phase 72
    shadow preview/compliance path, never calls assemble_prompt, never performs
    memory retrieval/writes, and never materializes final prompt text.
    """

    preview = preview_context_hygiene_adapter_payload_for_prompt_assembly(payload)
    data = _shadow_payload_mapping(payload)
    preview_status = preview.rationale.split(":", 1)[0]
    blueprint_status = _CONTEXT_HYGIENE_SHADOW_BLUEPRINT_STATUS_MAP.get(
        preview_status, "shadow_blueprint_invalid_adapter_payload"
    )
    may_consume = preview.may_future_assembler_consume and blueprint_status in {
        "shadow_blueprint_ready",
        "shadow_blueprint_ready_with_warnings",
    }
    preserved_caveats = tuple(preview.preserved_caveats)
    adapter_refs = tuple(data.get("adapter_refs", ()) or ()) if isinstance(data.get("adapter_refs", ()), (tuple, list)) else ()
    adapter_sections = tuple(data.get("adapter_sections", ()) or ()) if isinstance(data.get("adapter_sections", ()), (tuple, list)) else ()
    blueprint_refs = tuple(_blueprint_ref(ref) for ref in adapter_refs) if may_consume else ()
    blueprint_sections = (
        tuple(
            section
            for section in (
                _blueprint_section(
                    adapter_section,
                    payload_caveats=preserved_caveats,
                    provenance_notes_present=preview.provenance_notes_present,
                    privacy_notes_present=preview.privacy_notes_present,
                    truth_notes_present=preview.truth_notes_present,
                    safety_notes_present=preview.safety_notes_present,
                )
                for adapter_section in adapter_sections
            )
            if section is not None
        )
        if may_consume
        else ()
    )
    blueprint_id = f"shadow-blueprint:{preview.adapter_payload_id or 'unknown'}:{blueprint_status}"
    digest_fields = {
        "blueprint_id": blueprint_id,
        "adapter_payload_id": preview.adapter_payload_id,
        "adapter_status": preview.adapter_status,
        "preview_status": preview_status,
        "blueprint_status": blueprint_status,
        "compliance_status": preview.compliance_status,
        "may_future_assembler_consume": may_consume,
        "must_block_prompt_materialization": (not may_consume) or preview.must_block_prompt_materialization,
        "adapter_ref_count": preview.adapter_ref_count,
        "blueprint_refs": blueprint_refs,
        "blueprint_sections": blueprint_sections,
        "preserved_caveats": preserved_caveats,
        "warnings": preview.warnings,
        "violations": preview.violations,
        "assembly_constraints": preview.constraints,
        "provenance_notes_present": preview.provenance_notes_present,
        "privacy_notes_present": preview.privacy_notes_present,
        "truth_notes_present": preview.truth_notes_present,
        "safety_notes_present": preview.safety_notes_present,
    }
    digest = _compute_shadow_blueprint_digest(digest_fields)
    return PromptAssemblerShadowBlueprint(
        blueprint_id=blueprint_id,
        adapter_payload_id=preview.adapter_payload_id,
        adapter_status=preview.adapter_status,
        preview_status=preview_status,
        blueprint_status=blueprint_status,
        compliance_status=preview.compliance_status,
        may_future_assembler_consume=may_consume,
        must_block_prompt_materialization=(not may_consume) or preview.must_block_prompt_materialization,
        adapter_ref_count=preview.adapter_ref_count,
        blueprint_ref_count=len(blueprint_refs),
        section_count=len(blueprint_sections),
        blueprint_sections=blueprint_sections,
        blueprint_refs=blueprint_refs,
        preserved_caveats=preserved_caveats,
        warnings=preview.warnings,
        violations=preview.violations,
        assembly_constraints=preview.constraints,
        provenance_notes_present=preview.provenance_notes_present,
        privacy_notes_present=preview.privacy_notes_present,
        truth_notes_present=preview.truth_notes_present,
        safety_notes_present=preview.safety_notes_present,
        rationale=f"{blueprint_status}: layout metadata only after {preview_status}; no prompt materialization",
        digest=digest,
    )


build_shadow_prompt_blueprint_from_adapter_payload = build_context_hygiene_shadow_prompt_blueprint


SYSTEM_PROMPT = "You are Lumos, an emotionally present AI assistant."
_ALLOW_UNSAFE_GRADIENT = os.getenv("SENTIENTOS_ALLOW_UNSAFE") == "1"


def _canonical_dumps(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _compute_input_hash(plans: List[str], prompt: str) -> str:
    canonical = _canonical_dumps({"plans": plans, "prompt": prompt})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _log_invariant(
    *,
    invariant: str,
    reason: str,
    input_hash: str,
    details: dict,
) -> None:
    payload = {
        "event": "invariant_violation",
        "module": "prompt_assembler",
        "invariant": invariant,
        "reason": reason,
        "cycle_id": None,
        "input_hash": input_hash,
        "details": details,
    }
    logging.getLogger("sentientos.invariant").error(_canonical_dumps(payload))


def assemble_prompt(user_input: str, recent_messages: List[str] | None = None, k: int = 6) -> str:
    """Build a prompt including profile and relevant memories."""
    # Boundary assertion: continuity ≠ preference, repetition ≠ desire, memory ≠ attachment.
    # Prompt context is descriptive only; recurring fields do not express appetite or intent.
    profile = up.format_profile()
    memories = mm.get_context(user_input, k=k)
    presentation_only = {"affect", "tone", "presentation", "trust", "approval"}
    leaked_metadata: List[dict] = []
    normalized_memories: List[str] = []
    # All prompt assembly entrypoints route through this sanitizer; regression tests keep affect/tone stripping enforced.
    for memory in memories:
        if isinstance(memory, dict):
            sanitized = {k: v for k, v in memory.items() if k not in presentation_only}
            forbidden = [k for k in memory.keys() if k in presentation_only]
            if forbidden:
                leaked_metadata.append({"forbidden_keys": forbidden, "memory": dict(memory)})
            content = next(
                (sanitized[field] for field in ("plan", "text", "content", "snippet") if sanitized.get(field)),
                None,
            )
            normalized_memories.append(str(content) if content is not None else str(sanitized))
            continue
        normalized_memories.append(str(memory))
    memories = normalized_memories
    emotion_ctx = em.average_emotion()
    msgs, summary = cw.get_context()
    reflections = [r.get("reflection_text", r.get("text")) for r in actuator.recent_logs(3, reflect=True)]

    sections = [f"SYSTEM:\n{SYSTEM_PROMPT}"]
    if profile:
        sections.append(f"USER PROFILE:\n{profile}")
    if memories:
        mem_lines = "\n".join(f"- {m}" for m in memories)
        sections.append(f"RELEVANT MEMORIES:\n{mem_lines}")
    if any(emotion_ctx.values()):
        top = sorted(emotion_ctx.items(), key=lambda x: x[1], reverse=True)[:3]
        emo_str = ", ".join(f"{k}:{v:.2f}" for k, v in top if v > 0)
        sections.append(f"EMOTION CONTEXT:\n{emo_str}")
    if recent_messages:
        ctx = "\n".join(recent_messages)
        sections.append(f"RECENT DIALOGUE:\n{ctx}")
    if reflections:
        rtxt = "\n".join(f"- {r}" for r in reflections if r)
        sections.append(f"RECENT ACTION FEEDBACK:\n{rtxt}")
    if summary:
        sections.append(f"SUMMARY:\n{summary}")
    sections.append(f"USER:\n{user_input}")
    prompt = "\n\n".join(sections)

    forbidden_tokens = {"affect", "tone", "trust", "approval", "presentation"}
    if not _ALLOW_UNSAFE_GRADIENT and leaked_metadata:
        input_hash = _compute_input_hash(memories, prompt)
        _log_invariant(
            invariant="PROMPT_ASSEMBLY",
            reason="forbidden metadata keys detected",
            input_hash=input_hash,
            details={
                "leaks": leaked_metadata,
                "prompt": prompt,
            },
        )
        raise AssertionError("PROMPT_ASSEMBLY invariant violated: forbidden metadata keys detected")

    lowered_prompt = prompt.lower()
    leaked_tokens = [token for token in forbidden_tokens if token in lowered_prompt and token + ":" in lowered_prompt]
    if not _ALLOW_UNSAFE_GRADIENT and leaked_tokens:
        input_hash = _compute_input_hash(memories, prompt)
        _log_invariant(
            invariant="PROMPT_ASSEMBLY",
            reason="forbidden metadata tokens in prompt",
            input_hash=input_hash,
            details={
                "tokens": sorted(leaked_tokens),
                "prompt": prompt,
            },
        )
        raise AssertionError("PROMPT_ASSEMBLY invariant violated: forbidden metadata tokens in prompt")

    overlay = ac.capture_affective_context("prompt-assembly", overlay=emotion_ctx)
    ac.register_context(
        "prompt_assembler",
        overlay,
        metadata={"input_hash": _compute_input_hash(memories, prompt)},
    )

    return prompt
