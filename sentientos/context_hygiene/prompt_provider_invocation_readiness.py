from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_provider_client_custody import (
    ProviderClientCustodyManifest,
    ProviderClientCustodyPreflight,
    ProviderClientCustodyPreflightStatus,
    ProviderClientCustodyStatus,
    compute_provider_client_custody_digest,
    compute_provider_client_custody_preflight_digest,
    provider_client_custody_contains_no_clients,
    provider_client_custody_has_no_credentials,
    provider_client_custody_has_no_endpoints,
    provider_client_custody_has_no_network,
    provider_client_custody_has_no_runtime_authority,
    provider_client_preflight_remains_metadata_only,
)
from sentientos.context_hygiene.prompt_provider_credential_custody import (
    ProviderCredentialCustodyManifest,
    ProviderCredentialCustodyPreflight,
    ProviderCredentialCustodyPreflightStatus,
    ProviderCredentialCustodyStatus,
    compute_provider_credential_custody_digest,
    compute_provider_credential_custody_preflight_digest,
    provider_credential_custody_contains_no_secrets,
    provider_credential_custody_has_no_endpoint,
    provider_credential_custody_has_no_network,
    provider_credential_custody_has_no_provider_client,
    provider_credential_custody_has_no_runtime_authority,
    provider_credential_preflight_remains_metadata_only,
)
from sentientos.context_hygiene.prompt_provider_endpoint_custody import (
    ProviderEndpointCustodyManifest,
    ProviderEndpointCustodyPreflight,
    ProviderEndpointCustodyPreflightStatus,
    ProviderEndpointCustodyStatus,
    compute_provider_endpoint_custody_digest,
    compute_provider_endpoint_custody_preflight_digest,
    provider_endpoint_custody_contains_no_endpoints,
    provider_endpoint_custody_has_no_credentials,
    provider_endpoint_custody_has_no_network,
    provider_endpoint_custody_has_no_provider_client,
    provider_endpoint_custody_has_no_runtime_authority,
    provider_endpoint_preflight_remains_metadata_only,
)
from sentientos.context_hygiene.prompt_provider_null_transport import (
    ProviderNullTransportReceipt,
    compute_provider_null_transport_digest,
    provider_null_transport_digest_chain_complete as null_transport_chain_complete,
    provider_null_transport_has_no_endpoint,
    provider_null_transport_has_no_network,
    provider_null_transport_has_no_provider_client,
    provider_null_transport_has_no_provider_credentials,
    provider_null_transport_has_no_runtime_authority,
)
from sentientos.context_hygiene.prompt_provider_transport_capability import (
    ProviderTransportCapabilityManifest,
    ProviderTransportCapabilityStatus,
    ProviderTransportRegistrationPreflight,
    ProviderTransportRegistrationStatus,
    compute_provider_transport_capability_digest,
    compute_provider_transport_registration_preflight_digest,
    provider_transport_capability_has_no_credentials,
    provider_transport_capability_has_no_endpoint,
    provider_transport_capability_has_no_network,
    provider_transport_capability_has_no_provider_client,
    provider_transport_capability_has_no_runtime_authority,
    provider_transport_capability_is_null_only,
    provider_transport_registration_remains_forbidden,
)
from sentientos.context_hygiene.prompt_provider_transport_registry import (
    ProviderTransportRegistryManifest,
    compute_provider_transport_registry_digest,
    provider_transport_registry_is_null_only,
)


class ProviderInvocationReadinessStatus:
    INVOCATION_READINESS_FORBIDDEN = "invocation_readiness_forbidden"
    INVOCATION_READINESS_MISSING_EVIDENCE = "invocation_readiness_missing_evidence"
    INVOCATION_READINESS_INVALID = "invocation_readiness_invalid"
    INVOCATION_READINESS_CREDENTIALS_DETECTED = "invocation_readiness_credentials_detected"
    INVOCATION_READINESS_ENDPOINT_DETECTED = "invocation_readiness_endpoint_detected"
    INVOCATION_READINESS_CLIENT_DETECTED = "invocation_readiness_client_detected"
    INVOCATION_READINESS_NETWORK_DETECTED = "invocation_readiness_network_detected"
    INVOCATION_READINESS_RUNTIME_AUTHORITY_DETECTED = "invocation_readiness_runtime_authority_detected"
    INVOCATION_READINESS_NULL_ONLY_METADATA = "invocation_readiness_null_only_metadata"


class ProviderInvocationPreflightStatus:
    INVOCATION_PREFLIGHT_DENIED = "invocation_preflight_denied"
    INVOCATION_PREFLIGHT_FORBIDDEN = "invocation_preflight_forbidden"
    INVOCATION_PREFLIGHT_MISSING_EVIDENCE = "invocation_preflight_missing_evidence"
    INVOCATION_PREFLIGHT_INVALID_INPUT = "invocation_preflight_invalid_input"
    INVOCATION_PREFLIGHT_CREDENTIALS_DETECTED = "invocation_preflight_credentials_detected"
    INVOCATION_PREFLIGHT_ENDPOINT_DETECTED = "invocation_preflight_endpoint_detected"
    INVOCATION_PREFLIGHT_CLIENT_DETECTED = "invocation_preflight_client_detected"
    INVOCATION_PREFLIGHT_NETWORK_DETECTED = "invocation_preflight_network_detected"
    INVOCATION_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED = "invocation_preflight_runtime_authority_detected"
    INVOCATION_PREFLIGHT_METADATA_ONLY_NOT_INVOCABLE = "invocation_preflight_metadata_only_not_invocable"


@dataclass(frozen=True)
class ProviderInvocationReadinessFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderInvocationReadinessConstraint:
    code: str
    detail: str
    required: bool = True


@dataclass(frozen=True)
class ProviderInvocationReadinessGap:
    code: str
    detail: str
    required_for_real_invocation: bool = True


@dataclass(frozen=True)
class ProviderInvocationReadinessAuditChain:
    capability_manifest_id: str = ""
    capability_digest: str = ""
    registration_preflight_id: str = ""
    registration_preflight_digest: str = ""
    credential_custody_manifest_id: str = ""
    credential_custody_digest: str = ""
    credential_custody_preflight_id: str = ""
    credential_custody_preflight_digest: str = ""
    endpoint_custody_manifest_id: str = ""
    endpoint_custody_digest: str = ""
    endpoint_custody_preflight_id: str = ""
    endpoint_custody_preflight_digest: str = ""
    client_custody_manifest_id: str = ""
    client_custody_digest: str = ""
    client_custody_preflight_id: str = ""
    client_custody_preflight_digest: str = ""
    registry_id: str = ""
    registry_digest: str = ""
    null_transport_id: str = ""
    null_transport_digest: str = ""
    complete: bool = False
    mismatches: tuple[str, ...] = field(default_factory=tuple)
    missing: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProviderInvocationReadinessManifest:
    invocation_readiness_id: str
    readiness_status: str
    capability_manifest_id: str
    capability_digest: str
    registration_preflight_id: str
    registration_preflight_digest: str
    credential_custody_manifest_id: str
    credential_custody_digest: str
    credential_custody_preflight_id: str
    credential_custody_preflight_digest: str
    endpoint_custody_manifest_id: str
    endpoint_custody_digest: str
    endpoint_custody_preflight_id: str
    endpoint_custody_preflight_digest: str
    client_custody_manifest_id: str
    client_custody_digest: str
    client_custody_preflight_id: str
    client_custody_preflight_digest: str
    registry_id: str
    registry_digest: str
    null_transport_id: str
    null_transport_digest: str
    audit_chain: ProviderInvocationReadinessAuditChain
    digest_chain_complete: bool
    readiness_gaps: tuple[ProviderInvocationReadinessGap, ...]
    missing_required_evidence: tuple[str, ...]
    invocation_allowed: bool = False
    provider_send_allowed: bool = False
    credentials_allowed: bool = False
    endpoints_allowed: bool = False
    clients_allowed: bool = False
    network_allowed: bool = False
    socket_allowed: bool = False
    http_allowed: bool = False
    dns_allowed: bool = False
    provider_sdk_allowed: bool = False
    semantic_generation_allowed: bool = False
    tool_calls_allowed: bool = False
    memory_retrieval_allowed: bool = False
    memory_write_allowed: bool = False
    retention_allowed: bool = False
    action_execution_allowed: bool = False
    routing_allowed: bool = False
    findings: tuple[ProviderInvocationReadinessFinding, ...] = field(default_factory=tuple)
    constraints: tuple[ProviderInvocationReadinessConstraint, ...] = field(default_factory=tuple)
    rationale: str = ""
    readiness_digest: str = ""
    provider_invocation_readiness_manifest_only: bool = True
    provider_invocation_forbidden: bool = True
    metadata_only_not_invocable: bool = True
    real_transport_registration_forbidden: bool = True
    null_transport_only: bool = True
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


@dataclass(frozen=True)
class ProviderInvocationReadinessPreflight:
    invocation_preflight_id: str
    invocation_preflight_status: str
    invocation_readiness_id: str
    readiness_status: str
    readiness_digest: str
    audit_chain: ProviderInvocationReadinessAuditChain
    digest_chain_complete: bool
    requested_invocation: bool
    requested_registration: bool
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
    findings: tuple[ProviderInvocationReadinessFinding, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    constraints: tuple[ProviderInvocationReadinessConstraint, ...] = field(default_factory=tuple)
    readiness_gaps: tuple[ProviderInvocationReadinessGap, ...] = field(default_factory=tuple)
    rationale: str = ""
    invocation_preflight_digest: str = ""
    provider_invocation_readiness_preflight_only: bool = True
    provider_invocation_forbidden: bool = True
    metadata_only_not_invocable: bool = True
    credential_use_forbidden: bool = True
    endpoint_use_forbidden: bool = True
    provider_client_use_forbidden: bool = True
    network_access_forbidden: bool = True
    provider_send_forbidden: bool = True
    live_provider_transport_forbidden: bool = True
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


_REQUIRED_LINKS = (
    "capability_manifest",
    "registration_preflight",
    "credential_custody_manifest",
    "credential_custody_preflight",
    "endpoint_custody_manifest",
    "endpoint_custody_preflight",
    "client_custody_manifest",
    "client_custody_preflight",
)

_MARKER_FIELDS = (
    "provider_invocation_readiness_manifest_only",
    "provider_invocation_forbidden",
    "metadata_only_not_invocable",
    "real_transport_registration_forbidden",
    "null_transport_only",
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

_PREFLIGHT_MARKER_FIELDS = tuple(field for field in _MARKER_FIELDS if field not in {"provider_invocation_readiness_manifest_only", "real_transport_registration_forbidden", "live_prompt_assembly_forbidden", "null_transport_only"}) + (
    "provider_invocation_readiness_preflight_only",
)

_ALLOWANCE_FIELDS = (
    "invocation_allowed",
    "provider_send_allowed",
    "credentials_allowed",
    "endpoints_allowed",
    "clients_allowed",
    "network_allowed",
    "socket_allowed",
    "http_allowed",
    "dns_allowed",
    "provider_sdk_allowed",
    "semantic_generation_allowed",
    "tool_calls_allowed",
    "memory_retrieval_allowed",
    "memory_write_allowed",
    "retention_allowed",
    "action_execution_allowed",
    "routing_allowed",
)

_PREFLIGHT_ALLOWANCE_FIELDS = (
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

_NEGATIVE_TOKENS = (
    "forbidden",
    "does_not_",
    "no_",
    "not_invocable",
    "allowed_false",
    "metadata_only_not_invocable",
    "null_only",
)

_SCAN_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("invocation", ("provider invocation", "invoke", "completion", "chat.completions")),
    ("provider_send", ("provider send", "send_to_provider", "send provider")),
    ("provider_sdk", ("openai", "anthropic", "provider sdk")),
    ("endpoint", ("endpoint", "base_url", "host", "port", "url", "http://", "https://")),
    ("credentials", ("credential", "api_key", "bearer", "token", "secret", "auth")),
    ("clients", ("client", "session", "transport", "stream", "retry", "request builder")),
    ("network", ("network", "socket", "http", "dns", "resolve", "connect")),
    ("runtime", ("tool call", "action", "retention", "routing", "memory write", "raw_payload", "runtime_handle", "model_params", "provider_params", "semantic generation", "model output")),
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


def _finding(code: str, detail: str, severity: str = "blocker") -> ProviderInvocationReadinessFinding:
    return ProviderInvocationReadinessFinding(code=code, detail=detail, severity=severity)


def _constraints() -> tuple[ProviderInvocationReadinessConstraint, ...]:
    return (
        ProviderInvocationReadinessConstraint("readiness_manifest_only", "Phase 95 produces metadata readiness only; it cannot invoke a provider."),
        ProviderInvocationReadinessConstraint("provider_invocation_forbidden", "real provider invocation remains forbidden even for a complete clean chain."),
        ProviderInvocationReadinessConstraint("custody_chain_required", "Phase 91 through Phase 94 manifests and preflights are required evidence."),
        ProviderInvocationReadinessConstraint("no_runtime_authority", "no sockets, HTTP, DNS, clients, credentials, endpoints, semantic generation, memory, actions, retention, routing, or admission may occur."),
    )


def _default_gaps(missing: Sequence[str]) -> tuple[ProviderInvocationReadinessGap, ...]:
    base = [
        ProviderInvocationReadinessGap("external_security_review_not_present", "future real invocation requires an external security review outside Phase 95"),
        ProviderInvocationReadinessGap("explicit_invocation_denial_review_not_present", "future gates must review denial posture before any invocation design"),
        ProviderInvocationReadinessGap("real_provider_transport_not_authorized", "Phase 91 still forbids real transport registration"),
    ]
    base.extend(ProviderInvocationReadinessGap(f"missing_{item}", f"required linked evidence is missing: {item}") for item in missing)
    return tuple(base)


def _digest_payload(subject: ProviderInvocationReadinessManifest | Mapping[str, Any]) -> Mapping[str, Any]:
    data = dict(_mapping(subject))
    data.pop("invocation_readiness_id", None)
    data.pop("readiness_digest", None)
    return data


def _preflight_digest_payload(subject: ProviderInvocationReadinessPreflight | Mapping[str, Any]) -> Mapping[str, Any]:
    data = dict(_mapping(subject))
    data.pop("invocation_preflight_id", None)
    data.pop("invocation_preflight_digest", None)
    return data


def compute_provider_invocation_readiness_digest(manifest: ProviderInvocationReadinessManifest | Mapping[str, Any]) -> str:
    return _stable_digest(_digest_payload(manifest))


def compute_provider_invocation_readiness_preflight_digest(preflight: ProviderInvocationReadinessPreflight | Mapping[str, Any]) -> str:
    return _stable_digest(_preflight_digest_payload(preflight))


def _extract_identity(data: Mapping[str, Any], id_name: str, digest_name: str) -> tuple[str, str]:
    return str(data.get(id_name, "")), str(data.get(digest_name, ""))


def _scan_marker_categories(marker_evidence: Any) -> tuple[str, ...]:
    if marker_evidence is None:
        return ()
    text = json.dumps(_stable(marker_evidence), sort_keys=True, default=str).lower()
    categories: list[str] = []
    for category, patterns in _SCAN_PATTERNS:
        if any(pattern in text for pattern in patterns):
            categories.append(category)
    return tuple(sorted(set(categories)))


def _artifact_scan_categories(*artifacts: Any, marker_evidence: Any = None) -> tuple[str, ...]:
    categories = set(_scan_marker_categories(marker_evidence))
    for artifact in artifacts:
        data = _mapping(artifact)
        if not data:
            continue
        for key, value in data.items():
            lowered_key = str(key).lower()
            if isinstance(value, bool):
                if value is True and lowered_key.endswith(("capable", "present", "used", "access_allowed", "candidate")) and not any(token in lowered_key for token in _NEGATIVE_TOKENS):
                    categories.update(_scan_marker_categories({key: value}))
                continue
            continue
    return tuple(sorted(categories))


def _clean_registration_preflight(registration_preflight: Any) -> bool:
    data = _mapping(registration_preflight)
    return bool(
        data.get("registration_status") == ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_NULL_ONLY_ALLOWED
        and data.get("registration_allowed") is True
        and provider_transport_registration_remains_forbidden(registration_preflight)
        and compute_provider_transport_registration_preflight_digest(registration_preflight) == data.get("registration_preflight_digest")
    )


def _clean_credential_preflight(preflight: Any) -> bool:
    data = _mapping(preflight)
    return bool(
        data.get("custody_preflight_status") == ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_NO_SECRETS_ALLOWED
        and provider_credential_preflight_remains_metadata_only(preflight)
        and compute_provider_credential_custody_preflight_digest(preflight) == data.get("custody_preflight_digest")
    )


def _clean_endpoint_preflight(preflight: Any) -> bool:
    data = _mapping(preflight)
    return bool(
        data.get("endpoint_preflight_status") == ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_NO_ENDPOINTS_ALLOWED
        and provider_endpoint_preflight_remains_metadata_only(preflight)
        and compute_provider_endpoint_custody_preflight_digest(preflight) == data.get("endpoint_preflight_digest")
    )


def _clean_client_preflight(preflight: Any) -> bool:
    data = _mapping(preflight)
    return bool(
        data.get("client_preflight_status") == ProviderClientCustodyPreflightStatus.CLIENT_PREFLIGHT_NO_CLIENTS_ALLOWED
        and provider_client_preflight_remains_metadata_only(preflight)
        and compute_provider_client_custody_preflight_digest(preflight) == data.get("client_preflight_digest")
    )


def _audit_chain(
    *,
    capability_manifest: Any,
    registration_preflight: Any,
    credential_custody_manifest: Any,
    credential_custody_preflight: Any,
    endpoint_custody_manifest: Any,
    endpoint_custody_preflight: Any,
    client_custody_manifest: Any,
    client_custody_preflight: Any,
    registry_manifest: Any,
    null_transport_receipt: Any,
    missing: Sequence[str],
) -> ProviderInvocationReadinessAuditChain:
    mismatches: list[str] = []
    capability = _mapping(capability_manifest)
    registration = _mapping(registration_preflight)
    credential = _mapping(credential_custody_manifest)
    credential_preflight = _mapping(credential_custody_preflight)
    endpoint = _mapping(endpoint_custody_manifest)
    endpoint_preflight = _mapping(endpoint_custody_preflight)
    client = _mapping(client_custody_manifest)
    client_preflight = _mapping(client_custody_preflight)
    registry = _mapping(registry_manifest)
    null_transport = _mapping(null_transport_receipt)

    if capability and compute_provider_transport_capability_digest(capability_manifest) != capability.get("capability_digest"):
        mismatches.append("capability_digest")
    if registration and compute_provider_transport_registration_preflight_digest(registration_preflight) != registration.get("registration_preflight_digest"):
        mismatches.append("registration_preflight_digest")
    if credential and compute_provider_credential_custody_digest(credential_custody_manifest) != credential.get("custody_digest"):
        mismatches.append("credential_custody_digest")
    if credential_preflight and compute_provider_credential_custody_preflight_digest(credential_custody_preflight) != credential_preflight.get("custody_preflight_digest"):
        mismatches.append("credential_custody_preflight_digest")
    if endpoint and compute_provider_endpoint_custody_digest(endpoint_custody_manifest) != endpoint.get("endpoint_digest"):
        mismatches.append("endpoint_custody_digest")
    if endpoint_preflight and compute_provider_endpoint_custody_preflight_digest(endpoint_custody_preflight) != endpoint_preflight.get("endpoint_preflight_digest"):
        mismatches.append("endpoint_custody_preflight_digest")
    if client and compute_provider_client_custody_digest(client_custody_manifest) != client.get("client_digest"):
        mismatches.append("client_custody_digest")
    if client_preflight and compute_provider_client_custody_preflight_digest(client_custody_preflight) != client_preflight.get("client_preflight_digest"):
        mismatches.append("client_custody_preflight_digest")
    if registry and compute_provider_transport_registry_digest(registry_manifest) != registry.get("registry_digest"):
        mismatches.append("registry_digest")
    if null_transport and compute_provider_null_transport_digest(null_transport_receipt) != null_transport.get("null_transport_digest"):
        mismatches.append("null_transport_digest")

    capability_id, capability_digest = _extract_identity(capability, "capability_manifest_id", "capability_digest")
    registration_id, registration_digest = _extract_identity(registration, "registration_preflight_id", "registration_preflight_digest")
    credential_id, credential_digest = _extract_identity(credential, "custody_manifest_id", "custody_digest")
    credential_preflight_id, credential_preflight_digest = _extract_identity(credential_preflight, "custody_preflight_id", "custody_preflight_digest")
    endpoint_id, endpoint_digest = _extract_identity(endpoint, "endpoint_manifest_id", "endpoint_digest")
    endpoint_preflight_id, endpoint_preflight_digest = _extract_identity(endpoint_preflight, "endpoint_preflight_id", "endpoint_preflight_digest")
    client_id, client_digest = _extract_identity(client, "client_manifest_id", "client_digest")
    client_preflight_id, client_preflight_digest = _extract_identity(client_preflight, "client_preflight_id", "client_preflight_digest")
    registry_id, registry_digest = _extract_identity(registry, "registry_id", "registry_digest")
    null_id, null_digest = _extract_identity(null_transport, "null_transport_id", "null_transport_digest")
    complete = bool(not missing and not mismatches and capability_digest and registration_digest and credential_digest and credential_preflight_digest and endpoint_digest and endpoint_preflight_digest and client_digest and client_preflight_digest)
    return ProviderInvocationReadinessAuditChain(
        capability_manifest_id=capability_id,
        capability_digest=capability_digest,
        registration_preflight_id=registration_id,
        registration_preflight_digest=registration_digest,
        credential_custody_manifest_id=credential_id,
        credential_custody_digest=credential_digest,
        credential_custody_preflight_id=credential_preflight_id,
        credential_custody_preflight_digest=credential_preflight_digest,
        endpoint_custody_manifest_id=endpoint_id,
        endpoint_custody_digest=endpoint_digest,
        endpoint_custody_preflight_id=endpoint_preflight_id,
        endpoint_custody_preflight_digest=endpoint_preflight_digest,
        client_custody_manifest_id=client_id,
        client_custody_digest=client_digest,
        client_custody_preflight_id=client_preflight_id,
        client_custody_preflight_digest=client_preflight_digest,
        registry_id=registry_id,
        registry_digest=registry_digest,
        null_transport_id=null_id,
        null_transport_digest=null_digest,
        complete=complete,
        mismatches=tuple(mismatches),
        missing=tuple(str(item) for item in missing),
    )


def build_provider_invocation_readiness_manifest(
    *,
    capability_manifest: ProviderTransportCapabilityManifest | Mapping[str, Any] | None = None,
    registration_preflight: ProviderTransportRegistrationPreflight | Mapping[str, Any] | None = None,
    credential_custody_manifest: ProviderCredentialCustodyManifest | Mapping[str, Any] | None = None,
    credential_custody_preflight: ProviderCredentialCustodyPreflight | Mapping[str, Any] | None = None,
    endpoint_custody_manifest: ProviderEndpointCustodyManifest | Mapping[str, Any] | None = None,
    endpoint_custody_preflight: ProviderEndpointCustodyPreflight | Mapping[str, Any] | None = None,
    client_custody_manifest: ProviderClientCustodyManifest | Mapping[str, Any] | None = None,
    client_custody_preflight: ProviderClientCustodyPreflight | Mapping[str, Any] | None = None,
    registry_manifest: ProviderTransportRegistryManifest | Mapping[str, Any] | None = None,
    null_transport_receipt: ProviderNullTransportReceipt | Mapping[str, Any] | None = None,
    marker_evidence: Any = None,
    marker_overrides: Mapping[str, bool] | None = None,
) -> ProviderInvocationReadinessManifest:
    linked = {
        "capability_manifest": capability_manifest,
        "registration_preflight": registration_preflight,
        "credential_custody_manifest": credential_custody_manifest,
        "credential_custody_preflight": credential_custody_preflight,
        "endpoint_custody_manifest": endpoint_custody_manifest,
        "endpoint_custody_preflight": endpoint_custody_preflight,
        "client_custody_manifest": client_custody_manifest,
        "client_custody_preflight": client_custody_preflight,
    }
    missing = tuple(name for name in _REQUIRED_LINKS if not _mapping(linked[name]))
    findings: list[ProviderInvocationReadinessFinding] = []
    for name in missing:
        findings.append(_finding(f"{name}_missing", f"required Phase 91/92/93/94 evidence is missing: {name}"))

    categories = set(_artifact_scan_categories(*linked.values(), registry_manifest, null_transport_receipt, marker_evidence=marker_evidence))
    if marker_evidence is not None:
        for category in sorted(categories):
            findings.append(_finding(f"{category}_marker_detected", f"metadata marker evidence references forbidden {category} material"))

    capability_clean = bool(capability_manifest and provider_transport_capability_is_null_only(capability_manifest))
    registration_clean = bool(registration_preflight and _clean_registration_preflight(registration_preflight))
    credential_clean = bool(credential_custody_manifest and provider_credential_custody_contains_no_secrets(credential_custody_manifest))
    credential_preflight_clean = bool(credential_custody_preflight and _clean_credential_preflight(credential_custody_preflight))
    endpoint_clean = bool(endpoint_custody_manifest and provider_endpoint_custody_contains_no_endpoints(endpoint_custody_manifest))
    endpoint_preflight_clean = bool(endpoint_custody_preflight and _clean_endpoint_preflight(endpoint_custody_preflight))
    client_clean = bool(client_custody_manifest and provider_client_custody_contains_no_clients(client_custody_manifest))
    client_preflight_clean = bool(client_custody_preflight and _clean_client_preflight(client_custody_preflight))
    registry_clean = bool(not registry_manifest or provider_transport_registry_is_null_only(registry_manifest))
    null_clean = bool(not null_transport_receipt or (null_transport_chain_complete(null_transport_receipt) and provider_null_transport_has_no_network(null_transport_receipt)))

    if capability_manifest and not capability_clean:
        findings.append(_finding("capability_not_null_only", "Phase 91 capability evidence is not clean null-only metadata"))
    if registration_preflight and not registration_clean:
        findings.append(_finding("registration_not_null_only", "Phase 91 registration preflight is not clean null-only metadata"))
    if credential_custody_manifest and not credential_clean:
        findings.append(_finding("credential_custody_not_no_secret", "Phase 92 credential custody evidence is not no-secret metadata"))
    if credential_custody_preflight and not credential_preflight_clean:
        findings.append(_finding("credential_preflight_not_metadata_only", "Phase 92 credential custody preflight is not metadata-only"))
    if endpoint_custody_manifest and not endpoint_clean:
        findings.append(_finding("endpoint_custody_not_no_endpoint", "Phase 93 endpoint custody evidence is not no-endpoint metadata"))
    if endpoint_custody_preflight and not endpoint_preflight_clean:
        findings.append(_finding("endpoint_preflight_not_metadata_only", "Phase 93 endpoint custody preflight is not metadata-only"))
    if client_custody_manifest and not client_clean:
        findings.append(_finding("client_custody_not_no_client", "Phase 94 client custody evidence is not no-client metadata"))
    if client_custody_preflight and not client_preflight_clean:
        findings.append(_finding("client_preflight_not_metadata_only", "Phase 94 client custody preflight is not metadata-only"))
    if registry_manifest and not registry_clean:
        findings.append(_finding("registry_not_null_only", "Phase 90 registry must remain null-only when linked"))
    if null_transport_receipt and not null_clean:
        findings.append(_finding("null_transport_not_clean", "Phase 89 null transport receipt must prove no network/provider transfer when linked"))

    marker_values = {field_name: True for field_name in _MARKER_FIELDS}
    if marker_overrides:
        marker_values.update({str(key): bool(value) for key, value in marker_overrides.items() if str(key) in marker_values})
    for name, value in marker_values.items():
        if not value:
            findings.append(_finding("readiness_marker_missing", f"{name} must remain true"))
            categories.add("runtime")

    audit_chain = _audit_chain(
        capability_manifest=capability_manifest,
        registration_preflight=registration_preflight,
        credential_custody_manifest=credential_custody_manifest,
        credential_custody_preflight=credential_custody_preflight,
        endpoint_custody_manifest=endpoint_custody_manifest,
        endpoint_custody_preflight=endpoint_custody_preflight,
        client_custody_manifest=client_custody_manifest,
        client_custody_preflight=client_custody_preflight,
        registry_manifest=registry_manifest,
        null_transport_receipt=null_transport_receipt,
        missing=missing,
    )
    if audit_chain.mismatches:
        findings.append(_finding("digest_chain_mismatch", "one or more linked digests do not match stable metadata"))

    if not missing and "credentials" not in categories:
        no_credentials = all(
            (
                provider_transport_capability_has_no_credentials(capability_manifest or {}),
                provider_credential_custody_contains_no_secrets(credential_custody_manifest or {}),
                provider_endpoint_custody_has_no_credentials(endpoint_custody_manifest or {}),
                provider_client_custody_has_no_credentials(client_custody_manifest or {}),
                True if null_transport_receipt is None else provider_null_transport_has_no_provider_credentials(null_transport_receipt),
            )
        )
        if not no_credentials:
            categories.add("credentials")
    if not missing and "endpoint" not in categories:
        no_endpoint = all(
            (
                provider_transport_capability_has_no_endpoint(capability_manifest or {}),
                provider_credential_custody_has_no_endpoint(credential_custody_manifest or {}),
                provider_endpoint_custody_contains_no_endpoints(endpoint_custody_manifest or {}),
                provider_client_custody_has_no_endpoints(client_custody_manifest or {}),
                True if null_transport_receipt is None else provider_null_transport_has_no_endpoint(null_transport_receipt),
            )
        )
        if not no_endpoint:
            categories.add("endpoint")
    if not missing and "clients" not in categories:
        no_client = all(
            (
                provider_transport_capability_has_no_provider_client(capability_manifest or {}),
                provider_credential_custody_has_no_provider_client(credential_custody_manifest or {}),
                provider_endpoint_custody_has_no_provider_client(endpoint_custody_manifest or {}),
                provider_client_custody_contains_no_clients(client_custody_manifest or {}),
                True if null_transport_receipt is None else provider_null_transport_has_no_provider_client(null_transport_receipt),
            )
        )
        if not no_client:
            categories.add("clients")
    if not missing and "network" not in categories:
        no_network = all(
            (
                provider_transport_capability_has_no_network(capability_manifest or {}),
                provider_credential_custody_has_no_network(credential_custody_manifest or {}),
                provider_endpoint_custody_has_no_network(endpoint_custody_manifest or {}),
                provider_client_custody_has_no_network(client_custody_manifest or {}),
                True if null_transport_receipt is None else provider_null_transport_has_no_network(null_transport_receipt),
            )
        )
        if not no_network:
            categories.add("network")
    if not missing and "runtime" not in categories:
        no_runtime = all(
            (
                provider_transport_capability_has_no_runtime_authority(capability_manifest or {}),
                provider_credential_custody_has_no_runtime_authority(credential_custody_manifest or {}),
                provider_endpoint_custody_has_no_runtime_authority(endpoint_custody_manifest or {}),
                provider_client_custody_has_no_runtime_authority(client_custody_manifest or {}),
                True if null_transport_receipt is None else provider_null_transport_has_no_runtime_authority(null_transport_receipt),
            )
        )
        if not no_runtime:
            categories.add("runtime")

    if "credentials" in categories:
        status = ProviderInvocationReadinessStatus.INVOCATION_READINESS_CREDENTIALS_DETECTED
    elif "endpoint" in categories:
        status = ProviderInvocationReadinessStatus.INVOCATION_READINESS_ENDPOINT_DETECTED
    elif "clients" in categories or "provider_sdk" in categories:
        status = ProviderInvocationReadinessStatus.INVOCATION_READINESS_CLIENT_DETECTED
    elif "network" in categories or "provider_send" in categories:
        status = ProviderInvocationReadinessStatus.INVOCATION_READINESS_NETWORK_DETECTED
    elif "runtime" in categories or "invocation" in categories:
        status = ProviderInvocationReadinessStatus.INVOCATION_READINESS_RUNTIME_AUTHORITY_DETECTED
    elif missing:
        status = ProviderInvocationReadinessStatus.INVOCATION_READINESS_MISSING_EVIDENCE
    elif audit_chain.mismatches:
        status = ProviderInvocationReadinessStatus.INVOCATION_READINESS_INVALID
    elif all((capability_clean, registration_clean, credential_clean, credential_preflight_clean, endpoint_clean, endpoint_preflight_clean, client_clean, client_preflight_clean, registry_clean, null_clean, audit_chain.complete)):
        status = ProviderInvocationReadinessStatus.INVOCATION_READINESS_NULL_ONLY_METADATA
    else:
        status = ProviderInvocationReadinessStatus.INVOCATION_READINESS_FORBIDDEN

    gaps = _default_gaps(missing)
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "complete custody chain is metadata-only; real provider invocation remains forbidden"
    manifest = ProviderInvocationReadinessManifest(
        invocation_readiness_id="",
        readiness_status=status,
        capability_manifest_id=audit_chain.capability_manifest_id,
        capability_digest=audit_chain.capability_digest,
        registration_preflight_id=audit_chain.registration_preflight_id,
        registration_preflight_digest=audit_chain.registration_preflight_digest,
        credential_custody_manifest_id=audit_chain.credential_custody_manifest_id,
        credential_custody_digest=audit_chain.credential_custody_digest,
        credential_custody_preflight_id=audit_chain.credential_custody_preflight_id,
        credential_custody_preflight_digest=audit_chain.credential_custody_preflight_digest,
        endpoint_custody_manifest_id=audit_chain.endpoint_custody_manifest_id,
        endpoint_custody_digest=audit_chain.endpoint_custody_digest,
        endpoint_custody_preflight_id=audit_chain.endpoint_custody_preflight_id,
        endpoint_custody_preflight_digest=audit_chain.endpoint_custody_preflight_digest,
        client_custody_manifest_id=audit_chain.client_custody_manifest_id,
        client_custody_digest=audit_chain.client_custody_digest,
        client_custody_preflight_id=audit_chain.client_custody_preflight_id,
        client_custody_preflight_digest=audit_chain.client_custody_preflight_digest,
        registry_id=audit_chain.registry_id,
        registry_digest=audit_chain.registry_digest,
        null_transport_id=audit_chain.null_transport_id,
        null_transport_digest=audit_chain.null_transport_digest,
        audit_chain=audit_chain,
        digest_chain_complete=audit_chain.complete,
        readiness_gaps=gaps,
        missing_required_evidence=tuple(missing),
        findings=tuple(findings),
        constraints=_constraints(),
        rationale=rationale[:1000],
        readiness_digest="",
        **marker_values,
    )
    digest = compute_provider_invocation_readiness_digest(manifest)
    return replace(manifest, invocation_readiness_id=f"provider-invocation-readiness:{digest[:16]}", readiness_digest=digest)


def validate_provider_invocation_readiness_manifest(manifest: ProviderInvocationReadinessManifest | Mapping[str, Any]) -> tuple[ProviderInvocationReadinessFinding, ...]:
    data = _mapping(manifest)
    findings: list[ProviderInvocationReadinessFinding] = []
    if not data:
        return (_finding("readiness_manifest_missing", "ProviderInvocationReadinessManifest is required"),)
    allowed_statuses = {
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_FORBIDDEN,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_MISSING_EVIDENCE,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_INVALID,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_CREDENTIALS_DETECTED,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_ENDPOINT_DETECTED,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_CLIENT_DETECTED,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_NETWORK_DETECTED,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_RUNTIME_AUTHORITY_DETECTED,
        ProviderInvocationReadinessStatus.INVOCATION_READINESS_NULL_ONLY_METADATA,
    }
    if data.get("readiness_status") not in allowed_statuses:
        findings.append(_finding("readiness_status_unknown", "unknown invocation readiness status"))
    for field_name in _ALLOWANCE_FIELDS:
        if data.get(field_name) is not False:
            findings.append(_finding("readiness_allowance_detected", f"{field_name} must remain false"))
    for field_name in _MARKER_FIELDS:
        if data.get(field_name) is not True:
            findings.append(_finding("readiness_marker_missing", f"{field_name} must remain true"))
    if compute_provider_invocation_readiness_digest(data) != data.get("readiness_digest"):
        findings.append(_finding("readiness_digest_mismatch", "readiness digest does not match stable metadata"))
    return tuple(findings)


def evaluate_provider_invocation_readiness_preflight(
    manifest: ProviderInvocationReadinessManifest | Mapping[str, Any],
    *,
    requested_invocation: bool = False,
    requested_provider_send: bool = False,
    requested_network: bool = False,
    requested_credentials: bool = False,
    requested_endpoints: bool = False,
    requested_clients: bool = False,
    requested_provider_sdk: bool = False,
    requested_dns: bool = False,
    requested_http: bool = False,
    requested_socket: bool = False,
    requested_semantic_generation: bool = False,
    requested_registration: bool = False,
    internal_only: bool = True,
    no_invocation: bool = True,
    no_provider_send: bool = True,
    no_credentials: bool = True,
    no_endpoints: bool = True,
    no_clients: bool = True,
    no_network: bool = True,
    no_dns: bool = True,
    no_http: bool = True,
    no_socket: bool = True,
    no_provider_sdk: bool = True,
    no_tools: bool = True,
    no_memory: bool = True,
    no_retention: bool = True,
    no_actions: bool = True,
    no_routing: bool = True,
    no_semantic_generation: bool = True,
    marker_evidence: Any = None,
    marker_overrides: Mapping[str, bool] | None = None,
) -> ProviderInvocationReadinessPreflight:
    data = _mapping(manifest)
    findings: list[ProviderInvocationReadinessFinding] = list(validate_provider_invocation_readiness_manifest(manifest))
    warnings: list[str] = []
    if not data:
        findings.append(_finding("readiness_manifest_missing", "readiness manifest is required"))
    if not internal_only:
        findings.append(_finding("not_internal_only", "Phase 95 preflight must remain internal metadata only"))

    requested_flags = {
        "requested_invocation": requested_invocation,
        "requested_provider_send": requested_provider_send,
        "requested_network": requested_network,
        "requested_credentials": requested_credentials,
        "requested_endpoints": requested_endpoints,
        "requested_clients": requested_clients,
        "requested_provider_sdk": requested_provider_sdk,
        "requested_dns": requested_dns,
        "requested_http": requested_http,
        "requested_socket": requested_socket,
        "requested_semantic_generation": requested_semantic_generation,
        "requested_registration": requested_registration,
    }
    for name, value in requested_flags.items():
        if value:
            findings.append(_finding(name, f"{name} is forbidden in Phase 95 invocation readiness preflight"))
    no_flags = {
        "no_invocation": no_invocation,
        "no_provider_send": no_provider_send,
        "no_credentials": no_credentials,
        "no_endpoints": no_endpoints,
        "no_clients": no_clients,
        "no_network": no_network,
        "no_dns": no_dns,
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
    for name, value in no_flags.items():
        if not value:
            findings.append(_finding(name, f"{name} must remain true in Phase 95 invocation readiness preflight"))
    categories = set(_artifact_scan_categories(data, marker_evidence=marker_evidence))
    for category in sorted(categories):
        findings.append(_finding(f"{category}_marker_detected", f"metadata marker evidence references forbidden {category} material"))

    marker_values = {field_name: True for field_name in _PREFLIGHT_MARKER_FIELDS}
    if marker_overrides:
        marker_values.update({str(key): bool(value) for key, value in marker_overrides.items() if str(key) in marker_values})
    for name, value in marker_values.items():
        if not value:
            findings.append(_finding("preflight_marker_missing", f"{name} must remain true"))
            categories.add("runtime")

    readiness_status = str(data.get("readiness_status", ""))
    digest_complete = bool(data.get("digest_chain_complete") is True)
    if readiness_status == ProviderInvocationReadinessStatus.INVOCATION_READINESS_CREDENTIALS_DETECTED or requested_credentials:
        status = ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_CREDENTIALS_DETECTED
    elif readiness_status == ProviderInvocationReadinessStatus.INVOCATION_READINESS_ENDPOINT_DETECTED or requested_endpoints or requested_dns:
        status = ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_ENDPOINT_DETECTED
    elif readiness_status == ProviderInvocationReadinessStatus.INVOCATION_READINESS_CLIENT_DETECTED or requested_clients or requested_provider_sdk:
        status = ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_CLIENT_DETECTED
    elif readiness_status == ProviderInvocationReadinessStatus.INVOCATION_READINESS_NETWORK_DETECTED or requested_network or requested_provider_send or requested_http or requested_socket:
        status = ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_NETWORK_DETECTED
    elif readiness_status == ProviderInvocationReadinessStatus.INVOCATION_READINESS_RUNTIME_AUTHORITY_DETECTED or requested_invocation or requested_registration or requested_semantic_generation or any(not no_flags[name] for name in ("no_tools", "no_memory", "no_retention", "no_actions", "no_routing", "no_semantic_generation")) or categories:
        status = ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED
    elif readiness_status == ProviderInvocationReadinessStatus.INVOCATION_READINESS_MISSING_EVIDENCE or not digest_complete:
        status = ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_MISSING_EVIDENCE
    elif readiness_status == ProviderInvocationReadinessStatus.INVOCATION_READINESS_INVALID:
        status = ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_INVALID_INPUT
    elif requested_invocation or requested_provider_send or requested_network or not all(no_flags.values()):
        status = ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_FORBIDDEN
    elif readiness_status == ProviderInvocationReadinessStatus.INVOCATION_READINESS_NULL_ONLY_METADATA and not findings and digest_complete and all(not value for value in requested_flags.values()) and all(no_flags.values()):
        status = ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_METADATA_ONLY_NOT_INVOCABLE
        warnings.append("metadata_only_not_invocable")
    else:
        status = ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_DENIED

    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "preflight is metadata-only and not invocable; real provider invocation remains forbidden"
    preflight = ProviderInvocationReadinessPreflight(
        invocation_preflight_id="",
        invocation_preflight_status=status,
        invocation_readiness_id=str(data.get("invocation_readiness_id", "")),
        readiness_status=readiness_status,
        readiness_digest=str(data.get("readiness_digest", "")),
        audit_chain=ProviderInvocationReadinessAuditChain(**_mapping(data.get("audit_chain", {}))),
        digest_chain_complete=digest_complete,
        requested_invocation=bool(requested_invocation),
        requested_registration=bool(requested_registration),
        findings=tuple(findings),
        warnings=tuple(warnings),
        constraints=_constraints(),
        readiness_gaps=tuple(ProviderInvocationReadinessGap(**item) if isinstance(item, Mapping) else item for item in data.get("readiness_gaps", ())),
        rationale=rationale[:1000],
        invocation_preflight_digest="",
        **marker_values,
    )
    digest = compute_provider_invocation_readiness_preflight_digest(preflight)
    return replace(preflight, invocation_preflight_id=f"provider-invocation-preflight:{digest[:16]}", invocation_preflight_digest=digest)


def provider_invocation_readiness_forbids_invocation(subject: ProviderInvocationReadinessManifest | ProviderInvocationReadinessPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(data.get("provider_invocation_forbidden") is True and data.get("metadata_only_not_invocable") is True and data.get("invocation_allowed") is False and data.get("does_not_call_llm") is True and data.get("does_not_send_to_provider") is True)


def provider_invocation_readiness_has_no_credentials(subject: ProviderInvocationReadinessManifest | ProviderInvocationReadinessPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    allowed = data.get("credentials_allowed", data.get("credential_use_allowed", False))
    return bool(allowed is False and data.get("credential_use_forbidden") is True)


def provider_invocation_readiness_has_no_endpoints(subject: ProviderInvocationReadinessManifest | ProviderInvocationReadinessPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    allowed = data.get("endpoints_allowed", data.get("endpoint_use_allowed", False))
    return bool(allowed is False and data.get("endpoint_use_forbidden") is True and data.get("does_not_resolve_dns") is True)


def provider_invocation_readiness_has_no_clients(subject: ProviderInvocationReadinessManifest | ProviderInvocationReadinessPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    allowed = data.get("clients_allowed", data.get("client_use_allowed", False))
    return bool(allowed is False and data.get("provider_client_use_forbidden") is True and data.get("does_not_create_clients") is True and data.get("does_not_create_sessions") is True)


def provider_invocation_readiness_has_no_network(subject: ProviderInvocationReadinessManifest | ProviderInvocationReadinessPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    allowed = data.get("network_allowed", data.get("network_access_allowed", False))
    return bool(allowed is False and data.get("network_access_forbidden") is True and data.get("does_not_make_network_calls") is True and data.get("does_not_open_sockets") is True and data.get("does_not_make_http_requests") is True)


def provider_invocation_readiness_has_no_runtime_authority(subject: ProviderInvocationReadinessManifest | ProviderInvocationReadinessPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(
        data.get("semantic_generation_allowed") is False
        and data.get("tool_calls_allowed") is False
        and data.get("memory_retrieval_allowed") is False
        and data.get("memory_write_allowed") is False
        and data.get("retention_allowed") is False
        and data.get("action_execution_allowed") is False
        and data.get("routing_allowed") is False
        and data.get("does_not_execute_or_route_work") is True
        and data.get("does_not_admit_work") is True
    )


def provider_invocation_preflight_denies_real_invocation(preflight: ProviderInvocationReadinessPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(provider_invocation_readiness_forbids_invocation(data) and data.get("invocation_preflight_status") != ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_METADATA_ONLY_NOT_INVOCABLE)


def provider_invocation_preflight_remains_metadata_only(preflight: ProviderInvocationReadinessPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(
        data.get("invocation_preflight_status") == ProviderInvocationPreflightStatus.INVOCATION_PREFLIGHT_METADATA_ONLY_NOT_INVOCABLE
        and provider_invocation_readiness_forbids_invocation(data)
        and provider_invocation_readiness_has_no_credentials(data)
        and provider_invocation_readiness_has_no_endpoints(data)
        and provider_invocation_readiness_has_no_clients(data)
        and provider_invocation_readiness_has_no_network(data)
        and provider_invocation_readiness_has_no_runtime_authority(data)
    )


def provider_invocation_readiness_digest_chain_complete(manifest: ProviderInvocationReadinessManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    audit = _mapping(data.get("audit_chain", {}))
    return bool(data.get("digest_chain_complete") is True and audit.get("complete") is True and not tuple(audit.get("missing", ())) and not tuple(audit.get("mismatches", ())))


def explain_provider_invocation_readiness_findings(subject: ProviderInvocationReadinessManifest | ProviderInvocationReadinessPreflight | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(subject)
    return tuple(f"{item.get('severity', 'blocker')}:{item.get('code', '')}:{item.get('detail', '')}" for item in data.get("findings", ()) if isinstance(item, Mapping))


def summarize_provider_invocation_readiness_preflight(preflight: ProviderInvocationReadinessPreflight | Mapping[str, Any]) -> dict[str, Any]:
    data = _mapping(preflight)
    return {
        "invocation_preflight_status": data.get("invocation_preflight_status", ""),
        "invocation_allowed": data.get("invocation_allowed", False),
        "provider_send_allowed": data.get("provider_send_allowed", False),
        "readiness_status": data.get("readiness_status", ""),
        "digest_chain_complete": data.get("digest_chain_complete", False),
        "finding_codes": tuple(item.get("code", "") for item in data.get("findings", ()) if isinstance(item, Mapping)),
        "warning_codes": tuple(data.get("warnings", ())),
        "invocation_preflight_digest": data.get("invocation_preflight_digest", ""),
    }
