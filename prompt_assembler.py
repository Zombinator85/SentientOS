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
