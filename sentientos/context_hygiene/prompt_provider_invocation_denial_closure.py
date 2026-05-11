from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_provider_invocation_denial_attestation import (
    ProviderInvocationDenialAttestation,
    ProviderInvocationDenialAttestationStatus,
    compute_provider_invocation_denial_attestation_digest,
    provider_invocation_denial_attestation_contains_no_clients,
    provider_invocation_denial_attestation_contains_no_endpoints,
    provider_invocation_denial_attestation_contains_no_network_handles,
    provider_invocation_denial_attestation_contains_no_prompt_text,
    provider_invocation_denial_attestation_contains_no_runtime_authority,
    provider_invocation_denial_attestation_contains_no_secrets,
    provider_invocation_denial_attestation_denies_invocation,
    provider_invocation_denial_attestation_does_not_export,
    provider_invocation_denial_attestation_is_metadata_only,
    provider_invocation_denial_attestation_ready,
)


class ProviderInvocationDenialClosureStatus:
    PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED = "provider_invocation_denial_closure_sealed"
    PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED_WITH_CONDITIONS = "provider_invocation_denial_closure_sealed_with_conditions"
    PROVIDER_INVOCATION_DENIAL_CLOSURE_BLOCKED = "provider_invocation_denial_closure_blocked"
    PROVIDER_INVOCATION_DENIAL_CLOSURE_INVALID = "provider_invocation_denial_closure_invalid"
    PROVIDER_INVOCATION_DENIAL_CLOSURE_MISSING_EVIDENCE = "provider_invocation_denial_closure_missing_evidence"
    PROVIDER_INVOCATION_DENIAL_CLOSURE_ATTESTATION_NOT_READY = "provider_invocation_denial_closure_attestation_not_ready"
    PROVIDER_INVOCATION_DENIAL_CLOSURE_SENSITIVE_MATERIAL_DETECTED = "provider_invocation_denial_closure_sensitive_material_detected"
    PROVIDER_INVOCATION_DENIAL_CLOSURE_RUNTIME_AUTHORITY_DETECTED = "provider_invocation_denial_closure_runtime_authority_detected"
    PROVIDER_INVOCATION_DENIAL_CLOSURE_OVERRIDE_DETECTED = "provider_invocation_denial_closure_override_detected"


class ProviderInvocationReleaseBlockerStatus:
    PROVIDER_INVOCATION_RELEASE_BLOCKED = "provider_invocation_release_blocked"
    PROVIDER_INVOCATION_RELEASE_BLOCKED_WITH_CONDITIONS = "provider_invocation_release_blocked_with_conditions"
    PROVIDER_INVOCATION_RELEASE_BLOCKER_INVALID = "provider_invocation_release_blocker_invalid"
    PROVIDER_INVOCATION_RELEASE_BLOCKER_MISSING_EVIDENCE = "provider_invocation_release_blocker_missing_evidence"
    PROVIDER_INVOCATION_RELEASE_UNBLOCKED_FORBIDDEN = "provider_invocation_release_unblocked_forbidden"


class ProviderInvocationDenialClosureScope:
    PROVIDER_INVOCATION_DENIAL_CLOSURE = "provider_invocation_denial_closure"
    PHASE100_CONTEXT_HYGIENE_CLOSURE = "phase100_context_hygiene_closure"
    PROVIDER_INVOCATION_RELEASE_BLOCKER = "provider_invocation_release_blocker"
    INTERNAL_SECURITY_CLOSURE_SUMMARY = "internal_security_closure_summary"
    PROVIDER_INVOCATION_RELEASE_APPROVAL_FORBIDDEN = "provider_invocation_release_approval_forbidden"
    PROVIDER_INVOCATION_APPROVAL_FORBIDDEN = "provider_invocation_approval_forbidden"
    PROVIDER_SUBMISSION_FORBIDDEN = "provider_submission_forbidden"
    NETWORK_EGRESS_FORBIDDEN = "network_egress_forbidden"
    EXPORT_DELIVERY_FORBIDDEN = "export_delivery_forbidden"
    TOOL_OR_ACTION_FORBIDDEN = "tool_or_action_forbidden"
    EXTERNAL_USER_VISIBLE_FORBIDDEN = "external_user_visible_forbidden"


@dataclass(frozen=True)
class ProviderInvocationDenialClosureFinding:
    code: str
    category: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderInvocationDenialClosureConstraint:
    code: str
    category: str = "provider_invocation_denial_closure"
    required: bool = True
    accepted: bool = False


@dataclass(frozen=True)
class ProviderInvocationDenialClosureRequirement:
    code: str
    category: str = "future_clearance"
    satisfied: bool = False


@dataclass(frozen=True)
class ProviderInvocationDenialClosureEvidenceSummary:
    linked_artifact_count: int = 0
    formal_attestation_ready: bool = False
    export_receipt_ready: bool = False
    external_review_packet_ready: bool = False
    denial_review_affirmed: bool = False
    readiness_metadata_only: bool = False
    registry_null_only: bool = False
    transport_capability_null_only: bool = False
    credential_custody_no_secret: bool = False
    endpoint_custody_no_endpoint: bool = False
    client_custody_no_client: bool = False
    digest_chain_complete: bool = False
    constraint_count: int = 0
    warning_count: int = 0
    finding_count: int = 0


@dataclass(frozen=True)
class ProviderInvocationDenialClosureGuardrailSummary:
    prompt_boundary_guardrail_required: bool = True
    architecture_boundary_manifest_required: bool = True
    import_purity_required: bool = True
    immutability_audit_required: bool = True
    prompt_boundary_guardrail_clean: bool = False
    architecture_boundaries_clean: bool = False
    import_purity_clean: bool = False
    immutability_audit_clean: bool = False
    guardrail_summary_complete: bool = False


@dataclass(frozen=True)
class ProviderInvocationDenialClosureManifest:
    closure_manifest_id: str
    closure_status: str
    release_blocker_status: str
    closure_scope: str
    closure_ref: str
    closure_label: str
    formal_attestation_id: str
    formal_attestation_status: str
    formal_attestation_digest: str
    expected_attestation_digest: str = ""
    attestation_digest_match: bool = True
    external_audit_export_receipt_id: str = ""
    external_audit_export_digest: str = ""
    external_security_review_packet_id: str = ""
    external_security_review_packet_digest: str = ""
    invocation_denial_review_receipt_id: str = ""
    invocation_denial_review_digest: str = ""
    invocation_readiness_id: str = ""
    invocation_readiness_digest: str = ""
    registry_id: str = ""
    registry_digest: str = ""
    transport_capability_manifest_id: str = ""
    transport_capability_digest: str = ""
    credential_custody_manifest_id: str = ""
    credential_custody_digest: str = ""
    endpoint_custody_manifest_id: str = ""
    endpoint_custody_digest: str = ""
    client_custody_manifest_id: str = ""
    client_custody_digest: str = ""
    evidence_summary: ProviderInvocationDenialClosureEvidenceSummary = field(default_factory=ProviderInvocationDenialClosureEvidenceSummary)
    guardrail_summary: ProviderInvocationDenialClosureGuardrailSummary = field(default_factory=ProviderInvocationDenialClosureGuardrailSummary)
    release_blocker_codes: tuple[str, ...] = field(default_factory=tuple)
    future_clearance_requirement_codes: tuple[str, ...] = field(default_factory=tuple)
    accepted_evidence_codes: tuple[str, ...] = field(default_factory=tuple)
    rejected_evidence_codes: tuple[str, ...] = field(default_factory=tuple)
    approved_constraint_codes: tuple[str, ...] = field(default_factory=tuple)
    rejected_constraint_codes: tuple[str, ...] = field(default_factory=tuple)
    metadata_only: bool = True
    closure_release_blocker: bool = True
    invocation_denial_preserved: bool = True
    provider_invocation_release_blocked: bool = True
    export_io_performed: bool = False
    external_delivery_performed: bool = False
    network_upload_performed: bool = False
    email_delivery_performed: bool = False
    webhook_delivery_performed: bool = False
    file_write_performed: bool = False
    object_storage_write_performed: bool = False
    prompt_text_included: bool = False
    hidden_chain_of_thought_included: bool = False
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
    model_params_included: bool = False
    tool_schemas_included: bool = False
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
    constraints: tuple[ProviderInvocationDenialClosureConstraint, ...] = field(default_factory=tuple)
    requirements: tuple[ProviderInvocationDenialClosureRequirement, ...] = field(default_factory=tuple)
    rationale: str = ""
    closure_digest: str = ""
    provider_invocation_denial_closure_manifest_only: bool = True
    phase100_closure_manifest: bool = True
    closure_not_release_approval: bool = True
    export_io_not_performed: bool = True
    external_delivery_not_performed: bool = True
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
    no_model_params: bool = True
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
    does_not_export_files: bool = True
    does_not_upload: bool = True
    does_not_send_email: bool = True
    does_not_call_webhooks: bool = True
    does_not_write_object_storage: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True


_ALLOWED_SCOPES = frozenset({
    ProviderInvocationDenialClosureScope.PROVIDER_INVOCATION_DENIAL_CLOSURE,
    ProviderInvocationDenialClosureScope.PHASE100_CONTEXT_HYGIENE_CLOSURE,
    ProviderInvocationDenialClosureScope.PROVIDER_INVOCATION_RELEASE_BLOCKER,
    ProviderInvocationDenialClosureScope.INTERNAL_SECURITY_CLOSURE_SUMMARY,
})
_FORBIDDEN_SCOPES = frozenset({
    ProviderInvocationDenialClosureScope.PROVIDER_INVOCATION_RELEASE_APPROVAL_FORBIDDEN,
    ProviderInvocationDenialClosureScope.PROVIDER_INVOCATION_APPROVAL_FORBIDDEN,
    ProviderInvocationDenialClosureScope.PROVIDER_SUBMISSION_FORBIDDEN,
    ProviderInvocationDenialClosureScope.NETWORK_EGRESS_FORBIDDEN,
    ProviderInvocationDenialClosureScope.EXPORT_DELIVERY_FORBIDDEN,
    ProviderInvocationDenialClosureScope.TOOL_OR_ACTION_FORBIDDEN,
    ProviderInvocationDenialClosureScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
})
_READY_ATTESTATION_STATUSES = frozenset({
    ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_ATTESTED,
    ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_ATTESTED_WITH_CONDITIONS,
})
_IO_FIELDS = (
    "export_io_performed", "external_delivery_performed", "network_upload_performed", "email_delivery_performed", "webhook_delivery_performed", "file_write_performed", "object_storage_write_performed",
)
_SENSITIVE_FIELDS = (
    "prompt_text_included", "hidden_chain_of_thought_included", "raw_payloads_included", "secrets_included", "secret_references_included", "endpoints_included", "endpoint_references_included", "clients_included", "client_references_included", "network_handles_included", "runtime_handles_included", "provider_params_included", "model_params_included", "tool_schemas_included",
)
_ALLOWANCE_FIELDS = (
    "invocation_allowed", "provider_send_allowed", "network_allowed", "credential_use_allowed", "endpoint_use_allowed", "client_use_allowed", "provider_sdk_allowed", "semantic_generation_allowed", "tool_calls_allowed", "memory_retrieval_allowed", "memory_write_allowed", "retention_allowed", "action_execution_allowed", "routing_allowed",
)
_REQUIRED_BLOCKER_CODES = (
    "provider_invocation_release_blocked", "real_transport_registration_blocked", "credentials_blocked", "endpoints_blocked", "clients_blocked", "network_egress_blocked", "provider_sdk_blocked", "prompt_text_export_blocked", "runtime_authority_blocked", "export_io_blocked", "live_prompt_assembly_unchanged_required", "prompt_assembler_modification_forbidden",
)
_REQUIRED_FUTURE_CODES = (
    "future_phase_required_to_introduce_any_real_transport", "future_phase_required_to_introduce_any_credentials", "future_phase_required_to_introduce_any_endpoints", "future_phase_required_to_introduce_any_clients", "future_phase_required_to_introduce_network_egress", "future_phase_required_to_modify_prompt_assembler", "future_phase_required_to_allow_provider_invocation", "independent_security_review_required_before_any_unblock", "explicit_operator_approval_required_before_any_unblock", "new_guardrail_update_required_before_any_unblock",
)
_NEGATIVE_MARKERS = (
    "forbidden", "blocked", "denied", "denial", "not_", "no_", "does_not_", "metadata_only", "not_invocable", "future_phase_required", "required_before_any_unblock", "_included=false", "_allowed=false", "_performed=false", "not_performed", "closure_not_release_approval",
)
_MARKER_CATEGORIES: Mapping[str, tuple[str, ...]] = {
    "invocation_approval": ("release approved", "invocation approved", "provider invocation allowed", "approve provider call", "unblock provider"),
    "export_destination": ("upload", "send", "deliver", "email", "webhook", "bucket", "object storage", "s3://", "gs://", "file://", "path=", "destination", "recipient"),
    "prompt_text": ("prompt_text", "internal_candidate_text", "synthetic_prompt_text", "dry_run_prompt_text", "final_prompt_text", "assembled_prompt", "system_prompt", "developer_prompt"),
    "hidden_chain_of_thought": ("chain_of_thought", "hidden reasoning", "scratchpad"),
    "secrets": ("api_key", "bearer", "token", "secret", "password", "private_key", "authorization"),
    "endpoints": ("https://", "http://", "endpoint", "base_url", "host", "port", "dns", "resolve"),
    "clients": ("client", "session", "transport", "stream", "retry", "request builder", "sdk", "openai", "anthropic"),
    "runtime": ("runtime handle", "raw_payload", "tool schema", "function call", "action", "retention", "routing", "memory write"),
    "provider_invocation": ("invoke", "send_to_provider", "chat.completions", "completion"),
}


def _mapping(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return value
    return {}


def _tuple_str(values: Sequence[str] | str | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        return (values,) if values else ()
    return tuple(str(value) for value in values if str(value))


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value)))


def _stable(value: Any) -> Any:
    if is_dataclass(value):
        return _stable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _stable(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_stable(item) for item in value]
    return value


def _safe_text(value: Any) -> str:
    return json.dumps(_stable(value), sort_keys=True, separators=(",", ":"), default=str).lower()


def _is_negative_fragment(fragment: str) -> bool:
    lowered = fragment.lower()
    return any(marker in lowered for marker in _NEGATIVE_MARKERS)


def _scan_categories(*values: Any) -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        text = _safe_text(value)
        for category, markers in _MARKER_CATEGORIES.items():
            count = 0
            for marker in markers:
                start = 0
                marker_lower = marker.lower()
                while True:
                    index = text.find(marker_lower, start)
                    if index == -1:
                        break
                    fragment = text[max(0, index - 50): index + len(marker_lower) + 50]
                    if not _is_negative_fragment(fragment):
                        count += 1
                    start = index + len(marker_lower)
            if count:
                counts[category] = counts.get(category, 0) + count
    return counts


def _digest_from_data(data: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(_stable(data), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _artifact_digest(data: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        if str(data.get(key, "")):
            return str(data[key])
    return ""


def _artifact_id(data: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        if str(data.get(key, "")):
            return str(data[key])
    return ""


def _linked_clean(data: Mapping[str, Any], true_keys: Sequence[str] = (), false_keys: Sequence[str] = ()) -> bool:
    if not data:
        return False
    return all(data.get(key) is True for key in true_keys) and all(data.get(key) is False for key in false_keys)


def _evidence_summary(
    attestation: Any,
    export_receipt: Any,
    external_review_packet: Any,
    denial_review: Any,
    readiness_manifest: Any,
    registry_manifest: Any,
    capability_manifest: Any,
    credential_manifest: Any,
    endpoint_manifest: Any,
    client_manifest: Any,
    constraint_count: int,
    warning_count: int,
    finding_count: int,
) -> ProviderInvocationDenialClosureEvidenceSummary:
    attestation_data = _mapping(attestation)
    export_data = _mapping(export_receipt)
    review_data = _mapping(external_review_packet)
    denial_data = _mapping(denial_review)
    readiness_data = _mapping(readiness_manifest)
    registry_data = _mapping(registry_manifest)
    capability_data = _mapping(capability_manifest)
    credential_data = _mapping(credential_manifest)
    endpoint_data = _mapping(endpoint_manifest)
    client_data = _mapping(client_manifest)
    linked = sum(1 for data in (attestation_data, export_data, review_data, denial_data, readiness_data, registry_data, capability_data, credential_data, endpoint_data, client_data) if data)
    digest_keys = (
        _artifact_digest(attestation_data, ("attestation_digest",)),
        _artifact_digest(export_data, ("export_receipt_digest",)),
        _artifact_digest(review_data, ("external_review_packet_digest", "review_packet_digest")),
        _artifact_digest(denial_data, ("denial_review_digest",)),
        _artifact_digest(readiness_data, ("readiness_digest",)),
    )
    return ProviderInvocationDenialClosureEvidenceSummary(
        linked_artifact_count=linked,
        formal_attestation_ready=provider_invocation_denial_attestation_ready(attestation),
        export_receipt_ready=_linked_clean(export_data, ("metadata_only", "export_io_not_performed", "external_delivery_not_performed"), ("export_io_performed",)),
        external_review_packet_ready=_linked_clean(review_data, ("metadata_only",), ("runtime_handles_included",)),
        denial_review_affirmed=_linked_clean(denial_data, ("invocation_denial_preserved", "metadata_only"), ("invocation_allowed", "provider_send_allowed")),
        readiness_metadata_only=_linked_clean(readiness_data, ("metadata_only", "provider_invocation_forbidden"), ("invocation_allowed", "provider_send_allowed")),
        registry_null_only=bool(registry_data.get("null_only", registry_data.get("registry_null_only", registry_data.get("metadata_only", False)))) and not bool(registry_data.get("live_transport_registered", False)),
        transport_capability_null_only=bool(capability_data.get("null_transport_only", capability_data.get("metadata_only", False))) and not bool(capability_data.get("real_transport_registration_allowed", False)),
        credential_custody_no_secret=bool(credential_data.get("no_secret_material", credential_data.get("contains_no_secrets", credential_data.get("metadata_only", False)))) and not bool(credential_data.get("secrets_included", False)),
        endpoint_custody_no_endpoint=bool(endpoint_data.get("no_endpoint_material", endpoint_data.get("contains_no_endpoints", endpoint_data.get("metadata_only", False)))) and not bool(endpoint_data.get("endpoints_included", False)),
        client_custody_no_client=bool(client_data.get("no_client_material", client_data.get("contains_no_clients", client_data.get("metadata_only", False)))) and not bool(client_data.get("clients_included", False)),
        digest_chain_complete=all(bool(value) for value in digest_keys if linked > 1) if linked > 1 else bool(attestation_data.get("attestation_digest")),
        constraint_count=constraint_count,
        warning_count=warning_count,
        finding_count=finding_count,
    )


def _status_from_findings(findings: Sequence[str], attestation_status: str, has_attestation: bool) -> str:
    if not has_attestation:
        return ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_MISSING_EVIDENCE
    if any("release_unblocked" in code or "invocation_override" in code or "allowance" in code for code in findings):
        return ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_OVERRIDE_DETECTED
    if any("runtime_authority" in code for code in findings):
        return ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_RUNTIME_AUTHORITY_DETECTED
    if any("sensitive_material" in code or "metadata_marker_detected:prompt_text" in code or "metadata_marker_detected:hidden_chain_of_thought" in code or "metadata_marker_detected:secrets" in code or "metadata_marker_detected:endpoints" in code or "metadata_marker_detected:clients" in code for code in findings):
        return ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SENSITIVE_MATERIAL_DETECTED
    if any("attestation_not_ready" in code for code in findings):
        return ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_ATTESTATION_NOT_READY
    if any("missing" in code or "digest_mismatch" in code or "linked_artifact_contradiction" in code for code in findings):
        return ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_BLOCKED
    if any("invalid" in code or "forbidden_scope" in code or "unknown_scope" in code or "io_attempt" in code for code in findings):
        return ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_INVALID
    if attestation_status == ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_ATTESTED_WITH_CONDITIONS:
        return ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED_WITH_CONDITIONS
    return ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED


def _release_status(closure_status: str, findings: Sequence[str]) -> str:
    if any("release_unblocked" in code for code in findings):
        return ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_UNBLOCKED_FORBIDDEN
    if closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_MISSING_EVIDENCE:
        return ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_BLOCKER_MISSING_EVIDENCE
    if closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED_WITH_CONDITIONS:
        return ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_BLOCKED_WITH_CONDITIONS
    if closure_status == ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED:
        return ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_BLOCKED
    return ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_BLOCKER_INVALID


def build_provider_invocation_denial_closure_manifest(
    formal_attestation: ProviderInvocationDenialAttestation | Mapping[str, Any] | None,
    *,
    external_audit_export_receipt: Mapping[str, Any] | Any | None = None,
    external_security_review_packet: Mapping[str, Any] | Any | None = None,
    invocation_denial_review_receipt: Mapping[str, Any] | Any | None = None,
    invocation_readiness_manifest: Mapping[str, Any] | Any | None = None,
    registry_manifest: Mapping[str, Any] | Any | None = None,
    transport_capability_manifest: Mapping[str, Any] | Any | None = None,
    credential_custody_manifest: Mapping[str, Any] | Any | None = None,
    endpoint_custody_manifest: Mapping[str, Any] | Any | None = None,
    client_custody_manifest: Mapping[str, Any] | Any | None = None,
    closure_scope: str = ProviderInvocationDenialClosureScope.PROVIDER_INVOCATION_DENIAL_CLOSURE,
    closure_ref: str = "",
    release_blocker_codes: Sequence[str] = _REQUIRED_BLOCKER_CODES,
    future_clearance_requirement_codes: Sequence[str] = _REQUIRED_FUTURE_CODES,
    accepted_evidence_codes: Sequence[str] = (),
    rejected_evidence_codes: Sequence[str] = (),
    approved_constraint_codes: Sequence[str] = (),
    rejected_constraint_codes: Sequence[str] = (),
    rationale: str = "",
    closure_label: str = "",
    expected_attestation_digest: str = "",
    guardrail_summary: ProviderInvocationDenialClosureGuardrailSummary | Mapping[str, Any] | None = None,
    release_blocker_status: str | None = None,
    closure_manifest_id: str = "",
    **flag_overrides: Any,
) -> ProviderInvocationDenialClosureManifest:
    attestation_data = _mapping(formal_attestation)
    attestation_digest = str(attestation_data.get("attestation_digest", "")) if attestation_data else ""
    if attestation_data and not attestation_digest:
        attestation_digest = compute_provider_invocation_denial_attestation_digest(formal_attestation)
    expected_match = not expected_attestation_digest or expected_attestation_digest == attestation_digest
    release_codes = _dedupe(_tuple_str(release_blocker_codes))
    future_codes = _dedupe(_tuple_str(future_clearance_requirement_codes))
    accepted_codes = _dedupe(_tuple_str(accepted_evidence_codes))
    rejected_codes = _dedupe(_tuple_str(rejected_evidence_codes))
    approved_codes = _dedupe(_tuple_str(approved_constraint_codes))
    rejected_constraint_codes_tuple = _dedupe(_tuple_str(rejected_constraint_codes))
    findings: list[str] = []
    warnings: list[str] = []

    if not attestation_data:
        findings.append("formal_attestation_missing")
    else:
        status = str(attestation_data.get("attestation_status", ""))
        if status not in _READY_ATTESTATION_STATUSES or not provider_invocation_denial_attestation_ready(formal_attestation):
            findings.append(f"attestation_not_ready:{status}")
        if not provider_invocation_denial_attestation_is_metadata_only(formal_attestation):
            findings.append("sensitive_material:attestation_not_metadata_only")
        if not provider_invocation_denial_attestation_denies_invocation(formal_attestation):
            findings.append("invocation_override:attestation_does_not_deny_invocation")
        if not provider_invocation_denial_attestation_does_not_export(formal_attestation):
            findings.append("io_attempt:attestation_export_attempt")
        if not provider_invocation_denial_attestation_contains_no_prompt_text(formal_attestation):
            findings.append("sensitive_material:attestation_prompt_text")
        if not provider_invocation_denial_attestation_contains_no_secrets(formal_attestation):
            findings.append("sensitive_material:attestation_secrets")
        if not provider_invocation_denial_attestation_contains_no_endpoints(formal_attestation):
            findings.append("sensitive_material:attestation_endpoints")
        if not provider_invocation_denial_attestation_contains_no_clients(formal_attestation):
            findings.append("sensitive_material:attestation_clients")
        if not provider_invocation_denial_attestation_contains_no_network_handles(formal_attestation):
            findings.append("runtime_authority:attestation_network_handles")
        if not provider_invocation_denial_attestation_contains_no_runtime_authority(formal_attestation):
            findings.append("runtime_authority:attestation_runtime_authority")
    if expected_attestation_digest and not expected_match:
        findings.append("attestation_digest_mismatch")
    if not str(closure_ref).strip():
        findings.append("missing_closure_ref")
    if closure_scope in _FORBIDDEN_SCOPES:
        findings.append(f"forbidden_scope:{closure_scope}")
    elif closure_scope not in _ALLOWED_SCOPES:
        findings.append(f"unknown_scope:{closure_scope}")
    if not release_codes:
        findings.append("missing_release_blocker_codes")
    if not future_codes:
        findings.append("missing_future_clearance_requirement_codes")
    if release_blocker_status == ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_UNBLOCKED_FORBIDDEN:
        findings.append("release_unblocked_forbidden")

    field_values = {field_name: bool(flag_overrides.get(field_name, False)) for field_name in _IO_FIELDS + _SENSITIVE_FIELDS + _ALLOWANCE_FIELDS}
    for field_name in _IO_FIELDS:
        if field_values[field_name]:
            findings.append(f"io_attempt:{field_name}")
    for field_name in _SENSITIVE_FIELDS:
        if field_values[field_name]:
            findings.append(f"sensitive_material_included:{field_name}")
    for field_name in _ALLOWANCE_FIELDS:
        if field_values[field_name]:
            findings.append(f"runtime_authority_allowed:{field_name}")
    if bool(flag_overrides.get("provider_invocation_release_blocked", True)) is not True:
        findings.append("release_unblocked_forbidden")

    marker_counts = _scan_categories(closure_scope, closure_ref, closure_label, rationale, release_codes, future_codes, accepted_codes, rejected_codes, approved_codes, rejected_constraint_codes_tuple)
    for category, count in sorted(marker_counts.items()):
        findings.append(f"metadata_marker_detected:{category}:{count}")
    if "invocation_approval" in marker_counts:
        findings.append("release_unblocked_forbidden")

    linked_values = (
        (external_audit_export_receipt, ("metadata_only", "export_io_not_performed", "external_delivery_not_performed"), ("export_io_performed", "invocation_allowed", "provider_send_allowed"), "external_audit_export"),
        (external_security_review_packet, ("metadata_only",), ("runtime_handles_included", "invocation_allowed"), "external_security_review"),
        (invocation_denial_review_receipt, ("metadata_only", "invocation_denial_preserved"), ("invocation_allowed", "provider_send_allowed"), "invocation_denial_review"),
        (invocation_readiness_manifest, ("metadata_only", "provider_invocation_forbidden"), ("invocation_allowed", "provider_send_allowed"), "invocation_readiness"),
    )
    for artifact, true_keys, false_keys, name in linked_values:
        data = _mapping(artifact)
        if data and not _linked_clean(data, true_keys, false_keys):
            findings.append(f"linked_artifact_contradiction:{name}")

    base_constraints = _dedupe(approved_codes + rejected_constraint_codes_tuple + ("metadata_only", "provider_invocation_release_blocked", "provider_invocation_forbidden", "closure_not_release_approval", "export_io_not_performed"))
    constraints = tuple(ProviderInvocationDenialClosureConstraint(code=code, accepted=code in set(approved_codes)) for code in base_constraints)
    requirements = tuple(ProviderInvocationDenialClosureRequirement(code=code) for code in future_codes)
    deduped_findings = _dedupe(findings)
    deduped_warnings = _dedupe(warnings) or ("phase100_closure_manifest_only", "metadata_only", "provider_invocation_release_blocked", "provider_invocation_forbidden")
    guardrail = guardrail_summary if guardrail_summary is not None else ProviderInvocationDenialClosureGuardrailSummary()
    guardrail_obj = guardrail if isinstance(guardrail, ProviderInvocationDenialClosureGuardrailSummary) else ProviderInvocationDenialClosureGuardrailSummary(**dict(_mapping(guardrail)))
    evidence = _evidence_summary(
        formal_attestation, external_audit_export_receipt, external_security_review_packet, invocation_denial_review_receipt,
        invocation_readiness_manifest, registry_manifest, transport_capability_manifest, credential_custody_manifest,
        endpoint_custody_manifest, client_custody_manifest, len(constraints), len(deduped_warnings), len(deduped_findings),
    )
    closure_status = _status_from_findings(deduped_findings, str(attestation_data.get("attestation_status", "")), bool(attestation_data))
    final_release_status = release_blocker_status or _release_status(closure_status, deduped_findings)

    export_data = _mapping(external_audit_export_receipt)
    review_packet_data = _mapping(external_security_review_packet)
    denial_data = _mapping(invocation_denial_review_receipt)
    readiness_data = _mapping(invocation_readiness_manifest)
    registry_data = _mapping(registry_manifest)
    capability_data = _mapping(transport_capability_manifest)
    credential_data = _mapping(credential_custody_manifest)
    endpoint_data = _mapping(endpoint_custody_manifest)
    client_data = _mapping(client_custody_manifest)
    manifest = ProviderInvocationDenialClosureManifest(
        closure_manifest_id=closure_manifest_id or "provider-invocation-denial-closure:pending-digest",
        closure_status=closure_status,
        release_blocker_status=final_release_status,
        closure_scope=str(closure_scope),
        closure_ref=str(closure_ref),
        closure_label=str(closure_label),
        formal_attestation_id=str(attestation_data.get("attestation_id", "")),
        formal_attestation_status=str(attestation_data.get("attestation_status", "")),
        formal_attestation_digest=attestation_digest,
        expected_attestation_digest=str(expected_attestation_digest),
        attestation_digest_match=expected_match,
        external_audit_export_receipt_id=_artifact_id(export_data or attestation_data, ("export_receipt_id",)),
        external_audit_export_digest=_artifact_digest(export_data or attestation_data, ("export_receipt_digest",)),
        external_security_review_packet_id=_artifact_id(review_packet_data or attestation_data, ("external_review_packet_id",)),
        external_security_review_packet_digest=_artifact_digest(review_packet_data or attestation_data, ("external_review_packet_digest", "review_packet_digest")),
        invocation_denial_review_receipt_id=_artifact_id(denial_data or attestation_data, ("denial_review_receipt_id", "invocation_denial_review_receipt_id")),
        invocation_denial_review_digest=_artifact_digest(denial_data or attestation_data, ("denial_review_digest", "invocation_denial_review_digest")),
        invocation_readiness_id=_artifact_id(readiness_data or attestation_data, ("readiness_id",)),
        invocation_readiness_digest=_artifact_digest(readiness_data or attestation_data, ("readiness_digest",)),
        registry_id=_artifact_id(registry_data, ("registry_id",)),
        registry_digest=_artifact_digest(registry_data, ("registry_digest",)),
        transport_capability_manifest_id=_artifact_id(capability_data, ("capability_manifest_id", "transport_capability_manifest_id")),
        transport_capability_digest=_artifact_digest(capability_data, ("capability_digest", "transport_capability_digest")),
        credential_custody_manifest_id=_artifact_id(credential_data, ("credential_custody_manifest_id",)),
        credential_custody_digest=_artifact_digest(credential_data, ("credential_custody_digest",)),
        endpoint_custody_manifest_id=_artifact_id(endpoint_data, ("endpoint_custody_manifest_id",)),
        endpoint_custody_digest=_artifact_digest(endpoint_data, ("endpoint_custody_digest",)),
        client_custody_manifest_id=_artifact_id(client_data, ("client_custody_manifest_id",)),
        client_custody_digest=_artifact_digest(client_data, ("client_custody_digest",)),
        evidence_summary=evidence,
        guardrail_summary=guardrail_obj,
        release_blocker_codes=release_codes,
        future_clearance_requirement_codes=future_codes,
        accepted_evidence_codes=accepted_codes,
        rejected_evidence_codes=rejected_codes,
        approved_constraint_codes=approved_codes,
        rejected_constraint_codes=rejected_constraint_codes_tuple,
        metadata_only=not any(field_values.values()) and not marker_counts,
        invocation_denial_preserved=bool(attestation_data and provider_invocation_denial_attestation_denies_invocation(formal_attestation) and not field_values["invocation_allowed"] and not field_values["provider_send_allowed"]),
        provider_invocation_release_blocked=bool(flag_overrides.get("provider_invocation_release_blocked", True)) is True,
        export_io_not_performed=not any(field_values[field_name] for field_name in _IO_FIELDS),
        external_delivery_not_performed=not any(field_values[field_name] for field_name in ("external_delivery_performed", "network_upload_performed", "email_delivery_performed", "webhook_delivery_performed")),
        no_prompt_text=not field_values["prompt_text_included"],
        no_raw_payloads=not field_values["raw_payloads_included"],
        no_secret_material=not field_values["secrets_included"] and not field_values["secret_references_included"],
        no_endpoint_material=not field_values["endpoints_included"] and not field_values["endpoint_references_included"],
        no_client_material=not field_values["clients_included"] and not field_values["client_references_included"],
        no_network_handles=not field_values["network_handles_included"],
        no_runtime_handles=not field_values["runtime_handles_included"],
        no_provider_params=not field_values["provider_params_included"],
        no_model_params=not field_values["model_params_included"],
        no_tool_schemas=not field_values["tool_schemas_included"],
        no_hidden_chain_of_thought=not field_values["hidden_chain_of_thought_included"],
        findings=deduped_findings,
        warnings=deduped_warnings,
        constraints=constraints,
        requirements=requirements,
        rationale=str(rationale),
        **field_values,
    )
    digest = compute_provider_invocation_denial_closure_digest(manifest)
    return replace(manifest, closure_manifest_id=closure_manifest_id or f"provider-invocation-denial-closure:{digest}", closure_digest=digest)


def compute_provider_invocation_denial_closure_digest(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> str:
    data = dict(_mapping(manifest))
    data.pop("closure_digest", None)
    if data.get("closure_manifest_id") == "provider-invocation-denial-closure:pending-digest" or str(data.get("closure_manifest_id", "")).startswith("provider-invocation-denial-closure:sha256:"):
        data["closure_manifest_id"] = "provider-invocation-denial-closure:pending-digest"
    return _digest_from_data(data)


def validate_provider_invocation_denial_closure_manifest(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> tuple[ProviderInvocationDenialClosureFinding, ...]:
    data = _mapping(manifest)
    if not data:
        return (ProviderInvocationDenialClosureFinding("closure_manifest_malformed", "invalid"),)
    findings: list[ProviderInvocationDenialClosureFinding] = []
    for code in _tuple_str(data.get("findings", ())):
        category = code.split(":", 1)[0]
        findings.append(ProviderInvocationDenialClosureFinding(code=code, category=category))
    if data.get("closure_digest") and compute_provider_invocation_denial_closure_digest(data) != data.get("closure_digest"):
        findings.append(ProviderInvocationDenialClosureFinding("closure_digest_mismatch", "integrity"))
    if data.get("release_blocker_status") == ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_UNBLOCKED_FORBIDDEN:
        findings.append(ProviderInvocationDenialClosureFinding("release_unblocked_forbidden", "override"))
    return tuple(findings)


def provider_invocation_denial_closure_is_metadata_only(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data and data.get("metadata_only") is True and all(data.get(field_name) is False for field_name in _IO_FIELDS + _SENSITIVE_FIELDS + _ALLOWANCE_FIELDS))


def provider_invocation_denial_closure_blocks_release(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data and data.get("provider_invocation_release_blocked") is True and data.get("release_blocker_status") in {ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_BLOCKED, ProviderInvocationReleaseBlockerStatus.PROVIDER_INVOCATION_RELEASE_BLOCKED_WITH_CONDITIONS})


def provider_invocation_denial_closure_denies_invocation(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data and data.get("invocation_denial_preserved") is True and data.get("provider_invocation_forbidden") is True and data.get("actual_provider_invocation_forbidden") is True and data.get("invocation_allowed") is False and data.get("provider_send_allowed") is False)


def provider_invocation_denial_closure_does_not_export(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data and data.get("export_io_not_performed") is True and data.get("external_delivery_not_performed") is True and all(data.get(field_name) is False for field_name in _IO_FIELDS))


def provider_invocation_denial_closure_contains_no_prompt_text(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data and data.get("no_prompt_text") is True and data.get("prompt_text_included") is False and data.get("hidden_chain_of_thought_included") is False)


def provider_invocation_denial_closure_contains_no_secrets(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data and data.get("no_secret_material") is True and data.get("secrets_included") is False and data.get("secret_references_included") is False)


def provider_invocation_denial_closure_contains_no_endpoints(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data and data.get("no_endpoint_material") is True and data.get("endpoints_included") is False and data.get("endpoint_references_included") is False)


def provider_invocation_denial_closure_contains_no_clients(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data and data.get("no_client_material") is True and data.get("clients_included") is False and data.get("client_references_included") is False)


def provider_invocation_denial_closure_contains_no_network_handles(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data and data.get("no_network_handles") is True and data.get("network_handles_included") is False and data.get("network_allowed") is False)


def provider_invocation_denial_closure_contains_no_runtime_authority(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(data and data.get("no_runtime_handles") is True and data.get("runtime_handles_included") is False and all(data.get(field_name) is False for field_name in _ALLOWANCE_FIELDS))


def provider_invocation_denial_closure_guardrails_present(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    guardrail = _mapping(data.get("guardrail_summary", {}))
    return bool(guardrail and all(guardrail.get(key) is True for key in ("prompt_boundary_guardrail_required", "architecture_boundary_manifest_required", "import_purity_required", "immutability_audit_required", "guardrail_summary_complete")))


def provider_invocation_denial_closure_ready(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> bool:
    data = _mapping(manifest)
    return bool(
        data
        and data.get("closure_status") in {ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED, ProviderInvocationDenialClosureStatus.PROVIDER_INVOCATION_DENIAL_CLOSURE_SEALED_WITH_CONDITIONS}
        and provider_invocation_denial_closure_is_metadata_only(manifest)
        and provider_invocation_denial_closure_blocks_release(manifest)
        and provider_invocation_denial_closure_denies_invocation(manifest)
        and provider_invocation_denial_closure_does_not_export(manifest)
    )


def explain_provider_invocation_denial_closure_findings(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(manifest)
    if not data:
        return ("closure_manifest_malformed",)
    return _dedupe(_tuple_str(data.get("findings", ())) + tuple(finding.code for finding in validate_provider_invocation_denial_closure_manifest(manifest)))


def summarize_provider_invocation_denial_closure_manifest(manifest: ProviderInvocationDenialClosureManifest | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(manifest)
    evidence = _mapping(data.get("evidence_summary", {}))
    guardrail = _mapping(data.get("guardrail_summary", {}))
    return {
        "closure_manifest_id": data.get("closure_manifest_id", ""),
        "closure_status": data.get("closure_status", ""),
        "release_blocker_status": data.get("release_blocker_status", ""),
        "closure_scope": data.get("closure_scope", ""),
        "closure_ref": data.get("closure_ref", ""),
        "formal_attestation_id": data.get("formal_attestation_id", ""),
        "formal_attestation_digest": data.get("formal_attestation_digest", ""),
        "linked_artifact_count": evidence.get("linked_artifact_count", 0),
        "digest_chain_complete": evidence.get("digest_chain_complete", False),
        "guardrail_summary_complete": guardrail.get("guardrail_summary_complete", False),
        "metadata_only": data.get("metadata_only", False),
        "provider_invocation_release_blocked": data.get("provider_invocation_release_blocked", False),
        "invocation_denial_preserved": data.get("invocation_denial_preserved", False),
        "provider_invocation_forbidden": data.get("provider_invocation_forbidden", False),
        "closure_digest": data.get("closure_digest", ""),
    }
