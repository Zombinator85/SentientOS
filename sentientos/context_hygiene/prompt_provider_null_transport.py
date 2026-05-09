from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_network_egress_preflight import (
    ProviderNetworkEgressPreflight,
    ProviderNetworkEgressPreflightStatus,
    compute_provider_network_egress_preflight_digest,
    provider_network_egress_preflight_allows_future_review_gate,
    provider_network_egress_preflight_digest_chain_complete,
    provider_network_egress_preflight_forbids_network,
    provider_network_egress_preflight_forbids_provider_send,
    provider_network_egress_preflight_has_no_credentials,
    provider_network_egress_preflight_has_no_runtime_authority,
)
from sentientos.context_hygiene.prompt_network_egress_review import (
    ProviderNetworkEgressReviewReceipt,
    ProviderNetworkEgressReviewScope,
    ProviderNetworkEgressReviewStatus,
    compute_provider_network_egress_review_digest,
    provider_network_egress_review_approves_future_null_transport_gate,
    provider_network_egress_review_has_no_credentials,
    provider_network_egress_review_has_no_runtime_authority,
    provider_network_egress_review_preserves_network_forbidden,
    provider_network_egress_review_preserves_provider_forbidden,
    provider_network_egress_review_satisfies_preflight,
)
from sentientos.context_hygiene.prompt_provider_dry_run import (
    ProviderDryRunRequestEnvelope,
    ProviderDryRunStatus,
    compute_provider_dry_run_digest,
    provider_dry_run_has_no_network_egress,
    provider_dry_run_has_no_provider_credentials,
    provider_dry_run_has_no_runtime_authority,
    provider_dry_run_is_non_sendable,
)


class ProviderNullTransportStatus:
    NULL_TRANSPORT_READY = "null_transport_ready"
    NULL_TRANSPORT_READY_WITH_WARNINGS = "null_transport_ready_with_warnings"
    NULL_TRANSPORT_BLOCKED = "null_transport_blocked"
    NULL_TRANSPORT_INVALID_INPUT = "null_transport_invalid_input"
    NULL_TRANSPORT_REVIEW_MISSING = "null_transport_review_missing"
    NULL_TRANSPORT_REVIEW_NOT_SATISFIED = "null_transport_review_not_satisfied"
    NULL_TRANSPORT_PREFLIGHT_NOT_READY = "null_transport_preflight_not_ready"
    NULL_TRANSPORT_DRY_RUN_NOT_READY = "null_transport_dry_run_not_ready"
    NULL_TRANSPORT_NETWORK_FORBIDDEN = "null_transport_network_forbidden"
    NULL_TRANSPORT_CREDENTIALS_DETECTED = "null_transport_credentials_detected"
    NULL_TRANSPORT_ENDPOINT_DETECTED = "null_transport_endpoint_detected"
    NULL_TRANSPORT_CLIENT_DETECTED = "null_transport_client_detected"
    NULL_TRANSPORT_RUNTIME_AUTHORITY_DETECTED = "null_transport_runtime_authority_detected"
    NULL_TRANSPORT_SEND_ATTEMPT_DETECTED = "null_transport_send_attempt_detected"


class ProviderNullTransportMode:
    NULL_TRANSPORT_MODE_NOOP = "null_transport_mode_noop"
    NULL_TRANSPORT_MODE_DIGEST_ONLY = "null_transport_mode_digest_only"
    NULL_TRANSPORT_MODE_AUDIT_ONLY = "null_transport_mode_audit_only"
    NULL_TRANSPORT_MODE_UNKNOWN_FORBIDDEN = "null_transport_mode_unknown_forbidden"
    LIVE_NETWORK = "live_network"
    PROVIDER_SEND = "provider_send"
    HTTP_REQUEST = "http_request"
    SOCKET_TRANSPORT = "socket_transport"
    SEMANTIC_GENERATION = "semantic_generation"


class ProviderNullTransportScope:
    FUTURE_TRANSPORT_NULL_ADAPTER_GATE = "future_transport_null_adapter_gate"
    INTERNAL_NULL_TRANSPORT_AUDIT = "internal_null_transport_audit"
    PROVIDER_SEND_FORBIDDEN = "provider_send_forbidden"
    NETWORK_EGRESS_FORBIDDEN = "network_egress_forbidden"
    CREDENTIAL_USE_FORBIDDEN = "credential_use_forbidden"
    ENDPOINT_USE_FORBIDDEN = "endpoint_use_forbidden"
    PROVIDER_CLIENT_USE_FORBIDDEN = "provider_client_use_forbidden"
    EXTERNAL_USER_VISIBLE_FORBIDDEN = "external_user_visible_forbidden"


@dataclass(frozen=True)
class ProviderNullTransportFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderNullTransportConstraint:
    code: str
    detail: str
    required: bool = True


@dataclass(frozen=True)
class ProviderNullTransportBoundary:
    provider_null_transport_only: bool = True
    null_transport_sent_nothing: bool = True
    network_egress_forbidden: bool = True
    provider_send_forbidden: bool = True
    credentials_forbidden: bool = True
    endpoint_forbidden: bool = True
    provider_client_forbidden: bool = True
    socket_forbidden: bool = True
    http_forbidden: bool = True
    llm_call_forbidden: bool = True
    semantic_generation_forbidden: bool = True
    does_not_make_network_calls: bool = True
    does_not_send_to_provider: bool = True
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True


@dataclass(frozen=True)
class ProviderNullTransportAuditChain:
    dry_run_id: str = ""
    dry_run_digest: str = ""
    network_preflight_id: str = ""
    network_preflight_digest: str = ""
    network_review_receipt_id: str = ""
    network_review_digest: str = ""
    egress_review_receipt_id: str = ""
    egress_review_digest: str = ""
    simulation_id: str = ""
    simulation_digest: str = ""
    candidate_id: str = ""
    candidate_digest: str = ""
    packet_id: str = ""
    packet_scope: str = ""
    complete: bool = False
    mismatches: tuple[str, ...] = field(default_factory=tuple)
    missing: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProviderNullTransportReceipt:
    null_transport_id: str
    null_transport_status: str
    null_transport_mode: str
    null_transport_scope: str
    transport_reason: str
    dry_run_id: str
    dry_run_status: str
    dry_run_digest: str
    network_preflight_id: str
    network_preflight_status: str
    network_preflight_digest: str
    network_review_receipt_id: str
    network_review_status: str
    network_review_digest: str
    provider_family_label: str
    model_family_label: str
    candidate_id: str
    candidate_digest: str
    packet_id: str
    packet_scope: str
    audit_chain: ProviderNullTransportAuditChain
    digest_chain_complete: bool
    sent: bool
    bytes_sent: int
    request_created: bool
    response_received: bool
    network_egress_attempted: bool
    provider_send_attempted: bool
    credentials_used: bool
    endpoint_used: bool
    provider_client_used: bool
    socket_opened: bool
    http_request_attempted: bool
    llm_call_attempted: bool
    semantic_generation_attempted: bool
    tool_calls_attempted: bool
    memory_access_attempted: bool
    retention_attempted: bool
    action_execution_attempted: bool
    routing_attempted: bool
    findings: tuple[ProviderNullTransportFinding, ...]
    warnings: tuple[str, ...]
    constraints: tuple[ProviderNullTransportConstraint, ...]
    rationale: str
    null_transport_digest: str
    provider_null_transport_only: bool = True
    null_transport_sent_nothing: bool = True
    network_egress_forbidden: bool = True
    provider_send_forbidden: bool = True
    credentials_forbidden: bool = True
    endpoint_forbidden: bool = True
    provider_client_forbidden: bool = True
    socket_forbidden: bool = True
    http_forbidden: bool = True
    llm_call_forbidden: bool = True
    semantic_generation_forbidden: bool = True
    does_not_make_network_calls: bool = True
    does_not_send_to_provider: bool = True
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True
    boundary: ProviderNullTransportBoundary = field(default_factory=ProviderNullTransportBoundary)


_READY_DRY_RUN_STATUSES = frozenset({ProviderDryRunStatus.PROVIDER_DRY_RUN_READY, ProviderDryRunStatus.PROVIDER_DRY_RUN_READY_WITH_WARNINGS})
_READY_PREFLIGHT_STATUSES = frozenset(
    {
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_FOR_REVIEW,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_WITH_WARNINGS,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_REVIEW_REQUIRED,
    }
)
_READY_REVIEW_STATUSES = frozenset(
    {
        ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_APPROVED,
        ProviderNetworkEgressReviewStatus.NETWORK_EGRESS_REVIEW_APPROVED_WITH_CONSTRAINTS,
    }
)
_ALLOWED_MODES = frozenset(
    {
        ProviderNullTransportMode.NULL_TRANSPORT_MODE_NOOP,
        ProviderNullTransportMode.NULL_TRANSPORT_MODE_DIGEST_ONLY,
        ProviderNullTransportMode.NULL_TRANSPORT_MODE_AUDIT_ONLY,
        "noop",
        "digest_only",
        "audit_only",
    }
)
_ALLOWED_SCOPES = frozenset(
    {
        ProviderNullTransportScope.FUTURE_TRANSPORT_NULL_ADAPTER_GATE,
        ProviderNullTransportScope.INTERNAL_NULL_TRANSPORT_AUDIT,
    }
)
_FORBIDDEN_SCOPE_STATUS = {
    ProviderNullTransportScope.PROVIDER_SEND_FORBIDDEN: ProviderNullTransportStatus.NULL_TRANSPORT_SEND_ATTEMPT_DETECTED,
    ProviderNullTransportScope.NETWORK_EGRESS_FORBIDDEN: ProviderNullTransportStatus.NULL_TRANSPORT_NETWORK_FORBIDDEN,
    ProviderNullTransportScope.CREDENTIAL_USE_FORBIDDEN: ProviderNullTransportStatus.NULL_TRANSPORT_CREDENTIALS_DETECTED,
    ProviderNullTransportScope.ENDPOINT_USE_FORBIDDEN: ProviderNullTransportStatus.NULL_TRANSPORT_ENDPOINT_DETECTED,
    ProviderNullTransportScope.PROVIDER_CLIENT_USE_FORBIDDEN: ProviderNullTransportStatus.NULL_TRANSPORT_CLIENT_DETECTED,
    ProviderNullTransportScope.EXTERNAL_USER_VISIBLE_FORBIDDEN: ProviderNullTransportStatus.NULL_TRANSPORT_RUNTIME_AUTHORITY_DETECTED,
}
_ATTEMPT_FIELDS = (
    "sent",
    "request_created",
    "response_received",
    "network_egress_attempted",
    "provider_send_attempted",
    "credentials_used",
    "endpoint_used",
    "provider_client_used",
    "socket_opened",
    "http_request_attempted",
    "llm_call_attempted",
    "semantic_generation_attempted",
    "tool_calls_attempted",
    "memory_access_attempted",
    "retention_attempted",
    "action_execution_attempted",
    "routing_attempted",
)
_MARKER_FIELDS = (
    "provider_null_transport_only",
    "null_transport_sent_nothing",
    "network_egress_forbidden",
    "provider_send_forbidden",
    "credentials_forbidden",
    "endpoint_forbidden",
    "provider_client_forbidden",
    "socket_forbidden",
    "http_forbidden",
    "llm_call_forbidden",
    "semantic_generation_forbidden",
    "does_not_make_network_calls",
    "does_not_send_to_provider",
    "does_not_call_llm",
    "does_not_retrieve_memory",
    "does_not_write_memory",
    "does_not_trigger_feedback",
    "does_not_commit_retention",
    "does_not_execute_or_route_work",
    "does_not_admit_work",
)
_RUNTIME_MARKER_KEYS = (
    "raw_payload",
    "raw_memory_payload",
    "raw_screen_payload",
    "raw_audio_payload",
    "raw_vision_payload",
    "raw_multimodal_payload",
    "runtime_handle",
    "execution_handle",
    "network_handle",
    "request_handle",
    "response_handle",
    "provider_params",
    "model_params",
    "llm_params",
    "llm_parameters",
    "api_key",
    "auth_header",
    "endpoint",
    "provider_client",
    "session",
    "transport",
    "tool_call",
    "tool_schema",
    "function_call",
    "memory_handle",
    "action_handle",
    "retention_handle",
    "routing_handle",
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


def _finding(code: str, detail: str, severity: str = "blocker") -> ProviderNullTransportFinding:
    return ProviderNullTransportFinding(code=code, detail=detail, severity=severity)


def _constraints() -> tuple[ProviderNullTransportConstraint, ...]:
    return (
        ProviderNullTransportConstraint("null_transport_only", "Phase 89 is a metadata-only null transport adapter"),
        ProviderNullTransportConstraint("sent_nothing", "sent must be false and bytes_sent must be zero"),
        ProviderNullTransportConstraint("no_network", "network, socket, and HTTP activity remain forbidden"),
        ProviderNullTransportConstraint("no_provider_objects", "credentials, endpoints, and provider clients remain absent"),
        ProviderNullTransportConstraint("no_runtime_authority", "tools, memory, retention, action, routing, admission, and execution remain forbidden"),
        ProviderNullTransportConstraint("no_semantic_generation", "LLM calls, model outputs, and semantic generation remain forbidden"),
    )


def _digest_or_stored(value: Any, stored_field: str, compute: Any) -> str:
    data = _mapping(value)
    if not data:
        return ""
    try:
        computed = compute(value)
    except Exception:
        computed = ""
    return str(computed or data.get(stored_field, ""))


def _build_audit_chain(
    dry_run_envelope: Any,
    network_preflight: Any,
    network_review_receipt: Any,
    *,
    expected_dry_run_digest: str | None,
    expected_preflight_digest: str | None,
    expected_review_digest: str | None,
) -> ProviderNullTransportAuditChain:
    dry = _mapping(dry_run_envelope)
    preflight = _mapping(network_preflight)
    review = _mapping(network_review_receipt)
    preflight_chain = _mapping(preflight.get("audit_chain", {}))
    missing: list[str] = []
    mismatches: list[str] = []
    required = {
        "dry_run_id": dry.get("dry_run_id", preflight.get("dry_run_id", review.get("dry_run_id", ""))),
        "dry_run_digest": dry.get("dry_run_digest", preflight.get("dry_run_digest", review.get("dry_run_digest", ""))),
        "network_preflight_id": preflight.get("preflight_id", review.get("network_preflight_id", "")),
        "network_preflight_digest": preflight.get("preflight_digest", review.get("network_preflight_digest", "")),
        "network_review_receipt_id": review.get("review_receipt_id", ""),
        "network_review_digest": review.get("review_digest", ""),
        "candidate_id": dry.get("candidate_id", preflight.get("candidate_id", review.get("candidate_id", ""))),
        "candidate_digest": dry.get("candidate_digest", preflight.get("candidate_digest", review.get("candidate_digest", ""))),
    }
    for key, value in required.items():
        if not value:
            missing.append(key)
    if dry and str(dry.get("dry_run_digest", "")) != _digest_or_stored(dry_run_envelope, "dry_run_digest", compute_provider_dry_run_digest):
        mismatches.append("dry_run_digest")
    if preflight and str(preflight.get("preflight_digest", "")) != _digest_or_stored(network_preflight, "preflight_digest", compute_provider_network_egress_preflight_digest):
        mismatches.append("network_preflight_digest")
    if review and str(review.get("review_digest", "")) != _digest_or_stored(network_review_receipt, "review_digest", compute_provider_network_egress_review_digest):
        mismatches.append("network_review_digest")
    expected_pairs = (
        ("expected_dry_run_digest", expected_dry_run_digest, dry.get("dry_run_digest", "")),
        ("expected_preflight_digest", expected_preflight_digest, preflight.get("preflight_digest", "")),
        ("expected_review_digest", expected_review_digest, review.get("review_digest", "")),
    )
    for label, expected, actual in expected_pairs:
        if expected is not None and str(expected) != str(actual):
            mismatches.append(label)
    if dry and preflight:
        if dry.get("dry_run_id") != preflight.get("dry_run_id"):
            mismatches.append("preflight_dry_run_id")
        if dry.get("dry_run_digest") != preflight.get("dry_run_digest"):
            mismatches.append("preflight_dry_run_digest")
    if dry and review:
        if dry.get("dry_run_id") != review.get("dry_run_id"):
            mismatches.append("review_dry_run_id")
        if dry.get("dry_run_digest") != review.get("dry_run_digest"):
            mismatches.append("review_dry_run_digest")
    if preflight and review:
        if preflight.get("preflight_id") != review.get("network_preflight_id"):
            mismatches.append("review_preflight_id")
        if preflight.get("preflight_digest") != review.get("network_preflight_digest"):
            mismatches.append("review_preflight_digest")
    return ProviderNullTransportAuditChain(
        dry_run_id=str(required["dry_run_id"]),
        dry_run_digest=str(required["dry_run_digest"]),
        network_preflight_id=str(required["network_preflight_id"]),
        network_preflight_digest=str(required["network_preflight_digest"]),
        network_review_receipt_id=str(required["network_review_receipt_id"]),
        network_review_digest=str(required["network_review_digest"]),
        egress_review_receipt_id=str(preflight.get("egress_review_receipt_id", preflight_chain.get("egress_review_receipt_id", review.get("egress_review_receipt_id", "")))),
        egress_review_digest=str(preflight.get("egress_review_digest", preflight_chain.get("egress_review_digest", review.get("egress_review_digest", "")))),
        simulation_id=str(preflight.get("simulation_id", preflight_chain.get("simulation_id", review.get("simulation_id", "")))),
        simulation_digest=str(preflight.get("simulation_digest", preflight_chain.get("simulation_digest", review.get("simulation_digest", "")))),
        candidate_id=str(required["candidate_id"]),
        candidate_digest=str(required["candidate_digest"]),
        packet_id=str(dry.get("packet_id", preflight.get("packet_id", review.get("packet_id", "")))),
        packet_scope=str(dry.get("packet_scope", preflight.get("packet_scope", review.get("packet_scope", "")))),
        complete=not missing and not mismatches,
        mismatches=tuple(mismatches),
        missing=tuple(missing),
    )


def _contains_runtime_marker(value: Any) -> bool:
    text = json.dumps(_stable(value), sort_keys=True, ensure_ascii=True, default=str).lower()
    return any(marker in text for marker in _RUNTIME_MARKER_KEYS)


def _evaluate_findings(
    dry_run_envelope: Any,
    network_preflight: Any,
    network_review_receipt: Any,
    *,
    null_transport_mode: str,
    null_transport_scope: str,
    audit_chain: ProviderNullTransportAuditChain,
    internal_only: bool,
    no_network: bool,
    no_provider_send: bool,
    no_credentials: bool,
    no_endpoint: bool,
    no_provider_client: bool,
    no_http: bool,
    no_socket: bool,
    no_tools: bool,
    no_memory: bool,
    no_retention: bool,
    no_actions: bool,
    no_routing: bool,
    no_semantic_generation: bool,
    sent: bool,
    bytes_sent: int,
    request_created: bool,
    response_received: bool,
    network_egress_attempted: bool,
    provider_send_attempted: bool,
    credentials_used: bool,
    endpoint_used: bool,
    provider_client_used: bool,
    socket_opened: bool,
    http_request_attempted: bool,
    llm_call_attempted: bool,
    semantic_generation_attempted: bool,
    tool_calls_attempted: bool,
    memory_access_attempted: bool,
    retention_attempted: bool,
    action_execution_attempted: bool,
    routing_attempted: bool,
    no_raw_payload_marker: bool,
    no_runtime_handle_marker: bool,
    no_provider_model_params: bool,
    marker_evidence: Mapping[str, Any] | None,
) -> tuple[ProviderNullTransportFinding, ...]:
    dry = _mapping(dry_run_envelope)
    preflight = _mapping(network_preflight)
    review = _mapping(network_review_receipt)
    findings: list[ProviderNullTransportFinding] = []
    if not dry:
        findings.append(_finding("dry_run_missing", "Phase 84 ProviderDryRunRequestEnvelope is required"))
    if not preflight:
        findings.append(_finding("network_preflight_missing", "Phase 87 ProviderNetworkEgressPreflight is required"))
    if not review:
        findings.append(_finding("network_review_missing", "Phase 88 ProviderNetworkEgressReviewReceipt is required"))
    if str(null_transport_mode) not in _ALLOWED_MODES:
        findings.append(_finding("null_transport_mode_forbidden", "null transport mode must be noop, digest-only, or audit-only metadata"))
    if str(null_transport_scope) not in _ALLOWED_SCOPES:
        findings.append(_finding("null_transport_scope_forbidden", "null transport scope cannot authorize provider, network, credential, endpoint, client, or external-user activity"))
    if not internal_only:
        findings.append(_finding("external_visibility_forbidden", "null transport receipt must remain internal metadata only"))
    if dry and str(dry.get("dry_run_status", "")) not in _READY_DRY_RUN_STATUSES:
        findings.append(_finding("dry_run_not_ready", "dry run must be ready or ready with warnings"))
    if dry and not provider_dry_run_is_non_sendable(dry_run_envelope):
        findings.append(_finding("dry_run_sendable", "dry run must remain non-sendable"))
    if dry and not provider_dry_run_has_no_network_egress(dry_run_envelope):
        findings.append(_finding("dry_run_network_marker", "dry run must preserve no-network markers"))
    if dry and not provider_dry_run_has_no_provider_credentials(dry_run_envelope):
        findings.append(_finding("dry_run_credentials_marker", "dry run must preserve credential absence"))
    if dry and not provider_dry_run_has_no_runtime_authority(dry_run_envelope):
        findings.append(_finding("dry_run_runtime_marker", "dry run must preserve no-runtime authority"))
    if preflight and str(preflight.get("preflight_status", "")) not in _READY_PREFLIGHT_STATUSES:
        findings.append(_finding("network_preflight_not_ready", "network preflight must be ready, ready with warnings, or review required"))
    if preflight and not provider_network_egress_preflight_allows_future_review_gate(network_preflight):
        findings.append(_finding("network_preflight_future_gate_not_allowed", "network preflight does not allow a future metadata review gate"))
    if preflight and not provider_network_egress_preflight_forbids_network(network_preflight):
        findings.append(_finding("network_preflight_network_not_forbidden", "network preflight must forbid network egress"))
    if preflight and not provider_network_egress_preflight_forbids_provider_send(network_preflight):
        findings.append(_finding("network_preflight_provider_send_not_forbidden", "network preflight must forbid provider send"))
    if preflight and not provider_network_egress_preflight_has_no_credentials(network_preflight):
        findings.append(_finding("network_preflight_credentials_marker", "network preflight must preserve credential absence"))
    if preflight and not provider_network_egress_preflight_has_no_runtime_authority(network_preflight):
        findings.append(_finding("network_preflight_runtime_marker", "network preflight must preserve no-runtime authority"))
    if preflight and not provider_network_egress_preflight_digest_chain_complete(network_preflight):
        findings.append(_finding("network_preflight_digest_chain_incomplete", "network preflight digest chain must be complete"))
    if review:
        if str(review.get("review_status", "")) not in _READY_REVIEW_STATUSES:
            findings.append(_finding("network_review_not_approved", "network review must be approved or approved with constraints"))
        if not provider_network_egress_review_satisfies_preflight(network_preflight, network_review_receipt):
            findings.append(_finding("network_review_does_not_satisfy_preflight", "network review must satisfy the Phase 87 preflight"))
        if not provider_network_egress_review_approves_future_null_transport_gate(network_review_receipt):
            findings.append(_finding("network_review_missing_null_transport_gate", "network review must approve future_transport_null_adapter_gate"))
        if not provider_network_egress_review_preserves_network_forbidden(network_review_receipt):
            findings.append(_finding("network_review_network_not_forbidden", "network review must preserve network forbidden markers"))
        if not provider_network_egress_review_preserves_provider_forbidden(network_review_receipt):
            findings.append(_finding("network_review_provider_send_not_forbidden", "network review must preserve provider-send forbidden markers"))
        if not provider_network_egress_review_has_no_credentials(network_review_receipt):
            findings.append(_finding("network_review_credentials_marker", "network review must preserve credential/client/endpoint absence"))
        if not provider_network_egress_review_has_no_runtime_authority(network_review_receipt):
            findings.append(_finding("network_review_runtime_marker", "network review must preserve no-runtime authority"))
    if not audit_chain.complete:
        findings.append(_finding("digest_chain_incomplete", f"required digests must be present and matching; missing={audit_chain.missing!r}; mismatches={audit_chain.mismatches!r}"))
    flag_checks = {
        "no_network_false": no_network,
        "no_provider_send_false": no_provider_send,
        "no_credentials_false": no_credentials,
        "no_endpoint_false": no_endpoint,
        "no_provider_client_false": no_provider_client,
        "no_http_false": no_http,
        "no_socket_false": no_socket,
        "no_tools_false": no_tools,
        "no_memory_false": no_memory,
        "no_retention_false": no_retention,
        "no_actions_false": no_actions,
        "no_routing_false": no_routing,
        "no_semantic_generation_false": no_semantic_generation,
        "raw_payload_marker_detected": no_raw_payload_marker,
        "runtime_handle_marker_detected": no_runtime_handle_marker,
        "provider_model_params_detected": no_provider_model_params,
    }
    for code, ok in flag_checks.items():
        if not ok:
            findings.append(_finding(code, "null transport no-runtime/no-network proof flag must remain true"))
    if sent or bytes_sent != 0 or request_created or response_received or provider_send_attempted:
        findings.append(_finding("send_attempt_detected", "null transport cannot send, create requests, receive responses, or report nonzero bytes"))
    if network_egress_attempted or socket_opened or http_request_attempted:
        findings.append(_finding("network_attempt_detected", "null transport cannot attempt network, socket, or HTTP activity"))
    if credentials_used:
        findings.append(_finding("credentials_used", "null transport cannot use credentials"))
    if endpoint_used:
        findings.append(_finding("endpoint_used", "null transport cannot use endpoints"))
    if provider_client_used:
        findings.append(_finding("provider_client_used", "null transport cannot use provider clients"))
    if llm_call_attempted or semantic_generation_attempted:
        findings.append(_finding("semantic_generation_attempted", "null transport cannot call an LLM or perform semantic generation"))
    if tool_calls_attempted or memory_access_attempted or retention_attempted or action_execution_attempted or routing_attempted:
        findings.append(_finding("runtime_authority_attempted", "null transport cannot use tools, memory, retention, actions, or routing"))
    if marker_evidence and _contains_runtime_marker(marker_evidence):
        findings.append(_finding("forbidden_runtime_marker_evidence", "marker evidence contains raw/provider/network/runtime handles or parameters"))
    return tuple(findings)


def _status_for_findings(findings: Sequence[ProviderNullTransportFinding], warnings: Sequence[str], scope: str) -> str:
    codes = {finding.code for finding in findings}
    if "network_review_missing" in codes:
        return ProviderNullTransportStatus.NULL_TRANSPORT_REVIEW_MISSING
    if any(code.startswith("dry_run") for code in codes):
        return ProviderNullTransportStatus.NULL_TRANSPORT_DRY_RUN_NOT_READY
    if any(code.startswith("network_preflight") for code in codes):
        return ProviderNullTransportStatus.NULL_TRANSPORT_PREFLIGHT_NOT_READY
    if "network_review_does_not_satisfy_preflight" in codes or "network_review_missing_null_transport_gate" in codes or "network_review_not_approved" in codes:
        return ProviderNullTransportStatus.NULL_TRANSPORT_REVIEW_NOT_SATISFIED
    if "null_transport_mode_forbidden" in codes or "null_transport_scope_forbidden" in codes or "external_visibility_forbidden" in codes or "digest_chain_incomplete" in codes:
        return _FORBIDDEN_SCOPE_STATUS.get(scope, ProviderNullTransportStatus.NULL_TRANSPORT_INVALID_INPUT)
    if "send_attempt_detected" in codes:
        return ProviderNullTransportStatus.NULL_TRANSPORT_SEND_ATTEMPT_DETECTED
    if "network_attempt_detected" in codes or any(code in codes for code in {"no_network_false", "no_http_false", "no_socket_false"}):
        return ProviderNullTransportStatus.NULL_TRANSPORT_NETWORK_FORBIDDEN
    if "credentials_used" in codes or "no_credentials_false" in codes:
        return ProviderNullTransportStatus.NULL_TRANSPORT_CREDENTIALS_DETECTED
    if "endpoint_used" in codes or "no_endpoint_false" in codes:
        return ProviderNullTransportStatus.NULL_TRANSPORT_ENDPOINT_DETECTED
    if "provider_client_used" in codes or "no_provider_client_false" in codes:
        return ProviderNullTransportStatus.NULL_TRANSPORT_CLIENT_DETECTED
    if findings:
        return ProviderNullTransportStatus.NULL_TRANSPORT_RUNTIME_AUTHORITY_DETECTED
    if warnings:
        return ProviderNullTransportStatus.NULL_TRANSPORT_READY_WITH_WARNINGS
    return ProviderNullTransportStatus.NULL_TRANSPORT_READY


def compute_provider_null_transport_digest(receipt: ProviderNullTransportReceipt | Mapping[str, Any]) -> str:
    data = dict(_mapping(receipt))
    data.pop("null_transport_digest", None)
    data.pop("null_transport_id", None)
    payload = {
        "null_transport_status": data.get("null_transport_status", ""),
        "null_transport_mode": data.get("null_transport_mode", ""),
        "null_transport_scope": data.get("null_transport_scope", ""),
        "transport_reason": data.get("transport_reason", ""),
        "dry_run_id": data.get("dry_run_id", ""),
        "dry_run_status": data.get("dry_run_status", ""),
        "dry_run_digest": data.get("dry_run_digest", ""),
        "network_preflight_id": data.get("network_preflight_id", ""),
        "network_preflight_status": data.get("network_preflight_status", ""),
        "network_preflight_digest": data.get("network_preflight_digest", ""),
        "network_review_receipt_id": data.get("network_review_receipt_id", ""),
        "network_review_status": data.get("network_review_status", ""),
        "network_review_digest": data.get("network_review_digest", ""),
        "provider_family_label": data.get("provider_family_label", ""),
        "model_family_label": data.get("model_family_label", ""),
        "candidate_id": data.get("candidate_id", ""),
        "candidate_digest": data.get("candidate_digest", ""),
        "packet_id": data.get("packet_id", ""),
        "packet_scope": data.get("packet_scope", ""),
        "audit_chain": _stable(data.get("audit_chain", {})),
        "digest_chain_complete": bool(data.get("digest_chain_complete", False)),
        "attempts": {field_name: data.get(field_name, False) for field_name in _ATTEMPT_FIELDS},
        "bytes_sent": int(data.get("bytes_sent", 0) or 0),
        "findings": _stable(data.get("findings", ())),
        "warnings": _stable(data.get("warnings", ())),
        "constraints": _stable(data.get("constraints", ())),
        "rationale": data.get("rationale", ""),
        "markers": {field_name: bool(data.get(field_name, False)) for field_name in _MARKER_FIELDS},
        "boundary": _stable(data.get("boundary", {})),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_provider_null_transport_receipt(
    dry_run_envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any] | None,
    network_preflight: ProviderNetworkEgressPreflight | Mapping[str, Any] | None,
    network_review_receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any] | None,
    *,
    null_transport_mode: str = ProviderNullTransportMode.NULL_TRANSPORT_MODE_NOOP,
    null_transport_scope: str = ProviderNullTransportScope.FUTURE_TRANSPORT_NULL_ADAPTER_GATE,
    transport_reason: str = "metadata-only null transport proof; nothing was sent",
    expected_dry_run_digest: str | None = None,
    expected_preflight_digest: str | None = None,
    expected_review_digest: str | None = None,
    internal_only: bool = True,
    no_network: bool = True,
    no_provider_send: bool = True,
    no_credentials: bool = True,
    no_endpoint: bool = True,
    no_provider_client: bool = True,
    no_http: bool = True,
    no_socket: bool = True,
    no_tools: bool = True,
    no_memory: bool = True,
    no_retention: bool = True,
    no_actions: bool = True,
    no_routing: bool = True,
    no_semantic_generation: bool = True,
    sent: bool = False,
    bytes_sent: int = 0,
    request_created: bool = False,
    response_received: bool = False,
    network_egress_attempted: bool = False,
    provider_send_attempted: bool = False,
    credentials_used: bool = False,
    endpoint_used: bool = False,
    provider_client_used: bool = False,
    socket_opened: bool = False,
    http_request_attempted: bool = False,
    llm_call_attempted: bool = False,
    semantic_generation_attempted: bool = False,
    tool_calls_attempted: bool = False,
    memory_access_attempted: bool = False,
    retention_attempted: bool = False,
    action_execution_attempted: bool = False,
    routing_attempted: bool = False,
    no_raw_payload_marker: bool = True,
    no_runtime_handle_marker: bool = True,
    no_provider_model_params: bool = True,
    marker_evidence: Mapping[str, Any] | None = None,
    marker_overrides: Mapping[str, bool] | None = None,
) -> ProviderNullTransportReceipt:
    dry = _mapping(dry_run_envelope)
    preflight = _mapping(network_preflight)
    review = _mapping(network_review_receipt)
    audit_chain = _build_audit_chain(
        dry_run_envelope,
        network_preflight,
        network_review_receipt,
        expected_dry_run_digest=expected_dry_run_digest,
        expected_preflight_digest=expected_preflight_digest,
        expected_review_digest=expected_review_digest,
    )
    findings = _evaluate_findings(
        dry_run_envelope,
        network_preflight,
        network_review_receipt,
        null_transport_mode=str(null_transport_mode),
        null_transport_scope=str(null_transport_scope),
        audit_chain=audit_chain,
        internal_only=internal_only,
        no_network=no_network,
        no_provider_send=no_provider_send,
        no_credentials=no_credentials,
        no_endpoint=no_endpoint,
        no_provider_client=no_provider_client,
        no_http=no_http,
        no_socket=no_socket,
        no_tools=no_tools,
        no_memory=no_memory,
        no_retention=no_retention,
        no_actions=no_actions,
        no_routing=no_routing,
        no_semantic_generation=no_semantic_generation,
        sent=sent,
        bytes_sent=int(bytes_sent),
        request_created=request_created,
        response_received=response_received,
        network_egress_attempted=network_egress_attempted,
        provider_send_attempted=provider_send_attempted,
        credentials_used=credentials_used,
        endpoint_used=endpoint_used,
        provider_client_used=provider_client_used,
        socket_opened=socket_opened,
        http_request_attempted=http_request_attempted,
        llm_call_attempted=llm_call_attempted,
        semantic_generation_attempted=semantic_generation_attempted,
        tool_calls_attempted=tool_calls_attempted,
        memory_access_attempted=memory_access_attempted,
        retention_attempted=retention_attempted,
        action_execution_attempted=action_execution_attempted,
        routing_attempted=routing_attempted,
        no_raw_payload_marker=no_raw_payload_marker,
        no_runtime_handle_marker=no_runtime_handle_marker,
        no_provider_model_params=no_provider_model_params,
        marker_evidence=marker_evidence,
    )
    warnings = tuple(str(item) for source in (dry, preflight, review) for item in (source.get("warnings", ()) or ()))
    if preflight.get("preflight_status") == ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_REVIEW_REQUIRED:
        warnings = warnings + ("network preflight required Phase 88 review before null transport",)
    marker_values = {field_name: True for field_name in _MARKER_FIELDS}
    if marker_overrides:
        marker_values.update({str(key): bool(value) for key, value in marker_overrides.items() if str(key) in marker_values})
    marker_findings = tuple(_finding("null_transport_marker_missing", f"marker {key} must remain true") for key, value in marker_values.items() if not value)
    findings = tuple(findings) + marker_findings
    status = _status_for_findings(findings, warnings, str(null_transport_scope))
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "null transport adapter proved that no transport was attempted; network and provider send remain forbidden"
    receipt = ProviderNullTransportReceipt(
        null_transport_id="",
        null_transport_status=status,
        null_transport_mode=str(null_transport_mode),
        null_transport_scope=str(null_transport_scope),
        transport_reason=str(transport_reason)[:500],
        dry_run_id=str(dry.get("dry_run_id", preflight.get("dry_run_id", review.get("dry_run_id", "")))),
        dry_run_status=str(dry.get("dry_run_status", preflight.get("dry_run_status", ""))),
        dry_run_digest=str(dry.get("dry_run_digest", preflight.get("dry_run_digest", review.get("dry_run_digest", "")))),
        network_preflight_id=str(preflight.get("preflight_id", review.get("network_preflight_id", ""))),
        network_preflight_status=str(preflight.get("preflight_status", review.get("network_preflight_status", ""))),
        network_preflight_digest=str(preflight.get("preflight_digest", review.get("network_preflight_digest", ""))),
        network_review_receipt_id=str(review.get("review_receipt_id", "")),
        network_review_status=str(review.get("review_status", "")),
        network_review_digest=str(review.get("review_digest", "")),
        provider_family_label=str(dry.get("provider_family_label", preflight.get("provider_family_label", review.get("provider_family_label", "")))),
        model_family_label=str(dry.get("model_family_label", preflight.get("model_family_label", review.get("model_family_label", "")))),
        candidate_id=str(dry.get("candidate_id", preflight.get("candidate_id", review.get("candidate_id", "")))),
        candidate_digest=str(dry.get("candidate_digest", preflight.get("candidate_digest", review.get("candidate_digest", "")))),
        packet_id=str(dry.get("packet_id", preflight.get("packet_id", review.get("packet_id", "")))),
        packet_scope=str(dry.get("packet_scope", preflight.get("packet_scope", review.get("packet_scope", "")))),
        audit_chain=audit_chain,
        digest_chain_complete=audit_chain.complete,
        sent=False if not sent else bool(sent),
        bytes_sent=0 if int(bytes_sent) == 0 else int(bytes_sent),
        request_created=bool(request_created),
        response_received=bool(response_received),
        network_egress_attempted=bool(network_egress_attempted),
        provider_send_attempted=bool(provider_send_attempted),
        credentials_used=bool(credentials_used),
        endpoint_used=bool(endpoint_used),
        provider_client_used=bool(provider_client_used),
        socket_opened=bool(socket_opened),
        http_request_attempted=bool(http_request_attempted),
        llm_call_attempted=bool(llm_call_attempted),
        semantic_generation_attempted=bool(semantic_generation_attempted),
        tool_calls_attempted=bool(tool_calls_attempted),
        memory_access_attempted=bool(memory_access_attempted),
        retention_attempted=bool(retention_attempted),
        action_execution_attempted=bool(action_execution_attempted),
        routing_attempted=bool(routing_attempted),
        findings=tuple(findings),
        warnings=tuple(warnings),
        constraints=_constraints(),
        rationale=rationale[:1000],
        null_transport_digest="",
        **marker_values,
    )
    digest = compute_provider_null_transport_digest(receipt)
    return replace(receipt, null_transport_id=f"provider-null-transport:{receipt.dry_run_id or 'missing'}:{digest[:16]}", null_transport_digest=digest)


def validate_provider_null_transport_receipt(receipt: ProviderNullTransportReceipt | Mapping[str, Any]) -> tuple[ProviderNullTransportFinding, ...]:
    data = _mapping(receipt)
    findings: list[ProviderNullTransportFinding] = []
    if not data:
        return (_finding("null_transport_receipt_missing", "ProviderNullTransportReceipt is required"),)
    if str(data.get("null_transport_status", "")) not in {
        ProviderNullTransportStatus.NULL_TRANSPORT_READY,
        ProviderNullTransportStatus.NULL_TRANSPORT_READY_WITH_WARNINGS,
        ProviderNullTransportStatus.NULL_TRANSPORT_BLOCKED,
        ProviderNullTransportStatus.NULL_TRANSPORT_INVALID_INPUT,
        ProviderNullTransportStatus.NULL_TRANSPORT_REVIEW_MISSING,
        ProviderNullTransportStatus.NULL_TRANSPORT_REVIEW_NOT_SATISFIED,
        ProviderNullTransportStatus.NULL_TRANSPORT_PREFLIGHT_NOT_READY,
        ProviderNullTransportStatus.NULL_TRANSPORT_DRY_RUN_NOT_READY,
        ProviderNullTransportStatus.NULL_TRANSPORT_NETWORK_FORBIDDEN,
        ProviderNullTransportStatus.NULL_TRANSPORT_CREDENTIALS_DETECTED,
        ProviderNullTransportStatus.NULL_TRANSPORT_ENDPOINT_DETECTED,
        ProviderNullTransportStatus.NULL_TRANSPORT_CLIENT_DETECTED,
        ProviderNullTransportStatus.NULL_TRANSPORT_RUNTIME_AUTHORITY_DETECTED,
        ProviderNullTransportStatus.NULL_TRANSPORT_SEND_ATTEMPT_DETECTED,
    }:
        findings.append(_finding("null_transport_status_unknown", "unknown null transport status"))
    for field_name in _MARKER_FIELDS:
        if data.get(field_name) is not True:
            findings.append(_finding("null_transport_marker_missing", f"{field_name} must be true"))
    if data.get("sent") is not False or int(data.get("bytes_sent", -1) or 0) != 0:
        findings.append(_finding("send_attempt_detected", "receipt must prove sent is false and bytes_sent is zero"))
    for field_name in _ATTEMPT_FIELDS:
        if field_name == "sent":
            continue
        if data.get(field_name) is not False:
            findings.append(_finding("attempt_marker_detected", f"{field_name} must be false"))
    if compute_provider_null_transport_digest(receipt) != str(data.get("null_transport_digest", "")):
        findings.append(_finding("null_transport_digest_mismatch", "null transport digest does not match stable metadata"))
    return tuple(findings)


def provider_null_transport_sent_nothing(receipt: ProviderNullTransportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("null_transport_status") in {ProviderNullTransportStatus.NULL_TRANSPORT_READY, ProviderNullTransportStatus.NULL_TRANSPORT_READY_WITH_WARNINGS}
        and data.get("sent") is False
        and int(data.get("bytes_sent", -1) or 0) == 0
        and data.get("request_created") is False
        and data.get("response_received") is False
        and data.get("network_egress_attempted") is False
        and data.get("provider_send_attempted") is False
        and data.get("http_request_attempted") is False
        and data.get("socket_opened") is False
        and data.get("null_transport_sent_nothing") is True
        and data.get("does_not_make_network_calls") is True
        and data.get("does_not_send_to_provider") is True
    )


def provider_null_transport_has_no_network(receipt: ProviderNullTransportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        provider_null_transport_sent_nothing(receipt)
        and data.get("network_egress_attempted") is False
        and data.get("socket_opened") is False
        and data.get("http_request_attempted") is False
        and data.get("network_egress_forbidden") is True
        and data.get("socket_forbidden") is True
        and data.get("http_forbidden") is True
        and data.get("does_not_make_network_calls") is True
    )


def provider_null_transport_has_no_provider_credentials(receipt: ProviderNullTransportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data.get("credentials_used") is False and data.get("credentials_forbidden") is True)


def provider_null_transport_has_no_endpoint(receipt: ProviderNullTransportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data.get("endpoint_used") is False and data.get("endpoint_forbidden") is True)


def provider_null_transport_has_no_provider_client(receipt: ProviderNullTransportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data.get("provider_client_used") is False and data.get("provider_client_forbidden") is True)


def provider_null_transport_has_no_runtime_authority(receipt: ProviderNullTransportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("llm_call_attempted") is False
        and data.get("semantic_generation_attempted") is False
        and data.get("tool_calls_attempted") is False
        and data.get("memory_access_attempted") is False
        and data.get("retention_attempted") is False
        and data.get("action_execution_attempted") is False
        and data.get("routing_attempted") is False
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


def provider_null_transport_preserves_network_egress_review(
    receipt: ProviderNullTransportReceipt | Mapping[str, Any],
    review_receipt: ProviderNetworkEgressReviewReceipt | Mapping[str, Any] | None,
) -> bool:
    data = _mapping(receipt)
    review = _mapping(review_receipt)
    return bool(
        data
        and review
        and data.get("network_review_receipt_id") == review.get("review_receipt_id")
        and data.get("network_review_digest") == review.get("review_digest")
        and provider_network_egress_review_approves_future_null_transport_gate(review_receipt)
    )


def provider_null_transport_digest_chain_complete(receipt: ProviderNullTransportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    chain = _mapping(data.get("audit_chain", {}))
    return bool(data.get("digest_chain_complete") is True and chain.get("complete") is True and not chain.get("missing", ()) and not chain.get("mismatches", ()))


def explain_provider_null_transport_findings(receipt_or_findings: ProviderNullTransportReceipt | Mapping[str, Any] | Sequence[ProviderNullTransportFinding]) -> tuple[str, ...]:
    if isinstance(receipt_or_findings, Sequence) and not isinstance(receipt_or_findings, (str, bytes, Mapping)):
        findings = receipt_or_findings
    else:
        findings = _mapping(receipt_or_findings).get("findings", ()) or ()
    return tuple(f"{_mapping(item).get('severity', '')}:{_mapping(item).get('code', '')}:{_mapping(item).get('detail', '')}" for item in findings)


def summarize_provider_null_transport_receipt(receipt: ProviderNullTransportReceipt | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(receipt)
    return {
        "null_transport_id": str(data.get("null_transport_id", "")),
        "null_transport_status": str(data.get("null_transport_status", "")),
        "null_transport_mode": str(data.get("null_transport_mode", "")),
        "null_transport_scope": str(data.get("null_transport_scope", "")),
        "dry_run_id": str(data.get("dry_run_id", "")),
        "network_preflight_id": str(data.get("network_preflight_id", "")),
        "network_review_receipt_id": str(data.get("network_review_receipt_id", "")),
        "digest_chain_complete": bool(data.get("digest_chain_complete", False)),
        "sent": bool(data.get("sent", True)),
        "bytes_sent": int(data.get("bytes_sent", -1) or 0),
        "request_created": bool(data.get("request_created", True)),
        "response_received": bool(data.get("response_received", True)),
        "network_egress_attempted": bool(data.get("network_egress_attempted", True)),
        "provider_send_attempted": bool(data.get("provider_send_attempted", True)),
        "finding_count": len(tuple(data.get("findings", ()) or ())),
        "warning_count": len(tuple(data.get("warnings", ()) or ())),
        "null_transport_digest": str(data.get("null_transport_digest", "")),
        "provider_null_transport_only": bool(data.get("provider_null_transport_only", False)),
        "null_transport_sent_nothing": bool(data.get("null_transport_sent_nothing", False)),
        "does_not_call_llm": bool(data.get("does_not_call_llm", False)),
        "does_not_send_to_provider": bool(data.get("does_not_send_to_provider", False)),
        "does_not_make_network_calls": bool(data.get("does_not_make_network_calls", False)),
    }
