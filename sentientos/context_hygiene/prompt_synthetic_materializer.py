from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_materialization_audit import (
    PromptMaterializationAuditReceipt,
    audit_receipt_allows_shadow_materializer,
)
from sentientos.context_hygiene.prompt_materialization_policy import (
    PromptMaterializationPolicyDecision,
    PromptMaterializationPolicyRing,
    PromptMaterializationPolicyStatus,
    policy_decision_allows_synthetic_materializer,
    policy_decision_requires_operator_review,
)
from sentientos.context_hygiene.prompt_operator_review import (
    PromptOperatorReviewReceipt,
    operator_review_satisfies_policy_decision,
    validate_prompt_operator_review_receipt,
)


class SyntheticPromptMaterializationStatus:
    SYNTHETIC_PROMPT_READY = "synthetic_prompt_ready"
    SYNTHETIC_PROMPT_READY_WITH_WARNINGS = "synthetic_prompt_ready_with_warnings"
    SYNTHETIC_PROMPT_BLOCKED = "synthetic_prompt_blocked"
    SYNTHETIC_PROMPT_INVALID_INPUT = "synthetic_prompt_invalid_input"
    SYNTHETIC_PROMPT_POLICY_DENIED = "synthetic_prompt_policy_denied"
    SYNTHETIC_PROMPT_REVIEW_REQUIRED = "synthetic_prompt_review_required"
    SYNTHETIC_PROMPT_FORBIDDEN_REAL_CONTEXT = "synthetic_prompt_forbidden_real_context"
    SYNTHETIC_PROMPT_RUNTIME_AUTHORITY_DETECTED = "synthetic_prompt_runtime_authority_detected"


@dataclass(frozen=True)
class SyntheticPromptMaterializationFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class SyntheticPromptFixtureRef:
    ref_id: str
    ref_kind: str = "synthetic_fixture_ref"
    summary: str = ""
    caveats: tuple[str, ...] = field(default_factory=tuple)
    boundary_notes: tuple[str, ...] = field(default_factory=tuple)
    untrusted_reference_only: bool = True
    synthetic_only: bool = True


@dataclass(frozen=True)
class SyntheticPromptMaterializationSection:
    section_id: str
    section_kind: str
    synthetic_summary: str
    ref_ids: tuple[str, ...] = field(default_factory=tuple)
    caveats: tuple[str, ...] = field(default_factory=tuple)
    boundary_notes: tuple[str, ...] = field(default_factory=tuple)
    untrusted_reference_only: bool = True
    synthetic_only: bool = True


@dataclass(frozen=True)
class SyntheticPromptMaterializationBoundary:
    synthetic_only: bool = True
    fixture_only: bool = True
    real_context_used: bool = False
    live_prompt_materialization: bool = False
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True
    no_tool_or_action_capability: bool = True


@dataclass(frozen=True)
class SyntheticPromptMaterializationInput:
    policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any]
    audit_receipt: PromptMaterializationAuditReceipt | Mapping[str, Any]
    operator_review_receipt: PromptOperatorReviewReceipt | Mapping[str, Any] | None = None
    synthetic_fixture_only: bool = True
    requested_ring: str = PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY
    fixture_id: str = ""
    fixture_scope: str = ""
    synthetic_refs: tuple[SyntheticPromptFixtureRef | Mapping[str, Any], ...] = field(default_factory=tuple)
    synthetic_sections: tuple[SyntheticPromptMaterializationSection | Mapping[str, Any], ...] = field(default_factory=tuple)
    allowed_boundary_notes: tuple[str, ...] = field(default_factory=tuple)
    expected_caveats: tuple[str, ...] = field(default_factory=tuple)
    feature_flag_state: Mapping[str, bool] = field(default_factory=dict)
    boundary: SyntheticPromptMaterializationBoundary = field(default_factory=SyntheticPromptMaterializationBoundary)


@dataclass(frozen=True)
class SyntheticPromptCandidate:
    candidate_id: str
    status: str
    fixture_id: str
    fixture_scope: str
    policy_decision_id: str
    policy_status: str
    policy_digest: str
    review_receipt_id: str
    review_digest: str
    audit_receipt_id: str
    audit_receipt_digest: str
    synthetic_sections: tuple[SyntheticPromptMaterializationSection, ...]
    synthetic_prompt_text: str
    rendered_section_count: int
    synthetic_ref_count: int
    preserved_caveats: tuple[str, ...]
    preserved_boundary_notes: tuple[str, ...]
    findings: tuple[SyntheticPromptMaterializationFinding, ...]
    rationale: str
    candidate_digest: str
    synthetic_only: bool = True
    fixture_only: bool = True
    real_context_used: bool = False
    live_prompt_materialization: bool = False
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True
    no_tool_or_action_capability: bool = True
    boundary: SyntheticPromptMaterializationBoundary = field(default_factory=SyntheticPromptMaterializationBoundary)


_SYNTHETIC_PREFIXES = ("synthetic:", "fixture:", "test:")
_FORBIDDEN_REF_TOKENS = (
    "memory:",
    "mem:",
    "http://",
    "https://",
    "file://",
    "s3://",
)
_FORBIDDEN_KEY_FRAGMENTS = (
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
    "system_prompt",
    "developer_prompt",
    "final_prompt_text",
    "assembled_prompt",
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
    "memory_write",
    "write_memory",
    "retention_commit",
    "commit_retention",
    "feedback_trigger",
    "execute_action",
    "route_work",
    "admit_work",
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
)
_REAL_PATH_RE = re.compile(r"(^/|^[A-Za-z]:\\|\.\./|\./|[/\\][\w.-]+[/\\])")
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
        return tuple(str(item) for item in value)
    return ()


def _fixture_ref(value: SyntheticPromptFixtureRef | Mapping[str, Any]) -> SyntheticPromptFixtureRef:
    if isinstance(value, SyntheticPromptFixtureRef):
        return value
    data = _mapping(value)
    return SyntheticPromptFixtureRef(
        ref_id=str(data.get("ref_id", "")),
        ref_kind=str(data.get("ref_kind", "synthetic_fixture_ref")),
        summary=str(data.get("summary", data.get("synthetic_summary", ""))),
        caveats=_tuple_str(data.get("caveats", ())),
        boundary_notes=_tuple_str(data.get("boundary_notes", ())),
        untrusted_reference_only=bool(data.get("untrusted_reference_only", True)),
        synthetic_only=bool(data.get("synthetic_only", True)),
    )


def _section(value: SyntheticPromptMaterializationSection | Mapping[str, Any]) -> SyntheticPromptMaterializationSection:
    if isinstance(value, SyntheticPromptMaterializationSection):
        return value
    data = _mapping(value)
    return SyntheticPromptMaterializationSection(
        section_id=str(data.get("section_id", "")),
        section_kind=str(data.get("section_kind", "synthetic_fixture_section")),
        synthetic_summary=str(data.get("synthetic_summary", data.get("summary", ""))),
        ref_ids=_tuple_str(data.get("ref_ids", ())),
        caveats=_tuple_str(data.get("caveats", ())),
        boundary_notes=_tuple_str(data.get("boundary_notes", ())),
        untrusted_reference_only=bool(data.get("untrusted_reference_only", True)),
        synthetic_only=bool(data.get("synthetic_only", True)),
    )


def _finding(code: str, detail: str, severity: str = "blocker") -> SyntheticPromptMaterializationFinding:
    return SyntheticPromptMaterializationFinding(code=code, detail=detail, severity=severity)


def _looks_synthetic_id(value: str) -> bool:
    return str(value).startswith(_SYNTHETIC_PREFIXES)


def _looks_real_reference(value: str) -> bool:
    lowered = str(value).strip().lower()
    if not lowered:
        return False
    if lowered.startswith(_SYNTHETIC_PREFIXES):
        return False
    if lowered.startswith(("embodiment:", "packet:", "context:", "source:", "provenance:", "prov:", "adapter-payload:")):
        return True
    if lowered.startswith(_FORBIDDEN_REF_TOKENS):
        return True
    if _REAL_PATH_RE.search(str(value)):
        return True
    return False


def _negative_marker_key(key: str) -> bool:
    lowered = key.lower()
    return lowered.startswith(("does_not_", "no_", "non_", "not_", "without_", "must_not_")) or "does_not" in lowered or "must_not" in lowered


def _contains_key_fragment(value: Any, fragments: tuple[str, ...]) -> bool:
    return any(not _negative_marker_key(key) and any(fragment in key.lower() for fragment in fragments) and bool(nested) for key, nested in _walk(value))


def _contains_real_reference_value(value: Any) -> bool:
    for key, nested in _walk(value):
        key_lower = key.lower()
        if key_lower == "synthetic_prompt_text":
            continue
        if any(token in key_lower for token in ("packet_id", "context_id", "memory_ref", "source_path", "source_locator", "provenance_ref", "adapter_payload_id", "packet_scope", "uri", "url")):
            if isinstance(nested, str) and not _looks_synthetic_id(nested) and _looks_real_reference(nested):
                return True
            if isinstance(nested, str) and key_lower in {"packet_id", "packet_scope", "adapter_payload_id"} and nested and not _looks_synthetic_id(nested):
                return True
        if isinstance(nested, str) and _looks_real_reference(nested):
            return True
    return False


def _has_runtime_markers(value: Any) -> bool:
    return _contains_key_fragment(value, _RUNTIME_KEY_FRAGMENTS)


def _has_capability_markers(value: Any) -> bool:
    return _contains_key_fragment(value, _CAPABILITY_KEY_FRAGMENTS)


def _has_forbidden_payload_markers(value: Any) -> bool:
    return _contains_key_fragment(value, _FORBIDDEN_KEY_FRAGMENTS)


def build_synthetic_prompt_materialization_input(
    *,
    policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any],
    audit_receipt: PromptMaterializationAuditReceipt | Mapping[str, Any],
    operator_review_receipt: PromptOperatorReviewReceipt | Mapping[str, Any] | None = None,
    synthetic_fixture_only: bool = True,
    requested_ring: str = PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY,
    fixture_id: str,
    fixture_scope: str,
    synthetic_refs: Sequence[SyntheticPromptFixtureRef | Mapping[str, Any]] = (),
    synthetic_sections: Sequence[SyntheticPromptMaterializationSection | Mapping[str, Any]] = (),
    allowed_boundary_notes: Sequence[str] = (),
    expected_caveats: Sequence[str] = (),
    feature_flag_state: Mapping[str, bool] | None = None,
) -> SyntheticPromptMaterializationInput:
    return SyntheticPromptMaterializationInput(
        policy_decision=policy_decision,
        audit_receipt=audit_receipt,
        operator_review_receipt=operator_review_receipt,
        synthetic_fixture_only=synthetic_fixture_only,
        requested_ring=requested_ring,
        fixture_id=fixture_id,
        fixture_scope=fixture_scope,
        synthetic_refs=tuple(synthetic_refs),
        synthetic_sections=tuple(synthetic_sections),
        allowed_boundary_notes=tuple(str(item) for item in allowed_boundary_notes),
        expected_caveats=tuple(str(item) for item in expected_caveats),
        feature_flag_state=dict(feature_flag_state or {}),
    )


def validate_synthetic_prompt_materialization_input(materializer_input: SyntheticPromptMaterializationInput | Mapping[str, Any]) -> tuple[SyntheticPromptMaterializationFinding, ...]:
    data = _mapping(materializer_input)
    if not data:
        return (_finding("synthetic_input_malformed", "synthetic materializer input is malformed"),)
    findings: list[SyntheticPromptMaterializationFinding] = []
    policy = data.get("policy_decision")
    audit = data.get("audit_receipt")
    review = data.get("operator_review_receipt")
    requested_ring = str(data.get("requested_ring", ""))
    fixture_id = str(data.get("fixture_id", ""))
    fixture_scope = str(data.get("fixture_scope", ""))
    refs = tuple(_fixture_ref(item) for item in data.get("synthetic_refs", ()) or ())
    sections = tuple(_section(item) for item in data.get("synthetic_sections", ()) or ())
    expected_caveats = _tuple_str(data.get("expected_caveats", ()))
    allowed_boundary_notes = _tuple_str(data.get("allowed_boundary_notes", ()))

    if not bool(data.get("synthetic_fixture_only", False)):
        findings.append(_finding("synthetic_fixture_only_required", "synthetic_fixture_only must be true"))
    if requested_ring != PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY:
        findings.append(_finding("synthetic_ring_required", "requested_ring must be ring_synthetic_fixture_only"))
    for label, value in (("fixture_id", fixture_id), ("fixture_scope", fixture_scope)):
        if not value or not _looks_synthetic_id(value):
            findings.append(_finding("non_synthetic_fixture_identifier", f"{label} must use synthetic:, fixture:, or test: prefix"))

    policy_data = _mapping(policy)
    audit_data = _mapping(audit)
    if not policy_data:
        findings.append(_finding("missing_policy_decision", "Phase 77 policy decision is required"))
    elif not policy_decision_allows_synthetic_materializer(policy):
        if policy_decision_requires_operator_review(policy):
            if review is None:
                findings.append(_finding("operator_review_required", "Phase 77 policy requires a matching Phase 78 operator review", "review"))
            elif not operator_review_satisfies_policy_decision(policy, review):
                findings.append(_finding("operator_review_unsatisfied", "operator review receipt does not satisfy policy decision"))
        else:
            findings.append(_finding("policy_denied", "Phase 77 policy does not allow synthetic materializer"))
    if review is not None:
        for review_finding in validate_prompt_operator_review_receipt(review):
            findings.append(_finding(f"review_{review_finding.code}", review_finding.detail, review_finding.severity))
    if not audit_data:
        findings.append(_finding("missing_audit_receipt", "Phase 74 audit receipt is required"))
    elif not audit_receipt_allows_shadow_materializer(audit):
        findings.append(_finding("audit_disallows_shadow_materializer", "Phase 74 audit receipt does not allow shadow materializer"))

    for label, item in (("policy", policy), ("audit", audit), ("review", review), ("input", materializer_input)):
        if item is not None and _has_forbidden_payload_markers(item):
            findings.append(_finding("forbidden_payload_marker", f"{label} contains forbidden payload or prompt marker"))
        if item is not None and _has_runtime_markers(item):
            findings.append(_finding("runtime_authority_marker", f"{label} contains runtime authority marker"))
        if item is not None and _has_capability_markers(item):
            findings.append(_finding("capability_marker", f"{label} contains LLM/tool/action/retention/memory capability marker"))
        if item is not None and _contains_real_reference_value(item):
            findings.append(_finding("forbidden_real_context", f"{label} contains real-looking context, source, URI, path, or provenance reference"))

    if not refs:
        findings.append(_finding("synthetic_refs_missing", "at least one synthetic fixture reference is required"))
    if not sections:
        findings.append(_finding("synthetic_sections_missing", "at least one synthetic section is required"))
    ref_ids = {ref.ref_id for ref in refs}
    for ref in refs:
        if not _looks_synthetic_id(ref.ref_id):
            findings.append(_finding("non_synthetic_ref_id", f"reference {ref.ref_id!r} is not synthetic"))
        if not ref.synthetic_only or not ref.untrusted_reference_only:
            findings.append(_finding("ref_boundary_missing", f"reference {ref.ref_id!r} must be synthetic-only and untrusted/reference-only"))
    for section in sections:
        if not _looks_synthetic_id(section.section_id):
            findings.append(_finding("non_synthetic_section_id", f"section {section.section_id!r} is not synthetic"))
        if not section.synthetic_only or not section.untrusted_reference_only:
            findings.append(_finding("section_boundary_missing", f"section {section.section_id!r} must be synthetic-only and untrusted/reference-only"))
        if section.section_kind.lower() in _FORBIDDEN_SECTION_KINDS:
            findings.append(_finding("authority_section_forbidden", "synthetic refs cannot create system/developer instruction sections"))
        for ref_id in section.ref_ids:
            if ref_id not in ref_ids:
                findings.append(_finding("unknown_synthetic_ref", f"section references unknown synthetic ref {ref_id!r}"))
    all_caveats = set(expected_caveats)
    all_notes = set(allowed_boundary_notes)
    rendered_caveats = set().union(*(set(section.caveats) for section in sections), *(set(ref.caveats) for ref in refs))
    rendered_notes = set().union(*(set(section.boundary_notes) for section in sections), *(set(ref.boundary_notes) for ref in refs))
    if not all_caveats.issubset(rendered_caveats | set(expected_caveats)):
        findings.append(_finding("caveat_not_preserved", "expected caveats must remain preserved"))
    if not all_notes.issubset(rendered_notes | set(allowed_boundary_notes)):
        findings.append(_finding("boundary_note_not_preserved", "allowed boundary notes must remain preserved"))
    return tuple(findings)


def _status_for_findings(findings: Sequence[SyntheticPromptMaterializationFinding], materializer_input: SyntheticPromptMaterializationInput | Mapping[str, Any]) -> str:
    codes = {finding.code for finding in findings}
    severities = {finding.severity for finding in findings}
    if "synthetic_input_malformed" in codes or "missing_policy_decision" in codes or "missing_audit_receipt" in codes:
        return SyntheticPromptMaterializationStatus.SYNTHETIC_PROMPT_INVALID_INPUT
    if "operator_review_required" in codes:
        return SyntheticPromptMaterializationStatus.SYNTHETIC_PROMPT_REVIEW_REQUIRED
    if "policy_denied" in codes:
        return SyntheticPromptMaterializationStatus.SYNTHETIC_PROMPT_POLICY_DENIED
    if "forbidden_real_context" in codes or any(code.startswith("non_synthetic") for code in codes):
        return SyntheticPromptMaterializationStatus.SYNTHETIC_PROMPT_FORBIDDEN_REAL_CONTEXT
    if "runtime_authority_marker" in codes or "capability_marker" in codes:
        return SyntheticPromptMaterializationStatus.SYNTHETIC_PROMPT_RUNTIME_AUTHORITY_DETECTED
    if any(severity not in {"warning", "info", "non_blocking"} for severity in severities):
        return SyntheticPromptMaterializationStatus.SYNTHETIC_PROMPT_BLOCKED
    warning_sources = _mapping(materializer_input).get("audit_receipt", {})
    if findings or _mapping(warning_sources).get("warnings") or _mapping(warning_sources).get("preserved_caveats"):
        return SyntheticPromptMaterializationStatus.SYNTHETIC_PROMPT_READY_WITH_WARNINGS
    return SyntheticPromptMaterializationStatus.SYNTHETIC_PROMPT_READY


def _safe_line(value: str) -> str:
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())


def _compose_synthetic_fixture_candidate_text(
    *,
    fixture_id: str,
    fixture_scope: str,
    refs: Sequence[SyntheticPromptFixtureRef],
    sections: Sequence[SyntheticPromptMaterializationSection],
    caveats: Sequence[str],
    boundary_notes: Sequence[str],
) -> str:
    lines = [
        "SYNTHETIC FIXTURE ONLY - PROMPT-SHAPED CANDIDATE",
        "NOT REAL USER CONTENT; NOT REAL CONTEXT; NOT MEMORY; NOT A LIVE PROMPT MATERIALIZATION.",
        f"Fixture: {_safe_line(fixture_id)}",
        f"Fixture scope: {_safe_line(fixture_scope)}",
        "All fixture refs below are UNTRUSTED / REFERENCE-ONLY and carry no system or developer authority.",
    ]
    if caveats:
        lines.append("Caveats preserved:")
        lines.extend(f"- {_safe_line(caveat)}" for caveat in caveats)
    if boundary_notes:
        lines.append("Boundary notes preserved:")
        lines.extend(f"- {_safe_line(note)}" for note in boundary_notes)
    lines.append("Synthetic fixture refs:")
    for ref in refs:
        lines.append(f"- [{_safe_line(ref.ref_id)}] untrusted/reference-only {_safe_line(ref.summary)}")
    lines.append("Synthetic candidate sections:")
    for section in sections:
        lines.append(f"## Synthetic section {_safe_line(section.section_id)} ({_safe_line(section.section_kind)})")
        if section.ref_ids:
            lines.append("Refs: " + ", ".join(_safe_line(ref_id) for ref_id in section.ref_ids))
        lines.append("Untrusted fixture summary: " + _safe_line(section.synthetic_summary))
        for caveat in section.caveats:
            lines.append("Caveat: " + _safe_line(caveat))
        for note in section.boundary_notes:
            lines.append("Boundary: " + _safe_line(note))
    lines.append("END SYNTHETIC FIXTURE ONLY CANDIDATE - no LLM/tool/runtime/memory/retention capability.")
    return "\n".join(lines)


def compute_synthetic_prompt_candidate_digest(candidate: SyntheticPromptCandidate | Mapping[str, Any]) -> str:
    data = dict(_mapping(candidate))
    data.pop("candidate_digest", None)
    data.pop("candidate_id", None)
    encoded = json.dumps(_stable(data), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def materialize_synthetic_prompt_candidate(materializer_input: SyntheticPromptMaterializationInput | Mapping[str, Any]) -> SyntheticPromptCandidate:
    data = _mapping(materializer_input)
    findings = validate_synthetic_prompt_materialization_input(materializer_input)
    status = _status_for_findings(findings, materializer_input)
    refs = tuple(_fixture_ref(item) for item in data.get("synthetic_refs", ()) or ())
    sections = tuple(_section(item) for item in data.get("synthetic_sections", ()) or ())
    policy = _mapping(data.get("policy_decision", {}))
    audit = _mapping(data.get("audit_receipt", {}))
    review = _mapping(data.get("operator_review_receipt", {}))
    caveats = tuple(dict.fromkeys((*_tuple_str(data.get("expected_caveats", ())), *(c for ref in refs for c in ref.caveats), *(c for section in sections for c in section.caveats))))
    boundary_notes = tuple(dict.fromkeys((*_tuple_str(data.get("allowed_boundary_notes", ())), *(n for ref in refs for n in ref.boundary_notes), *(n for section in sections for n in section.boundary_notes))))
    ready = status in {
        SyntheticPromptMaterializationStatus.SYNTHETIC_PROMPT_READY,
        SyntheticPromptMaterializationStatus.SYNTHETIC_PROMPT_READY_WITH_WARNINGS,
    }
    synthetic_prompt_text = ""
    if ready:
        synthetic_prompt_text = _compose_synthetic_fixture_candidate_text(
            fixture_id=str(data.get("fixture_id", "")),
            fixture_scope=str(data.get("fixture_scope", "")),
            refs=refs,
            sections=sections,
            caveats=caveats,
            boundary_notes=boundary_notes,
        )
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "synthetic fixture gates satisfied"
    candidate = SyntheticPromptCandidate(
        candidate_id="",
        status=status,
        fixture_id=str(data.get("fixture_id", "")),
        fixture_scope=str(data.get("fixture_scope", "")),
        policy_decision_id=str(policy.get("decision_id", "")),
        policy_status=str(policy.get("policy_status", "")),
        policy_digest=str(policy.get("policy_digest", "")),
        review_receipt_id=str(review.get("review_receipt_id", "")),
        review_digest=str(review.get("review_digest", "")),
        audit_receipt_id=str(audit.get("receipt_id", "")),
        audit_receipt_digest=str(audit.get("receipt_digest", "")),
        synthetic_sections=sections,
        synthetic_prompt_text=synthetic_prompt_text,
        rendered_section_count=len(sections) if ready else 0,
        synthetic_ref_count=len(refs),
        preserved_caveats=caveats,
        preserved_boundary_notes=boundary_notes,
        findings=tuple(findings),
        rationale=rationale,
        candidate_digest="",
    )
    digest = compute_synthetic_prompt_candidate_digest(candidate)
    return replace(candidate, candidate_id=f"synthetic-prompt-candidate:{candidate.fixture_id}:{digest[:16]}", candidate_digest=digest)


def synthetic_prompt_candidate_is_fixture_only(candidate: SyntheticPromptCandidate | Mapping[str, Any]) -> bool:
    data = _mapping(candidate)
    return bool(data.get("synthetic_only", False) and data.get("fixture_only", False) and str(data.get("fixture_id", "")).startswith(_SYNTHETIC_PREFIXES))


def synthetic_prompt_candidate_contains_no_real_context(candidate: SyntheticPromptCandidate | Mapping[str, Any]) -> bool:
    data = _mapping(candidate)
    return bool(data.get("real_context_used") is False and not _contains_real_reference_value(candidate))


def synthetic_prompt_candidate_has_no_runtime_authority(candidate: SyntheticPromptCandidate | Mapping[str, Any]) -> bool:
    data = _mapping(candidate)
    return bool(data.get("live_prompt_materialization") is False and not _has_runtime_markers(candidate))


def synthetic_prompt_candidate_has_no_llm_or_tool_capability(candidate: SyntheticPromptCandidate | Mapping[str, Any]) -> bool:
    data = _mapping(candidate)
    return bool(data.get("does_not_call_llm") is True and data.get("no_tool_or_action_capability") is True and not _has_capability_markers(candidate))


def synthetic_prompt_candidate_preserves_boundaries(candidate: SyntheticPromptCandidate | Mapping[str, Any]) -> bool:
    data = _mapping(candidate)
    text = str(data.get("synthetic_prompt_text", ""))
    if data.get("status") not in {
        SyntheticPromptMaterializationStatus.SYNTHETIC_PROMPT_READY,
        SyntheticPromptMaterializationStatus.SYNTHETIC_PROMPT_READY_WITH_WARNINGS,
    }:
        return not text
    required = ("SYNTHETIC FIXTURE ONLY", "NOT REAL USER CONTENT", "UNTRUSTED / REFERENCE-ONLY")
    return all(marker in text for marker in required)


def explain_synthetic_prompt_materialization_findings(candidate_or_findings: SyntheticPromptCandidate | Mapping[str, Any] | Sequence[SyntheticPromptMaterializationFinding]) -> tuple[str, ...]:
    if isinstance(candidate_or_findings, Sequence) and not isinstance(candidate_or_findings, (str, bytes, Mapping)):
        findings = tuple(candidate_or_findings)
    else:
        findings = tuple(_mapping(candidate_or_findings).get("findings", ()) or ())
    return tuple(f"{_mapping(finding).get('severity', '')}:{_mapping(finding).get('code', '')}:{_mapping(finding).get('detail', '')}" for finding in findings)


def summarize_synthetic_prompt_candidate(candidate: SyntheticPromptCandidate | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(candidate)
    return {
        "candidate_id": str(data.get("candidate_id", "")),
        "status": str(data.get("status", "")),
        "fixture_id": str(data.get("fixture_id", "")),
        "fixture_scope": str(data.get("fixture_scope", "")),
        "policy_status": str(data.get("policy_status", "")),
        "rendered_section_count": int(data.get("rendered_section_count", 0)),
        "synthetic_ref_count": int(data.get("synthetic_ref_count", 0)),
        "finding_count": len(tuple(data.get("findings", ()) or ())),
        "candidate_digest": str(data.get("candidate_digest", "")),
        "synthetic_only": bool(data.get("synthetic_only", False)),
        "fixture_only": bool(data.get("fixture_only", False)),
        "live_prompt_materialization": bool(data.get("live_prompt_materialization", True)),
    }
