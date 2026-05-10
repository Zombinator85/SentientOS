from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_provider_credential_custody import (
    ProviderCredentialCustodyManifest,
    ProviderCredentialCustodyPreflight,
    ProviderCredentialCustodyPreflightStatus,
    ProviderCredentialCustodyStatus,
    compute_provider_credential_custody_digest,
    compute_provider_credential_custody_preflight_digest,
    provider_credential_custody_contains_no_secrets,
    provider_credential_preflight_remains_metadata_only,
)
from sentientos.context_hygiene.prompt_provider_transport_capability import (
    ProviderTransportCapabilityManifest,
    ProviderTransportCapabilityStatus,
    compute_provider_transport_capability_digest,
    provider_transport_capability_is_null_only,
)


class ProviderEndpointCustodyStatus:
    ENDPOINT_CUSTODY_NO_ENDPOINTS = "endpoint_custody_no_endpoints"
    ENDPOINT_CUSTODY_FORBIDDEN_ENDPOINT_DETECTED = "endpoint_custody_forbidden_endpoint_detected"
    ENDPOINT_CUSTODY_ENDPOINT_REFERENCE_DETECTED = "endpoint_custody_endpoint_reference_detected"
    ENDPOINT_CUSTODY_DNS_RESOLUTION_DETECTED = "endpoint_custody_dns_resolution_detected"
    ENDPOINT_CUSTODY_ENV_ACCESS_DETECTED = "endpoint_custody_env_access_detected"
    ENDPOINT_CUSTODY_FILE_ACCESS_DETECTED = "endpoint_custody_file_access_detected"
    ENDPOINT_CUSTODY_CONFIG_STORE_ACCESS_DETECTED = "endpoint_custody_config_store_access_detected"
    ENDPOINT_CUSTODY_CREDENTIALS_DETECTED = "endpoint_custody_credentials_detected"
    ENDPOINT_CUSTODY_CLIENT_DETECTED = "endpoint_custody_client_detected"
    ENDPOINT_CUSTODY_NETWORK_DETECTED = "endpoint_custody_network_detected"
    ENDPOINT_CUSTODY_INCOMPLETE = "endpoint_custody_incomplete"
    ENDPOINT_CUSTODY_INVALID = "endpoint_custody_invalid"
    ENDPOINT_CUSTODY_RUNTIME_AUTHORITY_DETECTED = "endpoint_custody_runtime_authority_detected"


class ProviderEndpointCustodyPreflightStatus:
    ENDPOINT_PREFLIGHT_DENIED = "endpoint_preflight_denied"
    ENDPOINT_PREFLIGHT_NO_ENDPOINTS_ALLOWED = "endpoint_preflight_no_endpoints_allowed"
    ENDPOINT_PREFLIGHT_FORBIDDEN_ENDPOINT_DETECTED = "endpoint_preflight_forbidden_endpoint_detected"
    ENDPOINT_PREFLIGHT_ENDPOINT_RESOLUTION_FORBIDDEN = "endpoint_preflight_endpoint_resolution_forbidden"
    ENDPOINT_PREFLIGHT_DNS_RESOLUTION_DETECTED = "endpoint_preflight_dns_resolution_detected"
    ENDPOINT_PREFLIGHT_ENV_ACCESS_DETECTED = "endpoint_preflight_env_access_detected"
    ENDPOINT_PREFLIGHT_FILE_ACCESS_DETECTED = "endpoint_preflight_file_access_detected"
    ENDPOINT_PREFLIGHT_CONFIG_STORE_ACCESS_DETECTED = "endpoint_preflight_config_store_access_detected"
    ENDPOINT_PREFLIGHT_CREDENTIALS_DETECTED = "endpoint_preflight_credentials_detected"
    ENDPOINT_PREFLIGHT_CLIENT_DETECTED = "endpoint_preflight_client_detected"
    ENDPOINT_PREFLIGHT_NETWORK_DETECTED = "endpoint_preflight_network_detected"
    ENDPOINT_PREFLIGHT_INCOMPLETE_EVIDENCE = "endpoint_preflight_incomplete_evidence"
    ENDPOINT_PREFLIGHT_INVALID_INPUT = "endpoint_preflight_invalid_input"
    ENDPOINT_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED = "endpoint_preflight_runtime_authority_detected"


class ProviderEndpointCustodyKind:
    ENDPOINT_CUSTODY_NONE = "endpoint_custody_none"
    ENDPOINT_CUSTODY_NO_ENDPOINT_PLACEHOLDER = "endpoint_custody_no_endpoint_placeholder"
    ENDPOINT_CUSTODY_FUTURE_ENDPOINT_CONTRACT_PLACEHOLDER = "endpoint_custody_future_endpoint_contract_placeholder"
    ENDPOINT_CUSTODY_INLINE_URL_FORBIDDEN = "endpoint_custody_inline_url_forbidden"
    ENDPOINT_CUSTODY_ENV_ENDPOINT_FORBIDDEN = "endpoint_custody_env_endpoint_forbidden"
    ENDPOINT_CUSTODY_FILE_ENDPOINT_FORBIDDEN = "endpoint_custody_file_endpoint_forbidden"
    ENDPOINT_CUSTODY_CONFIG_STORE_ENDPOINT_FORBIDDEN = "endpoint_custody_config_store_endpoint_forbidden"
    ENDPOINT_CUSTODY_DNS_NAME_FORBIDDEN = "endpoint_custody_dns_name_forbidden"
    ENDPOINT_CUSTODY_IP_ADDRESS_FORBIDDEN = "endpoint_custody_ip_address_forbidden"
    ENDPOINT_CUSTODY_PROVIDER_CLIENT_ENDPOINT_FORBIDDEN = "endpoint_custody_provider_client_endpoint_forbidden"
    ENDPOINT_CUSTODY_UNKNOWN_FORBIDDEN = "endpoint_custody_unknown_forbidden"


@dataclass(frozen=True)
class ProviderEndpointCustodyFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderEndpointCustodyConstraint:
    code: str
    detail: str
    required: bool = True


@dataclass(frozen=True)
class ProviderEndpointCustodyGap:
    code: str
    detail: str
    required_for_real_custody: bool = True


@dataclass(frozen=True)
class ProviderEndpointCustodyAuditChain:
    endpoint_manifest_id: str = ""
    endpoint_digest: str = ""
    capability_manifest_id: str = ""
    capability_digest: str = ""
    credential_custody_manifest_id: str = ""
    credential_custody_digest: str = ""
    credential_custody_preflight_id: str = ""
    credential_custody_preflight_digest: str = ""
    complete: bool = False
    mismatches: tuple[str, ...] = field(default_factory=tuple)
    missing: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProviderEndpointCustodyManifest:
    endpoint_manifest_id: str
    endpoint_status: str
    endpoint_custody_kind: str
    linked_capability_manifest_id: str
    linked_capability_digest: str
    linked_credential_custody_manifest_id: str
    linked_credential_custody_digest: str
    declared_endpoint_properties: tuple[str, ...]
    forbidden_endpoint_properties: tuple[str, ...]
    missing_required_evidence: tuple[str, ...]
    endpoint_gaps: tuple[ProviderEndpointCustodyGap, ...]
    no_endpoint_material: bool = True
    endpoint_values_present: bool = False
    endpoint_references_present: bool = False
    endpoint_resolution_allowed: bool = False
    dns_resolution_allowed: bool = False
    env_access_allowed: bool = False
    file_access_allowed: bool = False
    config_store_access_allowed: bool = False
    credential_material_present: bool = False
    provider_client_material_present: bool = False
    network_access_allowed: bool = False
    endpoint_runtime_authority: bool = False
    findings: tuple[ProviderEndpointCustodyFinding, ...] = field(default_factory=tuple)
    constraints: tuple[ProviderEndpointCustodyConstraint, ...] = field(default_factory=tuple)
    rationale: str = ""
    endpoint_digest: str = ""
    provider_endpoint_custody_manifest_only: bool = True
    endpoint_resolution_forbidden: bool = True
    dns_resolution_forbidden: bool = True
    env_endpoint_access_forbidden: bool = True
    file_endpoint_access_forbidden: bool = True
    config_store_endpoint_access_forbidden: bool = True
    credential_material_forbidden: bool = True
    provider_client_material_forbidden: bool = True
    network_access_forbidden: bool = True
    endpoint_use_forbidden: bool = True
    credential_use_forbidden: bool = True
    live_provider_transport_forbidden: bool = True
    live_prompt_assembly_forbidden: bool = True
    live_model_call_forbidden: bool = True
    does_not_resolve_dns: bool = True
    does_not_read_environment: bool = True
    does_not_read_files: bool = True
    does_not_access_config_stores: bool = True
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
class ProviderEndpointCustodyPreflight:
    endpoint_preflight_id: str
    endpoint_preflight_status: str
    endpoint_manifest_id: str
    endpoint_status: str
    endpoint_digest: str
    capability_manifest_id: str
    capability_digest: str
    credential_custody_manifest_id: str
    credential_custody_digest: str
    credential_custody_preflight_id: str
    credential_custody_preflight_digest: str
    requested_endpoint_custody_kind: str
    requested_registration: bool
    endpoint_allowed: bool
    endpoint_material_allowed: bool
    endpoint_reference_allowed: bool
    endpoint_resolution_allowed: bool
    dns_resolution_allowed: bool
    env_access_allowed: bool
    file_access_allowed: bool
    config_store_access_allowed: bool
    credential_material_allowed: bool
    provider_client_material_allowed: bool
    network_access_allowed: bool
    provider_send_allowed: bool
    socket_allowed: bool
    http_allowed: bool
    provider_sdk_allowed: bool
    semantic_generation_allowed: bool
    findings: tuple[ProviderEndpointCustodyFinding, ...]
    warnings: tuple[str, ...]
    constraints: tuple[ProviderEndpointCustodyConstraint, ...]
    endpoint_gaps: tuple[ProviderEndpointCustodyGap, ...]
    rationale: str
    endpoint_preflight_digest: str
    internal_only: bool = True
    no_endpoint_material: bool = True
    no_endpoint_references: bool = True
    no_endpoint_resolution: bool = True
    no_dns_resolution: bool = True
    no_env_access: bool = True
    no_file_access: bool = True
    no_config_store_access: bool = True
    no_credentials: bool = True
    no_provider_client: bool = True
    no_network: bool = True
    no_provider_send: bool = True
    no_http: bool = True
    no_socket: bool = True
    no_provider_sdk: bool = True
    no_tools: bool = True
    no_memory: bool = True
    no_retention: bool = True
    no_actions: bool = True
    no_routing: bool = True
    no_semantic_generation: bool = True
    provider_endpoint_custody_preflight_only: bool = True
    endpoint_resolution_forbidden: bool = True
    dns_resolution_forbidden: bool = True
    env_endpoint_access_forbidden: bool = True
    file_endpoint_access_forbidden: bool = True
    config_store_endpoint_access_forbidden: bool = True
    credential_material_forbidden: bool = True
    provider_client_material_forbidden: bool = True
    network_access_forbidden: bool = True
    endpoint_use_forbidden: bool = True
    credential_use_forbidden: bool = True
    provider_send_forbidden: bool = True
    live_provider_transport_forbidden: bool = True
    live_model_call_forbidden: bool = True
    does_not_resolve_dns: bool = True
    does_not_read_environment: bool = True
    does_not_read_files: bool = True
    does_not_access_config_stores: bool = True
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
        ProviderEndpointCustodyKind.ENDPOINT_CUSTODY_NONE,
        ProviderEndpointCustodyKind.ENDPOINT_CUSTODY_NO_ENDPOINT_PLACEHOLDER,
        ProviderEndpointCustodyKind.ENDPOINT_CUSTODY_FUTURE_ENDPOINT_CONTRACT_PLACEHOLDER,
    }
)
_FORBIDDEN_KINDS = frozenset(
    {
        ProviderEndpointCustodyKind.ENDPOINT_CUSTODY_INLINE_URL_FORBIDDEN,
        ProviderEndpointCustodyKind.ENDPOINT_CUSTODY_ENV_ENDPOINT_FORBIDDEN,
        ProviderEndpointCustodyKind.ENDPOINT_CUSTODY_FILE_ENDPOINT_FORBIDDEN,
        ProviderEndpointCustodyKind.ENDPOINT_CUSTODY_CONFIG_STORE_ENDPOINT_FORBIDDEN,
        ProviderEndpointCustodyKind.ENDPOINT_CUSTODY_DNS_NAME_FORBIDDEN,
        ProviderEndpointCustodyKind.ENDPOINT_CUSTODY_IP_ADDRESS_FORBIDDEN,
        ProviderEndpointCustodyKind.ENDPOINT_CUSTODY_PROVIDER_CLIENT_ENDPOINT_FORBIDDEN,
        ProviderEndpointCustodyKind.ENDPOINT_CUSTODY_UNKNOWN_FORBIDDEN,
    }
)
_MANIFEST_FLAG_FIELDS = (
    "no_endpoint_material",
    "endpoint_values_present",
    "endpoint_references_present",
    "endpoint_resolution_allowed",
    "dns_resolution_allowed",
    "env_access_allowed",
    "file_access_allowed",
    "config_store_access_allowed",
    "credential_material_present",
    "provider_client_material_present",
    "network_access_allowed",
    "endpoint_runtime_authority",
)
_MANIFEST_MARKER_FIELDS = (
    "provider_endpoint_custody_manifest_only",
    "endpoint_resolution_forbidden",
    "dns_resolution_forbidden",
    "env_endpoint_access_forbidden",
    "file_endpoint_access_forbidden",
    "config_store_endpoint_access_forbidden",
    "credential_material_forbidden",
    "provider_client_material_forbidden",
    "network_access_forbidden",
    "endpoint_use_forbidden",
    "credential_use_forbidden",
    "live_provider_transport_forbidden",
    "live_prompt_assembly_forbidden",
    "live_model_call_forbidden",
    "does_not_resolve_dns",
    "does_not_read_environment",
    "does_not_read_files",
    "does_not_access_config_stores",
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
_PREFLIGHT_MARKER_FIELDS = tuple(field_name for field_name in _MANIFEST_MARKER_FIELDS if field_name not in {"provider_endpoint_custody_manifest_only", "live_prompt_assembly_forbidden"}) + (
    "provider_endpoint_custody_preflight_only",
    "provider_send_forbidden",
)
_RUNTIME_MARKER_KEYS = (
    "raw_payload",
    "runtime_handle",
    "execution_handle",
    "network_handle",
    "request_handle",
    "response_handle",
    "provider_params",
    "model_params",
    "llm_params",
    "endpoint_url",
    "provider_client_handle",
    "session_handle",
    "transport_handle",
    "socket_handle",
    "http_client",
    "tool_schema",
    "credential_handle",
)
_ENDPOINT_PATTERNS = (
    "https://",
    "http://",
    "ws://",
    "wss://",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "endpoint=",
    "base_url",
    "api_url",
    "host=",
    "hostname",
    "port=",
    "dns:",
    "resolve",
    "socket",
    "connect",
    "request",
    "session",
    "client",
    "/etc/hosts",
    ".env",
    "config:",
    "~/.config",
    "provider endpoint",
    "openai.com",
    "anthropic.com",
    "azure.com",
    "googleapis.com",
    "authorization",
    "bearer",
    "api key",
    "token=",
    "secret=",
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


def _finding(code: str, detail: str, severity: str = "blocker") -> ProviderEndpointCustodyFinding:
    return ProviderEndpointCustodyFinding(code=code, detail=detail, severity=severity)


def _constraints() -> tuple[ProviderEndpointCustodyConstraint, ...]:
    return (
        ProviderEndpointCustodyConstraint("endpoint_custody_manifest_only", "endpoint custody manifest is evidence metadata only, not endpoint custody"),
        ProviderEndpointCustodyConstraint("no_endpoint_material", "endpoint values, references, resolver material, DNS names, hostnames, addresses, and ports are forbidden"),
        ProviderEndpointCustodyConstraint("no_endpoint_resolution", "DNS, environment, file, and config-store endpoint lookup are forbidden"),
        ProviderEndpointCustodyConstraint("no_credentials_or_clients", "credential and provider-client material are forbidden"),
        ProviderEndpointCustodyConstraint("no_network_or_runtime", "network egress, provider send, model calls, memory, tools, routing, actions, and retention are forbidden"),
    )


def _default_gaps() -> tuple[ProviderEndpointCustodyGap, ...]:
    return (
        ProviderEndpointCustodyGap("real_endpoint_review_missing", "future real custody requires external endpoint review without storing the endpoint"),
        ProviderEndpointCustodyGap("endpoint_ownership_proof_missing", "future real custody requires custody and ownership evidence"),
        ProviderEndpointCustodyGap("resolver_isolation_missing", "future real custody requires resolver isolation evidence outside Phase 93"),
        ProviderEndpointCustodyGap("network_egress_review_missing", "future real custody requires network egress review outside Phase 93"),
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


def _endpoint_pattern_findings(*values: Any) -> tuple[ProviderEndpointCustodyFinding, ...]:
    findings: list[ProviderEndpointCustodyFinding] = []
    for value in values:
        for path, text in _metadata_strings(value):
            lowered = text.lower()
            if _is_negative_marker_name(path, text):
                continue
            for pattern in _ENDPOINT_PATTERNS:
                if pattern in lowered:
                    code = "endpoint_like_metadata_detected"
                    if pattern in {"dns:", "resolve"}:
                        code = "dns_resolution_detected"
                    elif pattern in {".env"}:
                        code = "env_endpoint_reference_detected"
                    elif pattern in {"/etc/hosts", "~/.config"}:
                        code = "file_endpoint_reference_detected"
                    elif pattern in {"config:"}:
                        code = "config_store_endpoint_reference_detected"
                    elif pattern in {"client", "session"}:
                        code = "provider_client_material_detected"
                    elif pattern in {"socket", "connect", "request", "ws://", "wss://"}:
                        code = "network_material_detected"
                    elif pattern in {"authorization", "bearer", "api key", "token=", "secret="}:
                        code = "credential_material_detected"
                    findings.append(_finding(code, f"metadata at {path or '<value>'} matched forbidden endpoint custody pattern {pattern!r}"))
                    break
    return tuple(findings)


def _runtime_marker_findings(value: Any) -> tuple[ProviderEndpointCustodyFinding, ...]:
    findings: list[ProviderEndpointCustodyFinding] = []
    for path, text in _metadata_strings(value):
        lowered = text.lower()
        if _is_negative_marker_name(path, text):
            continue
        for key in _RUNTIME_MARKER_KEYS:
            if key in lowered:
                findings.append(_finding("runtime_marker_detected", f"metadata at {path or '<value>'} included forbidden runtime marker {key!r}"))
                break
    return tuple(findings)


def _status_for_findings(findings: Sequence[ProviderEndpointCustodyFinding], missing: Sequence[str]) -> str:
    codes = {finding.code for finding in findings}
    if "invalid_endpoint_custody_kind" in codes:
        return ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_INVALID
    if any(code in codes for code in ("forbidden_endpoint_custody_kind", "endpoint_value_present", "endpoint_like_metadata_detected")):
        return ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_FORBIDDEN_ENDPOINT_DETECTED
    if any(code in codes for code in ("endpoint_reference_present",)):
        return ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_ENDPOINT_REFERENCE_DETECTED
    if any(code in codes for code in ("endpoint_resolution_allowed", "dns_resolution_detected")):
        return ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_DNS_RESOLUTION_DETECTED
    if any(code in codes for code in ("env_access_allowed", "env_endpoint_reference_detected")):
        return ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_ENV_ACCESS_DETECTED
    if any(code in codes for code in ("file_access_allowed", "file_endpoint_reference_detected")):
        return ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_FILE_ACCESS_DETECTED
    if any(code in codes for code in ("config_store_access_allowed", "config_store_endpoint_reference_detected")):
        return ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_CONFIG_STORE_ACCESS_DETECTED
    if any(code in codes for code in ("credential_material_present", "credential_material_detected")):
        return ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_CREDENTIALS_DETECTED
    if any(code in codes for code in ("provider_client_material_present", "provider_client_material_detected")):
        return ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_CLIENT_DETECTED
    if any(code in codes for code in ("network_access_allowed", "network_material_detected")):
        return ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_NETWORK_DETECTED
    if any(code in codes for code in ("runtime_marker_detected", "runtime_authority_detected", "endpoint_marker_missing")):
        return ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_RUNTIME_AUTHORITY_DETECTED
    if missing:
        return ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_INCOMPLETE
    return ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_NO_ENDPOINTS


def build_provider_endpoint_custody_manifest(
    *,
    endpoint_custody_kind: str = ProviderEndpointCustodyKind.ENDPOINT_CUSTODY_NONE,
    linked_capability_manifest: ProviderTransportCapabilityManifest | Mapping[str, Any] | None = None,
    linked_capability_manifest_id: str = "",
    linked_capability_digest: str = "",
    linked_credential_custody_manifest: ProviderCredentialCustodyManifest | Mapping[str, Any] | None = None,
    linked_credential_custody_manifest_id: str = "",
    linked_credential_custody_digest: str = "",
    declared_endpoint_properties: Sequence[str] = (),
    forbidden_endpoint_properties: Sequence[str] = (),
    missing_required_evidence: Sequence[str] = (),
    metadata_evidence: Any = None,
    no_endpoint_material: bool = True,
    endpoint_values_present: bool = False,
    endpoint_references_present: bool = False,
    endpoint_resolution_allowed: bool = False,
    dns_resolution_allowed: bool = False,
    env_access_allowed: bool = False,
    file_access_allowed: bool = False,
    config_store_access_allowed: bool = False,
    credential_material_present: bool = False,
    provider_client_material_present: bool = False,
    network_access_allowed: bool = False,
    endpoint_runtime_authority: bool = False,
    marker_overrides: Mapping[str, bool] | None = None,
) -> ProviderEndpointCustodyManifest:
    linked_capability = _mapping(linked_capability_manifest)
    linked_credential = _mapping(linked_credential_custody_manifest)
    capability_id = linked_capability_manifest_id or str(linked_capability.get("capability_manifest_id", ""))
    capability_digest = linked_capability_digest or str(linked_capability.get("capability_digest", ""))
    credential_id = linked_credential_custody_manifest_id or str(linked_credential.get("custody_manifest_id", ""))
    credential_digest = linked_credential_custody_digest or str(linked_credential.get("custody_digest", ""))
    findings: list[ProviderEndpointCustodyFinding] = []
    kind = str(endpoint_custody_kind)
    if kind in _FORBIDDEN_KINDS:
        findings.append(_finding("forbidden_endpoint_custody_kind", f"{kind} is forbidden in Phase 93"))
    elif kind not in _ALLOWED_KINDS:
        findings.append(_finding("invalid_endpoint_custody_kind", "unknown endpoint custody kind is forbidden"))
    flag_values = {
        "no_endpoint_material": bool(no_endpoint_material),
        "endpoint_values_present": bool(endpoint_values_present),
        "endpoint_references_present": bool(endpoint_references_present),
        "endpoint_resolution_allowed": bool(endpoint_resolution_allowed),
        "dns_resolution_allowed": bool(dns_resolution_allowed),
        "env_access_allowed": bool(env_access_allowed),
        "file_access_allowed": bool(file_access_allowed),
        "config_store_access_allowed": bool(config_store_access_allowed),
        "credential_material_present": bool(credential_material_present),
        "provider_client_material_present": bool(provider_client_material_present),
        "network_access_allowed": bool(network_access_allowed),
        "endpoint_runtime_authority": bool(endpoint_runtime_authority),
    }
    if not flag_values["no_endpoint_material"] or flag_values["endpoint_values_present"]:
        findings.append(_finding("endpoint_value_present", "endpoint material is forbidden"))
    if flag_values["endpoint_references_present"]:
        findings.append(_finding("endpoint_reference_present", "endpoint references are forbidden"))
    for field_name in (
        "endpoint_resolution_allowed",
        "dns_resolution_allowed",
        "env_access_allowed",
        "file_access_allowed",
        "config_store_access_allowed",
        "credential_material_present",
        "provider_client_material_present",
        "network_access_allowed",
        "endpoint_runtime_authority",
    ):
        if flag_values[field_name]:
            findings.append(_finding(field_name if field_name != "endpoint_runtime_authority" else "runtime_authority_detected", f"{field_name} must remain false"))
    evidence = (kind, tuple(declared_endpoint_properties), tuple(forbidden_endpoint_properties), tuple(missing_required_evidence), metadata_evidence)
    findings.extend(_endpoint_pattern_findings(evidence))
    findings.extend(_runtime_marker_findings(metadata_evidence))
    markers = {field_name: True for field_name in _MANIFEST_MARKER_FIELDS}
    if marker_overrides:
        markers.update({str(key): bool(value) for key, value in marker_overrides.items() if str(key) in markers})
    for field_name, value in markers.items():
        if value is not True:
            findings.append(_finding("endpoint_marker_missing", f"{field_name} must be true"))
    missing = tuple(str(item) for item in missing_required_evidence)
    status = _status_for_findings(findings, missing)
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "endpoint custody manifest is metadata-only and contains no endpoint values, references, resolver access, credentials, provider clients, network authority, or runtime authority"
    manifest = ProviderEndpointCustodyManifest(
        endpoint_manifest_id="",
        endpoint_status=status,
        endpoint_custody_kind=kind,
        linked_capability_manifest_id=capability_id,
        linked_capability_digest=capability_digest,
        linked_credential_custody_manifest_id=credential_id,
        linked_credential_custody_digest=credential_digest,
        declared_endpoint_properties=tuple(str(item) for item in declared_endpoint_properties),
        forbidden_endpoint_properties=tuple(str(item) for item in forbidden_endpoint_properties),
        missing_required_evidence=missing,
        endpoint_gaps=_default_gaps(),
        findings=tuple(findings),
        constraints=_constraints(),
        rationale=rationale[:1000],
        endpoint_digest="",
        **flag_values,
        **markers,
    )
    digest = compute_provider_endpoint_custody_digest(manifest)
    return replace(manifest, endpoint_manifest_id=f"provider-endpoint-custody:{digest[:16]}", endpoint_digest=digest)


def _digest_payload(data: Mapping[str, Any], digest_field: str, id_field: str) -> dict[str, Any]:
    payload = dict(data)
    payload[digest_field] = ""
    payload[id_field] = ""
    return payload


def compute_provider_endpoint_custody_digest(manifest: ProviderEndpointCustodyManifest | Mapping[str, Any]) -> str:
    return _stable_digest(_digest_payload(_mapping(manifest), "endpoint_digest", "endpoint_manifest_id"))


def compute_provider_endpoint_custody_preflight_digest(preflight: ProviderEndpointCustodyPreflight | Mapping[str, Any]) -> str:
    return _stable_digest(_digest_payload(_mapping(preflight), "endpoint_preflight_digest", "endpoint_preflight_id"))


def validate_provider_endpoint_custody_manifest(manifest: ProviderEndpointCustodyManifest | Mapping[str, Any]) -> tuple[ProviderEndpointCustodyFinding, ...]:
    data = _mapping(manifest)
    findings: list[ProviderEndpointCustodyFinding] = []
    if not data:
        return (_finding("endpoint_manifest_missing", "ProviderEndpointCustodyManifest is required"),)
    digest = str(data.get("endpoint_digest", ""))
    if digest and compute_provider_endpoint_custody_digest(data) != digest:
        findings.append(_finding("endpoint_digest_mismatch", "endpoint custody digest does not match manifest fields"))
    kind = str(data.get("endpoint_custody_kind", ""))
    if kind in _FORBIDDEN_KINDS:
        findings.append(_finding("forbidden_endpoint_custody_kind", f"{kind} is forbidden in Phase 93"))
    elif kind not in _ALLOWED_KINDS:
        findings.append(_finding("invalid_endpoint_custody_kind", "unknown endpoint custody kind is forbidden"))
    for field_name in _MANIFEST_FLAG_FIELDS:
        value = data.get(field_name)
        if field_name == "no_endpoint_material":
            if value is not True:
                findings.append(_finding("endpoint_value_present", "no_endpoint_material must be true"))
        elif value is True:
            code = field_name if field_name != "endpoint_runtime_authority" else "runtime_authority_detected"
            findings.append(_finding(code, f"{field_name} must remain false"))
    for field_name in _MANIFEST_MARKER_FIELDS:
        if data.get(field_name) is not True:
            findings.append(_finding("endpoint_marker_missing", f"{field_name} must be true"))
    findings.extend(_endpoint_pattern_findings(data.get("declared_endpoint_properties", ()), data.get("forbidden_endpoint_properties", ())))
    findings.extend(_runtime_marker_findings(data.get("declared_endpoint_properties", ())))
    return tuple(findings)


def _preflight_status_for_findings(findings: Sequence[ProviderEndpointCustodyFinding], manifest_status: str, allowed: bool) -> str:
    if allowed and not findings:
        return ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_NO_ENDPOINTS_ALLOWED
    codes = {finding.code for finding in findings}
    if any(code in codes for code in ("endpoint_manifest_missing", "invalid_endpoint_custody_kind", "endpoint_digest_mismatch", "credential_custody_digest_mismatch", "credential_custody_preflight_digest_mismatch", "capability_digest_mismatch")):
        return ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_INVALID_INPUT
    if any(code in codes for code in ("forbidden_endpoint_custody_kind", "endpoint_value_present", "endpoint_like_metadata_detected")):
        return ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_FORBIDDEN_ENDPOINT_DETECTED
    if any(code in codes for code in ("endpoint_reference_present", "requested_endpoint_resolution", "endpoint_resolution_allowed", "endpoint_resolution_not_negated")):
        return ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_ENDPOINT_RESOLUTION_FORBIDDEN
    if any(code in codes for code in ("requested_dns_resolution", "dns_resolution_allowed", "dns_resolution_detected", "dns_resolution_not_negated")):
        return ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_DNS_RESOLUTION_DETECTED
    if any(code in codes for code in ("requested_env_access", "env_access_allowed", "env_endpoint_reference_detected", "env_access_not_negated")):
        return ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_ENV_ACCESS_DETECTED
    if any(code in codes for code in ("requested_file_access", "file_access_allowed", "file_endpoint_reference_detected", "file_access_not_negated")):
        return ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_FILE_ACCESS_DETECTED
    if any(code in codes for code in ("requested_config_store_access", "config_store_access_allowed", "config_store_endpoint_reference_detected", "config_store_access_not_negated")):
        return ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_CONFIG_STORE_ACCESS_DETECTED
    if any(code in codes for code in ("requested_credential_material", "credential_material_present", "credential_material_detected", "credentials_not_negated", "credential_custody_secret_detected", "credential_preflight_secret_detected")):
        return ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_CREDENTIALS_DETECTED
    if any(code in codes for code in ("requested_provider_client_material", "provider_client_material_present", "provider_client_material_detected", "provider_client_not_negated")):
        return ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_CLIENT_DETECTED
    if any(code in codes for code in ("requested_network_access", "network_access_allowed", "network_material_detected", "network_not_negated", "provider_send_not_negated", "http_not_negated", "socket_not_negated", "requested_registration", "capability_real_transport_detected")):
        return ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_NETWORK_DETECTED
    if any(code in codes for code in ("runtime_marker_detected", "runtime_flag_not_negated", "runtime_authority_detected", "endpoint_marker_missing")):
        return ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED
    if manifest_status == ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_INCOMPLETE or "missing_required_evidence" in codes:
        return ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_INCOMPLETE_EVIDENCE
    return ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_DENIED


def evaluate_provider_endpoint_custody_preflight(
    endpoint_manifest: ProviderEndpointCustodyManifest | Mapping[str, Any] | None,
    capability_manifest: ProviderTransportCapabilityManifest | Mapping[str, Any] | None = None,
    credential_custody_manifest: ProviderCredentialCustodyManifest | Mapping[str, Any] | None = None,
    credential_custody_preflight: ProviderCredentialCustodyPreflight | Mapping[str, Any] | None = None,
    *,
    requested_endpoint_custody_kind: str = ProviderEndpointCustodyKind.ENDPOINT_CUSTODY_NONE,
    requested_endpoint_resolution: bool = False,
    requested_dns_resolution: bool = False,
    requested_env_access: bool = False,
    requested_file_access: bool = False,
    requested_config_store_access: bool = False,
    requested_credential_material: bool = False,
    requested_provider_client_material: bool = False,
    requested_network_access: bool = False,
    requested_registration: bool = False,
    internal_only: bool = True,
    no_endpoint_material: bool = True,
    no_endpoint_references: bool = True,
    no_endpoint_resolution: bool = True,
    no_dns_resolution: bool = True,
    no_env_access: bool = True,
    no_file_access: bool = True,
    no_config_store_access: bool = True,
    no_credentials: bool = True,
    no_provider_client: bool = True,
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
) -> ProviderEndpointCustodyPreflight:
    manifest = _mapping(endpoint_manifest)
    capability = _mapping(capability_manifest)
    credential = _mapping(credential_custody_manifest)
    credential_preflight = _mapping(credential_custody_preflight)
    findings: list[ProviderEndpointCustodyFinding] = []
    warnings: list[str] = []
    if not manifest:
        findings.append(_finding("endpoint_manifest_missing", "endpoint custody manifest is required"))
    else:
        findings.extend(validate_provider_endpoint_custody_manifest(endpoint_manifest or {}))
        manifest_status = str(manifest.get("endpoint_status", ""))
        status_to_code = {
            ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_FORBIDDEN_ENDPOINT_DETECTED: "endpoint_value_present",
            ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_ENDPOINT_REFERENCE_DETECTED: "endpoint_reference_present",
            ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_DNS_RESOLUTION_DETECTED: "dns_resolution_allowed",
            ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_ENV_ACCESS_DETECTED: "env_access_allowed",
            ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_FILE_ACCESS_DETECTED: "file_access_allowed",
            ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_CONFIG_STORE_ACCESS_DETECTED: "config_store_access_allowed",
            ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_CREDENTIALS_DETECTED: "credential_material_present",
            ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_CLIENT_DETECTED: "provider_client_material_present",
            ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_NETWORK_DETECTED: "network_access_allowed",
            ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_RUNTIME_AUTHORITY_DETECTED: "runtime_authority_detected",
            ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_INCOMPLETE: "missing_required_evidence",
            ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_INVALID: "invalid_endpoint_custody_kind",
        }
        if manifest_status in status_to_code:
            findings.append(_finding(status_to_code[manifest_status], f"endpoint custody manifest reports {manifest_status}"))
    requested_kind = str(requested_endpoint_custody_kind)
    if requested_kind in _FORBIDDEN_KINDS:
        findings.append(_finding("forbidden_endpoint_custody_kind", f"{requested_kind} is forbidden in Phase 93"))
    elif requested_kind not in _ALLOWED_KINDS:
        findings.append(_finding("invalid_endpoint_custody_kind", "unknown requested endpoint custody kind is forbidden"))
    requested_flags = {
        "requested_endpoint_resolution": requested_endpoint_resolution,
        "requested_dns_resolution": requested_dns_resolution,
        "requested_env_access": requested_env_access,
        "requested_file_access": requested_file_access,
        "requested_config_store_access": requested_config_store_access,
        "requested_credential_material": requested_credential_material,
        "requested_provider_client_material": requested_provider_client_material,
        "requested_network_access": requested_network_access,
        "requested_registration": requested_registration,
    }
    for field_name, value in requested_flags.items():
        if bool(value):
            findings.append(_finding(field_name, f"{field_name} is forbidden in Phase 93"))
    no_flags = {
        "no_endpoint_material": no_endpoint_material,
        "no_endpoint_references": no_endpoint_references,
        "no_endpoint_resolution": no_endpoint_resolution,
        "no_dns_resolution": no_dns_resolution,
        "no_env_access": no_env_access,
        "no_file_access": no_file_access,
        "no_config_store_access": no_config_store_access,
        "no_credentials": no_credentials,
        "no_provider_client": no_provider_client,
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
        "no_endpoint_material": "endpoint_value_present",
        "no_endpoint_references": "endpoint_reference_present",
        "no_endpoint_resolution": "endpoint_resolution_not_negated",
        "no_dns_resolution": "dns_resolution_not_negated",
        "no_env_access": "env_access_not_negated",
        "no_file_access": "file_access_not_negated",
        "no_config_store_access": "config_store_access_not_negated",
        "no_credentials": "credentials_not_negated",
        "no_provider_client": "provider_client_not_negated",
        "no_network": "network_not_negated",
        "no_provider_send": "provider_send_not_negated",
        "no_http": "http_not_negated",
        "no_socket": "socket_not_negated",
        "no_provider_sdk": "runtime_flag_not_negated",
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
    if capability:
        cap_digest = str(capability.get("capability_digest", ""))
        if cap_digest and compute_provider_transport_capability_digest(capability_manifest or {}) != cap_digest:
            findings.append(_finding("capability_digest_mismatch", "linked capability digest mismatch"))
        if not provider_transport_capability_is_null_only(capability_manifest or {}):
            findings.append(_finding("capability_real_transport_detected", "linked Phase 91 capability is not null-only"))
        if str(capability.get("capability_status", "")) != ProviderTransportCapabilityStatus.TRANSPORT_CAPABILITY_NULL_ONLY:
            findings.append(_finding("capability_real_transport_detected", "linked Phase 91 capability is not null-only metadata"))
    if credential:
        cred_digest = str(credential.get("custody_digest", ""))
        if cred_digest and compute_provider_credential_custody_digest(credential_custody_manifest or {}) != cred_digest:
            findings.append(_finding("credential_custody_digest_mismatch", "linked credential custody digest mismatch"))
        if not provider_credential_custody_contains_no_secrets(credential_custody_manifest or {}):
            findings.append(_finding("credential_custody_secret_detected", "linked Phase 92 credential custody is not no-secret metadata"))
        if str(credential.get("custody_status", "")) != ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_NO_SECRETS:
            findings.append(_finding("credential_custody_secret_detected", "linked Phase 92 credential custody status is not no-secret"))
    if credential_preflight:
        cred_preflight_digest = str(credential_preflight.get("custody_preflight_digest", ""))
        if cred_preflight_digest and compute_provider_credential_custody_preflight_digest(credential_custody_preflight or {}) != cred_preflight_digest:
            findings.append(_finding("credential_custody_preflight_digest_mismatch", "linked credential custody preflight digest mismatch"))
        if not provider_credential_preflight_remains_metadata_only(credential_custody_preflight or {}):
            findings.append(_finding("credential_preflight_secret_detected", "linked Phase 92 credential preflight is not metadata-only no-secret"))
        if str(credential_preflight.get("custody_preflight_status", "")) not in {
            ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_NO_SECRETS_ALLOWED,
        }:
            findings.append(_finding("credential_preflight_secret_detected", "linked Phase 92 credential preflight status is not no-secret metadata"))
    for field_name in (
        "endpoint_resolution_allowed",
        "dns_resolution_allowed",
        "env_access_allowed",
        "file_access_allowed",
        "config_store_access_allowed",
        "credential_material_present",
        "provider_client_material_present",
        "network_access_allowed",
        "endpoint_runtime_authority",
    ):
        if manifest.get(field_name) is True:
            findings.append(_finding(field_name if field_name != "endpoint_runtime_authority" else "runtime_authority_detected", f"manifest {field_name} is forbidden"))
    if manifest.get("no_endpoint_material") is not True or manifest.get("endpoint_values_present") is True:
        findings.append(_finding("endpoint_value_present", "manifest endpoint values are forbidden"))
    if manifest.get("endpoint_references_present") is True:
        findings.append(_finding("endpoint_reference_present", "manifest endpoint references are forbidden"))
    for field_name in _MANIFEST_MARKER_FIELDS:
        if manifest and manifest.get(field_name) is not True:
            findings.append(_finding("endpoint_marker_missing", f"manifest {field_name} must be true"))
    findings.extend(_endpoint_pattern_findings(metadata_evidence, manifest.get("declared_endpoint_properties", ()), manifest.get("forbidden_endpoint_properties", ())))
    findings.extend(_runtime_marker_findings(metadata_evidence))
    clean = bool(
        manifest
        and not findings
        and str(manifest.get("endpoint_status", "")) == ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_NO_ENDPOINTS
        and requested_kind in _ALLOWED_KINDS
        and all(bool(value) is True for value in no_flags.values())
        and not any(bool(value) for value in requested_flags.values())
    )
    status = _preflight_status_for_findings(findings, str(manifest.get("endpoint_status", "")), clean)
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "endpoint custody preflight allows only no-endpoint metadata compatibility and still forbids endpoint use, endpoint resolution, DNS, credentials, provider clients, network egress, model calls, and runtime side effects"
    preflight = ProviderEndpointCustodyPreflight(
        endpoint_preflight_id="",
        endpoint_preflight_status=status,
        endpoint_manifest_id=str(manifest.get("endpoint_manifest_id", "")),
        endpoint_status=str(manifest.get("endpoint_status", "")),
        endpoint_digest=str(manifest.get("endpoint_digest", "")),
        capability_manifest_id=str(capability.get("capability_manifest_id", "")),
        capability_digest=str(capability.get("capability_digest", "")),
        credential_custody_manifest_id=str(credential.get("custody_manifest_id", "")),
        credential_custody_digest=str(credential.get("custody_digest", "")),
        credential_custody_preflight_id=str(credential_preflight.get("custody_preflight_id", "")),
        credential_custody_preflight_digest=str(credential_preflight.get("custody_preflight_digest", "")),
        requested_endpoint_custody_kind=requested_kind,
        requested_registration=bool(requested_registration),
        endpoint_allowed=clean,
        endpoint_material_allowed=False,
        endpoint_reference_allowed=False,
        endpoint_resolution_allowed=False,
        dns_resolution_allowed=False,
        env_access_allowed=False,
        file_access_allowed=False,
        config_store_access_allowed=False,
        credential_material_allowed=False,
        provider_client_material_allowed=False,
        network_access_allowed=False,
        provider_send_allowed=False,
        socket_allowed=False,
        http_allowed=False,
        provider_sdk_allowed=False,
        semantic_generation_allowed=False,
        findings=tuple(findings),
        warnings=tuple(warnings),
        constraints=_constraints(),
        endpoint_gaps=tuple(manifest.get("endpoint_gaps", ())) if manifest else _default_gaps(),
        rationale=rationale[:1000],
        endpoint_preflight_digest="",
        internal_only=bool(internal_only),
        **{key: bool(value) for key, value in no_flags.items()},
    )
    digest = compute_provider_endpoint_custody_preflight_digest(preflight)
    return replace(preflight, endpoint_preflight_id=f"provider-endpoint-custody-preflight:{digest[:16]}", endpoint_preflight_digest=digest)


def provider_endpoint_custody_contains_no_endpoints(manifest: ProviderEndpointCustodyManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data.get("endpoint_status") == ProviderEndpointCustodyStatus.ENDPOINT_CUSTODY_NO_ENDPOINTS and data.get("no_endpoint_material") is True and data.get("endpoint_values_present") is False and data.get("endpoint_references_present") is False)


def provider_endpoint_custody_forbids_endpoint_resolution(subject: ProviderEndpointCustodyManifest | ProviderEndpointCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(data.get("endpoint_resolution_allowed") is False and data.get("endpoint_resolution_forbidden") is True)


def provider_endpoint_custody_forbids_dns_resolution(subject: ProviderEndpointCustodyManifest | ProviderEndpointCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(data.get("dns_resolution_allowed") is False and data.get("dns_resolution_forbidden") is True and data.get("does_not_resolve_dns") is True)


def provider_endpoint_custody_forbids_env_access(subject: ProviderEndpointCustodyManifest | ProviderEndpointCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(data.get("env_access_allowed") is False and data.get("env_endpoint_access_forbidden") is True and data.get("does_not_read_environment") is True)


def provider_endpoint_custody_forbids_file_access(subject: ProviderEndpointCustodyManifest | ProviderEndpointCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(data.get("file_access_allowed") is False and data.get("file_endpoint_access_forbidden") is True and data.get("does_not_read_files") is True)


def provider_endpoint_custody_forbids_config_store_access(subject: ProviderEndpointCustodyManifest | ProviderEndpointCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(data.get("config_store_access_allowed") is False and data.get("config_store_endpoint_access_forbidden") is True and data.get("does_not_access_config_stores") is True)


def provider_endpoint_custody_has_no_network(subject: ProviderEndpointCustodyManifest | ProviderEndpointCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(data.get("network_access_allowed") is False and data.get("network_access_forbidden") is True and data.get("does_not_make_network_calls") is True and data.get("does_not_send_to_provider") is True)


def provider_endpoint_custody_has_no_credentials(subject: ProviderEndpointCustodyManifest | ProviderEndpointCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    present_or_allowed = data.get("credential_material_present", data.get("credential_material_allowed", False))
    return bool(present_or_allowed is False and data.get("credential_material_forbidden") is True and data.get("credential_use_forbidden") is True)


def provider_endpoint_custody_has_no_provider_client(subject: ProviderEndpointCustodyManifest | ProviderEndpointCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    present_or_allowed = data.get("provider_client_material_present", data.get("provider_client_material_allowed", False))
    return bool(present_or_allowed is False and data.get("provider_client_material_forbidden") is True)


def provider_endpoint_custody_has_no_runtime_authority(subject: ProviderEndpointCustodyManifest | ProviderEndpointCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(data.get("endpoint_runtime_authority", False) is False and data.get("does_not_execute_or_route_work") is True and data.get("does_not_admit_work") is True and data.get("does_not_retrieve_memory") is True and data.get("does_not_write_memory") is True and data.get("does_not_commit_retention") is True)


def provider_endpoint_preflight_denies_real_endpoints(preflight: ProviderEndpointCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(data.get("endpoint_preflight_status") != ProviderEndpointCustodyPreflightStatus.ENDPOINT_PREFLIGHT_NO_ENDPOINTS_ALLOWED and data.get("endpoint_material_allowed") is False and data.get("endpoint_reference_allowed") is False and data.get("endpoint_use_forbidden") is True)


def provider_endpoint_preflight_remains_metadata_only(preflight: ProviderEndpointCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(data.get("provider_endpoint_custody_preflight_only") is True and data.get("endpoint_allowed") is True and data.get("no_endpoint_material") is True and provider_endpoint_custody_has_no_network(data) and provider_endpoint_custody_has_no_runtime_authority(data))


def explain_provider_endpoint_custody_findings(subject: ProviderEndpointCustodyManifest | ProviderEndpointCustodyPreflight | Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(f"{item.get('severity', 'blocker')}:{item.get('code', '')}:{item.get('detail', '')}" for item in _mapping(subject).get("findings", ()) if isinstance(item, Mapping)) or tuple(
        f"{finding.severity}:{finding.code}:{finding.detail}" for finding in getattr(subject, "findings", ())
    )


def summarize_provider_endpoint_custody_preflight(preflight: ProviderEndpointCustodyPreflight | Mapping[str, Any]) -> dict[str, Any]:
    data = _mapping(preflight)
    return {
        "endpoint_preflight_status": data.get("endpoint_preflight_status", ""),
        "endpoint_allowed": data.get("endpoint_allowed", False),
        "requested_endpoint_custody_kind": data.get("requested_endpoint_custody_kind", ""),
        "requested_registration": data.get("requested_registration", False),
        "endpoint_manifest_id": data.get("endpoint_manifest_id", ""),
        "capability_manifest_id": data.get("capability_manifest_id", ""),
        "credential_custody_manifest_id": data.get("credential_custody_manifest_id", ""),
        "credential_custody_preflight_id": data.get("credential_custody_preflight_id", ""),
        "finding_codes": tuple(item.get("code", "") for item in data.get("findings", ()) if isinstance(item, Mapping)),
        "warning_codes": tuple(data.get("warnings", ())),
        "endpoint_preflight_digest": data.get("endpoint_preflight_digest", ""),
    }
