from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_provider_null_transport import (
    ProviderNullTransportReceipt,
    ProviderNullTransportStatus,
    compute_provider_null_transport_digest,
    provider_null_transport_has_no_endpoint,
    provider_null_transport_has_no_network,
    provider_null_transport_has_no_provider_client,
    provider_null_transport_has_no_provider_credentials,
    provider_null_transport_has_no_runtime_authority,
    provider_null_transport_sent_nothing,
)


class ProviderTransportRegistryStatus:
    TRANSPORT_REGISTRY_NULL_ONLY = "transport_registry_null_only"
    TRANSPORT_REGISTRY_INVALID = "transport_registry_invalid"
    TRANSPORT_REGISTRY_FORBIDDEN_ADAPTER_REGISTERED = "transport_registry_forbidden_adapter_registered"
    TRANSPORT_REGISTRY_RUNTIME_AUTHORITY_DETECTED = "transport_registry_runtime_authority_detected"


class ProviderTransportAdapterKind:
    PROVIDER_TRANSPORT_NULL_ADAPTER = "provider_transport_null_adapter"
    PROVIDER_TRANSPORT_OPENAI_LIVE_ADAPTER_FORBIDDEN = "provider_transport_openai_live_adapter_forbidden"
    PROVIDER_TRANSPORT_HTTP_ADAPTER_FORBIDDEN = "provider_transport_http_adapter_forbidden"
    PROVIDER_TRANSPORT_SOCKET_ADAPTER_FORBIDDEN = "provider_transport_socket_adapter_forbidden"
    PROVIDER_TRANSPORT_LOCAL_MODEL_LIVE_ADAPTER_FORBIDDEN = "provider_transport_local_model_live_adapter_forbidden"
    PROVIDER_TRANSPORT_CUSTOM_ENDPOINT_ADAPTER_FORBIDDEN = "provider_transport_custom_endpoint_adapter_forbidden"
    PROVIDER_TRANSPORT_UNKNOWN_FORBIDDEN = "provider_transport_unknown_forbidden"


class ProviderTransportSelectionStatus:
    TRANSPORT_SELECTION_NULL_READY = "transport_selection_null_ready"
    TRANSPORT_SELECTION_NULL_READY_WITH_WARNINGS = "transport_selection_null_ready_with_warnings"
    TRANSPORT_SELECTION_BLOCKED = "transport_selection_blocked"
    TRANSPORT_SELECTION_INVALID_INPUT = "transport_selection_invalid_input"
    TRANSPORT_SELECTION_ADAPTER_UNREGISTERED = "transport_selection_adapter_unregistered"
    TRANSPORT_SELECTION_ADAPTER_FORBIDDEN = "transport_selection_adapter_forbidden"
    TRANSPORT_SELECTION_NULL_TRANSPORT_NOT_READY = "transport_selection_null_transport_not_ready"
    TRANSPORT_SELECTION_SEND_ATTEMPT_DETECTED = "transport_selection_send_attempt_detected"
    TRANSPORT_SELECTION_NETWORK_DETECTED = "transport_selection_network_detected"
    TRANSPORT_SELECTION_CREDENTIALS_DETECTED = "transport_selection_credentials_detected"
    TRANSPORT_SELECTION_ENDPOINT_DETECTED = "transport_selection_endpoint_detected"
    TRANSPORT_SELECTION_CLIENT_DETECTED = "transport_selection_client_detected"
    TRANSPORT_SELECTION_RUNTIME_AUTHORITY_DETECTED = "transport_selection_runtime_authority_detected"


@dataclass(frozen=True)
class ProviderTransportRegistryFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderTransportRegistryConstraint:
    code: str
    detail: str
    required: bool = True


@dataclass(frozen=True)
class ProviderTransportRegistryAuditChain:
    registry_id: str = ""
    registry_digest: str = ""
    null_transport_id: str = ""
    null_transport_digest: str = ""
    dry_run_id: str = ""
    dry_run_digest: str = ""
    network_preflight_id: str = ""
    network_preflight_digest: str = ""
    network_review_receipt_id: str = ""
    network_review_digest: str = ""
    candidate_id: str = ""
    candidate_digest: str = ""
    packet_id: str = ""
    packet_scope: str = ""
    complete: bool = False
    mismatches: tuple[str, ...] = field(default_factory=tuple)
    missing: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProviderTransportRegistryManifest:
    registry_id: str
    registry_status: str
    registered_adapter_kinds: tuple[str, ...]
    forbidden_adapter_kinds: tuple[str, ...]
    default_adapter_kind: str
    null_adapter_required: bool
    live_provider_adapters_registered: bool
    network_adapters_registered: bool
    credentialed_adapters_registered: bool
    endpoint_adapters_registered: bool
    socket_adapters_registered: bool
    http_adapters_registered: bool
    semantic_generation_adapters_registered: bool
    runtime_authority_adapters_registered: bool
    findings: tuple[ProviderTransportRegistryFinding, ...]
    constraints: tuple[ProviderTransportRegistryConstraint, ...]
    rationale: str
    registry_digest: str
    provider_transport_registry_only: bool = True
    null_transport_only: bool = True
    live_provider_adapters_forbidden: bool = True
    network_adapters_forbidden: bool = True
    credentialed_adapters_forbidden: bool = True
    endpoint_adapters_forbidden: bool = True
    socket_adapters_forbidden: bool = True
    http_adapters_forbidden: bool = True
    semantic_generation_adapters_forbidden: bool = True
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


@dataclass(frozen=True)
class ProviderTransportSelectionReceipt:
    transport_selection_id: str
    selection_status: str
    registry_id: str
    registry_status: str
    registry_digest: str
    requested_adapter_kind: str
    selected_adapter_kind: str
    null_transport_id: str
    null_transport_status: str
    null_transport_digest: str
    dry_run_id: str
    dry_run_digest: str
    network_preflight_id: str
    network_preflight_digest: str
    network_review_receipt_id: str
    network_review_digest: str
    candidate_id: str
    candidate_digest: str
    packet_id: str
    packet_scope: str
    audit_chain: ProviderTransportRegistryAuditChain
    digest_chain_complete: bool
    sent: bool
    bytes_sent: int
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
    findings: tuple[ProviderTransportRegistryFinding, ...]
    warnings: tuple[str, ...]
    constraints: tuple[ProviderTransportRegistryConstraint, ...]
    rationale: str
    selection_digest: str
    provider_transport_selection_only: bool = True
    selected_null_transport_only: bool = True
    live_provider_transport_forbidden: bool = True
    network_transport_forbidden: bool = True
    credentialed_transport_forbidden: bool = True
    endpoint_transport_forbidden: bool = True
    socket_transport_forbidden: bool = True
    http_transport_forbidden: bool = True
    null_transport_sent_nothing: bool = True
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


_ALLOWED_ADAPTER = ProviderTransportAdapterKind.PROVIDER_TRANSPORT_NULL_ADAPTER
_FORBIDDEN_ADAPTERS = (
    ProviderTransportAdapterKind.PROVIDER_TRANSPORT_OPENAI_LIVE_ADAPTER_FORBIDDEN,
    ProviderTransportAdapterKind.PROVIDER_TRANSPORT_HTTP_ADAPTER_FORBIDDEN,
    ProviderTransportAdapterKind.PROVIDER_TRANSPORT_SOCKET_ADAPTER_FORBIDDEN,
    ProviderTransportAdapterKind.PROVIDER_TRANSPORT_LOCAL_MODEL_LIVE_ADAPTER_FORBIDDEN,
    ProviderTransportAdapterKind.PROVIDER_TRANSPORT_CUSTOM_ENDPOINT_ADAPTER_FORBIDDEN,
    ProviderTransportAdapterKind.PROVIDER_TRANSPORT_UNKNOWN_FORBIDDEN,
)
_READY_NULL_STATUSES = frozenset(
    {
        ProviderNullTransportStatus.NULL_TRANSPORT_READY,
        ProviderNullTransportStatus.NULL_TRANSPORT_READY_WITH_WARNINGS,
    }
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
_MARKER_FIELDS = (
    "provider_transport_selection_only",
    "selected_null_transport_only",
    "live_provider_transport_forbidden",
    "network_transport_forbidden",
    "credentialed_transport_forbidden",
    "endpoint_transport_forbidden",
    "socket_transport_forbidden",
    "http_transport_forbidden",
    "null_transport_sent_nothing",
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
_REGISTRY_MARKER_FIELDS = (
    "provider_transport_registry_only",
    "null_transport_only",
    "live_provider_adapters_forbidden",
    "network_adapters_forbidden",
    "credentialed_adapters_forbidden",
    "endpoint_adapters_forbidden",
    "socket_adapters_forbidden",
    "http_adapters_forbidden",
    "semantic_generation_adapters_forbidden",
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


def _finding(code: str, detail: str, severity: str = "blocker") -> ProviderTransportRegistryFinding:
    return ProviderTransportRegistryFinding(code=code, detail=detail, severity=severity)


def _constraints() -> tuple[ProviderTransportRegistryConstraint, ...]:
    return (
        ProviderTransportRegistryConstraint("null_registry_only", "Phase 90 registers only the Phase 89 null transport adapter"),
        ProviderTransportRegistryConstraint("real_transports_forbidden", "live provider, network, HTTP, socket, SDK, credential, endpoint, and custom transports remain unregistered"),
        ProviderTransportRegistryConstraint("selection_metadata_only", "selection receipts contain only stable metadata and upstream digest linkage"),
        ProviderTransportRegistryConstraint("no_send", "selection must preserve sent=false and bytes_sent=0"),
        ProviderTransportRegistryConstraint("no_runtime_authority", "LLM, memory, tools, actions, retention, routing, admission, and execution remain forbidden"),
    )


def _stable_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(_stable(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _registry_digest_payload(manifest: ProviderTransportRegistryManifest | Mapping[str, Any]) -> dict[str, Any]:
    data = dict(_mapping(manifest))
    data.pop("registry_id", None)
    data.pop("registry_digest", None)
    return data


def compute_provider_transport_registry_digest(manifest: ProviderTransportRegistryManifest | Mapping[str, Any]) -> str:
    return _stable_digest(_registry_digest_payload(manifest))


def _selection_digest_payload(receipt: ProviderTransportSelectionReceipt | Mapping[str, Any]) -> dict[str, Any]:
    data = dict(_mapping(receipt))
    data.pop("transport_selection_id", None)
    data.pop("selection_digest", None)
    return data


def compute_provider_transport_selection_digest(receipt: ProviderTransportSelectionReceipt | Mapping[str, Any]) -> str:
    return _stable_digest(_selection_digest_payload(receipt))


def build_provider_transport_registry_manifest(
    *,
    registered_adapter_kinds: Sequence[str] | None = None,
    forbidden_adapter_kinds: Sequence[str] | None = None,
    default_adapter_kind: str = _ALLOWED_ADAPTER,
    null_adapter_required: bool = True,
    live_provider_adapters_registered: bool = False,
    network_adapters_registered: bool = False,
    credentialed_adapters_registered: bool = False,
    endpoint_adapters_registered: bool = False,
    socket_adapters_registered: bool = False,
    http_adapters_registered: bool = False,
    semantic_generation_adapters_registered: bool = False,
    runtime_authority_adapters_registered: bool = False,
    marker_overrides: Mapping[str, bool] | None = None,
) -> ProviderTransportRegistryManifest:
    registered = tuple(str(kind) for kind in (registered_adapter_kinds if registered_adapter_kinds is not None else (_ALLOWED_ADAPTER,)))
    forbidden = tuple(str(kind) for kind in (forbidden_adapter_kinds if forbidden_adapter_kinds is not None else _FORBIDDEN_ADAPTERS))
    findings: list[ProviderTransportRegistryFinding] = []
    forbidden_registered = tuple(kind for kind in registered if kind != _ALLOWED_ADAPTER)
    if not registered:
        findings.append(_finding("registry_no_adapters", "registry must include the Phase 89 null transport adapter"))
    if _ALLOWED_ADAPTER not in registered and null_adapter_required:
        findings.append(_finding("null_adapter_missing", "provider_transport_null_adapter is required"))
    if forbidden_registered:
        findings.append(_finding("forbidden_adapter_registered", "only provider_transport_null_adapter may be registered"))
    if str(default_adapter_kind) != _ALLOWED_ADAPTER or str(default_adapter_kind) not in registered:
        findings.append(_finding("default_adapter_invalid", "default adapter must be the registered null adapter"))
    runtime_flags = {
        "live_provider_adapters_registered": live_provider_adapters_registered,
        "network_adapters_registered": network_adapters_registered,
        "credentialed_adapters_registered": credentialed_adapters_registered,
        "endpoint_adapters_registered": endpoint_adapters_registered,
        "socket_adapters_registered": socket_adapters_registered,
        "http_adapters_registered": http_adapters_registered,
        "semantic_generation_adapters_registered": semantic_generation_adapters_registered,
        "runtime_authority_adapters_registered": runtime_authority_adapters_registered,
    }
    for name, value in runtime_flags.items():
        if value:
            findings.append(_finding(name, f"{name} must remain false in the null-only registry"))
    marker_values = {field_name: True for field_name in _REGISTRY_MARKER_FIELDS}
    if marker_overrides:
        marker_values.update({str(key): bool(value) for key, value in marker_overrides.items() if str(key) in marker_values})
    for name, value in marker_values.items():
        if not value:
            findings.append(_finding("registry_marker_missing", f"{name} must remain true"))
    if any(runtime_flags.values()):
        status = ProviderTransportRegistryStatus.TRANSPORT_REGISTRY_RUNTIME_AUTHORITY_DETECTED
    elif forbidden_registered:
        status = ProviderTransportRegistryStatus.TRANSPORT_REGISTRY_FORBIDDEN_ADAPTER_REGISTERED
    elif findings:
        status = ProviderTransportRegistryStatus.TRANSPORT_REGISTRY_INVALID
    else:
        status = ProviderTransportRegistryStatus.TRANSPORT_REGISTRY_NULL_ONLY
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "transport registry is metadata-only and registers only the Phase 89 null transport adapter"
    manifest = ProviderTransportRegistryManifest(
        registry_id="",
        registry_status=status,
        registered_adapter_kinds=registered,
        forbidden_adapter_kinds=forbidden,
        default_adapter_kind=str(default_adapter_kind),
        null_adapter_required=bool(null_adapter_required),
        live_provider_adapters_registered=bool(live_provider_adapters_registered),
        network_adapters_registered=bool(network_adapters_registered),
        credentialed_adapters_registered=bool(credentialed_adapters_registered),
        endpoint_adapters_registered=bool(endpoint_adapters_registered),
        socket_adapters_registered=bool(socket_adapters_registered),
        http_adapters_registered=bool(http_adapters_registered),
        semantic_generation_adapters_registered=bool(semantic_generation_adapters_registered),
        runtime_authority_adapters_registered=bool(runtime_authority_adapters_registered),
        findings=tuple(findings),
        constraints=_constraints(),
        rationale=rationale[:1000],
        registry_digest="",
        **marker_values,
    )
    digest = compute_provider_transport_registry_digest(manifest)
    return replace(manifest, registry_id=f"provider-transport-registry:{digest[:16]}", registry_digest=digest)


def _contains_runtime_marker(value: Any) -> bool:
    text = json.dumps(_stable(value), sort_keys=True, ensure_ascii=True, default=str).lower()
    return any(marker in text for marker in _RUNTIME_MARKER_KEYS)


def _build_audit_chain(
    registry_manifest: Any,
    null_transport_receipt: Any,
    *,
    expected_null_transport_digest: str | None,
) -> ProviderTransportRegistryAuditChain:
    registry = _mapping(registry_manifest)
    null = _mapping(null_transport_receipt)
    missing: list[str] = []
    mismatches: list[str] = []
    required = {
        "registry_id": registry.get("registry_id", ""),
        "registry_digest": registry.get("registry_digest", ""),
        "null_transport_id": null.get("null_transport_id", ""),
        "null_transport_digest": null.get("null_transport_digest", ""),
        "dry_run_id": null.get("dry_run_id", ""),
        "dry_run_digest": null.get("dry_run_digest", ""),
        "network_preflight_id": null.get("network_preflight_id", ""),
        "network_preflight_digest": null.get("network_preflight_digest", ""),
        "network_review_receipt_id": null.get("network_review_receipt_id", ""),
        "network_review_digest": null.get("network_review_digest", ""),
        "candidate_id": null.get("candidate_id", ""),
        "candidate_digest": null.get("candidate_digest", ""),
    }
    for key, value in required.items():
        if not value:
            missing.append(key)
    if registry and registry.get("registry_digest") != compute_provider_transport_registry_digest(registry_manifest):
        mismatches.append("registry_digest")
    if null and null.get("null_transport_digest") != compute_provider_null_transport_digest(null_transport_receipt):
        mismatches.append("null_transport_digest")
    if expected_null_transport_digest is not None and str(expected_null_transport_digest) != str(null.get("null_transport_digest", "")):
        mismatches.append("expected_null_transport_digest")
    return ProviderTransportRegistryAuditChain(
        registry_id=str(required["registry_id"]),
        registry_digest=str(required["registry_digest"]),
        null_transport_id=str(required["null_transport_id"]),
        null_transport_digest=str(required["null_transport_digest"]),
        dry_run_id=str(required["dry_run_id"]),
        dry_run_digest=str(required["dry_run_digest"]),
        network_preflight_id=str(required["network_preflight_id"]),
        network_preflight_digest=str(required["network_preflight_digest"]),
        network_review_receipt_id=str(required["network_review_receipt_id"]),
        network_review_digest=str(required["network_review_digest"]),
        candidate_id=str(required["candidate_id"]),
        candidate_digest=str(required["candidate_digest"]),
        packet_id=str(null.get("packet_id", "")),
        packet_scope=str(null.get("packet_scope", "")),
        complete=not missing and not mismatches,
        mismatches=tuple(mismatches),
        missing=tuple(missing),
    )


def _status_for_findings(findings: Sequence[ProviderTransportRegistryFinding], warnings: Sequence[str], null_status: str) -> str:
    if not findings:
        if null_status == ProviderNullTransportStatus.NULL_TRANSPORT_READY_WITH_WARNINGS or warnings:
            return ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_READY_WITH_WARNINGS
        return ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_READY
    codes = {finding.code for finding in findings}
    if "null_transport_missing" in codes:
        return ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_TRANSPORT_NOT_READY
    if codes.intersection({"registry_missing", "registry_invalid", "digest_chain_incomplete", "digest_chain_mismatch"}):
        return ProviderTransportSelectionStatus.TRANSPORT_SELECTION_INVALID_INPUT
    if "requested_adapter_forbidden" in codes:
        return ProviderTransportSelectionStatus.TRANSPORT_SELECTION_ADAPTER_FORBIDDEN
    if "network_detected" in codes:
        return ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NETWORK_DETECTED
    if "send_attempt_detected" in codes:
        return ProviderTransportSelectionStatus.TRANSPORT_SELECTION_SEND_ATTEMPT_DETECTED
    if "credentials_detected" in codes:
        return ProviderTransportSelectionStatus.TRANSPORT_SELECTION_CREDENTIALS_DETECTED
    if "endpoint_detected" in codes:
        return ProviderTransportSelectionStatus.TRANSPORT_SELECTION_ENDPOINT_DETECTED
    if "client_detected" in codes:
        return ProviderTransportSelectionStatus.TRANSPORT_SELECTION_CLIENT_DETECTED
    if codes.intersection({"runtime_authority_detected", "raw_payload_marker_detected", "runtime_handle_marker_detected", "provider_model_params_detected"}):
        return ProviderTransportSelectionStatus.TRANSPORT_SELECTION_RUNTIME_AUTHORITY_DETECTED
    if "null_transport_not_ready" in codes or "null_transport_missing" in codes:
        return ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_TRANSPORT_NOT_READY
    if "requested_adapter_unregistered" in codes:
        return ProviderTransportSelectionStatus.TRANSPORT_SELECTION_ADAPTER_UNREGISTERED
    return ProviderTransportSelectionStatus.TRANSPORT_SELECTION_BLOCKED


def select_provider_transport_adapter(
    registry_manifest: ProviderTransportRegistryManifest | Mapping[str, Any] | None,
    requested_adapter_kind: str,
    null_transport_receipt: ProviderNullTransportReceipt | Mapping[str, Any] | None,
    *,
    expected_null_transport_digest: str | None = None,
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
) -> ProviderTransportSelectionReceipt:
    registry = _mapping(registry_manifest)
    null = _mapping(null_transport_receipt)
    audit_chain = _build_audit_chain(registry_manifest, null_transport_receipt, expected_null_transport_digest=expected_null_transport_digest)
    findings: list[ProviderTransportRegistryFinding] = []
    if not registry:
        findings.append(_finding("registry_missing", "ProviderTransportRegistryManifest is required"))
    elif not provider_transport_registry_is_null_only(registry_manifest):
        findings.append(_finding("registry_invalid", "registry must be valid and null-only"))
    if not null:
        findings.append(_finding("null_transport_missing", "Phase 89 ProviderNullTransportReceipt is required"))
    elif str(null.get("null_transport_status", "")) not in _READY_NULL_STATUSES:
        findings.append(_finding("null_transport_not_ready", "null transport receipt must be ready or ready with warnings"))
    requested = str(requested_adapter_kind)
    if requested != _ALLOWED_ADAPTER:
        if requested in _FORBIDDEN_ADAPTERS or requested.endswith("_forbidden"):
            findings.append(_finding("requested_adapter_forbidden", "only provider_transport_null_adapter may be selected"))
        else:
            findings.append(_finding("requested_adapter_unregistered", "requested adapter is not registered in the Phase 90 null-only registry"))
    elif registry and requested not in tuple(registry.get("registered_adapter_kinds", ())):
        findings.append(_finding("requested_adapter_unregistered", "requested null adapter is not registered"))
    null_status = str(null.get("null_transport_status", ""))
    if null and null_status == ProviderNullTransportStatus.NULL_TRANSPORT_SEND_ATTEMPT_DETECTED:
        findings.append(_finding("send_attempt_detected", "null transport receipt recorded a send attempt marker"))
    if null and null_status == ProviderNullTransportStatus.NULL_TRANSPORT_NETWORK_FORBIDDEN:
        findings.append(_finding("network_detected", "null transport receipt recorded a network/socket/HTTP marker"))
    if null and null_status == ProviderNullTransportStatus.NULL_TRANSPORT_CREDENTIALS_DETECTED:
        findings.append(_finding("credentials_detected", "null transport receipt recorded credential usage"))
    if null and null_status == ProviderNullTransportStatus.NULL_TRANSPORT_ENDPOINT_DETECTED:
        findings.append(_finding("endpoint_detected", "null transport receipt recorded endpoint usage"))
    if null and null_status == ProviderNullTransportStatus.NULL_TRANSPORT_CLIENT_DETECTED:
        findings.append(_finding("client_detected", "null transport receipt recorded provider-client usage"))
    if null and null_status == ProviderNullTransportStatus.NULL_TRANSPORT_RUNTIME_AUTHORITY_DETECTED:
        findings.append(_finding("runtime_authority_detected", "null transport receipt recorded runtime authority"))
    if null_status in _READY_NULL_STATUSES:
        if null and not provider_null_transport_sent_nothing(null_transport_receipt):
            findings.append(_finding("send_attempt_detected", "null transport receipt must prove zero sends and zero bytes"))
        if null and not provider_null_transport_has_no_network(null_transport_receipt):
            findings.append(_finding("network_detected", "null transport receipt must preserve no network, socket, and HTTP activity"))
        if null and not provider_null_transport_has_no_provider_credentials(null_transport_receipt):
            findings.append(_finding("credentials_detected", "null transport receipt must preserve credential absence"))
        if null and not provider_null_transport_has_no_endpoint(null_transport_receipt):
            findings.append(_finding("endpoint_detected", "null transport receipt must preserve endpoint absence"))
        if null and not provider_null_transport_has_no_provider_client(null_transport_receipt):
            findings.append(_finding("client_detected", "null transport receipt must preserve provider-client absence"))
        if null and not provider_null_transport_has_no_runtime_authority(null_transport_receipt):
            findings.append(_finding("runtime_authority_detected", "null transport receipt must preserve no runtime authority"))
    if audit_chain.missing:
        findings.append(_finding("digest_chain_incomplete", "required registry/null/upstream IDs and digests must be present"))
    if audit_chain.mismatches:
        findings.append(_finding("digest_chain_mismatch", "registry or null transport digest linkage must match"))
    if not internal_only:
        findings.append(_finding("runtime_authority_detected", "selection must remain internal-only metadata"))
    false_flags = {
        "no_network": no_network,
        "no_provider_send": no_provider_send,
        "no_credentials": no_credentials,
        "no_endpoint": no_endpoint,
        "no_provider_client": no_provider_client,
        "no_http": no_http,
        "no_socket": no_socket,
        "no_tools": no_tools,
        "no_memory": no_memory,
        "no_retention": no_retention,
        "no_actions": no_actions,
        "no_routing": no_routing,
        "no_semantic_generation": no_semantic_generation,
    }
    for flag_name, value in false_flags.items():
        if not value:
            if flag_name in {"no_network", "no_http", "no_socket"}:
                findings.append(_finding("network_detected", f"{flag_name} must remain true"))
            elif flag_name == "no_provider_send":
                findings.append(_finding("send_attempt_detected", f"{flag_name} must remain true"))
            elif flag_name == "no_credentials":
                findings.append(_finding("credentials_detected", f"{flag_name} must remain true"))
            elif flag_name == "no_endpoint":
                findings.append(_finding("endpoint_detected", f"{flag_name} must remain true"))
            elif flag_name == "no_provider_client":
                findings.append(_finding("client_detected", f"{flag_name} must remain true"))
            else:
                findings.append(_finding("runtime_authority_detected", f"{flag_name} must remain true"))
    if sent or int(bytes_sent) != 0 or provider_send_attempted:
        findings.append(_finding("send_attempt_detected", "selection input must not attempt send or move bytes"))
    if network_egress_attempted or socket_opened or http_request_attempted:
        findings.append(_finding("network_detected", "selection input must not attempt network, socket, or HTTP activity"))
    if credentials_used:
        findings.append(_finding("credentials_detected", "selection input must not use credentials"))
    if endpoint_used:
        findings.append(_finding("endpoint_detected", "selection input must not use endpoints"))
    if provider_client_used:
        findings.append(_finding("client_detected", "selection input must not use provider clients"))
    if llm_call_attempted or semantic_generation_attempted or tool_calls_attempted or memory_access_attempted or retention_attempted or action_execution_attempted or routing_attempted:
        findings.append(_finding("runtime_authority_detected", "selection input must not carry runtime authority"))
    if not no_raw_payload_marker:
        findings.append(_finding("raw_payload_marker_detected", "raw payload markers are forbidden"))
    if not no_runtime_handle_marker:
        findings.append(_finding("runtime_handle_marker_detected", "runtime handle markers are forbidden"))
    if not no_provider_model_params:
        findings.append(_finding("provider_model_params_detected", "provider/model parameter markers are forbidden"))
    if marker_evidence and _contains_runtime_marker(marker_evidence):
        findings.append(_finding("runtime_authority_detected", "marker evidence contains forbidden runtime/provider/network terms"))
    marker_values = {field_name: True for field_name in _MARKER_FIELDS}
    if marker_overrides:
        marker_values.update({str(key): bool(value) for key, value in marker_overrides.items() if str(key) in marker_values})
    for name, value in marker_values.items():
        if not value:
            findings.append(_finding("runtime_authority_detected", f"{name} must remain true"))
    warnings = tuple(str(item) for item in (null.get("warnings", ()) or ()))
    status = _status_for_findings(findings, warnings, str(null.get("null_transport_status", "")))
    selected = _ALLOWED_ADAPTER if status in {
        ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_READY,
        ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_READY_WITH_WARNINGS,
    } else ""
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "null-only transport selection linked the registry to the Phase 89 null transport receipt without sending anything"
    receipt = ProviderTransportSelectionReceipt(
        transport_selection_id="",
        selection_status=status,
        registry_id=str(registry.get("registry_id", "")),
        registry_status=str(registry.get("registry_status", "")),
        registry_digest=str(registry.get("registry_digest", "")),
        requested_adapter_kind=requested,
        selected_adapter_kind=selected,
        null_transport_id=str(null.get("null_transport_id", "")),
        null_transport_status=str(null.get("null_transport_status", "")),
        null_transport_digest=str(null.get("null_transport_digest", "")),
        dry_run_id=str(null.get("dry_run_id", "")),
        dry_run_digest=str(null.get("dry_run_digest", "")),
        network_preflight_id=str(null.get("network_preflight_id", "")),
        network_preflight_digest=str(null.get("network_preflight_digest", "")),
        network_review_receipt_id=str(null.get("network_review_receipt_id", "")),
        network_review_digest=str(null.get("network_review_digest", "")),
        candidate_id=str(null.get("candidate_id", "")),
        candidate_digest=str(null.get("candidate_digest", "")),
        packet_id=str(null.get("packet_id", "")),
        packet_scope=str(null.get("packet_scope", "")),
        audit_chain=audit_chain,
        digest_chain_complete=audit_chain.complete,
        sent=bool(sent),
        bytes_sent=int(bytes_sent),
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
        warnings=warnings,
        constraints=_constraints(),
        rationale=rationale[:1000],
        selection_digest="",
        **marker_values,
    )
    digest = compute_provider_transport_selection_digest(receipt)
    return replace(receipt, transport_selection_id=f"provider-transport-selection:{receipt.dry_run_id or 'missing'}:{digest[:16]}", selection_digest=digest)


def validate_provider_transport_selection_receipt(receipt: ProviderTransportSelectionReceipt | Mapping[str, Any]) -> tuple[ProviderTransportRegistryFinding, ...]:
    data = _mapping(receipt)
    findings: list[ProviderTransportRegistryFinding] = []
    if not data:
        return (_finding("selection_receipt_missing", "ProviderTransportSelectionReceipt is required"),)
    if str(data.get("selection_status", "")) not in {
        ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_READY,
        ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_READY_WITH_WARNINGS,
        ProviderTransportSelectionStatus.TRANSPORT_SELECTION_BLOCKED,
        ProviderTransportSelectionStatus.TRANSPORT_SELECTION_INVALID_INPUT,
        ProviderTransportSelectionStatus.TRANSPORT_SELECTION_ADAPTER_UNREGISTERED,
        ProviderTransportSelectionStatus.TRANSPORT_SELECTION_ADAPTER_FORBIDDEN,
        ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_TRANSPORT_NOT_READY,
        ProviderTransportSelectionStatus.TRANSPORT_SELECTION_SEND_ATTEMPT_DETECTED,
        ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NETWORK_DETECTED,
        ProviderTransportSelectionStatus.TRANSPORT_SELECTION_CREDENTIALS_DETECTED,
        ProviderTransportSelectionStatus.TRANSPORT_SELECTION_ENDPOINT_DETECTED,
        ProviderTransportSelectionStatus.TRANSPORT_SELECTION_CLIENT_DETECTED,
        ProviderTransportSelectionStatus.TRANSPORT_SELECTION_RUNTIME_AUTHORITY_DETECTED,
    }:
        findings.append(_finding("selection_status_unknown", "unknown transport selection status"))
    for field_name in _MARKER_FIELDS:
        if data.get(field_name) is not True:
            findings.append(_finding("selection_marker_missing", f"{field_name} must be true"))
    if compute_provider_transport_selection_digest(receipt) != str(data.get("selection_digest", "")):
        findings.append(_finding("selection_digest_mismatch", "selection digest does not match stable metadata"))
    if data.get("selection_status") in {ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_READY, ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_READY_WITH_WARNINGS}:
        if not provider_transport_selection_uses_null_transport_only(receipt):
            findings.append(_finding("selection_not_null_only", "ready selection must use only the null adapter"))
        if not provider_transport_selection_sent_nothing(receipt):
            findings.append(_finding("selection_sent_something", "ready selection must prove no send"))
    return tuple(findings)


def provider_transport_registry_is_null_only(manifest: ProviderTransportRegistryManifest | Mapping[str, Any] | None) -> bool:
    data = _mapping(manifest)
    return bool(
        data.get("registry_status") == ProviderTransportRegistryStatus.TRANSPORT_REGISTRY_NULL_ONLY
        and tuple(data.get("registered_adapter_kinds", ())) == (_ALLOWED_ADAPTER,)
        and data.get("default_adapter_kind") == _ALLOWED_ADAPTER
        and data.get("live_provider_adapters_registered") is False
        and data.get("network_adapters_registered") is False
        and data.get("credentialed_adapters_registered") is False
        and data.get("endpoint_adapters_registered") is False
        and data.get("socket_adapters_registered") is False
        and data.get("http_adapters_registered") is False
        and data.get("semantic_generation_adapters_registered") is False
        and data.get("runtime_authority_adapters_registered") is False
        and data.get("null_transport_only") is True
        and all(data.get(field_name) is True for field_name in _REGISTRY_MARKER_FIELDS)
        and str(data.get("registry_digest", "")) == compute_provider_transport_registry_digest(manifest)
    )


def provider_transport_selection_uses_null_transport_only(receipt: ProviderTransportSelectionReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data.get("selection_status") in {
            ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_READY,
            ProviderTransportSelectionStatus.TRANSPORT_SELECTION_NULL_READY_WITH_WARNINGS,
        }
        and data.get("selected_adapter_kind") == _ALLOWED_ADAPTER
        and data.get("selected_null_transport_only") is True
        and data.get("live_provider_transport_forbidden") is True
        and data.get("network_transport_forbidden") is True
        and data.get("credentialed_transport_forbidden") is True
        and data.get("endpoint_transport_forbidden") is True
        and data.get("socket_transport_forbidden") is True
        and data.get("http_transport_forbidden") is True
    )


def provider_transport_selection_sent_nothing(receipt: ProviderTransportSelectionReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        provider_transport_selection_uses_null_transport_only(receipt)
        and data.get("sent") is False
        and int(data.get("bytes_sent", -1) or 0) == 0
        and data.get("provider_send_attempted") is False
        and data.get("null_transport_sent_nothing") is True
        and data.get("does_not_send_to_provider") is True
    )


def provider_transport_selection_has_no_network(receipt: ProviderTransportSelectionReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        provider_transport_selection_sent_nothing(receipt)
        and data.get("network_egress_attempted") is False
        and data.get("socket_opened") is False
        and data.get("http_request_attempted") is False
        and data.get("network_transport_forbidden") is True
        and data.get("socket_transport_forbidden") is True
        and data.get("http_transport_forbidden") is True
        and data.get("does_not_make_network_calls") is True
        and data.get("does_not_open_sockets") is True
        and data.get("does_not_make_http_requests") is True
    )


def provider_transport_selection_has_no_credentials(receipt: ProviderTransportSelectionReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(provider_transport_selection_uses_null_transport_only(receipt) and data.get("credentials_used") is False and data.get("credentialed_transport_forbidden") is True)


def provider_transport_selection_has_no_endpoint(receipt: ProviderTransportSelectionReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(provider_transport_selection_uses_null_transport_only(receipt) and data.get("endpoint_used") is False and data.get("endpoint_transport_forbidden") is True)


def provider_transport_selection_has_no_provider_client(receipt: ProviderTransportSelectionReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(provider_transport_selection_uses_null_transport_only(receipt) and data.get("provider_client_used") is False and data.get("live_provider_transport_forbidden") is True)


def provider_transport_selection_has_no_runtime_authority(receipt: ProviderTransportSelectionReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        provider_transport_selection_uses_null_transport_only(receipt)
        and data.get("llm_call_attempted") is False
        and data.get("semantic_generation_attempted") is False
        and data.get("tool_calls_attempted") is False
        and data.get("memory_access_attempted") is False
        and data.get("retention_attempted") is False
        and data.get("action_execution_attempted") is False
        and data.get("routing_attempted") is False
        and data.get("does_not_call_llm") is True
        and data.get("does_not_retrieve_memory") is True
        and data.get("does_not_write_memory") is True
        and data.get("does_not_trigger_feedback") is True
        and data.get("does_not_commit_retention") is True
        and data.get("does_not_execute_or_route_work") is True
        and data.get("does_not_admit_work") is True
    )


def provider_transport_registry_digest_chain_complete(receipt: ProviderTransportSelectionReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    chain = _mapping(data.get("audit_chain", {}))
    return bool(
        data.get("digest_chain_complete") is True
        and chain.get("complete") is True
        and not chain.get("missing")
        and not chain.get("mismatches")
        and data.get("registry_id") == chain.get("registry_id")
        and data.get("registry_digest") == chain.get("registry_digest")
        and data.get("null_transport_id") == chain.get("null_transport_id")
        and data.get("null_transport_digest") == chain.get("null_transport_digest")
    )


def explain_provider_transport_registry_findings(subject: ProviderTransportRegistryManifest | ProviderTransportSelectionReceipt | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(subject)
    return tuple(f"{item.get('severity', 'blocker')}:{item.get('code', '')}:{item.get('detail', '')}" for item in (_mapping(finding) for finding in data.get("findings", ()) or ()))


def summarize_provider_transport_selection_receipt(receipt: ProviderTransportSelectionReceipt | Mapping[str, Any]) -> dict[str, Any]:
    data = _mapping(receipt)
    return {
        "transport_selection_id": data.get("transport_selection_id", ""),
        "selection_status": data.get("selection_status", ""),
        "registry_id": data.get("registry_id", ""),
        "requested_adapter_kind": data.get("requested_adapter_kind", ""),
        "selected_adapter_kind": data.get("selected_adapter_kind", ""),
        "null_transport_id": data.get("null_transport_id", ""),
        "digest_chain_complete": bool(data.get("digest_chain_complete", False)),
        "sent": bool(data.get("sent", True)),
        "bytes_sent": int(data.get("bytes_sent", -1) or 0),
        "findings": [item.get("code", "") for item in (_mapping(finding) for finding in data.get("findings", ()) or ())],
        "warnings": list(data.get("warnings", ()) or ()),
        "selection_digest": data.get("selection_digest", ""),
    }
