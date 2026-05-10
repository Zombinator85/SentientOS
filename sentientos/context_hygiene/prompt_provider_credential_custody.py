from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_provider_transport_capability import (
    ProviderTransportCapabilityManifest,
    ProviderTransportCapabilityStatus,
    ProviderTransportRegistrationPreflight,
    ProviderTransportRegistrationStatus,
    compute_provider_transport_capability_digest,
    compute_provider_transport_registration_preflight_digest,
    provider_transport_capability_is_null_only,
    provider_transport_registration_remains_forbidden,
)


class ProviderCredentialCustodyStatus:
    CREDENTIAL_CUSTODY_NO_SECRETS = "credential_custody_no_secrets"
    CREDENTIAL_CUSTODY_FORBIDDEN_SECRET_DETECTED = "credential_custody_forbidden_secret_detected"
    CREDENTIAL_CUSTODY_SECRET_REFERENCE_DETECTED = "credential_custody_secret_reference_detected"
    CREDENTIAL_CUSTODY_ENV_ACCESS_DETECTED = "credential_custody_env_access_detected"
    CREDENTIAL_CUSTODY_FILE_ACCESS_DETECTED = "credential_custody_file_access_detected"
    CREDENTIAL_CUSTODY_VAULT_ACCESS_DETECTED = "credential_custody_vault_access_detected"
    CREDENTIAL_CUSTODY_ENDPOINT_DETECTED = "credential_custody_endpoint_detected"
    CREDENTIAL_CUSTODY_CLIENT_DETECTED = "credential_custody_client_detected"
    CREDENTIAL_CUSTODY_NETWORK_DETECTED = "credential_custody_network_detected"
    CREDENTIAL_CUSTODY_INCOMPLETE = "credential_custody_incomplete"
    CREDENTIAL_CUSTODY_INVALID = "credential_custody_invalid"
    CREDENTIAL_CUSTODY_RUNTIME_AUTHORITY_DETECTED = "credential_custody_runtime_authority_detected"


class ProviderCredentialCustodyPreflightStatus:
    CREDENTIAL_PREFLIGHT_DENIED = "credential_preflight_denied"
    CREDENTIAL_PREFLIGHT_NO_SECRETS_ALLOWED = "credential_preflight_no_secrets_allowed"
    CREDENTIAL_PREFLIGHT_FORBIDDEN_SECRET_DETECTED = "credential_preflight_forbidden_secret_detected"
    CREDENTIAL_PREFLIGHT_SECRET_RESOLUTION_FORBIDDEN = "credential_preflight_secret_resolution_forbidden"
    CREDENTIAL_PREFLIGHT_ENV_ACCESS_DETECTED = "credential_preflight_env_access_detected"
    CREDENTIAL_PREFLIGHT_FILE_ACCESS_DETECTED = "credential_preflight_file_access_detected"
    CREDENTIAL_PREFLIGHT_VAULT_ACCESS_DETECTED = "credential_preflight_vault_access_detected"
    CREDENTIAL_PREFLIGHT_ENDPOINT_DETECTED = "credential_preflight_endpoint_detected"
    CREDENTIAL_PREFLIGHT_CLIENT_DETECTED = "credential_preflight_client_detected"
    CREDENTIAL_PREFLIGHT_NETWORK_DETECTED = "credential_preflight_network_detected"
    CREDENTIAL_PREFLIGHT_INCOMPLETE_EVIDENCE = "credential_preflight_incomplete_evidence"
    CREDENTIAL_PREFLIGHT_INVALID_INPUT = "credential_preflight_invalid_input"
    CREDENTIAL_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED = "credential_preflight_runtime_authority_detected"


class ProviderCredentialCustodyKind:
    CREDENTIAL_CUSTODY_NONE = "credential_custody_none"
    CREDENTIAL_CUSTODY_NO_SECRET_PLACEHOLDER = "credential_custody_no_secret_placeholder"
    CREDENTIAL_CUSTODY_FUTURE_VAULT_CONTRACT_PLACEHOLDER = "credential_custody_future_vault_contract_placeholder"
    CREDENTIAL_CUSTODY_INLINE_SECRET_FORBIDDEN = "credential_custody_inline_secret_forbidden"
    CREDENTIAL_CUSTODY_ENV_SECRET_FORBIDDEN = "credential_custody_env_secret_forbidden"
    CREDENTIAL_CUSTODY_FILE_SECRET_FORBIDDEN = "credential_custody_file_secret_forbidden"
    CREDENTIAL_CUSTODY_KEYCHAIN_SECRET_FORBIDDEN = "credential_custody_keychain_secret_forbidden"
    CREDENTIAL_CUSTODY_VAULT_SECRET_FORBIDDEN = "credential_custody_vault_secret_forbidden"
    CREDENTIAL_CUSTODY_CLOUD_SECRET_FORBIDDEN = "credential_custody_cloud_secret_forbidden"
    CREDENTIAL_CUSTODY_PROVIDER_CLIENT_SECRET_FORBIDDEN = "credential_custody_provider_client_secret_forbidden"
    CREDENTIAL_CUSTODY_UNKNOWN_FORBIDDEN = "credential_custody_unknown_forbidden"


@dataclass(frozen=True)
class ProviderCredentialCustodyFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderCredentialCustodyConstraint:
    code: str
    detail: str
    required: bool = True


@dataclass(frozen=True)
class ProviderCredentialCustodyGap:
    code: str
    detail: str
    required_for_real_custody: bool = True


@dataclass(frozen=True)
class ProviderCredentialCustodyAuditChain:
    custody_manifest_id: str = ""
    custody_digest: str = ""
    capability_manifest_id: str = ""
    capability_digest: str = ""
    registration_preflight_id: str = ""
    registration_preflight_digest: str = ""
    complete: bool = False
    mismatches: tuple[str, ...] = field(default_factory=tuple)
    missing: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProviderCredentialCustodyManifest:
    custody_manifest_id: str
    custody_status: str
    custody_kind: str
    linked_capability_manifest_id: str
    linked_capability_digest: str
    declared_custody_properties: tuple[str, ...]
    forbidden_custody_properties: tuple[str, ...]
    missing_required_evidence: tuple[str, ...]
    custody_gaps: tuple[ProviderCredentialCustodyGap, ...]
    no_secret_material: bool = True
    secret_values_present: bool = False
    secret_references_present: bool = False
    secret_resolution_allowed: bool = False
    env_access_allowed: bool = False
    file_access_allowed: bool = False
    vault_access_allowed: bool = False
    keychain_access_allowed: bool = False
    cloud_secret_access_allowed: bool = False
    endpoint_material_present: bool = False
    provider_client_material_present: bool = False
    network_access_allowed: bool = False
    credential_runtime_authority: bool = False
    findings: tuple[ProviderCredentialCustodyFinding, ...] = field(default_factory=tuple)
    constraints: tuple[ProviderCredentialCustodyConstraint, ...] = field(default_factory=tuple)
    rationale: str = ""
    custody_digest: str = ""
    provider_credential_custody_manifest_only: bool = True
    secret_resolution_forbidden: bool = True
    env_secret_access_forbidden: bool = True
    file_secret_access_forbidden: bool = True
    vault_secret_access_forbidden: bool = True
    keychain_secret_access_forbidden: bool = True
    cloud_secret_access_forbidden: bool = True
    endpoint_material_forbidden: bool = True
    provider_client_material_forbidden: bool = True
    network_access_forbidden: bool = True
    credential_use_forbidden: bool = True
    live_provider_transport_forbidden: bool = True
    live_prompt_assembly_forbidden: bool = True
    live_model_call_forbidden: bool = True
    does_not_read_environment: bool = True
    does_not_read_files: bool = True
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
class ProviderCredentialCustodyPreflight:
    custody_preflight_id: str
    custody_preflight_status: str
    custody_manifest_id: str
    custody_status: str
    custody_digest: str
    capability_manifest_id: str
    capability_digest: str
    registration_preflight_id: str
    registration_preflight_digest: str
    requested_custody_kind: str
    requested_registration: bool
    custody_allowed: bool
    secret_material_allowed: bool
    secret_reference_allowed: bool
    secret_resolution_allowed: bool
    env_access_allowed: bool
    file_access_allowed: bool
    vault_access_allowed: bool
    keychain_access_allowed: bool
    cloud_secret_access_allowed: bool
    endpoint_material_allowed: bool
    provider_client_material_allowed: bool
    network_access_allowed: bool
    provider_send_allowed: bool
    socket_allowed: bool
    http_allowed: bool
    provider_sdk_allowed: bool
    semantic_generation_allowed: bool
    findings: tuple[ProviderCredentialCustodyFinding, ...]
    warnings: tuple[str, ...]
    constraints: tuple[ProviderCredentialCustodyConstraint, ...]
    custody_gaps: tuple[ProviderCredentialCustodyGap, ...]
    rationale: str
    custody_preflight_digest: str
    internal_only: bool = True
    no_secret_material: bool = True
    no_secret_references: bool = True
    no_secret_resolution: bool = True
    no_env_access: bool = True
    no_file_access: bool = True
    no_vault_access: bool = True
    no_keychain_access: bool = True
    no_cloud_secret_access: bool = True
    no_endpoint: bool = True
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
    provider_credential_custody_preflight_only: bool = True
    secret_resolution_forbidden: bool = True
    env_secret_access_forbidden: bool = True
    file_secret_access_forbidden: bool = True
    vault_secret_access_forbidden: bool = True
    keychain_secret_access_forbidden: bool = True
    cloud_secret_access_forbidden: bool = True
    endpoint_material_forbidden: bool = True
    provider_client_material_forbidden: bool = True
    network_access_forbidden: bool = True
    credential_use_forbidden: bool = True
    provider_send_forbidden: bool = True
    live_provider_transport_forbidden: bool = True
    live_model_call_forbidden: bool = True
    does_not_read_environment: bool = True
    does_not_read_files: bool = True
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


_ALLOWED_KINDS = frozenset(
    {
        ProviderCredentialCustodyKind.CREDENTIAL_CUSTODY_NONE,
        ProviderCredentialCustodyKind.CREDENTIAL_CUSTODY_NO_SECRET_PLACEHOLDER,
        ProviderCredentialCustodyKind.CREDENTIAL_CUSTODY_FUTURE_VAULT_CONTRACT_PLACEHOLDER,
    }
)
_FORBIDDEN_KINDS = frozenset(
    {
        ProviderCredentialCustodyKind.CREDENTIAL_CUSTODY_INLINE_SECRET_FORBIDDEN,
        ProviderCredentialCustodyKind.CREDENTIAL_CUSTODY_ENV_SECRET_FORBIDDEN,
        ProviderCredentialCustodyKind.CREDENTIAL_CUSTODY_FILE_SECRET_FORBIDDEN,
        ProviderCredentialCustodyKind.CREDENTIAL_CUSTODY_KEYCHAIN_SECRET_FORBIDDEN,
        ProviderCredentialCustodyKind.CREDENTIAL_CUSTODY_VAULT_SECRET_FORBIDDEN,
        ProviderCredentialCustodyKind.CREDENTIAL_CUSTODY_CLOUD_SECRET_FORBIDDEN,
        ProviderCredentialCustodyKind.CREDENTIAL_CUSTODY_PROVIDER_CLIENT_SECRET_FORBIDDEN,
        ProviderCredentialCustodyKind.CREDENTIAL_CUSTODY_UNKNOWN_FORBIDDEN,
    }
)
_MANIFEST_FLAG_FIELDS = (
    "no_secret_material",
    "secret_values_present",
    "secret_references_present",
    "secret_resolution_allowed",
    "env_access_allowed",
    "file_access_allowed",
    "vault_access_allowed",
    "keychain_access_allowed",
    "cloud_secret_access_allowed",
    "endpoint_material_present",
    "provider_client_material_present",
    "network_access_allowed",
    "credential_runtime_authority",
)
_MANIFEST_MARKER_FIELDS = (
    "provider_credential_custody_manifest_only",
    "secret_resolution_forbidden",
    "env_secret_access_forbidden",
    "file_secret_access_forbidden",
    "vault_secret_access_forbidden",
    "keychain_secret_access_forbidden",
    "cloud_secret_access_forbidden",
    "endpoint_material_forbidden",
    "provider_client_material_forbidden",
    "network_access_forbidden",
    "credential_use_forbidden",
    "live_provider_transport_forbidden",
    "live_prompt_assembly_forbidden",
    "live_model_call_forbidden",
    "does_not_read_environment",
    "does_not_read_files",
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
_PREFLIGHT_MARKER_FIELDS = tuple(field_name for field_name in _MANIFEST_MARKER_FIELDS if field_name not in {"provider_credential_custody_manifest_only", "live_prompt_assembly_forbidden"}) + (
    "provider_credential_custody_preflight_only",
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
    "llm_parameters",
    "api_key",
    "auth_header",
    "endpoint_url",
    "provider_client_handle",
    "session_handle",
    "transport_handle",
    "socket_handle",
    "http_client",
    "tool_schema",
    "credential_handle",
)
_SECRET_PATTERNS = (
    "sk-",
    "api key",
    "bearer",
    "authorization",
    "token=",
    "password",
    "secret=",
    "client_secret",
    "private_key",
    "begin private key",
    "env:",
    "getenv",
    "os.environ",
    ".env",
    "~/.config",
    "/secrets/",
    "vault:",
    "keychain:",
    "aws secretsmanager",
    "gcp secret manager",
    "azure key vault",
    "endpoint=",
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


def _finding(code: str, detail: str, severity: str = "blocker") -> ProviderCredentialCustodyFinding:
    return ProviderCredentialCustodyFinding(code=code, detail=detail, severity=severity)


def _constraints() -> tuple[ProviderCredentialCustodyConstraint, ...]:
    return (
        ProviderCredentialCustodyConstraint("custody_manifest_only", "credential custody manifest is evidence metadata only, not credential custody"),
        ProviderCredentialCustodyConstraint("no_secret_material", "secret values and resolvable references are forbidden"),
        ProviderCredentialCustodyConstraint("no_secret_resolution", "environment, file, vault, keychain, and cloud-secret lookup are forbidden"),
        ProviderCredentialCustodyConstraint("no_endpoint_or_client", "endpoint and provider-client material are forbidden"),
        ProviderCredentialCustodyConstraint("no_network_or_runtime", "network egress, provider send, model calls, memory, tools, routing, actions, and retention are forbidden"),
    )


def _default_gaps() -> tuple[ProviderCredentialCustodyGap, ...]:
    return (
        ProviderCredentialCustodyGap("real_secret_store_review_missing", "future real custody requires external review of a non-inline secret store without revealing a secret"),
        ProviderCredentialCustodyGap("credential_rotation_proof_missing", "future real custody requires rotation and revocation evidence"),
        ProviderCredentialCustodyGap("least_privilege_scope_missing", "future real custody requires least-privilege scope evidence"),
        ProviderCredentialCustodyGap("runtime_isolation_missing", "future real custody requires a runtime isolation proof outside Phase 92"),
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
    if any(fragment in lowered for fragment in _NEGATIVE_MARKER_FRAGMENTS):
        return True
    return False


def _secret_pattern_findings(*values: Any) -> tuple[ProviderCredentialCustodyFinding, ...]:
    findings: list[ProviderCredentialCustodyFinding] = []
    for value in values:
        for path, text in _metadata_strings(value):
            lowered = text.lower()
            if _is_negative_marker_name(path, text):
                continue
            for pattern in _SECRET_PATTERNS:
                if pattern in lowered:
                    code = "secret_like_metadata_detected"
                    if pattern in {"env:", "getenv", "os.environ", ".env"}:
                        code = "env_secret_reference_detected"
                    elif pattern in {"~/.config", "/secrets/"}:
                        code = "file_secret_reference_detected"
                    elif pattern in {"vault:", "keychain:", "aws secretsmanager", "gcp secret manager", "azure key vault"}:
                        code = "vault_or_keychain_secret_reference_detected"
                    elif pattern in {"endpoint=", "https://", "http://"}:
                        code = "endpoint_material_detected"
                    findings.append(_finding(code, f"metadata at {path or '<value>'} matched forbidden custody pattern {pattern!r}"))
                    break
    return tuple(findings)


def _runtime_marker_findings(value: Any) -> tuple[ProviderCredentialCustodyFinding, ...]:
    findings: list[ProviderCredentialCustodyFinding] = []
    for path, text in _metadata_strings(value):
        lowered = text.lower()
        if _is_negative_marker_name(path, text):
            continue
        for key in _RUNTIME_MARKER_KEYS:
            if key in lowered:
                findings.append(_finding("runtime_marker_detected", f"metadata at {path or '<value>'} included forbidden runtime marker {key!r}"))
                break
    return tuple(findings)


def _status_for_findings(findings: Sequence[ProviderCredentialCustodyFinding], missing: Sequence[str]) -> str:
    codes = {finding.code for finding in findings}
    if "invalid_custody_kind" in codes:
        return ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_INVALID
    if any(code in codes for code in ("secret_like_metadata_detected", "forbidden_custody_kind", "secret_value_present")):
        return ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_FORBIDDEN_SECRET_DETECTED
    if any(code in codes for code in ("env_secret_reference_detected", "secret_reference_present")):
        return ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_SECRET_REFERENCE_DETECTED
    if "env_access_allowed" in codes:
        return ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_ENV_ACCESS_DETECTED
    if any(code in codes for code in ("file_access_allowed", "file_secret_reference_detected")):
        return ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_FILE_ACCESS_DETECTED
    if any(code in codes for code in ("vault_access_allowed", "keychain_access_allowed", "cloud_secret_access_allowed", "vault_or_keychain_secret_reference_detected")):
        return ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_VAULT_ACCESS_DETECTED
    if any(code in codes for code in ("endpoint_material_present", "endpoint_material_detected")):
        return ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_ENDPOINT_DETECTED
    if "provider_client_material_present" in codes:
        return ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_CLIENT_DETECTED
    if "network_access_allowed" in codes:
        return ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_NETWORK_DETECTED
    if any(code in codes for code in ("runtime_authority_detected", "runtime_marker_detected")):
        return ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_RUNTIME_AUTHORITY_DETECTED
    if missing:
        return ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_INCOMPLETE
    return ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_NO_SECRETS


def build_provider_credential_custody_manifest(
    *,
    custody_kind: str = ProviderCredentialCustodyKind.CREDENTIAL_CUSTODY_NONE,
    linked_capability_manifest: ProviderTransportCapabilityManifest | Mapping[str, Any] | None = None,
    linked_capability_manifest_id: str = "",
    linked_capability_digest: str = "",
    declared_custody_properties: Sequence[str] = (),
    forbidden_custody_properties: Sequence[str] = (),
    missing_required_evidence: Sequence[str] = (),
    metadata_evidence: Any = None,
    no_secret_material: bool = True,
    secret_values_present: bool = False,
    secret_references_present: bool = False,
    secret_resolution_allowed: bool = False,
    env_access_allowed: bool = False,
    file_access_allowed: bool = False,
    vault_access_allowed: bool = False,
    keychain_access_allowed: bool = False,
    cloud_secret_access_allowed: bool = False,
    endpoint_material_present: bool = False,
    provider_client_material_present: bool = False,
    network_access_allowed: bool = False,
    credential_runtime_authority: bool = False,
    marker_overrides: Mapping[str, bool] | None = None,
) -> ProviderCredentialCustodyManifest:
    linked = _mapping(linked_capability_manifest)
    capability_id = linked_capability_manifest_id or str(linked.get("capability_manifest_id", ""))
    capability_digest = linked_capability_digest or str(linked.get("capability_digest", ""))
    findings: list[ProviderCredentialCustodyFinding] = []
    kind = str(custody_kind)
    if kind in _FORBIDDEN_KINDS:
        findings.append(_finding("forbidden_custody_kind", f"{kind} is forbidden in Phase 92"))
    elif kind not in _ALLOWED_KINDS:
        findings.append(_finding("invalid_custody_kind", "unknown custody kind is forbidden"))
    flag_values = {
        "no_secret_material": bool(no_secret_material),
        "secret_values_present": bool(secret_values_present),
        "secret_references_present": bool(secret_references_present),
        "secret_resolution_allowed": bool(secret_resolution_allowed),
        "env_access_allowed": bool(env_access_allowed),
        "file_access_allowed": bool(file_access_allowed),
        "vault_access_allowed": bool(vault_access_allowed),
        "keychain_access_allowed": bool(keychain_access_allowed),
        "cloud_secret_access_allowed": bool(cloud_secret_access_allowed),
        "endpoint_material_present": bool(endpoint_material_present),
        "provider_client_material_present": bool(provider_client_material_present),
        "network_access_allowed": bool(network_access_allowed),
        "credential_runtime_authority": bool(credential_runtime_authority),
    }
    if not flag_values["no_secret_material"] or flag_values["secret_values_present"]:
        findings.append(_finding("secret_value_present", "secret material is forbidden"))
    if flag_values["secret_references_present"]:
        findings.append(_finding("secret_reference_present", "secret references are forbidden"))
    for field_name in (
        "secret_resolution_allowed",
        "env_access_allowed",
        "file_access_allowed",
        "vault_access_allowed",
        "keychain_access_allowed",
        "cloud_secret_access_allowed",
        "endpoint_material_present",
        "provider_client_material_present",
        "network_access_allowed",
        "credential_runtime_authority",
    ):
        if flag_values[field_name]:
            findings.append(_finding(field_name if field_name != "credential_runtime_authority" else "runtime_authority_detected", f"{field_name} must remain false"))
    evidence = (kind, tuple(declared_custody_properties), tuple(forbidden_custody_properties), tuple(missing_required_evidence), metadata_evidence)
    findings.extend(_secret_pattern_findings(evidence))
    findings.extend(_runtime_marker_findings(metadata_evidence))
    markers = {field_name: True for field_name in _MANIFEST_MARKER_FIELDS}
    if marker_overrides:
        markers.update({str(key): bool(value) for key, value in marker_overrides.items() if str(key) in markers})
    for field_name, value in markers.items():
        if value is not True:
            findings.append(_finding("custody_marker_missing", f"{field_name} must be true"))
    missing = tuple(str(item) for item in missing_required_evidence)
    status = _status_for_findings(findings, missing)
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "credential custody manifest is metadata-only and contains no secrets, resolvable references, endpoint material, provider clients, network authority, or runtime authority"
    manifest = ProviderCredentialCustodyManifest(
        custody_manifest_id="",
        custody_status=status,
        custody_kind=kind,
        linked_capability_manifest_id=capability_id,
        linked_capability_digest=capability_digest,
        declared_custody_properties=tuple(str(item) for item in declared_custody_properties),
        forbidden_custody_properties=tuple(str(item) for item in forbidden_custody_properties),
        missing_required_evidence=missing,
        custody_gaps=_default_gaps(),
        findings=tuple(findings),
        constraints=_constraints(),
        rationale=rationale[:1000],
        custody_digest="",
        **flag_values,
        **markers,
    )
    digest = compute_provider_credential_custody_digest(manifest)
    return replace(manifest, custody_manifest_id=f"provider-credential-custody:{digest[:16]}", custody_digest=digest)


def _digest_payload(data: Mapping[str, Any], digest_field: str, id_field: str) -> dict[str, Any]:
    payload = dict(data)
    payload[digest_field] = ""
    payload[id_field] = ""
    return payload


def compute_provider_credential_custody_digest(manifest: ProviderCredentialCustodyManifest | Mapping[str, Any]) -> str:
    return _stable_digest(_digest_payload(_mapping(manifest), "custody_digest", "custody_manifest_id"))


def compute_provider_credential_custody_preflight_digest(preflight: ProviderCredentialCustodyPreflight | Mapping[str, Any]) -> str:
    return _stable_digest(_digest_payload(_mapping(preflight), "custody_preflight_digest", "custody_preflight_id"))


def validate_provider_credential_custody_manifest(manifest: ProviderCredentialCustodyManifest | Mapping[str, Any]) -> tuple[ProviderCredentialCustodyFinding, ...]:
    data = _mapping(manifest)
    findings: list[ProviderCredentialCustodyFinding] = []
    if not data:
        return (_finding("custody_manifest_missing", "ProviderCredentialCustodyManifest is required"),)
    valid_statuses = {
        ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_NO_SECRETS,
        ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_FORBIDDEN_SECRET_DETECTED,
        ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_SECRET_REFERENCE_DETECTED,
        ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_ENV_ACCESS_DETECTED,
        ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_FILE_ACCESS_DETECTED,
        ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_VAULT_ACCESS_DETECTED,
        ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_ENDPOINT_DETECTED,
        ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_CLIENT_DETECTED,
        ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_NETWORK_DETECTED,
        ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_INCOMPLETE,
        ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_INVALID,
        ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_RUNTIME_AUTHORITY_DETECTED,
    }
    if str(data.get("custody_status", "")) not in valid_statuses:
        findings.append(_finding("custody_status_unknown", "unknown credential custody status"))
    if str(data.get("custody_kind", "")) not in _ALLOWED_KINDS and str(data.get("custody_kind", "")) not in _FORBIDDEN_KINDS:
        findings.append(_finding("invalid_custody_kind", "unknown custody kind is forbidden"))
    for field_name in _MANIFEST_MARKER_FIELDS:
        if data.get(field_name) is not True:
            findings.append(_finding("custody_marker_missing", f"{field_name} must be true"))
    for field_name in _MANIFEST_FLAG_FIELDS:
        expected = True if field_name == "no_secret_material" else False
        if data.get(field_name) is not expected:
            findings.append(_finding("custody_forbidden_flag_detected", f"{field_name} must be {expected}"))
    findings.extend(_secret_pattern_findings(data.get("custody_kind", ""), data.get("declared_custody_properties", ()), data.get("forbidden_custody_properties", ())))
    if compute_provider_credential_custody_digest(manifest) != str(data.get("custody_digest", "")):
        findings.append(_finding("custody_digest_mismatch", "custody digest does not match stable metadata"))
    return tuple(findings)


def _preflight_status_for_findings(findings: Sequence[ProviderCredentialCustodyFinding], manifest_status: str, allowed: bool) -> str:
    if allowed:
        return ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_NO_SECRETS_ALLOWED
    codes = {finding.code for finding in findings}
    if any(code in codes for code in ("custody_manifest_missing", "custody_manifest_invalid", "invalid_custody_kind", "custody_digest_mismatch")):
        return ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_INVALID_INPUT
    if any(code in codes for code in ("forbidden_custody_kind", "secret_like_metadata_detected", "secret_value_present", "secret_material_requested")):
        return ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_FORBIDDEN_SECRET_DETECTED
    if any(code in codes for code in ("requested_secret_resolution", "secret_resolution_not_negated", "secret_resolution_allowed")):
        return ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_SECRET_RESOLUTION_FORBIDDEN
    if any(code in codes for code in ("requested_env_access", "env_access_not_negated", "env_access_allowed", "env_secret_reference_detected")):
        return ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_ENV_ACCESS_DETECTED
    if any(code in codes for code in ("requested_file_access", "file_access_not_negated", "file_access_allowed", "file_secret_reference_detected")):
        return ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_FILE_ACCESS_DETECTED
    if any(code in codes for code in ("requested_vault_access", "requested_keychain_access", "requested_cloud_secret_access", "vault_access_not_negated", "keychain_access_not_negated", "cloud_secret_access_not_negated", "vault_access_allowed", "keychain_access_allowed", "cloud_secret_access_allowed", "vault_or_keychain_secret_reference_detected")):
        return ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_VAULT_ACCESS_DETECTED
    if any(code in codes for code in ("requested_endpoint_material", "endpoint_not_negated", "endpoint_material_present", "endpoint_material_detected")):
        return ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_ENDPOINT_DETECTED
    if any(code in codes for code in ("requested_provider_client_material", "provider_client_not_negated", "provider_client_material_present")):
        return ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_CLIENT_DETECTED
    if any(code in codes for code in ("requested_network_access", "network_not_negated", "provider_send_not_negated", "http_not_negated", "socket_not_negated", "network_access_allowed", "capability_real_transport_detected", "registration_real_transport_detected")):
        return ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_NETWORK_DETECTED
    if any(code in codes for code in ("runtime_marker_detected", "runtime_flag_not_negated", "runtime_authority_detected")):
        return ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED
    if manifest_status == ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_INCOMPLETE or "missing_required_evidence" in codes:
        return ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_INCOMPLETE_EVIDENCE
    return ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_DENIED


def evaluate_provider_credential_custody_preflight(
    custody_manifest: ProviderCredentialCustodyManifest | Mapping[str, Any] | None,
    capability_manifest: ProviderTransportCapabilityManifest | Mapping[str, Any] | None = None,
    registration_preflight: ProviderTransportRegistrationPreflight | Mapping[str, Any] | None = None,
    *,
    requested_custody_kind: str = ProviderCredentialCustodyKind.CREDENTIAL_CUSTODY_NONE,
    requested_secret_resolution: bool = False,
    requested_env_access: bool = False,
    requested_file_access: bool = False,
    requested_vault_access: bool = False,
    requested_keychain_access: bool = False,
    requested_cloud_secret_access: bool = False,
    requested_endpoint_material: bool = False,
    requested_provider_client_material: bool = False,
    requested_network_access: bool = False,
    requested_registration: bool = False,
    internal_only: bool = True,
    no_secret_material: bool = True,
    no_secret_references: bool = True,
    no_secret_resolution: bool = True,
    no_env_access: bool = True,
    no_file_access: bool = True,
    no_vault_access: bool = True,
    no_keychain_access: bool = True,
    no_cloud_secret_access: bool = True,
    no_endpoint: bool = True,
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
) -> ProviderCredentialCustodyPreflight:
    manifest = _mapping(custody_manifest)
    capability = _mapping(capability_manifest)
    registration = _mapping(registration_preflight)
    findings: list[ProviderCredentialCustodyFinding] = []
    warnings: list[str] = []
    if not manifest:
        findings.append(_finding("custody_manifest_missing", "custody manifest is required"))
    else:
        findings.extend(validate_provider_credential_custody_manifest(custody_manifest or {}))
        manifest_status = str(manifest.get("custody_status", ""))
        if manifest_status == ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_FORBIDDEN_SECRET_DETECTED:
            findings.append(_finding("secret_value_present", "custody manifest reports forbidden secret material"))
        elif manifest_status == ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_SECRET_REFERENCE_DETECTED:
            findings.append(_finding("secret_reference_present", "custody manifest reports forbidden secret references"))
        elif manifest_status == ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_ENV_ACCESS_DETECTED:
            findings.append(_finding("env_access_allowed", "custody manifest reports environment secret access"))
        elif manifest_status == ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_FILE_ACCESS_DETECTED:
            findings.append(_finding("file_access_allowed", "custody manifest reports file secret access"))
        elif manifest_status == ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_VAULT_ACCESS_DETECTED:
            findings.append(_finding("vault_access_allowed", "custody manifest reports vault/keychain/cloud-secret access"))
        elif manifest_status == ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_ENDPOINT_DETECTED:
            findings.append(_finding("endpoint_material_present", "custody manifest reports endpoint material"))
        elif manifest_status == ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_CLIENT_DETECTED:
            findings.append(_finding("provider_client_material_present", "custody manifest reports provider-client material"))
        elif manifest_status == ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_NETWORK_DETECTED:
            findings.append(_finding("network_access_allowed", "custody manifest reports network access"))
        elif manifest_status == ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_RUNTIME_AUTHORITY_DETECTED:
            findings.append(_finding("runtime_authority_detected", "custody manifest reports runtime authority"))
        elif manifest_status == ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_INCOMPLETE:
            findings.append(_finding("missing_required_evidence", "custody manifest reports incomplete evidence"))
        elif manifest_status == ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_INVALID:
            findings.append(_finding("invalid_custody_kind", "custody manifest is invalid"))
    requested_kind = str(requested_custody_kind)
    if requested_kind in _FORBIDDEN_KINDS:
        findings.append(_finding("forbidden_custody_kind", f"{requested_kind} is forbidden in Phase 92"))
    elif requested_kind not in _ALLOWED_KINDS:
        findings.append(_finding("invalid_custody_kind", "unknown requested custody kind is forbidden"))
    requested_flags = {
        "requested_secret_resolution": requested_secret_resolution,
        "requested_env_access": requested_env_access,
        "requested_file_access": requested_file_access,
        "requested_vault_access": requested_vault_access,
        "requested_keychain_access": requested_keychain_access,
        "requested_cloud_secret_access": requested_cloud_secret_access,
        "requested_endpoint_material": requested_endpoint_material,
        "requested_provider_client_material": requested_provider_client_material,
        "requested_network_access": requested_network_access,
    }
    for field_name, value in requested_flags.items():
        if bool(value):
            findings.append(_finding(field_name, f"{field_name} is forbidden in Phase 92"))
    no_flags = {
        "no_secret_material": no_secret_material,
        "no_secret_references": no_secret_references,
        "no_secret_resolution": no_secret_resolution,
        "no_env_access": no_env_access,
        "no_file_access": no_file_access,
        "no_vault_access": no_vault_access,
        "no_keychain_access": no_keychain_access,
        "no_cloud_secret_access": no_cloud_secret_access,
        "no_endpoint": no_endpoint,
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
        "no_secret_material": "secret_material_requested",
        "no_secret_references": "secret_reference_requested",
        "no_secret_resolution": "secret_resolution_not_negated",
        "no_env_access": "env_access_not_negated",
        "no_file_access": "file_access_not_negated",
        "no_vault_access": "vault_access_not_negated",
        "no_keychain_access": "keychain_access_not_negated",
        "no_cloud_secret_access": "cloud_secret_access_not_negated",
        "no_endpoint": "endpoint_not_negated",
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
    if registration:
        reg_digest = str(registration.get("registration_preflight_digest", ""))
        if reg_digest and compute_provider_transport_registration_preflight_digest(registration_preflight or {}) != reg_digest:
            findings.append(_finding("registration_preflight_digest_mismatch", "linked registration preflight digest mismatch"))
        if not provider_transport_registration_remains_forbidden(registration_preflight or {}):
            findings.append(_finding("registration_real_transport_detected", "linked Phase 91 registration preflight allows real transport"))
        if str(registration.get("registration_status", "")) not in {
            ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_NULL_ONLY_ALLOWED,
            ProviderTransportRegistrationStatus.TRANSPORT_REGISTRATION_DENIED,
        }:
            findings.append(_finding("registration_real_transport_detected", "linked Phase 91 registration preflight is not null-compatible metadata"))
    elif requested_registration and capability and not provider_transport_capability_is_null_only(capability_manifest or {}):
        findings.append(_finding("registration_real_transport_detected", "requested registration with non-null capability is forbidden"))
    for field_name in (
        "secret_resolution_allowed",
        "env_access_allowed",
        "file_access_allowed",
        "vault_access_allowed",
        "keychain_access_allowed",
        "cloud_secret_access_allowed",
        "endpoint_material_present",
        "provider_client_material_present",
        "network_access_allowed",
        "credential_runtime_authority",
    ):
        if manifest.get(field_name) is True:
            findings.append(_finding(field_name if field_name != "credential_runtime_authority" else "runtime_authority_detected", f"manifest {field_name} is forbidden"))
    if manifest.get("no_secret_material") is not True or manifest.get("secret_values_present") is True:
        findings.append(_finding("secret_value_present", "manifest contains or permits secret material"))
    if manifest.get("secret_references_present") is True:
        findings.append(_finding("secret_reference_present", "manifest contains secret references"))
    marker_failures = [field_name for field_name in _MANIFEST_MARKER_FIELDS if manifest and manifest.get(field_name) is not True]
    for field_name in marker_failures:
        findings.append(_finding("custody_marker_missing", f"manifest {field_name} must be true"))
    findings.extend(_secret_pattern_findings(requested_kind, metadata_evidence))
    findings.extend(_runtime_marker_findings(metadata_evidence))
    clean = bool(
        manifest
        and not findings
        and str(manifest.get("custody_status", "")) == ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_NO_SECRETS
        and requested_kind in _ALLOWED_KINDS
        and all(bool(value) is True for value in no_flags.values())
        and not any(bool(value) for value in requested_flags.values())
    )
    status = _preflight_status_for_findings(findings, str(manifest.get("custody_status", "")), clean)
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "credential custody preflight allows only no-secret metadata compatibility and still forbids credential use, secret resolution, endpoints, provider clients, network egress, model calls, and runtime side effects"
    preflight = ProviderCredentialCustodyPreflight(
        custody_preflight_id="",
        custody_preflight_status=status,
        custody_manifest_id=str(manifest.get("custody_manifest_id", "")),
        custody_status=str(manifest.get("custody_status", "")),
        custody_digest=str(manifest.get("custody_digest", "")),
        capability_manifest_id=str(capability.get("capability_manifest_id", "")),
        capability_digest=str(capability.get("capability_digest", "")),
        registration_preflight_id=str(registration.get("registration_preflight_id", "")),
        registration_preflight_digest=str(registration.get("registration_preflight_digest", "")),
        requested_custody_kind=requested_kind,
        requested_registration=bool(requested_registration),
        custody_allowed=clean,
        secret_material_allowed=False,
        secret_reference_allowed=False,
        secret_resolution_allowed=False,
        env_access_allowed=False,
        file_access_allowed=False,
        vault_access_allowed=False,
        keychain_access_allowed=False,
        cloud_secret_access_allowed=False,
        endpoint_material_allowed=False,
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
        custody_gaps=tuple(manifest.get("custody_gaps", ())) if manifest else _default_gaps(),
        rationale=rationale[:1000],
        custody_preflight_digest="",
        internal_only=bool(internal_only),
        **{key: bool(value) for key, value in no_flags.items()},
    )
    digest = compute_provider_credential_custody_preflight_digest(preflight)
    return replace(preflight, custody_preflight_id=f"provider-credential-custody-preflight:{digest[:16]}", custody_preflight_digest=digest)


def provider_credential_custody_contains_no_secrets(manifest: ProviderCredentialCustodyManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data.get("custody_status") == ProviderCredentialCustodyStatus.CREDENTIAL_CUSTODY_NO_SECRETS and data.get("no_secret_material") is True and data.get("secret_values_present") is False and data.get("secret_references_present") is False)


def provider_credential_custody_forbids_secret_resolution(subject: ProviderCredentialCustodyManifest | ProviderCredentialCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(data.get("secret_resolution_allowed") is False and data.get("secret_resolution_forbidden") is True and data.get("does_not_read_environment") is True and data.get("does_not_read_files") is True)


def provider_credential_custody_forbids_env_access(subject: ProviderCredentialCustodyManifest | ProviderCredentialCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(data.get("env_access_allowed") is False and data.get("env_secret_access_forbidden") is True and data.get("does_not_read_environment") is True)


def provider_credential_custody_forbids_file_access(subject: ProviderCredentialCustodyManifest | ProviderCredentialCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(data.get("file_access_allowed") is False and data.get("file_secret_access_forbidden") is True and data.get("does_not_read_files") is True)


def provider_credential_custody_forbids_vault_access(subject: ProviderCredentialCustodyManifest | ProviderCredentialCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(data.get("vault_access_allowed") is False and data.get("keychain_access_allowed") is False and data.get("cloud_secret_access_allowed") is False and data.get("vault_secret_access_forbidden") is True and data.get("keychain_secret_access_forbidden") is True and data.get("cloud_secret_access_forbidden") is True)


def provider_credential_custody_has_no_network(subject: ProviderCredentialCustodyManifest | ProviderCredentialCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(data.get("network_access_allowed") is False and data.get("network_access_forbidden") is True and data.get("does_not_make_network_calls") is True and data.get("does_not_send_to_provider") is True)


def provider_credential_custody_has_no_endpoint(subject: ProviderCredentialCustodyManifest | ProviderCredentialCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    present_or_allowed = data.get("endpoint_material_present", data.get("endpoint_material_allowed", False))
    return bool(present_or_allowed is False and data.get("endpoint_material_forbidden") is True)


def provider_credential_custody_has_no_provider_client(subject: ProviderCredentialCustodyManifest | ProviderCredentialCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    present_or_allowed = data.get("provider_client_material_present", data.get("provider_client_material_allowed", False))
    return bool(present_or_allowed is False and data.get("provider_client_material_forbidden") is True)


def provider_credential_custody_has_no_runtime_authority(subject: ProviderCredentialCustodyManifest | ProviderCredentialCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(subject)
    return bool(data.get("credential_runtime_authority", False) is False and data.get("does_not_execute_or_route_work") is True and data.get("does_not_admit_work") is True and data.get("does_not_retrieve_memory") is True and data.get("does_not_write_memory") is True and data.get("does_not_commit_retention") is True)


def provider_credential_preflight_denies_real_credentials(preflight: ProviderCredentialCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(data.get("custody_preflight_status") != ProviderCredentialCustodyPreflightStatus.CREDENTIAL_PREFLIGHT_NO_SECRETS_ALLOWED and data.get("secret_material_allowed") is False and data.get("secret_reference_allowed") is False and data.get("credential_use_forbidden") is True)


def provider_credential_preflight_remains_metadata_only(preflight: ProviderCredentialCustodyPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(data.get("provider_credential_custody_preflight_only") is True and data.get("custody_allowed") is True and data.get("no_secret_material") is True and provider_credential_custody_has_no_network(data) and provider_credential_custody_has_no_runtime_authority(data))


def explain_provider_credential_custody_findings(subject: ProviderCredentialCustodyManifest | ProviderCredentialCustodyPreflight | Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(f"{item.get('severity', 'blocker')}:{item.get('code', '')}:{item.get('detail', '')}" for item in _mapping(subject).get("findings", ()) if isinstance(item, Mapping)) or tuple(
        f"{finding.severity}:{finding.code}:{finding.detail}" for finding in getattr(subject, "findings", ())
    )


def summarize_provider_credential_custody_preflight(preflight: ProviderCredentialCustodyPreflight | Mapping[str, Any]) -> dict[str, Any]:
    data = _mapping(preflight)
    return {
        "custody_preflight_status": data.get("custody_preflight_status", ""),
        "custody_allowed": data.get("custody_allowed", False),
        "requested_custody_kind": data.get("requested_custody_kind", ""),
        "requested_registration": data.get("requested_registration", False),
        "custody_manifest_id": data.get("custody_manifest_id", ""),
        "capability_manifest_id": data.get("capability_manifest_id", ""),
        "registration_preflight_id": data.get("registration_preflight_id", ""),
        "finding_codes": tuple(item.get("code", "") for item in data.get("findings", ()) if isinstance(item, Mapping)),
        "warning_codes": tuple(data.get("warnings", ())),
        "custody_preflight_digest": data.get("custody_preflight_digest", ""),
    }
