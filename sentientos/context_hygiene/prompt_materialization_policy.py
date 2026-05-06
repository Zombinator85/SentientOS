from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_materialization_audit import (
    PromptMaterializationAuditReceipt,
    PromptMaterializationAuditStatus,
    audit_receipt_allows_shadow_materializer,
    audit_receipt_chain_is_complete,
    audit_receipt_contains_no_prompt_text,
    audit_receipt_contains_no_raw_payloads,
    audit_receipt_has_no_runtime_authority,
)
from sentientos.context_hygiene.source_kind_contracts import get_context_source_kind_safety_contract


class PromptMaterializationPolicyStatus:
    POLICY_DENY = "policy_deny"
    POLICY_SHADOW_ONLY = "policy_shadow_only"
    POLICY_OPERATOR_REVIEW_REQUIRED = "policy_operator_review_required"
    POLICY_SYNTHETIC_MATERIALIZATION_ALLOWED = "policy_synthetic_materialization_allowed"
    POLICY_INVALID_INPUT = "policy_invalid_input"
    POLICY_RUNTIME_WIRING_DETECTED = "policy_runtime_wiring_detected"


class PromptMaterializationPolicyRing:
    RING_SHADOW_METADATA_ONLY = "ring_shadow_metadata_only"
    RING_SHADOW_RECEIPT_ONLY = "ring_shadow_receipt_only"
    RING_OPERATOR_REVIEW_QUEUE = "ring_operator_review_queue"
    RING_SYNTHETIC_FIXTURE_ONLY = "ring_synthetic_fixture_only"
    RING_INTERNAL_CANDIDATE_NO_LLM = "ring_internal_candidate_no_llm"
    RING_LIVE_LLM_FORBIDDEN = "ring_live_llm_forbidden"


@dataclass(frozen=True)
class PromptMaterializationPolicyReason:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class PromptMaterializationPolicyMitigation:
    code: str
    detail: str
    required: bool = True


@dataclass(frozen=True)
class PromptMaterializationPolicyBoundary:
    policy_decision_only: bool = True
    policy_enforcement_not_included: bool = True
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
class PromptMaterializationPolicyInput:
    receipt_id: str = ""
    audit_status: str = ""
    receipt_digest: str = ""
    digest_chain_complete: bool = False
    audit_allows_shadow_materializer: bool = False
    blueprint_status: str = ""
    preview_status: str = ""
    compliance_status: str = ""
    adapter_status: str = ""
    packet_id: str = ""
    packet_scope: str = ""
    source_kind_summary: Mapping[str, int] = field(default_factory=dict)
    preserved_caveats: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[Mapping[str, str], ...] = field(default_factory=tuple)
    violations: tuple[Mapping[str, str], ...] = field(default_factory=tuple)
    findings: tuple[Mapping[str, str], ...] = field(default_factory=tuple)
    boundary_summary: Mapping[str, Any] = field(default_factory=dict)
    provenance_summary: Mapping[str, Any] = field(default_factory=dict)
    privacy_summary: Mapping[str, Any] = field(default_factory=dict)
    truth_summary: Mapping[str, Any] = field(default_factory=dict)
    safety_summary: Mapping[str, Any] = field(default_factory=dict)
    ref_counts: Mapping[str, int] = field(default_factory=dict)
    section_counts: Mapping[str, int] = field(default_factory=dict)
    requested_ring: str = PromptMaterializationPolicyRing.RING_SHADOW_RECEIPT_ONLY
    synthetic_fixture_only: bool = False
    operator_review_present: bool = False
    operator_review_decision: str = ""
    feature_flag_state: Mapping[str, bool] = field(default_factory=dict)
    environment_label: str = ""
    no_runtime_markers: Mapping[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptMaterializationPolicyDecision:
    decision_id: str
    policy_status: str
    requested_ring: str
    effective_ring: str
    allowed: bool
    denied: bool
    requires_operator_review: bool
    allows_shadow_only: bool
    allows_synthetic_materializer: bool
    forbids_live_llm: bool
    forbids_memory_retrieval: bool
    forbids_memory_write: bool
    forbids_action_execution: bool
    forbids_retention_commit: bool
    reasons: tuple[PromptMaterializationPolicyReason, ...]
    required_mitigations: tuple[PromptMaterializationPolicyMitigation, ...]
    receipt_id: str
    receipt_digest: str
    packet_id: str
    packet_scope: str
    source_kind_summary: Mapping[str, int]
    caveat_count: int
    warning_count: int
    violation_count: int
    finding_count: int
    rationale: str
    policy_digest: str
    policy_decision_only: bool = True
    policy_enforcement_not_included: bool = True
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
    boundary: PromptMaterializationPolicyBoundary = field(default_factory=PromptMaterializationPolicyBoundary)


_ALLOWED_RINGS = frozenset(
    {
        PromptMaterializationPolicyRing.RING_SHADOW_METADATA_ONLY,
        PromptMaterializationPolicyRing.RING_SHADOW_RECEIPT_ONLY,
        PromptMaterializationPolicyRing.RING_OPERATOR_REVIEW_QUEUE,
        PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY,
        PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM,
        PromptMaterializationPolicyRing.RING_LIVE_LLM_FORBIDDEN,
    }
)
_SHADOW_RINGS = frozenset(
    {
        PromptMaterializationPolicyRing.RING_SHADOW_METADATA_ONLY,
        PromptMaterializationPolicyRing.RING_SHADOW_RECEIPT_ONLY,
    }
)
_OPERATOR_OR_HIGHER_RINGS = frozenset(
    {
        PromptMaterializationPolicyRing.RING_OPERATOR_REVIEW_QUEUE,
        PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY,
        PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM,
        PromptMaterializationPolicyRing.RING_LIVE_LLM_FORBIDDEN,
    }
)
_FORBIDDEN_PHASE77_RINGS = frozenset(
    {
        PromptMaterializationPolicyRing.RING_INTERNAL_CANDIDATE_NO_LLM,
        PromptMaterializationPolicyRing.RING_LIVE_LLM_FORBIDDEN,
    }
)
_READY_AUDIT_STATUSES = frozenset(
    {
        PromptMaterializationAuditStatus.AUDIT_READY_FOR_SHADOW_MATERIALIZATION,
        PromptMaterializationAuditStatus.AUDIT_READY_WITH_WARNINGS,
    }
)
_BLOCKED_STATUS_TOKENS = ("blocked", "not_applicable", "invalid", "runtime_wiring")
_FORBIDDEN_PROMPT_KEYS = frozenset({"prompt_text", "final_prompt_text", "assembled_prompt", "rendered_prompt", "system_prompt", "developer_prompt"})
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
    }
)
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
        "retention_commit",
        "can_commit_retention",
        "execute_action",
        "action_execution",
        "can_execute_action",
        "route_work",
        "admit_work",
        "execute_work",
        "llm_params",
        "llm_parameters",
        "model_params",
        "provider_params",
    }
)
_NON_RUNTIME_MARKERS = (
    "policy_decision_only",
    "policy_enforcement_not_included",
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
        return (value,)
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(str(item) for item in value)
    return ()


def _issue_tuple(value: Any) -> tuple[Mapping[str, str], ...]:
    if not isinstance(value, (tuple, list, set, frozenset)):
        return ()
    out: list[Mapping[str, str]] = []
    for issue in value:
        data = _mapping(issue)
        if data:
            out.append({"code": str(data.get("code", "")), "detail": str(data.get("detail", "")), "severity": str(data.get("severity", "")), "requires_review": str(data.get("requires_review", ""))})
    return tuple(out)


def _int_mapping(value: Any) -> Mapping[str, int]:
    data = _mapping(value)
    return {str(k): int(v) for k, v in data.items() if isinstance(v, int) or str(v).isdigit()}


def _bool_mapping(value: Any) -> Mapping[str, bool]:
    data = _mapping(value)
    return {str(k): bool(v) for k, v in data.items()}


def _reason(code: str, detail: str, severity: str = "blocker") -> PromptMaterializationPolicyReason:
    return PromptMaterializationPolicyReason(code=code, detail=detail, severity=severity)


def _mitigation(code: str, detail: str) -> PromptMaterializationPolicyMitigation:
    return PromptMaterializationPolicyMitigation(code=code, detail=detail, required=True)


def _contains_truthy_key(value: Any, keys: frozenset[str]) -> bool:
    return any(key in keys and bool(nested) for key, nested in _walk(value))


def _has_status_token(status: str) -> bool:
    lowered = str(status).lower()
    return any(token in lowered for token in _BLOCKED_STATUS_TOKENS)


def _review_required(item: Mapping[str, Any] | str) -> bool:
    if isinstance(item, str):
        lowered = item.lower()
        return "review" in lowered or "operator" in lowered
    detail = str(item.get("detail", "")).lower()
    code = str(item.get("code", "")).lower()
    severity = str(item.get("severity", "")).lower()
    requires_review = str(item.get("requires_review", "")).lower()
    return requires_review in {"1", "true", "yes", "required"} or "review" in detail or "operator_review" in code or severity == "review"


def _accepted_review(policy_input: PromptMaterializationPolicyInput) -> bool:
    return bool(policy_input.operator_review_present and policy_input.operator_review_decision in {"accepted", "approved", "allow", "accepted_for_synthetic_fixture"})


def _feature_enabled(policy_input: PromptMaterializationPolicyInput, key: str) -> bool | None:
    if key not in policy_input.feature_flag_state:
        return None
    return bool(policy_input.feature_flag_state[key])


def _ring_feature_enabled(policy_input: PromptMaterializationPolicyInput) -> bool | None:
    ring = policy_input.requested_ring
    if ring in _SHADOW_RINGS:
        return _feature_enabled(policy_input, "allow_shadow_policy")
    if ring == PromptMaterializationPolicyRing.RING_OPERATOR_REVIEW_QUEUE:
        return _feature_enabled(policy_input, "allow_operator_review_queue")
    if ring == PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY:
        return _feature_enabled(policy_input, "allow_synthetic_fixture_policy")
    return False


def _unknown_source_kind(summary: Mapping[str, int]) -> bool:
    if not summary:
        return False
    for source_kind in summary:
        if source_kind == "unknown":
            return True
        contract = get_context_source_kind_safety_contract(source_kind)
        if contract.source_kind == "unknown" and source_kind != "unknown":
            return True
    return False


def build_prompt_materialization_policy_input(
    receipt: PromptMaterializationAuditReceipt | Mapping[str, Any] | None = None,
    *,
    requested_ring: str = PromptMaterializationPolicyRing.RING_SHADOW_RECEIPT_ONLY,
    synthetic_fixture_only: bool = False,
    operator_review_present: bool = False,
    operator_review_decision: str = "",
    feature_flag_state: Mapping[str, bool] | None = None,
    environment_label: str = "",
    no_runtime_markers: Mapping[str, bool] | None = None,
    **overrides: Any,
) -> PromptMaterializationPolicyInput:
    data = _mapping(receipt)
    values: dict[str, Any] = {
        "receipt_id": str(data.get("receipt_id", "")),
        "audit_status": str(data.get("audit_status", "")),
        "receipt_digest": str(data.get("receipt_digest", "")),
        "digest_chain_complete": bool(data.get("digest_chain_complete", False)) and (audit_receipt_chain_is_complete(receipt) if receipt is not None else False),
        "audit_allows_shadow_materializer": bool(audit_receipt_allows_shadow_materializer(receipt)) if receipt is not None else False,
        "blueprint_status": str(data.get("blueprint_status", "")),
        "preview_status": str(data.get("preview_status", "")),
        "compliance_status": str(data.get("compliance_status", "")),
        "adapter_status": str(data.get("adapter_status", "")),
        "packet_id": str(data.get("packet_id", "")),
        "packet_scope": str(data.get("packet_scope", "")),
        "source_kind_summary": _int_mapping(data.get("source_kind_summary", {})),
        "preserved_caveats": _tuple_str(data.get("preserved_caveats", ())),
        "warnings": _issue_tuple(data.get("warnings", ())),
        "violations": _issue_tuple(data.get("violations", ())),
        "findings": _issue_tuple(data.get("findings", ())),
        "boundary_summary": _mapping(data.get("boundary_summary", {})),
        "provenance_summary": _mapping(data.get("provenance_summary", {})),
        "privacy_summary": _mapping(data.get("privacy_summary", {})),
        "truth_summary": _mapping(data.get("truth_summary", {})),
        "safety_summary": _mapping(data.get("safety_summary", {})),
        "ref_counts": _int_mapping(data.get("ref_counts", {})),
        "section_counts": _int_mapping(data.get("section_counts", {})),
        "requested_ring": str(requested_ring),
        "synthetic_fixture_only": bool(synthetic_fixture_only),
        "operator_review_present": bool(operator_review_present),
        "operator_review_decision": str(operator_review_decision),
        "feature_flag_state": _bool_mapping(feature_flag_state or {}),
        "environment_label": str(environment_label),
        "no_runtime_markers": _bool_mapping(no_runtime_markers or {marker: True for marker in _NON_RUNTIME_MARKERS}),
    }
    values.update(overrides)
    return PromptMaterializationPolicyInput(**values)


def _validate_input(policy_input: PromptMaterializationPolicyInput | Mapping[str, Any]) -> PromptMaterializationPolicyInput | None:
    if isinstance(policy_input, PromptMaterializationPolicyInput):
        return policy_input
    data = _mapping(policy_input)
    if not data:
        return None
    try:
        return PromptMaterializationPolicyInput(
            receipt_id=str(data.get("receipt_id", "")),
            audit_status=str(data.get("audit_status", "")),
            receipt_digest=str(data.get("receipt_digest", "")),
            digest_chain_complete=bool(data.get("digest_chain_complete", False)),
            audit_allows_shadow_materializer=bool(data.get("audit_allows_shadow_materializer", False)),
            blueprint_status=str(data.get("blueprint_status", "")),
            preview_status=str(data.get("preview_status", "")),
            compliance_status=str(data.get("compliance_status", "")),
            adapter_status=str(data.get("adapter_status", "")),
            packet_id=str(data.get("packet_id", "")),
            packet_scope=str(data.get("packet_scope", "")),
            source_kind_summary=_int_mapping(data.get("source_kind_summary", {})),
            preserved_caveats=_tuple_str(data.get("preserved_caveats", ())),
            warnings=_issue_tuple(data.get("warnings", ())),
            violations=_issue_tuple(data.get("violations", ())),
            findings=_issue_tuple(data.get("findings", ())),
            boundary_summary=_mapping(data.get("boundary_summary", {})),
            provenance_summary=_mapping(data.get("provenance_summary", {})),
            privacy_summary=_mapping(data.get("privacy_summary", {})),
            truth_summary=_mapping(data.get("truth_summary", {})),
            safety_summary=_mapping(data.get("safety_summary", {})),
            ref_counts=_int_mapping(data.get("ref_counts", {})),
            section_counts=_int_mapping(data.get("section_counts", {})),
            requested_ring=str(data.get("requested_ring", "")),
            synthetic_fixture_only=bool(data.get("synthetic_fixture_only", False)),
            operator_review_present=bool(data.get("operator_review_present", False)),
            operator_review_decision=str(data.get("operator_review_decision", "")),
            feature_flag_state=_bool_mapping(data.get("feature_flag_state", {})),
            environment_label=str(data.get("environment_label", "")),
            no_runtime_markers=_bool_mapping(data.get("no_runtime_markers", {})),
        )
    except Exception:
        return None


def compute_prompt_materialization_policy_digest(decision: PromptMaterializationPolicyDecision | Mapping[str, Any]) -> str:
    data = dict(_mapping(decision))
    data.pop("policy_digest", None)
    payload = {
        "policy_status": data.get("policy_status", ""),
        "requested_ring": data.get("requested_ring", ""),
        "effective_ring": data.get("effective_ring", ""),
        "allowed": bool(data.get("allowed", False)),
        "denied": bool(data.get("denied", False)),
        "requires_operator_review": bool(data.get("requires_operator_review", False)),
        "allows_shadow_only": bool(data.get("allows_shadow_only", False)),
        "allows_synthetic_materializer": bool(data.get("allows_synthetic_materializer", False)),
        "reasons": _stable(data.get("reasons", ())),
        "required_mitigations": _stable(data.get("required_mitigations", ())),
        "receipt_id": data.get("receipt_id", ""),
        "receipt_digest": data.get("receipt_digest", ""),
        "packet_id": data.get("packet_id", ""),
        "packet_scope": data.get("packet_scope", ""),
        "source_kind_summary": _stable(data.get("source_kind_summary", {})),
        "caveat_count": int(data.get("caveat_count", 0)),
        "warning_count": int(data.get("warning_count", 0)),
        "violation_count": int(data.get("violation_count", 0)),
        "finding_count": int(data.get("finding_count", 0)),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _finalize_decision(
    policy_input: PromptMaterializationPolicyInput,
    status: str,
    effective_ring: str,
    reasons: Sequence[PromptMaterializationPolicyReason],
    mitigations: Sequence[PromptMaterializationPolicyMitigation],
) -> PromptMaterializationPolicyDecision:
    allowed = status in {
        PromptMaterializationPolicyStatus.POLICY_SHADOW_ONLY,
        PromptMaterializationPolicyStatus.POLICY_SYNTHETIC_MATERIALIZATION_ALLOWED,
    }
    decision = PromptMaterializationPolicyDecision(
        decision_id="",
        policy_status=status,
        requested_ring=policy_input.requested_ring,
        effective_ring=effective_ring,
        allowed=allowed,
        denied=not allowed and status != PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED,
        requires_operator_review=status == PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED,
        allows_shadow_only=status == PromptMaterializationPolicyStatus.POLICY_SHADOW_ONLY,
        allows_synthetic_materializer=status == PromptMaterializationPolicyStatus.POLICY_SYNTHETIC_MATERIALIZATION_ALLOWED,
        forbids_live_llm=True,
        forbids_memory_retrieval=True,
        forbids_memory_write=True,
        forbids_action_execution=True,
        forbids_retention_commit=True,
        reasons=tuple(reasons),
        required_mitigations=tuple(mitigations),
        receipt_id=policy_input.receipt_id,
        receipt_digest=policy_input.receipt_digest,
        packet_id=policy_input.packet_id,
        packet_scope=policy_input.packet_scope,
        source_kind_summary=dict(policy_input.source_kind_summary),
        caveat_count=len(policy_input.preserved_caveats),
        warning_count=len(policy_input.warnings),
        violation_count=len(policy_input.violations),
        finding_count=len(policy_input.findings),
        rationale="; ".join(reason.detail for reason in reasons) or f"{status}: default deny-by-policy posture",
        policy_digest="",
    )
    digest = compute_prompt_materialization_policy_digest(decision)
    return replace(decision, decision_id=f"policy:{policy_input.receipt_id or 'missing'}:{digest[:16]}", policy_digest=digest)


def _invalid_decision() -> PromptMaterializationPolicyDecision:
    blank = PromptMaterializationPolicyInput()
    return _finalize_decision(
        blank,
        PromptMaterializationPolicyStatus.POLICY_INVALID_INPUT,
        PromptMaterializationPolicyRing.RING_SHADOW_RECEIPT_ONLY,
        (_reason("malformed_policy_input", "policy input is malformed or not metadata-only"),),
        (_mitigation("provide_policy_input", "provide a structured PromptMaterializationPolicyInput built from audit metadata"),),
    )


def evaluate_prompt_materialization_policy(policy_input: PromptMaterializationPolicyInput | Mapping[str, Any]) -> PromptMaterializationPolicyDecision:
    raw_policy_input = policy_input
    parsed = _validate_input(policy_input)
    if parsed is None:
        return _invalid_decision()

    reasons: list[PromptMaterializationPolicyReason] = []
    mitigations: list[PromptMaterializationPolicyMitigation] = []
    runtime_wiring = False

    def add(code: str, detail: str, mitigation_code: str | None = None, mitigation_detail: str | None = None) -> None:
        reasons.append(_reason(code, detail))
        if mitigation_code and mitigation_detail:
            mitigations.append(_mitigation(mitigation_code, mitigation_detail))

    if not parsed.receipt_id or not parsed.audit_status or not parsed.receipt_digest:
        add("missing_audit_receipt", "audit receipt metadata is missing", "provide_audit_receipt", "evaluate a complete Phase 74 audit receipt before policy")
    if parsed.audit_status == PromptMaterializationAuditStatus.AUDIT_RUNTIME_WIRING_DETECTED:
        runtime_wiring = True
        add("audit_runtime_wiring_detected", "audit receipt reports runtime wiring", "remove_runtime_wiring", "remove runtime wiring before any policy allowance")
    elif parsed.audit_status not in _READY_AUDIT_STATUSES:
        add("audit_status_not_ready", f"audit status {parsed.audit_status or '<missing>'} is not ready", "repair_audit_status", "provide ready or ready-with-warnings audit evidence")
    if not parsed.audit_allows_shadow_materializer:
        add("audit_disallows_shadow_materializer", "audit receipt does not allow shadow materializer", "satisfy_audit_shadow_gate", "satisfy Phase 74 shadow-materializer audit gate")
    if not parsed.digest_chain_complete:
        add("digest_chain_incomplete", "audit digest chain is incomplete", "complete_digest_chain", "preserve complete Phase 67-74 digest chain evidence")

    for status_name, status_value in (
        ("blueprint_status", parsed.blueprint_status),
        ("preview_status", parsed.preview_status),
        ("compliance_status", parsed.compliance_status),
        ("adapter_status", parsed.adapter_status),
    ):
        if _has_status_token(status_value):
            if "runtime_wiring" in str(status_value):
                runtime_wiring = True
            add("chain_status_not_ready", f"{status_name} {status_value!r} is blocked/not-applicable/invalid", "repair_shadow_chain", "repair blocked shadow assembly evidence before policy allowance")

    if parsed.requested_ring not in _ALLOWED_RINGS:
        add("unknown_policy_ring", f"requested policy ring {parsed.requested_ring!r} is unknown", "use_known_policy_ring", "request a declared Phase 77 policy ring")
    elif parsed.requested_ring in _FORBIDDEN_PHASE77_RINGS:
        add("phase77_ring_forbidden", f"requested ring {parsed.requested_ring} is live/internal/LLM-capable and forbidden in Phase 77", "downgrade_policy_ring", "request shadow metadata, receipt, review queue, or synthetic fixture ring only")

    feature = _ring_feature_enabled(parsed)
    if feature is None:
        add("feature_flag_missing", "feature flag state is missing for requested ring", "set_feature_flag", "provide an explicit enabled policy feature flag for the requested ring")
    elif feature is False:
        add("feature_flag_disabled", "feature flag state is disabled for requested ring", "enable_feature_flag", "enable the requested policy ring feature flag before allowance")

    if _contains_truthy_key(parsed, _FORBIDDEN_PROMPT_KEYS) or _contains_truthy_key(raw_policy_input, _FORBIDDEN_PROMPT_KEYS) or parsed.no_runtime_markers.get("contains_prompt_text") is True:
        add("forbidden_prompt_marker", "prompt text marker is present in policy input", "remove_prompt_marker", "remove prompt text markers from policy metadata")
    if _contains_truthy_key(parsed, _FORBIDDEN_RAW_KEYS) or _contains_truthy_key(raw_policy_input, _FORBIDDEN_RAW_KEYS) or parsed.no_runtime_markers.get("contains_raw_payload") is True:
        add("forbidden_raw_marker", "raw payload marker is present in policy input", "remove_raw_marker", "remove raw payload markers from policy metadata")
    if _contains_truthy_key(parsed, _RUNTIME_AUTHORITY_KEYS) or _contains_truthy_key(raw_policy_input, _RUNTIME_AUTHORITY_KEYS) or parsed.no_runtime_markers.get("has_runtime_authority") is True:
        runtime_wiring = True
        add("runtime_authority_marker", "runtime authority marker is present in policy input", "remove_runtime_authority", "remove execution, action, retention, retrieval, or LLM authority markers")

    if parsed.violations:
        add("violations_present", "blocking policy violations are present", "clear_violations", "resolve violations before policy allowance")
    blocking_findings = tuple(f for f in parsed.findings if str(f.get("severity", "blocker")) not in {"warning", "review", "info", "non_blocking"})
    if blocking_findings:
        add("blocking_findings_present", "blocking audit/policy findings are present", "clear_findings", "resolve blocking findings before policy allowance")
    if _unknown_source_kind(parsed.source_kind_summary):
        add("unknown_source_kind", "unknown source kind appears in policy input", "classify_source_kind", "use declared source-kind safety contracts only")

    review_items = tuple(item for item in (*parsed.preserved_caveats, *parsed.warnings) if _review_required(item))
    review_needed = bool(review_items)
    review_accepted = _accepted_review(parsed)
    if review_needed and not parsed.operator_review_present:
        if parsed.requested_ring in _OPERATOR_OR_HIGHER_RINGS and not parsed.violations and not blocking_findings and not any(r.code in {"audit_status_not_ready", "audit_disallows_shadow_materializer", "digest_chain_incomplete", "missing_audit_receipt", "feature_flag_missing", "feature_flag_disabled", "unknown_policy_ring", "phase77_ring_forbidden", "forbidden_prompt_marker", "forbidden_raw_marker", "runtime_authority_marker", "unknown_source_kind", "chain_status_not_ready"} for r in reasons):
            return _finalize_decision(
                parsed,
                PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED,
                PromptMaterializationPolicyRing.RING_OPERATOR_REVIEW_QUEUE,
                (_reason("operator_review_required", "warnings or caveats require operator review before higher-ring allowance", "review"),),
                (_mitigation("obtain_operator_review", "obtain accepted operator review for review-required warnings/caveats"),),
            )
        add("operator_review_missing", "warning or caveat requires operator review", "obtain_operator_review", "obtain operator review before allowance")
    elif review_needed and parsed.operator_review_present and not review_accepted:
        add("operator_review_not_accepted", "operator review decision is not accepted", "accept_or_deny_review", "record an accepted operator review decision before higher-ring allowance")

    if parsed.requested_ring == PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY and not parsed.synthetic_fixture_only:
        add("synthetic_fixture_required", "synthetic materialization policy requires synthetic_fixture_only=True", "mark_synthetic_fixture_only", "mark input as synthetic fixture only before synthetic allowance")

    if runtime_wiring:
        return _finalize_decision(parsed, PromptMaterializationPolicyStatus.POLICY_RUNTIME_WIRING_DETECTED, PromptMaterializationPolicyRing.RING_SHADOW_RECEIPT_ONLY, reasons, mitigations)
    if reasons:
        return _finalize_decision(parsed, PromptMaterializationPolicyStatus.POLICY_DENY, PromptMaterializationPolicyRing.RING_SHADOW_RECEIPT_ONLY, reasons, mitigations)

    if parsed.requested_ring in _SHADOW_RINGS:
        return _finalize_decision(
            parsed,
            PromptMaterializationPolicyStatus.POLICY_SHADOW_ONLY,
            parsed.requested_ring,
            (_reason("shadow_only_allowed", "complete audit metadata allows shadow-only policy posture", "info"),),
            (),
        )

    if parsed.requested_ring == PromptMaterializationPolicyRing.RING_OPERATOR_REVIEW_QUEUE:
        return _finalize_decision(
            parsed,
            PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED,
            PromptMaterializationPolicyRing.RING_OPERATOR_REVIEW_QUEUE,
            (_reason("operator_review_queue_requested", "operator review queue requested as non-runtime policy posture", "review"),),
            (_mitigation("complete_operator_review", "complete operator review before any higher-ring policy posture"),),
        )

    if parsed.requested_ring == PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY:
        return _finalize_decision(
            parsed,
            PromptMaterializationPolicyStatus.POLICY_SYNTHETIC_MATERIALIZATION_ALLOWED,
            PromptMaterializationPolicyRing.RING_SYNTHETIC_FIXTURE_ONLY,
            (_reason("synthetic_fixture_policy_allowed", "complete audit metadata allows synthetic-fixture-only policy posture", "info"),),
            (),
        )

    return _finalize_decision(
        parsed,
        PromptMaterializationPolicyStatus.POLICY_DENY,
        PromptMaterializationPolicyRing.RING_SHADOW_RECEIPT_ONLY,
        (_reason("default_deny", "policy fell through to deny-by-default"),),
        (_mitigation("review_policy_input", "review policy input and requested ring"),),
    )


def evaluate_prompt_materialization_policy_from_audit_receipt(
    receipt: PromptMaterializationAuditReceipt | Mapping[str, Any] | None,
    **kwargs: Any,
) -> PromptMaterializationPolicyDecision:
    policy_input = build_prompt_materialization_policy_input(receipt, **kwargs)
    return evaluate_prompt_materialization_policy(policy_input)


def policy_decision_allows_shadow_only(decision: PromptMaterializationPolicyDecision | Mapping[str, Any]) -> bool:
    data = _mapping(decision)
    return data.get("policy_status") == PromptMaterializationPolicyStatus.POLICY_SHADOW_ONLY and bool(data.get("allows_shadow_only"))


def policy_decision_allows_synthetic_materializer(decision: PromptMaterializationPolicyDecision | Mapping[str, Any]) -> bool:
    data = _mapping(decision)
    return data.get("policy_status") == PromptMaterializationPolicyStatus.POLICY_SYNTHETIC_MATERIALIZATION_ALLOWED and bool(data.get("allows_synthetic_materializer"))


def policy_decision_requires_operator_review(decision: PromptMaterializationPolicyDecision | Mapping[str, Any]) -> bool:
    data = _mapping(decision)
    return data.get("policy_status") == PromptMaterializationPolicyStatus.POLICY_OPERATOR_REVIEW_REQUIRED and bool(data.get("requires_operator_review"))


def policy_decision_denies_materialization(decision: PromptMaterializationPolicyDecision | Mapping[str, Any]) -> bool:
    data = _mapping(decision)
    return data.get("policy_status") in {
        PromptMaterializationPolicyStatus.POLICY_DENY,
        PromptMaterializationPolicyStatus.POLICY_INVALID_INPUT,
        PromptMaterializationPolicyStatus.POLICY_RUNTIME_WIRING_DETECTED,
    } or bool(data.get("denied"))


def explain_prompt_materialization_policy_reasons(decision: PromptMaterializationPolicyDecision | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(decision)
    return tuple(
        f"{item.get('severity', '')}:{item.get('code', '')}:{item.get('detail', '')}"
        for item in (_mapping(reason) for reason in data.get("reasons", ()) or ())
    )


def summarize_prompt_materialization_policy_decision(decision: PromptMaterializationPolicyDecision | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(decision)
    return {
        "decision_id": str(data.get("decision_id", "")),
        "policy_status": str(data.get("policy_status", "")),
        "requested_ring": str(data.get("requested_ring", "")),
        "effective_ring": str(data.get("effective_ring", "")),
        "allowed": bool(data.get("allowed", False)),
        "denied": bool(data.get("denied", False)),
        "requires_operator_review": bool(data.get("requires_operator_review", False)),
        "allows_shadow_only": bool(data.get("allows_shadow_only", False)),
        "allows_synthetic_materializer": bool(data.get("allows_synthetic_materializer", False)),
        "receipt_id": str(data.get("receipt_id", "")),
        "receipt_digest": str(data.get("receipt_digest", "")),
        "packet_id": str(data.get("packet_id", "")),
        "caveat_count": int(data.get("caveat_count", 0)),
        "warning_count": int(data.get("warning_count", 0)),
        "violation_count": int(data.get("violation_count", 0)),
        "finding_count": int(data.get("finding_count", 0)),
        "policy_digest": str(data.get("policy_digest", "")),
    }
