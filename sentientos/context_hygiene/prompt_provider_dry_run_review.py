from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_provider_dry_run import (
    ProviderDryRunModelFamily,
    ProviderDryRunProviderFamily,
    ProviderDryRunRequestEnvelope,
    ProviderDryRunStatus,
    compute_provider_dry_run_digest,
    provider_dry_run_has_no_network_egress,
    provider_dry_run_has_no_provider_credentials,
    provider_dry_run_has_no_runtime_authority,
    provider_dry_run_is_non_sendable,
)


class ProviderDryRunEgressReviewStatus:
    PROVIDER_DRY_RUN_REVIEW_APPROVED = "provider_dry_run_review_approved"
    PROVIDER_DRY_RUN_REVIEW_APPROVED_WITH_CONSTRAINTS = "provider_dry_run_review_approved_with_constraints"
    PROVIDER_DRY_RUN_REVIEW_REJECTED = "provider_dry_run_review_rejected"
    PROVIDER_DRY_RUN_REVIEW_EXPIRED = "provider_dry_run_review_expired"
    PROVIDER_DRY_RUN_REVIEW_INVALID = "provider_dry_run_review_invalid"
    PROVIDER_DRY_RUN_REVIEW_FORBIDDEN_SEND_OVERRIDE_ATTEMPTED = "provider_dry_run_review_forbidden_send_override_attempted"
    PROVIDER_DRY_RUN_REVIEW_NOT_APPLICABLE = "provider_dry_run_review_not_applicable"


class ProviderDryRunEgressReviewDecision:
    APPROVE_FUTURE_PROVIDER_SIMULATION_GATE = "approve_future_provider_simulation_gate"
    APPROVE_FUTURE_EGRESS_REVIEW_GATE = "approve_future_egress_review_gate"
    APPROVE_WITH_CONSTRAINTS = "approve_with_constraints"
    REJECT_PROVIDER_DRY_RUN = "reject_provider_dry_run"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"
    NO_DECISION = "no_decision"


class ProviderDryRunEgressReviewScope:
    FUTURE_PROVIDER_SIMULATION_GATE = "future_provider_simulation_gate"
    FUTURE_EGRESS_REVIEW_GATE = "future_egress_review_gate"
    ACTUAL_PROVIDER_SEND_FORBIDDEN = "actual_provider_send_forbidden"
    NETWORK_EGRESS_FORBIDDEN = "network_egress_forbidden"
    CREDENTIAL_USE_FORBIDDEN = "credential_use_forbidden"
    TOOL_OR_ACTION_FORBIDDEN = "tool_or_action_forbidden"
    EXTERNAL_USER_VISIBLE_FORBIDDEN = "external_user_visible_forbidden"


@dataclass(frozen=True)
class ProviderDryRunEgressReviewFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderDryRunEgressReviewConstraint:
    code: str
    detail: str
    required: bool = True


@dataclass(frozen=True)
class ProviderDryRunEgressReviewExpiration:
    reviewed_at: str = ""
    expires_at: str = ""
    ttl_seconds: int = 0
    evaluated_at: str = ""


@dataclass(frozen=True)
class ProviderDryRunEgressReviewReceipt:
    review_receipt_id: str
    review_status: str
    dry_run_id: str
    dry_run_status: str
    dry_run_digest: str
    provider_family_label: str
    model_family_label: str
    candidate_id: str
    candidate_digest: str
    display_receipt_id: str
    display_receipt_digest: str
    preflight_id: str
    preflight_digest: str
    model_call_review_receipt_id: str
    model_call_review_digest: str
    packet_id: str
    packet_scope: str
    reviewer_ref: str
    review_scope: str
    decision: str
    approved_constraint_codes: tuple[str, ...]
    rejected_constraint_codes: tuple[str, ...]
    required_mitigation_codes: tuple[str, ...]
    accepted_mitigation_codes: tuple[str, ...]
    rejected_mitigation_codes: tuple[str, ...]
    provider_send_allowed: bool
    network_egress_allowed: bool
    credentials_allowed: bool
    provider_client_allowed: bool
    llm_call_allowed: bool
    tool_calls_allowed: bool
    memory_retrieval_allowed: bool
    memory_write_allowed: bool
    retention_allowed: bool
    action_execution_allowed: bool
    routing_allowed: bool
    expiration: ProviderDryRunEgressReviewExpiration
    expired: bool
    forbidden_send_override_attempted: bool
    findings: tuple[ProviderDryRunEgressReviewFinding, ...]
    rationale: str
    review_digest: str
    provider_dry_run_review_receipt_only: bool = True
    future_simulation_gate_review_only: bool = True
    non_sendable_preserved: bool = True
    provider_send_forbidden: bool = True
    network_egress_forbidden: bool = True
    credentials_forbidden: bool = True
    provider_client_forbidden: bool = True
    llm_call_forbidden: bool = True
    does_not_call_llm: bool = True
    does_not_send_to_provider: bool = True
    does_not_make_network_calls: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True


_APPROVE_DECISIONS = frozenset(
    {
        ProviderDryRunEgressReviewDecision.APPROVE_FUTURE_PROVIDER_SIMULATION_GATE,
        ProviderDryRunEgressReviewDecision.APPROVE_FUTURE_EGRESS_REVIEW_GATE,
        ProviderDryRunEgressReviewDecision.APPROVE_WITH_CONSTRAINTS,
    }
)
_REJECT_DECISIONS = frozenset(
    {
        ProviderDryRunEgressReviewDecision.REJECT_PROVIDER_DRY_RUN,
        ProviderDryRunEgressReviewDecision.REQUEST_MORE_EVIDENCE,
    }
)
_ALLOWED_DECISIONS = _APPROVE_DECISIONS | _REJECT_DECISIONS | {ProviderDryRunEgressReviewDecision.NO_DECISION}
_ALLOWED_SCOPES = frozenset(
    {
        ProviderDryRunEgressReviewScope.FUTURE_PROVIDER_SIMULATION_GATE,
        ProviderDryRunEgressReviewScope.FUTURE_EGRESS_REVIEW_GATE,
        ProviderDryRunEgressReviewScope.ACTUAL_PROVIDER_SEND_FORBIDDEN,
        ProviderDryRunEgressReviewScope.NETWORK_EGRESS_FORBIDDEN,
        ProviderDryRunEgressReviewScope.CREDENTIAL_USE_FORBIDDEN,
        ProviderDryRunEgressReviewScope.TOOL_OR_ACTION_FORBIDDEN,
        ProviderDryRunEgressReviewScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
    }
)
_READY_DRY_RUN_STATUSES = frozenset(
    {
        ProviderDryRunStatus.PROVIDER_DRY_RUN_READY,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_READY_WITH_WARNINGS,
    }
)
_HARD_DENIAL_DRY_RUN_STATUSES = frozenset(
    {
        ProviderDryRunStatus.PROVIDER_DRY_RUN_BLOCKED,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_INVALID_INPUT,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_REVIEW_MISSING,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_PREFLIGHT_NOT_READY,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_SEND_FORBIDDEN,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_RUNTIME_AUTHORITY_DETECTED,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_CREDENTIALS_DETECTED,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_NETWORK_EGRESS_DETECTED,
    }
)
_KNOWN_PROVIDER_FAMILIES = frozenset(
    {
        ProviderDryRunProviderFamily.PROVIDER_FAMILY_OPENAI_LABEL_ONLY,
        ProviderDryRunProviderFamily.PROVIDER_FAMILY_LOCAL_LABEL_ONLY,
    }
)
_KNOWN_MODEL_FAMILIES = frozenset(
    {
        ProviderDryRunModelFamily.MODEL_FAMILY_REASONING_LABEL_ONLY,
        ProviderDryRunModelFamily.MODEL_FAMILY_CHAT_LABEL_ONLY,
    }
)
_ALLOWANCE_FIELDS = (
    "provider_send_allowed",
    "network_egress_allowed",
    "credentials_allowed",
    "provider_client_allowed",
    "llm_call_allowed",
    "tool_calls_allowed",
    "memory_retrieval_allowed",
    "memory_write_allowed",
    "retention_allowed",
    "action_execution_allowed",
    "routing_allowed",
)
_MARKER_FIELDS = (
    "provider_dry_run_review_receipt_only",
    "future_simulation_gate_review_only",
    "non_sendable_preserved",
    "provider_send_forbidden",
    "network_egress_forbidden",
    "credentials_forbidden",
    "provider_client_forbidden",
    "llm_call_forbidden",
    "does_not_call_llm",
    "does_not_send_to_provider",
    "does_not_make_network_calls",
    "does_not_retrieve_memory",
    "does_not_write_memory",
    "does_not_trigger_feedback",
    "does_not_commit_retention",
    "does_not_execute_or_route_work",
    "does_not_admit_work",
)
_REQUIRED_DIGEST_FIELDS = (
    "dry_run_digest",
    "candidate_digest",
    "display_receipt_digest",
    "preflight_digest",
    "review_digest",
)
_PROVIDER_FORBIDDEN_CONSTRAINT_CODES = (
    "constraint:provider_send_forbidden",
    "constraint:network_egress_forbidden",
    "constraint:credentials_forbidden",
    "constraint:provider_client_forbidden",
    "constraint:llm_call_forbidden",
    "constraint:does_not_send_to_provider",
    "constraint:no_tools_memory_retention_actions_routing",
)
_FORBIDDEN_SCOPES = frozenset(
    {
        ProviderDryRunEgressReviewScope.ACTUAL_PROVIDER_SEND_FORBIDDEN,
        ProviderDryRunEgressReviewScope.NETWORK_EGRESS_FORBIDDEN,
        ProviderDryRunEgressReviewScope.CREDENTIAL_USE_FORBIDDEN,
        ProviderDryRunEgressReviewScope.TOOL_OR_ACTION_FORBIDDEN,
        ProviderDryRunEgressReviewScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
    }
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
    "api_key",
    "endpoint",
    "auth_header",
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
        return {str(key): _stable(item) for key, item in asdict(value).items()}
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


def _finding(code: str, detail: str, severity: str = "blocker") -> ProviderDryRunEgressReviewFinding:
    return ProviderDryRunEgressReviewFinding(code=code, detail=detail, severity=severity)


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


def _expiration(expires_at: str | None, ttl_seconds: int | None, reviewed_at: str | None, evaluated_at: str | None) -> ProviderDryRunEgressReviewExpiration:
    reviewed = reviewed_at or "1970-01-01T00:00:00Z"
    ttl = int(ttl_seconds or 0)
    expiry = expires_at or ""
    if not expiry and ttl > 0:
        base = _parse_time(reviewed) or datetime(1970, 1, 1, tzinfo=timezone.utc)
        expiry = _format_time(base + timedelta(seconds=ttl))
    return ProviderDryRunEgressReviewExpiration(reviewed_at=reviewed, expires_at=expiry, ttl_seconds=ttl, evaluated_at=evaluated_at or reviewed)


def _is_expired(expiration: ProviderDryRunEgressReviewExpiration) -> bool:
    expires = _parse_time(expiration.expires_at)
    evaluated = _parse_time(expiration.evaluated_at)
    return bool(expires and evaluated and evaluated >= expires)


def _code_from_text(prefix: str, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"


def extract_required_provider_dry_run_egress_review_mitigation_codes(envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(envelope)
    required: list[str] = []
    for finding in data.get("findings", ()) or ():
        code = str(_mapping(finding).get("code", ""))
        if code:
            required.append(f"mitigate:{code}")
    for warning in _tuple_str(data.get("warnings", ())):
        required.append(_code_from_text("warning", warning))
    for constraint in data.get("constraints", ()) or ():
        item = _mapping(constraint)
        code = str(item.get("code", ""))
        if code and bool(item.get("required", True)):
            required.append(f"constraint:{code}" if not code.startswith("constraint:") else code)
    if str(data.get("dry_run_status", "")) == ProviderDryRunStatus.PROVIDER_DRY_RUN_READY_WITH_WARNINGS:
        required.append("mitigate:provider_dry_run_warning_review_required")
    if bool(data.get("provider_send_forbidden", True)):
        required.extend(_PROVIDER_FORBIDDEN_CONSTRAINT_CODES)
    if bool(data.get("network_egress_forbidden", True)):
        required.append("constraint:network_egress_forbidden")
    if bool(data.get("credentials_forbidden", True)):
        required.append("constraint:credentials_forbidden")
    if bool(data.get("provider_client_absent", True)):
        required.append("constraint:provider_client_absent")
    return _dedupe(required)


def _contains_forbidden_marker(value: Any) -> bool:
    text = json.dumps(_stable(value), sort_keys=True, ensure_ascii=True, default=str).lower()
    return any(marker in text for marker in _PROMPT_RAW_RUNTIME_MARKERS)


def _dry_run_digest(envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any]) -> str:
    data = _mapping(envelope)
    recorded = str(data.get("dry_run_digest", ""))
    if not data:
        return ""
    try:
        computed = compute_provider_dry_run_digest(envelope)
    except Exception:
        computed = ""
    return computed or recorded


def _review_findings(
    envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any],
    *,
    decision: str,
    review_scope: str,
    reviewer_ref: str,
    approved_constraint_codes: Sequence[str],
    rejected_constraint_codes: Sequence[str],
    required_mitigation_codes: Sequence[str],
    accepted_mitigation_codes: Sequence[str],
    rejected_mitigation_codes: Sequence[str],
    provider_send_allowed: bool,
    network_egress_allowed: bool,
    credentials_allowed: bool,
    provider_client_allowed: bool,
    llm_call_allowed: bool,
    tool_calls_allowed: bool,
    memory_retrieval_allowed: bool,
    memory_write_allowed: bool,
    retention_allowed: bool,
    action_execution_allowed: bool,
    routing_allowed: bool,
    expired: bool,
) -> tuple[ProviderDryRunEgressReviewFinding, ...]:
    data = _mapping(envelope)
    findings: list[ProviderDryRunEgressReviewFinding] = []
    if not data:
        findings.append(_finding("dry_run_missing", "Phase 84 ProviderDryRunRequestEnvelope metadata is required"))
    if not reviewer_ref:
        findings.append(_finding("reviewer_ref_missing", "reviewer_ref is required for provider dry-run egress review receipt"))
    if decision not in _ALLOWED_DECISIONS:
        findings.append(_finding("decision_unknown", "provider dry-run egress review decision is not recognized"))
    if review_scope not in _ALLOWED_SCOPES:
        findings.append(_finding("review_scope_unknown", "provider dry-run egress review scope is not recognized"))
    if expired:
        findings.append(_finding("review_expired", "provider dry-run egress review receipt is expired"))

    approving = decision in _APPROVE_DECISIONS
    status = str(data.get("dry_run_status", ""))
    if approving and status in _HARD_DENIAL_DRY_RUN_STATUSES:
        findings.append(_finding("dry_run_hard_denial_non_overridable", f"dry-run status {status!r} cannot be approved in Phase 85"))
    if approving and status not in _READY_DRY_RUN_STATUSES:
        findings.append(_finding("dry_run_not_ready_for_review", "only ready or ready-with-warnings dry-runs may receive future-gate approval"))
    if approving and str(data.get("provider_family_label", "")) not in _KNOWN_PROVIDER_FAMILIES:
        findings.append(_finding("provider_family_unknown_non_overridable", "unknown provider family labels cannot be approved"))
    if approving and str(data.get("model_family_label", "")) not in _KNOWN_MODEL_FAMILIES:
        findings.append(_finding("model_family_unknown_non_overridable", "unknown model family labels cannot be approved"))
    if approving and review_scope == ProviderDryRunEgressReviewScope.FUTURE_EGRESS_REVIEW_GATE and decision == ProviderDryRunEgressReviewDecision.APPROVE_FUTURE_PROVIDER_SIMULATION_GATE:
        findings.append(_finding("egress_review_scope_requires_constraints", "future egress review gate approval must be constrained"))
    if approving and review_scope in _FORBIDDEN_SCOPES:
        findings.append(_finding("review_scope_non_overridable", f"scope {review_scope!r} cannot be approved in Phase 85"))
    if approving and not provider_dry_run_is_non_sendable(envelope):
        findings.append(_finding("dry_run_non_sendable_not_preserved", "Phase 84 envelope must remain non-sendable"))
    if approving and not provider_dry_run_has_no_network_egress(envelope):
        findings.append(_finding("dry_run_network_egress_detected", "network egress markers cannot be approved"))
    if approving and not provider_dry_run_has_no_provider_credentials(envelope):
        findings.append(_finding("dry_run_credentials_detected", "credential/client markers cannot be approved"))
    if approving and not provider_dry_run_has_no_runtime_authority(envelope):
        findings.append(_finding("dry_run_runtime_authority_detected", "runtime authority cannot be approved"))

    for field_name in _REQUIRED_DIGEST_FIELDS:
        if not str(data.get(field_name, "")):
            findings.append(_finding("linked_digest_missing", f"{field_name} is required for provider dry-run egress review receipt"))
    if str(data.get("dry_run_digest", "")) and _dry_run_digest(envelope) != str(data.get("dry_run_digest", "")):
        findings.append(_finding("dry_run_digest_mismatch", "dry_run_digest does not match stable dry-run metadata"))

    allowances = {
        "provider_send_allowed": provider_send_allowed,
        "network_egress_allowed": network_egress_allowed,
        "credentials_allowed": credentials_allowed,
        "provider_client_allowed": provider_client_allowed,
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
            findings.append(_finding("forbidden_allowance_requested", f"{field_name} must remain false in Phase 85"))
    for finding in data.get("findings", ()) or ():
        if _contains_forbidden_marker(_mapping(finding)):
            findings.append(_finding("dry_run_forbidden_marker_finding_non_overridable", "dry-run findings contain non-overridable prompt/raw/provider/runtime marker evidence"))
            break
    return tuple(findings)


def _status(decision: str, findings: Sequence[ProviderDryRunEgressReviewFinding], expired: bool) -> str:
    codes = {finding.code for finding in findings}
    if expired:
        return ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_EXPIRED
    if any(code in codes for code in {"dry_run_missing", "reviewer_ref_missing", "decision_unknown", "review_scope_unknown", "linked_digest_missing", "dry_run_digest_mismatch"}):
        return ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_INVALID
    if "prompt_raw_runtime_marker_detected" in codes and decision not in _APPROVE_DECISIONS:
        return ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_INVALID
    if findings and decision in _APPROVE_DECISIONS:
        return ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_FORBIDDEN_SEND_OVERRIDE_ATTEMPTED
    if decision == ProviderDryRunEgressReviewDecision.APPROVE_FUTURE_PROVIDER_SIMULATION_GATE:
        return ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_APPROVED
    if decision in {
        ProviderDryRunEgressReviewDecision.APPROVE_FUTURE_EGRESS_REVIEW_GATE,
        ProviderDryRunEgressReviewDecision.APPROVE_WITH_CONSTRAINTS,
    }:
        return ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_APPROVED_WITH_CONSTRAINTS
    if decision in _REJECT_DECISIONS:
        return ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_REJECTED
    return ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_NOT_APPLICABLE


def build_provider_dry_run_egress_review_receipt(
    envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any],
    *,
    reviewer_ref: str,
    decision: str,
    review_scope: str = ProviderDryRunEgressReviewScope.FUTURE_PROVIDER_SIMULATION_GATE,
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
    provider_send_allowed: bool = False,
    network_egress_allowed: bool = False,
    credentials_allowed: bool = False,
    provider_client_allowed: bool = False,
    llm_call_allowed: bool = False,
    tool_calls_allowed: bool = False,
    memory_retrieval_allowed: bool = False,
    memory_write_allowed: bool = False,
    retention_allowed: bool = False,
    action_execution_allowed: bool = False,
    routing_allowed: bool = False,
) -> ProviderDryRunEgressReviewReceipt:
    data = _mapping(envelope)
    expiration = _expiration(expires_at, ttl_seconds, reviewed_at, evaluated_at)
    expired = _is_expired(expiration)
    required = _dedupe(_tuple_str(required_mitigation_codes) or extract_required_provider_dry_run_egress_review_mitigation_codes(envelope))
    approved = _dedupe(_tuple_str(approved_constraint_codes))
    rejected_constraints = _dedupe(_tuple_str(rejected_constraint_codes))
    accepted = _dedupe(_tuple_str(accepted_mitigation_codes))
    rejected_mitigations = _dedupe(_tuple_str(rejected_mitigation_codes))
    findings = _review_findings(
        envelope,
        decision=decision,
        review_scope=review_scope,
        reviewer_ref=reviewer_ref,
        approved_constraint_codes=approved,
        rejected_constraint_codes=rejected_constraints,
        required_mitigation_codes=required,
        accepted_mitigation_codes=accepted,
        rejected_mitigation_codes=rejected_mitigations,
        provider_send_allowed=bool(provider_send_allowed),
        network_egress_allowed=bool(network_egress_allowed),
        credentials_allowed=bool(credentials_allowed),
        provider_client_allowed=bool(provider_client_allowed),
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
    receipt = ProviderDryRunEgressReviewReceipt(
        review_receipt_id="",
        review_status=status,
        dry_run_id=str(data.get("dry_run_id", "")),
        dry_run_status=str(data.get("dry_run_status", "")),
        dry_run_digest=str(data.get("dry_run_digest", "")),
        provider_family_label=str(data.get("provider_family_label", "")),
        model_family_label=str(data.get("model_family_label", "")),
        candidate_id=str(data.get("candidate_id", "")),
        candidate_digest=str(data.get("candidate_digest", "")),
        display_receipt_id=str(data.get("display_receipt_id", "")),
        display_receipt_digest=str(data.get("display_receipt_digest", "")),
        preflight_id=str(data.get("preflight_id", "")),
        preflight_digest=str(data.get("preflight_digest", "")),
        model_call_review_receipt_id=str(data.get("review_receipt_id", "")),
        model_call_review_digest=str(data.get("review_digest", "")),
        packet_id=str(data.get("packet_id", "")),
        packet_scope=str(data.get("packet_scope", "")),
        reviewer_ref=str(reviewer_ref),
        review_scope=str(review_scope),
        decision=str(decision),
        approved_constraint_codes=approved,
        rejected_constraint_codes=rejected_constraints,
        required_mitigation_codes=required,
        accepted_mitigation_codes=accepted,
        rejected_mitigation_codes=rejected_mitigations,
        provider_send_allowed=bool(provider_send_allowed),
        network_egress_allowed=bool(network_egress_allowed),
        credentials_allowed=bool(credentials_allowed),
        provider_client_allowed=bool(provider_client_allowed),
        llm_call_allowed=bool(llm_call_allowed),
        tool_calls_allowed=bool(tool_calls_allowed),
        memory_retrieval_allowed=bool(memory_retrieval_allowed),
        memory_write_allowed=bool(memory_write_allowed),
        retention_allowed=bool(retention_allowed),
        action_execution_allowed=bool(action_execution_allowed),
        routing_allowed=bool(routing_allowed),
        expiration=expiration,
        expired=expired,
        forbidden_send_override_attempted=status == ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_FORBIDDEN_SEND_OVERRIDE_ATTEMPTED,
        findings=tuple(findings),
        rationale=str(rationale)[:1000],
        review_digest="",
    )
    digest = compute_provider_dry_run_egress_review_digest(receipt)
    return replace(receipt, review_receipt_id=f"provider-dry-run-egress-review:{receipt.dry_run_id or 'missing'}:{digest[:16]}", review_digest=digest)


def build_provider_dry_run_egress_review_receipt_from_envelope(
    envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any],
    **kwargs: Any,
) -> ProviderDryRunEgressReviewReceipt:
    return build_provider_dry_run_egress_review_receipt(envelope, **kwargs)


def compute_provider_dry_run_egress_review_digest(receipt: ProviderDryRunEgressReviewReceipt | Mapping[str, Any]) -> str:
    data = dict(_mapping(receipt))
    data.pop("review_digest", None)
    data.pop("review_receipt_id", None)
    payload = {
        "review_status": data.get("review_status", ""),
        "dry_run_id": data.get("dry_run_id", ""),
        "dry_run_status": data.get("dry_run_status", ""),
        "dry_run_digest": data.get("dry_run_digest", ""),
        "provider_family_label": data.get("provider_family_label", ""),
        "model_family_label": data.get("model_family_label", ""),
        "candidate_id": data.get("candidate_id", ""),
        "candidate_digest": data.get("candidate_digest", ""),
        "display_receipt_id": data.get("display_receipt_id", ""),
        "display_receipt_digest": data.get("display_receipt_digest", ""),
        "preflight_id": data.get("preflight_id", ""),
        "preflight_digest": data.get("preflight_digest", ""),
        "model_call_review_receipt_id": data.get("model_call_review_receipt_id", ""),
        "model_call_review_digest": data.get("model_call_review_digest", ""),
        "packet_id": data.get("packet_id", ""),
        "packet_scope": data.get("packet_scope", ""),
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
        "forbidden_send_override_attempted": bool(data.get("forbidden_send_override_attempted", False)),
        "findings": _stable(data.get("findings", ())),
        "rationale": data.get("rationale", ""),
        "markers": {marker: bool(data.get(marker, False)) for marker in _MARKER_FIELDS},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _markers_true(receipt: ProviderDryRunEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return all(bool(data.get(marker, False)) for marker in _MARKER_FIELDS)


def _has_no_allowance(receipt: ProviderDryRunEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return all(data.get(field_name) is False for field_name in _ALLOWANCE_FIELDS)


def provider_dry_run_review_preserves_non_sendable(receipt: ProviderDryRunEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("provider_send_allowed") is False
        and data.get("network_egress_allowed") is False
        and data.get("credentials_allowed") is False
        and data.get("provider_client_allowed") is False
        and data.get("llm_call_allowed") is False
        and data.get("non_sendable_preserved") is True
        and data.get("provider_send_forbidden") is True
        and data.get("network_egress_forbidden") is True
        and data.get("credentials_forbidden") is True
        and data.get("provider_client_forbidden") is True
        and data.get("llm_call_forbidden") is True
        and data.get("does_not_call_llm") is True
        and data.get("does_not_send_to_provider") is True
        and data.get("does_not_make_network_calls") is True
    )


def validate_provider_dry_run_egress_review_receipt(receipt: ProviderDryRunEgressReviewReceipt | Mapping[str, Any]) -> tuple[ProviderDryRunEgressReviewFinding, ...]:
    data = _mapping(receipt)
    findings: list[ProviderDryRunEgressReviewFinding] = []
    if not data:
        return (_finding("review_receipt_malformed", "provider dry-run egress review receipt is malformed"),)
    if not str(data.get("reviewer_ref", "")):
        findings.append(_finding("reviewer_ref_missing", "reviewer_ref is required"))
    if not _markers_true(receipt):
        findings.append(_finding("non_sendable_marker_missing", "all non-sendable review markers must be true"))
    for field_name in _ALLOWANCE_FIELDS:
        if bool(data.get(field_name, False)):
            findings.append(_finding("forbidden_allowance_requested", f"{field_name} must remain false"))
    if bool(data.get("expired", False)):
        findings.append(_finding("review_expired", "provider dry-run egress review receipt is expired"))
    if bool(data.get("forbidden_send_override_attempted", False)):
        findings.append(_finding("forbidden_send_override_attempted", "provider dry-run egress review attempted a forbidden send override"))
    expected = compute_provider_dry_run_egress_review_digest(receipt)
    if str(data.get("review_digest", "")) != expected:
        findings.append(_finding("review_digest_mismatch", "review digest does not match receipt metadata"))
    return tuple(findings)


def provider_dry_run_review_attempts_forbidden_send_override(receipt: ProviderDryRunEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    non_overridable = {
        "forbidden_allowance_requested",
        "dry_run_hard_denial_non_overridable",
        "review_scope_non_overridable",
        "provider_family_unknown_non_overridable",
        "model_family_unknown_non_overridable",
        "dry_run_forbidden_marker_finding_non_overridable",
    }
    return bool(
        data.get("forbidden_send_override_attempted", False)
        or data.get("review_status") == ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_FORBIDDEN_SEND_OVERRIDE_ATTEMPTED
        or any(_mapping(finding).get("code") in non_overridable for finding in data.get("findings", ()) or ())
    )


def _required_mitigations_addressed(receipt: ProviderDryRunEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    required = set(_tuple_str(data.get("required_mitigation_codes", ())))
    accepted = set(_tuple_str(data.get("accepted_mitigation_codes", ())))
    approved_constraints = set(_tuple_str(data.get("approved_constraint_codes", ())))
    rejected = set(_tuple_str(data.get("rejected_mitigation_codes", ()))) | set(_tuple_str(data.get("rejected_constraint_codes", ())))
    addressed = accepted | approved_constraints
    return required.isdisjoint(rejected) and required.issubset(addressed)


def provider_dry_run_review_satisfies_envelope(
    envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any],
    review_receipt: ProviderDryRunEgressReviewReceipt | Mapping[str, Any] | None,
) -> bool:
    if review_receipt is None:
        return False
    envelope_data = _mapping(envelope)
    review_data = _mapping(review_receipt)
    if not envelope_data or not review_data:
        return False
    if str(envelope_data.get("dry_run_status", "")) not in _READY_DRY_RUN_STATUSES:
        return False
    if str(review_data.get("review_status", "")) not in {
        ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_APPROVED,
        ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_APPROVED_WITH_CONSTRAINTS,
    }:
        return False
    if str(review_data.get("dry_run_id", "")) != str(envelope_data.get("dry_run_id", "")):
        return False
    if str(review_data.get("dry_run_digest", "")) != str(envelope_data.get("dry_run_digest", "")):
        return False
    if bool(review_data.get("expired", False)) or provider_dry_run_review_attempts_forbidden_send_override(review_receipt):
        return False
    if validate_provider_dry_run_egress_review_receipt(review_receipt):
        return False
    if not _required_mitigations_addressed(review_receipt):
        return False
    if not provider_dry_run_review_preserves_non_sendable(review_receipt):
        return False
    if not _has_no_allowance(review_receipt):
        return False
    return _markers_true(review_receipt)


def provider_dry_run_review_approves_future_simulation_gate(receipt: ProviderDryRunEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("review_status") == ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_APPROVED
        and data.get("review_scope") == ProviderDryRunEgressReviewScope.FUTURE_PROVIDER_SIMULATION_GATE
        and not data.get("expired", False)
        and not provider_dry_run_review_attempts_forbidden_send_override(receipt)
        and provider_dry_run_review_preserves_non_sendable(receipt)
        and _has_no_allowance(receipt)
        and _required_mitigations_addressed(receipt)
    )


def provider_dry_run_review_approves_future_egress_review_gate(receipt: ProviderDryRunEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("review_status") == ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_APPROVED_WITH_CONSTRAINTS
        and data.get("review_scope") == ProviderDryRunEgressReviewScope.FUTURE_EGRESS_REVIEW_GATE
        and not data.get("expired", False)
        and not provider_dry_run_review_attempts_forbidden_send_override(receipt)
        and provider_dry_run_review_preserves_non_sendable(receipt)
        and _has_no_allowance(receipt)
        and _required_mitigations_addressed(receipt)
    )


def provider_dry_run_review_denies_send(receipt: ProviderDryRunEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("provider_send_allowed") is False
        and data.get("provider_send_forbidden") is True
        and data.get("does_not_send_to_provider") is True
        and str(data.get("review_status", "")) in {
            ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_APPROVED,
            ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_APPROVED_WITH_CONSTRAINTS,
            ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_REJECTED,
            ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_EXPIRED,
            ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_INVALID,
            ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_FORBIDDEN_SEND_OVERRIDE_ATTEMPTED,
            ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_NOT_APPLICABLE,
        }
    )


def explain_provider_dry_run_egress_review_findings(receipt_or_findings: ProviderDryRunEgressReviewReceipt | Mapping[str, Any] | Sequence[ProviderDryRunEgressReviewFinding]) -> tuple[str, ...]:
    if isinstance(receipt_or_findings, Sequence) and not isinstance(receipt_or_findings, (str, bytes, Mapping)):
        findings = receipt_or_findings
    else:
        findings = _mapping(receipt_or_findings).get("findings", ()) or ()
    return tuple(
        f"{item.get('severity', '')}:{item.get('code', '')}:{item.get('detail', '')}"
        for item in (_mapping(finding) for finding in findings)
    )


def summarize_provider_dry_run_egress_review_receipt(receipt: ProviderDryRunEgressReviewReceipt | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(receipt)
    return {
        "review_receipt_id": str(data.get("review_receipt_id", "")),
        "review_status": str(data.get("review_status", "")),
        "dry_run_id": str(data.get("dry_run_id", "")),
        "dry_run_status": str(data.get("dry_run_status", "")),
        "dry_run_digest": str(data.get("dry_run_digest", "")),
        "reviewer_ref": str(data.get("reviewer_ref", "")),
        "review_scope": str(data.get("review_scope", "")),
        "decision": str(data.get("decision", "")),
        "required_mitigation_count": len(_tuple_str(data.get("required_mitigation_codes", ()))),
        "accepted_mitigation_count": len(_tuple_str(data.get("accepted_mitigation_codes", ()))),
        "rejected_mitigation_count": len(_tuple_str(data.get("rejected_mitigation_codes", ()))),
        "approved_constraint_count": len(_tuple_str(data.get("approved_constraint_codes", ()))),
        "rejected_constraint_count": len(_tuple_str(data.get("rejected_constraint_codes", ()))),
        "expired": bool(data.get("expired", False)),
        "forbidden_send_override_attempted": bool(data.get("forbidden_send_override_attempted", False)),
        "provider_send_allowed": bool(data.get("provider_send_allowed", False)),
        "network_egress_allowed": bool(data.get("network_egress_allowed", False)),
        "credentials_allowed": bool(data.get("credentials_allowed", False)),
        "provider_client_allowed": bool(data.get("provider_client_allowed", False)),
        "llm_call_allowed": bool(data.get("llm_call_allowed", False)),
        "runtime_allowance_allowed": any(bool(data.get(field_name, False)) for field_name in _ALLOWANCE_FIELDS if field_name not in {"provider_send_allowed", "network_egress_allowed", "credentials_allowed", "provider_client_allowed", "llm_call_allowed"}),
        "finding_count": len(tuple(data.get("findings", ()) or ())),
        "review_digest": str(data.get("review_digest", "")),
        "provider_dry_run_review_receipt_only": bool(data.get("provider_dry_run_review_receipt_only", False)),
        "future_simulation_gate_review_only": bool(data.get("future_simulation_gate_review_only", False)),
        "non_sendable_preserved": bool(data.get("non_sendable_preserved", False)),
        "provider_send_forbidden": bool(data.get("provider_send_forbidden", False)),
        "network_egress_forbidden": bool(data.get("network_egress_forbidden", False)),
        "credentials_forbidden": bool(data.get("credentials_forbidden", False)),
        "provider_client_forbidden": bool(data.get("provider_client_forbidden", False)),
        "llm_call_forbidden": bool(data.get("llm_call_forbidden", False)),
        "does_not_call_llm": bool(data.get("does_not_call_llm", False)),
        "does_not_send_to_provider": bool(data.get("does_not_send_to_provider", False)),
        "does_not_make_network_calls": bool(data.get("does_not_make_network_calls", False)),
    }
