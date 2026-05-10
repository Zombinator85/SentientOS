from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_external_audit_export import (
    ExternalAuditExportReceipt,
    ExternalAuditExportStatus,
    compute_external_audit_export_receipt_digest,
    external_audit_export_receipt_contains_no_clients,
    external_audit_export_receipt_contains_no_endpoints,
    external_audit_export_receipt_contains_no_network_handles,
    external_audit_export_receipt_contains_no_prompt_text,
    external_audit_export_receipt_contains_no_runtime_authority,
    external_audit_export_receipt_contains_no_secrets,
    external_audit_export_receipt_does_not_export,
    external_audit_export_receipt_is_metadata_only,
    external_audit_export_receipt_preserves_invocation_denial,
    external_audit_export_receipt_ready_for_export_review,
)
from sentientos.context_hygiene.prompt_external_security_review import ExternalSecurityReviewPacket, external_security_review_packet_ready_for_review
from sentientos.context_hygiene.prompt_provider_invocation_denial_review import ProviderInvocationDenialReviewReceipt, provider_invocation_denial_review_affirms_forbidden_invocation
from sentientos.context_hygiene.prompt_provider_invocation_readiness import ProviderInvocationReadinessManifest, provider_invocation_readiness_forbids_invocation


class ProviderInvocationDenialAttestationStatus:
    PROVIDER_INVOCATION_DENIAL_ATTESTED = "provider_invocation_denial_attested"
    PROVIDER_INVOCATION_DENIAL_ATTESTED_WITH_CONDITIONS = "provider_invocation_denial_attested_with_conditions"
    PROVIDER_INVOCATION_DENIAL_REJECTED = "provider_invocation_denial_rejected"
    PROVIDER_INVOCATION_DENIAL_EXPIRED = "provider_invocation_denial_expired"
    PROVIDER_INVOCATION_DENIAL_INVALID = "provider_invocation_denial_invalid"
    PROVIDER_INVOCATION_DENIAL_MISSING_EVIDENCE = "provider_invocation_denial_missing_evidence"
    PROVIDER_INVOCATION_DENIAL_EXPORT_NOT_READY = "provider_invocation_denial_export_not_ready"
    PROVIDER_INVOCATION_DENIAL_SENSITIVE_MATERIAL_DETECTED = "provider_invocation_denial_sensitive_material_detected"
    PROVIDER_INVOCATION_DENIAL_RUNTIME_AUTHORITY_DETECTED = "provider_invocation_denial_runtime_authority_detected"
    PROVIDER_INVOCATION_DENIAL_OVERRIDE_DETECTED = "provider_invocation_denial_override_detected"


class ProviderInvocationDenialAttestationDecision:
    ATTEST_PROVIDER_INVOCATION_FORBIDDEN = "attest_provider_invocation_forbidden"
    ATTEST_METADATA_ONLY_NOT_INVOCABLE = "attest_metadata_only_not_invocable"
    ATTEST_WITH_CONDITIONS = "attest_with_conditions"
    REJECT_ATTESTATION = "reject_attestation"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"
    REQUEST_MORE_REDACTION = "request_more_redaction"
    NO_DECISION = "no_decision"


class ProviderInvocationDenialAttestationScope:
    PROVIDER_INVOCATION_DENIAL_ATTESTATION = "provider_invocation_denial_attestation"
    EXTERNAL_AUDIT_DENIAL_ATTESTATION = "external_audit_denial_attestation"
    INTERNAL_SECURITY_DENIAL_ATTESTATION = "internal_security_denial_attestation"
    INVOCATION_DENIAL_CHAIN_ATTESTATION = "invocation_denial_chain_attestation"
    PROVIDER_INVOCATION_APPROVAL_FORBIDDEN = "provider_invocation_approval_forbidden"
    PROVIDER_SUBMISSION_FORBIDDEN = "provider_submission_forbidden"
    NETWORK_EGRESS_FORBIDDEN = "network_egress_forbidden"
    EXPORT_DELIVERY_FORBIDDEN = "export_delivery_forbidden"
    TOOL_OR_ACTION_FORBIDDEN = "tool_or_action_forbidden"
    EXTERNAL_USER_VISIBLE_FORBIDDEN = "external_user_visible_forbidden"


@dataclass(frozen=True)
class ProviderInvocationDenialAttestationFinding:
    code: str
    category: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderInvocationDenialAttestationConstraint:
    code: str
    category: str = "formal_denial_attestation"
    required: bool = True
    accepted: bool = False


@dataclass(frozen=True)
class ProviderInvocationDenialAttestationEvidenceSummary:
    linked_artifact_count: int = 0
    export_receipt_ready: bool = False
    external_review_packet_ready: bool = False
    denial_review_affirmed: bool = False
    readiness_metadata_only: bool = False
    digest_chain_complete: bool = False
    constraint_count: int = 0
    warning_count: int = 0
    finding_count: int = 0


@dataclass(frozen=True)
class ProviderInvocationDenialAttestationExpiration:
    attested_at: str = ""
    expires_at: str = ""
    ttl_seconds: int | None = None


@dataclass(frozen=True)
class ProviderInvocationDenialAttestation:
    attestation_id: str
    attestation_status: str
    attestation_scope: str
    decision: str
    attestor_ref: str
    attestation_label: str
    formal_denial_statement_code: str
    export_receipt_id: str
    export_receipt_status: str
    export_receipt_digest: str
    expected_export_receipt_digest: str = ""
    export_receipt_digest_match: bool = True
    external_review_packet_id: str = ""
    external_review_packet_digest: str = ""
    invocation_denial_review_receipt_id: str = ""
    invocation_denial_review_digest: str = ""
    readiness_id: str = ""
    readiness_digest: str = ""
    evidence_summary: ProviderInvocationDenialAttestationEvidenceSummary = field(default_factory=ProviderInvocationDenialAttestationEvidenceSummary)
    approved_constraint_codes: tuple[str, ...] = field(default_factory=tuple)
    rejected_constraint_codes: tuple[str, ...] = field(default_factory=tuple)
    accepted_evidence_codes: tuple[str, ...] = field(default_factory=tuple)
    rejected_evidence_codes: tuple[str, ...] = field(default_factory=tuple)
    accepted_denial_codes: tuple[str, ...] = field(default_factory=tuple)
    rejected_denial_codes: tuple[str, ...] = field(default_factory=tuple)
    invocation_denial_preserved: bool = True
    metadata_only: bool = True
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
    expiration: ProviderInvocationDenialAttestationExpiration = field(default_factory=ProviderInvocationDenialAttestationExpiration)
    expired: bool = False
    findings: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    constraints: tuple[ProviderInvocationDenialAttestationConstraint, ...] = field(default_factory=tuple)
    rationale: str = ""
    attestation_digest: str = ""
    provider_invocation_denial_attestation_only: bool = True
    formal_denial_attestation: bool = True
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
    ProviderInvocationDenialAttestationScope.PROVIDER_INVOCATION_DENIAL_ATTESTATION,
    ProviderInvocationDenialAttestationScope.EXTERNAL_AUDIT_DENIAL_ATTESTATION,
    ProviderInvocationDenialAttestationScope.INTERNAL_SECURITY_DENIAL_ATTESTATION,
    ProviderInvocationDenialAttestationScope.INVOCATION_DENIAL_CHAIN_ATTESTATION,
})
_FORBIDDEN_SCOPES = frozenset({
    ProviderInvocationDenialAttestationScope.PROVIDER_INVOCATION_APPROVAL_FORBIDDEN,
    ProviderInvocationDenialAttestationScope.PROVIDER_SUBMISSION_FORBIDDEN,
    ProviderInvocationDenialAttestationScope.NETWORK_EGRESS_FORBIDDEN,
    ProviderInvocationDenialAttestationScope.EXPORT_DELIVERY_FORBIDDEN,
    ProviderInvocationDenialAttestationScope.TOOL_OR_ACTION_FORBIDDEN,
    ProviderInvocationDenialAttestationScope.EXTERNAL_USER_VISIBLE_FORBIDDEN,
})
_ATTESTING_DECISIONS = frozenset({
    ProviderInvocationDenialAttestationDecision.ATTEST_PROVIDER_INVOCATION_FORBIDDEN,
    ProviderInvocationDenialAttestationDecision.ATTEST_METADATA_ONLY_NOT_INVOCABLE,
    ProviderInvocationDenialAttestationDecision.ATTEST_WITH_CONDITIONS,
})
_EXPORT_READY_STATUSES = frozenset({
    ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_READY,
    ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_READY_WITH_CONDITIONS,
})
_IO_FIELDS = (
    "export_io_performed",
    "external_delivery_performed",
    "network_upload_performed",
    "email_delivery_performed",
    "webhook_delivery_performed",
    "file_write_performed",
    "object_storage_write_performed",
)
_SENSITIVE_FIELDS = (
    "prompt_text_included",
    "hidden_chain_of_thought_included",
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
    "model_params_included",
    "tool_schemas_included",
)
_ALLOWANCE_FIELDS = (
    "invocation_allowed",
    "provider_send_allowed",
    "network_allowed",
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
)
_MARKER_CATEGORIES = (
    ("approval", ("invocation approved", "provider invocation allowed", "approve provider call")),
    ("io", ("upload", "send", "deliver", "email", "webhook", "bucket", "object storage", "s3://", "gs://", "file://", "path=", "destination", "recipient")),
    ("prompt_text", ("prompt_text", "internal_candidate_text", "synthetic_prompt_text", "dry_run_prompt_text", "final_prompt_text", "assembled_prompt", "system_prompt", "developer_prompt")),
    ("hidden_chain_of_thought", ("chain_of_thought", "hidden reasoning", "scratchpad")),
    ("secrets", ("api_key", "bearer", "token", "secret", "password", "private_key", "authorization")),
    ("endpoints", ("https://", "http://", "endpoint", "base_url", "host", "port", "dns", "resolve")),
    ("clients", ("client", "session", "transport", "stream", "retry", "request builder", "sdk", "openai", "anthropic")),
    ("runtime", ("runtime handle", "raw_payload", "tool schema", "function call", "action", "retention", "routing", "memory write")),
    ("provider_invocation", ("invoke", "send_to_provider", "chat.completions", "completion")),
)
_NEGATIVE_TOKENS = ("provider_invocation_forbidden", "actual_provider_invocation_forbidden", "no_prompt_text", "no_hidden_chain_of_thought", "no_secret_material", "no_endpoint_material", "no_client_material", "export_io_not_performed", "external_delivery_not_performed", "forbidden", "does_not_", "does not", "metadata_only", "denied", "denial", "not_invocable", "_included=false", "_allowed=false", "_performed=false", "not_performed")


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


def _digest_payload(attestation: ProviderInvocationDenialAttestation | Mapping[str, Any]) -> Mapping[str, Any]:
    data = dict(_mapping(attestation))
    data.pop("attestation_id", None)
    data.pop("attestation_digest", None)
    return data


def compute_provider_invocation_denial_attestation_digest(attestation: ProviderInvocationDenialAttestation | Mapping[str, Any]) -> str:
    return _stable_digest(_digest_payload(attestation))


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


def _scan_categories(*values: Any) -> dict[str, int]:
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
                        index = text.find(marker, index + len(marker))
    return counts


def _evidence_summary(
    receipt: ExternalAuditExportReceipt | Mapping[str, Any] | None,
    external_review_packet: ExternalSecurityReviewPacket | Mapping[str, Any] | None,
    denial_review_receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any] | None,
    readiness_manifest: ProviderInvocationReadinessManifest | Mapping[str, Any] | None,
    constraint_count: int,
    warning_count: int,
    finding_count: int,
) -> ProviderInvocationDenialAttestationEvidenceSummary:
    receipt_data = _mapping(receipt)
    linked = sum(1 for item in (receipt, external_review_packet, denial_review_receipt, readiness_manifest) if _mapping(item))
    external_ready = external_security_review_packet_ready_for_review(external_review_packet) if _mapping(external_review_packet) else bool(receipt_data.get("external_review_packet_digest", ""))
    denial_affirmed = provider_invocation_denial_review_affirms_forbidden_invocation(denial_review_receipt) if _mapping(denial_review_receipt) else bool(receipt_data.get("invocation_denial_review_digest", ""))
    readiness_metadata = provider_invocation_readiness_forbids_invocation(readiness_manifest) if _mapping(readiness_manifest) else bool(receipt_data.get("readiness_digest", ""))
    return ProviderInvocationDenialAttestationEvidenceSummary(
        linked_artifact_count=linked,
        export_receipt_ready=external_audit_export_receipt_ready_for_export_review(receipt) if receipt_data else False,
        external_review_packet_ready=external_ready,
        denial_review_affirmed=denial_affirmed,
        readiness_metadata_only=readiness_metadata,
        digest_chain_complete=bool(receipt_data.get("export_receipt_digest", "") and receipt_data.get("external_review_packet_digest", "") and receipt_data.get("invocation_denial_review_digest", "") and receipt_data.get("readiness_digest", "")),
        constraint_count=constraint_count,
        warning_count=warning_count,
        finding_count=finding_count,
    )


def _status_from_findings(findings: tuple[str, ...], decision: str, expired: bool) -> str:
    if expired:
        return ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_EXPIRED
    if any(code.startswith("export_receipt_missing") for code in findings):
        return ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_MISSING_EVIDENCE
    if any("override" in code or "approval" in code or "provider_invocation" in code for code in findings):
        return ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_OVERRIDE_DETECTED
    if any("io_attempt" in code or code.startswith("forbidden_scope") or "metadata_marker_detected:io" in code for code in findings):
        return ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_EXPORT_NOT_READY
    if any("runtime" in code or "allowance" in code or "metadata_marker_detected:runtime" in code for code in findings):
        return ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_RUNTIME_AUTHORITY_DETECTED
    if any("sensitive" in code or "included" in code or "metadata_marker_detected:prompt_text" in code or "metadata_marker_detected:hidden_chain_of_thought" in code or "metadata_marker_detected:secrets" in code or "metadata_marker_detected:endpoints" in code or "metadata_marker_detected:clients" in code for code in findings):
        return ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_SENSITIVE_MATERIAL_DETECTED
    if any("export_not_ready" in code or "digest_mismatch" in code or "linked_artifact_contradiction" in code for code in findings):
        return ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_EXPORT_NOT_READY
    if any(code.startswith("invalid") or code.startswith("missing_attestor") or code.startswith("unknown_scope") for code in findings):
        return ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_INVALID
    if decision in {ProviderInvocationDenialAttestationDecision.REJECT_ATTESTATION, ProviderInvocationDenialAttestationDecision.REQUEST_MORE_REDACTION, ProviderInvocationDenialAttestationDecision.REQUEST_MORE_EVIDENCE, ProviderInvocationDenialAttestationDecision.NO_DECISION}:
        return ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_REJECTED
    if decision == ProviderInvocationDenialAttestationDecision.ATTEST_WITH_CONDITIONS:
        return ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_ATTESTED_WITH_CONDITIONS
    return ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_ATTESTED


def build_provider_invocation_denial_attestation(
    external_audit_export_receipt: ExternalAuditExportReceipt | Mapping[str, Any] | None,
    *,
    external_review_packet: ExternalSecurityReviewPacket | Mapping[str, Any] | None = None,
    invocation_denial_review_receipt: ProviderInvocationDenialReviewReceipt | Mapping[str, Any] | None = None,
    readiness_manifest: ProviderInvocationReadinessManifest | Mapping[str, Any] | None = None,
    attestor_ref: str,
    decision: str = ProviderInvocationDenialAttestationDecision.NO_DECISION,
    attestation_scope: str = ProviderInvocationDenialAttestationScope.PROVIDER_INVOCATION_DENIAL_ATTESTATION,
    approved_constraint_codes: Sequence[str] = (),
    rejected_constraint_codes: Sequence[str] = (),
    accepted_evidence_codes: Sequence[str] = (),
    rejected_evidence_codes: Sequence[str] = (),
    accepted_denial_codes: Sequence[str] = (),
    rejected_denial_codes: Sequence[str] = (),
    rationale: str = "",
    expires_at: str = "",
    ttl_seconds: int | None = None,
    expected_export_receipt_digest: str = "",
    attestation_label: str = "",
    attested_at: str = "",
    expired: bool = False,
    attestation_id: str = "",
    **flag_overrides: Any,
) -> ProviderInvocationDenialAttestation:
    receipt_data = _mapping(external_audit_export_receipt)
    receipt_digest = str(receipt_data.get("export_receipt_digest", "")) if receipt_data else ""
    if receipt_data and not receipt_digest:
        receipt_digest = compute_external_audit_export_receipt_digest(external_audit_export_receipt)
    expected_match = not expected_export_receipt_digest or expected_export_receipt_digest == receipt_digest
    findings: list[str] = []
    warnings: list[str] = []

    if not receipt_data:
        findings.append("export_receipt_missing")
    elif str(receipt_data.get("export_status", "")) not in _EXPORT_READY_STATUSES or not external_audit_export_receipt_ready_for_export_review(external_audit_export_receipt):
        findings.append(f"export_not_ready:{receipt_data.get('export_status', '')}")
    if receipt_data and not external_audit_export_receipt_is_metadata_only(external_audit_export_receipt):
        findings.append("sensitive_material:export_receipt_not_metadata_only")
    if receipt_data and not external_audit_export_receipt_does_not_export(external_audit_export_receipt):
        findings.append("io_attempt:export_receipt_exports")
    if receipt_data and not external_audit_export_receipt_preserves_invocation_denial(external_audit_export_receipt):
        findings.append("invocation_override:export_receipt_denial_not_preserved")
    if receipt_data and not external_audit_export_receipt_contains_no_prompt_text(external_audit_export_receipt):
        findings.append("sensitive_material:prompt_text")
    if receipt_data and not external_audit_export_receipt_contains_no_secrets(external_audit_export_receipt):
        findings.append("sensitive_material:secrets")
    if receipt_data and not external_audit_export_receipt_contains_no_endpoints(external_audit_export_receipt):
        findings.append("sensitive_material:endpoints")
    if receipt_data and not external_audit_export_receipt_contains_no_clients(external_audit_export_receipt):
        findings.append("sensitive_material:clients")
    if receipt_data and not external_audit_export_receipt_contains_no_network_handles(external_audit_export_receipt):
        findings.append("runtime_authority:network_handles")
    if receipt_data and not external_audit_export_receipt_contains_no_runtime_authority(external_audit_export_receipt):
        findings.append("runtime_authority:runtime_or_provider_material")
    if expected_export_receipt_digest and not expected_match:
        findings.append("export_receipt_digest_mismatch")
    if not str(attestor_ref).strip():
        findings.append("missing_attestor_ref")
    if attestation_scope in _FORBIDDEN_SCOPES:
        findings.append(f"forbidden_scope:{attestation_scope}")
    elif attestation_scope not in _ALLOWED_SCOPES:
        findings.append(f"unknown_scope:{attestation_scope}")
    if decision not in _ATTESTING_DECISIONS:
        warnings.append(f"decision_not_attestation:{decision}")
    if _mapping(external_review_packet) and not external_security_review_packet_ready_for_review(external_review_packet):
        findings.append("linked_artifact_contradiction:external_review_packet_not_ready")
    if _mapping(invocation_denial_review_receipt) and not provider_invocation_denial_review_affirms_forbidden_invocation(invocation_denial_review_receipt):
        findings.append("linked_artifact_contradiction:denial_review_not_affirmed")
    if _mapping(readiness_manifest) and not provider_invocation_readiness_forbids_invocation(readiness_manifest):
        findings.append("linked_artifact_contradiction:readiness_not_denial_only")

    marker_counts = _scan_categories(attestor_ref, attestation_label, rationale, accepted_evidence_codes, rejected_evidence_codes, accepted_denial_codes, rejected_denial_codes, approved_constraint_codes, rejected_constraint_codes)
    for category, count in sorted(marker_counts.items()):
        findings.append(f"metadata_marker_detected:{category}:{count}")

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

    base_constraint_codes = _dedupe(_tuple_str(approved_constraint_codes) + _tuple_str(rejected_constraint_codes) + ("metadata_only", "export_io_not_performed", "provider_invocation_forbidden", "formal_denial_attestation"))
    constraints = tuple(
        ProviderInvocationDenialAttestationConstraint(code=code, category="attestation_constraint", required=True, accepted=code in set(_tuple_str(approved_constraint_codes)))
        for code in base_constraint_codes
    )
    deduped_findings = _dedupe(findings)
    deduped_warnings = _dedupe(warnings) or ("formal_denial_attestation_only", "metadata_only", "export_io_not_performed", "provider_invocation_remains_forbidden")
    evidence_summary = _evidence_summary(external_audit_export_receipt, external_review_packet, invocation_denial_review_receipt, readiness_manifest, len(constraints), len(deduped_warnings), len(deduped_findings))
    status = _status_from_findings(deduped_findings, decision, expired)
    attestation = ProviderInvocationDenialAttestation(
        attestation_id=attestation_id or "provider-invocation-denial-attestation:pending-digest",
        attestation_status=status,
        attestation_scope=attestation_scope,
        decision=decision,
        attestor_ref=str(attestor_ref),
        attestation_label=str(attestation_label),
        formal_denial_statement_code="provider_invocation_remains_forbidden_metadata_only_no_export",
        export_receipt_id=str(receipt_data.get("export_receipt_id", "")),
        export_receipt_status=str(receipt_data.get("export_status", "")),
        export_receipt_digest=receipt_digest,
        expected_export_receipt_digest=str(expected_export_receipt_digest),
        export_receipt_digest_match=expected_match,
        external_review_packet_id=str(receipt_data.get("external_review_packet_id", _mapping(external_review_packet).get("external_review_packet_id", ""))),
        external_review_packet_digest=str(receipt_data.get("external_review_packet_digest", _mapping(external_review_packet).get("external_review_packet_digest", ""))),
        invocation_denial_review_receipt_id=str(receipt_data.get("invocation_denial_review_receipt_id", _mapping(invocation_denial_review_receipt).get("denial_review_receipt_id", ""))),
        invocation_denial_review_digest=str(receipt_data.get("invocation_denial_review_digest", _mapping(invocation_denial_review_receipt).get("denial_review_digest", ""))),
        readiness_id=str(receipt_data.get("readiness_id", _mapping(readiness_manifest).get("readiness_id", ""))),
        readiness_digest=str(receipt_data.get("readiness_digest", _mapping(readiness_manifest).get("readiness_digest", ""))),
        evidence_summary=evidence_summary,
        approved_constraint_codes=_dedupe(_tuple_str(approved_constraint_codes)),
        rejected_constraint_codes=_dedupe(_tuple_str(rejected_constraint_codes)),
        accepted_evidence_codes=_dedupe(_tuple_str(accepted_evidence_codes)),
        rejected_evidence_codes=_dedupe(_tuple_str(rejected_evidence_codes)),
        accepted_denial_codes=_dedupe(_tuple_str(accepted_denial_codes)),
        rejected_denial_codes=_dedupe(_tuple_str(rejected_denial_codes)),
        invocation_denial_preserved=bool(receipt_data and external_audit_export_receipt_preserves_invocation_denial(external_audit_export_receipt) and not field_values["invocation_allowed"] and not field_values["provider_send_allowed"]),
        metadata_only=not any(field_values.values()) and not marker_counts,
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
        expiration=ProviderInvocationDenialAttestationExpiration(attested_at=str(attested_at), expires_at=str(expires_at), ttl_seconds=ttl_seconds),
        expired=expired,
        findings=deduped_findings,
        warnings=deduped_warnings,
        constraints=constraints,
        rationale=str(rationale),
        **field_values,
    )
    digest = compute_provider_invocation_denial_attestation_digest(attestation)
    return replace(attestation, attestation_id=attestation_id or f"provider-invocation-denial-attestation:{digest[-16:]}", attestation_digest=digest)


def validate_provider_invocation_denial_attestation(attestation: ProviderInvocationDenialAttestation | Mapping[str, Any]) -> tuple[ProviderInvocationDenialAttestationFinding, ...]:
    data = _mapping(attestation)
    if not data:
        return (ProviderInvocationDenialAttestationFinding(code="attestation_malformed", category="input"),)
    findings: list[ProviderInvocationDenialAttestationFinding] = []
    if str(data.get("attestation_status", "")) in {ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_ATTESTED, ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_ATTESTED_WITH_CONDITIONS}:
        if not provider_invocation_denial_attestation_ready(attestation):
            findings.append(ProviderInvocationDenialAttestationFinding(code="attested_status_but_not_ready", category="gating"))
    if str(data.get("attestation_digest", "")) != compute_provider_invocation_denial_attestation_digest(attestation):
        findings.append(ProviderInvocationDenialAttestationFinding(code="attestation_digest_mismatch", category="digest"))
    for field_name in _IO_FIELDS:
        if bool(data.get(field_name, False)):
            findings.append(ProviderInvocationDenialAttestationFinding(code=f"io_attempt:{field_name}", category="export_io"))
    for field_name in _SENSITIVE_FIELDS:
        if bool(data.get(field_name, False)):
            findings.append(ProviderInvocationDenialAttestationFinding(code=f"sensitive_material_included:{field_name}", category="sensitive_material"))
    for field_name in _ALLOWANCE_FIELDS:
        if bool(data.get(field_name, False)):
            findings.append(ProviderInvocationDenialAttestationFinding(code=f"runtime_authority_allowed:{field_name}", category="runtime_authority"))
    return tuple(findings)


def provider_invocation_denial_attestation_is_metadata_only(attestation: ProviderInvocationDenialAttestation | Mapping[str, Any]) -> bool:
    data = _mapping(attestation)
    return bool(data and data.get("metadata_only") is True and all(data.get(field_name) is False for field_name in _SENSITIVE_FIELDS + _ALLOWANCE_FIELDS))


def provider_invocation_denial_attestation_denies_invocation(attestation: ProviderInvocationDenialAttestation | Mapping[str, Any]) -> bool:
    data = _mapping(attestation)
    return bool(data and data.get("invocation_denial_preserved") is True and data.get("provider_invocation_forbidden") is True and data.get("actual_provider_invocation_forbidden") is True and data.get("invocation_allowed") is False and data.get("provider_send_allowed") is False)


def provider_invocation_denial_attestation_does_not_export(attestation: ProviderInvocationDenialAttestation | Mapping[str, Any]) -> bool:
    data = _mapping(attestation)
    return bool(data and data.get("export_io_not_performed") is True and data.get("external_delivery_not_performed") is True and all(data.get(field_name) is False for field_name in _IO_FIELDS))


def provider_invocation_denial_attestation_contains_no_prompt_text(attestation: ProviderInvocationDenialAttestation | Mapping[str, Any]) -> bool:
    data = _mapping(attestation)
    return bool(data and data.get("no_prompt_text") is True and data.get("prompt_text_included") is False)


def provider_invocation_denial_attestation_contains_no_secrets(attestation: ProviderInvocationDenialAttestation | Mapping[str, Any]) -> bool:
    data = _mapping(attestation)
    return bool(data and data.get("no_secret_material") is True and data.get("secrets_included") is False and data.get("secret_references_included") is False)


def provider_invocation_denial_attestation_contains_no_endpoints(attestation: ProviderInvocationDenialAttestation | Mapping[str, Any]) -> bool:
    data = _mapping(attestation)
    return bool(data and data.get("no_endpoint_material") is True and data.get("endpoints_included") is False and data.get("endpoint_references_included") is False)


def provider_invocation_denial_attestation_contains_no_clients(attestation: ProviderInvocationDenialAttestation | Mapping[str, Any]) -> bool:
    data = _mapping(attestation)
    return bool(data and data.get("no_client_material") is True and data.get("clients_included") is False and data.get("client_references_included") is False)


def provider_invocation_denial_attestation_contains_no_network_handles(attestation: ProviderInvocationDenialAttestation | Mapping[str, Any]) -> bool:
    data = _mapping(attestation)
    return bool(data and data.get("no_network_handles") is True and data.get("network_handles_included") is False and data.get("network_allowed") is False)


def provider_invocation_denial_attestation_contains_no_runtime_authority(attestation: ProviderInvocationDenialAttestation | Mapping[str, Any]) -> bool:
    data = _mapping(attestation)
    return bool(data and data.get("no_runtime_handles") is True and data.get("runtime_handles_included") is False and all(data.get(field_name) is False for field_name in _ALLOWANCE_FIELDS))


def provider_invocation_denial_attestation_ready(attestation: ProviderInvocationDenialAttestation | Mapping[str, Any]) -> bool:
    data = _mapping(attestation)
    return bool(
        data
        and data.get("attestation_status") in {ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_ATTESTED, ProviderInvocationDenialAttestationStatus.PROVIDER_INVOCATION_DENIAL_ATTESTED_WITH_CONDITIONS}
        and provider_invocation_denial_attestation_is_metadata_only(attestation)
        and provider_invocation_denial_attestation_does_not_export(attestation)
        and provider_invocation_denial_attestation_denies_invocation(attestation)
        and not data.get("expired", False)
    )


def explain_provider_invocation_denial_attestation_findings(attestation: ProviderInvocationDenialAttestation | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(attestation)
    if not data:
        return ("attestation_malformed",)
    return _dedupe(_tuple_str(data.get("findings", ())) + tuple(finding.code for finding in validate_provider_invocation_denial_attestation(attestation)))


def summarize_provider_invocation_denial_attestation(attestation: ProviderInvocationDenialAttestation | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(attestation)
    evidence = _mapping(data.get("evidence_summary", {}))
    return {
        "attestation_id": data.get("attestation_id", ""),
        "attestation_status": data.get("attestation_status", ""),
        "attestation_scope": data.get("attestation_scope", ""),
        "decision": data.get("decision", ""),
        "attestor_ref": data.get("attestor_ref", ""),
        "formal_denial_statement_code": data.get("formal_denial_statement_code", ""),
        "export_receipt_id": data.get("export_receipt_id", ""),
        "export_receipt_digest": data.get("export_receipt_digest", ""),
        "linked_artifact_count": evidence.get("linked_artifact_count", 0),
        "digest_chain_complete": evidence.get("digest_chain_complete", False),
        "metadata_only": data.get("metadata_only", False),
        "export_io_not_performed": data.get("export_io_not_performed", False),
        "invocation_denial_preserved": data.get("invocation_denial_preserved", False),
        "provider_invocation_forbidden": data.get("provider_invocation_forbidden", False),
        "attestation_digest": data.get("attestation_digest", ""),
    }
