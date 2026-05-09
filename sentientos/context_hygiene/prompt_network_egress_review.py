from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_network_egress_preflight import (
    ProviderNetworkEgressPreflight,
    ProviderNetworkEgressPreflightRing,
    ProviderNetworkEgressPreflightStatus,
    compute_provider_network_egress_preflight_digest,
    provider_network_egress_preflight_allows_future_review_gate,
    provider_network_egress_preflight_digest_chain_complete,
    provider_network_egress_preflight_forbids_network,
    provider_network_egress_preflight_forbids_provider_send,
    provider_network_egress_preflight_has_no_credentials,
    provider_network_egress_preflight_has_no_runtime_authority,
)


class ProviderNetworkEgressReviewStatus:
    NETWORK_EGRESS_REVIEW_APPROVED = "network_egress_review_approved"
    NETWORK_EGRESS_REVIEW_APPROVED_WITH_CONSTRAINTS = "network_egress_review_approved_with_constraints"
    NETWORK_EGRESS_REVIEW_REJECTED = "network_egress_review_rejected"
    NETWORK_EGRESS_REVIEW_EXPIRED = "network_egress_review_expired"
    NETWORK_EGRESS_REVIEW_INVALID = "network_egress_review_invalid"
    NETWORK_EGRESS_REVIEW_FORBIDDEN_NETWORK_OVERRIDE_ATTEMPTED = "network_egress_review_forbidden_network_override_attempted"
    NETWORK_EGRESS_REVIEW_NOT_APPLICABLE = "network_egress_review_not_applicable"


class ProviderNetworkEgressReviewDecision:
    APPROVE_FUTURE_NETWORK_EGRESS_REVIEW_GATE = "approve_future_network_egress_review_gate"
    APPROVE_FUTURE_PROVIDER_CALL_DRY_RUN_GATE = "approve_future_provider_call_dry_run_gate"
    APPROVE_FUTURE_TRANSPORT_NULL_ADAPTER_GATE = "approve_future_transport_null_adapter_gate"
    APPROVE_WITH_CONSTRAINTS = "approve_with_constraints"
    REJECT_NETWORK_EGRESS_PREFLIGHT = "reject_network_egress_preflight"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"
    NO_DECISION = "no_decision"


class ProviderNetworkEgressReviewScope:
    FUTURE_NETWORK_EGRESS_REVIEW_GATE = "future_network_egress_review_gate"
    FUTURE_PROVIDER_CALL_DRY_RUN_GATE = "future_provider_call_dry_run_gate"
    FUTURE_TRANSPORT_NULL_ADAPTER_GATE = "future_transport_null_adapter_gate"
    ACTUAL_NETWORK_EGRESS_FORBIDDEN = "actual_network_egress_forbidden"
    ACTUAL_PROVIDER_SEND_FORBIDDEN = "actual_provider_send_forbidden"
    CREDENTIAL_USE_FORBIDDEN = "credential_use_forbidden"
    PROVIDER_CLIENT_USE_FORBIDDEN = "provider_client_use_forbidden"
    ENDPOINT_USE_FORBIDDEN = "endpoint_use_forbidden"
    TOOL_OR_ACTION_FORBIDDEN = "tool_or_action_forbidden"
    EXTERNAL_USER_VISIBLE_FORBIDDEN = "external_user_visible_forbidden"


@dataclass(frozen=True)
class ProviderNetworkEgressReviewFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderNetworkEgressReviewConstraint:
    code: str
    detail: str
    required: bool = True


@dataclass(frozen=True)
class ProviderNetworkEgressReviewExpiration:
    reviewed_at: str = ""
    expires_at: str = ""
    ttl_seconds: int = 0
    evaluated_at: str = ""


@dataclass(frozen=True)
class ProviderNetworkEgressReviewReceipt:
    review_receipt_id: str
    review_status: str
    network_preflight_id: str
    network_preflight_status: str
    network_preflight_digest: str
    requested_ring: str
    effective_ring: str
    dry_run_id: str
    dry_run_digest: str
    egress_review_receipt_id: str
    egress_review_digest: str
    simulation_id: str
    simulation_digest: str
    provider_family_label: str
    model_family_label: str
    candidate_id: str
    candidate_digest: str
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
    network_egress_allowed: bool
    provider_send_allowed: bool
    credentials_allowed: bool
    provider_client_allowed: bool
    endpoint_allowed: bool
    llm_call_allowed: bool
    semantic_generation_allowed: bool
    tool_calls_allowed: bool
    memory_retrieval_allowed: bool
    memory_write_allowed: bool
    retention_allowed: bool
    action_execution_allowed: bool
    routing_allowed: bool
    expiration: ProviderNetworkEgressReviewExpiration
    expired: bool
    forbidden_network_override_attempted: bool
    findings: tuple[ProviderNetworkEgressReviewFinding, ...]
    rationale: str
    review_digest: str
    network_egress_review_receipt_only: bool = True
    future_network_gate_review_only: bool = True
    network_egress_forbidden: bool = True
    provider_send_forbidden: bool = True
    credentials_forbidden: bool = True
    provider_client_forbidden: bool = True
    endpoint_forbidden: bool = True
    llm_call_forbidden: bool = True
    semantic_generation_forbidden: bool = True
    does_not_make_network_calls: bool = True
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
        ProviderNetworkEgressReviewDecision.APPROVE_FUTURE_NETWORK_EGRESS_REVIEW_GATE,
        ProviderNetworkEgressReviewDecision.APPROVE_FUTURE_PROVIDER_CALL_DRY_RUN_GATE,
        ProviderNetworkEgressReviewDecision.APPROVE_FUTURE_TRANSPORT_NULL_ADAPTER_GATE,
        ProviderNetworkEgressReviewDecision.APPROVE_WITH_CONSTRAINTS,
    }
)
_REJECT_DECISIONS = frozenset(
    {
        ProviderNetworkEgressReviewDecision.REJECT_NETWORK_EGRESS_PREFLIGHT,
        ProviderNetworkEgressReviewDecision.REQUEST_MORE_EVIDENCE,
    }
)
_ALLOWED_DECISIONS = _APPROVE_DECISIONS | _REJECT_DECISIONS | {ProviderNetworkEgressReviewDecision.NO_DECISION}
_ALLOWED_SCOPES = frozenset(
    {
        ProviderNetworkEgressReviewScope.FUTURE_NETWORK_EGRESS_REVIEW_GATE,
        ProviderNetworkEgressReviewScope.FUTURE_PROVIDER_CALL_DRY_RUN_GATE,
        ProviderNetworkEgressReviewScope.FUTURE_TRANSPORT_NULL_ADAPTER_GATE,
        ProviderNetworkEgressReviewScope.ACTUAL_NETWORK_EGRESS_FORBIDDEN,
        ProviderNetworkEgressReviewScope.ACTUAL_PROVIDER_SEND_FORBIDDEN,
        ProviderNetworkEgressReviewScope.CREDENTIAL_USE_FORBIDDEN,
        ProviderNetworkEgressReviewScope.PROVIDER_CLIENT_USE_FORBIDDEN,
        ProviderNetworkEgressReviewScope.ENDPOINT_USE_FORBIDDEN,
        ProviderNetworkEgressReviewScope.TOOL_OR_ACTION_FORBIDDEN,
        ProviderNetworkEgressReviewScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
    }
)
_FUTURE_SCOPES = frozenset(
    {
        ProviderNetworkEgressReviewScope.FUTURE_NETWORK_EGRESS_REVIEW_GATE,
        ProviderNetworkEgressReviewScope.FUTURE_PROVIDER_CALL_DRY_RUN_GATE,
        ProviderNetworkEgressReviewScope.FUTURE_TRANSPORT_NULL_ADAPTER_GATE,
    }
)
_FORBIDDEN_SCOPES = _ALLOWED_SCOPES - _FUTURE_SCOPES
_READY_PREFLIGHT_STATUSES = frozenset(
    {
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_FOR_REVIEW,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_WITH_WARNINGS,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_REVIEW_REQUIRED,
    }
)
_HARD_DENIAL_PREFLIGHT_STATUSES = frozenset(
    {
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_DENIED,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_INVALID_INPUT,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_DRY_RUN_INVALID,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_REVIEW_INVALID,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_SIMULATION_INVALID,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_CREDENTIALS_DETECTED,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_NETWORK_FORBIDDEN,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED,
    }
)
_ALLOWANCE_FIELDS = (
    "network_egress_allowed",
    "provider_send_allowed",
    "credentials_allowed",
    "provider_client_allowed",
    "endpoint_allowed",
    "llm_call_allowed",
    "semantic_generation_allowed",
    "tool_calls_allowed",
    "memory_retrieval_allowed",
    "memory_write_allowed",
    "retention_allowed",
    "action_execution_allowed",
    "routing_allowed",
)
_MARKER_FIELDS = (
    "network_egress_review_receipt_only",
    "future_network_gate_review_only",
    "network_egress_forbidden",
    "provider_send_forbidden",
    "credentials_forbidden",
    "provider_client_forbidden",
    "endpoint_forbidden",
    "llm_call_forbidden",
    "semantic_generation_forbidden",
    "does_not_make_network_calls",
    "does_not_call_llm",
    "does_not_send_to_provider",
    "does_not_retrieve_memory",
    "does_not_write_memory",
    "does_not_trigger_feedback",
    "does_not_commit_retention",
    "does_not_execute_or_route_work",
    "does_not_admit_work",
)
_PROVIDER_FORBIDDEN_CONSTRAINT_CODES = (
    "constraint:network_egress_forbidden",
    "constraint:provider_send_forbidden",
    "constraint:credentials_forbidden",
    "constraint:provider_client_forbidden",
    "constraint:endpoint_forbidden",
    "constraint:llm_call_forbidden",
    "constraint:semantic_generation_forbidden",
    "constraint:no_tools_memory_retention_actions_routing",
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
    "network_handle",
    "request_handle",
    "response_handle",
    "provider_client",
    "session",
    "transport",
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


def _finding(code: str, detail: str, severity: str = "blocker") -> ProviderNetworkEgressReviewFinding:
    return ProviderNetworkEgressReviewFinding(code=code, detail=detail, severity=severity)


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


def _expiration(expires_at: str | None, ttl_seconds: int | None, reviewed_at: str | None, evaluated_at: str | None) -> ProviderNetworkEgressReviewExpiration:
    reviewed = reviewed_at or "1970-01-01T00:00:00Z"
    ttl = int(ttl_seconds or 0)
    expiry = expires_at or ""
    if not expiry and ttl > 0:
        base = _parse_time(reviewed) or datetime(1970, 1, 1, tzinfo=timezone.utc)
        expiry = _format_time(base + timedelta(seconds=ttl))
    return ProviderNetworkEgressReviewExpiration(reviewed_at=reviewed, expires_at=expiry, ttl_seconds=ttl, evaluated_at=evaluated_at or reviewed)


def _is_expired(expiration: ProviderNetworkEgressReviewExpiration) -> bool:
    expires = _parse_time(expiration.expires_at)
    evaluated = _parse_time(expiration.evaluated_at)
    return bool(expires and evaluated and evaluated >= expires)


def _code_from_text(prefix: str, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"


def _contains_forbidden_marker(value: Any) -> bool:
    text = json.dumps(_stable(value), sort_keys=True, ensure_ascii=True, default=str).lower()
    return any(marker in text for marker in _PROMPT_RAW_RUNTIME_MARKERS)


def _preflight_digest(preflight: ProviderNetworkEgressPreflight | Mapping[str, Any]) -> str:
    data = _mapping(preflight)
    recorded = str(data.get("preflight_digest", ""))
    if not data:
        return ""
    try:
        computed = compute_provider_network_egress_preflight_digest(preflight)
    except Exception:
        computed = ""
    return computed or recorded


def extract_required_provider_network_egress_review_mitigation_codes(preflight: ProviderNetworkEgressPreflight | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(preflight)
    required: list[str] = []
    for finding in data.get("findings", ()) or ():
        code = str(_mapping(finding).get("code", ""))
        if code:
            required.append(f"mitigate:{code}")
    for warning in _tuple_str(data.get("warnings", ())):
        required.append(_code_from_text("warning", warning))
    for mitigation in _tuple_str(data.get("required_mitigations", ())):
        required.append(mitigation if ":" in mitigation else f"mitigate:{mitigation}")
    status = str(data.get("preflight_status", ""))
    if status == ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_REVIEW_REQUIRED:
        required.append("mitigate:network_egress_preflight_review_required")
    if status == ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_WITH_WARNINGS:
        required.append("mitigate:network_egress_preflight_warning_review_required")
    if bool(data.get("network_egress_forbidden", True)):
        required.append("constraint:network_egress_forbidden")
    if bool(data.get("provider_send_forbidden", True)):
        required.append("constraint:provider_send_forbidden")
    if bool(data.get("credentials_forbidden", True)):
        required.append("constraint:credentials_forbidden")
    if bool(data.get("provider_client_forbidden", True)):
        required.append("constraint:provider_client_forbidden")
    if bool(data.get("llm_call_forbidden", True)):
        required.append("constraint:llm_call_forbidden")
    if bool(data.get("semantic_generation_forbidden", True)):
        required.append("constraint:semantic_generation_forbidden")
    required.extend(_PROVIDER_FORBIDDEN_CONSTRAINT_CODES)
    return _dedupe(required)


def _review_findings(
    preflight: ProviderNetworkEgressPreflight | Mapping[str, Any],
    *,
    decision: str,
    review_scope: str,
    reviewer_ref: str,
    network_egress_allowed: bool,
    provider_send_allowed: bool,
    credentials_allowed: bool,
    provider_client_allowed: bool,
    endpoint_allowed: bool,
    llm_call_allowed: bool,
    semantic_generation_allowed: bool,
    tool_calls_allowed: bool,
    memory_retrieval_allowed: bool,
    memory_write_allowed: bool,
    retention_allowed: bool,
    action_execution_allowed: bool,
    routing_allowed: bool,
    expired: bool,
) -> tuple[ProviderNetworkEgressReviewFinding, ...]:
    data = _mapping(preflight)
    findings: list[ProviderNetworkEgressReviewFinding] = []
    if not data:
        findings.append(_finding("network_preflight_missing", "Phase 87 ProviderNetworkEgressPreflight metadata is required"))
    if not reviewer_ref:
        findings.append(_finding("reviewer_ref_missing", "reviewer_ref is required for provider network-egress review receipt"))
    if decision not in _ALLOWED_DECISIONS:
        findings.append(_finding("decision_unknown", "provider network-egress review decision is not recognized"))
    if review_scope not in _ALLOWED_SCOPES:
        findings.append(_finding("review_scope_unknown", "provider network-egress review scope is not recognized"))
    if expired:
        findings.append(_finding("review_expired", "provider network-egress review receipt is expired"))

    approving = decision in _APPROVE_DECISIONS
    status = str(data.get("preflight_status", ""))
    if approving and status in _HARD_DENIAL_PREFLIGHT_STATUSES:
        findings.append(_finding("network_preflight_hard_denial_non_overridable", f"network preflight status {status!r} cannot be approved in Phase 88"))
    if approving and status not in _READY_PREFLIGHT_STATUSES:
        findings.append(_finding("network_preflight_not_ready_for_review", "only ready, ready-with-warnings, or review-required preflights may receive future-gate approval"))
    if approving and review_scope in _FORBIDDEN_SCOPES:
        findings.append(_finding("review_scope_non_overridable", f"scope {review_scope!r} cannot be approved in Phase 88"))
    if approving and str(data.get("requested_ring", "")) == ProviderNetworkEgressPreflightRing.LIVE_PROVIDER_SEND_FORBIDDEN:
        findings.append(_finding("live_provider_send_ring_non_overridable", "live provider send ring remains forbidden"))
    if approving and str(data.get("requested_ring", "")) not in {
        ProviderNetworkEgressPreflightRing.NETWORK_EGRESS_REVIEW_PREFLIGHT_ONLY,
        ProviderNetworkEgressPreflightRing.FUTURE_NETWORK_EGRESS_REVIEW_GATE,
        ProviderNetworkEgressPreflightRing.FUTURE_PROVIDER_CALL_DRY_RUN_GATE,
    }:
        findings.append(_finding("requested_ring_unknown_non_overridable", "unknown network preflight ring cannot be approved"))
    if approving and not provider_network_egress_preflight_allows_future_review_gate(preflight):
        findings.append(_finding("network_preflight_future_gate_not_allowed", "preflight does not allow a future metadata review gate"))
    if approving and not provider_network_egress_preflight_digest_chain_complete(preflight):
        findings.append(_finding("digest_chain_incomplete_non_overridable", "network preflight digest/evidence chain is incomplete or mismatched"))
    if approving and not provider_network_egress_preflight_forbids_network(preflight):
        findings.append(_finding("network_forbidden_not_preserved", "network-forbidden markers cannot be overridden"))
    if approving and not provider_network_egress_preflight_forbids_provider_send(preflight):
        findings.append(_finding("provider_send_forbidden_not_preserved", "provider-send-forbidden markers cannot be overridden"))
    if approving and not provider_network_egress_preflight_has_no_credentials(preflight):
        findings.append(_finding("credentials_detected_non_overridable", "credential markers cannot be approved"))
    if approving and not provider_network_egress_preflight_has_no_runtime_authority(preflight):
        findings.append(_finding("runtime_authority_detected_non_overridable", "runtime authority cannot be approved"))

    for field_name, allowed in {
        "network_egress_allowed": network_egress_allowed,
        "provider_send_allowed": provider_send_allowed,
        "credentials_allowed": credentials_allowed,
        "provider_client_allowed": provider_client_allowed,
        "endpoint_allowed": endpoint_allowed,
        "llm_call_allowed": llm_call_allowed,
        "semantic_generation_allowed": semantic_generation_allowed,
        "tool_calls_allowed": tool_calls_allowed,
        "memory_retrieval_allowed": memory_retrieval_allowed,
        "memory_write_allowed": memory_write_allowed,
        "retention_allowed": retention_allowed,
        "action_execution_allowed": action_execution_allowed,
        "routing_allowed": routing_allowed,
    }.items():
        if allowed:
            findings.append(_finding("forbidden_allowance_requested", f"{field_name} must remain false in Phase 88"))

    if not str(data.get("preflight_digest", "")):
        findings.append(_finding("linked_digest_missing", "network_preflight_digest is required for provider network-egress review receipt"))
    elif _preflight_digest(preflight) != str(data.get("preflight_digest", "")):
        findings.append(_finding("network_preflight_digest_mismatch", "network_preflight_digest does not match stable preflight metadata"))
    if not str(data.get("preflight_id", "")):
        findings.append(_finding("network_preflight_id_missing", "network_preflight_id is required for provider network-egress review receipt"))
    if approving and _contains_forbidden_marker(data.get("findings", ())) :
        findings.append(_finding("preflight_forbidden_marker_finding_non_overridable", "network preflight findings contain non-overridable prompt/raw/provider/network/runtime marker evidence"))
    return tuple(findings)


def _status(decision: str, findings: Sequence[ProviderNetworkEgressReviewFinding], expired: bool) -> str:
    codes = {finding.code for finding in findings}
    if expired:
        return ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_EXPIRED
    if any(code in codes for code in {"network_preflight_missing", "reviewer_ref_missing", "decision_unknown", "review_scope_unknown", "linked_digest_missing", "network_preflight_digest_mismatch", "network_preflight_id_missing"}):
        return ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_INVALID
    if findings and decision in _APPROVE_DECISIONS:
        return ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_FORBIDDEN_NETWORK_OVERRIDE_ATTEMPTED
    if decision == ProviderNetworkEgressReviewDecision.APPROVE_FUTURE_NETWORK_EGRESS_REVIEW_GATE:
        return ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_APPROVED
    if decision in {
        ProviderNetworkEgressReviewDecision.APPROVE_FUTURE_PROVIDER_CALL_DRY_RUN_GATE,
        ProviderNetworkEgressReviewDecision.APPROVE_FUTURE_TRANSPORT_NULL_ADAPTER_GATE,
        ProviderNetworkEgressReviewDecision.APPROVE_WITH_CONSTRAINTS,
    }:
        return ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_APPROVED_WITH_CONSTRAINTS
    if decision in _REJECT_DECISIONS:
        return ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_REJECTED
    return ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_NOT_APPLICABLE


def build_provider_network_egress_review_receipt(
    preflight: ProviderNetworkEgressPreflight | Mapping[str, Any],
    *,
    reviewer_ref: str,
    decision: str,
    review_scope: str = ProviderNetworkEgressReviewScope.FUTURE_NETWORK_EGRESS_REVIEW_GATE,
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
    network_egress_allowed: bool = False,
    provider_send_allowed: bool = False,
    credentials_allowed: bool = False,
    provider_client_allowed: bool = False,
    endpoint_allowed: bool = False,
    llm_call_allowed: bool = False,
    semantic_generation_allowed: bool = False,
    tool_calls_allowed: bool = False,
    memory_retrieval_allowed: bool = False,
    memory_write_allowed: bool = False,
    retention_allowed: bool = False,
    action_execution_allowed: bool = False,
    routing_allowed: bool = False,
) -> ProviderNetworkEgressReviewReceipt:
    data = _mapping(preflight)
    expiration = _expiration(expires_at, ttl_seconds, reviewed_at, evaluated_at)
    expired = _is_expired(expiration)
    required = _dedupe(_tuple_str(required_mitigation_codes) or extract_required_provider_network_egress_review_mitigation_codes(preflight))
    approved = _dedupe(_tuple_str(approved_constraint_codes))
    rejected_constraints = _dedupe(_tuple_str(rejected_constraint_codes))
    accepted = _dedupe(_tuple_str(accepted_mitigation_codes))
    rejected_mitigations = _dedupe(_tuple_str(rejected_mitigation_codes))
    findings = _review_findings(
        preflight,
        decision=decision,
        review_scope=review_scope,
        reviewer_ref=reviewer_ref,
        network_egress_allowed=bool(network_egress_allowed),
        provider_send_allowed=bool(provider_send_allowed),
        credentials_allowed=bool(credentials_allowed),
        provider_client_allowed=bool(provider_client_allowed),
        endpoint_allowed=bool(endpoint_allowed),
        llm_call_allowed=bool(llm_call_allowed),
        semantic_generation_allowed=bool(semantic_generation_allowed),
        tool_calls_allowed=bool(tool_calls_allowed),
        memory_retrieval_allowed=bool(memory_retrieval_allowed),
        memory_write_allowed=bool(memory_write_allowed),
        retention_allowed=bool(retention_allowed),
        action_execution_allowed=bool(action_execution_allowed),
        routing_allowed=bool(routing_allowed),
        expired=expired,
    )
    status = _status(decision, findings, expired)
    receipt = ProviderNetworkEgressReviewReceipt(
        review_receipt_id="",
        review_status=status,
        network_preflight_id=str(data.get("preflight_id", "")),
        network_preflight_status=str(data.get("preflight_status", "")),
        network_preflight_digest=str(data.get("preflight_digest", "")),
        requested_ring=str(data.get("requested_ring", "")),
        effective_ring=str(data.get("effective_ring", "")),
        dry_run_id=str(data.get("dry_run_id", "")),
        dry_run_digest=str(data.get("dry_run_digest", "")),
        egress_review_receipt_id=str(data.get("egress_review_receipt_id", "")),
        egress_review_digest=str(data.get("egress_review_digest", "")),
        simulation_id=str(data.get("simulation_id", "")),
        simulation_digest=str(data.get("simulation_digest", "")),
        provider_family_label=str(data.get("provider_family_label", "")),
        model_family_label=str(data.get("model_family_label", "")),
        candidate_id=str(data.get("candidate_id", "")),
        candidate_digest=str(data.get("candidate_digest", "")),
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
        network_egress_allowed=bool(network_egress_allowed),
        provider_send_allowed=bool(provider_send_allowed),
        credentials_allowed=bool(credentials_allowed),
        provider_client_allowed=bool(provider_client_allowed),
        endpoint_allowed=bool(endpoint_allowed),
        llm_call_allowed=bool(llm_call_allowed),
        semantic_generation_allowed=bool(semantic_generation_allowed),
        tool_calls_allowed=bool(tool_calls_allowed),
        memory_retrieval_allowed=bool(memory_retrieval_allowed),
        memory_write_allowed=bool(memory_write_allowed),
        retention_allowed=bool(retention_allowed),
        action_execution_allowed=bool(action_execution_allowed),
        routing_allowed=bool(routing_allowed),
        expiration=expiration,
        expired=expired,
        forbidden_network_override_attempted=status == ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_FORBIDDEN_NETWORK_OVERRIDE_ATTEMPTED,
        findings=tuple(findings),
        rationale=str(rationale)[:1000],
        review_digest="",
    )
    digest = compute_provider_network_egress_review_digest(receipt)
    return replace(receipt, review_receipt_id=f"provider-network-egress-review:{receipt.network_preflight_id or 'missing'}:{digest[:16]}", review_digest=digest)


def build_provider_network_egress_review_receipt_from_preflight(
    preflight: ProviderNetworkEgressPreflight | Mapping[str, Any],
    **kwargs: Any,
) -> ProviderNetworkEgressReviewReceipt:
    return build_provider_network_egress_review_receipt(preflight, **kwargs)


def compute_provider_network_egress_review_digest(receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any]) -> str:
    data = dict(_mapping(receipt))
    data.pop("review_digest", None)
    data.pop("review_receipt_id", None)
    payload = {
        "review_status": data.get("review_status", ""),
        "network_preflight_id": data.get("network_preflight_id", ""),
        "network_preflight_status": data.get("network_preflight_status", ""),
        "network_preflight_digest": data.get("network_preflight_digest", ""),
        "requested_ring": data.get("requested_ring", ""),
        "effective_ring": data.get("effective_ring", ""),
        "dry_run_id": data.get("dry_run_id", ""),
        "dry_run_digest": data.get("dry_run_digest", ""),
        "egress_review_receipt_id": data.get("egress_review_receipt_id", ""),
        "egress_review_digest": data.get("egress_review_digest", ""),
        "simulation_id": data.get("simulation_id", ""),
        "simulation_digest": data.get("simulation_digest", ""),
        "provider_family_label": data.get("provider_family_label", ""),
        "model_family_label": data.get("model_family_label", ""),
        "candidate_id": data.get("candidate_id", ""),
        "candidate_digest": data.get("candidate_digest", ""),
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
        "forbidden_network_override_attempted": bool(data.get("forbidden_network_override_attempted", False)),
        "findings": _stable(data.get("findings", ())),
        "rationale": data.get("rationale", ""),
        "markers": {marker: bool(data.get(marker, False)) for marker in _MARKER_FIELDS},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _markers_true(receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return all(bool(data.get(marker, False)) for marker in _MARKER_FIELDS)


def _has_no_allowance(receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return all(data.get(field_name) is False for field_name in _ALLOWANCE_FIELDS)


def provider_network_egress_review_preserves_network_forbidden(receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data.get("network_egress_allowed") is False and data.get("network_egress_forbidden") is True and data.get("does_not_make_network_calls") is True)


def provider_network_egress_review_preserves_provider_forbidden(receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data.get("provider_send_allowed") is False and data.get("provider_send_forbidden") is True and data.get("does_not_send_to_provider") is True)


def provider_network_egress_review_has_no_credentials(receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("credentials_allowed") is False
        and data.get("provider_client_allowed") is False
        and data.get("endpoint_allowed") is False
        and data.get("credentials_forbidden") is True
        and data.get("provider_client_forbidden") is True
        and data.get("endpoint_forbidden") is True
    )


def provider_network_egress_review_has_no_runtime_authority(receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("llm_call_allowed") is False
        and data.get("semantic_generation_allowed") is False
        and data.get("tool_calls_allowed") is False
        and data.get("memory_retrieval_allowed") is False
        and data.get("memory_write_allowed") is False
        and data.get("retention_allowed") is False
        and data.get("action_execution_allowed") is False
        and data.get("routing_allowed") is False
        and data.get("llm_call_forbidden") is True
        and data.get("semantic_generation_forbidden") is True
        and data.get("does_not_call_llm") is True
        and data.get("does_not_retrieve_memory") is True
        and data.get("does_not_write_memory") is True
        and data.get("does_not_trigger_feedback") is True
        and data.get("does_not_commit_retention") is True
        and data.get("does_not_execute_or_route_work") is True
        and data.get("does_not_admit_work") is True
    )


def validate_provider_network_egress_review_receipt(receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any]) -> tuple[ProviderNetworkEgressReviewFinding, ...]:
    data = _mapping(receipt)
    findings: list[ProviderNetworkEgressReviewFinding] = []
    if not data:
        return (_finding("review_receipt_malformed", "provider network-egress review receipt is malformed"),)
    if not str(data.get("reviewer_ref", "")):
        findings.append(_finding("reviewer_ref_missing", "reviewer_ref is required"))
    if not _markers_true(receipt):
        findings.append(_finding("network_egress_review_marker_missing", "all provider network-egress review markers must be true"))
    for field_name in _ALLOWANCE_FIELDS:
        if bool(data.get(field_name, False)):
            findings.append(_finding("forbidden_allowance_requested", f"{field_name} must remain false"))
    if bool(data.get("expired", False)):
        findings.append(_finding("review_expired", "provider network-egress review receipt is expired"))
    if bool(data.get("forbidden_network_override_attempted", False)):
        findings.append(_finding("forbidden_network_override_attempted", "provider network-egress review attempted a forbidden network override"))
    expected = compute_provider_network_egress_review_digest(receipt)
    if str(data.get("review_digest", "")) != expected:
        findings.append(_finding("review_digest_mismatch", "review digest does not match receipt metadata"))
    return tuple(findings)


def provider_network_egress_review_attempts_forbidden_network_override(receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    non_overridable = {
        "forbidden_allowance_requested",
        "network_preflight_hard_denial_non_overridable",
        "network_preflight_not_ready_for_review",
        "network_preflight_future_gate_not_allowed",
        "digest_chain_incomplete_non_overridable",
        "requested_ring_unknown_non_overridable",
        "live_provider_send_ring_non_overridable",
        "review_scope_non_overridable",
        "network_forbidden_not_preserved",
        "provider_send_forbidden_not_preserved",
        "credentials_detected_non_overridable",
        "runtime_authority_detected_non_overridable",
        "preflight_forbidden_marker_finding_non_overridable",
    }
    return bool(
        data.get("forbidden_network_override_attempted", False)
        or data.get("review_status") == ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_FORBIDDEN_NETWORK_OVERRIDE_ATTEMPTED
        or any(_mapping(finding).get("code") in non_overridable for finding in data.get("findings", ()) or ())
    )


def _required_mitigations_addressed(receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    required = set(_tuple_str(data.get("required_mitigation_codes", ())))
    accepted = set(_tuple_str(data.get("accepted_mitigation_codes", ())))
    approved_constraints = set(_tuple_str(data.get("approved_constraint_codes", ())))
    rejected = set(_tuple_str(data.get("rejected_mitigation_codes", ()))) | set(_tuple_str(data.get("rejected_constraint_codes", ())))
    addressed = accepted | approved_constraints
    return required.isdisjoint(rejected) and required.issubset(addressed)


def provider_network_egress_review_satisfies_preflight(
    preflight: ProviderNetworkEgressPreflight | Mapping[str, Any],
    review_receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any] | None,
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
        ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_APPROVED,
        ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_APPROVED_WITH_CONSTRAINTS,
    }:
        return False
    if str(preflight_data.get("preflight_id", "")) != str(review_data.get("network_preflight_id", "")):
        return False
    if str(preflight_data.get("preflight_digest", "")) != str(review_data.get("network_preflight_digest", "")):
        return False
    if bool(review_data.get("expired", False)):
        return False
    if provider_network_egress_review_attempts_forbidden_network_override(review_receipt):
        return False
    if not provider_network_egress_preflight_allows_future_review_gate(preflight):
        return False
    if not _required_mitigations_addressed(review_receipt):
        return False
    return bool(
        _markers_true(review_receipt)
        and _has_no_allowance(review_receipt)
        and provider_network_egress_review_preserves_network_forbidden(review_receipt)
        and provider_network_egress_review_preserves_provider_forbidden(review_receipt)
        and provider_network_egress_review_has_no_credentials(review_receipt)
        and provider_network_egress_review_has_no_runtime_authority(review_receipt)
    )


def provider_network_egress_review_approves_future_review_gate(receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("review_status") == ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_APPROVED
        and data.get("review_scope") == ProviderNetworkEgressReviewScope.FUTURE_NETWORK_EGRESS_REVIEW_GATE
        and not data.get("expired", False)
        and not provider_network_egress_review_attempts_forbidden_network_override(receipt)
        and _markers_true(receipt)
        and _has_no_allowance(receipt)
        and _required_mitigations_addressed(receipt)
    )


def provider_network_egress_review_approves_future_dry_run_gate(receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("review_status") == ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_APPROVED_WITH_CONSTRAINTS
        and data.get("review_scope") == ProviderNetworkEgressReviewScope.FUTURE_PROVIDER_CALL_DRY_RUN_GATE
        and not data.get("expired", False)
        and not provider_network_egress_review_attempts_forbidden_network_override(receipt)
        and _markers_true(receipt)
        and _has_no_allowance(receipt)
        and _required_mitigations_addressed(receipt)
    )


def provider_network_egress_review_approves_future_null_transport_gate(receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("review_status") == ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_APPROVED_WITH_CONSTRAINTS
        and data.get("review_scope") == ProviderNetworkEgressReviewScope.FUTURE_TRANSPORT_NULL_ADAPTER_GATE
        and not data.get("expired", False)
        and not provider_network_egress_review_attempts_forbidden_network_override(receipt)
        and _markers_true(receipt)
        and _has_no_allowance(receipt)
        and _required_mitigations_addressed(receipt)
    )


def provider_network_egress_review_denies_network(receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("network_egress_allowed") is False
        and data.get("network_egress_forbidden") is True
        and data.get("does_not_make_network_calls") is True
        and str(data.get("review_status", "")) in {
            ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_APPROVED,
            ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_APPROVED_WITH_CONSTRAINTS,
            ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_REJECTED,
            ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_EXPIRED,
            ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_INVALID,
            ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_FORBIDDEN_NETWORK_OVERRIDE_ATTEMPTED,
            ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_NOT_APPLICABLE,
        }
    )


def explain_provider_network_egress_review_findings(receipt_or_findings: ProviderNetworkEgressReviewReceipt | Mapping[str, Any] | Sequence[ProviderNetworkEgressReviewFinding]) -> tuple[str, ...]:
    if isinstance(receipt_or_findings, Sequence) and not isinstance(receipt_or_findings, (str, bytes, Mapping)):
        findings = receipt_or_findings
    else:
        findings = _mapping(receipt_or_findings).get("findings", ()) or ()
    return tuple(f"{item.get('severity', '')}:{item.get('code', '')}:{item.get('detail', '')}" for item in (_mapping(finding) for finding in findings))


def summarize_provider_network_egress_review_receipt(receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(receipt)
    return {
        "review_receipt_id": str(data.get("review_receipt_id", "")),
        "review_status": str(data.get("review_status", "")),
        "network_preflight_id": str(data.get("network_preflight_id", "")),
        "network_preflight_status": str(data.get("network_preflight_status", "")),
        "network_preflight_digest": str(data.get("network_preflight_digest", "")),
        "reviewer_ref": str(data.get("reviewer_ref", "")),
        "review_scope": str(data.get("review_scope", "")),
        "decision": str(data.get("decision", "")),
        "required_mitigation_count": len(_tuple_str(data.get("required_mitigation_codes", ()))),
        "accepted_mitigation_count": len(_tuple_str(data.get("accepted_mitigation_codes", ()))),
        "rejected_mitigation_count": len(_tuple_str(data.get("rejected_mitigation_codes", ()))),
        "approved_constraint_count": len(_tuple_str(data.get("approved_constraint_codes", ()))),
        "rejected_constraint_count": len(_tuple_str(data.get("rejected_constraint_codes", ()))),
        "expired": bool(data.get("expired", False)),
        "forbidden_network_override_attempted": bool(data.get("forbidden_network_override_attempted", False)),
        "network_egress_allowed": bool(data.get("network_egress_allowed", False)),
        "provider_send_allowed": bool(data.get("provider_send_allowed", False)),
        "credentials_allowed": bool(data.get("credentials_allowed", False)),
        "provider_client_allowed": bool(data.get("provider_client_allowed", False)),
        "endpoint_allowed": bool(data.get("endpoint_allowed", False)),
        "llm_call_allowed": bool(data.get("llm_call_allowed", False)),
        "semantic_generation_allowed": bool(data.get("semantic_generation_allowed", False)),
        "runtime_allowance_allowed": any(bool(data.get(field_name, False)) for field_name in _ALLOWANCE_FIELDS if field_name not in {"network_egress_allowed", "provider_send_allowed", "credentials_allowed", "provider_client_allowed", "endpoint_allowed", "llm_call_allowed", "semantic_generation_allowed"}),
        "finding_count": len(tuple(data.get("findings", ()) or ())),
        "review_digest": str(data.get("review_digest", "")),
        "network_egress_review_receipt_only": bool(data.get("network_egress_review_receipt_only", False)),
        "future_network_gate_review_only": bool(data.get("future_network_gate_review_only", False)),
        "network_egress_forbidden": bool(data.get("network_egress_forbidden", False)),
        "provider_send_forbidden": bool(data.get("provider_send_forbidden", False)),
        "credentials_forbidden": bool(data.get("credentials_forbidden", False)),
        "provider_client_forbidden": bool(data.get("provider_client_forbidden", False)),
        "endpoint_forbidden": bool(data.get("endpoint_forbidden", False)),
        "llm_call_forbidden": bool(data.get("llm_call_forbidden", False)),
        "semantic_generation_forbidden": bool(data.get("semantic_generation_forbidden", False)),
        "does_not_call_llm": bool(data.get("does_not_call_llm", False)),
        "does_not_send_to_provider": bool(data.get("does_not_send_to_provider", False)),
        "does_not_make_network_calls": bool(data.get("does_not_make_network_calls", False)),
    }
