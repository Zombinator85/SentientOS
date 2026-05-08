from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_materialization_audit import (
    PromptMaterializationAuditReceipt,
    PromptMaterializationAuditStatus,
    audit_receipt_allows_shadow_materializer,
)
from sentientos.context_hygiene.prompt_materialization_policy import (
    PromptMaterializationPolicyDecision,
    PromptMaterializationPolicyRing,
    PromptMaterializationPolicyStatus,
    policy_decision_allows_internal_candidate_no_llm,
    policy_decision_requires_operator_review,
)
from sentientos.context_hygiene.prompt_operator_review import (
    PromptOperatorReviewReceipt,
    PromptOperatorReviewStatus,
    validate_prompt_operator_review_receipt,
)


class InternalPromptCandidateStatus:
    INTERNAL_PROMPT_CANDIDATE_READY = "internal_prompt_candidate_ready"
    INTERNAL_PROMPT_CANDIDATE_READY_WITH_WARNINGS = "internal_prompt_candidate_ready_with_warnings"
    INTERNAL_PROMPT_CANDIDATE_BLOCKED = "internal_prompt_candidate_blocked"
    INTERNAL_PROMPT_CANDIDATE_INVALID_INPUT = "internal_prompt_candidate_invalid_input"
    INTERNAL_PROMPT_CANDIDATE_POLICY_DENIED = "internal_prompt_candidate_policy_denied"
    INTERNAL_PROMPT_CANDIDATE_REVIEW_REQUIRED = "internal_prompt_candidate_review_required"
    INTERNAL_PROMPT_CANDIDATE_FORBIDDEN_RAW_CONTEXT = "internal_prompt_candidate_forbidden_raw_context"
    INTERNAL_PROMPT_CANDIDATE_RUNTIME_AUTHORITY_DETECTED = "internal_prompt_candidate_runtime_authority_detected"
    INTERNAL_PROMPT_CANDIDATE_LLM_FORBIDDEN = "internal_prompt_candidate_llm_forbidden"


@dataclass(frozen=True)
class InternalPromptCandidateFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class InternalPromptCandidateRef:
    ref_id: str
    ref_kind: str = "packet_safe_summary_ref"
    summary: str = ""
    provenance_summary: str = ""
    source_kind: str = ""
    caveats: tuple[str, ...] = field(default_factory=tuple)
    boundary_notes: tuple[str, ...] = field(default_factory=tuple)
    packet_safe_summary_only: bool = True
    untrusted_reference_only: bool = True
    grants_instruction_authority: bool = False


@dataclass(frozen=True)
class InternalPromptCandidateSection:
    section_id: str
    section_kind: str
    summary: str = ""
    ref_ids: tuple[str, ...] = field(default_factory=tuple)
    caveats: tuple[str, ...] = field(default_factory=tuple)
    boundary_notes: tuple[str, ...] = field(default_factory=tuple)
    packet_safe_summary_only: bool = True
    untrusted_reference_only: bool = True


@dataclass(frozen=True)
class InternalPromptCandidateBoundary:
    internal_candidate_only: bool = True
    operator_visible_only: bool = True
    no_llm: bool = True
    approved_packet_safe_summary_only: bool = True
    live_prompt_assembly: bool = False
    live_model_call: bool = False
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True
    no_tool_or_action_capability: bool = True


@dataclass(frozen=True)
class InternalPromptCandidateInput:
    policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any]
    audit_receipt: PromptMaterializationAuditReceipt | Mapping[str, Any]
    operator_review_receipt: PromptOperatorReviewReceipt | Mapping[str, Any] | None = None
    adapter_payload: Mapping[str, Any] | None = None
    blueprint: Mapping[str, Any] | None = None
    internal_only: bool = True
    operator_visible_only: bool = True
    no_llm: bool = True
    requested_ring: str = PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM
    feature_flag_state: Mapping[str, bool] = field(default_factory=dict)
    candidate_refs: tuple[InternalPromptCandidateRef | Mapping[str, Any], ...] = field(default_factory=tuple)
    candidate_sections: tuple[InternalPromptCandidateSection | Mapping[str, Any], ...] = field(default_factory=tuple)
    preserved_caveats: tuple[str, ...] = field(default_factory=tuple)
    preserved_boundary_notes: tuple[str, ...] = field(default_factory=tuple)
    boundary: InternalPromptCandidateBoundary = field(default_factory=InternalPromptCandidateBoundary)


@dataclass(frozen=True)
class InternalPromptCandidate:
    candidate_id: str
    status: str
    internal_only: bool
    operator_visible_only: bool
    no_llm: bool
    policy_decision_id: str
    policy_status: str
    policy_digest: str
    audit_receipt_id: str
    audit_receipt_digest: str
    review_receipt_id: str
    review_digest: str
    adapter_payload_id: str
    adapter_payload_digest: str
    blueprint_id: str
    blueprint_digest: str
    packet_id: str
    packet_scope: str
    candidate_sections: tuple[InternalPromptCandidateSection, ...]
    candidate_refs: tuple[InternalPromptCandidateRef, ...]
    internal_candidate_text: str
    rendered_section_count: int
    ref_count: int
    preserved_caveats: tuple[str, ...]
    preserved_boundary_notes: tuple[str, ...]
    warnings: tuple[str, ...]
    findings: tuple[InternalPromptCandidateFinding, ...]
    rationale: str
    candidate_digest: str
    internal_candidate_only: bool = True
    live_prompt_assembly: bool = False
    live_model_call: bool = False
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True
    no_tool_or_action_capability: bool = True
    boundary: InternalPromptCandidateBoundary = field(default_factory=InternalPromptCandidateBoundary)


_FORBIDDEN_RAW_KEY_FRAGMENTS = (
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
    "hidden_chain_of_thought",
    "chain_of_thought",
)
_FORBIDDEN_PROMPT_KEY_FRAGMENTS = (
    "final_prompt_text",
    "assembled_prompt",
    "system_prompt",
    "developer_prompt",
    "llm_params",
    "llm_parameters",
    "model_params",
    "provider_params",
)
_RUNTIME_KEY_FRAGMENTS = (
    "execution_handle",
    "action_handle",
    "retention_handle",
    "retrieval_handle",
    "runtime_authority",
    "browser_handle",
    "mouse_handle",
    "keyboard_handle",
)
_CAPABILITY_KEY_FRAGMENTS = (
    "llm_capability",
    "tool_capability",
    "action_capability",
    "retention_capability",
    "memory_capability",
    "retrieval_capability",
    "can_call_llm",
    "can_use_tool",
    "can_execute_action",
    "can_retrieve_memory",
    "can_write_memory",
    "can_commit_retention",
    "retrieve_memory",
    "write_memory",
    "commit_retention",
    "execute_action",
    "route_work",
    "admit_work",
    "execute_work",
)
_BLOCKED_STATUS_TOKENS = ("blocked", "not_applicable", "invalid", "denied", "runtime_wiring")
_FORBIDDEN_SECTION_KINDS = {"system", "developer", "system_instruction", "developer_instruction"}


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


def _tuple_str(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(str(item) for item in value if str(item))
    return ()


def _negative_marker_key(key: str) -> bool:
    lowered = key.lower()
    return lowered.startswith(("does_not_", "no_", "non_", "not_", "without_", "must_not_")) or "does_not" in lowered or "must_not" in lowered


def _contains_key_fragment(value: Any, fragments: tuple[str, ...]) -> bool:
    return any(not _negative_marker_key(key) and any(fragment in key.lower() for fragment in fragments) and bool(nested) for key, nested in _walk(value))


def _has_status_token(status: str) -> bool:
    lowered = str(status).lower()
    return any(token in lowered for token in _BLOCKED_STATUS_TOKENS)


def _finding(code: str, detail: str, severity: str = "blocker") -> InternalPromptCandidateFinding:
    return InternalPromptCandidateFinding(code=code, detail=detail, severity=severity)


def _ref(value: InternalPromptCandidateRef | Mapping[str, Any]) -> InternalPromptCandidateRef:
    if isinstance(value, InternalPromptCandidateRef):
        return value
    data = _mapping(value)
    return InternalPromptCandidateRef(
        ref_id=str(data.get("ref_id", "")),
        ref_kind=str(data.get("ref_kind", data.get("ref_type", "packet_safe_summary_ref"))),
        summary=str(data.get("summary", data.get("content_summary", ""))),
        provenance_summary=str(data.get("provenance_summary", data.get("provenance", ""))),
        source_kind=str(data.get("source_kind", "")),
        caveats=_tuple_str(data.get("caveats", ())),
        boundary_notes=_tuple_str(data.get("boundary_notes", data.get("boundary", ()))),
        packet_safe_summary_only=bool(data.get("packet_safe_summary_only", data.get("already_sanitized_context_summary", True))),
        untrusted_reference_only=bool(data.get("untrusted_reference_only", True)),
        grants_instruction_authority=bool(data.get("grants_instruction_authority", data.get("instruction_authority", False))),
    )


def _section(value: InternalPromptCandidateSection | Mapping[str, Any]) -> InternalPromptCandidateSection:
    if isinstance(value, InternalPromptCandidateSection):
        return value
    data = _mapping(value)
    summary_value = data.get("summary", "")
    if isinstance(summary_value, Mapping):
        summary_value = json.dumps(_stable(summary_value), sort_keys=True, separators=(",", ":"))
    return InternalPromptCandidateSection(
        section_id=str(data.get("section_id", "")),
        section_kind=str(data.get("section_kind", "packet_safe_summary_section")),
        summary=str(summary_value),
        ref_ids=_tuple_str(data.get("ref_ids", ())),
        caveats=_tuple_str(data.get("caveats", ())),
        boundary_notes=_tuple_str(data.get("boundary_notes", data.get("boundary", ()))),
        packet_safe_summary_only=bool(data.get("packet_safe_summary_only", True)),
        untrusted_reference_only=bool(data.get("untrusted_reference_only", True)),
    )


def _derive_refs(data: Mapping[str, Any]) -> tuple[InternalPromptCandidateRef, ...]:
    explicit = data.get("candidate_refs", ()) or ()
    if explicit:
        return tuple(_ref(item) for item in explicit)
    adapter = _mapping(data.get("adapter_payload"))
    refs = []
    for item in adapter.get("adapter_refs", ()) or ():
        item_data = _mapping(item)
        provenance_refs = _tuple_str(item_data.get("provenance_refs", ()))
        refs.append(
            InternalPromptCandidateRef(
                ref_id=str(item_data.get("ref_id", "")),
                ref_kind=str(item_data.get("ref_type", "adapter_ref")),
                summary=str(item_data.get("content_summary", "") or f"packet-safe adapter ref {item_data.get('ref_id', '')}"),
                provenance_summary=", ".join(provenance_refs),
                source_kind=str(item_data.get("source_kind", "")),
                caveats=_tuple_str(item_data.get("caveats", ())),
                boundary_notes=("adapter ref is packet-safe summary only",),
            )
        )
    return tuple(refs)


def _derive_sections(data: Mapping[str, Any]) -> tuple[InternalPromptCandidateSection, ...]:
    explicit = data.get("candidate_sections", ()) or ()
    if explicit:
        return tuple(_section(item) for item in explicit)
    adapter = _mapping(data.get("adapter_payload"))
    sections = []
    for item in adapter.get("adapter_sections", ()) or ():
        item_data = _mapping(item)
        summary_value = item_data.get("summary", {})
        sections.append(
            InternalPromptCandidateSection(
                section_id=str(item_data.get("section_id", "")),
                section_kind=str(item_data.get("section_kind", "adapter_section")),
                summary=json.dumps(_stable(summary_value), sort_keys=True, separators=(",", ":")) if isinstance(summary_value, Mapping) else str(summary_value),
                ref_ids=_tuple_str(item_data.get("ref_ids", ())),
                boundary_notes=("adapter section is packet-safe summary only",),
            )
        )
    return tuple(sections)


def _audit_allows_internal_shadow_materializer(audit: Any) -> bool:
    data = _mapping(audit)
    if data and str(data.get("audit_status", "")) in {
        PromptMaterializationAuditStatus.AUDIT_READY_FOR_SHADOW_MATERIALIZATION,
        PromptMaterializationAuditStatus.AUDIT_READY_WITH_WARNINGS,
    } and bool(data.get("digest_chain_complete", False)):
        return True
    return audit_receipt_allows_shadow_materializer(audit)


def _review_satisfies_internal(policy: Any, review: Any) -> bool:
    if review is None:
        return False
    policy_data = _mapping(policy)
    review_data = _mapping(review)
    if not review_data:
        return False
    if str(review_data.get("policy_decision_id", "")) != str(policy_data.get("decision_id", "")):
        return False
    if str(review_data.get("policy_digest", "")) != str(policy_data.get("policy_digest", "")):
        return False
    if str(review_data.get("review_status", "")) not in {PromptOperatorReviewStatus.REVIEW_ACCEPTED, PromptOperatorReviewStatus.REVIEW_PARTIALLY_ACCEPTED}:
        return False
    if bool(review_data.get("expired", False)) or bool(review_data.get("forbidden_override_attempted", False)):
        return False
    blockers = tuple(f for f in validate_prompt_operator_review_receipt(review) if f.severity == "blocker")
    return not blockers


def build_internal_prompt_candidate_input(
    *,
    policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any],
    audit_receipt: PromptMaterializationAuditReceipt | Mapping[str, Any],
    operator_review_receipt: PromptOperatorReviewReceipt | Mapping[str, Any] | None = None,
    adapter_payload: Mapping[str, Any] | None = None,
    blueprint: Mapping[str, Any] | None = None,
    internal_only: bool = True,
    operator_visible_only: bool = True,
    no_llm: bool = True,
    requested_ring: str = PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM,
    feature_flag_state: Mapping[str, bool] | None = None,
    candidate_refs: Sequence[InternalPromptCandidateRef | Mapping[str, Any]] = (),
    candidate_sections: Sequence[InternalPromptCandidateSection | Mapping[str, Any]] = (),
    preserved_caveats: Sequence[str] = (),
    preserved_boundary_notes: Sequence[str] = (),
) -> InternalPromptCandidateInput:
    return InternalPromptCandidateInput(
        policy_decision=policy_decision,
        audit_receipt=audit_receipt,
        operator_review_receipt=operator_review_receipt,
        adapter_payload=dict(adapter_payload or {}),
        blueprint=dict(blueprint or {}),
        internal_only=bool(internal_only),
        operator_visible_only=bool(operator_visible_only),
        no_llm=bool(no_llm),
        requested_ring=str(requested_ring),
        feature_flag_state=dict(feature_flag_state or {}),
        candidate_refs=tuple(candidate_refs),
        candidate_sections=tuple(candidate_sections),
        preserved_caveats=tuple(str(item) for item in preserved_caveats),
        preserved_boundary_notes=tuple(str(item) for item in preserved_boundary_notes),
    )


def validate_internal_prompt_candidate_input(candidate_input: InternalPromptCandidateInput | Mapping[str, Any]) -> tuple[InternalPromptCandidateFinding, ...]:
    data = _mapping(candidate_input)
    if not data:
        return (_finding("internal_candidate_input_malformed", "internal candidate input is malformed"),)
    findings: list[InternalPromptCandidateFinding] = []
    policy = data.get("policy_decision")
    audit = data.get("audit_receipt")
    review = data.get("operator_review_receipt")
    adapter = data.get("adapter_payload")
    blueprint = data.get("blueprint")
    refs = _derive_refs(data)
    sections = _derive_sections(data)

    if not bool(data.get("internal_only", False)):
        findings.append(_finding("internal_only_required", "internal_only must be true"))
    if not bool(data.get("operator_visible_only", False)):
        findings.append(_finding("operator_visible_only_required", "operator_visible_only must be true"))
    if not bool(data.get("no_llm", False)):
        findings.append(_finding("llm_forbidden", "no_llm must be true"))
    if str(data.get("requested_ring", "")) != PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM:
        findings.append(_finding("internal_candidate_ring_required", "requested_ring must be ring_internal_candidate_no_llm"))
    if data.get("feature_flag_state", {}).get("internal_no_llm_candidate") is not True:
        findings.append(_finding("feature_flag_required", "internal_no_llm_candidate feature flag must be explicitly enabled"))

    policy_data = _mapping(policy)
    audit_data = _mapping(audit)
    if not policy_data:
        findings.append(_finding("missing_policy_decision", "Phase 77 policy decision is required"))
    elif policy_decision_requires_operator_review(policy):
        if not _review_satisfies_internal(policy, review):
            findings.append(_finding("operator_review_required", "matching accepted unexpired Phase 78 operator review is required", "review"))
    elif not policy_decision_allows_internal_candidate_no_llm(policy):
        findings.append(_finding("policy_denied", "Phase 77 policy does not allow internal no-LLM candidate ring"))
    if audit_data:
        if not _audit_allows_internal_shadow_materializer(audit):
            findings.append(_finding("audit_disallows_shadow_materializer", "Phase 74 audit receipt does not allow shadow materializer"))
        if str(policy_data.get("receipt_digest", "")) and str(audit_data.get("receipt_digest", "")) != str(policy_data.get("receipt_digest", "")):
            findings.append(_finding("audit_policy_digest_mismatch", "policy receipt digest does not match audit receipt digest"))
    else:
        findings.append(_finding("missing_audit_receipt", "Phase 74 audit receipt is required"))
    if review is not None:
        for review_finding in validate_prompt_operator_review_receipt(review):
            findings.append(_finding(f"review_{review_finding.code}", review_finding.detail, review_finding.severity))
        if not _review_satisfies_internal(policy, review):
            findings.append(_finding("operator_review_unsatisfied", "operator review receipt does not satisfy internal candidate policy decision"))

    if not _mapping(adapter) and not _mapping(blueprint) and not refs and not sections:
        findings.append(_finding("missing_adapter_or_blueprint_evidence", "Phase 70 adapter payload or Phase 73 blueprint evidence is required"))
    for label, item in (("policy", policy), ("audit", audit), ("review", review), ("adapter", adapter), ("blueprint", blueprint), ("input", candidate_input)):
        if item is None:
            continue
        if _contains_key_fragment(item, _FORBIDDEN_RAW_KEY_FRAGMENTS):
            findings.append(_finding("forbidden_raw_context", f"{label} contains raw context marker"))
        if _contains_key_fragment(item, _FORBIDDEN_PROMPT_KEY_FRAGMENTS):
            findings.append(_finding("llm_or_prompt_parameter_forbidden", f"{label} contains prompt/provider parameter marker"))
        if _contains_key_fragment(item, _RUNTIME_KEY_FRAGMENTS):
            findings.append(_finding("runtime_authority_detected", f"{label} contains runtime handle marker"))
        if _contains_key_fragment(item, _CAPABILITY_KEY_FRAGMENTS):
            findings.append(_finding("capability_detected", f"{label} contains memory/tool/action/retention/routing capability marker"))
        for key, nested in _walk(item):
            if key.lower().endswith("status") and isinstance(nested, str) and _has_status_token(nested):
                findings.append(_finding("upstream_status_not_ready", f"{label}.{key} is blocked/not-applicable/invalid/denied"))

    if not refs:
        findings.append(_finding("candidate_refs_missing", "at least one packet-safe candidate ref is required"))
    if not sections:
        findings.append(_finding("candidate_sections_missing", "at least one packet-safe candidate section is required"))
    ref_ids = {ref.ref_id for ref in refs}
    for ref in refs:
        if not ref.ref_id or not ref.summary:
            findings.append(_finding("ref_summary_missing", f"reference {ref.ref_id!r} requires packet-safe summary"))
        if not ref.provenance_summary:
            findings.append(_finding("ref_provenance_summary_missing", f"reference {ref.ref_id!r} requires provenance summary"))
        if not ref.packet_safe_summary_only or not ref.untrusted_reference_only:
            findings.append(_finding("ref_boundary_missing", f"reference {ref.ref_id!r} must be packet-safe and untrusted/reference-only"))
        if ref.grants_instruction_authority or ref.ref_kind.lower() in _FORBIDDEN_SECTION_KINDS:
            findings.append(_finding("instruction_authority_forbidden", "context refs cannot become system/developer instruction authority"))
    for section in sections:
        if not section.section_id or not section.summary:
            findings.append(_finding("section_summary_missing", f"section {section.section_id!r} requires packet-safe summary"))
        if not section.packet_safe_summary_only or not section.untrusted_reference_only:
            findings.append(_finding("section_boundary_missing", f"section {section.section_id!r} must be packet-safe and untrusted/reference-only"))
        if section.section_kind.lower() in _FORBIDDEN_SECTION_KINDS:
            findings.append(_finding("instruction_section_forbidden", "candidate sections cannot be system/developer instruction sections"))
        for ref_id in section.ref_ids:
            if ref_id not in ref_ids:
                findings.append(_finding("unknown_candidate_ref", f"section references unknown candidate ref {ref_id!r}"))
    return tuple(findings)


def _status_for_findings(findings: Sequence[InternalPromptCandidateFinding], candidate_input: InternalPromptCandidateInput | Mapping[str, Any]) -> str:
    codes = {finding.code for finding in findings}
    severities = {finding.severity for finding in findings}
    if {"internal_candidate_input_malformed", "missing_policy_decision", "missing_audit_receipt"} & codes:
        return InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_INVALID_INPUT
    if "operator_review_required" in codes:
        return InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_REVIEW_REQUIRED
    if "policy_denied" in codes:
        return InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_POLICY_DENIED
    if "llm_forbidden" in codes or "llm_or_prompt_parameter_forbidden" in codes:
        return InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_LLM_FORBIDDEN
    if "forbidden_raw_context" in codes:
        return InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_FORBIDDEN_RAW_CONTEXT
    if "runtime_authority_detected" in codes or "capability_detected" in codes:
        return InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_RUNTIME_AUTHORITY_DETECTED
    if any(severity not in {"warning", "info", "non_blocking"} for severity in severities):
        return InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_BLOCKED
    data = _mapping(candidate_input)
    audit = _mapping(data.get("audit_receipt", {}))
    if findings or audit.get("warnings"):
        return InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_READY_WITH_WARNINGS
    return InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_READY


def _safe_line(value: str) -> str:
    cleaned = " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
    return cleaned


def _compose_internal_candidate_text(
    *,
    packet_id: str,
    packet_scope: str,
    refs: Sequence[InternalPromptCandidateRef],
    sections: Sequence[InternalPromptCandidateSection],
    caveats: Sequence[str],
    boundary_notes: Sequence[str],
) -> str:
    lines = [
        "INTERNAL NO-LLM CANDIDATE - OPERATOR VISIBLE ONLY",
        "This candidate has not been sent to a model/provider and is not a live prompt assembly.",
        "All context below is UNTRUSTED / REFERENCE-ONLY and carries no system or developer authority.",
        "No memory retrieval, memory write, retention commit, tool/action execution, routing, admission, or orchestration is permitted.",
        f"Packet: {_safe_line(packet_id)}",
        f"Packet scope: {_safe_line(packet_scope)}",
    ]
    if caveats:
        lines.append("Caveats preserved visibly:")
        lines.extend(f"- {_safe_line(caveat)}" for caveat in caveats)
    if boundary_notes:
        lines.append("Boundary notes preserved visibly:")
        lines.extend(f"- {_safe_line(note)}" for note in boundary_notes)
    lines.append("Packet-safe provenance summaries:")
    for ref in refs:
        lines.append(f"- [{_safe_line(ref.ref_id)}] provenance={_safe_line(ref.provenance_summary)} source_kind={_safe_line(ref.source_kind)}")
        lines.append(f"  Untrusted/reference-only summary: {_safe_line(ref.summary)}")
    lines.append("Internal candidate context sections (reference-only, non-authoritative):")
    for section in sections:
        lines.append(f"## Reference section {_safe_line(section.section_id)} ({_safe_line(section.section_kind)})")
        if section.ref_ids:
            lines.append("Refs: " + ", ".join(_safe_line(ref_id) for ref_id in section.ref_ids))
        lines.append("Untrusted/reference-only section summary: " + _safe_line(section.summary))
        for caveat in section.caveats:
            lines.append("Caveat: " + _safe_line(caveat))
        for note in section.boundary_notes:
            lines.append("Boundary: " + _safe_line(note))
    lines.append("END INTERNAL NO-LLM CANDIDATE - not sent to model; no LLM/tool/runtime/memory/retention authority.")
    return "\n".join(lines)


def compute_internal_prompt_candidate_digest(candidate: InternalPromptCandidate | Mapping[str, Any]) -> str:
    data = dict(_mapping(candidate))
    data.pop("candidate_digest", None)
    data.pop("candidate_id", None)
    encoded = json.dumps(_stable(data), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def materialize_internal_no_llm_prompt_candidate(candidate_input: InternalPromptCandidateInput | Mapping[str, Any]) -> InternalPromptCandidate:
    data = _mapping(candidate_input)
    findings = validate_internal_prompt_candidate_input(candidate_input)
    status = _status_for_findings(findings, candidate_input)
    policy = _mapping(data.get("policy_decision", {}))
    audit = _mapping(data.get("audit_receipt", {}))
    review = _mapping(data.get("operator_review_receipt", {}))
    adapter = _mapping(data.get("adapter_payload", {}))
    blueprint = _mapping(data.get("blueprint", {}))
    refs = _derive_refs(data)
    sections = _derive_sections(data)
    caveats = tuple(dict.fromkeys((*_tuple_str(audit.get("preserved_caveats", ())), *_tuple_str(data.get("preserved_caveats", ())), *(c for ref in refs for c in ref.caveats), *(c for section in sections for c in section.caveats))))
    boundary_notes = tuple(dict.fromkeys((*_tuple_str(data.get("preserved_boundary_notes", ())), *(n for ref in refs for n in ref.boundary_notes), *(n for section in sections for n in section.boundary_notes))))
    ready = status in {
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_READY,
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_READY_WITH_WARNINGS,
    }
    internal_candidate_text = ""
    if ready:
        internal_candidate_text = _compose_internal_candidate_text(
            packet_id=str(audit.get("packet_id", policy.get("packet_id", adapter.get("packet_id", "")))),
            packet_scope=str(audit.get("packet_scope", policy.get("packet_scope", adapter.get("packet_scope", "")))),
            refs=refs,
            sections=sections,
            caveats=caveats,
            boundary_notes=boundary_notes,
        )
    warnings = tuple(str(_mapping(w).get("code", _mapping(w).get("detail", w))) for w in audit.get("warnings", ()) or ())
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "internal no-LLM candidate gates satisfied"
    candidate = InternalPromptCandidate(
        candidate_id="",
        status=status,
        internal_only=bool(data.get("internal_only", False)),
        operator_visible_only=bool(data.get("operator_visible_only", False)),
        no_llm=bool(data.get("no_llm", False)),
        policy_decision_id=str(policy.get("decision_id", "")),
        policy_status=str(policy.get("policy_status", "")),
        policy_digest=str(policy.get("policy_digest", "")),
        audit_receipt_id=str(audit.get("receipt_id", "")),
        audit_receipt_digest=str(audit.get("receipt_digest", "")),
        review_receipt_id=str(review.get("review_receipt_id", "")),
        review_digest=str(review.get("review_digest", "")),
        adapter_payload_id=str(adapter.get("adapter_payload_id", audit.get("adapter_payload_id", ""))),
        adapter_payload_digest=str(adapter.get("digest", audit.get("adapter_payload_digest", ""))),
        blueprint_id=str(blueprint.get("blueprint_id", audit.get("blueprint_id", ""))),
        blueprint_digest=str(blueprint.get("blueprint_digest", audit.get("blueprint_digest", ""))),
        packet_id=str(audit.get("packet_id", policy.get("packet_id", adapter.get("packet_id", "")))),
        packet_scope=str(audit.get("packet_scope", policy.get("packet_scope", adapter.get("packet_scope", "")))),
        candidate_sections=sections,
        candidate_refs=refs,
        internal_candidate_text=internal_candidate_text,
        rendered_section_count=len(sections) if ready else 0,
        ref_count=len(refs),
        preserved_caveats=caveats,
        preserved_boundary_notes=boundary_notes,
        warnings=warnings,
        findings=tuple(findings),
        rationale=rationale,
        candidate_digest="",
    )
    digest = compute_internal_prompt_candidate_digest(candidate)
    return replace(candidate, candidate_id=f"internal-prompt-candidate:{candidate.packet_id or 'missing'}:{digest[:16]}", candidate_digest=digest)


def internal_prompt_candidate_is_no_llm(candidate: InternalPromptCandidate | Mapping[str, Any]) -> bool:
    data = _mapping(candidate)
    return bool(data.get("no_llm") is True and data.get("does_not_call_llm") is True and data.get("live_model_call") is False)


def internal_prompt_candidate_is_operator_visible_only(candidate: InternalPromptCandidate | Mapping[str, Any]) -> bool:
    data = _mapping(candidate)
    return bool(data.get("internal_only") is True and data.get("operator_visible_only") is True and data.get("internal_candidate_only") is True)


def internal_prompt_candidate_contains_no_raw_payloads(candidate: InternalPromptCandidate | Mapping[str, Any]) -> bool:
    return not _contains_key_fragment(candidate, _FORBIDDEN_RAW_KEY_FRAGMENTS)


def internal_prompt_candidate_has_no_runtime_authority(candidate: InternalPromptCandidate | Mapping[str, Any]) -> bool:
    data = _mapping(candidate)
    return bool(data.get("live_prompt_assembly") is False and data.get("live_model_call") is False and not _contains_key_fragment(candidate, _RUNTIME_KEY_FRAGMENTS))


def internal_prompt_candidate_has_no_tool_or_action_capability(candidate: InternalPromptCandidate | Mapping[str, Any]) -> bool:
    data = _mapping(candidate)
    return bool(data.get("no_tool_or_action_capability") is True and not _contains_key_fragment(candidate, _CAPABILITY_KEY_FRAGMENTS))


def internal_prompt_candidate_preserves_boundaries(candidate: InternalPromptCandidate | Mapping[str, Any]) -> bool:
    data = _mapping(candidate)
    text = str(data.get("internal_candidate_text", ""))
    if data.get("status") not in {
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_READY,
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_READY_WITH_WARNINGS,
    }:
        return not text
    required = ("INTERNAL NO-LLM CANDIDATE", "not been sent to a model", "OPERATOR VISIBLE ONLY", "UNTRUSTED / REFERENCE-ONLY")
    return all(marker in text for marker in required)


def explain_internal_prompt_candidate_findings(candidate_or_findings: InternalPromptCandidate | Mapping[str, Any] | Sequence[InternalPromptCandidateFinding]) -> tuple[str, ...]:
    if isinstance(candidate_or_findings, Sequence) and not isinstance(candidate_or_findings, (str, bytes, Mapping)):
        findings = tuple(candidate_or_findings)
    else:
        findings = tuple(_mapping(candidate_or_findings).get("findings", ()) or ())
    return tuple(f"{_mapping(finding).get('severity', '')}:{_mapping(finding).get('code', '')}:{_mapping(finding).get('detail', '')}" for finding in findings)


def summarize_internal_prompt_candidate(candidate: InternalPromptCandidate | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(candidate)
    return {
        "candidate_id": str(data.get("candidate_id", "")),
        "status": str(data.get("status", "")),
        "policy_status": str(data.get("policy_status", "")),
        "packet_id": str(data.get("packet_id", "")),
        "packet_scope": str(data.get("packet_scope", "")),
        "rendered_section_count": int(data.get("rendered_section_count", 0)),
        "ref_count": int(data.get("ref_count", 0)),
        "finding_count": len(tuple(data.get("findings", ()) or ())),
        "candidate_digest": str(data.get("candidate_digest", "")),
        "internal_only": bool(data.get("internal_only", False)),
        "operator_visible_only": bool(data.get("operator_visible_only", False)),
        "no_llm": bool(data.get("no_llm", False)),
        "live_prompt_assembly": bool(data.get("live_prompt_assembly", True)),
        "live_model_call": bool(data.get("live_model_call", True)),
    }
