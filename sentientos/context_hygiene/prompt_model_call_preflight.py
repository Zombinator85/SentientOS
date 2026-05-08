from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_internal_candidate import (
    InternalPromptCandidate,
    InternalPromptCandidateStatus,
    compute_internal_prompt_candidate_digest,
    internal_prompt_candidate_contains_no_raw_payloads,
    internal_prompt_candidate_has_no_runtime_authority,
    internal_prompt_candidate_has_no_tool_or_action_capability,
    internal_prompt_candidate_is_no_llm,
    internal_prompt_candidate_is_operator_visible_only,
)
from sentientos.context_hygiene.prompt_internal_display import (
    InternalPromptDisplayReceipt,
    InternalPromptDisplayScope,
    InternalPromptDisplayStatus,
    internal_prompt_candidate_may_be_displayed,
    internal_prompt_display_has_no_model_egress,
    internal_prompt_display_has_no_runtime_authority,
    internal_prompt_display_preserves_candidate_digest,
    validate_internal_prompt_display_receipt,
)
from sentientos.context_hygiene.prompt_materialization_audit import (
    PromptMaterializationAuditReceipt,
    audit_receipt_allows_shadow_materializer,
)
from sentientos.context_hygiene.prompt_materialization_policy import (
    PromptMaterializationPolicyDecision,
    policy_decision_allows_internal_candidate_no_llm,
    policy_decision_requires_operator_review,
)
from sentientos.context_hygiene.prompt_operator_review import (
    PromptOperatorReviewReceipt,
    operator_review_satisfies_policy_decision,
    validate_prompt_operator_review_receipt,
)


class InternalModelCallPreflightStatus:
    MODEL_CALL_PREFLIGHT_DENIED = "model_call_preflight_denied"
    MODEL_CALL_PREFLIGHT_READY_FOR_REVIEW = "model_call_preflight_ready_for_review"
    MODEL_CALL_PREFLIGHT_READY_WITH_WARNINGS = "model_call_preflight_ready_with_warnings"
    MODEL_CALL_PREFLIGHT_REVIEW_REQUIRED = "model_call_preflight_review_required"
    MODEL_CALL_PREFLIGHT_INVALID_INPUT = "model_call_preflight_invalid_input"
    MODEL_CALL_PREFLIGHT_DISPLAY_DENIED = "model_call_preflight_display_denied"
    MODEL_CALL_PREFLIGHT_POLICY_DENIED = "model_call_preflight_policy_denied"
    MODEL_CALL_PREFLIGHT_PROVIDER_FORBIDDEN = "model_call_preflight_provider_forbidden"
    MODEL_CALL_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED = "model_call_preflight_runtime_authority_detected"


class InternalModelCallPreflightRing:
    MODEL_REVIEW_PREFLIGHT_ONLY = "model_review_preflight_only"
    INTERNAL_MODEL_CALL_REVIEW_QUEUE = "internal_model_call_review_queue"
    INTERNAL_MODEL_CALL_DRY_RUN_FORBIDDEN_PROVIDER = "internal_model_call_dry_run_forbidden_provider"
    LIVE_MODEL_CALL_FORBIDDEN = "live_model_call_forbidden"


@dataclass(frozen=True)
class InternalModelCallPreflightFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class InternalModelCallPreflightBoundary:
    model_call_preflight_only: bool = True
    provider_call_forbidden: bool = True
    llm_call_forbidden: bool = True
    model_review_gate_precondition_only: bool = True
    live_prompt_assembly_forbidden: bool = True
    live_model_call_forbidden: bool = True
    no_tools: bool = True
    no_memory: bool = True
    no_retention: bool = True
    no_actions: bool = True
    no_background_execution: bool = True
    does_not_call_llm: bool = True
    does_not_send_to_provider: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True


@dataclass(frozen=True)
class InternalModelCallPreflightConstraint:
    internal_only: bool = True
    operator_visible_only: bool = True
    no_tools: bool = True
    no_memory: bool = True
    no_retention: bool = True
    no_actions: bool = True
    no_provider_call: bool = True
    no_background_execution: bool = True


@dataclass(frozen=True)
class InternalModelCallPreflightInput:
    candidate: InternalPromptCandidate | Mapping[str, Any] | None
    display_receipt: InternalPromptDisplayReceipt | Mapping[str, Any] | None
    policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any] | None
    audit_receipt: PromptMaterializationAuditReceipt | Mapping[str, Any] | None
    operator_review_receipt: PromptOperatorReviewReceipt | Mapping[str, Any] | None = None
    requested_model_review_ring: str = InternalModelCallPreflightRing.MODEL_REVIEW_PREFLIGHT_ONLY
    feature_flag_state: Mapping[str, bool] = field(default_factory=dict)
    internal_only: bool = True
    operator_visible_only: bool = True
    no_tools: bool = True
    no_memory: bool = True
    no_retention: bool = True
    no_actions: bool = True
    no_provider_call: bool = True
    no_background_execution: bool = True
    provider_configuration: Mapping[str, Any] = field(default_factory=dict)
    model_configuration: Mapping[str, Any] = field(default_factory=dict)
    llm_configuration: Mapping[str, Any] = field(default_factory=dict)
    runtime_authority_markers: tuple[str, ...] = field(default_factory=tuple)
    raw_markers: tuple[str, ...] = field(default_factory=tuple)
    boundary: InternalModelCallPreflightBoundary = field(default_factory=InternalModelCallPreflightBoundary)


@dataclass(frozen=True)
class InternalModelCallPreflight:
    preflight_id: str
    preflight_status: str
    requested_model_review_ring: str
    effective_model_review_ring: str
    candidate_id: str
    candidate_digest: str
    display_receipt_id: str
    display_receipt_digest: str
    policy_decision_id: str
    policy_status: str
    policy_digest: str
    audit_receipt_id: str
    audit_receipt_digest: str
    review_receipt_id: str
    review_digest: str
    packet_id: str
    packet_scope: str
    provider_call_allowed: bool
    llm_call_allowed: bool
    tool_calls_allowed: bool
    memory_retrieval_allowed: bool
    memory_write_allowed: bool
    retention_allowed: bool
    action_execution_allowed: bool
    routing_allowed: bool
    findings: tuple[InternalModelCallPreflightFinding, ...]
    warnings: tuple[str, ...]
    required_mitigations: tuple[str, ...]
    rationale: str
    preflight_digest: str
    model_call_preflight_only: bool = True
    provider_call_forbidden: bool = True
    llm_call_forbidden: bool = True
    no_tools: bool = True
    no_memory: bool = True
    no_retention: bool = True
    no_actions: bool = True
    no_background_execution: bool = True
    does_not_call_llm: bool = True
    does_not_send_to_provider: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True
    boundary: InternalModelCallPreflightBoundary = field(default_factory=InternalModelCallPreflightBoundary)


_READY_CANDIDATE_STATUSES = frozenset(
    {
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_READY,
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_READY_WITH_WARNINGS,
    }
)
_ALLOWED_DISPLAY_STATUSES = frozenset(
    {
        InternalPromptDisplayStatus.DISPLAY_ALLOWED,
        InternalPromptDisplayStatus.DISPLAY_ALLOWED_WITH_WARNINGS,
    }
)
_ALLOWED_DISPLAY_SCOPES = frozenset(
    {
        InternalPromptDisplayScope.OPERATOR_INTERNAL_REVIEW,
        InternalPromptDisplayScope.OPERATOR_INTERNAL_DEBUG,
        InternalPromptDisplayScope.AUDIT_REPLAY,
    }
)
_ALLOWED_RINGS = frozenset(
    {
        InternalModelCallPreflightRing.MODEL_REVIEW_PREFLIGHT_ONLY,
        InternalModelCallPreflightRing.INTERNAL_MODEL_CALL_REVIEW_QUEUE,
        InternalModelCallPreflightRing.INTERNAL_MODEL_CALL_DRY_RUN_FORBIDDEN_PROVIDER,
        InternalModelCallPreflightRing.LIVE_MODEL_CALL_FORBIDDEN,
    }
)
_REQUIRED_TEXT_MARKERS = (
    ("missing_internal_no_llm_marker", ("internal no-llm candidate",)),
    ("missing_not_sent_to_model_marker", ("not been sent to a model", "not sent to model")),
    ("missing_operator_visible_only_marker", ("operator visible only",)),
)
_BLOCKED_STATUS_TOKENS = ("blocked", "not_applicable", "invalid", "runtime_wiring")
_RUNTIME_MARKERS = (
    "execution_handle",
    "action_handle",
    "retention_handle",
    "retrieval_handle",
    "runtime_authority",
    "tool_handle",
    "route_work",
    "admit_work",
)
_RAW_MARKERS = (
    "raw_payload",
    "raw_memory_payload",
    "raw_screen_payload",
    "raw_audio_payload",
    "raw_vision_payload",
    "raw_multimodal_payload",
    "hidden_chain_of_thought",
    "chain_of_thought",
)
_AUTHORITY_TEXT_MARKERS = ("system:", "developer:", "assistant:", "tool:", "# system", "# developer")
_FORBIDDEN_PARAMETER_KEYS = tuple(f"{prefix}_params" for prefix in ("provider", "model", "llm")) + ("llm_parameters",)
_ALLOWED_INTERNAL_LABELS = ("internal no-llm candidate", "operator visible only", "not sent to model", "not been sent to a model")


def _is_dataclass_instance(value: Any) -> bool:
    return is_dataclass(value) and not isinstance(value, type)


def _mapping(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
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
        return [_stable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_stable(item) for item in value)
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


def _finding(code: str, detail: str, severity: str = "blocker") -> InternalModelCallPreflightFinding:
    return InternalModelCallPreflightFinding(code=code, detail=detail, severity=severity)


def _truthy_forbidden(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and value.strip().lower() not in {"false", "none", "null", "0"}
    if isinstance(value, (tuple, list, set, frozenset, Mapping)):
        return bool(value)
    return bool(value)


def _has_forbidden_keys(value: Any, keys: Sequence[str]) -> bool:
    key_set = {key.lower() for key in keys}
    return any(key.lower() in key_set and _truthy_forbidden(nested) for key, nested in _walk(value))


def _contains_any(text: str, markers: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def _has_blocked_status(value: Any) -> bool:
    for key, nested in _walk(value):
        if "status" in key.lower() and any(token in str(nested).lower() for token in _BLOCKED_STATUS_TOKENS):
            return True
    return False


def _review_satisfies_or_not_required(policy_decision: Any, review_receipt: Any | None) -> bool:
    if policy_decision_requires_operator_review(policy_decision):
        return operator_review_satisfies_policy_decision(policy_decision, review_receipt)
    return True


def _warnings_from_sources(candidate: Any, display_receipt: Any, policy_decision: Any) -> tuple[str, ...]:
    warnings: list[str] = []
    for source in (candidate, display_receipt):
        for item in _mapping(source).get("warnings", ()) or ():
            warnings.append(str(item))
    policy_data = _mapping(policy_decision)
    if int(policy_data.get("warning_count", 0) or 0) > 0:
        warnings.append(f"policy_warning_count:{policy_data.get('warning_count')}")
    if int(policy_data.get("caveat_count", 0) or 0) > 0:
        warnings.append(f"policy_caveat_count:{policy_data.get('caveat_count')}")
    return tuple(warnings)


def build_internal_model_call_preflight_input(
    candidate: InternalPromptCandidate | Mapping[str, Any] | None,
    display_receipt: InternalPromptDisplayReceipt | Mapping[str, Any] | None,
    policy_decision: PromptMaterializationPolicyDecision | Mapping[str, Any] | None,
    audit_receipt: PromptMaterializationAuditReceipt | Mapping[str, Any] | None,
    operator_review_receipt: PromptOperatorReviewReceipt | Mapping[str, Any] | None = None,
    *,
    requested_model_review_ring: str = InternalModelCallPreflightRing.MODEL_REVIEW_PREFLIGHT_ONLY,
    feature_flag_state: Mapping[str, bool] | None = None,
    internal_only: bool = True,
    operator_visible_only: bool = True,
    no_tools: bool = True,
    no_memory: bool = True,
    no_retention: bool = True,
    no_actions: bool = True,
    no_provider_call: bool = True,
    no_background_execution: bool = True,
    provider_configuration: Mapping[str, Any] | None = None,
    model_configuration: Mapping[str, Any] | None = None,
    llm_configuration: Mapping[str, Any] | None = None,
    runtime_authority_markers: Sequence[str] = (),
    raw_payload_markers: Sequence[str] = (),
) -> InternalModelCallPreflightInput:
    return InternalModelCallPreflightInput(
        candidate=candidate,
        display_receipt=display_receipt,
        policy_decision=policy_decision,
        audit_receipt=audit_receipt,
        operator_review_receipt=operator_review_receipt,
        requested_model_review_ring=str(requested_model_review_ring),
        feature_flag_state={str(k): bool(v) for k, v in (feature_flag_state or {}).items()},
        internal_only=bool(internal_only),
        operator_visible_only=bool(operator_visible_only),
        no_tools=bool(no_tools),
        no_memory=bool(no_memory),
        no_retention=bool(no_retention),
        no_actions=bool(no_actions),
        no_provider_call=bool(no_provider_call),
        no_background_execution=bool(no_background_execution),
        provider_configuration=dict(provider_configuration or {}),
        model_configuration=dict(model_configuration or {}),
        llm_configuration=dict(llm_configuration or {}),
        runtime_authority_markers=_tuple_str(runtime_authority_markers),
        raw_markers=_tuple_str(raw_payload_markers),
    )


def _coerce_input(preflight_input: InternalModelCallPreflightInput | Mapping[str, Any]) -> InternalModelCallPreflightInput:
    if isinstance(preflight_input, InternalModelCallPreflightInput):
        return preflight_input
    data = _mapping(preflight_input)
    return build_internal_model_call_preflight_input(
        data.get("candidate"),
        data.get("display_receipt"),
        data.get("policy_decision"),
        data.get("audit_receipt"),
        data.get("operator_review_receipt"),
        requested_model_review_ring=str(data.get("requested_model_review_ring", InternalModelCallPreflightRing.MODEL_REVIEW_PREFLIGHT_ONLY)),
        feature_flag_state=_mapping(data.get("feature_flag_state", {})),
        internal_only=bool(data.get("internal_only", True)),
        operator_visible_only=bool(data.get("operator_visible_only", True)),
        no_tools=bool(data.get("no_tools", True)),
        no_memory=bool(data.get("no_memory", True)),
        no_retention=bool(data.get("no_retention", True)),
        no_actions=bool(data.get("no_actions", True)),
        no_provider_call=bool(data.get("no_provider_call", True)),
        no_background_execution=bool(data.get("no_background_execution", True)),
        provider_configuration=_mapping(data.get("provider_configuration", data.get("provider_params", {}))),
        model_configuration=_mapping(data.get("model_configuration", data.get("model_params", {}))),
        llm_configuration=_mapping(data.get("llm_configuration", data.get("llm_params", data.get("llm_parameters", {})))),
        runtime_authority_markers=_tuple_str(data.get("runtime_authority_markers", ())),
        raw_payload_markers=_tuple_str(data.get("raw_payload_markers", data.get("raw_markers", ()))),
    )


def _candidate_digest(candidate: Any) -> str:
    data = _mapping(candidate)
    if not data:
        return ""
    recorded = str(data.get("candidate_digest", ""))
    try:
        computed = compute_internal_prompt_candidate_digest(candidate)
    except Exception:
        computed = ""
    return computed or recorded


def _evaluate_findings(input_data: InternalModelCallPreflightInput) -> tuple[InternalModelCallPreflightFinding, ...]:
    findings: list[InternalModelCallPreflightFinding] = []
    candidate = input_data.candidate
    display_receipt = input_data.display_receipt
    policy_decision = input_data.policy_decision
    audit_receipt = input_data.audit_receipt
    review_receipt = input_data.operator_review_receipt
    candidate_data = _mapping(candidate)
    display_data = _mapping(display_receipt)
    policy_data = _mapping(policy_decision)
    audit_data = _mapping(audit_receipt)
    ring = input_data.requested_model_review_ring

    if ring not in _ALLOWED_RINGS:
        findings.append(_finding("requested_ring_unknown", "requested model review ring is not recognized"))
    if ring == InternalModelCallPreflightRing.LIVE_MODEL_CALL_FORBIDDEN:
        findings.append(_finding("live_model_call_forbidden", "live model-call rings are explicitly denied in Phase 82"))
    if ring == InternalModelCallPreflightRing.INTERNAL_MODEL_CALL_DRY_RUN_FORBIDDEN_PROVIDER:
        findings.append(_finding("provider_dry_run_forbidden", "provider dry-run ring remains provider-forbidden in Phase 82"))

    if not input_data.feature_flag_state.get("model_call_preflight", False):
        findings.append(_finding("feature_flag_disabled", "model_call_preflight feature flag must be explicitly enabled"))
    if not input_data.internal_only or not input_data.operator_visible_only:
        findings.append(_finding("internal_operator_boundary_missing", "preflight input must be internal-only and operator-visible-only"))
    if not input_data.no_provider_call:
        findings.append(_finding("provider_call_constraint_false", "no_provider_call must remain true"))
    for field_name in ("no_tools", "no_memory", "no_retention", "no_actions", "no_background_execution"):
        if getattr(input_data, field_name) is not True:
            findings.append(_finding("runtime_constraint_false", f"{field_name} must remain true"))
    if input_data.provider_configuration or input_data.model_configuration or input_data.llm_configuration:
        findings.append(_finding("provider_or_model_configuration_present", "provider/model/LLM configuration is forbidden in model-call preflight"))
    if _has_forbidden_keys(input_data, _FORBIDDEN_PARAMETER_KEYS):
        findings.append(_finding("provider_or_model_parameter_marker", "provider/model/LLM parameter markers are forbidden"))
    if input_data.runtime_authority_markers:
        findings.append(_finding("runtime_authority_marker", "runtime authority markers are forbidden"))
    if input_data.raw_markers:
        findings.append(_finding("raw_payload_marker", "raw payload markers are forbidden"))

    if not candidate_data:
        findings.append(_finding("candidate_missing", "Phase 80 InternalPromptCandidate is required"))
    else:
        status = str(candidate_data.get("status", ""))
        if not status or status not in _READY_CANDIDATE_STATUSES:
            findings.append(_finding("candidate_invalid_or_not_ready", f"candidate status {status!r} is not ready for model-call preflight"))
        if _has_blocked_status(candidate):
            findings.append(_finding("upstream_blocked_status", "candidate contains blocked/not-applicable/invalid upstream status"))
        if str(candidate_data.get("candidate_digest", "")) != _candidate_digest(candidate):
            findings.append(_finding("candidate_digest_unstable", "candidate digest is missing or unstable"))
        if not internal_prompt_candidate_is_operator_visible_only(candidate):
            findings.append(_finding("candidate_not_operator_visible_only", "candidate is not internal/operator-visible-only"))
        if not internal_prompt_candidate_is_no_llm(candidate):
            findings.append(_finding("candidate_not_no_llm", "candidate is not marked no-LLM"))
        if not internal_prompt_candidate_contains_no_raw_payloads(candidate):
            findings.append(_finding("candidate_raw_payload_detected", "candidate contains raw payload markers"))
        if not internal_prompt_candidate_has_no_runtime_authority(candidate):
            findings.append(_finding("candidate_runtime_authority_detected", "candidate contains runtime authority markers"))
        if not internal_prompt_candidate_has_no_tool_or_action_capability(candidate):
            findings.append(_finding("candidate_tool_or_action_capability", "candidate contains tool/action/memory/retention/routing capability"))
        text = str(candidate_data.get("internal_candidate_text", ""))
        lowered_text = text.lower()
        for code, marker_options in _REQUIRED_TEXT_MARKERS:
            if not any(marker in lowered_text for marker in marker_options):
                findings.append(_finding(code, "candidate text lacks required internal no-LLM/operator-visible/not-sent marker"))
        if _contains_any(text, _RUNTIME_MARKERS):
            findings.append(_finding("candidate_text_runtime_authority_marker", "candidate text contains runtime authority marker"))
        if _contains_any(text, _RAW_MARKERS):
            findings.append(_finding("candidate_text_raw_payload_marker", "candidate text contains raw payload marker"))
        for line in lowered_text.splitlines():
            if _contains_any(line, _AUTHORITY_TEXT_MARKERS) and not any(label in line for label in _ALLOWED_INTERNAL_LABELS):
                findings.append(_finding("candidate_text_authority_marker", "authority markers are forbidden outside allowed internal candidate labels"))
                break

    if not display_data:
        findings.append(_finding("display_receipt_missing", "Phase 81 InternalPromptDisplayReceipt is required"))
    else:
        if display_data.get("display_status") not in _ALLOWED_DISPLAY_STATUSES:
            findings.append(_finding("display_not_allowed", "display receipt does not allow internal display"))
        if str(display_data.get("display_scope", "")) not in _ALLOWED_DISPLAY_SCOPES:
            findings.append(_finding("display_scope_forbidden", "display scope is not internal operator/audit scope"))
        if validate_internal_prompt_display_receipt(display_receipt, candidate if candidate_data else None):
            findings.append(_finding("display_receipt_invalid", "display receipt validation failed"))
        if not internal_prompt_candidate_may_be_displayed(display_receipt, candidate if candidate_data else None):
            findings.append(_finding("display_denies_candidate", "display receipt does not preserve an allowed display decision"))
        if not internal_prompt_display_preserves_candidate_digest(display_receipt, candidate if candidate_data else None):
            findings.append(_finding("candidate_display_digest_mismatch", "candidate digest mismatches display receipt"))
        if not internal_prompt_display_has_no_model_egress(display_receipt):
            findings.append(_finding("display_model_egress_detected", "display receipt permits model/provider egress"))
        if not internal_prompt_display_has_no_runtime_authority(display_receipt):
            findings.append(_finding("display_runtime_authority_detected", "display receipt permits runtime authority"))

    if not policy_data:
        findings.append(_finding("policy_missing", "Phase 77 policy decision is required"))
    else:
        if not policy_decision_allows_internal_candidate_no_llm(policy_decision):
            findings.append(_finding("policy_not_internal_no_llm_allowed", "policy decision does not allow internal no-LLM candidate preflight"))
        if str(policy_data.get("policy_digest", "")) != str(candidate_data.get("policy_digest", policy_data.get("policy_digest", ""))):
            findings.append(_finding("policy_candidate_digest_mismatch", "policy digest does not match candidate linkage"))

    if not audit_data:
        findings.append(_finding("audit_receipt_missing", "Phase 74 audit receipt is required"))
    else:
        if not audit_receipt_allows_shadow_materializer(audit_receipt):
            findings.append(_finding("audit_shadow_materializer_not_allowed", "audit receipt does not allow shadow materializer precondition"))
        if str(audit_data.get("receipt_digest", "")) != str(candidate_data.get("audit_receipt_digest", audit_data.get("receipt_digest", ""))):
            findings.append(_finding("audit_candidate_digest_mismatch", "audit receipt digest does not match candidate linkage"))

    review_required = ring == InternalModelCallPreflightRing.INTERNAL_MODEL_CALL_REVIEW_QUEUE or policy_decision_requires_operator_review(policy_decision or {})
    has_warning_candidate = str(candidate_data.get("status", "")) == InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_READY_WITH_WARNINGS
    if review_required or has_warning_candidate:
        if review_receipt is None:
            findings.append(_finding("operator_review_required", "operator review evidence is required before this preflight can advance"))
        elif validate_prompt_operator_review_receipt(review_receipt):
            findings.append(_finding("operator_review_invalid", "operator review receipt is expired, mismatched, or invalid"))
        elif not _review_satisfies_or_not_required(policy_decision or {}, review_receipt) and policy_decision_requires_operator_review(policy_decision or {}):
            findings.append(_finding("operator_review_policy_mismatch", "operator review does not satisfy policy decision"))

    if _has_forbidden_keys((candidate, display_receipt, policy_decision, audit_receipt, review_receipt), _FORBIDDEN_PARAMETER_KEYS):
        findings.append(_finding("linked_artifact_provider_or_model_parameter_marker", "linked evidence contains provider/model/LLM parameter markers"))
    if _has_forbidden_keys((candidate, display_receipt, policy_decision, audit_receipt, review_receipt), _RUNTIME_MARKERS):
        findings.append(_finding("linked_artifact_runtime_authority_marker", "linked evidence contains runtime authority markers"))
    return tuple(findings)


def _status_for_findings(input_data: InternalModelCallPreflightInput, findings: Sequence[InternalModelCallPreflightFinding], warnings: Sequence[str]) -> str:
    codes = {finding.code for finding in findings}
    if "candidate_missing" in codes or "candidate_invalid_or_not_ready" in codes or "candidate_digest_unstable" in codes or "requested_ring_unknown" in codes:
        return InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_INVALID_INPUT
    if any(code.startswith("display") or code == "candidate_display_digest_mismatch" for code in codes):
        return InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_DISPLAY_DENIED
    if any(code.startswith("policy") for code in codes):
        return InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_POLICY_DENIED
    if any("provider" in code or "model_call" in code for code in codes):
        return InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_PROVIDER_FORBIDDEN
    if any("runtime" in code or "tool" in code or "action" in code or "raw_payload" in code for code in codes):
        return InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED
    if codes == {"operator_review_required"} or ("operator_review_required" in codes and len(codes) == 1):
        return InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_REVIEW_REQUIRED
    if findings:
        return InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_DENIED
    if input_data.requested_model_review_ring == InternalModelCallPreflightRing.INTERNAL_MODEL_CALL_REVIEW_QUEUE:
        return InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_FOR_REVIEW
    if warnings:
        return InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_WITH_WARNINGS
    return InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_FOR_REVIEW


def _effective_ring(requested_ring: str, status: str) -> str:
    if status in {
        InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_FOR_REVIEW,
        InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_WITH_WARNINGS,
        InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_REVIEW_REQUIRED,
    }:
        return requested_ring
    return InternalModelCallPreflightRing.MODEL_REVIEW_PREFLIGHT_ONLY


def _mitigations(findings: Sequence[InternalModelCallPreflightFinding]) -> tuple[str, ...]:
    if not findings:
        return ()
    return tuple(f"mitigate:{finding.code}" for finding in findings)


def compute_internal_model_call_preflight_digest(preflight: InternalModelCallPreflight | Mapping[str, Any]) -> str:
    data = dict(_mapping(preflight))
    data.pop("preflight_digest", None)
    data.pop("preflight_id", None)
    payload = {
        "preflight_status": data.get("preflight_status", ""),
        "requested_model_review_ring": data.get("requested_model_review_ring", ""),
        "effective_model_review_ring": data.get("effective_model_review_ring", ""),
        "candidate_id": data.get("candidate_id", ""),
        "candidate_digest": data.get("candidate_digest", ""),
        "display_receipt_id": data.get("display_receipt_id", ""),
        "display_receipt_digest": data.get("display_receipt_digest", ""),
        "policy_decision_id": data.get("policy_decision_id", ""),
        "policy_status": data.get("policy_status", ""),
        "policy_digest": data.get("policy_digest", ""),
        "audit_receipt_id": data.get("audit_receipt_id", ""),
        "audit_receipt_digest": data.get("audit_receipt_digest", ""),
        "review_receipt_id": data.get("review_receipt_id", ""),
        "review_digest": data.get("review_digest", ""),
        "packet_id": data.get("packet_id", ""),
        "packet_scope": data.get("packet_scope", ""),
        "allowances": {
            "provider_call_allowed": bool(data.get("provider_call_allowed", False)),
            "llm_call_allowed": bool(data.get("llm_call_allowed", False)),
            "tool_calls_allowed": bool(data.get("tool_calls_allowed", False)),
            "memory_retrieval_allowed": bool(data.get("memory_retrieval_allowed", False)),
            "memory_write_allowed": bool(data.get("memory_write_allowed", False)),
            "retention_allowed": bool(data.get("retention_allowed", False)),
            "action_execution_allowed": bool(data.get("action_execution_allowed", False)),
            "routing_allowed": bool(data.get("routing_allowed", False)),
        },
        "findings": _stable(data.get("findings", ())),
        "warnings": _stable(data.get("warnings", ())),
        "required_mitigations": _stable(data.get("required_mitigations", ())),
        "markers": {
            key: bool(data.get(key, False))
            for key in (
                "model_call_preflight_only",
                "provider_call_forbidden",
                "llm_call_forbidden",
                "no_tools",
                "no_memory",
                "no_retention",
                "no_actions",
                "no_background_execution",
                "does_not_call_llm",
                "does_not_send_to_provider",
                "does_not_retrieve_memory",
                "does_not_write_memory",
                "does_not_trigger_feedback",
                "does_not_commit_retention",
                "does_not_execute_or_route_work",
                "does_not_admit_work",
            )
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evaluate_internal_model_call_preflight(preflight_input: InternalModelCallPreflightInput | Mapping[str, Any]) -> InternalModelCallPreflight:
    input_data = _coerce_input(preflight_input)
    candidate_data = _mapping(input_data.candidate)
    display_data = _mapping(input_data.display_receipt)
    policy_data = _mapping(input_data.policy_decision)
    audit_data = _mapping(input_data.audit_receipt)
    review_data = _mapping(input_data.operator_review_receipt)
    findings = _evaluate_findings(input_data)
    warnings = _warnings_from_sources(input_data.candidate, input_data.display_receipt, input_data.policy_decision)
    status = _status_for_findings(input_data, findings, warnings)
    if status == InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_WITH_WARNINGS and input_data.operator_review_receipt is None:
        status = InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_REVIEW_REQUIRED
    effective_ring = _effective_ring(input_data.requested_model_review_ring, status)
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "model-call preflight evidence is eligible for future internal review gate only"
    preflight = InternalModelCallPreflight(
        preflight_id="",
        preflight_status=status,
        requested_model_review_ring=input_data.requested_model_review_ring,
        effective_model_review_ring=effective_ring,
        candidate_id=str(candidate_data.get("candidate_id", "")),
        candidate_digest=str(candidate_data.get("candidate_digest", "")),
        display_receipt_id=str(display_data.get("display_receipt_id", "")),
        display_receipt_digest=str(display_data.get("display_receipt_digest", "")),
        policy_decision_id=str(policy_data.get("decision_id", "")),
        policy_status=str(policy_data.get("policy_status", "")),
        policy_digest=str(policy_data.get("policy_digest", "")),
        audit_receipt_id=str(audit_data.get("receipt_id", "")),
        audit_receipt_digest=str(audit_data.get("receipt_digest", "")),
        review_receipt_id=str(review_data.get("review_receipt_id", "")),
        review_digest=str(review_data.get("review_digest", "")),
        packet_id=str(candidate_data.get("packet_id", display_data.get("packet_id", policy_data.get("packet_id", audit_data.get("packet_id", ""))))),
        packet_scope=str(candidate_data.get("packet_scope", display_data.get("packet_scope", policy_data.get("packet_scope", audit_data.get("packet_scope", ""))))),
        provider_call_allowed=False,
        llm_call_allowed=False,
        tool_calls_allowed=False,
        memory_retrieval_allowed=False,
        memory_write_allowed=False,
        retention_allowed=False,
        action_execution_allowed=False,
        routing_allowed=False,
        findings=tuple(findings),
        warnings=tuple(warnings),
        required_mitigations=_mitigations(findings),
        rationale=rationale,
        preflight_digest="",
    )
    digest = compute_internal_model_call_preflight_digest(preflight)
    return replace(preflight, preflight_id=f"internal-model-call-preflight:{preflight.candidate_id or 'missing'}:{digest[:16]}", preflight_digest=digest)


def internal_model_call_preflight_allows_review_gate(preflight: InternalModelCallPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return str(data.get("preflight_status", "")) in {
        InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_FOR_REVIEW,
        InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_WITH_WARNINGS,
    } and internal_model_call_preflight_forbids_provider_call(preflight) and internal_model_call_preflight_has_no_runtime_authority(preflight)


def internal_model_call_preflight_forbids_provider_call(preflight: InternalModelCallPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(
        data.get("provider_call_allowed") is False
        and data.get("llm_call_allowed") is False
        and data.get("provider_call_forbidden") is True
        and data.get("llm_call_forbidden") is True
        and data.get("does_not_call_llm") is True
        and data.get("does_not_send_to_provider") is True
    )


def internal_model_call_preflight_has_no_runtime_authority(preflight: InternalModelCallPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(
        data.get("tool_calls_allowed") is False
        and data.get("memory_retrieval_allowed") is False
        and data.get("memory_write_allowed") is False
        and data.get("retention_allowed") is False
        and data.get("action_execution_allowed") is False
        and data.get("routing_allowed") is False
        and data.get("no_tools") is True
        and data.get("no_memory") is True
        and data.get("no_retention") is True
        and data.get("no_actions") is True
        and data.get("no_background_execution") is True
        and data.get("does_not_retrieve_memory") is True
        and data.get("does_not_write_memory") is True
        and data.get("does_not_commit_retention") is True
        and data.get("does_not_execute_or_route_work") is True
        and data.get("does_not_admit_work") is True
    )


def internal_model_call_preflight_preserves_display_receipt(
    preflight: InternalModelCallPreflight | Mapping[str, Any],
    display_receipt: InternalPromptDisplayReceipt | Mapping[str, Any],
) -> bool:
    data = _mapping(preflight)
    display_data = _mapping(display_receipt)
    return bool(
        data.get("display_receipt_id") == display_data.get("display_receipt_id")
        and data.get("display_receipt_digest") == display_data.get("display_receipt_digest")
        and data.get("candidate_digest") == display_data.get("candidate_digest")
    )


def explain_internal_model_call_preflight_findings(preflight_or_findings: InternalModelCallPreflight | Mapping[str, Any] | Sequence[InternalModelCallPreflightFinding]) -> tuple[str, ...]:
    if isinstance(preflight_or_findings, Sequence) and not isinstance(preflight_or_findings, (str, bytes, Mapping)):
        findings = preflight_or_findings
    else:
        findings = _mapping(preflight_or_findings).get("findings", ()) or ()
    return tuple(f"{_mapping(item).get('severity', '')}:{_mapping(item).get('code', '')}:{_mapping(item).get('detail', '')}" for item in findings)


def summarize_internal_model_call_preflight(preflight: InternalModelCallPreflight | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(preflight)
    return {
        "preflight_id": str(data.get("preflight_id", "")),
        "preflight_status": str(data.get("preflight_status", InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_DENIED)),
        "requested_model_review_ring": str(data.get("requested_model_review_ring", "")),
        "effective_model_review_ring": str(data.get("effective_model_review_ring", "")),
        "candidate_id": str(data.get("candidate_id", "")),
        "candidate_digest": str(data.get("candidate_digest", "")),
        "display_receipt_id": str(data.get("display_receipt_id", "")),
        "display_receipt_digest": str(data.get("display_receipt_digest", "")),
        "policy_decision_id": str(data.get("policy_decision_id", "")),
        "policy_status": str(data.get("policy_status", "")),
        "policy_digest": str(data.get("policy_digest", "")),
        "audit_receipt_id": str(data.get("audit_receipt_id", "")),
        "audit_receipt_digest": str(data.get("audit_receipt_digest", "")),
        "review_receipt_id": str(data.get("review_receipt_id", "")),
        "review_digest": str(data.get("review_digest", "")),
        "packet_id": str(data.get("packet_id", "")),
        "packet_scope": str(data.get("packet_scope", "")),
        "provider_call_allowed": bool(data.get("provider_call_allowed", False)),
        "llm_call_allowed": bool(data.get("llm_call_allowed", False)),
        "finding_count": len(data.get("findings", ()) or ()),
        "warning_count": len(data.get("warnings", ()) or ()),
        "preflight_digest": str(data.get("preflight_digest", "")),
    }
