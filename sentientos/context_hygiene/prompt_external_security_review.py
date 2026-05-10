from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_provider_client_custody import (
    ProviderClientCustodyManifest,
    compute_provider_client_custody_digest,
)
from sentientos.context_hygiene.prompt_provider_credential_custody import (
    ProviderCredentialCustodyManifest,
    compute_provider_credential_custody_digest,
)
from sentientos.context_hygiene.prompt_provider_endpoint_custody import (
    ProviderEndpointCustodyManifest,
    compute_provider_endpoint_custody_digest,
)
from sentientos.context_hygiene.prompt_provider_invocation_denial_review import (
    ProviderInvocationDenialReviewDecision,
    ProviderInvocationDenialReviewReceipt,
    ProviderInvocationDenialReviewStatus,
    compute_provider_invocation_denial_review_digest,
    provider_invocation_denial_review_affirms_forbidden_invocation,
    provider_invocation_denial_review_approves_future_denial_audit_gate,
    provider_invocation_denial_review_approves_future_external_security_review_gate,
    provider_invocation_denial_review_attempts_forbidden_invocation_override,
    provider_invocation_denial_review_has_no_clients,
    provider_invocation_denial_review_has_no_credentials,
    provider_invocation_denial_review_has_no_endpoints,
    provider_invocation_denial_review_has_no_network,
    provider_invocation_denial_review_has_no_runtime_authority,
    provider_invocation_denial_review_remains_metadata_only,
)
from sentientos.context_hygiene.prompt_provider_invocation_readiness import (
    ProviderInvocationReadinessManifest,
    ProviderInvocationReadinessPreflight,
    compute_provider_invocation_readiness_digest,
    compute_provider_invocation_readiness_preflight_digest,
    provider_invocation_preflight_remains_metadata_only,
    provider_invocation_readiness_forbids_invocation,
)
from sentientos.context_hygiene.prompt_provider_transport_capability import (
    ProviderTransportCapabilityManifest,
    compute_provider_transport_capability_digest,
)


class ExternalSecurityReviewPacketStatus:
    EXTERNAL_SECURITY_REVIEW_PACKET_READY = "external_security_review_packet_ready"
    EXTERNAL_SECURITY_REVIEW_PACKET_READY_WITH_CONDITIONS = "external_security_review_packet_ready_with_conditions"
    EXTERNAL_SECURITY_REVIEW_PACKET_BLOCKED = "external_security_review_packet_blocked"
    EXTERNAL_SECURITY_REVIEW_PACKET_INVALID_INPUT = "external_security_review_packet_invalid_input"
    EXTERNAL_SECURITY_REVIEW_PACKET_MISSING_DENIAL_REVIEW = "external_security_review_packet_missing_denial_review"
    EXTERNAL_SECURITY_REVIEW_PACKET_DENIAL_NOT_AFFIRMED = "external_security_review_packet_denial_not_affirmed"
    EXTERNAL_SECURITY_REVIEW_PACKET_SENSITIVE_MATERIAL_DETECTED = "external_security_review_packet_sensitive_material_detected"
    EXTERNAL_SECURITY_REVIEW_PACKET_RUNTIME_AUTHORITY_DETECTED = "external_security_review_packet_runtime_authority_detected"
    EXTERNAL_SECURITY_REVIEW_PACKET_INVOCATION_OVERRIDE_DETECTED = "external_security_review_packet_invocation_override_detected"


class ExternalSecurityReviewScope:
    EXTERNAL_SECURITY_REVIEW_METADATA_PACKET = "external_security_review_metadata_packet"
    INVOCATION_DENIAL_AUDIT_PACKET = "invocation_denial_audit_packet"
    INTERNAL_SECURITY_REVIEW_PACKET = "internal_security_review_packet"
    EXTERNAL_USER_VISIBLE_FORBIDDEN = "external_user_visible_forbidden"
    PROVIDER_SUBMISSION_FORBIDDEN = "provider_submission_forbidden"
    NETWORK_EGRESS_FORBIDDEN = "network_egress_forbidden"
    TOOL_OR_ACTION_FORBIDDEN = "tool_or_action_forbidden"


@dataclass(frozen=True)
class ExternalSecurityReviewFindingSummary:
    code: str
    category: str
    severity: str = "blocker"
    count: int = 1


@dataclass(frozen=True)
class ExternalSecurityReviewConstraintSummary:
    code: str
    category: str
    required: bool = True


@dataclass(frozen=True)
class ExternalSecurityReviewGapSummary:
    code: str
    category: str
    count: int = 1


@dataclass(frozen=True)
class ExternalSecurityReviewEvidenceLink:
    artifact_kind: str
    artifact_id: str
    artifact_status: str
    artifact_digest: str
    included: bool = True
    redacted: bool = False
    reason_code: str = "digest_only_metadata_link"


@dataclass(frozen=True)
class ExternalSecurityReviewRedactionSummary:
    prompt_text_removed: int = 0
    raw_payloads_removed: int = 0
    secrets_removed: int = 0
    endpoints_removed: int = 0
    clients_removed: int = 0
    network_handles_removed: int = 0
    runtime_handles_removed: int = 0
    provider_params_removed: int = 0
    tool_schemas_removed: int = 0
    hidden_chain_of_thought_removed: int = 0


@dataclass(frozen=True)
class ExternalSecurityReviewAuditChain:
    invocation_denial_review_receipt_id: str = ""
    invocation_denial_review_digest: str = ""
    readiness_id: str = ""
    readiness_digest: str = ""
    readiness_preflight_id: str = ""
    readiness_preflight_digest: str = ""
    capability_manifest_id: str = ""
    capability_manifest_digest: str = ""
    credential_custody_manifest_id: str = ""
    credential_custody_manifest_digest: str = ""
    endpoint_custody_manifest_id: str = ""
    endpoint_custody_manifest_digest: str = ""
    client_custody_manifest_id: str = ""
    client_custody_manifest_digest: str = ""
    complete: bool = False
    missing: tuple[str, ...] = field(default_factory=tuple)
    mismatches: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExternalSecurityReviewPacket:
    external_review_packet_id: str
    packet_status: str
    review_scope: str
    reviewer_packet_ref: str
    invocation_denial_review_receipt_id: str
    invocation_denial_review_status: str
    invocation_denial_review_digest: str
    readiness_id: str = ""
    readiness_status: str = ""
    readiness_digest: str = ""
    readiness_preflight_id: str = ""
    readiness_preflight_status: str = ""
    readiness_preflight_digest: str = ""
    capability_manifest_id: str = ""
    capability_manifest_digest: str = ""
    capability_manifest_status: str = ""
    credential_custody_manifest_id: str = ""
    credential_custody_manifest_digest: str = ""
    credential_custody_manifest_status: str = ""
    endpoint_custody_manifest_id: str = ""
    endpoint_custody_manifest_digest: str = ""
    endpoint_custody_manifest_status: str = ""
    client_custody_manifest_id: str = ""
    client_custody_manifest_digest: str = ""
    client_custody_manifest_status: str = ""
    evidence_links: tuple[ExternalSecurityReviewEvidenceLink, ...] = field(default_factory=tuple)
    audit_chain: ExternalSecurityReviewAuditChain = field(default_factory=ExternalSecurityReviewAuditChain)
    digest_chain_complete: bool = False
    finding_summaries: tuple[ExternalSecurityReviewFindingSummary, ...] = field(default_factory=tuple)
    constraint_summaries: tuple[ExternalSecurityReviewConstraintSummary, ...] = field(default_factory=tuple)
    gap_summaries: tuple[ExternalSecurityReviewGapSummary, ...] = field(default_factory=tuple)
    redaction_summary: ExternalSecurityReviewRedactionSummary = field(default_factory=ExternalSecurityReviewRedactionSummary)
    invocation_denial_preserved: bool = True
    metadata_only: bool = True
    sensitive_material_included: bool = False
    prompt_text_included: bool = False
    raw_payloads_included: bool = False
    secrets_included: bool = False
    secret_references_included: bool = False
    endpoints_included: bool = False
    endpoint_references_included: bool = False
    clients_included: bool = False
    client_references_included: bool = False
    network_handles_included: bool = False
    runtime_handles_included: bool = False
    provider_params_included: bool = False
    tool_schemas_included: bool = False
    hidden_chain_of_thought_included: bool = False
    invocation_allowed: bool = False
    provider_send_allowed: bool = False
    network_allowed: bool = False
    credential_use_allowed: bool = False
    endpoint_use_allowed: bool = False
    client_use_allowed: bool = False
    provider_sdk_allowed: bool = False
    semantic_generation_allowed: bool = False
    tool_calls_allowed: bool = False
    memory_retrieval_allowed: bool = False
    memory_write_allowed: bool = False
    retention_allowed: bool = False
    action_execution_allowed: bool = False
    routing_allowed: bool = False
    findings: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    constraints: tuple[str, ...] = field(default_factory=tuple)
    rationale: str = ""
    external_review_packet_digest: str = ""
    external_security_review_packet_only: bool = True
    provider_invocation_forbidden: bool = True
    actual_provider_invocation_forbidden: bool = True
    no_prompt_text: bool = True
    no_raw_payloads: bool = True
    no_secret_material: bool = True
    no_endpoint_material: bool = True
    no_client_material: bool = True
    no_network_handles: bool = True
    no_runtime_handles: bool = True
    no_provider_params: bool = True
    no_tool_schemas: bool = True
    no_hidden_chain_of_thought: bool = True
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


_ALLOWED_SCOPES = frozenset(
    {
        ExternalSecurityReviewScope.EXTERNAL_SECURITY_REVIEW_METADATA_PACKET,
        ExternalSecurityReviewScope.INVOCATION_DENIAL_AUDIT_PACKET,
        ExternalSecurityReviewScope.INTERNAL_SECURITY_REVIEW_PACKET,
    }
)
_FORBIDDEN_SCOPES = frozenset(
    {
        ExternalSecurityReviewScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
        ExternalSecurityReviewScope.PROVIDER_SUBMISSION_FORBIDDEN,
        ExternalSecurityReviewScope.NETWORK_EGRESS_FORBIDDEN,
        ExternalSecurityReviewScope.TOOL_OR_ACTION_FORBIDDEN,
    }
)
_READY_REVIEW_STATUSES = frozenset(
    {
        ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_ACCEPTED,
        ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_ACCEPTED_WITH_CONDITIONS,
    }
)
_ALLOWANCE_FIELDS = (
    "invocation_allowed",
    "provider_send_allowed",
    "network_allowed",
    "network_access_allowed",
    "credential_use_allowed",
    "endpoint_use_allowed",
    "client_use_allowed",
    "provider_sdk_allowed",
    "semantic_generation_allowed",
    "tool_calls_allowed",
    "memory_retrieval_allowed",
    "memory_write_allowed",
    "retention_allowed",
    "action_execution_allowed",
    "routing_allowed",
    "dns_allowed",
    "socket_allowed",
    "http_allowed",
)
_MARKER_FIELDS = (
    "external_security_review_packet_only",
    "metadata_only",
    "invocation_denial_preserved",
    "provider_invocation_forbidden",
    "actual_provider_invocation_forbidden",
    "no_prompt_text",
    "no_raw_payloads",
    "no_secret_material",
    "no_endpoint_material",
    "no_client_material",
    "no_network_handles",
    "no_runtime_handles",
    "no_provider_params",
    "no_tool_schemas",
    "no_hidden_chain_of_thought",
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
_SENSITIVE_INCLUDED_FIELDS = (
    "sensitive_material_included",
    "prompt_text_included",
    "raw_payloads_included",
    "secrets_included",
    "secret_references_included",
    "endpoints_included",
    "endpoint_references_included",
    "clients_included",
    "client_references_included",
    "network_handles_included",
    "runtime_handles_included",
    "provider_params_included",
    "tool_schemas_included",
    "hidden_chain_of_thought_included",
)

_MARKER_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("prompt_text", ("prompt_text", "internal_candidate_text", "synthetic_prompt_text", "dry_run_prompt_text", "final_prompt_text", "assembled_prompt", "system_prompt", "developer_prompt")),
    ("hidden_chain_of_thought", ("chain_of_thought", "hidden reasoning", "scratchpad")),
    ("secrets", ("api_key", "bearer", "token", "secret", "password", "private_key", "authorization")),
    ("endpoints", ("https://", "http://", "endpoint", "base_url", "host", "port", "dns", "resolve")),
    ("clients", ("client", "session", "transport", "stream", "retry", "request builder", "sdk", "openai", "anthropic")),
    ("network_handles", ("network handle", "socket", "http client", "stream handle")),
    ("runtime_handles", ("runtime handle", "raw_payload", "tool schema", "function call", "action", "retention", "routing", "memory write")),
    ("provider_params", ("provider params", "model params", "llm params")),
    ("tool_schemas", ("tool schema", "function call")),
    ("provider_invocation", ("invoke", "send_to_provider", "chat.completions", "completion")),
)
_NEGATIVE_TOKENS = (
    "no_",
    "no ",
    "forbidden",
    "does_not_",
    "does not",
    "metadata_only",
    "denied",
    "not_invocable",
    "not invocable",
    "_included=false",
    "_allowed=false",
    "allowed false",
    "included false",
)
_REDACTION_FIELD_BY_CATEGORY = {
    "prompt_text": "prompt_text_removed",
    "hidden_chain_of_thought": "hidden_chain_of_thought_removed",
    "secrets": "secrets_removed",
    "endpoints": "endpoints_removed",
    "clients": "clients_removed",
    "network_handles": "network_handles_removed",
    "runtime_handles": "runtime_handles_removed",
    "provider_params": "provider_params_removed",
    "tool_schemas": "tool_schemas_removed",
    "provider_invocation": "runtime_handles_removed",
}
_INCLUDED_FIELD_BY_CATEGORY = {
    "prompt_text": "prompt_text_included",
    "hidden_chain_of_thought": "hidden_chain_of_thought_included",
    "secrets": "secrets_included",
    "endpoints": "endpoints_included",
    "clients": "clients_included",
    "network_handles": "network_handles_included",
    "runtime_handles": "runtime_handles_included",
    "provider_params": "provider_params_included",
    "tool_schemas": "tool_schemas_included",
    "provider_invocation": "runtime_handles_included",
}


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


def _digest_payload(packet: ExternalSecurityReviewPacket | Mapping[str, Any]) -> Mapping[str, Any]:
    data = dict(_mapping(packet))
    data.pop("external_review_packet_id", None)
    data.pop("external_review_packet_digest", None)
    return data


def compute_external_security_review_packet_digest(packet: ExternalSecurityReviewPacket | Mapping[str, Any]) -> str:
    return _stable_digest(_digest_payload(packet))


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


def _safe_code(prefix: str, text: str) -> str:
    normalized = "_".join(str(text).lower().strip().replace(":", " ").split())
    normalized = "".join(char if char.isalnum() or char == "_" else "_" for char in normalized).strip("_")
    if normalized:
        return f"{prefix}:{normalized[:96]}"
    digest = hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"


def _string_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if _is_dataclass_instance(value):
        return _string_values(asdict(value))
    if isinstance(value, Mapping):
        values: list[str] = []
        for item in value.values():
            values.extend(_string_values(item))
        return tuple(values)
    if isinstance(value, (tuple, list, set, frozenset)):
        values = []
        for item in value:
            values.extend(_string_values(item))
        return tuple(values)
    return ()


def _is_negative_context(text: str, index: int, marker: str) -> bool:
    window = text[max(0, index - 64) : index + len(marker) + 64]
    return any(token in window for token in _NEGATIVE_TOKENS)


def _scan_sensitive_categories(*values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for raw in values:
        for text_value in _string_values(raw):
            text = str(text_value).lower().replace('"', " ")
            for category, markers in _MARKER_CATEGORIES:
                for marker in markers:
                    index = text.find(marker)
                    while index >= 0:
                        if not _is_negative_context(text, index, marker):
                            counts[category] = counts.get(category, 0) + 1
                        index = text.find(marker, index + 1)
    return counts


def _redaction_summary(counts: Mapping[str, int]) -> ExternalSecurityReviewRedactionSummary:
    kwargs = {field_name: 0 for field_name in _REDACTION_FIELD_BY_CATEGORY.values()}
    for category, count in counts.items():
        field_name = _REDACTION_FIELD_BY_CATEGORY.get(category)
        if field_name:
            kwargs[field_name] = int(kwargs.get(field_name, 0)) + int(count)
    return ExternalSecurityReviewRedactionSummary(**kwargs)


def _safe_summary(items: Any, prefix: str, cls: type[ExternalSecurityReviewFindingSummary] | type[ExternalSecurityReviewGapSummary]) -> tuple[Any, ...]:
    summaries: list[Any] = []
    for item in items or ():
        data = _mapping(item)
        code = str(data.get("code", "")) if data else str(item)
        severity = str(data.get("severity", "blocker")) if data else "blocker"
        if not code:
            code = _safe_code(prefix, str(item))
        category = code.split(":", 1)[0].split("_", 1)[0] or prefix
        if cls is ExternalSecurityReviewFindingSummary:
            summaries.append(ExternalSecurityReviewFindingSummary(code=_safe_code(prefix, code), category=category, severity=severity, count=1))
        else:
            summaries.append(ExternalSecurityReviewGapSummary(code=_safe_code(prefix, code), category=category, count=1))
    return tuple(summaries)


def _constraint_summary(items: Any) -> tuple[ExternalSecurityReviewConstraintSummary, ...]:
    summaries: list[ExternalSecurityReviewConstraintSummary] = []
    for item in items or ():
        data = _mapping(item)
        code = str(data.get("code", "")) if data else str(item)
        required = bool(data.get("required", True)) if data else True
        if not code:
            code = _safe_code("constraint", str(item))
        summaries.append(ExternalSecurityReviewConstraintSummary(code=_safe_code("constraint", code), category="constraint", required=required))
    return tuple(summaries)


def _artifact_digest(artifact: Any, digest_field: str, compute: Any) -> str:
    data = _mapping(artifact)
    if not data:
        return ""
    declared = str(data.get(digest_field, ""))
    if declared:
        return declared
    try:
        return str(compute(artifact))
    except Exception:
        return ""


def _artifact_link(kind: str, artifact: Any, id_field: str, status_field: str, digest_field: str, compute: Any) -> ExternalSecurityReviewEvidenceLink | None:
    data = _mapping(artifact)
    if not data:
        return None
    return ExternalSecurityReviewEvidenceLink(
        artifact_kind=kind,
        artifact_id=str(data.get(id_field, "")),
        artifact_status=str(data.get(status_field, "")),
        artifact_digest=_artifact_digest(artifact, digest_field, compute),
        included=True,
        redacted=False,
        reason_code="digest_only_metadata_link",
    )


def _build_evidence_links(
    denial_review_receipt: Any,
    readiness_manifest: Any,
    readiness_preflight: Any,
    capability_manifest: Any,
    credential_custody_manifest: Any,
    endpoint_custody_manifest: Any,
    client_custody_manifest: Any,
) -> tuple[ExternalSecurityReviewEvidenceLink, ...]:
    data = _mapping(denial_review_receipt)
    links: list[ExternalSecurityReviewEvidenceLink] = []
    if data:
        links.append(
            ExternalSecurityReviewEvidenceLink(
                artifact_kind="provider_invocation_denial_review_receipt",
                artifact_id=str(data.get("review_receipt_id", "")),
                artifact_status=str(data.get("review_status", "")),
                artifact_digest=_artifact_digest(denial_review_receipt, "review_digest", compute_provider_invocation_denial_review_digest),
                included=True,
                redacted=False,
                reason_code="phase96_denial_review_digest_only",
            )
        )
    optional_links = (
        _artifact_link("provider_invocation_readiness_manifest", readiness_manifest, "invocation_readiness_id", "readiness_status", "readiness_digest", compute_provider_invocation_readiness_digest),
        _artifact_link("provider_invocation_readiness_preflight", readiness_preflight, "invocation_preflight_id", "invocation_preflight_status", "invocation_preflight_digest", compute_provider_invocation_readiness_preflight_digest),
        _artifact_link("provider_transport_capability_manifest", capability_manifest, "capability_manifest_id", "capability_status", "capability_digest", compute_provider_transport_capability_digest),
        _artifact_link("provider_credential_custody_manifest", credential_custody_manifest, "custody_manifest_id", "custody_status", "custody_digest", compute_provider_credential_custody_digest),
        _artifact_link("provider_endpoint_custody_manifest", endpoint_custody_manifest, "endpoint_manifest_id", "endpoint_status", "endpoint_digest", compute_provider_endpoint_custody_digest),
        _artifact_link("provider_client_custody_manifest", client_custody_manifest, "client_manifest_id", "client_status", "client_digest", compute_provider_client_custody_digest),
    )
    links.extend(link for link in optional_links if link is not None)
    return tuple(links)


def _audit_chain(receipt: Any, readiness: Any, preflight: Any, capability: Any, credential: Any, endpoint: Any, client: Any, include_digest_chain: bool) -> ExternalSecurityReviewAuditChain:
    r = _mapping(receipt)
    readiness_data = _mapping(readiness)
    preflight_data = _mapping(preflight)
    capability_data = _mapping(capability)
    credential_data = _mapping(credential)
    endpoint_data = _mapping(endpoint)
    client_data = _mapping(client)
    missing: list[str] = []
    mismatches: list[str] = []
    if not r:
        missing.append("provider_invocation_denial_review_receipt")
    review_digest = _artifact_digest(receipt, "review_digest", compute_provider_invocation_denial_review_digest)
    if r and str(r.get("review_digest", "")) and review_digest != str(r.get("review_digest", "")):
        mismatches.append("invocation_denial_review_digest")
    readiness_digest = _artifact_digest(readiness, "readiness_digest", compute_provider_invocation_readiness_digest)
    preflight_digest = _artifact_digest(preflight, "invocation_preflight_digest", compute_provider_invocation_readiness_preflight_digest)
    capability_digest = _artifact_digest(capability, "capability_digest", compute_provider_transport_capability_digest)
    credential_digest = _artifact_digest(credential, "custody_digest", compute_provider_credential_custody_digest)
    endpoint_digest = _artifact_digest(endpoint, "endpoint_digest", compute_provider_endpoint_custody_digest)
    client_digest = _artifact_digest(client, "client_digest", compute_provider_client_custody_digest)
    if readiness_data and r and str(r.get("readiness_digest", "")) != str(readiness_data.get("readiness_digest", "")):
        mismatches.append("readiness_digest_link")
    if preflight_data and r and str(r.get("readiness_preflight_digest", "")) != str(preflight_data.get("invocation_preflight_digest", "")):
        mismatches.append("readiness_preflight_digest_link")
    complete = bool(r and not mismatches and (not include_digest_chain or bool(r.get("digest_chain_complete", False))))
    if include_digest_chain and r and not bool(r.get("digest_chain_complete", False)):
        missing.append("phase96_digest_chain_complete")
    return ExternalSecurityReviewAuditChain(
        invocation_denial_review_receipt_id=str(r.get("review_receipt_id", "")),
        invocation_denial_review_digest=review_digest or str(r.get("review_digest", "")),
        readiness_id=str(readiness_data.get("invocation_readiness_id", r.get("readiness_id", ""))),
        readiness_digest=readiness_digest or str(r.get("readiness_digest", "")),
        readiness_preflight_id=str(preflight_data.get("invocation_preflight_id", r.get("readiness_preflight_id", ""))),
        readiness_preflight_digest=preflight_digest or str(r.get("readiness_preflight_digest", "")),
        capability_manifest_id=str(capability_data.get("capability_manifest_id", "")),
        capability_manifest_digest=capability_digest,
        credential_custody_manifest_id=str(credential_data.get("custody_manifest_id", "")),
        credential_custody_manifest_digest=credential_digest,
        endpoint_custody_manifest_id=str(endpoint_data.get("endpoint_manifest_id", "")),
        endpoint_custody_manifest_digest=endpoint_digest,
        client_custody_manifest_id=str(client_data.get("client_manifest_id", "")),
        client_custody_manifest_digest=client_digest,
        complete=complete,
        missing=_dedupe(missing),
        mismatches=_dedupe(mismatches),
    )


def _denial_affirmed(receipt: Any) -> bool:
    data = _mapping(receipt)
    if not data:
        return False
    decision = str(data.get("decision", ""))
    return bool(
        provider_invocation_denial_review_affirms_forbidden_invocation(receipt)
        or provider_invocation_denial_review_approves_future_external_security_review_gate(receipt)
        or provider_invocation_denial_review_approves_future_denial_audit_gate(receipt)
        or decision
        in {
            ProviderInvocationDenialReviewDecision.AFFIRM_INVOCATION_FORBIDDEN,
            ProviderInvocationDenialReviewDecision.AFFIRM_METADATA_ONLY_NOT_INVOCABLE,
            ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_EXTERNAL_SECURITY_REVIEW_GATE,
            ProviderInvocationDenialReviewDecision.APPROVE_FUTURE_INVOCATION_DENIAL_AUDIT_GATE,
            ProviderInvocationDenialReviewDecision.APPROVE_WITH_CONDITIONS,
        }
    )


def _status(
    receipt: Any,
    scope: str,
    sensitive_counts: Mapping[str, int],
    audit: ExternalSecurityReviewAuditChain,
    include_digest_chain: bool,
) -> str:
    data = _mapping(receipt)
    if not data:
        return ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_MISSING_DENIAL_REVIEW
    if str(scope) not in _ALLOWED_SCOPES:
        return ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_BLOCKED
    review_status = str(data.get("review_status", ""))
    if review_status == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_FORBIDDEN_INVOCATION_OVERRIDE_ATTEMPTED or provider_invocation_denial_review_attempts_forbidden_invocation_override(receipt):
        return ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_INVOCATION_OVERRIDE_DETECTED
    if review_status in {
        ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_REJECTED,
        ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_EXPIRED,
        ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_INVALID,
    }:
        return ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_INVALID_INPUT
    if review_status not in _READY_REVIEW_STATUSES:
        return ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_INVALID_INPUT
    if bool(data.get("expired", False)):
        return ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_INVALID_INPUT
    if not _denial_affirmed(receipt):
        return ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_DENIAL_NOT_AFFIRMED
    if not provider_invocation_denial_review_has_no_credentials(receipt) or not provider_invocation_denial_review_has_no_endpoints(receipt) or not provider_invocation_denial_review_has_no_clients(receipt) or not provider_invocation_denial_review_has_no_network(receipt):
        return ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_SENSITIVE_MATERIAL_DETECTED
    if not provider_invocation_denial_review_has_no_runtime_authority(receipt) or any(bool(data.get(field_name, False)) for field_name in _ALLOWANCE_FIELDS):
        return ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_RUNTIME_AUTHORITY_DETECTED
    if sensitive_counts:
        if any(category in sensitive_counts for category in ("prompt_text", "hidden_chain_of_thought", "secrets", "endpoints", "clients", "network_handles", "provider_params", "tool_schemas")):
            return ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_SENSITIVE_MATERIAL_DETECTED
        return ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_RUNTIME_AUTHORITY_DETECTED
    if include_digest_chain and not audit.complete:
        return ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_INVALID_INPUT
    if review_status == ProviderInvocationDenialReviewStatus.INVOCATION_DENIAL_REVIEW_ACCEPTED_WITH_CONDITIONS or scope == ExternalSecurityReviewScope.INVOCATION_DENIAL_AUDIT_PACKET:
        return ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_READY_WITH_CONDITIONS
    return ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_READY


def build_external_security_review_packet(
    denial_review_receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any] | None,
    *,
    readiness_manifest: ProviderInvocationReadinessManifest | Mapping[str, Any] | None = None,
    readiness_preflight: ProviderInvocationReadinessPreflight | Mapping[str, Any] | None = None,
    capability_manifest: ProviderTransportCapabilityManifest | Mapping[str, Any] | None = None,
    credential_custody_manifest: ProviderCredentialCustodyManifest | Mapping[str, Any] | None = None,
    endpoint_custody_manifest: ProviderEndpointCustodyManifest | Mapping[str, Any] | None = None,
    client_custody_manifest: ProviderClientCustodyManifest | Mapping[str, Any] | None = None,
    review_scope: str = ExternalSecurityReviewScope.EXTERNAL_SECURITY_REVIEW_METADATA_PACKET,
    reviewer_packet_ref: str = "",
    include_redacted_summaries: bool = True,
    include_findings: bool = True,
    include_constraints: bool = True,
    include_gaps: bool = True,
    include_digest_chain: bool = True,
) -> ExternalSecurityReviewPacket:
    receipt_data = _mapping(denial_review_receipt)
    readiness_data = _mapping(readiness_manifest)
    preflight_data = _mapping(readiness_preflight)
    capability_data = _mapping(capability_manifest)
    credential_data = _mapping(credential_custody_manifest)
    endpoint_data = _mapping(endpoint_custody_manifest)
    client_data = _mapping(client_custody_manifest)
    scan_counts = _scan_sensitive_categories(
        reviewer_packet_ref,
        review_scope,
        receipt_data.get("rationale", ""),
    )
    redaction = _redaction_summary(scan_counts) if include_redacted_summaries else ExternalSecurityReviewRedactionSummary()
    evidence_links = _build_evidence_links(denial_review_receipt, readiness_manifest, readiness_preflight, capability_manifest, credential_custody_manifest, endpoint_custody_manifest, client_custody_manifest)
    audit = _audit_chain(denial_review_receipt, readiness_manifest, readiness_preflight, capability_manifest, credential_custody_manifest, endpoint_custody_manifest, client_custody_manifest, include_digest_chain)
    status = _status(denial_review_receipt, str(review_scope), scan_counts, audit, include_digest_chain)
    findings: list[str] = []
    if status != ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_READY:
        findings.append(status)
    if str(review_scope) in _FORBIDDEN_SCOPES or str(review_scope) not in _ALLOWED_SCOPES:
        findings.append("review_scope_not_metadata_only")
    for category, count in sorted(scan_counts.items()):
        findings.append(f"sensitive_marker_redacted:{category}:{count}")
    if receipt_data and not _denial_affirmed(denial_review_receipt):
        findings.append("denial_review_does_not_affirm_invocation_forbidden")
    if include_digest_chain and not audit.complete:
        findings.append("digest_chain_incomplete")
    finding_summaries = _safe_summary(receipt_data.get("findings", ()), "finding", ExternalSecurityReviewFindingSummary) if include_findings else ()
    if scan_counts:
        finding_summaries = tuple(finding_summaries) + tuple(
            ExternalSecurityReviewFindingSummary(code=f"redacted:{category}", category=category, severity="blocker", count=count) for category, count in sorted(scan_counts.items())
        )
    constraint_summaries = _constraint_summary(receipt_data.get("constraints", ())) if include_constraints else ()
    gap_sources = _tuple_str(receipt_data.get("accepted_gap_codes", ())) + _tuple_str(receipt_data.get("rejected_gap_codes", ()))
    gap_summaries = _safe_summary(gap_sources, "gap", ExternalSecurityReviewGapSummary) if include_gaps else ()
    included_flags = {field_name: False for field_name in _SENSITIVE_INCLUDED_FIELDS}
    for category in scan_counts:
        field_name = _INCLUDED_FIELD_BY_CATEGORY.get(category)
        if field_name:
            included_flags[field_name] = True
    included_flags["sensitive_material_included"] = bool(scan_counts)
    allowance_flags = {
        "invocation_allowed": False,
        "provider_send_allowed": False,
        "network_allowed": False,
        "credential_use_allowed": False,
        "endpoint_use_allowed": False,
        "client_use_allowed": False,
        "provider_sdk_allowed": False,
        "semantic_generation_allowed": False,
        "tool_calls_allowed": False,
        "memory_retrieval_allowed": False,
        "memory_write_allowed": False,
        "retention_allowed": False,
        "action_execution_allowed": False,
        "routing_allowed": False,
    }
    for field_name in tuple(allowance_flags) + ("network_access_allowed",):
        if bool(receipt_data.get(field_name, False)):
            target = "network_allowed" if field_name == "network_access_allowed" else field_name
            if target in allowance_flags:
                allowance_flags[target] = True
    packet = ExternalSecurityReviewPacket(
        external_review_packet_id="",
        packet_status=status,
        review_scope=str(review_scope),
        reviewer_packet_ref=str(reviewer_packet_ref),
        invocation_denial_review_receipt_id=str(receipt_data.get("review_receipt_id", "")),
        invocation_denial_review_status=str(receipt_data.get("review_status", "")),
        invocation_denial_review_digest=audit.invocation_denial_review_digest or str(receipt_data.get("review_digest", "")),
        readiness_id=str(readiness_data.get("invocation_readiness_id", receipt_data.get("readiness_id", ""))),
        readiness_status=str(readiness_data.get("readiness_status", receipt_data.get("readiness_status", ""))),
        readiness_digest=audit.readiness_digest or str(receipt_data.get("readiness_digest", "")),
        readiness_preflight_id=str(preflight_data.get("invocation_preflight_id", receipt_data.get("readiness_preflight_id", ""))),
        readiness_preflight_status=str(preflight_data.get("invocation_preflight_status", receipt_data.get("readiness_preflight_status", ""))),
        readiness_preflight_digest=audit.readiness_preflight_digest or str(receipt_data.get("readiness_preflight_digest", "")),
        capability_manifest_id=str(capability_data.get("capability_manifest_id", "")),
        capability_manifest_digest=audit.capability_manifest_digest,
        capability_manifest_status=str(capability_data.get("capability_status", "")),
        credential_custody_manifest_id=str(credential_data.get("custody_manifest_id", "")),
        credential_custody_manifest_digest=audit.credential_custody_manifest_digest,
        credential_custody_manifest_status=str(credential_data.get("custody_status", "")),
        endpoint_custody_manifest_id=str(endpoint_data.get("endpoint_manifest_id", "")),
        endpoint_custody_manifest_digest=audit.endpoint_custody_manifest_digest,
        endpoint_custody_manifest_status=str(endpoint_data.get("endpoint_status", "")),
        client_custody_manifest_id=str(client_data.get("client_manifest_id", "")),
        client_custody_manifest_digest=audit.client_custody_manifest_digest,
        client_custody_manifest_status=str(client_data.get("client_status", "")),
        evidence_links=evidence_links,
        audit_chain=audit,
        digest_chain_complete=audit.complete,
        finding_summaries=tuple(finding_summaries),
        constraint_summaries=tuple(constraint_summaries),
        gap_summaries=tuple(gap_summaries),
        redaction_summary=redaction,
        invocation_denial_preserved=bool(receipt_data and provider_invocation_denial_review_remains_metadata_only(denial_review_receipt) and not any(allowance_flags.values())),
        metadata_only=not any(allowance_flags.values()),
        findings=_dedupe(findings),
        warnings=("external_security_review_packet_is_metadata_only", "provider_invocation_remains_forbidden", "evidence_links_are_digest_only"),
        constraints=("metadata_only", "digest_only_evidence_links", "provider_invocation_forbidden", "no_sensitive_runtime_material"),
        rationale="Metadata-only external security review packet for Phase 91-96 provider invocation denial evidence; not executable and not provider-sendable.",
        **included_flags,
        **allowance_flags,
    )
    if packet.packet_status not in {
        ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_READY,
        ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_READY_WITH_CONDITIONS,
    }:
        packet = replace(packet, metadata_only=not any(allowance_flags.values()) and not bool(scan_counts), invocation_denial_preserved=False if packet.packet_status == ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_INVOCATION_OVERRIDE_DETECTED else packet.invocation_denial_preserved)
    digest = compute_external_security_review_packet_digest(packet)
    return replace(packet, external_review_packet_id=f"external-security-review:{packet.invocation_denial_review_receipt_id or 'missing'}:{digest[:16]}", external_review_packet_digest=digest)


def validate_external_security_review_packet(packet: ExternalSecurityReviewPacket | Mapping[str, Any]) -> tuple[ExternalSecurityReviewFindingSummary, ...]:
    data = _mapping(packet)
    findings: list[ExternalSecurityReviewFindingSummary] = []
    if not data:
        return (ExternalSecurityReviewFindingSummary(code="packet_malformed", category="input", severity="blocker"),)
    if str(data.get("review_scope", "")) not in _ALLOWED_SCOPES:
        findings.append(ExternalSecurityReviewFindingSummary(code="review_scope_not_allowed", category="scope", severity="blocker"))
    for field_name in _MARKER_FIELDS:
        if data.get(field_name) is not True:
            findings.append(ExternalSecurityReviewFindingSummary(code=f"marker_not_true:{field_name}", category="marker", severity="blocker"))
    for field_name in _SENSITIVE_INCLUDED_FIELDS:
        if data.get(field_name) is not False:
            findings.append(ExternalSecurityReviewFindingSummary(code=f"sensitive_flag_true:{field_name}", category="sensitive_material", severity="blocker"))
    for field_name in _ALLOWANCE_FIELDS:
        if bool(data.get(field_name, False)):
            findings.append(ExternalSecurityReviewFindingSummary(code=f"allowance_flag_true:{field_name}", category="runtime_authority", severity="blocker"))
    if str(data.get("external_review_packet_digest", "")) != compute_external_security_review_packet_digest(packet):
        findings.append(ExternalSecurityReviewFindingSummary(code="packet_digest_mismatch", category="digest", severity="blocker"))
    for link in data.get("evidence_links", ()) or ():
        link_data = _mapping(link)
        if not link_data.get("artifact_digest") or any(key in link_data for key in ("artifact_body", "raw_payload", "prompt_text")):
            findings.append(ExternalSecurityReviewFindingSummary(code="evidence_link_not_digest_only", category="evidence", severity="blocker"))
    return tuple(findings)


def external_security_review_packet_is_metadata_only(packet: ExternalSecurityReviewPacket | Mapping[str, Any]) -> bool:
    data = _mapping(packet)
    return bool(data and data.get("metadata_only") is True and all(data.get(field_name) is False for field_name in _ALLOWANCE_FIELDS if field_name in data) and all(data.get(field_name) is False for field_name in _SENSITIVE_INCLUDED_FIELDS))


def external_security_review_packet_contains_no_prompt_text(packet: ExternalSecurityReviewPacket | Mapping[str, Any]) -> bool:
    data = _mapping(packet)
    return bool(data and data.get("no_prompt_text") is True and data.get("prompt_text_included") is False)


def external_security_review_packet_contains_no_secrets(packet: ExternalSecurityReviewPacket | Mapping[str, Any]) -> bool:
    data = _mapping(packet)
    return bool(data and data.get("no_secret_material") is True and data.get("secrets_included") is False and data.get("secret_references_included") is False)


def external_security_review_packet_contains_no_endpoints(packet: ExternalSecurityReviewPacket | Mapping[str, Any]) -> bool:
    data = _mapping(packet)
    return bool(data and data.get("no_endpoint_material") is True and data.get("endpoints_included") is False and data.get("endpoint_references_included") is False)


def external_security_review_packet_contains_no_clients(packet: ExternalSecurityReviewPacket | Mapping[str, Any]) -> bool:
    data = _mapping(packet)
    return bool(data and data.get("no_client_material") is True and data.get("clients_included") is False and data.get("client_references_included") is False)


def external_security_review_packet_contains_no_network_handles(packet: ExternalSecurityReviewPacket | Mapping[str, Any]) -> bool:
    data = _mapping(packet)
    return bool(data and data.get("no_network_handles") is True and data.get("network_handles_included") is False and data.get("network_allowed") is False)


def external_security_review_packet_contains_no_runtime_authority(packet: ExternalSecurityReviewPacket | Mapping[str, Any]) -> bool:
    data = _mapping(packet)
    if not data:
        return False
    return bool(
        data.get("no_runtime_handles") is True
        and data.get("runtime_handles_included") is False
        and data.get("provider_params_included") is False
        and data.get("tool_schemas_included") is False
        and all(data.get(field_name) is False for field_name in _ALLOWANCE_FIELDS if field_name in data)
    )


def external_security_review_packet_preserves_invocation_denial(packet: ExternalSecurityReviewPacket | Mapping[str, Any]) -> bool:
    data = _mapping(packet)
    return bool(data and data.get("invocation_denial_preserved") is True and data.get("provider_invocation_forbidden") is True and data.get("actual_provider_invocation_forbidden") is True and data.get("invocation_allowed") is False and data.get("provider_send_allowed") is False)


def external_security_review_packet_ready_for_review(packet: ExternalSecurityReviewPacket | Mapping[str, Any]) -> bool:
    data = _mapping(packet)
    return bool(
        data
        and str(data.get("packet_status", ""))
        in {
            ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_READY,
            ExternalSecurityReviewPacketStatus.EXTERNAL_SECURITY_REVIEW_PACKET_READY_WITH_CONDITIONS,
        }
        and external_security_review_packet_is_metadata_only(packet)
        and external_security_review_packet_preserves_invocation_denial(packet)
    )


def explain_external_security_review_packet_findings(packet: ExternalSecurityReviewPacket | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(packet)
    if not data:
        return ("packet_malformed",)
    validation_codes = tuple(finding.code for finding in validate_external_security_review_packet(packet))
    return _dedupe(_tuple_str(data.get("findings", ())) + validation_codes)


def summarize_external_security_review_packet(packet: ExternalSecurityReviewPacket | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(packet)
    return {
        "external_review_packet_id": data.get("external_review_packet_id", ""),
        "packet_status": data.get("packet_status", ""),
        "review_scope": data.get("review_scope", ""),
        "reviewer_packet_ref": data.get("reviewer_packet_ref", ""),
        "invocation_denial_review_receipt_id": data.get("invocation_denial_review_receipt_id", ""),
        "invocation_denial_review_digest": data.get("invocation_denial_review_digest", ""),
        "evidence_link_count": len(tuple(data.get("evidence_links", ()) or ())),
        "digest_chain_complete": data.get("digest_chain_complete", False),
        "metadata_only": data.get("metadata_only", False),
        "invocation_denial_preserved": data.get("invocation_denial_preserved", False),
        "provider_invocation_forbidden": data.get("provider_invocation_forbidden", False),
        "external_review_packet_digest": data.get("external_review_packet_digest", ""),
    }
