from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_provider_credential_custody import (
    ProviderCredentialCustodyManifest,
    ProviderCredentialCustodyStatus,
    compute_provider_credential_custody_digest,
    provider_credential_custody_contains_no_secrets,
)
from sentientos.context_hygiene.prompt_provider_endpoint_custody import (
    ProviderEndpointCustodyManifest,
    ProviderEndpointCustodyPreflight,
    ProviderEndpointCustodyPreflightStatus,
    ProviderEndpointCustodyStatus,
    compute_provider_endpoint_custody_digest,
    compute_provider_endpoint_custody_preflight_digest,
    provider_endpoint_custody_contains_no_endpoints,
    provider_endpoint_preflight_remains_metadata_only,
)
from sentientos.context_hygiene.prompt_provider_transport_capability import (
    ProviderTransportCapabilityManifest,
    ProviderTransportCapabilityStatus,
    compute_provider_transport_capability_digest,
    provider_transport_capability_is_null_only,
)


class ProviderClientCustodyStatus:
    CLIENT_CUSTODY_NO_CLIENTS = "client_custody_no_clients"
    CLIENT_CUSTODY_FORBIDDEN_CLIENT_DETECTED = "client_custody_forbidden_client_detected"
    CLIENT_CUSTODY_CLIENT_REFERENCE_DETECTED = "client_custody_client_reference_detected"
    CLIENT_CUSTODY_SDK_IMPORT_DETECTED = "client_custody_sdk_import_detected"
    CLIENT_CUSTODY_SESSION_DETECTED = "client_custody_session_detected"
    CLIENT_CUSTODY_TRANSPORT_DETECTED = "client_custody_transport_detected"
    CLIENT_CUSTODY_STREAM_DETECTED = "client_custody_stream_detected"
    CLIENT_CUSTODY_ENDPOINT_DETECTED = "client_custody_endpoint_detected"
    CLIENT_CUSTODY_CREDENTIALS_DETECTED = "client_custody_credentials_detected"
    CLIENT_CUSTODY_NETWORK_DETECTED = "client_custody_network_detected"
    CLIENT_CUSTODY_INCOMPLETE = "client_custody_incomplete"
    CLIENT_CUSTODY_INVALID = "client_custody_invalid"
    CLIENT_CUSTODY_RUNTIME_AUTHORITY_DETECTED = "client_custody_runtime_authority_detected"


class ProviderClientCustodyPreflightStatus:
    CLIENT_PREFLIGHT_DENIED = "client_preflight_denied"
    CLIENT_PREFLIGHT_NO_CLIENTS_ALLOWED = "client_preflight_no_clients_allowed"
    CLIENT_PREFLIGHT_FORBIDDEN_CLIENT_DETECTED = "client_preflight_forbidden_client_detected"
    CLIENT_PREFLIGHT_CLIENT_INSTANTIATION_FORBIDDEN = "client_preflight_client_instantiation_forbidden"
    CLIENT_PREFLIGHT_SDK_IMPORT_DETECTED = "client_preflight_sdk_import_detected"
    CLIENT_PREFLIGHT_SESSION_DETECTED = "client_preflight_session_detected"
    CLIENT_PREFLIGHT_TRANSPORT_DETECTED = "client_preflight_transport_detected"
    CLIENT_PREFLIGHT_STREAM_DETECTED = "client_preflight_stream_detected"
    CLIENT_PREFLIGHT_ENDPOINT_DETECTED = "client_preflight_endpoint_detected"
    CLIENT_PREFLIGHT_CREDENTIALS_DETECTED = "client_preflight_credentials_detected"
    CLIENT_PREFLIGHT_NETWORK_DETECTED = "client_preflight_network_detected"
    CLIENT_PREFLIGHT_INCOMPLETE_EVIDENCE = "client_preflight_incomplete_evidence"
    CLIENT_PREFLIGHT_INVALID_INPUT = "client_preflight_invalid_input"
    CLIENT_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED = "client_preflight_runtime_authority_detected"


class ProviderClientCustodyKind:
    CLIENT_CUSTODY_NONE = "client_custody_none"
    CLIENT_CUSTODY_NO_CLIENT_PLACEHOLDER = "client_custody_no_client_placeholder"
    CLIENT_CUSTODY_FUTURE_CLIENT_CONTRACT_PLACEHOLDER = "client_custody_future_client_contract_placeholder"
    CLIENT_CUSTODY_PROVIDER_SDK_CLIENT_FORBIDDEN = "client_custody_provider_sdk_client_forbidden"
    CLIENT_CUSTODY_HTTP_CLIENT_FORBIDDEN = "client_custody_http_client_forbidden"
    CLIENT_CUSTODY_SOCKET_CLIENT_FORBIDDEN = "client_custody_socket_client_forbidden"
    CLIENT_CUSTODY_SESSION_FORBIDDEN = "client_custody_session_forbidden"
    CLIENT_CUSTODY_TRANSPORT_FORBIDDEN = "client_custody_transport_forbidden"
    CLIENT_CUSTODY_STREAMING_CLIENT_FORBIDDEN = "client_custody_streaming_client_forbidden"
    CLIENT_CUSTODY_RETRY_EXECUTOR_FORBIDDEN = "client_custody_retry_executor_forbidden"
    CLIENT_CUSTODY_REQUEST_BUILDER_FORBIDDEN = "client_custody_request_builder_forbidden"
    CLIENT_CUSTODY_PROVIDER_SPECIFIC_CLIENT_FORBIDDEN = "client_custody_provider_specific_client_forbidden"
    CLIENT_CUSTODY_UNKNOWN_FORBIDDEN = "client_custody_unknown_forbidden"


@dataclass(frozen=True)
class ProviderClientCustodyFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderClientCustodyConstraint:
    code: str
    detail: str
    required: bool = True


@dataclass(frozen=True)
class ProviderClientCustodyGap:
    code: str
    detail: str
    required_for_real_custody: bool = True


@dataclass(frozen=True)
class ProviderClientCustodyAuditChain:
    client_manifest_id: str = ""
    client_digest: str = ""
    capability_manifest_id: str = ""
    capability_digest: str = ""
    credential_custody_manifest_id: str = ""
    credential_custody_digest: str = ""
    endpoint_custody_manifest_id: str = ""
    endpoint_custody_digest: str = ""
    endpoint_custody_preflight_id: str = ""
    endpoint_custody_preflight_digest: str = ""
    complete: bool = False
    mismatches: tuple[str, ...] = field(default_factory=tuple)
    missing: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProviderClientCustodyManifest:
    client_manifest_id: str
    client_status: str
    client_custody_kind: str
    linked_capability_manifest_id: str
    linked_capability_digest: str
    linked_credential_custody_manifest_id: str
    linked_credential_custody_digest: str
    linked_endpoint_custody_manifest_id: str
    linked_endpoint_custody_digest: str
    linked_endpoint_custody_preflight_id: str
    linked_endpoint_custody_preflight_digest: str
    declared_client_properties: tuple[str, ...]
    forbidden_client_properties: tuple[str, ...]
    missing_required_evidence: tuple[str, ...]
    client_gaps: tuple[ProviderClientCustodyGap, ...]
    no_client_material: bool = True
    client_values_present: bool = False
    client_references_present: bool = False
    client_instantiation_allowed: bool = False
    sdk_import_allowed: bool = False
    session_creation_allowed: bool = False
    transport_creation_allowed: bool = False
    stream_creation_allowed: bool = False
    request_builder_allowed: bool = False
    retry_executor_allowed: bool = False
    credential_material_present: bool = False
    endpoint_material_present: bool = False
    network_access_allowed: bool = False
    client_runtime_authority: bool = False
    findings: tuple[ProviderClientCustodyFinding, ...] = field(default_factory=tuple)
    constraints: tuple[ProviderClientCustodyConstraint, ...] = field(default_factory=tuple)
    rationale: str = ""
    client_digest: str = ""
    provider_client_custody_manifest_only: bool = True
    client_instantiation_forbidden: bool = True
    provider_sdk_import_forbidden: bool = True
    session_creation_forbidden: bool = True
    transport_creation_forbidden: bool = True
    stream_creation_forbidden: bool = True
    request_builder_forbidden: bool = True
    retry_executor_forbidden: bool = True
    credential_material_forbidden: bool = True
    endpoint_material_forbidden: bool = True
    network_access_forbidden: bool = True
    provider_client_use_forbidden: bool = True
    endpoint_use_forbidden: bool = True
    credential_use_forbidden: bool = True
    live_provider_transport_forbidden: bool = True
    live_prompt_assembly_forbidden: bool = True
    live_model_call_forbidden: bool = True
    does_not_import_provider_sdks: bool = True
    does_not_create_clients: bool = True
    does_not_create_sessions: bool = True
    does_not_create_transports: bool = True
    does_not_open_streams: bool = True
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
class ProviderClientCustodyPreflight:
    client_preflight_id: str
    client_preflight_status: str
    client_manifest_id: str
    client_status: str
    client_digest: str
    capability_manifest_id: str
    capability_digest: str
    credential_custody_manifest_id: str
    credential_custody_digest: str
    endpoint_custody_manifest_id: str
    endpoint_custody_digest: str
    endpoint_custody_preflight_id: str
    endpoint_custody_preflight_digest: str
    requested_client_custody_kind: str
    requested_registration: bool
    client_allowed: bool
    client_material_allowed: bool
    client_reference_allowed: bool
    client_instantiation_allowed: bool
    sdk_import_allowed: bool
    session_creation_allowed: bool
    transport_creation_allowed: bool
    stream_creation_allowed: bool
    request_builder_allowed: bool
    retry_executor_allowed: bool
    credential_material_allowed: bool
    endpoint_material_allowed: bool
    network_access_allowed: bool
    provider_send_allowed: bool
    socket_allowed: bool
    http_allowed: bool
    provider_sdk_allowed: bool
    semantic_generation_allowed: bool
    findings: tuple[ProviderClientCustodyFinding, ...]
    warnings: tuple[str, ...]
    constraints: tuple[ProviderClientCustodyConstraint, ...]
    client_gaps: tuple[ProviderClientCustodyGap, ...]
    rationale: str
    client_preflight_digest: str
    provider_client_custody_preflight_only: bool = True
    no_client_material: bool = True
    client_instantiation_forbidden: bool = True
    provider_sdk_import_forbidden: bool = True
    session_creation_forbidden: bool = True
    transport_creation_forbidden: bool = True
    stream_creation_forbidden: bool = True
    request_builder_forbidden: bool = True
    retry_executor_forbidden: bool = True
    credential_material_forbidden: bool = True
    endpoint_material_forbidden: bool = True
    network_access_forbidden: bool = True
    provider_client_use_forbidden: bool = True
    endpoint_use_forbidden: bool = True
    credential_use_forbidden: bool = True
    provider_send_forbidden: bool = True
    live_provider_transport_forbidden: bool = True
    live_model_call_forbidden: bool = True
    does_not_import_provider_sdks: bool = True
    does_not_create_clients: bool = True
    does_not_create_sessions: bool = True
    does_not_create_transports: bool = True
    does_not_open_streams: bool = True
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


_ALLOWED_KINDS = frozenset(
    {
        ProviderClientCustodyKind.CLIENT_CUSTODY_NONE,
        ProviderClientCustodyKind.CLIENT_CUSTODY_NO_CLIENT_PLACEHOLDER,
        ProviderClientCustodyKind.CLIENT_CUSTODY_FUTURE_CLIENT_CONTRACT_PLACEHOLDER,
    }
)
_FORBIDDEN_KINDS = frozenset(
    {
        ProviderClientCustodyKind.CLIENT_CUSTODY_PROVIDER_SDK_CLIENT_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_HTTP_CLIENT_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_SOCKET_CLIENT_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_SESSION_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_TRANSPORT_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_STREAMING_CLIENT_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_RETRY_EXECUTOR_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_REQUEST_BUILDER_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_PROVIDER_SPECIFIC_CLIENT_FORBIDDEN,
        ProviderClientCustodyKind.CLIENT_CUSTODY_UNKNOWN_FORBIDDEN,
    }
)
_MANIFEST_FLAG_FIELDS = (
    "no_client_material",
    "client_values_present",
    "client_references_present",
    "client_instantiation_allowed",
    "sdk_import_allowed",
    "session_creation_allowed",
    "transport_creation_allowed",
    "stream_creation_allowed",
    "request_builder_allowed",
    "retry_executor_allowed",
    "credential_material_present",
    "endpoint_material_present",
    "network_access_allowed",
    "client_runtime_authority",
)
_MANIFEST_MARKER_FIELDS = (
    "provider_client_custody_manifest_only",
    "client_instantiation_forbidden",
    "provider_sdk_import_forbidden",
    "session_creation_forbidden",
    "transport_creation_forbidden",
    "stream_creation_forbidden",
    "request_builder_forbidden",
    "retry_executor_forbidden",
    "credential_material_forbidden",
    "endpoint_material_forbidden",
    "network_access_forbidden",
    "provider_client_use_forbidden",
    "endpoint_use_forbidden",
    "credential_use_forbidden",
    "live_provider_transport_forbidden",
    "live_prompt_assembly_forbidden",
    "live_model_call_forbidden",
    "does_not_import_provider_sdks",
    "does_not_create_clients",
    "does_not_create_sessions",
    "does_not_create_transports",
    "does_not_open_streams",
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
_PREFLIGHT_MARKER_FIELDS = tuple(field_name for field_name in _MANIFEST_MARKER_FIELDS if field_name not in {"provider_client_custody_manifest_only", "live_prompt_assembly_forbidden"}) + (
    "provider_client_custody_preflight_only",
    "provider_send_forbidden",
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
    "endpoint_handle",
    "provider_handle",
    "client_handle",
    "session_handle",
    "transport_handle",
    "socket_handle",
    "http_handle",
    "tool_schema",
    "credential_handle",
)
_CLIENT_PATTERNS = (
    "openai.openai",
    "asyncopenai",
    "anthropic",
    "boto3.client",
    "google.cloud",
    "azure.ai",
    "provider client",
    "client=",
    "session=",
    "transport=",
    "httpx.client",
    "requests.session",
    "aiohttp.clientsession",
    "urllib3",
    "socket",
    "websocket",
    "stream",
    "stream=true",
    "retry",
    "executor",
    "request_builder",
    "completion client",
    "chat client",
    "model client",
    "endpoint=",
    "base_url",
    "api_key",
    "authorization",
    "bearer",
    "token=",
    "secret=",
    "https://",
    "http://",
)
_NEGATIVE_MARKER_FRAGMENTS = (
    "forbidden",
    "does_not_",
    "no_",
    "not_",
    "without_",
    "absent",
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


def _finding(code: str, detail: str, severity: str = "blocker") -> ProviderClientCustodyFinding:
    return ProviderClientCustodyFinding(code=code, detail=detail, severity=severity)


def _constraints() -> tuple[ProviderClientCustodyConstraint, ...]:
    return (
        ProviderClientCustodyConstraint("provider_client_custody_manifest_only", "client custody manifest is evidence metadata only, not provider client custody"),
        ProviderClientCustodyConstraint("no_client_material", "client objects, references, factories, sessions, transports, streams, request builders, and retry executors are forbidden"),
        ProviderClientCustodyConstraint("no_sdk_or_runtime_import", "provider SDK imports and runtime client surfaces are forbidden"),
        ProviderClientCustodyConstraint("no_credentials_endpoints_or_network", "credential material, endpoint material, provider send, sockets, and HTTP are forbidden"),
        ProviderClientCustodyConstraint("no_runtime_side_effects", "model calls, semantic generation, memory, tools, routing, actions, and retention are forbidden"),
    )


def _default_gaps() -> tuple[ProviderClientCustodyGap, ...]:
    return (
        ProviderClientCustodyGap("real_client_review_missing", "future real custody requires external client review without storing a client"),
        ProviderClientCustodyGap("session_lifecycle_evidence_missing", "future real custody requires session lifecycle evidence outside Phase 94"),
        ProviderClientCustodyGap("transport_isolation_evidence_missing", "future real custody requires transport isolation evidence outside Phase 94"),
        ProviderClientCustodyGap("network_egress_review_missing", "future real custody requires network egress review outside Phase 94"),
    )


def _metadata_strings(value: Any, prefix: str = "") -> tuple[tuple[str, str], ...]:
    if _is_dataclass_instance(value):
        return _metadata_strings(asdict(value), prefix)
    if isinstance(value, Mapping):
        out: list[tuple[str, str]] = []
        for key, item in value.items():
            key_text = str(key)
            key_path = f"{prefix}.{key_text}" if prefix else key_text
            out.append((key_path, key_text))
            out.extend(_metadata_strings(item, key_path))
        return tuple(out)
    if isinstance(value, (tuple, list, set, frozenset)):
        out = []
        for index, item in enumerate(value):
            out.extend(_metadata_strings(item, f"{prefix}[{index}]"))
        return tuple(out)
    if isinstance(value, str):
        return ((prefix, value),)
    return ()


def _is_negative_marker_name(path: str, text: str) -> bool:
    lowered = (path.rsplit(".", 1)[-1] if path else text).lower()
    return any(fragment in lowered for fragment in _NEGATIVE_MARKER_FRAGMENTS)


def _client_pattern_findings(*values: Any) -> tuple[ProviderClientCustodyFinding, ...]:
    findings: list[ProviderClientCustodyFinding] = []
    for value in values:
        for path, text in _metadata_strings(value):
            lowered = text.lower()
            if _is_negative_marker_name(path, text):
                continue
            for pattern in _CLIENT_PATTERNS:
                if pattern in lowered:
                    code = "client_like_metadata_detected"
                    if pattern in {"openai.openai", "asyncopenai", "anthropic", "boto3.client", "google.cloud", "azure.ai"}:
                        code = "sdk_import_detected"
                    elif pattern in {"session=", "requests.session", "aiohttp.clientsession"}:
                        code = "session_material_detected"
                    elif pattern == "transport=":
                        code = "transport_material_detected"
                    elif pattern in {"stream", "stream=true"}:
                        code = "stream_material_detected"
                    elif pattern in {"retry", "executor"}:
                        code = "retry_executor_material_detected"
                    elif pattern == "request_builder":
                        code = "request_builder_material_detected"
                    elif pattern in {"endpoint=", "base_url", "https://", "http://"}:
                        code = "endpoint_material_detected"
                    elif pattern in {"api_key", "authorization", "bearer", "token=", "secret="}:
                        code = "credential_material_detected"
                    elif pattern in {"socket", "websocket", "httpx.client", "urllib3"}:
                        code = "network_material_detected"
                    findings.append(_finding(code, f"metadata at {path or '<value>'} matched forbidden provider client custody pattern {pattern!r}"))
                    break
    return tuple(findings)


def _runtime_marker_findings(value: Any) -> tuple[ProviderClientCustodyFinding, ...]:
    findings: list[ProviderClientCustodyFinding] = []
    for path, text in _metadata_strings(value):
        lowered = text.lower()
        if _is_negative_marker_name(path, text):
            continue
        for key in _RUNTIME_MARKER_KEYS:
            if key in lowered:
                findings.append(_finding("runtime_marker_detected", f"metadata at {path or '<value>'} included forbidden runtime marker {key!r}"))
                break
    return tuple(findings)


def _status_for_findings(findings: Sequence[ProviderClientCustodyFinding], missing: Sequence[str]) -> str:
    codes = {finding.code for finding in findings}
    if "invalid_client_custody_kind" in codes:
        return ProviderClientCustodyStatus.CLIENT_CUSTODY_INVALID
    if any(code in codes for code in ("forbidden_client_custody_kind", "client_value_present", "client_like_metadata_detected")):
        return ProviderClientCustodyStatus.CLIENT_CUSTODY_FORBIDDEN_CLIENT_DETECTED
    if any(code in codes for code in ("client_reference_present",)):
        return ProviderClientCustodyStatus.CLIENT_CUSTODY_CLIENT_REFERENCE_DETECTED
    if any(code in codes for code in ("sdk_import_allowed", "sdk_import_detected")):
        return ProviderClientCustodyStatus.CLIENT_CUSTODY_SDK_IMPORT_DETECTED
    if any(code in codes for code in ("session_creation_allowed", "session_material_detected")):
        return ProviderClientCustodyStatus.CLIENT_CUSTODY_SESSION_DETECTED
    if any(code in codes for code in ("transport_creation_allowed", "transport_material_detected")):
        return ProviderClientCustodyStatus.CLIENT_CUSTODY_TRANSPORT_DETECTED
    if any(code in codes for code in ("stream_creation_allowed", "stream_material_detected")):
        return ProviderClientCustodyStatus.CLIENT_CUSTODY_STREAM_DETECTED
    if any(code in codes for code in ("endpoint_material_present", "endpoint_material_detected")):
        return ProviderClientCustodyStatus.CLIENT_CUSTODY_ENDPOINT_DETECTED
    if any(code in codes for code in ("credential_material_present", "credential_material_detected")):
        return ProviderClientCustodyStatus.CLIENT_CUSTODY_CREDENTIALS_DETECTED
    if any(code in codes for code in ("network_access_allowed", "network_material_detected")):
        return ProviderClientCustodyStatus.CLIENT_CUSTODY_NETWORK_DETECTED
    if any(code in codes for code in ("runtime_marker_detected", "runtime_authority_detected", "client_marker_missing", "client_instantiation_allowed", "request_builder_material_detected", "retry_executor_material_detected", "request_builder_allowed", "retry_executor_allowed")):
        return ProviderClientCustodyStatus.CLIENT_CUSTODY_RUNTIME_AUTHORITY_DETECTED
    if missing:
        return ProviderClientCustodyStatus.CLIENT_CUSTODY_INCOMPLETE
    return ProviderClientCustodyStatus.CLIENT_CUSTODY_NO_CLIENTS


def build_provider_client_custody_manifest(
    *,
    client_custody_kind: str = ProviderClientCustodyKind.CLIENT_CUSTODY_NONE,
    linked_capability_manifest: ProviderTransportCapabilityManifest | Mapping[str, Any] | None = None,
    linked_capability_manifest_id: str = "",
    linked_capability_digest: str = "",
    linked_credential_custody_manifest: ProviderCredentialCustodyManifest | Mapping[str, Any] | None = None,
    linked_credential_custody_manifest_id: str = "",
    linked_credential_custody_digest: str = "",
    linked_endpoint_custody_manifest: ProviderEndpointCustodyManifest | Mapping[str, Any] | None = None,
    linked_endpoint_custody_manifest_id: str = "",
    linked_endpoint_custody_digest: str = "",
    linked_endpoint_custody_preflight: ProviderEndpointCustodyPreflight | Mapping[str, Any] | None = None,
    linked_endpoint_custody_preflight_id: str = "",
    linked_endpoint_custody_preflight_digest: str = "",
    declared_client_properties: Sequence[str] = (),
    forbidden_client_properties: Sequence[str] = (),
    missing_required_evidence: Sequence[str] = (),
    metadata_evidence: Any = None,
    no_client_material: bool = True,
    client_values_present: bool = False,
    client_references_present: bool = False,
    client_instantiation_allowed: bool = False,
    sdk_import_allowed: bool = False,
    session_creation_allowed: bool = False,
    transport_creation_allowed: bool = False,
    stream_creation_allowed: bool = False,
    request_builder_allowed: bool = False,
    retry_executor_allowed: bool = False,
    credential_material_present: bool = False,
    endpoint_material_present: bool = False,
    network_access_allowed: bool = False,
    client_runtime_authority: bool = False,
    marker_overrides: Mapping[str, bool] | None = None,
) -> ProviderClientCustodyManifest:
    linked_capability = _mapping(linked_capability_manifest)
    linked_credential = _mapping(linked_credential_custody_manifest)
    linked_endpoint = _mapping(linked_endpoint_custody_manifest)
    linked_endpoint_preflight = _mapping(linked_endpoint_custody_preflight)
    capability_id = linked_capability_manifest_id or str(linked_capability.get("capability_manifest_id", ""))
    capability_digest = linked_capability_digest or str(linked_capability.get("capability_digest", ""))
    credential_id = linked_credential_custody_manifest_id or str(linked_credential.get("custody_manifest_id", ""))
    credential_digest = linked_credential_custody_digest or str(linked_credential.get("custody_digest", ""))
    endpoint_id = linked_endpoint_custody_manifest_id or str(linked_endpoint.get("endpoint_manifest_id", ""))
    endpoint_digest = linked_endpoint_custody_digest or str(linked_endpoint.get("endpoint_digest", ""))
    endpoint_preflight_id = linked_endpoint_custody_preflight_id or str(linked_endpoint_preflight.get("endpoint_preflight_id", ""))
    endpoint_preflight_digest = linked_endpoint_custody_preflight_digest or str(linked_endpoint_preflight.get("endpoint_preflight_digest", ""))
    findings: list[ProviderClientCustodyFinding] = []
    kind = str(client_custody_kind)
    if kind in _FORBIDDEN_KINDS:
        findings.append(_finding("forbidden_client_custody_kind", f"{kind} is forbidden in Phase 94"))
    elif kind not in _ALLOWED_KINDS:
        findings.append(_finding("invalid_client_custody_kind", "unknown client custody kind is forbidden"))
    flag_values = {
        "no_client_material": bool(no_client_material),
        "client_values_present": bool(client_values_present),
        "client_references_present": bool(client_references_present),
        "client_instantiation_allowed": bool(client_instantiation_allowed),
        "sdk_import_allowed": bool(sdk_import_allowed),
        "session_creation_allowed": bool(session_creation_allowed),
        "transport_creation_allowed": bool(transport_creation_allowed),
        "stream_creation_allowed": bool(stream_creation_allowed),
        "request_builder_allowed": bool(request_builder_allowed),
        "retry_executor_allowed": bool(retry_executor_allowed),
        "credential_material_present": bool(credential_material_present),
        "endpoint_material_present": bool(endpoint_material_present),
        "network_access_allowed": bool(network_access_allowed),
        "client_runtime_authority": bool(client_runtime_authority),
    }
    if not flag_values["no_client_material"] or flag_values["client_values_present"]:
        findings.append(_finding("client_value_present", "client material is forbidden"))
    if flag_values["client_references_present"]:
        findings.append(_finding("client_reference_present", "client references are forbidden"))
    for field_name in (
        "client_instantiation_allowed",
        "sdk_import_allowed",
        "session_creation_allowed",
        "transport_creation_allowed",
        "stream_creation_allowed",
        "request_builder_allowed",
        "retry_executor_allowed",
        "credential_material_present",
        "endpoint_material_present",
        "network_access_allowed",
        "client_runtime_authority",
    ):
        if flag_values[field_name]:
            findings.append(_finding(field_name if field_name != "client_runtime_authority" else "runtime_authority_detected", f"{field_name} must remain false"))
    evidence = (kind, tuple(declared_client_properties), tuple(forbidden_client_properties), tuple(missing_required_evidence), metadata_evidence)
    findings.extend(_client_pattern_findings(evidence))
    findings.extend(_runtime_marker_findings(metadata_evidence))
    markers = {field_name: True for field_name in _MANIFEST_MARKER_FIELDS}
    if marker_overrides:
        markers.update({str(key): bool(value) for key, value in marker_overrides.items() if str(key) in markers})
    for field_name, value in markers.items():
        if value is not True:
            findings.append(_finding("client_marker_missing", f"{field_name} must be true"))
    missing = tuple(str(item) for item in missing_required_evidence)
    status = _status_for_findings(findings, missing)
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "provider client custody manifest is metadata-only and contains no clients, client references, SDK imports, sessions, transports, streams, request builders, retry executors, credentials, endpoints, network authority, or runtime authority"
    manifest = ProviderClientCustodyManifest(
        client_manifest_id="",
        client_status=status,
        client_custody_kind=kind,
        linked_capability_manifest_id=capability_id,
        linked_capability_digest=capability_digest,
        linked_credential_custody_manifest_id=credential_id,
        linked_credential_custody_digest=credential_digest,
        linked_endpoint_custody_manifest_id=endpoint_id,
        linked_endpoint_custody_digest=endpoint_digest,
        linked_endpoint_custody_preflight_id=endpoint_preflight_id,
        linked_endpoint_custody_preflight_digest=endpoint_preflight_digest,
        declared_client_properties=tuple(str(item) for item in declared_client_properties),
        forbidden_client_properties=tuple(str(item) for item in forbidden_client_properties),
        missing_required_evidence=missing,
        client_gaps=_default_gaps(),
        findings=tuple(findings),
        constraints=_constraints(),
        rationale=rationale[:1000],
        client_digest="",
        **flag_values,
        **markers,
    )
    digest = compute_provider_client_custody_digest(manifest)
    return replace(manifest, client_manifest_id=f"provider-client-custody:{digest[:16]}", client_digest=digest)


def _digest_payload(data: Mapping[str, Any], digest_field: str, id_field: str) -> dict[str, Any]:
    payload = dict(data)
    payload[digest_field] = ""
    payload[id_field] = ""
    return payload


def compute_provider_client_custody_digest(manifest: ProviderClientCustodyManifest | Mapping[str, Any]) -> str:
    return _stable_digest(_digest_payload(_mapping(manifest), "client_digest", "client_manifest_id"))


def compute_provider_client_custody_preflight_digest(preflight: ProviderClientCustodyPreflight | Mapping[str, Any]) -> str:
    return _stable_digest(_digest_payload(_mapping(preflight), "client_preflight_digest", "client_preflight_id"))


def validate_provider_client_custody_manifest(manifest: ProviderClientCustodyManifest | Mapping[str, Any]) -> tuple[ProviderClientCustodyFinding, ...]:
    data = _mapping(manifest)
    findings: list[ProviderClientCustodyFinding] = []
    if not data:
        return (_finding("client_manifest_missing", "ProviderClientCustodyManifest is required"),)
    digest = str(data.get("client_digest", ""))
    if digest and compute_provider_client_custody_digest(data) != digest:
        findings.append(_finding("client_digest_mismatch", "client custody digest does not match manifest fields"))
    kind = str(data.get("client_custody_kind", ""))
    if kind in _FORBIDDEN_KINDS:
        findings.append(_finding("forbidden_client_custody_kind", f"{kind} is forbidden in Phase 94"))
    elif kind not in _ALLOWED_KINDS:
        findings.append(_finding("invalid_client_custody_kind", "unknown client custody kind is forbidden"))
    for field_name in _MANIFEST_FLAG_FIELDS:
        value = data.get(field_name)
        if field_name == "no_client_material":
            if value is not True:
                findings.append(_finding("client_value_present", "no_client_material must be true"))
        elif value is True:
            code = field_name if field_name != "client_runtime_authority" else "runtime_authority_detected"
            findings.append(_finding(code, f"{field_name} must remain false"))
    for field_name in _MANIFEST_MARKER_FIELDS:
        if data.get(field_name) is not True:
            findings.append(_finding("client_marker_missing", f"{field_name} must be true"))
    findings.extend(_client_pattern_findings(data.get("declared_client_properties", ()), data.get("forbidden_client_properties", ())))
    findings.extend(_runtime_marker_findings(data.get("declared_client_properties", ())))
    return tuple(findings)


def _preflight_status_for_findings(findings: Sequence[ProviderClientCustodyFinding], manifest_status: str, allowed: bool) -> str:
    if allowed and not findings:
        return ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_NO_CLIENTS_ALLOWED
    codes = {finding.code for finding in findings}
    if any(code in codes for code in ("client_manifest_missing", "invalid_client_custody_kind", "client_digest_mismatch", "capability_digest_mismatch", "credential_custody_digest_mismatch", "endpoint_custody_digest_mismatch", "endpoint_custody_preflight_digest_mismatch")):
        return ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_INVALID_INPUT
    if any(code in codes for code in ("forbidden_client_custody_kind", "client_value_present", "client_like_metadata_detected")):
        return ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_FORBIDDEN_CLIENT_DETECTED
    if any(code in codes for code in ("client_reference_present", "requested_client_instantiation", "client_instantiation_allowed", "client_reference_not_negated", "client_material_not_negated", "client_instantiation_not_negated")):
        return ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_CLIENT_INSTANTIATION_FORBIDDEN
    if any(code in codes for code in ("requested_sdk_import", "sdk_import_allowed", "sdk_import_detected", "provider_sdk_not_negated")):
        return ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_SDK_IMPORT_DETECTED
    if any(code in codes for code in ("requested_session_creation", "session_creation_allowed", "session_material_detected", "session_creation_not_negated")):
        return ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_SESSION_DETECTED
    if any(code in codes for code in ("requested_transport_creation", "transport_creation_allowed", "transport_material_detected", "transport_creation_not_negated")):
        return ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_TRANSPORT_DETECTED
    if any(code in codes for code in ("requested_stream_creation", "stream_creation_allowed", "stream_material_detected", "stream_creation_not_negated")):
        return ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_STREAM_DETECTED
    if any(code in codes for code in ("requested_endpoint_material", "endpoint_material_present", "endpoint_material_detected", "endpoint_not_negated", "endpoint_custody_endpoint_detected", "endpoint_preflight_endpoint_detected")):
        return ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_ENDPOINT_DETECTED
    if any(code in codes for code in ("requested_credential_material", "credential_material_present", "credential_material_detected", "credentials_not_negated", "credential_custody_secret_detected")):
        return ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_CREDENTIALS_DETECTED
    if any(code in codes for code in ("requested_network_access", "network_access_allowed", "network_material_detected", "network_not_negated", "provider_send_not_negated", "http_not_negated", "socket_not_negated", "requested_registration", "capability_real_transport_detected")):
        return ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_NETWORK_DETECTED
    if any(code in codes for code in ("runtime_marker_detected", "runtime_authority_detected", "client_marker_missing", "runtime_flag_not_negated", "request_builder_material_detected", "retry_executor_material_detected", "requested_request_builder", "requested_retry_executor", "request_builder_not_negated", "retry_executor_not_negated")):
        return ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED
    if manifest_status == ProviderClientCustodyStatus.CLIENT_CUSTODY_INCOMPLETE or "missing_required_evidence" in codes:
        return ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_INCOMPLETE_EVIDENCE
    return ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_DENIED


def evaluate_provider_client_custody_preflight(
    client_manifest: ProviderClientCustodyManifest | Mapping[str, Any] | None,
    capability_manifest: ProviderTransportCapabilityManifest | Mapping[str, Any] | None = None,
    credential_custody_manifest: ProviderCredentialCustodyManifest | Mapping[str, Any] | None = None,
    endpoint_custody_manifest: ProviderEndpointCustodyManifest | Mapping[str, Any] | None = None,
    endpoint_custody_preflight: ProviderEndpointCustodyPreflight | Mapping[str, Any] | None = None,
    *,
    requested_client_custody_kind: str = ProviderClientCustodyKind.CLIENT_CUSTODY_NONE,
    requested_client_instantiation: bool = False,
    requested_sdk_import: bool = False,
    requested_session_creation: bool = False,
    requested_transport_creation: bool = False,
    requested_stream_creation: bool = False,
    requested_request_builder: bool = False,
    requested_retry_executor: bool = False,
    requested_credential_material: bool = False,
    requested_endpoint_material: bool = False,
    requested_network_access: bool = False,
    requested_registration: bool = False,
    internal_only: bool = True,
    no_client_material: bool = True,
    no_client_references: bool = True,
    no_client_instantiation: bool = True,
    no_sdk_import: bool = True,
    no_session_creation: bool = True,
    no_transport_creation: bool = True,
    no_stream_creation: bool = True,
    no_request_builder: bool = True,
    no_retry_executor: bool = True,
    no_credentials: bool = True,
    no_endpoints: bool = True,
    no_network: bool = True,
    no_provider_send: bool = True,
    no_http: bool = True,
    no_socket: bool = True,
    no_provider_sdk: bool = True,
    no_tools: bool = True,
    no_memory: bool = True,
    no_retention: bool = True,
    no_actions: bool = True,
    no_routing: bool = True,
    no_semantic_generation: bool = True,
    metadata_evidence: Any = None,
) -> ProviderClientCustodyPreflight:
    manifest = _mapping(client_manifest)
    capability = _mapping(capability_manifest)
    credential = _mapping(credential_custody_manifest)
    endpoint = _mapping(endpoint_custody_manifest)
    endpoint_preflight = _mapping(endpoint_custody_preflight)
    findings: list[ProviderClientCustodyFinding] = []
    warnings: list[str] = []
    if not manifest:
        findings.append(_finding("client_manifest_missing", "client custody manifest is required"))
    else:
        findings.extend(validate_provider_client_custody_manifest(client_manifest or {}))
        manifest_status = str(manifest.get("client_status", ""))
        status_to_code = {
            ProviderClientCustodyStatus.CLIENT_CUSTODY_FORBIDDEN_CLIENT_DETECTED: "client_value_present",
            ProviderClientCustodyStatus.CLIENT_CUSTODY_CLIENT_REFERENCE_DETECTED: "client_reference_present",
            ProviderClientCustodyStatus.CLIENT_CUSTODY_SDK_IMPORT_DETECTED: "sdk_import_detected",
            ProviderClientCustodyStatus.CLIENT_CUSTODY_SESSION_DETECTED: "session_material_detected",
            ProviderClientCustodyStatus.CLIENT_CUSTODY_TRANSPORT_DETECTED: "transport_material_detected",
            ProviderClientCustodyStatus.CLIENT_CUSTODY_STREAM_DETECTED: "stream_material_detected",
            ProviderClientCustodyStatus.CLIENT_CUSTODY_ENDPOINT_DETECTED: "endpoint_material_present",
            ProviderClientCustodyStatus.CLIENT_CUSTODY_CREDENTIALS_DETECTED: "credential_material_present",
            ProviderClientCustodyStatus.CLIENT_CUSTODY_NETWORK_DETECTED: "network_access_allowed",
            ProviderClientCustodyStatus.CLIENT_CUSTODY_RUNTIME_AUTHORITY_DETECTED: "runtime_authority_detected",
            ProviderClientCustodyStatus.CLIENT_CUSTODY_INCOMPLETE: "missing_required_evidence",
            ProviderClientCustodyStatus.CLIENT_CUSTODY_INVALID: "invalid_client_custody_kind",
        }
        if manifest_status in status_to_code:
            findings.append(_finding(status_to_code[manifest_status], f"client custody manifest reports {manifest_status}"))
    requested_kind = str(requested_client_custody_kind)
    if requested_kind in _FORBIDDEN_KINDS:
        findings.append(_finding("forbidden_client_custody_kind", f"{requested_kind} is forbidden in Phase 94"))
    elif requested_kind not in _ALLOWED_KINDS:
        findings.append(_finding("invalid_client_custody_kind", "unknown requested client custody kind is forbidden"))
    requested_flags = {
        "requested_client_instantiation": requested_client_instantiation,
        "requested_sdk_import": requested_sdk_import,
        "requested_session_creation": requested_session_creation,
        "requested_transport_creation": requested_transport_creation,
        "requested_stream_creation": requested_stream_creation,
        "requested_request_builder": requested_request_builder,
        "requested_retry_executor": requested_retry_executor,
        "requested_credential_material": requested_credential_material,
        "requested_endpoint_material": requested_endpoint_material,
        "requested_network_access": requested_network_access,
        "requested_registration": requested_registration,
    }
    for field_name, value in requested_flags.items():
        if bool(value):
            findings.append(_finding(field_name, f"{field_name} is forbidden in Phase 94"))
    no_flags = {
        "no_client_material": no_client_material,
        "no_client_references": no_client_references,
        "no_client_instantiation": no_client_instantiation,
        "no_sdk_import": no_sdk_import,
        "no_session_creation": no_session_creation,
        "no_transport_creation": no_transport_creation,
        "no_stream_creation": no_stream_creation,
        "no_request_builder": no_request_builder,
        "no_retry_executor": no_retry_executor,
        "no_credentials": no_credentials,
        "no_endpoints": no_endpoints,
        "no_network": no_network,
        "no_provider_send": no_provider_send,
        "no_http": no_http,
        "no_socket": no_socket,
        "no_provider_sdk": no_provider_sdk,
        "no_tools": no_tools,
        "no_memory": no_memory,
        "no_retention": no_retention,
        "no_actions": no_actions,
        "no_routing": no_routing,
        "no_semantic_generation": no_semantic_generation,
    }
    no_flag_codes = {
        "no_client_material": "client_material_not_negated",
        "no_client_references": "client_reference_not_negated",
        "no_client_instantiation": "client_instantiation_not_negated",
        "no_sdk_import": "sdk_import_not_negated",
        "no_session_creation": "session_creation_not_negated",
        "no_transport_creation": "transport_creation_not_negated",
        "no_stream_creation": "stream_creation_not_negated",
        "no_request_builder": "request_builder_not_negated",
        "no_retry_executor": "retry_executor_not_negated",
        "no_credentials": "credentials_not_negated",
        "no_endpoints": "endpoint_not_negated",
        "no_network": "network_not_negated",
        "no_provider_send": "provider_send_not_negated",
        "no_http": "http_not_negated",
        "no_socket": "socket_not_negated",
        "no_provider_sdk": "provider_sdk_not_negated",
        "no_tools": "runtime_flag_not_negated",
        "no_memory": "runtime_flag_not_negated",
        "no_retention": "runtime_flag_not_negated",
        "no_actions": "runtime_flag_not_negated",
        "no_routing": "runtime_flag_not_negated",
        "no_semantic_generation": "runtime_flag_not_negated",
    }
    for field_name, value in no_flags.items():
        if bool(value) is not True:
            findings.append(_finding(no_flag_codes[field_name], f"{field_name} must remain true"))
    if internal_only is not True:
        findings.append(_finding("runtime_flag_not_negated", "internal_only must remain true"))
    if capability:
        cap_digest = str(capability.get("capability_digest", ""))
        if cap_digest and compute_provider_transport_capability_digest(capability_manifest or {}) != cap_digest:
            findings.append(_finding("capability_digest_mismatch", "linked capability digest mismatch"))
        if not provider_transport_capability_is_null_only(capability_manifest or {}):
            findings.append(_finding("capability_real_transport_detected", "linked Phase 91 capability is not null-only"))
        if str(capability.get("capability_status", "")) != ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_NULL_ONLY:
            findings.append(_finding("capability_real_transport_detected", "linked Phase 91 capability status is not null-only metadata"))
    if credential:
        cred_digest = str(credential.get("custody_digest", ""))
        if cred_digest and compute_provider_credential_custody_digest(credential_custody_manifest or {}) != cred_digest:
            findings.append(_finding("credential_custody_digest_mismatch", "linked credential custody digest mismatch"))
        if not provider_credential_custody_contains_no_secrets(credential_custody_manifest or {}):
            findings.append(_finding("credential_custody_secret_detected", "linked Phase 92 credential custody is not no-secret metadata"))
        if str(credential.get("custody_status", "")) != ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_NO_SECRETS:
            findings.append(_finding("credential_custody_secret_detected", "linked Phase 92 credential custody status is not no-secret"))
    if endpoint:
        endpoint_digest = str(endpoint.get("endpoint_digest", ""))
        if endpoint_digest and compute_provider_endpoint_custody_digest(endpoint_custody_manifest or {}) != endpoint_digest:
            findings.append(_finding("endpoint_custody_digest_mismatch", "linked endpoint custody digest mismatch"))
        if not provider_endpoint_custody_contains_no_endpoints(endpoint_custody_manifest or {}):
            findings.append(_finding("endpoint_custody_endpoint_detected", "linked Phase 93 endpoint custody is not no-endpoint metadata"))
        if str(endpoint.get("endpoint_status", "")) != ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_NO_ENDPOINTS:
            findings.append(_finding("endpoint_custody_endpoint_detected", "linked Phase 93 endpoint custody status is not no-endpoint"))
    if endpoint_preflight:
        endpoint_preflight_digest = str(endpoint_preflight.get("endpoint_preflight_digest", ""))
        if endpoint_preflight_digest and compute_provider_endpoint_custody_preflight_digest(endpoint_custody_preflight or {}) != endpoint_preflight_digest:
            findings.append(_finding("endpoint_custody_preflight_digest_mismatch", "linked endpoint custody preflight digest mismatch"))
        if not provider_endpoint_preflight_remains_metadata_only(endpoint_custody_preflight or {}):
            findings.append(_finding("endpoint_preflight_endpoint_detected", "linked Phase 93 endpoint preflight is not metadata-only no-endpoint"))
        if str(endpoint_preflight.get("endpoint_preflight_status", "")) not in {ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_NO_ENDPOINTS_ALLOWED}:
            findings.append(_finding("endpoint_preflight_endpoint_detected", "linked Phase 93 endpoint preflight status is not no-endpoint metadata"))
    for field_name in (
        "client_instantiation_allowed",
        "sdk_import_allowed",
        "session_creation_allowed",
        "transport_creation_allowed",
        "stream_creation_allowed",
        "request_builder_allowed",
        "retry_executor_allowed",
        "credential_material_present",
        "endpoint_material_present",
        "network_access_allowed",
        "client_runtime_authority",
    ):
        if manifest.get(field_name) is True:
            findings.append(_finding(field_name if field_name != "client_runtime_authority" else "runtime_authority_detected", f"manifest {field_name} is forbidden"))
    if manifest.get("no_client_material") is not True or manifest.get("client_values_present") is True:
        findings.append(_finding("client_value_present", "manifest client values are forbidden"))
    if manifest.get("client_references_present") is True:
        findings.append(_finding("client_reference_present", "manifest client references are forbidden"))
    for field_name in _MANIFEST_MARKER_FIELDS:
        if manifest and manifest.get(field_name) is not True:
            findings.append(_finding("client_marker_missing", f"manifest {field_name} must be true"))
    findings.extend(_client_pattern_findings(metadata_evidence, manifest.get("declared_client_properties", ()), manifest.get("forbidden_client_properties", ())))
    findings.extend(_runtime_marker_findings(metadata_evidence))
    manifest_status = str(manifest.get("client_status", ""))
    allowed = bool(
        manifest
        and not findings
        and manifest_status == ProviderClientCustodyStatus.CLIENT_CUSTODY_NO_CLIENTS
        and requested_kind in _ALLOWED_KINDS
        and all(bool(value) is False for value in requested_flags.values())
        and all(bool(value) is True for value in no_flags.values())
        and internal_only is True
    )
    status = _preflight_status_for_findings(findings, manifest_status, allowed)
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:5]) or "client preflight permits only no-client metadata compatibility and keeps client/session/transport/SDK/credential/endpoint/network/provider use forbidden"
    preflight = ProviderClientCustodyPreflight(
        client_preflight_id="",
        client_preflight_status=status,
        client_manifest_id=str(manifest.get("client_manifest_id", "")),
        client_status=manifest_status,
        client_digest=str(manifest.get("client_digest", "")),
        capability_manifest_id=str(capability.get("capability_manifest_id", manifest.get("linked_capability_manifest_id", ""))),
        capability_digest=str(capability.get("capability_digest", manifest.get("linked_capability_digest", ""))),
        credential_custody_manifest_id=str(credential.get("custody_manifest_id", manifest.get("linked_credential_custody_manifest_id", ""))),
        credential_custody_digest=str(credential.get("custody_digest", manifest.get("linked_credential_custody_digest", ""))),
        endpoint_custody_manifest_id=str(endpoint.get("endpoint_manifest_id", manifest.get("linked_endpoint_custody_manifest_id", ""))),
        endpoint_custody_digest=str(endpoint.get("endpoint_digest", manifest.get("linked_endpoint_custody_digest", ""))),
        endpoint_custody_preflight_id=str(endpoint_preflight.get("endpoint_preflight_id", manifest.get("linked_endpoint_custody_preflight_id", ""))),
        endpoint_custody_preflight_digest=str(endpoint_preflight.get("endpoint_preflight_digest", manifest.get("linked_endpoint_custody_preflight_digest", ""))),
        requested_client_custody_kind=requested_kind,
        requested_registration=bool(requested_registration),
        client_allowed=allowed,
        client_material_allowed=False,
        client_reference_allowed=False,
        client_instantiation_allowed=False,
        sdk_import_allowed=False,
        session_creation_allowed=False,
        transport_creation_allowed=False,
        stream_creation_allowed=False,
        request_builder_allowed=False,
        retry_executor_allowed=False,
        credential_material_allowed=False,
        endpoint_material_allowed=False,
        network_access_allowed=False,
        provider_send_allowed=False,
        socket_allowed=False,
        http_allowed=False,
        provider_sdk_allowed=False,
        semantic_generation_allowed=False,
        findings=tuple(findings),
        warnings=tuple(warnings),
        constraints=_constraints(),
        client_gaps=tuple(manifest.get("client_gaps", _default_gaps())),
        rationale=rationale[:1000],
        client_preflight_digest="",
    )
    digest = compute_provider_client_custody_preflight_digest(preflight)
    return replace(preflight, client_preflight_id=f"provider-client-preflight:{digest[:16]}", client_preflight_digest=digest)


def provider_client_custody_contains_no_clients(manifest: ProviderClientCustodyManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(
        data
        and data.get("client_status") == ProviderClientCustodyStatus.CLIENT_CUSTODY_NO_CLIENTS
        and data.get("client_custody_kind") in _ALLOWED_KINDS
        and data.get("no_client_material") is True
        and data.get("client_values_present") is False
        and data.get("client_references_present") is False
        and data.get("client_instantiation_allowed") is False
        and data.get("sdk_import_allowed") is False
        and data.get("session_creation_allowed") is False
        and data.get("transport_creation_allowed") is False
        and data.get("stream_creation_allowed") is False
        and data.get("request_builder_allowed") is False
        and data.get("retry_executor_allowed") is False
        and not validate_provider_client_custody_manifest(data)
    )


def _subject_bool(subject: ProviderClientCustodyManifest | ProviderClientCustodyPreflight | Mapping[str, Any], field_name: str, expected: bool) -> bool:
    return _mapping(subject).get(field_name) is expected


def provider_client_custody_forbids_client_instantiation(subject: ProviderClientCustodyManifest | ProviderClientCustodyPreflight | Mapping[str, Any]) -> bool:
    return _subject_bool(subject, "client_instantiation_forbidden", True) and _subject_bool(subject, "does_not_create_clients", True) and _subject_bool(subject, "client_instantiation_allowed", False)


def provider_client_custody_forbids_sdk_import(subject: ProviderClientCustodyManifest | ProviderClientCustodyPreflight | Mapping[str, Any]) -> bool:
    return _subject_bool(subject, "provider_sdk_import_forbidden", True) and _subject_bool(subject, "does_not_import_provider_sdks", True) and _subject_bool(subject, "sdk_import_allowed", False)


def provider_client_custody_forbids_session_creation(subject: ProviderClientCustodyManifest | ProviderClientCustodyPreflight | Mapping[str, Any]) -> bool:
    return _subject_bool(subject, "session_creation_forbidden", True) and _subject_bool(subject, "does_not_create_sessions", True) and _subject_bool(subject, "session_creation_allowed", False)


def provider_client_custody_forbids_transport_creation(subject: ProviderClientCustodyManifest | ProviderClientCustodyPreflight | Mapping[str, Any]) -> bool:
    return _subject_bool(subject, "transport_creation_forbidden", True) and _subject_bool(subject, "does_not_create_transports", True) and _subject_bool(subject, "transport_creation_allowed", False)


def provider_client_custody_forbids_streaming(subject: ProviderClientCustodyManifest | ProviderClientCustodyPreflight | Mapping[str, Any]) -> bool:
    return _subject_bool(subject, "stream_creation_forbidden", True) and _subject_bool(subject, "does_not_open_streams", True) and _subject_bool(subject, "stream_creation_allowed", False)


def provider_client_custody_has_no_network(subject: ProviderClientCustodyManifest | ProviderClientCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(data.get("network_access_forbidden") is True and data.get("does_not_make_network_calls") is True and data.get("does_not_open_sockets") is True and data.get("does_not_make_http_requests") is True and data.get("network_access_allowed") is False)


def provider_client_custody_has_no_credentials(subject: ProviderClientCustodyManifest | ProviderClientCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    present_or_allowed = data.get("credential_material_present", data.get("credential_material_allowed", False))
    return bool(data.get("credential_material_forbidden") is True and data.get("credential_use_forbidden") is True and present_or_allowed is False)


def provider_client_custody_has_no_endpoints(subject: ProviderClientCustodyManifest | ProviderClientCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    present_or_allowed = data.get("endpoint_material_present", data.get("endpoint_material_allowed", False))
    return bool(data.get("endpoint_material_forbidden") is True and data.get("endpoint_use_forbidden") is True and present_or_allowed is False)


def provider_client_custody_has_no_runtime_authority(subject: ProviderClientCustodyManifest | ProviderClientCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    authority = data.get("client_runtime_authority", False)
    return bool(
        authority is False
        and data.get("does_not_call_llm") is True
        and data.get("does_not_send_to_provider") is True
        and data.get("does_not_retrieve_memory") is True
        and data.get("does_not_write_memory") is True
        and data.get("does_not_execute_or_route_work") is True
        and data.get("does_not_admit_work") is True
    )


def provider_client_preflight_denies_real_clients(preflight: ProviderClientCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(
        data
        and data.get("client_preflight_status") != ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_NO_CLIENTS_ALLOWED
        and data.get("provider_client_use_forbidden") is True
        and data.get("client_material_allowed") is False
        and data.get("client_instantiation_allowed") is False
    )


def provider_client_preflight_remains_metadata_only(preflight: ProviderClientCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(
        data
        and data.get("client_preflight_status") == ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_NO_CLIENTS_ALLOWED
        and data.get("provider_client_custody_preflight_only") is True
        and data.get("client_allowed") is True
        and data.get("client_material_allowed") is False
        and data.get("client_reference_allowed") is False
        and provider_client_custody_forbids_client_instantiation(data)
        and provider_client_custody_forbids_sdk_import(data)
        and provider_client_custody_forbids_session_creation(data)
        and provider_client_custody_forbids_transport_creation(data)
        and provider_client_custody_forbids_streaming(data)
        and provider_client_custody_has_no_network(data)
        and provider_client_custody_has_no_credentials(data)
        and provider_client_custody_has_no_endpoints(data)
        and provider_client_custody_has_no_runtime_authority(data)
    )


def explain_provider_client_custody_findings(findings: Sequence[ProviderClientCustodyFinding]) -> tuple[str, ...]:
    return tuple(f"{finding.severity}:{finding.code}:{finding.detail}" for finding in findings)


def summarize_provider_client_custody_preflight(preflight: ProviderClientCustodyPreflight | Mapping[str, Any]) -> str:
    data = _mapping(preflight)
    finding_codes = ",".join(str(item.get("code", "")) if isinstance(item, Mapping) else getattr(item, "code", "") for item in data.get("findings", ()))
    return (
        f"Provider client custody preflight {data.get('client_preflight_id', '')}: "
        f"{data.get('client_preflight_status', ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_DENIED)}; "
        f"client_allowed={data.get('client_allowed', False)}; findings={finding_codes or 'none'}"
    )
