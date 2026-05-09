from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_model_call_preflight import (
    InternalModelCallPreflight,
    InternalModelCallPreflightRing,
    InternalModelCallPreflightStatus,
    compute_internal_model_call_preflight_digest,
    internal_model_call_preflight_allows_review_gate,
    internal_model_call_preflight_forbids_provider_call,
    internal_model_call_preflight_has_no_runtime_authority,
)


class InternalModelCallReviewStatus:
    MODEL_CALL_REVIEW_APPROVED = "model_call_review_approved"
    MODEL_CALL_REVIEW_APPROVED_WITH_CONSTRAINTS = "model_call_review_approved_with_constraints"
    MODEL_CALL_REVIEW_REJECTED = "model_call_review_rejected"
    MODEL_CALL_REVIEW_EXPIRED = "model_call_review_expired"
    MODEL_CALL_REVIEW_INVALID = "model_call_review_invalid"
    MODEL_CALL_REVIEW_FORBIDDEN_OVERRIDE_ATTEMPTED = "model_call_review_forbidden_override_attempted"
    MODEL_CALL_REVIEW_NOT_APPLICABLE = "model_call_review_not_applicable"


class InternalModelCallReviewDecision:
    APPROVE_FUTURE_REVIEW_GATE = "approve_future_review_gate"
    APPROVE_WITH_CONSTRAINTS = "approve_with_constraints"
    REJECT_FUTURE_REVIEW_GATE = "reject_future_review_gate"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"
    NO_DECISION = "no_decision"


class InternalModelCallReviewScope:
    INTERNAL_MODEL_CALL_REVIEW_GATE = "internal_model_call_review_gate"
    PROVIDER_DRY_RUN_FUTURE_GATE = "provider_dry_run_future_gate"
    LIVE_PROVIDER_CALL_FORBIDDEN = "live_provider_call_forbidden"
    TOOL_OR_ACTION_FORBIDDEN = "tool_or_action_forbidden"
    EXTERNAL_USER_VISIBLE_FORBIDDEN = "external_user_visible_forbidden"


@dataclass(frozen=True)
class InternalModelCallReviewConstraint:
    code: str
    detail: str
    required: bool = True


@dataclass(frozen=True)
class InternalModelCallReviewFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class InternalModelCallReviewExpiration:
    reviewed_at: str = ""
    expires_at: str = ""
    ttl_seconds: int = 0
    evaluated_at: str = ""


@dataclass(frozen=True)
class InternalModelCallReviewReceipt:
    review_receipt_id: str
    review_status: str
    preflight_id: str
    preflight_status: str
    preflight_digest: str
    requested_model_review_ring: str
    effective_model_review_ring: str
    candidate_id: str
    candidate_digest: str
    display_receipt_id: str
    display_receipt_digest: str
    policy_decision_id: str
    policy_digest: str
    audit_receipt_id: str
    audit_receipt_digest: str
    reviewer_ref: str
    review_scope: str
    decision: str
    approved_constraint_codes: tuple[str, ...]
    rejected_constraint_codes: tuple[str, ...]
    required_mitigation_codes: tuple[str, ...]
    accepted_mitigation_codes: tuple[str, ...]
    rejected_mitigation_codes: tuple[str, ...]
    provider_call_allowed: bool
    llm_call_allowed: bool
    tool_calls_allowed: bool
    memory_retrieval_allowed: bool
    memory_write_allowed: bool
    retention_allowed: bool
    action_execution_allowed: bool
    routing_allowed: bool
    expiration: InternalModelCallReviewExpiration
    expired: bool
    forbidden_override_attempted: bool
    findings: tuple[InternalModelCallReviewFinding, ...]
    rationale: str
    review_digest: str
    model_call_review_receipt_only: bool = True
    future_gate_review_only: bool = True
    provider_call_forbidden: bool = True
    llm_call_forbidden: bool = True
    does_not_call_llm: bool = True
    does_not_send_to_provider: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True


_APPROVE_DECISIONS = frozenset(
    {
        InternalModelCallReviewDecision.APPROVE_FUTURE_REVIEW_GATE,
        InternalModelCallReviewDecision.APPROVE_WITH_CONSTRAINTS,
    }
)
_REJECT_DECISIONS = frozenset(
    {
        InternalModelCallReviewDecision.REJECT_FUTURE_REVIEW_GATE,
        InternalModelCallReviewDecision.REQUEST_MORE_EVIDENCE,
    }
)
_ALLOWED_DECISIONS = _APPROVE_DECISIONS | _REJECT_DECISIONS | {InternalModelCallReviewDecision.NO_DECISION}
_ALLOWED_SCOPES = frozenset(
    {
        InternalModelCallReviewScope.INTERNAL_MODEL_CALL_REVIEW_GATE,
        InternalModelCallReviewScope.PROVIDER_DRY_RUN_FUTURE_GATE,
        InternalModelCallReviewScope.LIVE_PROVIDER_CALL_FORBIDDEN,
        InternalModelCallReviewScope.TOOL_OR_ACTION_FORBIDDEN,
        InternalModelCallReviewScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
    }
)
_READY_PREFLIGHT_STATUSES = frozenset(
    {
        InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_FOR_REVIEW,
        InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_WITH_WARNINGS,
    }
)
_HARD_DENIAL_PREFLIGHT_STATUSES = frozenset(
    {
        InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_DENIED,
        InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_INVALID_INPUT,
        InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_DISPLAY_DENIED,
        InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_POLICY_DENIED,
        InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_PROVIDER_FORBIDDEN,
        InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED,
    }
)
_REQUIRED_DIGEST_FIELDS = (
    "candidate_digest",
    "display_receipt_digest",
    "policy_digest",
    "audit_receipt_digest",
)
_ALLOWANCE_FIELDS = (
    "provider_call_allowed",
    "llm_call_allowed",
    "tool_calls_allowed",
    "memory_retrieval_allowed",
    "memory_write_allowed",
    "retention_allowed",
    "action_execution_allowed",
    "routing_allowed",
)
_NON_RUNTIME_MARKERS = (
    "model_call_review_receipt_only",
    "future_gate_review_only",
    "provider_call_forbidden",
    "llm_call_forbidden",
    "does_not_call_llm",
    "does_not_send_to_provider",
    "does_not_retrieve_memory",
    "does_not_write_memory",
    "does_not_trigger_feedback",
    "does_not_commit_retention",
    "does_not_execute_or_route_work",
    "does_not_admit_work",
)
_PROMPT_RAW_RUNTIME_MARKERS = (
    "prompt_text",
    "final_prompt",
    "raw_payload",
    "raw_memory_payload",
    "raw_screen_payload",
    "raw_audio_payload",
    "raw_vision_payload",
    "raw_multimodal_payload",
    "execution_handle",
    "action_handle",
    "retention_handle",
    "retrieval_handle",
    "runtime_authority",
    "provider_params",
    "model_params",
    "llm_params",
    "llm_parameters",
)
_PROVIDER_FORBIDDEN_CONSTRAINT_CODES = (
    "constraint:provider_call_forbidden",
    "constraint:llm_call_forbidden",
    "constraint:does_not_send_to_provider",
    "constraint:no_tools_memory_retention_actions_routing",
)


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
        return {key: _stable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _stable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list)):
        return [_stable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_stable(item) for item in value)
    return value


def _tuple_str(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(str(item) for item in value if str(item))
    return ()


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return tuple(result)


def _finding(code: str, detail: str, severity: str = "blocker") -> InternalModelCallReviewFinding:
    return InternalModelCallReviewFinding(code=code, detail=detail, severity=severity)


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _expiration(expires_at: str | None, ttl_seconds: int | None, reviewed_at: str | None, evaluated_at: str | None) -> InternalModelCallReviewExpiration:
    reviewed = reviewed_at or "1970-01-01T00:00:00Z"
    ttl = int(ttl_seconds or 0)
    expiry = expires_at or ""
    if not expiry and ttl > 0:
        base = _parse_time(reviewed) or datetime(1970, 1, 1, tzinfo=timezone.utc)
        expiry = _format_time(base + timedelta(seconds=ttl))
    return InternalModelCallReviewExpiration(
        reviewed_at=reviewed,
        expires_at=expiry,
        ttl_seconds=ttl,
        evaluated_at=evaluated_at or reviewed,
    )


def _is_expired(expiration: InternalModelCallReviewExpiration) -> bool:
    expires = _parse_time(expiration.expires_at)
    evaluated = _parse_time(expiration.evaluated_at)
    return bool(expires and evaluated and evaluated >= expires)


def _code_from_text(prefix: str, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"


def extract_required_internal_model_call_review_mitigation_codes(preflight: InternalModelCallPreflight | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(preflight)
    required: list[str] = []
    required.extend(_tuple_str(data.get("required_mitigations", ())))
    for finding in data.get("findings", ()) or ():
        finding_data = _mapping(finding)
        code = str(finding_data.get("code", ""))
        if code:
            required.append(f"mitigate:{code}")
    for warning in _tuple_str(data.get("warnings", ())) or ():
        required.append(_code_from_text("warning", warning))
    if str(data.get("preflight_status", "")) == InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_REVIEW_REQUIRED:
        required.append("mitigate:operator_review_required")
    if bool(data.get("provider_call_forbidden", True)) and bool(data.get("llm_call_forbidden", True)):
        required.extend(_PROVIDER_FORBIDDEN_CONSTRAINT_CODES)
    return _dedupe(required)


def _contains_forbidden_marker(value: Any) -> bool:
    text = json.dumps(_stable(value), sort_keys=True, ensure_ascii=True, default=str).lower()
    return any(marker in text for marker in _PROMPT_RAW_RUNTIME_MARKERS)


def _preflight_digest(preflight: InternalModelCallPreflight | Mapping[str, Any]) -> str:
    data = _mapping(preflight)
    recorded = str(data.get("preflight_digest", ""))
    if not data:
        return ""
    try:
        computed = compute_internal_model_call_preflight_digest(preflight)
    except Exception:
        computed = ""
    return computed or recorded


def _preflight_findings(
    preflight: InternalModelCallPreflight | Mapping[str, Any],
    *,
    decision: str,
    review_scope: str,
    reviewer_ref: str,
    approved_constraint_codes: Sequence[str],
    rejected_constraint_codes: Sequence[str],
    required_mitigation_codes: Sequence[str],
    accepted_mitigation_codes: Sequence[str],
    rejected_mitigation_codes: Sequence[str],
    provider_call_allowed: bool,
    llm_call_allowed: bool,
    tool_calls_allowed: bool,
    memory_retrieval_allowed: bool,
    memory_write_allowed: bool,
    retention_allowed: bool,
    action_execution_allowed: bool,
    routing_allowed: bool,
    expired: bool,
) -> tuple[InternalModelCallReviewFinding, ...]:
    data = _mapping(preflight)
    findings: list[InternalModelCallReviewFinding] = []
    if not data:
        findings.append(_finding("preflight_missing", "Phase 82 InternalModelCallPreflight metadata is required"))
    if not reviewer_ref:
        findings.append(_finding("reviewer_ref_missing", "reviewer_ref is required for model-call review receipt"))
    if decision not in _ALLOWED_DECISIONS:
        findings.append(_finding("decision_unknown", "review decision is not recognized"))
    if review_scope not in _ALLOWED_SCOPES:
        findings.append(_finding("review_scope_unknown", "review scope is not recognized"))
    if expired:
        findings.append(_finding("review_expired", "model-call review receipt is expired"))

    approving = decision in _APPROVE_DECISIONS
    status = str(data.get("preflight_status", ""))
    if approving and status in _HARD_DENIAL_PREFLIGHT_STATUSES:
        findings.append(_finding("preflight_hard_denial_non_overridable", f"preflight status {status!r} cannot be approved in Phase 83"))
    if approving and status not in _READY_PREFLIGHT_STATUSES:
        findings.append(_finding("preflight_not_ready_for_review", "only ready or ready-with-warnings preflights may receive future-gate approval"))
    if approving and not internal_model_call_preflight_allows_review_gate(preflight):
        findings.append(_finding("preflight_review_gate_not_allowed", "preflight helper does not allow the internal review gate"))
    if approving and not internal_model_call_preflight_forbids_provider_call(preflight):
        findings.append(_finding("preflight_provider_forbidden_not_preserved", "preflight must keep provider/LLM calls forbidden"))
    if approving and not internal_model_call_preflight_has_no_runtime_authority(preflight):
        findings.append(_finding("preflight_runtime_authority_detected", "preflight must have no tool/memory/action/retention/routing authority"))
    if approving and str(data.get("effective_model_review_ring", "")) == InternalModelCallPreflightRing.LIVE_MODEL_CALL_FORBIDDEN:
        findings.append(_finding("live_model_call_ring_non_overridable", "live model-call rings cannot be approved in Phase 83"))
    if approving and review_scope == InternalModelCallReviewScope.PROVIDER_DRY_RUN_FUTURE_GATE and decision != InternalModelCallReviewDecision.APPROVE_WITH_CONSTRAINTS:
        findings.append(_finding("provider_dry_run_requires_constraints", "future provider dry-run scope may only be approved with explicit constraints"))
    if approving and review_scope in {
        InternalModelCallReviewScope.LIVE_PROVIDER_CALL_FORBIDDEN,
        InternalModelCallReviewScope.TOOL_OR_ACTION_FORBIDDEN,
        InternalModelCallReviewScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
    }:
        findings.append(_finding("review_scope_non_overridable", f"scope {review_scope!r} cannot be approved in Phase 83"))

    for field_name in _REQUIRED_DIGEST_FIELDS:
        if not str(data.get(field_name, "")):
            findings.append(_finding("linked_digest_missing", f"{field_name} is required for model-call review receipt"))
    if not str(data.get("preflight_digest", "")):
        findings.append(_finding("preflight_digest_missing", "preflight_digest is required"))
    elif _preflight_digest(preflight) != str(data.get("preflight_digest", "")):
        findings.append(_finding("preflight_digest_mismatch", "preflight_digest does not match stable preflight metadata"))

    allowances = {
        "provider_call_allowed": provider_call_allowed,
        "llm_call_allowed": llm_call_allowed,
        "tool_calls_allowed": tool_calls_allowed,
        "memory_retrieval_allowed": memory_retrieval_allowed,
        "memory_write_allowed": memory_write_allowed,
        "retention_allowed": retention_allowed,
        "action_execution_allowed": action_execution_allowed,
        "routing_allowed": routing_allowed,
    }
    for field_name, allowed in allowances.items():
        if allowed:
            findings.append(_finding("forbidden_allowance_requested", f"{field_name} must remain false in Phase 83"))
    if _contains_forbidden_marker((preflight, approved_constraint_codes, rejected_constraint_codes, required_mitigation_codes, accepted_mitigation_codes, rejected_mitigation_codes)):
        findings.append(_finding("prompt_raw_runtime_marker_detected", "review metadata contains forbidden prompt/raw/provider/runtime marker text"))
    return tuple(findings)


def _status(decision: str, findings: Sequence[InternalModelCallReviewFinding], expired: bool) -> str:
    codes = {finding.code for finding in findings}
    if expired:
        return InternalModelCallReviewStatus.MODEL_CALL_REVIEW_EXPIRED
    if any(code in codes for code in {"preflight_missing", "reviewer_ref_missing", "decision_unknown", "review_scope_unknown", "linked_digest_missing", "preflight_digest_missing", "preflight_digest_mismatch"}):
        return InternalModelCallReviewStatus.MODEL_CALL_REVIEW_INVALID
    if "prompt_raw_runtime_marker_detected" in codes and decision not in _APPROVE_DECISIONS:
        return InternalModelCallReviewStatus.MODEL_CALL_REVIEW_INVALID
    if findings and decision in _APPROVE_DECISIONS:
        return InternalModelCallReviewStatus.MODEL_CALL_REVIEW_FORBIDDEN_OVERRIDE_ATTEMPTED
    if decision == InternalModelCallReviewDecision.APPROVE_FUTURE_REVIEW_GATE:
        return InternalModelCallReviewStatus.MODEL_CALL_REVIEW_APPROVED
    if decision == InternalModelCallReviewDecision.APPROVE_WITH_CONSTRAINTS:
        return InternalModelCallReviewStatus.MODEL_CALL_REVIEW_APPROVED_WITH_CONSTRAINTS
    if decision in _REJECT_DECISIONS:
        return InternalModelCallReviewStatus.MODEL_CALL_REVIEW_REJECTED
    return InternalModelCallReviewStatus.MODEL_CALL_REVIEW_NOT_APPLICABLE


def build_internal_model_call_review_receipt(
    preflight: InternalModelCallPreflight | Mapping[str, Any],
    *,
    reviewer_ref: str,
    decision: str,
    review_scope: str = InternalModelCallReviewScope.INTERNAL_MODEL_CALL_REVIEW_GATE,
    approved_constraint_codes: Sequence[str] = (),
    rejected_constraint_codes: Sequence[str] = (),
    required_mitigation_codes: Sequence[str] | None = None,
    accepted_mitigation_codes: Sequence[str] = (),
    rejected_mitigation_codes: Sequence[str] = (),
    rationale: str = "",
    expires_at: str | None = None,
    ttl_seconds: int | None = None,
    reviewed_at: str | None = None,
    evaluated_at: str | None = None,
    provider_call_allowed: bool = False,
    llm_call_allowed: bool = False,
    tool_calls_allowed: bool = False,
    memory_retrieval_allowed: bool = False,
    memory_write_allowed: bool = False,
    retention_allowed: bool = False,
    action_execution_allowed: bool = False,
    routing_allowed: bool = False,
) -> InternalModelCallReviewReceipt:
    preflight_data = _mapping(preflight)
    expiration = _expiration(expires_at, ttl_seconds, reviewed_at, evaluated_at)
    expired = _is_expired(expiration)
    required = _dedupe(_tuple_str(required_mitigation_codes) or extract_required_internal_model_call_review_mitigation_codes(preflight))
    approved = _dedupe(_tuple_str(approved_constraint_codes))
    rejected_constraints = _dedupe(_tuple_str(rejected_constraint_codes))
    accepted = _dedupe(_tuple_str(accepted_mitigation_codes))
    rejected_mitigations = _dedupe(_tuple_str(rejected_mitigation_codes))
    findings = _preflight_findings(
        preflight,
        decision=decision,
        review_scope=review_scope,
        reviewer_ref=reviewer_ref,
        approved_constraint_codes=approved,
        rejected_constraint_codes=rejected_constraints,
        required_mitigation_codes=required,
        accepted_mitigation_codes=accepted,
        rejected_mitigation_codes=rejected_mitigations,
        provider_call_allowed=bool(provider_call_allowed),
        llm_call_allowed=bool(llm_call_allowed),
        tool_calls_allowed=bool(tool_calls_allowed),
        memory_retrieval_allowed=bool(memory_retrieval_allowed),
        memory_write_allowed=bool(memory_write_allowed),
        retention_allowed=bool(retention_allowed),
        action_execution_allowed=bool(action_execution_allowed),
        routing_allowed=bool(routing_allowed),
        expired=expired,
    )
    status = _status(decision, findings, expired)
    receipt = InternalModelCallReviewReceipt(
        review_receipt_id="",
        review_status=status,
        preflight_id=str(preflight_data.get("preflight_id", "")),
        preflight_status=str(preflight_data.get("preflight_status", "")),
        preflight_digest=str(preflight_data.get("preflight_digest", "")),
        requested_model_review_ring=str(preflight_data.get("requested_model_review_ring", "")),
        effective_model_review_ring=str(preflight_data.get("effective_model_review_ring", "")),
        candidate_id=str(preflight_data.get("candidate_id", "")),
        candidate_digest=str(preflight_data.get("candidate_digest", "")),
        display_receipt_id=str(preflight_data.get("display_receipt_id", "")),
        display_receipt_digest=str(preflight_data.get("display_receipt_digest", "")),
        policy_decision_id=str(preflight_data.get("policy_decision_id", "")),
        policy_digest=str(preflight_data.get("policy_digest", "")),
        audit_receipt_id=str(preflight_data.get("audit_receipt_id", "")),
        audit_receipt_digest=str(preflight_data.get("audit_receipt_digest", "")),
        reviewer_ref=str(reviewer_ref),
        review_scope=str(review_scope),
        decision=str(decision),
        approved_constraint_codes=approved,
        rejected_constraint_codes=rejected_constraints,
        required_mitigation_codes=required,
        accepted_mitigation_codes=accepted,
        rejected_mitigation_codes=rejected_mitigations,
        provider_call_allowed=bool(provider_call_allowed),
        llm_call_allowed=bool(llm_call_allowed),
        tool_calls_allowed=bool(tool_calls_allowed),
        memory_retrieval_allowed=bool(memory_retrieval_allowed),
        memory_write_allowed=bool(memory_write_allowed),
        retention_allowed=bool(retention_allowed),
        action_execution_allowed=bool(action_execution_allowed),
        routing_allowed=bool(routing_allowed),
        expiration=expiration,
        expired=expired,
        forbidden_override_attempted=status == InternalModelCallReviewStatus.MODEL_CALL_REVIEW_FORBIDDEN_OVERRIDE_ATTEMPTED,
        findings=tuple(findings),
        rationale=str(rationale)[:1000],
        review_digest="",
    )
    digest = compute_internal_model_call_review_digest(receipt)
    return replace(receipt, review_receipt_id=f"internal-model-call-review:{receipt.preflight_id or 'missing'}:{digest[:16]}", review_digest=digest)


def build_internal_model_call_review_receipt_from_preflight(
    preflight: InternalModelCallPreflight | Mapping[str, Any],
    **kwargs: Any,
) -> InternalModelCallReviewReceipt:
    return build_internal_model_call_review_receipt(preflight, **kwargs)


def compute_internal_model_call_review_digest(receipt: InternalModelCallReviewReceipt | Mapping[str, Any]) -> str:
    data = dict(_mapping(receipt))
    data.pop("review_digest", None)
    data.pop("review_receipt_id", None)
    payload = {
        "review_status": data.get("review_status", ""),
        "preflight_id": data.get("preflight_id", ""),
        "preflight_status": data.get("preflight_status", ""),
        "preflight_digest": data.get("preflight_digest", ""),
        "requested_model_review_ring": data.get("requested_model_review_ring", ""),
        "effective_model_review_ring": data.get("effective_model_review_ring", ""),
        "candidate_id": data.get("candidate_id", ""),
        "candidate_digest": data.get("candidate_digest", ""),
        "display_receipt_id": data.get("display_receipt_id", ""),
        "display_receipt_digest": data.get("display_receipt_digest", ""),
        "policy_decision_id": data.get("policy_decision_id", ""),
        "policy_digest": data.get("policy_digest", ""),
        "audit_receipt_id": data.get("audit_receipt_id", ""),
        "audit_receipt_digest": data.get("audit_receipt_digest", ""),
        "reviewer_ref": data.get("reviewer_ref", ""),
        "review_scope": data.get("review_scope", ""),
        "decision": data.get("decision", ""),
        "approved_constraint_codes": _stable(data.get("approved_constraint_codes", ())),
        "rejected_constraint_codes": _stable(data.get("rejected_constraint_codes", ())),
        "required_mitigation_codes": _stable(data.get("required_mitigation_codes", ())),
        "accepted_mitigation_codes": _stable(data.get("accepted_mitigation_codes", ())),
        "rejected_mitigation_codes": _stable(data.get("rejected_mitigation_codes", ())),
        "allowances": {field_name: bool(data.get(field_name, False)) for field_name in _ALLOWANCE_FIELDS},
        "expiration": _stable(data.get("expiration", {})),
        "expired": bool(data.get("expired", False)),
        "forbidden_override_attempted": bool(data.get("forbidden_override_attempted", False)),
        "findings": _stable(data.get("findings", ())),
        "rationale": data.get("rationale", ""),
        "markers": {marker: bool(data.get(marker, False)) for marker in _NON_RUNTIME_MARKERS},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _non_runtime_markers_true(receipt: InternalModelCallReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return all(bool(data.get(marker, False)) for marker in _NON_RUNTIME_MARKERS)


def validate_internal_model_call_review_receipt(receipt: InternalModelCallReviewReceipt | Mapping[str, Any]) -> tuple[InternalModelCallReviewFinding, ...]:
    data = _mapping(receipt)
    findings: list[InternalModelCallReviewFinding] = []
    if not data:
        return (_finding("review_receipt_malformed", "model-call review receipt is malformed"),)
    if not str(data.get("reviewer_ref", "")):
        findings.append(_finding("reviewer_ref_missing", "reviewer_ref is required"))
    if not _non_runtime_markers_true(receipt):
        findings.append(_finding("non_runtime_marker_missing", "all non-runtime markers must be true"))
    for field_name in _ALLOWANCE_FIELDS:
        if bool(data.get(field_name, False)):
            findings.append(_finding("forbidden_allowance_requested", f"{field_name} must remain false"))
    if bool(data.get("expired", False)):
        findings.append(_finding("review_expired", "model-call review receipt is expired"))
    if bool(data.get("forbidden_override_attempted", False)):
        findings.append(_finding("forbidden_override_attempted", "model-call review attempted a forbidden override"))
    expected = compute_internal_model_call_review_digest(receipt)
    if str(data.get("review_digest", "")) != expected:
        findings.append(_finding("review_digest_mismatch", "review digest does not match receipt metadata"))
    return tuple(findings)


def internal_model_call_review_attempts_forbidden_override(receipt: InternalModelCallReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("forbidden_override_attempted", False)
        or data.get("review_status") == InternalModelCallReviewStatus.MODEL_CALL_REVIEW_FORBIDDEN_OVERRIDE_ATTEMPTED
        or any(_mapping(finding).get("code") in {"forbidden_allowance_requested", "preflight_hard_denial_non_overridable"} for finding in data.get("findings", ()) or ())
    )


def internal_model_call_review_preserves_provider_forbidden(receipt: InternalModelCallReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("provider_call_allowed") is False
        and data.get("llm_call_allowed") is False
        and data.get("provider_call_forbidden") is True
        and data.get("llm_call_forbidden") is True
        and data.get("does_not_call_llm") is True
        and data.get("does_not_send_to_provider") is True
    )


def _has_no_runtime_allowance(receipt: InternalModelCallReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return all(data.get(field_name) is False for field_name in _ALLOWANCE_FIELDS)


def _required_mitigations_addressed(receipt: InternalModelCallReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    required = set(_tuple_str(data.get("required_mitigation_codes", ())))
    accepted = set(_tuple_str(data.get("accepted_mitigation_codes", ())))
    approved_constraints = set(_tuple_str(data.get("approved_constraint_codes", ())))
    rejected = set(_tuple_str(data.get("rejected_mitigation_codes", ()))) | set(_tuple_str(data.get("rejected_constraint_codes", ())))
    addressed = accepted | approved_constraints
    return required.isdisjoint(rejected) and required.issubset(addressed)


def internal_model_call_review_satisfies_preflight(
    preflight: InternalModelCallPreflight | Mapping[str, Any],
    review_receipt: InternalModelCallReviewReceipt | Mapping[str, Any] | None,
) -> bool:
    if review_receipt is None:
        return False
    preflight_data = _mapping(preflight)
    review_data = _mapping(review_receipt)
    if not preflight_data or not review_data:
        return False
    if str(preflight_data.get("preflight_status", "")) not in _READY_PREFLIGHT_STATUSES:
        return False
    if str(review_data.get("review_status", "")) not in {
        InternalModelCallReviewStatus.MODEL_CALL_REVIEW_APPROVED,
        InternalModelCallReviewStatus.MODEL_CALL_REVIEW_APPROVED_WITH_CONSTRAINTS,
    }:
        return False
    if str(review_data.get("preflight_id", "")) != str(preflight_data.get("preflight_id", "")):
        return False
    if str(review_data.get("preflight_digest", "")) != str(preflight_data.get("preflight_digest", "")):
        return False
    if bool(review_data.get("expired", False)) or internal_model_call_review_attempts_forbidden_override(review_receipt):
        return False
    if validate_internal_model_call_review_receipt(review_receipt):
        return False
    if not _required_mitigations_addressed(review_receipt):
        return False
    if not internal_model_call_review_preserves_provider_forbidden(review_receipt):
        return False
    if not _has_no_runtime_allowance(review_receipt):
        return False
    return _non_runtime_markers_true(review_receipt)


def internal_model_call_review_approves_future_gate(receipt: InternalModelCallReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("review_status") in {
            InternalModelCallReviewStatus.MODEL_CALL_REVIEW_APPROVED,
            InternalModelCallReviewStatus.MODEL_CALL_REVIEW_APPROVED_WITH_CONSTRAINTS,
        }
        and not data.get("expired", False)
        and not internal_model_call_review_attempts_forbidden_override(receipt)
        and internal_model_call_review_preserves_provider_forbidden(receipt)
        and _has_no_runtime_allowance(receipt)
        and _required_mitigations_addressed(receipt)
    )


def internal_model_call_review_denies_future_gate(receipt: InternalModelCallReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return str(data.get("review_status", "")) in {
        InternalModelCallReviewStatus.MODEL_CALL_REVIEW_REJECTED,
        InternalModelCallReviewStatus.MODEL_CALL_REVIEW_EXPIRED,
        InternalModelCallReviewStatus.MODEL_CALL_REVIEW_INVALID,
        InternalModelCallReviewStatus.MODEL_CALL_REVIEW_FORBIDDEN_OVERRIDE_ATTEMPTED,
        InternalModelCallReviewStatus.MODEL_CALL_REVIEW_NOT_APPLICABLE,
    }


def explain_internal_model_call_review_findings(receipt_or_findings: InternalModelCallReviewReceipt | Mapping[str, Any] | Sequence[InternalModelCallReviewFinding]) -> tuple[str, ...]:
    if isinstance(receipt_or_findings, Sequence) and not isinstance(receipt_or_findings, (str, bytes, Mapping)):
        findings = receipt_or_findings
    else:
        findings = _mapping(receipt_or_findings).get("findings", ()) or ()
    return tuple(
        f"{item.get('severity', '')}:{item.get('code', '')}:{item.get('detail', '')}"
        for item in (_mapping(finding) for finding in findings)
    )


def summarize_internal_model_call_review_receipt(receipt: InternalModelCallReviewReceipt | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(receipt)
    return {
        "review_receipt_id": str(data.get("review_receipt_id", "")),
        "review_status": str(data.get("review_status", "")),
        "preflight_id": str(data.get("preflight_id", "")),
        "preflight_status": str(data.get("preflight_status", "")),
        "preflight_digest": str(data.get("preflight_digest", "")),
        "reviewer_ref": str(data.get("reviewer_ref", "")),
        "review_scope": str(data.get("review_scope", "")),
        "decision": str(data.get("decision", "")),
        "required_mitigation_count": len(_tuple_str(data.get("required_mitigation_codes", ()))),
        "accepted_mitigation_count": len(_tuple_str(data.get("accepted_mitigation_codes", ()))),
        "rejected_mitigation_count": len(_tuple_str(data.get("rejected_mitigation_codes", ()))),
        "approved_constraint_count": len(_tuple_str(data.get("approved_constraint_codes", ()))),
        "rejected_constraint_count": len(_tuple_str(data.get("rejected_constraint_codes", ()))),
        "expired": bool(data.get("expired", False)),
        "forbidden_override_attempted": bool(data.get("forbidden_override_attempted", False)),
        "provider_call_allowed": bool(data.get("provider_call_allowed", False)),
        "llm_call_allowed": bool(data.get("llm_call_allowed", False)),
        "runtime_allowance_allowed": any(bool(data.get(field_name, False)) for field_name in _ALLOWANCE_FIELDS if field_name not in {"provider_call_allowed", "llm_call_allowed"}),
        "finding_count": len(tuple(data.get("findings", ()) or ())),
        "review_digest": str(data.get("review_digest", "")),
        "model_call_review_receipt_only": bool(data.get("model_call_review_receipt_only", False)),
        "future_gate_review_only": bool(data.get("future_gate_review_only", False)),
        "provider_call_forbidden": bool(data.get("provider_call_forbidden", False)),
        "llm_call_forbidden": bool(data.get("llm_call_forbidden", False)),
        "does_not_call_llm": bool(data.get("does_not_call_llm", False)),
        "does_not_send_to_provider": bool(data.get("does_not_send_to_provider", False)),
    }
