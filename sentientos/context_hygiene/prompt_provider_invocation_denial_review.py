from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_provider_invocation_readiness import (
    ProviderInvocationPreflightStatus,
    ProviderInvocationReadinessAuditChain,
    ProviderInvocationReadinessManifest,
    ProviderInvocationReadinessPreflight,
    ProviderInvocationReadinessStatus,
    compute_provider_invocation_readiness_digest,
    compute_provider_invocation_readiness_preflight_digest,
    provider_invocation_preflight_remains_metadata_only,
    provider_invocation_readiness_digest_chain_complete,
    provider_invocation_readiness_forbids_invocation,
    provider_invocation_readiness_has_no_clients,
    provider_invocation_readiness_has_no_credentials,
    provider_invocation_readiness_has_no_endpoints,
    provider_invocation_readiness_has_no_network,
    provider_invocation_readiness_has_no_runtime_authority,
)


class ProviderInvocationDenialReviewStatus:
    INVOCATION_DENIAL_REVIEW_ACCEPTED = "invocation_denial_review_accepted"
    INVOCATION_DENIAL_REVIEW_ACCEPTED_WITH_CONDITIONS = "invocation_denial_review_accepted_with_conditions"
    INVOCATION_DENIAL_REVIEW_REJECTED = "invocation_denial_review_rejected"
    INVOCATION_DENIAL_REVIEW_EXPIRED = "invocation_denial_review_expired"
    INVOCATION_DENIAL_REVIEW_INVALID = "invocation_denial_review_invalid"
    INVOCATION_DENIAL_REVIEW_FORBIDDEN_INVOCATION_OVERRIDE_ATTEMPTED = "invocation_denial_review_forbidden_invocation_override_attempted"
    INVOCATION_DENIAL_REVIEW_NOT_APPLICABLE = "invocation_denial_review_not_applicable"


class ProviderInvocationDenialReviewDecision:
    AFFIRM_INVOCATION_FORBIDDEN = "affirm_invocation_forbidden"
    AFFIRM_METADATA_ONLY_NOT_INVOCABLE = "affirm_metadata_only_not_invocable"
    APPROVE_FUTURE_EXTERNAL_SECURITY_REVIEW_GATE = "approve_future_external_security_review_gate"
    APPROVE_FUTURE_INVOCATION_DENIAL_AUDIT_GATE = "approve_future_invocation_denial_audit_gate"
    APPROVE_WITH_CONDITIONS = "approve_with_conditions"
    REJECT_READINESS_POSTURE = "reject_readiness_posture"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"
    NO_DECISION = "no_decision"


class ProviderInvocationDenialReviewScope:
    INVOCATION_DENIAL_REVIEW_GATE = "invocation_denial_review_gate"
    FUTURE_EXTERNAL_SECURITY_REVIEW_GATE = "future_external_security_review_gate"
    FUTURE_INVOCATION_DENIAL_AUDIT_GATE = "future_invocation_denial_audit_gate"
    ACTUAL_PROVIDER_INVOCATION_FORBIDDEN = "actual_provider_invocation_forbidden"
    ACTUAL_PROVIDER_SEND_FORBIDDEN = "actual_provider_send_forbidden"
    NETWORK_EGRESS_FORBIDDEN = "network_egress_forbidden"
    CREDENTIAL_USE_FORBIDDEN = "credential_use_forbidden"
    ENDPOINT_USE_FORBIDDEN = "endpoint_use_forbidden"
    PROVIDER_CLIENT_USE_FORBIDDEN = "provider_client_use_forbidden"
    PROVIDER_SDK_USE_FORBIDDEN = "provider_sdk_use_forbidden"
    TOOL_OR_ACTION_FORBIDDEN = "tool_or_action_forbidden"
    EXTERNAL_USER_VISIBLE_FORBIDDEN = "external_user_visible_forbidden"


@dataclass(frozen=True)
class ProviderInvocationDenialReviewFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderInvocationDenialReviewConstraint:
    code: str
    detail: str
    required: bool = True


@dataclass(frozen=True)
class ProviderInvocationDenialReviewExpiration:
    reviewed_at: str = ""
    expires_at: str = ""
    ttl_seconds: int = 0
    evaluated_at: str = ""


@dataclass(frozen=True)
class ProviderInvocationDenialReviewAuditChain:
    readiness_id: str = ""
    readiness_digest: str = ""
    readiness_preflight_id: str = ""
    readiness_preflight_digest: str = ""
    readiness_chain_complete: bool = False
    readiness_preflight_chain_complete: bool = False
    complete: bool = False
    mismatches: tuple[str, ...] = field(default_factory=tuple)
    missing: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProviderInvocationDenialReviewReceipt:
    review_receipt_id: str
    review_status: str
    readiness_id: str
    readiness_status: str
    readiness_digest: str
    readiness_preflight_id: str
    readiness_preflight_status: str
    readiness_preflight_digest: str
    audit_chain: ProviderInvocationDenialReviewAuditChain
    digest_chain_complete: bool
    reviewer_ref: str
    review_scope: str
    decision: str
    approved_constraint_codes: tuple[str, ...]
    rejected_constraint_codes: tuple[str, ...]
    accepted_gap_codes: tuple[str, ...]
    rejected_gap_codes: tuple[str, ...]
    accepted_denial_codes: tuple[str, ...]
    rejected_denial_codes: tuple[str, ...]
    invocation_allowed: bool = False
    provider_send_allowed: bool = False
    credential_use_allowed: bool = False
    endpoint_use_allowed: bool = False
    client_use_allowed: bool = False
    network_access_allowed: bool = False
    dns_allowed: bool = False
    socket_allowed: bool = False
    http_allowed: bool = False
    provider_sdk_allowed: bool = False
    semantic_generation_allowed: bool = False
    tool_calls_allowed: bool = False
    memory_retrieval_allowed: bool = False
    memory_write_allowed: bool = False
    retention_allowed: bool = False
    action_execution_allowed: bool = False
    routing_allowed: bool = False
    expiration: ProviderInvocationDenialReviewExpiration = field(default_factory=ProviderInvocationDenialReviewExpiration)
    expired: bool = False
    forbidden_invocation_override_attempted: bool = False
    findings: tuple[ProviderInvocationDenialReviewFinding, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    constraints: tuple[ProviderInvocationDenialReviewConstraint, ...] = field(default_factory=tuple)
    rationale: str = ""
    review_digest: str = ""
    provider_invocation_denial_review_receipt_only: bool = True
    provider_invocation_forbidden: bool = True
    metadata_only_not_invocable: bool = True
    future_security_review_gate_only: bool = True
    actual_provider_invocation_forbidden: bool = True
    credential_use_forbidden: bool = True
    endpoint_use_forbidden: bool = True
    provider_client_use_forbidden: bool = True
    network_access_forbidden: bool = True
    provider_send_forbidden: bool = True
    live_provider_transport_forbidden: bool = True
    live_prompt_assembly_forbidden: bool = True
    live_model_call_forbidden: bool = True
    does_not_import_provider_sdks: bool = True
    does_not_create_clients: bool = True
    does_not_create_sessions: bool = True
    does_not_create_transports: bool = True
    does_not_open_streams: bool = True
    does_not_resolve_dns: bool = True
    does_not_read_environment: bool = True
    does_not_read_files: bool = True
    does_not_access_config_stores: bool = True
    does_not_access_vaults: bool = True
    does_not_access_keychains: bool = True
    does_not_access_cloud_secrets: bool = True
    does_not_make_network_calls: bool = True
    does_not_send_to_provider: bool = True
    does_not_call_llm: bool = True
    does_not_open_sockets: bool = True
    does_not_make_http_requests: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True


_ACCEPT_DECISIONS = frozenset(
    {
        ProviderInvocationDenialReviewDecision.AFFIRM_INVOCATION_FORBIDDEN,
        ProviderInvocationDenialReviewDecision.AFFIRM_METADATA_ONLY_NOT_INVOCABLE,
        ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_EXTERNAL_SECURITY_REVIEW_GATE,
        ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_INVOCATION_DENIAL_AUDIT_GATE,
        ProviderInvocationDenialReviewDecision.APPROVE_WITH_CONDITIONS,
    }
)
_REJECT_DECISIONS = frozenset(
    {
        ProviderInvocationDenialReviewDecision.REJECT_READINESS_POSTURE,
        ProviderInvocationDenialReviewDecision.REQUEST_MORE_EVIDENCE,
    }
)
_ALLOWED_DECISIONS = _ACCEPT_DECISIONS | _REJECT_DECISIONS | {ProviderInvocationDenialReviewDecision.NO_DECISION}
_ALLOWED_SCOPES = frozenset(
    {
        ProviderInvocationDenialReviewScope.INVOCATION_DENIAL_REVIEW_GATE,
        ProviderInvocationDenialReviewScope.FUTURE_EXTERNAL_SECURITY_REVIEW_GATE,
        ProviderInvocationDenialReviewScope.FUTURE_INVOCATION_DENIAL_AUDIT_GATE,
        ProviderInvocationDenialReviewScope.ACTUAL_PROVIDER_INVOCATION_FORBIDDEN,
        ProviderInvocationDenialReviewScope.ACTUAL_PROVIDER_SEND_FORBIDDEN,
        ProviderInvocationDenialReviewScope.NETWORK_EGRESS_FORBIDDEN,
        ProviderInvocationDenialReviewScope.CREDENTIAL_USE_FORBIDDEN,
        ProviderInvocationDenialReviewScope.ENDPOINT_USE_FORBIDDEN,
        ProviderInvocationDenialReviewScope.PROVIDER_CLIENT_USE_FORBIDDEN,
        ProviderInvocationDenialReviewScope.PROVIDER_SDK_USE_FORBIDDEN,
        ProviderInvocationDenialReviewScope.TOOL_OR_ACTION_FORBIDDEN,
        ProviderInvocationDenialReviewScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
    }
)
_FUTURE_SCOPES = frozenset(
    {
        ProviderInvocationDenialReviewScope.INVOCATION_DENIAL_REVIEW_GATE,
        ProviderInvocationDenialReviewScope.FUTURE_EXTERNAL_SECURITY_REVIEW_GATE,
        ProviderInvocationDenialReviewScope.FUTURE_INVOCATION_DENIAL_AUDIT_GATE,
    }
)
_FORBIDDEN_SCOPES = _ALLOWED_SCOPES - _FUTURE_SCOPES
_ACCEPTABLE_READINESS_STATUSES = frozenset(
    {
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_NULL_ONLY_METADATA,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_FORBIDDEN,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_MISSING_EVIDENCE,
    }
)
_ACCEPTABLE_PREFLIGHT_STATUSES = frozenset(
    {
        ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_METADATA_ONLY_NOT_INVOCABLE,
        ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_DENIED,
        ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_FORBIDDEN,
        ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_MISSING_EVIDENCE,
    }
)
_DIRTY_READINESS_STATUSES = frozenset(
    {
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_CREDENTIALS_DETECTED,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_ENDPOINT_DETECTED,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_CLIENT_DETECTED,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_NETWORK_DETECTED,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_RUNTIME_AUTHORITY_DETECTED,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_INVALID,
    }
)
_DIRTY_PREFLIGHT_STATUSES = frozenset(
    {
        ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_CREDENTIALS_DETECTED,
        ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_ENDPOINT_DETECTED,
        ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_CLIENT_DETECTED,
        ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_NETWORK_DETECTED,
        ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED,
        ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_INVALID_INPUT,
    }
)
_ALLOWANCE_FIELDS = (
    "invocation_allowed",
    "provider_send_allowed",
    "credential_use_allowed",
    "endpoint_use_allowed",
    "client_use_allowed",
    "network_access_allowed",
    "dns_allowed",
    "socket_allowed",
    "http_allowed",
    "provider_sdk_allowed",
    "semantic_generation_allowed",
    "tool_calls_allowed",
    "memory_retrieval_allowed",
    "memory_write_allowed",
    "retention_allowed",
    "action_execution_allowed",
    "routing_allowed",
)
_MARKER_FIELDS = (
    "provider_invocation_denial_review_receipt_only",
    "provider_invocation_forbidden",
    "metadata_only_not_invocable",
    "future_security_review_gate_only",
    "actual_provider_invocation_forbidden",
    "credential_use_forbidden",
    "endpoint_use_forbidden",
    "provider_client_use_forbidden",
    "network_access_forbidden",
    "provider_send_forbidden",
    "live_provider_transport_forbidden",
    "live_prompt_assembly_forbidden",
    "live_model_call_forbidden",
    "does_not_import_provider_sdks",
    "does_not_create_clients",
    "does_not_create_sessions",
    "does_not_create_transports",
    "does_not_open_streams",
    "does_not_resolve_dns",
    "does_not_read_environment",
    "does_not_read_files",
    "does_not_access_config_stores",
    "does_not_access_vaults",
    "does_not_access_keychains",
    "does_not_access_cloud_secrets",
    "does_not_make_network_calls",
    "does_not_send_to_provider",
    "does_not_call_llm",
    "does_not_open_sockets",
    "does_not_make_http_requests",
    "does_not_retrieve_memory",
    "does_not_write_memory",
    "does_not_trigger_feedback",
    "does_not_commit_retention",
    "does_not_execute_or_route_work",
    "does_not_admit_work",
)
_BASE_DENIAL_CODES = (
    "denial:provider_invocation_forbidden",
    "denial:metadata_only_not_invocable",
    "denial:provider_send_forbidden",
    "denial:credential_use_forbidden",
    "denial:endpoint_use_forbidden",
    "denial:provider_client_use_forbidden",
    "denial:network_access_forbidden",
    "denial:runtime_authority_forbidden",
)
_BASE_CONSTRAINT_CODES = (
    "constraint:invocation_denial_review_receipt_only",
    "constraint:future_security_review_gate_only",
    "constraint:no_provider_invocation",
    "constraint:no_provider_send",
    "constraint:no_credentials_endpoints_clients_network",
    "constraint:no_semantic_generation_tools_memory_retention_actions_routing",
)
_PROMPT_RAW_RUNTIME_MARKERS = (
    "approve invocation",
    "invocation approved",
    "provider invocation allowed",
    "provider send",
    "send_to_provider",
    "network egress",
    "socket",
    "http",
    "dns",
    "resolve",
    "connect",
    "endpoint",
    "base_url",
    "host",
    "port",
    "url",
    "credential",
    "api_key",
    "bearer",
    "token",
    "secret",
    "auth",
    "client",
    "session",
    "transport",
    "stream",
    "retry",
    "request builder",
    "openai",
    "anthropic",
    "provider sdk",
    "completion",
    "chat.completions",
    "model output",
    "semantic generation",
    "tool call",
    "action",
    "retention",
    "routing",
    "memory write",
    "raw payload",
    "runtime handle",
)
_NEGATIVE_TOKENS = (
    "forbidden",
    "does_not_",
    "does not",
    "no_",
    "no ",
    "not_invocable",
    "not invocable",
    "denial",
    "denied",
    "metadata_only_not_invocable",
    "allowed=false",
    "allowed false",
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


def _stable_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(_stable(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _digest_payload(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> Mapping[str, Any]:
    data = dict(_mapping(receipt))
    data.pop("review_receipt_id", None)
    data.pop("review_digest", None)
    return data


def compute_provider_invocation_denial_review_digest(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> str:
    return _stable_digest(_digest_payload(receipt))


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


def _finding(code: str, detail: str, severity: str = "blocker") -> ProviderInvocationDenialReviewFinding:
    return ProviderInvocationDenialReviewFinding(code=code, detail=detail, severity=severity)


def _constraint(code: str, detail: str, required: bool = True) -> ProviderInvocationDenialReviewConstraint:
    return ProviderInvocationDenialReviewConstraint(code=code, detail=detail, required=required)


def _constraints() -> tuple[ProviderInvocationDenialReviewConstraint, ...]:
    return (
        _constraint("invocation_denial_review_receipt_only", "Phase 96 records review metadata only; it is not invocation approval."),
        _constraint("future_security_review_gate_only", "Future external security review or denial-audit gates remain metadata-only."),
        _constraint("provider_invocation_forbidden", "Actual provider invocation and provider send remain forbidden."),
        _constraint("no_runtime_authority", "No credentials, endpoints, clients, SDKs, network, semantic generation, tools, memory, retention, actions, routing, admission, execution, or orchestration are permitted."),
    )


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _expiration(expires_at: str | None, ttl_seconds: int | None, reviewed_at: str | None, evaluated_at: str | None) -> ProviderInvocationDenialReviewExpiration:
    reviewed = reviewed_at or "1970-01-01T00:00:00Z"
    ttl = int(ttl_seconds or 0)
    expiry = expires_at or ""
    if not expiry and ttl > 0:
        base = _parse_time(reviewed) or datetime(1970, 1, 1, tzinfo=timezone.utc)
        expiry = _format_time(base + timedelta(seconds=ttl))
    return ProviderInvocationDenialReviewExpiration(reviewed_at=reviewed, expires_at=expiry, ttl_seconds=ttl, evaluated_at=evaluated_at or reviewed)


def _is_expired(expiration: ProviderInvocationDenialReviewExpiration) -> bool:
    expires = _parse_time(expiration.expires_at)
    evaluated = _parse_time(expiration.evaluated_at)
    return bool(expires and evaluated and evaluated >= expires)


def _code_from_text(prefix: str, text: str) -> str:
    normalized = "_".join(str(text).lower().strip().replace(":", " ").split())
    normalized = "".join(char if char.isalnum() or char == "_" else "_" for char in normalized).strip("_")
    if normalized:
        return f"{prefix}:{normalized[:80]}"
    digest = hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"


def _contains_forbidden_marker(value: Any) -> bool:
    text = json.dumps(_stable(value), sort_keys=True, ensure_ascii=True, default=str).lower().replace('"', " ")
    for marker in _PROMPT_RAW_RUNTIME_MARKERS:
        index = text.find(marker)
        while index >= 0:
            window = text[max(0, index - 48) : index + len(marker) + 48]
            if not any(token in window for token in _NEGATIVE_TOKENS):
                return True
            index = text.find(marker, index + 1)
    return False


def _readiness_digest(readiness: ProviderInvocationReadinessManifest | Mapping[str, Any]) -> str:
    data = _mapping(readiness)
    if not data:
        return ""
    try:
        return compute_provider_invocation_readiness_digest(readiness)
    except Exception:
        return str(data.get("readiness_digest", ""))


def _preflight_digest(preflight: ProviderInvocationReadinessPreflight | Mapping[str, Any]) -> str:
    data = _mapping(preflight)
    if not data:
        return ""
    try:
        return compute_provider_invocation_readiness_preflight_digest(preflight)
    except Exception:
        return str(data.get("invocation_preflight_digest", ""))


def _normalize_gap_items(items: Any) -> tuple[str, ...]:
    codes: list[str] = []
    for item in items or ():
        data = _mapping(item)
        if data:
            code = str(data.get("code", ""))
            detail = str(data.get("detail", ""))
            if code:
                codes.append(f"gap:{code}")
            elif detail:
                codes.append(_code_from_text("gap", detail))
        elif str(item):
            codes.append(_code_from_text("gap", str(item)))
    return _dedupe(codes)


def _normalize_finding_items(items: Any, prefix: str = "finding") -> tuple[str, ...]:
    codes: list[str] = []
    for item in items or ():
        data = _mapping(item)
        if data:
            code = str(data.get("code", ""))
            detail = str(data.get("detail", ""))
            if code:
                codes.append(f"{prefix}:{code}")
            elif detail:
                codes.append(_code_from_text(prefix, detail))
        elif str(item):
            codes.append(_code_from_text(prefix, str(item)))
    return _dedupe(codes)


def _normalize_constraint_items(items: Any) -> tuple[str, ...]:
    codes: list[str] = []
    for item in items or ():
        data = _mapping(item)
        if data:
            code = str(data.get("code", ""))
            detail = str(data.get("detail", ""))
            if code:
                codes.append(f"constraint:{code}")
            elif detail:
                codes.append(_code_from_text("constraint", detail))
        elif str(item):
            codes.append(_code_from_text("constraint", str(item)))
    return _dedupe(codes)


def _audit_chain(readiness: ProviderInvocationReadinessManifest | Mapping[str, Any], preflight: ProviderInvocationReadinessPreflight | Mapping[str, Any]) -> ProviderInvocationDenialReviewAuditChain:
    rdata = _mapping(readiness)
    pdata = _mapping(preflight)
    missing: list[str] = []
    mismatches: list[str] = []
    if not rdata:
        missing.append("readiness_manifest")
    if not pdata:
        missing.append("readiness_preflight")
    readiness_id = str(rdata.get("invocation_readiness_id", ""))
    readiness_digest = str(rdata.get("readiness_digest", ""))
    preflight_id = str(pdata.get("invocation_preflight_id", ""))
    preflight_digest = str(pdata.get("invocation_preflight_digest", ""))
    if rdata and not readiness_id:
        missing.append("readiness_id")
    if rdata and not readiness_digest:
        missing.append("readiness_digest")
    if pdata and not preflight_id:
        missing.append("readiness_preflight_id")
    if pdata and not preflight_digest:
        missing.append("readiness_preflight_digest")
    if rdata and readiness_digest and _readiness_digest(readiness) != readiness_digest:
        mismatches.append("readiness_digest")
    if pdata and preflight_digest and _preflight_digest(preflight) != preflight_digest:
        mismatches.append("readiness_preflight_digest")
    if rdata and pdata and readiness_id != str(pdata.get("invocation_readiness_id", "")):
        mismatches.append("readiness_id")
    if rdata and pdata and readiness_digest != str(pdata.get("readiness_digest", "")):
        mismatches.append("readiness_digest_link")
    readiness_chain_complete = bool(rdata.get("digest_chain_complete") is True and provider_invocation_readiness_digest_chain_complete(readiness))
    preflight_chain_complete = bool(pdata.get("digest_chain_complete") is True and not mismatches and not missing)
    return ProviderInvocationDenialReviewAuditChain(
        readiness_id=readiness_id,
        readiness_digest=readiness_digest,
        readiness_preflight_id=preflight_id,
        readiness_preflight_digest=preflight_digest,
        readiness_chain_complete=readiness_chain_complete,
        readiness_preflight_chain_complete=preflight_chain_complete,
        complete=bool(readiness_chain_complete and preflight_chain_complete and not missing and not mismatches),
        mismatches=tuple(mismatches),
        missing=tuple(missing),
    )


def extract_required_provider_invocation_denial_review_codes(
    readiness: ProviderInvocationReadinessManifest | Mapping[str, Any],
    preflight: ProviderInvocationReadinessPreflight | Mapping[str, Any],
) -> Mapping[str, tuple[str, ...]]:
    rdata = _mapping(readiness)
    pdata = _mapping(preflight)
    gap_codes: list[str] = []
    denial_codes: list[str] = list(_BASE_DENIAL_CODES)
    constraint_codes: list[str] = list(_BASE_CONSTRAINT_CODES)
    if rdata.get("readiness_status") != ProviderInvocationReadinessStatus.INVOCATION_READINESS_NULL_ONLY_METADATA:
        gap_codes.extend(_normalize_gap_items(rdata.get("readiness_gaps", ())))
    for missing in _tuple_str(rdata.get("missing_required_evidence", ())) + _tuple_str(pdata.get("missing_required_evidence", ())) :
        gap_codes.append(f"gap:missing_{missing}")
    gap_codes.extend(_normalize_finding_items(rdata.get("findings", ()), "readiness_finding"))
    gap_codes.extend(_normalize_finding_items(pdata.get("findings", ()), "preflight_finding"))
    constraint_codes.extend(_normalize_constraint_items(rdata.get("constraints", ())))
    constraint_codes.extend(_normalize_constraint_items(pdata.get("constraints", ())))
    if rdata.get("digest_chain_complete") is not True or pdata.get("digest_chain_complete") is not True:
        gap_codes.append("gap:digest_chain_incomplete")
    audit = _audit_chain(readiness, preflight)
    for missing in audit.missing:
        gap_codes.append(f"gap:audit_missing_{missing}")
    for mismatch in audit.mismatches:
        gap_codes.append(f"gap:audit_mismatch_{mismatch}")
    if rdata.get("provider_invocation_forbidden") is True or pdata.get("provider_invocation_forbidden") is True:
        denial_codes.append("denial:provider_invocation_forbidden_marker_present")
    if rdata.get("metadata_only_not_invocable") is True or pdata.get("metadata_only_not_invocable") is True:
        denial_codes.append("denial:metadata_only_not_invocable_marker_present")
    if rdata.get("readiness_status") == ProviderInvocationReadinessStatus.INVOCATION_READINESS_NULL_ONLY_METADATA:
        denial_codes.append("denial:clean_null_only_metadata")
    if str(pdata.get("invocation_preflight_status", "")) in {
        ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_METADATA_ONLY_NOT_INVOCABLE,
        ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_DENIED,
        ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_FORBIDDEN,
        ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_MISSING_EVIDENCE,
    }:
        denial_codes.append(f"denial:{pdata.get('invocation_preflight_status')}")
    return {
        "gap_codes": _dedupe(gap_codes),
        "denial_codes": _dedupe(denial_codes),
        "constraint_codes": _dedupe(constraint_codes),
    }


def _review_findings(
    readiness: ProviderInvocationReadinessManifest | Mapping[str, Any],
    preflight: ProviderInvocationReadinessPreflight | Mapping[str, Any],
    *,
    decision: str,
    review_scope: str,
    reviewer_ref: str,
    accepted_gap_codes: Sequence[str],
    rejected_gap_codes: Sequence[str],
    accepted_denial_codes: Sequence[str],
    rejected_denial_codes: Sequence[str],
    approved_constraint_codes: Sequence[str],
    rejected_constraint_codes: Sequence[str],
    allowance_flags: Mapping[str, bool],
    expired: bool,
    rationale: str,
) -> tuple[ProviderInvocationDenialReviewFinding, ...]:
    rdata = _mapping(readiness)
    pdata = _mapping(preflight)
    findings: list[ProviderInvocationDenialReviewFinding] = []
    audit = _audit_chain(readiness, preflight)
    approving = decision in _ACCEPT_DECISIONS
    if not rdata:
        findings.append(_finding("readiness_manifest_missing", "Phase 95 ProviderInvocationReadinessManifest metadata is required"))
    if not pdata:
        findings.append(_finding("readiness_preflight_missing", "Phase 95 ProviderInvocationReadinessPreflight metadata is required"))
    if not reviewer_ref:
        findings.append(_finding("reviewer_ref_missing", "reviewer_ref is required for invocation-denial review receipt"))
    if decision not in _ALLOWED_DECISIONS:
        findings.append(_finding("decision_unknown", "invocation-denial review decision is not recognized"))
    if review_scope not in _ALLOWED_SCOPES:
        findings.append(_finding("review_scope_unknown", "invocation-denial review scope is not recognized"))
    if expired:
        findings.append(_finding("review_expired", "invocation-denial review receipt is expired"))
    if approving and review_scope in _FORBIDDEN_SCOPES:
        findings.append(_finding("review_scope_non_overridable", f"scope {review_scope!r} cannot be approved in Phase 96"))
    if approving and str(rdata.get("readiness_status", "")) in _DIRTY_READINESS_STATUSES:
        findings.append(_finding("readiness_dirty_evidence_non_overridable", f"readiness status {rdata.get('readiness_status')!r} cannot be approved"))
    if approving and str(pdata.get("invocation_preflight_status", "")) in _DIRTY_PREFLIGHT_STATUSES:
        findings.append(_finding("preflight_dirty_evidence_non_overridable", f"preflight status {pdata.get('invocation_preflight_status')!r} cannot be approved"))
    if approving and str(rdata.get("readiness_status", "")) not in _ACCEPTABLE_READINESS_STATUSES:
        findings.append(_finding("readiness_status_not_denial_reviewable", "only null-only metadata or denial/missing-evidence posture can be reviewed as denial-only"))
    if approving and str(pdata.get("invocation_preflight_status", "")) not in _ACCEPTABLE_PREFLIGHT_STATUSES:
        findings.append(_finding("preflight_status_not_denial_reviewable", "only metadata-only-not-invocable or denial posture can be reviewed as denial-only"))
    if approving and (audit.missing or audit.mismatches):
        findings.append(_finding("digest_chain_incomplete_non_overridable", "readiness/preflight audit chain is missing or mismatched"))
    if approving and not provider_invocation_readiness_forbids_invocation(readiness):
        findings.append(_finding("readiness_invocation_forbidden_not_preserved", "readiness provider-invocation-forbidden markers cannot be overridden"))
    if approving and not provider_invocation_readiness_forbids_invocation(preflight):
        findings.append(_finding("preflight_invocation_forbidden_not_preserved", "preflight provider-invocation-forbidden markers cannot be overridden"))
    if approving and not provider_invocation_readiness_has_no_credentials(readiness):
        findings.append(_finding("readiness_credentials_detected_non_overridable", "readiness credential markers cannot be approved"))
    if approving and not provider_invocation_readiness_has_no_endpoints(readiness):
        findings.append(_finding("readiness_endpoints_detected_non_overridable", "readiness endpoint markers cannot be approved"))
    if approving and not provider_invocation_readiness_has_no_clients(readiness):
        findings.append(_finding("readiness_clients_detected_non_overridable", "readiness client markers cannot be approved"))
    if approving and not provider_invocation_readiness_has_no_network(readiness):
        findings.append(_finding("readiness_network_detected_non_overridable", "readiness network markers cannot be approved"))
    if approving and not provider_invocation_readiness_has_no_runtime_authority(readiness):
        findings.append(_finding("readiness_runtime_authority_detected_non_overridable", "readiness runtime authority cannot be approved"))
    if approving and not provider_invocation_readiness_has_no_runtime_authority(preflight):
        findings.append(_finding("preflight_runtime_authority_detected_non_overridable", "preflight runtime authority cannot be approved"))
    for field_name, allowed in allowance_flags.items():
        if allowed:
            findings.append(_finding("forbidden_allowance_requested", f"{field_name} must remain false in Phase 96"))
    if approving and (_contains_forbidden_marker(rdata.get("findings", ())) or _contains_forbidden_marker(pdata.get("findings", ())) or _contains_forbidden_marker(rationale)):
        findings.append(_finding("forbidden_marker_non_overridable", "review metadata references non-overridable provider/runtime/secret/endpoint/client/network marker evidence"))
    required = extract_required_provider_invocation_denial_review_codes(readiness, preflight)
    accepted_gaps = set(_tuple_str(accepted_gap_codes))
    rejected_gaps = set(_tuple_str(rejected_gap_codes))
    accepted_denials = set(_tuple_str(accepted_denial_codes))
    rejected_denials = set(_tuple_str(rejected_denial_codes))
    approved_constraints = set(_tuple_str(approved_constraint_codes))
    rejected_constraints = set(_tuple_str(rejected_constraint_codes))
    required_gap_codes = set(required["gap_codes"])
    required_denial_codes = set(required["denial_codes"])
    required_constraint_codes = set(required["constraint_codes"])
    if approving and required_gap_codes.intersection(rejected_gaps):
        findings.append(_finding("required_gap_code_rejected", "a required readiness/preflight gap code was rejected"))
    if approving and required_denial_codes.intersection(rejected_denials):
        findings.append(_finding("required_denial_code_rejected", "a required denial posture code was rejected"))
    if approving and required_constraint_codes.intersection(rejected_constraints):
        findings.append(_finding("required_constraint_code_rejected", "a required invocation-denial constraint code was rejected"))
    if approving and not required_gap_codes.issubset(accepted_gaps):
        missing = tuple(sorted(required_gap_codes - accepted_gaps))
        if missing:
            findings.append(_finding("required_gap_code_not_accepted", f"required gap codes not accepted: {', '.join(missing[:5])}"))
    if approving and not required_denial_codes.issubset(accepted_denials):
        findings.append(_finding("required_denial_code_not_accepted", "all required denial posture codes must be accepted"))
    if approving and not required_constraint_codes.issubset(approved_constraints):
        findings.append(_finding("required_constraint_code_not_approved", "all required invocation-denial constraints must be approved"))
    return tuple(findings)


def _status(decision: str, findings: Sequence[ProviderInvocationDenialReviewFinding], expired: bool) -> str:
    codes = {finding.code for finding in findings}
    if expired:
        return ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_EXPIRED
    if any(code in codes for code in {"readiness_manifest_missing", "readiness_preflight_missing", "reviewer_ref_missing", "decision_unknown", "review_scope_unknown"}):
        return ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_INVALID
    non_overridable = {
        "review_scope_non_overridable",
        "readiness_dirty_evidence_non_overridable",
        "preflight_dirty_evidence_non_overridable",
        "readiness_status_not_denial_reviewable",
        "preflight_status_not_denial_reviewable",
        "digest_chain_incomplete_non_overridable",
        "readiness_invocation_forbidden_not_preserved",
        "preflight_invocation_forbidden_not_preserved",
        "readiness_credentials_detected_non_overridable",
        "readiness_endpoints_detected_non_overridable",
        "readiness_clients_detected_non_overridable",
        "readiness_network_detected_non_overridable",
        "readiness_runtime_authority_detected_non_overridable",
        "preflight_runtime_authority_detected_non_overridable",
        "forbidden_allowance_requested",
        "forbidden_marker_non_overridable",
    }
    if codes.intersection(non_overridable) and decision in _ACCEPT_DECISIONS:
        return ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_FORBIDDEN_INVOCATION_OVERRIDE_ATTEMPTED
    if findings and decision in _ACCEPT_DECISIONS:
        return ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_INVALID
    if decision in {
        ProviderInvocationDenialReviewDecision.AFFIRM_INVOCATION_FORBIDDEN,
        ProviderInvocationDenialReviewDecision.AFFIRM_METADATA_ONLY_NOT_INVOCABLE,
    }:
        return ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_ACCEPTED
    if decision in {
        ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_EXTERNAL_SECURITY_REVIEW_GATE,
        ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_INVOCATION_DENIAL_AUDIT_GATE,
        ProviderInvocationDenialReviewDecision.APPROVE_WITH_CONDITIONS,
    }:
        return ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_ACCEPTED_WITH_CONDITIONS
    if decision in _REJECT_DECISIONS:
        return ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_REJECTED
    return ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_NOT_APPLICABLE


def build_provider_invocation_denial_review_receipt(
    readiness: ProviderInvocationReadinessManifest | Mapping[str, Any],
    preflight: ProviderInvocationReadinessPreflight | Mapping[str, Any],
    *,
    reviewer_ref: str,
    decision: str,
    review_scope: str = ProviderInvocationDenialReviewScope.INVOCATION_DENIAL_REVIEW_GATE,
    approved_constraint_codes: Sequence[str] = (),
    rejected_constraint_codes: Sequence[str] = (),
    accepted_gap_codes: Sequence[str] = (),
    rejected_gap_codes: Sequence[str] = (),
    accepted_denial_codes: Sequence[str] = (),
    rejected_denial_codes: Sequence[str] = (),
    rationale: str = "",
    expires_at: str | None = None,
    ttl_seconds: int | None = None,
    reviewed_at: str | None = None,
    evaluated_at: str | None = None,
    invocation_allowed: bool = False,
    provider_send_allowed: bool = False,
    credential_use_allowed: bool = False,
    endpoint_use_allowed: bool = False,
    client_use_allowed: bool = False,
    network_access_allowed: bool = False,
    dns_allowed: bool = False,
    socket_allowed: bool = False,
    http_allowed: bool = False,
    provider_sdk_allowed: bool = False,
    semantic_generation_allowed: bool = False,
    tool_calls_allowed: bool = False,
    memory_retrieval_allowed: bool = False,
    memory_write_allowed: bool = False,
    retention_allowed: bool = False,
    action_execution_allowed: bool = False,
    routing_allowed: bool = False,
) -> ProviderInvocationDenialReviewReceipt:
    rdata = _mapping(readiness)
    pdata = _mapping(preflight)
    expiration = _expiration(expires_at, ttl_seconds, reviewed_at, evaluated_at)
    expired = _is_expired(expiration)
    required = extract_required_provider_invocation_denial_review_codes(readiness, preflight)
    approved_constraints = _dedupe(tuple(approved_constraint_codes) + tuple(required["constraint_codes"]))
    accepted_denials = _dedupe(tuple(accepted_denial_codes) + tuple(required["denial_codes"]))
    accepted_gaps = _dedupe(tuple(accepted_gap_codes))
    allowance_flags = {
        "invocation_allowed": bool(invocation_allowed),
        "provider_send_allowed": bool(provider_send_allowed),
        "credential_use_allowed": bool(credential_use_allowed),
        "endpoint_use_allowed": bool(endpoint_use_allowed),
        "client_use_allowed": bool(client_use_allowed),
        "network_access_allowed": bool(network_access_allowed),
        "dns_allowed": bool(dns_allowed),
        "socket_allowed": bool(socket_allowed),
        "http_allowed": bool(http_allowed),
        "provider_sdk_allowed": bool(provider_sdk_allowed),
        "semantic_generation_allowed": bool(semantic_generation_allowed),
        "tool_calls_allowed": bool(tool_calls_allowed),
        "memory_retrieval_allowed": bool(memory_retrieval_allowed),
        "memory_write_allowed": bool(memory_write_allowed),
        "retention_allowed": bool(retention_allowed),
        "action_execution_allowed": bool(action_execution_allowed),
        "routing_allowed": bool(routing_allowed),
    }
    audit = _audit_chain(readiness, preflight)
    findings = _review_findings(
        readiness,
        preflight,
        decision=str(decision),
        review_scope=str(review_scope),
        reviewer_ref=str(reviewer_ref),
        accepted_gap_codes=accepted_gaps,
        rejected_gap_codes=_dedupe(rejected_gap_codes),
        accepted_denial_codes=accepted_denials,
        rejected_denial_codes=_dedupe(rejected_denial_codes),
        approved_constraint_codes=approved_constraints,
        rejected_constraint_codes=_dedupe(rejected_constraint_codes),
        allowance_flags=allowance_flags,
        expired=expired,
        rationale=rationale,
    )
    status = _status(str(decision), findings, expired)
    warnings = ("invocation_denial_review_is_not_invocation_approval", "provider_invocation_remains_forbidden")
    if str(review_scope) in {
        ProviderInvocationDenialReviewScope.FUTURE_EXTERNAL_SECURITY_REVIEW_GATE,
        ProviderInvocationDenialReviewScope.FUTURE_INVOCATION_DENIAL_AUDIT_GATE,
    }:
        warnings += ("future_metadata_gate_only",)
    receipt = ProviderInvocationDenialReviewReceipt(
        review_receipt_id="",
        review_status=status,
        readiness_id=str(rdata.get("invocation_readiness_id", "")),
        readiness_status=str(rdata.get("readiness_status", "")),
        readiness_digest=str(rdata.get("readiness_digest", "")),
        readiness_preflight_id=str(pdata.get("invocation_preflight_id", "")),
        readiness_preflight_status=str(pdata.get("invocation_preflight_status", "")),
        readiness_preflight_digest=str(pdata.get("invocation_preflight_digest", "")),
        audit_chain=audit,
        digest_chain_complete=bool(audit.complete),
        reviewer_ref=str(reviewer_ref),
        review_scope=str(review_scope),
        decision=str(decision),
        approved_constraint_codes=approved_constraints,
        rejected_constraint_codes=_dedupe(rejected_constraint_codes),
        accepted_gap_codes=accepted_gaps,
        rejected_gap_codes=_dedupe(rejected_gap_codes),
        accepted_denial_codes=accepted_denials,
        rejected_denial_codes=_dedupe(rejected_denial_codes),
        expiration=expiration,
        expired=expired,
        forbidden_invocation_override_attempted=status == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_FORBIDDEN_INVOCATION_OVERRIDE_ATTEMPTED,
        findings=tuple(findings),
        warnings=warnings,
        constraints=_constraints(),
        rationale=str(rationale)[:1000],
        review_digest="",
        **allowance_flags,
    )
    digest = compute_provider_invocation_denial_review_digest(receipt)
    return replace(receipt, review_receipt_id=f"provider-invocation-denial-review:{receipt.readiness_id or 'missing'}:{digest[:16]}", review_digest=digest)


def build_provider_invocation_denial_review_receipt_from_preflight(
    preflight: ProviderInvocationReadinessPreflight | Mapping[str, Any],
    *,
    readiness: ProviderInvocationReadinessManifest | Mapping[str, Any],
    reviewer_ref: str,
    decision: str,
    review_scope: str = ProviderInvocationDenialReviewScope.INVOCATION_DENIAL_REVIEW_GATE,
    approved_constraint_codes: Sequence[str] = (),
    rejected_constraint_codes: Sequence[str] = (),
    accepted_gap_codes: Sequence[str] = (),
    rejected_gap_codes: Sequence[str] = (),
    accepted_denial_codes: Sequence[str] = (),
    rejected_denial_codes: Sequence[str] = (),
    rationale: str = "",
    expires_at: str | None = None,
    ttl_seconds: int | None = None,
    reviewed_at: str | None = None,
    evaluated_at: str | None = None,
) -> ProviderInvocationDenialReviewReceipt:
    return build_provider_invocation_denial_review_receipt(
        readiness,
        preflight,
        reviewer_ref=reviewer_ref,
        decision=decision,
        review_scope=review_scope,
        approved_constraint_codes=approved_constraint_codes,
        rejected_constraint_codes=rejected_constraint_codes,
        accepted_gap_codes=accepted_gap_codes,
        rejected_gap_codes=rejected_gap_codes,
        accepted_denial_codes=accepted_denial_codes,
        rejected_denial_codes=rejected_denial_codes,
        rationale=rationale,
        expires_at=expires_at,
        ttl_seconds=ttl_seconds,
        reviewed_at=reviewed_at,
        evaluated_at=evaluated_at,
    )


def _markers_true(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data and all(data.get(field_name) is True for field_name in _MARKER_FIELDS))


def _has_no_allowance(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data and all(data.get(field_name) is False for field_name in _ALLOWANCE_FIELDS))


def validate_provider_invocation_denial_review_receipt(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> tuple[ProviderInvocationDenialReviewFinding, ...]:
    data = _mapping(receipt)
    findings: list[ProviderInvocationDenialReviewFinding] = []
    if not data:
        return (_finding("review_receipt_malformed", "provider invocation-denial review receipt is malformed"),)
    if not str(data.get("reviewer_ref", "")):
        findings.append(_finding("reviewer_ref_missing", "reviewer_ref is required"))
    if not _markers_true(receipt):
        findings.append(_finding("invocation_denial_review_marker_missing", "all invocation-denial review markers must be true"))
    for field_name in _ALLOWANCE_FIELDS:
        if bool(data.get(field_name, False)):
            findings.append(_finding("forbidden_allowance_requested", f"{field_name} must remain false"))
    if bool(data.get("expired", False)):
        findings.append(_finding("review_expired", "provider invocation-denial review receipt is expired"))
    if bool(data.get("forbidden_invocation_override_attempted", False)):
        findings.append(_finding("forbidden_invocation_override_attempted", "receipt attempted a forbidden provider invocation override"))
    expected = compute_provider_invocation_denial_review_digest(receipt)
    if str(data.get("review_digest", "")) != expected:
        findings.append(_finding("review_digest_mismatch", "review digest does not match receipt metadata"))
    return tuple(findings)


def provider_invocation_denial_review_attempts_forbidden_invocation_override(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    non_overridable = {
        "review_scope_non_overridable",
        "readiness_dirty_evidence_non_overridable",
        "preflight_dirty_evidence_non_overridable",
        "readiness_status_not_denial_reviewable",
        "preflight_status_not_denial_reviewable",
        "digest_chain_incomplete_non_overridable",
        "readiness_invocation_forbidden_not_preserved",
        "preflight_invocation_forbidden_not_preserved",
        "readiness_credentials_detected_non_overridable",
        "readiness_endpoints_detected_non_overridable",
        "readiness_clients_detected_non_overridable",
        "readiness_network_detected_non_overridable",
        "readiness_runtime_authority_detected_non_overridable",
        "preflight_runtime_authority_detected_non_overridable",
        "forbidden_allowance_requested",
        "forbidden_marker_non_overridable",
    }
    return bool(
        data.get("forbidden_invocation_override_attempted", False)
        or data.get("review_status") == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_FORBIDDEN_INVOCATION_OVERRIDE_ATTEMPTED
        or any(_mapping(finding).get("code") in non_overridable for finding in data.get("findings", ()) or ())
    )


def _required_codes_addressed(
    readiness: ProviderInvocationReadinessManifest | Mapping[str, Any],
    preflight: ProviderInvocationReadinessPreflight | Mapping[str, Any],
    receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any],
) -> bool:
    data = _mapping(receipt)
    required = extract_required_provider_invocation_denial_review_codes(readiness, preflight)
    gap_codes = set(required["gap_codes"])
    denial_codes = set(required["denial_codes"])
    constraint_codes = set(required["constraint_codes"])
    accepted_gaps = set(_tuple_str(data.get("accepted_gap_codes", ())))
    accepted_denials = set(_tuple_str(data.get("accepted_denial_codes", ())))
    approved_constraints = set(_tuple_str(data.get("approved_constraint_codes", ())))
    rejected = set(_tuple_str(data.get("rejected_gap_codes", ()))) | set(_tuple_str(data.get("rejected_denial_codes", ()))) | set(_tuple_str(data.get("rejected_constraint_codes", ())))
    return bool(gap_codes.isdisjoint(rejected) and denial_codes.isdisjoint(rejected) and constraint_codes.isdisjoint(rejected) and gap_codes.issubset(accepted_gaps) and denial_codes.issubset(accepted_denials) and constraint_codes.issubset(approved_constraints))


def provider_invocation_denial_review_satisfies_readiness_preflight(
    readiness: ProviderInvocationReadinessManifest | Mapping[str, Any],
    preflight: ProviderInvocationReadinessPreflight | Mapping[str, Any],
    review_receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any] | None,
) -> bool:
    if review_receipt is None:
        return False
    rdata = _mapping(readiness)
    pdata = _mapping(preflight)
    review = _mapping(review_receipt)
    if not rdata or not pdata or not review:
        return False
    if str(rdata.get("readiness_status", "")) not in _ACCEPTABLE_READINESS_STATUSES:
        return False
    if str(pdata.get("invocation_preflight_status", "")) not in _ACCEPTABLE_PREFLIGHT_STATUSES:
        return False
    if str(review.get("review_status", "")) not in {
        ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_ACCEPTED,
        ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_ACCEPTED_WITH_CONDITIONS,
    }:
        return False
    if str(rdata.get("invocation_readiness_id", "")) != str(review.get("readiness_id", "")):
        return False
    if str(pdata.get("invocation_preflight_id", "")) != str(review.get("readiness_preflight_id", "")):
        return False
    if str(rdata.get("readiness_digest", "")) != str(review.get("readiness_digest", "")):
        return False
    if str(pdata.get("invocation_preflight_digest", "")) != str(review.get("readiness_preflight_digest", "")):
        return False
    if bool(review.get("expired", False)):
        return False
    if str(review.get("decision", "")) not in {
        ProviderInvocationDenialReviewDecision.AFFIRM_INVOCATION_FORBIDDEN,
        ProviderInvocationDenialReviewDecision.AFFIRM_METADATA_ONLY_NOT_INVOCABLE,
        ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_EXTERNAL_SECURITY_REVIEW_GATE,
        ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_INVOCATION_DENIAL_AUDIT_GATE,
        ProviderInvocationDenialReviewDecision.APPROVE_WITH_CONDITIONS,
    }:
        return False
    if provider_invocation_denial_review_attempts_forbidden_invocation_override(review_receipt):
        return False
    if not _required_codes_addressed(readiness, preflight, review_receipt):
        return False
    clean_metadata = bool(
        rdata.get("readiness_status") == ProviderInvocationReadinessStatus.INVOCATION_READINESS_NULL_ONLY_METADATA
        and pdata.get("invocation_preflight_status") == ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_METADATA_ONLY_NOT_INVOCABLE
        and provider_invocation_preflight_remains_metadata_only(preflight)
    )
    denial_posture = bool(
        str(rdata.get("readiness_status", "")) in {
            ProviderInvocationReadinessStatus.INVOCATION_READINESS_FORBIDDEN,
            ProviderInvocationReadinessStatus.INVOCATION_READINESS_MISSING_EVIDENCE,
        }
        and str(pdata.get("invocation_preflight_status", "")) in {
            ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_DENIED,
            ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_FORBIDDEN,
            ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_MISSING_EVIDENCE,
        }
    )
    return bool(
        (clean_metadata or denial_posture)
        and _markers_true(review_receipt)
        and _has_no_allowance(review_receipt)
        and provider_invocation_denial_review_affirms_forbidden_invocation(review_receipt)
        and provider_invocation_denial_review_has_no_credentials(review_receipt)
        and provider_invocation_denial_review_has_no_endpoints(review_receipt)
        and provider_invocation_denial_review_has_no_clients(review_receipt)
        and provider_invocation_denial_review_has_no_network(review_receipt)
        and provider_invocation_denial_review_has_no_runtime_authority(review_receipt)
    )


def provider_invocation_denial_review_affirms_forbidden_invocation(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("provider_invocation_forbidden") is True
        and data.get("actual_provider_invocation_forbidden") is True
        and data.get("metadata_only_not_invocable") is True
        and data.get("invocation_allowed") is False
        and data.get("provider_send_allowed") is False
        and data.get("does_not_call_llm") is True
        and data.get("does_not_send_to_provider") is True
        and str(data.get("decision", "")) in {
            ProviderInvocationDenialReviewDecision.AFFIRM_INVOCATION_FORBIDDEN,
            ProviderInvocationDenialReviewDecision.AFFIRM_METADATA_ONLY_NOT_INVOCABLE,
            ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_EXTERNAL_SECURITY_REVIEW_GATE,
            ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_INVOCATION_DENIAL_AUDIT_GATE,
            ProviderInvocationDenialReviewDecision.APPROVE_WITH_CONDITIONS,
        }
    )


def provider_invocation_denial_review_approves_future_external_security_review_gate(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("review_status") == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_ACCEPTED_WITH_CONDITIONS
        and data.get("review_scope") == ProviderInvocationDenialReviewScope.FUTURE_EXTERNAL_SECURITY_REVIEW_GATE
        and data.get("decision") == ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_EXTERNAL_SECURITY_REVIEW_GATE
        and not data.get("expired", False)
        and not provider_invocation_denial_review_attempts_forbidden_invocation_override(receipt)
        and _markers_true(receipt)
        and _has_no_allowance(receipt)
    )


def provider_invocation_denial_review_approves_future_denial_audit_gate(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("review_status") == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_ACCEPTED_WITH_CONDITIONS
        and data.get("review_scope") == ProviderInvocationDenialReviewScope.FUTURE_INVOCATION_DENIAL_AUDIT_GATE
        and data.get("decision") == ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_INVOCATION_DENIAL_AUDIT_GATE
        and not data.get("expired", False)
        and not provider_invocation_denial_review_attempts_forbidden_invocation_override(receipt)
        and data.get("provider_invocation_forbidden") is True
        and _markers_true(receipt)
        and _has_no_allowance(receipt)
    )


def provider_invocation_denial_review_has_no_credentials(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data.get("credential_use_allowed") is False and data.get("credential_use_forbidden") is True and data.get("does_not_read_environment") is True and data.get("does_not_access_vaults") is True and data.get("does_not_access_keychains") is True and data.get("does_not_access_cloud_secrets") is True)


def provider_invocation_denial_review_has_no_endpoints(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data.get("endpoint_use_allowed") is False and data.get("endpoint_use_forbidden") is True and data.get("does_not_resolve_dns") is True and data.get("does_not_read_files") is True and data.get("does_not_access_config_stores") is True)


def provider_invocation_denial_review_has_no_clients(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data.get("client_use_allowed") is False and data.get("provider_client_use_forbidden") is True and data.get("does_not_create_clients") is True and data.get("does_not_create_sessions") is True and data.get("does_not_create_transports") is True and data.get("does_not_import_provider_sdks") is True)


def provider_invocation_denial_review_has_no_network(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data.get("network_access_allowed") is False and data.get("dns_allowed") is False and data.get("socket_allowed") is False and data.get("http_allowed") is False and data.get("network_access_forbidden") is True and data.get("does_not_make_network_calls") is True and data.get("does_not_open_sockets") is True and data.get("does_not_make_http_requests") is True and data.get("does_not_resolve_dns") is True)


def provider_invocation_denial_review_has_no_runtime_authority(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("semantic_generation_allowed") is False
        and data.get("tool_calls_allowed") is False
        and data.get("memory_retrieval_allowed") is False
        and data.get("memory_write_allowed") is False
        and data.get("retention_allowed") is False
        and data.get("action_execution_allowed") is False
        and data.get("routing_allowed") is False
        and data.get("does_not_call_llm") is True
        and data.get("does_not_retrieve_memory") is True
        and data.get("does_not_write_memory") is True
        and data.get("does_not_trigger_feedback") is True
        and data.get("does_not_commit_retention") is True
        and data.get("does_not_execute_or_route_work") is True
        and data.get("does_not_admit_work") is True
    )


def provider_invocation_denial_review_remains_metadata_only(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> bool:
    return bool(
        _markers_true(receipt)
        and _has_no_allowance(receipt)
        and provider_invocation_denial_review_affirms_forbidden_invocation(receipt)
        and provider_invocation_denial_review_has_no_credentials(receipt)
        and provider_invocation_denial_review_has_no_endpoints(receipt)
        and provider_invocation_denial_review_has_no_clients(receipt)
        and provider_invocation_denial_review_has_no_network(receipt)
        and provider_invocation_denial_review_has_no_runtime_authority(receipt)
    )


def explain_provider_invocation_denial_review_findings(receipt_or_findings: ProviderInvocationDenialReviewReceipt | Mapping[str, Any] | Sequence[ProviderInvocationDenialReviewFinding]) -> tuple[str, ...]:
    if isinstance(receipt_or_findings, Sequence) and not isinstance(receipt_or_findings, (str, bytes, Mapping)):
        findings = receipt_or_findings
    else:
        findings = _mapping(receipt_or_findings).get("findings", ()) or ()
    return tuple(f"{item.get('severity', '')}:{item.get('code', '')}:{item.get('detail', '')}" for item in (_mapping(finding) for finding in findings))


def summarize_provider_invocation_denial_review_receipt(receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(receipt)
    return {
        "review_receipt_id": str(data.get("review_receipt_id", "")),
        "review_status": str(data.get("review_status", "")),
        "readiness_id": str(data.get("readiness_id", "")),
        "readiness_status": str(data.get("readiness_status", "")),
        "readiness_digest": str(data.get("readiness_digest", "")),
        "readiness_preflight_id": str(data.get("readiness_preflight_id", "")),
        "readiness_preflight_status": str(data.get("readiness_preflight_status", "")),
        "readiness_preflight_digest": str(data.get("readiness_preflight_digest", "")),
        "digest_chain_complete": bool(data.get("digest_chain_complete", False)),
        "reviewer_ref": str(data.get("reviewer_ref", "")),
        "review_scope": str(data.get("review_scope", "")),
        "decision": str(data.get("decision", "")),
        "approved_constraint_count": len(_tuple_str(data.get("approved_constraint_codes", ()))),
        "rejected_constraint_count": len(_tuple_str(data.get("rejected_constraint_codes", ()))),
        "accepted_gap_count": len(_tuple_str(data.get("accepted_gap_codes", ()))),
        "rejected_gap_count": len(_tuple_str(data.get("rejected_gap_codes", ()))),
        "accepted_denial_count": len(_tuple_str(data.get("accepted_denial_codes", ()))),
        "rejected_denial_count": len(_tuple_str(data.get("rejected_denial_codes", ()))),
        "expired": bool(data.get("expired", False)),
        "forbidden_invocation_override_attempted": bool(data.get("forbidden_invocation_override_attempted", False)),
        "invocation_allowed": bool(data.get("invocation_allowed", False)),
        "provider_send_allowed": bool(data.get("provider_send_allowed", False)),
        "credential_use_allowed": bool(data.get("credential_use_allowed", False)),
        "endpoint_use_allowed": bool(data.get("endpoint_use_allowed", False)),
        "client_use_allowed": bool(data.get("client_use_allowed", False)),
        "network_access_allowed": bool(data.get("network_access_allowed", False)),
        "runtime_allowance_allowed": any(bool(data.get(field_name, False)) for field_name in _ALLOWANCE_FIELDS),
        "finding_count": len(tuple(data.get("findings", ()) or ())),
        "warning_count": len(tuple(data.get("warnings", ()) or ())),
        "review_digest": str(data.get("review_digest", "")),
        "provider_invocation_denial_review_receipt_only": bool(data.get("provider_invocation_denial_review_receipt_only", False)),
        "provider_invocation_forbidden": bool(data.get("provider_invocation_forbidden", False)),
        "metadata_only_not_invocable": bool(data.get("metadata_only_not_invocable", False)),
        "future_security_review_gate_only": bool(data.get("future_security_review_gate_only", False)),
        "actual_provider_invocation_forbidden": bool(data.get("actual_provider_invocation_forbidden", False)),
        "does_not_call_llm": bool(data.get("does_not_call_llm", False)),
        "does_not_send_to_provider": bool(data.get("does_not_send_to_provider", False)),
        "does_not_make_network_calls": bool(data.get("does_not_make_network_calls", False)),
    }
