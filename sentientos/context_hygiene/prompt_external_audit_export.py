from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_external_security_review import (
    ExternalSecurityReviewPacket,
    ExternalSecurityReviewPacketStatus,
    compute_external_security_review_packet_digest,
    external_security_review_packet_contains_no_clients,
    external_security_review_packet_contains_no_endpoints,
    external_security_review_packet_contains_no_network_handles,
    external_security_review_packet_contains_no_prompt_text,
    external_security_review_packet_contains_no_runtime_authority,
    external_security_review_packet_contains_no_secrets,
    external_security_review_packet_is_metadata_only,
    external_security_review_packet_preserves_invocation_denial,
    external_security_review_packet_ready_for_review,
)


class ExternalAuditExportStatus:
    EXTERNAL_AUDIT_EXPORT_READY = "external_audit_export_ready"
    EXTERNAL_AUDIT_EXPORT_READY_WITH_CONDITIONS = "external_audit_export_ready_with_conditions"
    EXTERNAL_AUDIT_EXPORT_REJECTED = "external_audit_export_rejected"
    EXTERNAL_AUDIT_EXPORT_EXPIRED = "external_audit_export_expired"
    EXTERNAL_AUDIT_EXPORT_INVALID = "external_audit_export_invalid"
    EXTERNAL_AUDIT_EXPORT_PACKET_MISSING = "external_audit_export_packet_missing"
    EXTERNAL_AUDIT_EXPORT_PACKET_NOT_READY = "external_audit_export_packet_not_ready"
    EXTERNAL_AUDIT_EXPORT_SENSITIVE_MATERIAL_DETECTED = "external_audit_export_sensitive_material_detected"
    EXTERNAL_AUDIT_EXPORT_RUNTIME_AUTHORITY_DETECTED = "external_audit_export_runtime_authority_detected"
    EXTERNAL_AUDIT_EXPORT_INVOCATION_OVERRIDE_DETECTED = "external_audit_export_invocation_override_detected"
    EXTERNAL_AUDIT_EXPORT_IO_ATTEMPT_DETECTED = "external_audit_export_io_attempt_detected"


class ExternalAuditExportDecision:
    APPROVE_METADATA_EXPORT_REVIEW = "approve_metadata_export_review"
    APPROVE_WITH_CONDITIONS = "approve_with_conditions"
    REJECT_EXPORT = "reject_export"
    REQUEST_MORE_REDACTION = "request_more_redaction"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"
    NO_DECISION = "no_decision"


class ExternalAuditExportScope:
    EXTERNAL_AUDIT_METADATA_EXPORT_RECEIPT = "external_audit_metadata_export_receipt"
    INTERNAL_AUDIT_METADATA_EXPORT_RECEIPT = "internal_audit_metadata_export_receipt"
    SECURITY_REVIEW_EXPORT_RECEIPT = "security_review_export_receipt"
    INVOCATION_DENIAL_AUDIT_EXPORT_RECEIPT = "invocation_denial_audit_export_receipt"
    LIVE_EXTERNAL_DELIVERY_FORBIDDEN = "live_external_delivery_forbidden"
    PROVIDER_SUBMISSION_FORBIDDEN = "provider_submission_forbidden"
    NETWORK_UPLOAD_FORBIDDEN = "network_upload_forbidden"
    EMAIL_DELIVERY_FORBIDDEN = "email_delivery_forbidden"
    WEBHOOK_DELIVERY_FORBIDDEN = "webhook_delivery_forbidden"
    FILE_WRITE_FORBIDDEN = "file_write_forbidden"
    OBJECT_STORAGE_FORBIDDEN = "object_storage_forbidden"
    TOOL_OR_ACTION_FORBIDDEN = "tool_or_action_forbidden"


@dataclass(frozen=True)
class ExternalAuditExportFinding:
    code: str
    category: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ExternalAuditExportConstraint:
    code: str
    category: str = "metadata_export"
    required: bool = True
    accepted: bool = False


@dataclass(frozen=True)
class ExternalAuditExportRedactionSummary:
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
    required_redaction_rejected: bool = False


@dataclass(frozen=True)
class ExternalAuditExportEvidenceSummary:
    evidence_link_count: int = 0
    included_evidence_link_count: int = 0
    redacted_evidence_link_count: int = 0
    finding_summary_count: int = 0
    constraint_summary_count: int = 0
    gap_summary_count: int = 0
    digest_chain_complete: bool = False
    packet_ready_for_review: bool = False


@dataclass(frozen=True)
class ExternalAuditExportExpiration:
    reviewed_at: str = ""
    expires_at: str = ""
    ttl_seconds: int | None = None


@dataclass(frozen=True)
class ExternalAuditExportReceipt:
    export_receipt_id: str
    export_status: str
    export_scope: str
    decision: str
    exporter_ref: str
    export_label: str
    external_review_packet_id: str
    external_review_packet_status: str
    external_review_packet_digest: str
    expected_packet_digest: str = ""
    packet_digest_match: bool = True
    invocation_denial_review_receipt_id: str = ""
    invocation_denial_review_digest: str = ""
    readiness_id: str = ""
    readiness_digest: str = ""
    evidence_summary: ExternalAuditExportEvidenceSummary = field(default_factory=ExternalAuditExportEvidenceSummary)
    redaction_summary: ExternalAuditExportRedactionSummary = field(default_factory=ExternalAuditExportRedactionSummary)
    approved_constraint_codes: tuple[str, ...] = field(default_factory=tuple)
    rejected_constraint_codes: tuple[str, ...] = field(default_factory=tuple)
    accepted_redaction_codes: tuple[str, ...] = field(default_factory=tuple)
    rejected_redaction_codes: tuple[str, ...] = field(default_factory=tuple)
    accepted_evidence_codes: tuple[str, ...] = field(default_factory=tuple)
    rejected_evidence_codes: tuple[str, ...] = field(default_factory=tuple)
    exported_body_included: bool = False
    export_io_performed: bool = False
    external_delivery_performed: bool = False
    network_upload_performed: bool = False
    email_delivery_performed: bool = False
    webhook_delivery_performed: bool = False
    file_write_performed: bool = False
    object_storage_write_performed: bool = False
    packet_body_included: bool = False
    artifact_bodies_included: bool = False
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
    expiration: ExternalAuditExportExpiration = field(default_factory=ExternalAuditExportExpiration)
    expired: bool = False
    findings: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    constraints: tuple[ExternalAuditExportConstraint, ...] = field(default_factory=tuple)
    rationale: str = ""
    export_receipt_digest: str = ""
    external_audit_export_receipt_only: bool = True
    metadata_only: bool = True
    export_io_not_performed: bool = True
    external_delivery_not_performed: bool = True
    invocation_denial_preserved: bool = True
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
        ExternalAuditExportScope.EXTERNAL_AUDIT_METADATA_EXPORT_RECEIPT,
        ExternalAuditExportScope.INTERNAL_AUDIT_METADATA_EXPORT_RECEIPT,
        ExternalAuditExportScope.SECURITY_REVIEW_EXPORT_RECEIPT,
        ExternalAuditExportScope.INVOCATION_DENIAL_AUDIT_EXPORT_RECEIPT,
    }
)
_FORBIDDEN_SCOPES = frozenset(
    {
        ExternalAuditExportScope.LIVE_EXTERNAL_DELIVERY_FORBIDDEN,
        ExternalAuditExportScope.PROVIDER_SUBMISSION_FORBIDDEN,
        ExternalAuditExportScope.NETWORK_UPLOAD_FORBIDDEN,
        ExternalAuditExportScope.EMAIL_DELIVERY_FORBIDDEN,
        ExternalAuditExportScope.WEBHOOK_DELIVERY_FORBIDDEN,
        ExternalAuditExportScope.FILE_WRITE_FORBIDDEN,
        ExternalAuditExportScope.OBJECT_STORAGE_FORBIDDEN,
        ExternalAuditExportScope.TOOL_OR_ACTION_FORBIDDEN,
    }
)
_APPROVING_DECISIONS = frozenset({ExternalAuditExportDecision.APPROVE_METADATA_EXPORT_REVIEW, ExternalAuditExportDecision.APPROVE_WITH_CONDITIONS})
_REQUIRED_REDACTION_CODES = frozenset(
    {
        "prompt_text_removed",
        "raw_payloads_removed",
        "secrets_removed",
        "endpoints_removed",
        "clients_removed",
        "network_handles_removed",
        "runtime_handles_removed",
        "provider_params_removed",
        "tool_schemas_removed",
        "hidden_chain_of_thought_removed",
    }
)
_IO_FIELDS = (
    "exported_body_included",
    "export_io_performed",
    "external_delivery_performed",
    "network_upload_performed",
    "email_delivery_performed",
    "webhook_delivery_performed",
    "file_write_performed",
    "object_storage_write_performed",
)
_SENSITIVE_FIELDS = (
    "packet_body_included",
    "artifact_bodies_included",
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
    ("io", ("upload", "send", "deliver", "email", "webhook", "bucket", "object storage", "s3://", "gs://", "file://", "path=", "destination", "recipient")),
    ("prompt_text", ("prompt_text", "internal_candidate_text", "synthetic_prompt_text", "dry_run_prompt_text", "final_prompt_text", "assembled_prompt", "system_prompt", "developer_prompt")),
    ("hidden_chain_of_thought", ("chain_of_thought", "hidden reasoning", "scratchpad")),
    ("secrets", ("api_key", "bearer", "token", "secret", "password", "private_key", "authorization")),
    ("endpoints", ("https://", "http://", "endpoint", "base_url", "host", "port", "dns", "resolve")),
    ("clients", ("client", "session", "transport", "stream", "retry", "request builder", "sdk", "openai", "anthropic")),
    ("runtime", ("runtime handle", "raw_payload", "tool schema", "function call", "action", "retention", "routing", "memory write")),
    ("provider_invocation", ("invoke", "send_to_provider", "chat.completions", "completion")),
)
_NEGATIVE_TOKENS = ("no_", "no ", "forbidden", "does_not_", "does not", "metadata_only", "denied", "not_invocable", "_included=false", "_allowed=false", "_performed=false", "not_performed")


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


def _digest_payload(receipt: ExternalAuditExportReceipt | Mapping[str, Any]) -> Mapping[str, Any]:
    data = dict(_mapping(receipt))
    data.pop("export_receipt_id", None)
    data.pop("export_receipt_digest", None)
    return data


def compute_external_audit_export_receipt_digest(receipt: ExternalAuditExportReceipt | Mapping[str, Any]) -> str:
    return _stable_digest(_digest_payload(receipt))


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
    return f"{prefix}:empty"


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
                        index = text.find(marker, index + 1)
    return counts


def _evidence_summary(packet: ExternalSecurityReviewPacket | Mapping[str, Any] | None) -> ExternalAuditExportEvidenceSummary:
    data = _mapping(packet)
    links = tuple(data.get("evidence_links", ()) or ())
    return ExternalAuditExportEvidenceSummary(
        evidence_link_count=len(links),
        included_evidence_link_count=sum(1 for link in links if bool(_mapping(link).get("included", True))),
        redacted_evidence_link_count=sum(1 for link in links if bool(_mapping(link).get("redacted", False))),
        finding_summary_count=len(tuple(data.get("finding_summaries", ()) or ())),
        constraint_summary_count=len(tuple(data.get("constraint_summaries", ()) or ())),
        gap_summary_count=len(tuple(data.get("gap_summaries", ()) or ())),
        digest_chain_complete=bool(data.get("digest_chain_complete", False)),
        packet_ready_for_review=external_security_review_packet_ready_for_review(packet) if data else False,
    )


def _redaction_summary(packet: ExternalSecurityReviewPacket | Mapping[str, Any] | None, rejected_redaction_codes: tuple[str, ...]) -> ExternalAuditExportRedactionSummary:
    redaction_data = _mapping(_mapping(packet).get("redaction_summary", {}))
    rejected = set(rejected_redaction_codes)
    return ExternalAuditExportRedactionSummary(
        prompt_text_removed=int(redaction_data.get("prompt_text_removed", 0) or 0),
        raw_payloads_removed=int(redaction_data.get("raw_payloads_removed", 0) or 0),
        secrets_removed=int(redaction_data.get("secrets_removed", 0) or 0),
        endpoints_removed=int(redaction_data.get("endpoints_removed", 0) or 0),
        clients_removed=int(redaction_data.get("clients_removed", 0) or 0),
        network_handles_removed=int(redaction_data.get("network_handles_removed", 0) or 0),
        runtime_handles_removed=int(redaction_data.get("runtime_handles_removed", 0) or 0),
        provider_params_removed=int(redaction_data.get("provider_params_removed", 0) or 0),
        tool_schemas_removed=int(redaction_data.get("tool_schemas_removed", 0) or 0),
        hidden_chain_of_thought_removed=int(redaction_data.get("hidden_chain_of_thought_removed", 0) or 0),
        required_redaction_rejected=bool(_REQUIRED_REDACTION_CODES & rejected),
    )


def _status_from_findings(findings: tuple[str, ...], decision: str, expired: bool) -> str:
    if expired:
        return ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_EXPIRED
    if any(code.startswith("packet_missing") for code in findings):
        return ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_PACKET_MISSING
    if any("invocation_override" in code or "metadata_marker_detected:provider_invocation" in code for code in findings):
        return ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_INVOCATION_OVERRIDE_DETECTED
    if any("io_attempt" in code or code.startswith("forbidden_scope") or "metadata_marker_detected:io" in code for code in findings):
        return ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_IO_ATTEMPT_DETECTED
    if any("runtime" in code or "allowance" in code or "metadata_marker_detected:runtime" in code for code in findings):
        return ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_RUNTIME_AUTHORITY_DETECTED
    if any("sensitive" in code or "included" in code or "redaction" in code or "metadata_marker_detected:prompt_text" in code or "metadata_marker_detected:hidden_chain_of_thought" in code or "metadata_marker_detected:secrets" in code or "metadata_marker_detected:endpoints" in code or "metadata_marker_detected:clients" in code for code in findings):
        return ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_SENSITIVE_MATERIAL_DETECTED
    if any("packet_not_ready" in code or "packet_digest_mismatch" in code for code in findings):
        return ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_PACKET_NOT_READY
    if any(code.startswith("invalid") or code.startswith("missing_exporter") or code.startswith("unknown_scope") for code in findings):
        return ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_INVALID
    if decision in {ExternalAuditExportDecision.REJECT_EXPORT, ExternalAuditExportDecision.REQUEST_MORE_REDACTION, ExternalAuditExportDecision.REQUEST_MORE_EVIDENCE, ExternalAuditExportDecision.NO_DECISION}:
        return ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_REJECTED
    if decision == ExternalAuditExportDecision.APPROVE_WITH_CONDITIONS:
        return ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_READY_WITH_CONDITIONS
    return ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_READY


def build_external_audit_export_receipt(
    external_review_packet: ExternalSecurityReviewPacket | Mapping[str, Any] | None,
    *,
    exporter_ref: str,
    decision: str = ExternalAuditExportDecision.NO_DECISION,
    export_scope: str = ExternalAuditExportScope.EXTERNAL_AUDIT_METADATA_EXPORT_RECEIPT,
    approved_constraint_codes: Sequence[str] = (),
    rejected_constraint_codes: Sequence[str] = (),
    accepted_redaction_codes: Sequence[str] = (),
    rejected_redaction_codes: Sequence[str] = (),
    accepted_evidence_codes: Sequence[str] = (),
    rejected_evidence_codes: Sequence[str] = (),
    rationale: str = "",
    expires_at: str = "",
    ttl_seconds: int | None = None,
    expected_packet_digest: str = "",
    export_label: str = "",
    reviewed_at: str = "",
    expired: bool = False,
    export_receipt_id: str = "",
    **flag_overrides: Any,
) -> ExternalAuditExportReceipt:
    packet_data = _mapping(external_review_packet)
    packet_digest = str(packet_data.get("external_review_packet_digest", "")) if packet_data else ""
    if packet_data and not packet_digest:
        packet_digest = compute_external_security_review_packet_digest(external_review_packet)  # deterministic metadata digest only
    expected_match = not expected_packet_digest or expected_packet_digest == packet_digest
    accepted_redactions = _dedupe(_tuple_str(accepted_redaction_codes))
    rejected_redactions = _dedupe(_tuple_str(rejected_redaction_codes))
    evidence_summary = _evidence_summary(external_review_packet)
    redaction_summary = _redaction_summary(external_review_packet, rejected_redactions)
    findings: list[str] = []
    warnings: list[str] = []

    if not packet_data:
        findings.append("packet_missing")
    elif not external_security_review_packet_ready_for_review(external_review_packet):
        findings.append("packet_not_ready")
    if packet_data and not external_security_review_packet_is_metadata_only(external_review_packet):
        findings.append("packet_not_metadata_only")
    if packet_data and not external_security_review_packet_preserves_invocation_denial(external_review_packet):
        findings.append("invocation_override_detected")
    if packet_data and not external_security_review_packet_contains_no_prompt_text(external_review_packet):
        findings.append("sensitive_material:prompt_text")
    if packet_data and not external_security_review_packet_contains_no_secrets(external_review_packet):
        findings.append("sensitive_material:secrets")
    if packet_data and not external_security_review_packet_contains_no_endpoints(external_review_packet):
        findings.append("sensitive_material:endpoints")
    if packet_data and not external_security_review_packet_contains_no_clients(external_review_packet):
        findings.append("sensitive_material:clients")
    if packet_data and not external_security_review_packet_contains_no_network_handles(external_review_packet):
        findings.append("runtime_authority:network_handles")
    if packet_data and not external_security_review_packet_contains_no_runtime_authority(external_review_packet):
        findings.append("runtime_authority:runtime_or_provider_material")
    if expected_packet_digest and not expected_match:
        findings.append("packet_digest_mismatch")
    if not str(exporter_ref).strip():
        findings.append("missing_exporter_ref")
    if export_scope in _FORBIDDEN_SCOPES:
        findings.append(f"forbidden_scope:{export_scope}")
    elif export_scope not in _ALLOWED_SCOPES:
        findings.append(f"unknown_scope:{export_scope}")
    if decision not in _APPROVING_DECISIONS:
        warnings.append(f"decision_not_approval:{decision}")
    if redaction_summary.required_redaction_rejected:
        findings.append("required_redaction_rejected")

    override_counts = _scan_categories(exporter_ref, export_label, rationale)
    for category, count in sorted(override_counts.items()):
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

    status = _status_from_findings(_dedupe(findings), decision, expired)
    constraints = tuple(
        ExternalAuditExportConstraint(code=code, category="export_constraint", required=True, accepted=code in set(_tuple_str(approved_constraint_codes)))
        for code in _dedupe(_tuple_str(approved_constraint_codes) + _tuple_str(rejected_constraint_codes) + ("metadata_only", "export_io_not_performed", "provider_invocation_forbidden"))
    )
    receipt = ExternalAuditExportReceipt(
        export_receipt_id=export_receipt_id or "external-audit-export-receipt:pending-digest",
        export_status=status,
        export_scope=export_scope,
        decision=decision,
        exporter_ref=str(exporter_ref),
        export_label=str(export_label),
        external_review_packet_id=str(packet_data.get("external_review_packet_id", "")),
        external_review_packet_status=str(packet_data.get("packet_status", "")),
        external_review_packet_digest=packet_digest,
        expected_packet_digest=str(expected_packet_digest),
        packet_digest_match=expected_match,
        invocation_denial_review_receipt_id=str(packet_data.get("invocation_denial_review_receipt_id", "")),
        invocation_denial_review_digest=str(packet_data.get("invocation_denial_review_digest", "")),
        readiness_id=str(packet_data.get("readiness_id", "")),
        readiness_digest=str(packet_data.get("readiness_digest", "")),
        evidence_summary=evidence_summary,
        redaction_summary=redaction_summary,
        approved_constraint_codes=_dedupe(_tuple_str(approved_constraint_codes)),
        rejected_constraint_codes=_dedupe(_tuple_str(rejected_constraint_codes)),
        accepted_redaction_codes=accepted_redactions,
        rejected_redaction_codes=rejected_redactions,
        accepted_evidence_codes=_dedupe(_tuple_str(accepted_evidence_codes)),
        rejected_evidence_codes=_dedupe(_tuple_str(rejected_evidence_codes)),
        expiration=ExternalAuditExportExpiration(reviewed_at=str(reviewed_at), expires_at=str(expires_at), ttl_seconds=ttl_seconds),
        expired=expired,
        findings=_dedupe(findings),
        warnings=_dedupe(warnings) or ("external_audit_export_receipt_is_metadata_only", "export_io_not_performed", "provider_invocation_remains_forbidden"),
        constraints=constraints,
        rationale=str(rationale),
        metadata_only=not any(field_values.values()) and not override_counts,
        export_io_not_performed=not any(field_values[field_name] for field_name in _IO_FIELDS),
        external_delivery_not_performed=not any(field_values[field_name] for field_name in ("external_delivery_performed", "network_upload_performed", "email_delivery_performed", "webhook_delivery_performed")),
        invocation_denial_preserved=bool(packet_data and external_security_review_packet_preserves_invocation_denial(external_review_packet) and not field_values["invocation_allowed"] and not field_values["provider_send_allowed"]),
        no_prompt_text=not field_values["prompt_text_included"],
        no_raw_payloads=not field_values["raw_payloads_included"],
        no_secret_material=not field_values["secrets_included"] and not field_values["secret_references_included"],
        no_endpoint_material=not field_values["endpoints_included"] and not field_values["endpoint_references_included"],
        no_client_material=not field_values["clients_included"] and not field_values["client_references_included"],
        no_network_handles=not field_values["network_handles_included"],
        no_runtime_handles=not field_values["runtime_handles_included"],
        no_provider_params=not field_values["provider_params_included"],
        no_tool_schemas=not field_values["tool_schemas_included"],
        no_hidden_chain_of_thought=not field_values["hidden_chain_of_thought_included"],
        **field_values,
    )
    digest = compute_external_audit_export_receipt_digest(receipt)
    return replace(receipt, export_receipt_id=export_receipt_id or f"external-audit-export-receipt:{digest[-16:]}", export_receipt_digest=digest)


def validate_external_audit_export_receipt(receipt: ExternalAuditExportReceipt | Mapping[str, Any]) -> tuple[ExternalAuditExportFinding, ...]:
    data = _mapping(receipt)
    if not data:
        return (ExternalAuditExportFinding(code="receipt_malformed", category="input"),)
    findings: list[ExternalAuditExportFinding] = []
    if str(data.get("export_status", "")) in {ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_READY, ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_READY_WITH_CONDITIONS}:
        if not external_audit_export_receipt_ready_for_export_review(receipt):
            findings.append(ExternalAuditExportFinding(code="ready_status_but_not_ready", category="gating"))
    if str(data.get("export_receipt_digest", "")) != compute_external_audit_export_receipt_digest(receipt):
        findings.append(ExternalAuditExportFinding(code="receipt_digest_mismatch", category="digest"))
    for field_name in _IO_FIELDS:
        if bool(data.get(field_name, False)):
            findings.append(ExternalAuditExportFinding(code=f"io_attempt:{field_name}", category="export_io"))
    for field_name in _SENSITIVE_FIELDS:
        if bool(data.get(field_name, False)):
            findings.append(ExternalAuditExportFinding(code=f"sensitive_material_included:{field_name}", category="sensitive_material"))
    for field_name in _ALLOWANCE_FIELDS:
        if bool(data.get(field_name, False)):
            findings.append(ExternalAuditExportFinding(code=f"runtime_authority_allowed:{field_name}", category="runtime_authority"))
    return tuple(findings)


def external_audit_export_receipt_is_metadata_only(receipt: ExternalAuditExportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data and data.get("metadata_only") is True and all(data.get(field_name) is False for field_name in _SENSITIVE_FIELDS + _ALLOWANCE_FIELDS))


def external_audit_export_receipt_does_not_export(receipt: ExternalAuditExportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data and data.get("export_io_not_performed") is True and data.get("external_delivery_not_performed") is True and all(data.get(field_name) is False for field_name in _IO_FIELDS))


def external_audit_export_receipt_contains_no_prompt_text(receipt: ExternalAuditExportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data and data.get("no_prompt_text") is True and data.get("prompt_text_included") is False)


def external_audit_export_receipt_contains_no_secrets(receipt: ExternalAuditExportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data and data.get("no_secret_material") is True and data.get("secrets_included") is False and data.get("secret_references_included") is False)


def external_audit_export_receipt_contains_no_endpoints(receipt: ExternalAuditExportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data and data.get("no_endpoint_material") is True and data.get("endpoints_included") is False and data.get("endpoint_references_included") is False)


def external_audit_export_receipt_contains_no_clients(receipt: ExternalAuditExportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data and data.get("no_client_material") is True and data.get("clients_included") is False and data.get("client_references_included") is False)


def external_audit_export_receipt_contains_no_network_handles(receipt: ExternalAuditExportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data and data.get("no_network_handles") is True and data.get("network_handles_included") is False and data.get("network_allowed") is False)


def external_audit_export_receipt_contains_no_runtime_authority(receipt: ExternalAuditExportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data and data.get("no_runtime_handles") is True and data.get("runtime_handles_included") is False and all(data.get(field_name) is False for field_name in _ALLOWANCE_FIELDS))


def external_audit_export_receipt_preserves_invocation_denial(receipt: ExternalAuditExportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(data and data.get("invocation_denial_preserved") is True and data.get("provider_invocation_forbidden") is True and data.get("actual_provider_invocation_forbidden") is True and data.get("invocation_allowed") is False and data.get("provider_send_allowed") is False)


def external_audit_export_receipt_ready_for_export_review(receipt: ExternalAuditExportReceipt | Mapping[str, Any]) -> bool:
    data = _mapping(receipt)
    return bool(
        data
        and data.get("export_status") in {ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_READY, ExternalAuditExportStatus.EXTERNAL_AUDIT_EXPORT_READY_WITH_CONDITIONS}
        and external_audit_export_receipt_is_metadata_only(receipt)
        and external_audit_export_receipt_does_not_export(receipt)
        and external_audit_export_receipt_preserves_invocation_denial(receipt)
        and not data.get("expired", False)
    )


def explain_external_audit_export_receipt_findings(receipt: ExternalAuditExportReceipt | Mapping[str, Any]) -> tuple[str, ...]:
    data = _mapping(receipt)
    if not data:
        return ("receipt_malformed",)
    return _dedupe(_tuple_str(data.get("findings", ())) + tuple(finding.code for finding in validate_external_audit_export_receipt(receipt)))


def summarize_external_audit_export_receipt(receipt: ExternalAuditExportReceipt | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(receipt)
    evidence = _mapping(data.get("evidence_summary", {}))
    redaction = _mapping(data.get("redaction_summary", {}))
    return {
        "export_receipt_id": data.get("export_receipt_id", ""),
        "export_status": data.get("export_status", ""),
        "export_scope": data.get("export_scope", ""),
        "decision": data.get("decision", ""),
        "exporter_ref": data.get("exporter_ref", ""),
        "external_review_packet_id": data.get("external_review_packet_id", ""),
        "external_review_packet_digest": data.get("external_review_packet_digest", ""),
        "evidence_link_count": evidence.get("evidence_link_count", 0),
        "redaction_removed_total": sum(int(redaction.get(name, 0) or 0) for name in _REQUIRED_REDACTION_CODES if name in redaction),
        "metadata_only": data.get("metadata_only", False),
        "export_io_not_performed": data.get("export_io_not_performed", False),
        "invocation_denial_preserved": data.get("invocation_denial_preserved", False),
        "provider_invocation_forbidden": data.get("provider_invocation_forbidden", False),
        "export_receipt_digest": data.get("export_receipt_digest", ""),
    }
