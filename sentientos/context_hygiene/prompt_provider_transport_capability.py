from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_provider_transport_registry import (
    ProviderTransportAdapterKind,
    ProviderTransportRegistryManifest,
    ProviderTransportRegistryStatus,
    compute_provider_transport_registry_digest,
    provider_transport_registry_is_null_only,
)


class ProviderTransportCapabilityStatus:
    TRANSPORT_CAPABILITY_NULL_ONLY = "transport_capability_null_only"
    TRANSPORT_CAPABILITY_FORBIDDEN_REAL_TRANSPORT = "transport_capability_forbidden_real_transport"
    TRANSPORT_CAPABILITY_INCOMPLETE = "transport_capability_incomplete"
    TRANSPORT_CAPABILITY_INVALID = "transport_capability_invalid"
    TRANSPORT_CAPABILITY_RUNTIME_AUTHORITY_DETECTED = "transport_capability_runtime_authority_detected"
    TRANSPORT_CAPABILITY_NETWORK_DETECTED = "transport_capability_network_detected"
    TRANSPORT_CAPABILITY_CREDENTIALS_DETECTED = "transport_capability_credentials_detected"
    TRANSPORT_CAPABILITY_ENDPOINT_DETECTED = "transport_capability_endpoint_detected"
    TRANSPORT_CAPABILITY_CLIENT_DETECTED = "transport_capability_client_detected"


class ProviderTransportRegistrationStatus:
    TRANSPORT_REGISTRATION_DENIED = "transport_registration_denied"
    TRANSPORT_REGISTRATION_NULL_ONLY_ALLOWED = "transport_registration_null_only_allowed"
    TRANSPORT_REGISTRATION_FORBIDDEN_REAL_TRANSPORT = "transport_registration_forbidden_real_transport"
    TRANSPORT_REGISTRATION_INCOMPLETE_EVIDENCE = "transport_registration_incomplete_evidence"
    TRANSPORT_REGISTRATION_INVALID_INPUT = "transport_registration_invalid_input"
    TRANSPORT_REGISTRATION_NETWORK_DETECTED = "transport_registration_network_detected"
    TRANSPORT_REGISTRATION_CREDENTIALS_DETECTED = "transport_registration_credentials_detected"
    TRANSPORT_REGISTRATION_ENDPOINT_DETECTED = "transport_registration_endpoint_detected"
    TRANSPORT_REGISTRATION_CLIENT_DETECTED = "transport_registration_client_detected"
    TRANSPORT_REGISTRATION_RUNTIME_AUTHORITY_DETECTED = "transport_registration_runtime_authority_detected"


class ProviderTransportCapabilityKind:
    TRANSPORT_CAPABILITY_NULL_ADAPTER = "transport_capability_null_adapter"
    TRANSPORT_CAPABILITY_LIVE_PROVIDER = "transport_capability_live_provider"
    TRANSPORT_CAPABILITY_NETWORK_EGRESS = "transport_capability_network_egress"
    TRANSPORT_CAPABILITY_HTTP = "transport_capability_http"
    TRANSPORT_CAPABILITY_SOCKET = "transport_capability_socket"
    TRANSPORT_CAPABILITY_PROVIDER_SDK = "transport_capability_provider_sdk"
    TRANSPORT_CAPABILITY_CREDENTIALED = "transport_capability_credentialed"
    TRANSPORT_CAPABILITY_ENDPOINT = "transport_capability_endpoint"
    TRANSPORT_CAPABILITY_PROVIDER_CLIENT = "transport_capability_provider_client"
    TRANSPORT_CAPABILITY_STREAMING = "transport_capability_streaming"
    TRANSPORT_CAPABILITY_TOOL_CALLING = "transport_capability_tool_calling"
    TRANSPORT_CAPABILITY_SEMANTIC_GENERATION = "transport_capability_semantic_generation"
    TRANSPORT_CAPABILITY_MEMORY_ACCESS = "transport_capability_memory_access"
    TRANSPORT_CAPABILITY_ACTION_EXECUTION = "transport_capability_action_execution"
    TRANSPORT_CAPABILITY_RETENTION_COMMIT = "transport_capability_retention_commit"
    TRANSPORT_CAPABILITY_ROUTING_EXECUTION = "transport_capability_routing_execution"
    TRANSPORT_CAPABILITY_UNKNOWN_FORBIDDEN = "transport_capability_unknown_forbidden"


@dataclass(frozen=True)
class ProviderTransportCapabilityFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderTransportCapabilityConstraint:
    code: str
    detail: str
    required: bool = True


@dataclass(frozen=True)
class ProviderTransportCapabilityGap:
    code: str
    detail: str
    required_for_real_transport: bool = True


@dataclass(frozen=True)
class ProviderTransportCapabilityAuditChain:
    capability_manifest_id: str = ""
    capability_digest: str = ""
    registry_id: str = ""
    registry_digest: str = ""
    registry_status: str = ""
    complete: bool = False
    mismatches: tuple[str, ...] = field(default_factory=tuple)
    missing: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProviderTransportCapabilityManifest:
    capability_manifest_id: str
    capability_status: str
    adapter_kind: str
    declared_capabilities: tuple[str, ...]
    forbidden_capabilities: tuple[str, ...]
    missing_required_evidence: tuple[str, ...]
    capability_gaps: tuple[ProviderTransportCapabilityGap, ...]
    null_only_compatible: bool
    registration_candidate: bool = False
    real_transport_candidate: bool = False
    network_egress_capable: bool = False
    provider_send_capable: bool = False
    credentials_capable: bool = False
    endpoint_capable: bool = False
    provider_client_capable: bool = False
    socket_capable: bool = False
    http_capable: bool = False
    provider_sdk_capable: bool = False
    streaming_capable: bool = False
    tool_calling_capable: bool = False
    semantic_generation_capable: bool = False
    memory_access_capable: bool = False
    retention_capable: bool = False
    action_execution_capable: bool = False
    routing_capable: bool = False
    findings: tuple[ProviderTransportCapabilityFinding, ...] = field(default_factory=tuple)
    constraints: tuple[ProviderTransportCapabilityConstraint, ...] = field(default_factory=tuple)
    rationale: str = ""
    capability_digest: str = ""
    provider_transport_capability_manifest_only: bool = True
    real_transport_registration_forbidden: bool = True
    null_transport_only: bool = True
    network_transport_forbidden: bool = True
    provider_send_forbidden: bool = True
    credentials_forbidden: bool = True
    endpoint_forbidden: bool = True
    provider_client_forbidden: bool = True
    socket_forbidden: bool = True
    http_forbidden: bool = True
    provider_sdk_forbidden: bool = True
    semantic_generation_forbidden: bool = True
    live_prompt_assembly_forbidden: bool = True
    live_model_call_forbidden: bool = True
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
class ProviderTransportRegistrationPreflight:
    registration_preflight_id: str
    registration_status: str
    capability_manifest_id: str
    capability_status: str
    capability_digest: str
    registry_id: str
    registry_status: str
    registry_digest: str
    requested_adapter_kind: str
    requested_registration: bool
    registration_allowed: bool
    selected_adapter_kind: str
    null_only_compatible: bool
    real_transport_registration_allowed: bool
    live_provider_registration_allowed: bool
    network_transport_registration_allowed: bool
    credentialed_transport_registration_allowed: bool
    endpoint_transport_registration_allowed: bool
    socket_transport_registration_allowed: bool
    http_transport_registration_allowed: bool
    provider_sdk_registration_allowed: bool
    semantic_generation_transport_registration_allowed: bool
    findings: tuple[ProviderTransportCapabilityFinding, ...]
    warnings: tuple[str, ...]
    constraints: tuple[ProviderTransportCapabilityConstraint, ...]
    capability_gaps: tuple[ProviderTransportCapabilityGap, ...]
    rationale: str
    registration_preflight_digest: str
    no_network: bool = True
    no_provider_send: bool = True
    no_credentials: bool = True
    no_endpoint: bool = True
    no_provider_client: bool = True
    no_http: bool = True
    no_socket: bool = True
    no_provider_sdk: bool = True
    no_tools: bool = True
    no_memory: bool = True
    no_retention: bool = True
    no_actions: bool = True
    no_routing: bool = True
    no_semantic_generation: bool = True
    no_raw_payload_marker: bool = True
    no_runtime_handle_marker: bool = True
    no_provider_model_params: bool = True
    internal_only: bool = True
    provider_transport_registration_preflight_only: bool = True
    real_transport_registration_forbidden: bool = True
    null_transport_only: bool = True
    network_transport_forbidden: bool = True
    provider_send_forbidden: bool = True
    credentials_forbidden: bool = True
    endpoint_forbidden: bool = True
    provider_client_forbidden: bool = True
    socket_forbidden: bool = True
    http_forbidden: bool = True
    provider_sdk_forbidden: bool = True
    semantic_generation_forbidden: bool = True
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


_ALLOWED_CAPABILITY = ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_NULL_ADAPTER
_ALLOWED_ADAPTER = ProviderTransportAdapterKind.PROVIDER_TRANSPORT_NULL_ADAPTER
_FORBIDDEN_CAPABILITIES = frozenset(
    {
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_LIVE_PROVIDER,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_NETWORK_EGRESS,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_HTTP,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_SOCKET,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_PROVIDER_SDK,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_CREDENTIALED,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_ENDPOINT,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_PROVIDER_CLIENT,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_STREAMING,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_TOOL_CALLING,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_SEMANTIC_GENERATION,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_MEMORY_ACCESS,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_ACTION_EXECUTION,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_RETENTION_COMMIT,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_ROUTING_EXECUTION,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_UNKNOWN_FORBIDDEN,
    }
)
_NETWORK_CAPABILITIES = frozenset({ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_NETWORK_EGRESS})
_CREDENTIAL_CAPABILITIES = frozenset({ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_CREDENTIALED})
_ENDPOINT_CAPABILITIES = frozenset({ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_ENDPOINT})
_CLIENT_CAPABILITIES = frozenset({ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_PROVIDER_CLIENT})
_RUNTIME_CAPABILITIES = frozenset(
    {
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_TOOL_CALLING,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_MEMORY_ACCESS,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_ACTION_EXECUTION,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_RETENTION_COMMIT,
        ProviderTransportCapabilityKind.TRANSPORT_CAPABILITY_ROUTING_EXECUTION,
    }
)
_FLAG_FIELDS = (
    "registration_candidate",
    "real_transport_candidate",
    "network_egress_capable",
    "provider_send_capable",
    "credentials_capable",
    "endpoint_capable",
    "provider_client_capable",
    "socket_capable",
    "http_capable",
    "provider_sdk_capable",
    "streaming_capable",
    "tool_calling_capable",
    "semantic_generation_capable",
    "memory_access_capable",
    "retention_capable",
    "action_execution_capable",
    "routing_capable",
)
_MARKER_FIELDS = (
    "provider_transport_capability_manifest_only",
    "real_transport_registration_forbidden",
    "null_transport_only",
    "network_transport_forbidden",
    "provider_send_forbidden",
    "credentials_forbidden",
    "endpoint_forbidden",
    "provider_client_forbidden",
    "socket_forbidden",
    "http_forbidden",
    "provider_sdk_forbidden",
    "semantic_generation_forbidden",
    "live_prompt_assembly_forbidden",
    "live_model_call_forbidden",
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
_PREFLIGHT_MARKER_FIELDS = tuple(field_name for field_name in _MARKER_FIELDS if field_name != "provider_transport_capability_manifest_only") + (
    "provider_transport_registration_preflight_only",
)
_RUNTIME_MARKER_KEYS = (
    "raw_payload",
    "raw_memory_payload",
    "runtime_handle",
    "execution_handle",
    "network_handle",
    "request_handle",
    "response_handle",
    "provider_params",
    "model_params",
    "llm_params",
    "api_key",
    "auth_header",
    "endpoint_url",
    "provider_client_handle",
    "session_handle",
    "transport_handle",
    "socket_handle",
    "http_client",
    "tool_schema",
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


def _finding(code: str, detail: str, severity: str = "blocker") -> ProviderTransportCapabilityFinding:
    return ProviderTransportCapabilityFinding(code=code, detail=detail, severity=severity)


def _constraints() -> tuple[ProviderTransportCapabilityConstraint, ...]:
    return (
        ProviderTransportCapabilityConstraint("capability_manifest_only", "capability descriptors are metadata-only and are not transport registration"),
        ProviderTransportCapabilityConstraint("null_transport_only", "only the Phase 89 null adapter may be null-only compatible"),
        ProviderTransportCapabilityConstraint("real_transports_forbidden", "live provider, network, HTTP, socket, SDK, credentialed, endpoint, client, streaming, tool, semantic, memory, action, retention, and routing transports remain forbidden"),
        ProviderTransportCapabilityConstraint("no_runtime_authority", "the manifest and preflight do not call LLMs, retrieve/write memory, execute actions, commit retention, route/admit work, or perform network egress"),
    )


def _default_gaps() -> tuple[ProviderTransportCapabilityGap, ...]:
    return (
        ProviderTransportCapabilityGap("future_provider_security_review", "future real transports require a separate security and privacy review"),
        ProviderTransportCapabilityGap("future_credential_custody_review", "future credential handling requires a separate custody contract"),
        ProviderTransportCapabilityGap("future_network_egress_review", "future network egress requires a separate egress contract and approval path"),
    )


def _contains_runtime_marker(value: Any) -> bool:
    text = json.dumps(_stable(value), sort_keys=True, ensure_ascii=True, default=str).lower()
    return any(marker in text for marker in _RUNTIME_MARKER_KEYS)


def _capability_digest_payload(manifest: ProviderTransportCapabilityManifest | Mapping[str, Any]) -> dict[str, Any]:
    data = dict(_mapping(manifest))
    data.pop("capability_manifest_id", None)
    data.pop("capability_digest", None)
    return data


def compute_provider_transport_capability_digest(manifest: ProviderTransportCapabilityManifest | Mapping[str, Any]) -> str:
    return _stable_digest(_capability_digest_payload(manifest))


def _preflight_digest_payload(preflight: ProviderTransportRegistrationPreflight | Mapping[str, Any]) -> dict[str, Any]:
    data = dict(_mapping(preflight))
    data.pop("registration_preflight_id", None)
    data.pop("registration_preflight_digest", None)
    return data


def compute_provider_transport_registration_preflight_digest(preflight: ProviderTransportRegistrationPreflight | Mapping[str, Any]) -> str:
    return _stable_digest(_preflight_digest_payload(preflight))


def build_provider_transport_capability_manifest(
    *,
    adapter_kind: str = _ALLOWED_CAPABILITY,
    declared_capabilities: Sequence[str] | None = None,
    missing_required_evidence: Sequence[str] | None = None,
    has_null_only_evidence: bool = True,
    registration_candidate: bool = False,
    real_transport_candidate: bool = False,
    network_egress_capable: bool = False,
    provider_send_capable: bool = False,
    credentials_capable: bool = False,
    endpoint_capable: bool = False,
    provider_client_capable: bool = False,
    socket_capable: bool = False,
    http_capable: bool = False,
    provider_sdk_capable: bool = False,
    streaming_capable: bool = False,
    tool_calling_capable: bool = False,
    semantic_generation_capable: bool = False,
    memory_access_capable: bool = False,
    retention_capable: bool = False,
    action_execution_capable: bool = False,
    routing_capable: bool = False,
    marker_overrides: Mapping[str, bool] | None = None,
) -> ProviderTransportCapabilityManifest:
    declared = tuple(str(item) for item in (declared_capabilities if declared_capabilities is not None else (_ALLOWED_CAPABILITY,)))
    declared_set = set(declared)
    forbidden = tuple(item for item in declared if item in _FORBIDDEN_CAPABILITIES or item != _ALLOWED_CAPABILITY)
    missing = list(str(item) for item in (missing_required_evidence or ()))
    if not has_null_only_evidence:
        missing.append("null_only_evidence")
    findings: list[ProviderTransportCapabilityFinding] = []
    if not str(adapter_kind):
        findings.append(_finding("adapter_kind_missing", "capability adapter kind is required"))
    if not declared:
        findings.append(_finding("declared_capabilities_missing", "at least the null adapter capability must be declared"))
    if forbidden:
        findings.append(_finding("forbidden_capability_declared", "only transport_capability_null_adapter is allowed in Phase 91"))
    if missing:
        findings.append(_finding("incomplete_null_only_evidence", "required null-only capability evidence is missing", "warning"))
    flag_values = {
        "registration_candidate": registration_candidate,
        "real_transport_candidate": real_transport_candidate,
        "network_egress_capable": network_egress_capable,
        "provider_send_capable": provider_send_capable,
        "credentials_capable": credentials_capable,
        "endpoint_capable": endpoint_capable,
        "provider_client_capable": provider_client_capable,
        "socket_capable": socket_capable,
        "http_capable": http_capable,
        "provider_sdk_capable": provider_sdk_capable,
        "streaming_capable": streaming_capable,
        "tool_calling_capable": tool_calling_capable,
        "semantic_generation_capable": semantic_generation_capable,
        "memory_access_capable": memory_access_capable,
        "retention_capable": retention_capable,
        "action_execution_capable": action_execution_capable,
        "routing_capable": routing_capable,
    }
    for name, value in flag_values.items():
        if value:
            findings.append(_finding(name, f"{name} must remain false in Phase 91"))
    marker_values = {field_name: True for field_name in _MARKER_FIELDS}
    if marker_overrides:
        marker_values.update({str(key): bool(value) for key, value in marker_overrides.items() if str(key) in marker_values})
    for name, value in marker_values.items():
        if not value:
            findings.append(_finding("capability_marker_missing", f"{name} must remain true"))
    runtime_detected = bool(
        declared_set & _RUNTIME_CAPABILITIES
        or tool_calling_capable
        or memory_access_capable
        or retention_capable
        or action_execution_capable
        or routing_capable
        or any(not value for value in marker_values.values())
    )
    network_detected = bool(declared_set & _NETWORK_CAPABILITIES or network_egress_capable or provider_send_capable)
    credentials_detected = bool(declared_set & _CREDENTIAL_CAPABILITIES or credentials_capable)
    endpoint_detected = bool(declared_set & _ENDPOINT_CAPABILITIES or endpoint_capable)
    client_detected = bool(declared_set & _CLIENT_CAPABILITIES or provider_client_capable)
    real_detected = bool(
        forbidden
        or real_transport_candidate
        or registration_candidate
        or socket_capable
        or http_capable
        or provider_sdk_capable
        or streaming_capable
        or semantic_generation_capable
    )
    if not str(adapter_kind) or not declared:
        status = ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_INVALID
    elif network_detected:
        status = ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_NETWORK_DETECTED
    elif credentials_detected:
        status = ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_CREDENTIALS_DETECTED
    elif endpoint_detected:
        status = ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_ENDPOINT_DETECTED
    elif client_detected:
        status = ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_CLIENT_DETECTED
    elif runtime_detected:
        status = ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_RUNTIME_AUTHORITY_DETECTED
    elif real_detected:
        status = ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_FORBIDDEN_REAL_TRANSPORT
    elif missing:
        status = ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_INCOMPLETE
    elif str(adapter_kind) == _ALLOWED_CAPABILITY and declared == (_ALLOWED_CAPABILITY,):
        status = ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_NULL_ONLY
    else:
        status = ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_FORBIDDEN_REAL_TRANSPORT
        findings.append(_finding("adapter_kind_not_null_only", "only transport_capability_null_adapter may be null-only compatible"))
    null_only = status == ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_NULL_ONLY
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "capability manifest is metadata-only and compatible only with the Phase 89 null adapter"
    manifest = ProviderTransportCapabilityManifest(
        capability_manifest_id="",
        capability_status=status,
        adapter_kind=str(adapter_kind),
        declared_capabilities=declared,
        forbidden_capabilities=forbidden,
        missing_required_evidence=tuple(missing),
        capability_gaps=_default_gaps(),
        null_only_compatible=null_only,
        findings=tuple(findings),
        constraints=_constraints(),
        rationale=rationale[:1000],
        capability_digest="",
        **flag_values,
        **marker_values,
    )
    digest = compute_provider_transport_capability_digest(manifest)
    return replace(manifest, capability_manifest_id=f"provider-transport-capability:{digest[:16]}", capability_digest=digest)


def validate_provider_transport_capability_manifest(manifest: ProviderTransportCapabilityManifest | Mapping[str, Any]) -> tuple[ProviderTransportCapabilityFinding, ...]:
    data = _mapping(manifest)
    findings: list[ProviderTransportCapabilityFinding] = []
    if not data:
        return (_finding("capability_manifest_missing", "ProviderTransportCapabilityManifest is required"),)
    if str(data.get("capability_status", "")) not in {
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_NULL_ONLY,
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_FORBIDDEN_REAL_TRANSPORT,
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_INCOMPLETE,
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_INVALID,
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_RUNTIME_AUTHORITY_DETECTED,
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_NETWORK_DETECTED,
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_CREDENTIALS_DETECTED,
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_ENDPOINT_DETECTED,
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_CLIENT_DETECTED,
    }:
        findings.append(_finding("capability_status_unknown", "unknown transport capability status"))
    for field_name in _MARKER_FIELDS:
        if data.get(field_name) is not True:
            findings.append(_finding("capability_marker_missing", f"{field_name} must be true"))
    for field_name in _FLAG_FIELDS:
        if data.get(field_name) is True:
            findings.append(_finding("capability_runtime_flag_detected", f"{field_name} must remain false"))
    if compute_provider_transport_capability_digest(manifest) != str(data.get("capability_digest", "")):
        findings.append(_finding("capability_digest_mismatch", "capability digest does not match stable metadata"))
    if data.get("capability_status") == ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_NULL_ONLY and not provider_transport_capability_is_null_only(manifest):
        findings.append(_finding("capability_null_only_mismatch", "null-only status requires a clean null adapter capability"))
    return tuple(findings)


def _registry_valid_and_null_only(registry_manifest: ProviderTransportRegistryManifest | Mapping[str, Any]) -> bool:
    registry = _mapping(registry_manifest)
    if not registry:
        return False
    return (
        str(registry.get("registry_status", "")) == ProviderTransportRegistryStatus.TRANSPORT_REGISTRY_NULL_ONLY
        and provider_transport_registry_is_null_only(registry_manifest)
        and compute_provider_transport_registry_digest(registry_manifest) == str(registry.get("registry_digest", ""))
    )


def evaluate_provider_transport_registration_preflight(
    capability_manifest: ProviderTransportCapabilityManifest | Mapping[str, Any] | None,
    registry_manifest: ProviderTransportRegistryManifest | Mapping[str, Any] | None,
    *,
    requested_adapter_kind: str = _ALLOWED_ADAPTER,
    requested_registration: bool = False,
    internal_only: bool = True,
    no_network: bool = True,
    no_provider_send: bool = True,
    no_credentials: bool = True,
    no_endpoint: bool = True,
    no_provider_client: bool = True,
    no_http: bool = True,
    no_socket: bool = True,
    no_provider_sdk: bool = True,
    no_tools: bool = True,
    no_memory: bool = True,
    no_retention: bool = True,
    no_actions: bool = True,
    no_routing: bool = True,
    no_semantic_generation: bool = True,
    no_raw_payload_marker: bool = True,
    no_runtime_handle_marker: bool = True,
    no_provider_model_params: bool = True,
    marker_evidence: Any = None,
) -> ProviderTransportRegistrationPreflight:
    capability = _mapping(capability_manifest)
    registry = _mapping(registry_manifest)
    findings: list[ProviderTransportCapabilityFinding] = []
    warnings: list[str] = []
    if not capability:
        findings.append(_finding("capability_manifest_missing", "capability manifest is required"))
    else:
        findings.extend(validate_provider_transport_capability_manifest(capability_manifest or {}))
    if not registry:
        findings.append(_finding("registry_manifest_missing", "Phase 90 registry manifest is required"))
    elif not _registry_valid_and_null_only(registry_manifest or {}):
        findings.append(_finding("registry_not_null_only", "Phase 90 registry must remain null-only and digest-valid"))
    requested = str(requested_adapter_kind)
    if requested != _ALLOWED_ADAPTER:
        findings.append(_finding("requested_adapter_forbidden", "Phase 91 preflight allows only provider_transport_null_adapter as a metadata-only request"))
    if requested_registration and requested != _ALLOWED_ADAPTER:
        findings.append(_finding("requested_real_registration_forbidden", "requested real transport registration is forbidden"))
    no_flags = {
        "no_network": no_network,
        "no_provider_send": no_provider_send,
        "no_credentials": no_credentials,
        "no_endpoint": no_endpoint,
        "no_provider_client": no_provider_client,
        "no_http": no_http,
        "no_socket": no_socket,
        "no_provider_sdk": no_provider_sdk,
        "no_tools": no_tools,
        "no_memory": no_memory,
        "no_retention": no_retention,
        "no_actions": no_actions,
        "no_routing": no_routing,
        "no_semantic_generation": no_semantic_generation,
        "no_raw_payload_marker": no_raw_payload_marker,
        "no_runtime_handle_marker": no_runtime_handle_marker,
        "no_provider_model_params": no_provider_model_params,
    }
    for name, value in no_flags.items():
        if not value:
            findings.append(_finding(name, f"{name} must remain true for metadata-only preflight"))
    if not internal_only:
        findings.append(_finding("external_preflight_attempted", "registration preflight is internal metadata only"))
    if _contains_runtime_marker(marker_evidence):
        findings.append(_finding("runtime_marker_detected", "marker evidence contains forbidden raw payload/runtime/provider/network handle terms"))
    capability_status = str(capability.get("capability_status", ""))
    if capability_status == ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_INCOMPLETE:
        findings.append(_finding("capability_evidence_incomplete", "capability manifest evidence is incomplete"))
    elif capability_status in {
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_FORBIDDEN_REAL_TRANSPORT,
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_RUNTIME_AUTHORITY_DETECTED,
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_NETWORK_DETECTED,
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_CREDENTIALS_DETECTED,
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_ENDPOINT_DETECTED,
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_CLIENT_DETECTED,
        ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_INVALID,
    }:
        findings.append(_finding("capability_not_null_only", "capability manifest is not clean null-only"))
    if not no_network or not no_provider_send:
        status = ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_NETWORK_DETECTED
    elif not no_credentials:
        status = ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_CREDENTIALS_DETECTED
    elif not no_endpoint:
        status = ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_ENDPOINT_DETECTED
    elif not no_provider_client:
        status = ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_CLIENT_DETECTED
    elif not (no_tools and no_memory and no_retention and no_actions and no_routing and no_raw_payload_marker and no_runtime_handle_marker and no_provider_model_params and internal_only):
        status = ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_RUNTIME_AUTHORITY_DETECTED
    elif not (no_http and no_socket and no_provider_sdk and no_semantic_generation):
        status = ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_FORBIDDEN_REAL_TRANSPORT
    elif requested != _ALLOWED_ADAPTER:
        status = ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_FORBIDDEN_REAL_TRANSPORT
    elif capability_status == ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_INCOMPLETE:
        status = ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_INCOMPLETE_EVIDENCE
    elif capability_status == ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_NULL_ONLY and _registry_valid_and_null_only(registry_manifest or {}):
        status = ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_NULL_ONLY_ALLOWED
        if requested_registration:
            warnings.append("requested_registration_true_treated_as_null_only_no_op_metadata")
    elif not capability or not registry or capability_status == ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_INVALID:
        status = ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_INVALID_INPUT
    else:
        status = ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_DENIED
    if marker_evidence is not None and _contains_runtime_marker(marker_evidence):
        status = ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_RUNTIME_AUTHORITY_DETECTED
    allowed = status == ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_NULL_ONLY_ALLOWED
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "registration preflight is metadata-only and allows only a null-only no-op compatibility decision"
    preflight = ProviderTransportRegistrationPreflight(
        registration_preflight_id="",
        registration_status=status,
        capability_manifest_id=str(capability.get("capability_manifest_id", "")),
        capability_status=capability_status,
        capability_digest=str(capability.get("capability_digest", "")),
        registry_id=str(registry.get("registry_id", "")),
        registry_status=str(registry.get("registry_status", "")),
        registry_digest=str(registry.get("registry_digest", "")),
        requested_adapter_kind=requested,
        requested_registration=bool(requested_registration),
        registration_allowed=allowed,
        selected_adapter_kind=_ALLOWED_ADAPTER if allowed else "",
        null_only_compatible=bool(allowed and capability.get("null_only_compatible") is True),
        real_transport_registration_allowed=False,
        live_provider_registration_allowed=False,
        network_transport_registration_allowed=False,
        credentialed_transport_registration_allowed=False,
        endpoint_transport_registration_allowed=False,
        socket_transport_registration_allowed=False,
        http_transport_registration_allowed=False,
        provider_sdk_registration_allowed=False,
        semantic_generation_transport_registration_allowed=False,
        findings=tuple(findings),
        warnings=tuple(warnings),
        constraints=_constraints(),
        capability_gaps=tuple(capability.get("capability_gaps", ())),
        rationale=rationale[:1000],
        registration_preflight_digest="",
        no_network=bool(no_network),
        no_provider_send=bool(no_provider_send),
        no_credentials=bool(no_credentials),
        no_endpoint=bool(no_endpoint),
        no_provider_client=bool(no_provider_client),
        no_http=bool(no_http),
        no_socket=bool(no_socket),
        no_provider_sdk=bool(no_provider_sdk),
        no_tools=bool(no_tools),
        no_memory=bool(no_memory),
        no_retention=bool(no_retention),
        no_actions=bool(no_actions),
        no_routing=bool(no_routing),
        no_semantic_generation=bool(no_semantic_generation),
        no_raw_payload_marker=bool(no_raw_payload_marker),
        no_runtime_handle_marker=bool(no_runtime_handle_marker),
        no_provider_model_params=bool(no_provider_model_params),
        internal_only=bool(internal_only),
    )
    digest = compute_provider_transport_registration_preflight_digest(preflight)
    return replace(preflight, registration_preflight_id=f"provider-transport-registration-preflight:{digest[:16]}", registration_preflight_digest=digest)


def provider_transport_capability_is_null_only(manifest: ProviderTransportCapabilityManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(
        data.get("capability_status") == ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_NULL_ONLY
        and data.get("adapter_kind") == _ALLOWED_CAPABILITY
        and tuple(data.get("declared_capabilities", ())) == (_ALLOWED_CAPABILITY,)
        and not tuple(data.get("forbidden_capabilities", ()))
        and not tuple(data.get("missing_required_evidence", ()))
        and data.get("null_only_compatible") is True
        and all(data.get(field_name) is False for field_name in _FLAG_FIELDS)
        and all(data.get(field_name) is True for field_name in _MARKER_FIELDS)
    )


def provider_transport_capability_forbids_real_transport(manifest: ProviderTransportCapabilityManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return not provider_transport_capability_is_null_only(data) and bool(
        data.get("real_transport_registration_forbidden") is True
        and data.get("null_transport_only") is True
        and data.get("capability_status") != ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_INVALID
    )


def provider_transport_capability_has_no_network(manifest: ProviderTransportCapabilityManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data.get("network_egress_capable") is False and data.get("provider_send_capable") is False and data.get("does_not_make_network_calls") is True and data.get("does_not_send_to_provider") is True)


def provider_transport_capability_has_no_credentials(manifest: ProviderTransportCapabilityManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data.get("credentials_capable") is False and data.get("credentials_forbidden") is True)


def provider_transport_capability_has_no_endpoint(manifest: ProviderTransportCapabilityManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data.get("endpoint_capable") is False and data.get("endpoint_forbidden") is True)


def provider_transport_capability_has_no_provider_client(manifest: ProviderTransportCapabilityManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data.get("provider_client_capable") is False and data.get("provider_client_forbidden") is True)


def provider_transport_capability_has_no_runtime_authority(manifest: ProviderTransportCapabilityManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    runtime_fields = ("tool_calling_capable", "memory_access_capable", "retention_capable", "action_execution_capable", "routing_capable", "semantic_generation_capable")
    return bool(all(data.get(field_name) is False for field_name in runtime_fields) and data.get("does_not_execute_or_route_work") is True and data.get("does_not_admit_work") is True)


def provider_transport_registration_remains_forbidden(preflight: ProviderTransportRegistrationPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(
        data.get("real_transport_registration_allowed") is False
        and data.get("live_provider_registration_allowed") is False
        and data.get("network_transport_registration_allowed") is False
        and data.get("credentialed_transport_registration_allowed") is False
        and data.get("endpoint_transport_registration_allowed") is False
        and data.get("socket_transport_registration_allowed") is False
        and data.get("http_transport_registration_allowed") is False
        and data.get("provider_sdk_registration_allowed") is False
        and data.get("semantic_generation_transport_registration_allowed") is False
        and data.get("real_transport_registration_forbidden") is True
    )


def provider_transport_registration_preflight_denies_real_transport(preflight: ProviderTransportRegistrationPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(
        provider_transport_registration_remains_forbidden(data)
        and data.get("registration_status") != ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_NULL_ONLY_ALLOWED
        and data.get("selected_adapter_kind", "") == ""
    )


def explain_provider_transport_capability_findings(manifest: ProviderTransportCapabilityManifest | Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(f"{item.get('severity', 'blocker')}:{item.get('code', '')}:{item.get('detail', '')}" for item in _mapping(manifest).get("findings", ()) if isinstance(item, Mapping)) or tuple(
        f"{finding.severity}:{finding.code}:{finding.detail}" for finding in getattr(manifest, "findings", ())
    )


def summarize_provider_transport_registration_preflight(preflight: ProviderTransportRegistrationPreflight | Mapping[str, Any]) -> dict[str, Any]:
    data = _mapping(preflight)
    return {
        "registration_status": data.get("registration_status", ""),
        "registration_allowed": data.get("registration_allowed", False),
        "requested_adapter_kind": data.get("requested_adapter_kind", ""),
        "selected_adapter_kind": data.get("selected_adapter_kind", ""),
        "null_only_compatible": data.get("null_only_compatible", False),
        "real_transport_registration_allowed": data.get("real_transport_registration_allowed", False),
        "finding_codes": tuple(item.get("code", "") for item in data.get("findings", ()) if isinstance(item, Mapping)),
        "warning_codes": tuple(data.get("warnings", ())),
        "registration_preflight_digest": data.get("registration_preflight_digest", ""),
    }
