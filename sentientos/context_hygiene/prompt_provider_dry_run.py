from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_internal_candidate import (
    InternalPromptCandidate,
    InternalPromptCandidateStatus,
    compute_internal_prompt_candidate_digest,
)
from sentientos.context_hygiene.prompt_internal_display import (
    InternalPromptDisplayReceipt,
    InternalPromptDisplayStatus,
    compute_internal_prompt_display_receipt_digest,
    internal_prompt_candidate_may_be_displayed,
    internal_prompt_display_has_no_model_egress,
    internal_prompt_display_has_no_runtime_authority,
)
from sentientos.context_hygiene.prompt_model_call_preflight import (
    InternalModelCallPreflight,
    InternalModelCallPreflightStatus,
    compute_internal_model_call_preflight_digest,
    internal_model_call_preflight_allows_review_gate,
    internal_model_call_preflight_forbids_provider_call,
    internal_model_call_preflight_has_no_runtime_authority,
)
from sentientos.context_hygiene.prompt_model_call_review import (
    InternalModelCallReviewReceipt,
    compute_internal_model_call_review_digest,
    internal_model_call_review_satisfies_preflight,
)


class ProviderDryRunStatus:
    PROVIDER_DRY_RUN_READY = "provider_dry_run_ready"
    PROVIDER_DRY_RUN_READY_WITH_WARNINGS = "provider_dry_run_ready_with_warnings"
    PROVIDER_DRY_RUN_BLOCKED = "provider_dry_run_blocked"
    PROVIDER_DRY_RUN_INVALID_INPUT = "provider_dry_run_invalid_input"
    PROVIDER_DRY_RUN_REVIEW_MISSING = "provider_dry_run_review_missing"
    PROVIDER_DRY_RUN_PREFLIGHT_NOT_READY = "provider_dry_run_preflight_not_ready"
    PROVIDER_DRY_RUN_SEND_FORBIDDEN = "provider_dry_run_send_forbidden"
    PROVIDER_DRY_RUN_RUNTIME_AUTHORITY_DETECTED = "provider_dry_run_runtime_authority_detected"
    PROVIDER_DRY_RUN_CREDENTIALS_DETECTED = "provider_dry_run_credentials_detected"
    PROVIDER_DRY_RUN_NETWORK_EGRESS_DETECTED = "provider_dry_run_network_egress_detected"


class ProviderDryRunProviderFamily:
    PROVIDER_FAMILY_OPENAI_LABEL_ONLY = "provider_family_openai_label_only"
    PROVIDER_FAMILY_LOCAL_LABEL_ONLY = "provider_family_local_label_only"
    PROVIDER_FAMILY_UNKNOWN_FORBIDDEN = "provider_family_unknown_forbidden"


class ProviderDryRunModelFamily:
    MODEL_FAMILY_REASONING_LABEL_ONLY = "model_family_reasoning_label_only"
    MODEL_FAMILY_CHAT_LABEL_ONLY = "model_family_chat_label_only"
    MODEL_FAMILY_UNKNOWN_FORBIDDEN = "model_family_unknown_forbidden"


class ProviderDryRunScope:
    INTERNAL_REVIEW_ONLY = "internal_review_only"


@dataclass(frozen=True)
class ProviderDryRunFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderDryRunConstraint:
    code: str
    detail: str
    required: bool = True


@dataclass(frozen=True)
class ProviderDryRunBoundary:
    provider_dry_run_only: bool = True
    non_sendable: bool = True
    provider_send_forbidden: bool = True
    network_egress_forbidden: bool = True
    credentials_forbidden: bool = True
    provider_client_absent: bool = True
    endpoint_absent: bool = True
    api_key_absent: bool = True
    tool_calls_forbidden: bool = True
    memory_forbidden: bool = True
    retention_forbidden: bool = True
    action_execution_forbidden: bool = True
    routing_forbidden: bool = True
    does_not_call_llm: bool = True
    does_not_send_to_provider: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True


@dataclass(frozen=True)
class ProviderDryRunPayload:
    payload_kind: str = "non_sendable_provider_dry_run_shape"
    entries: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    digest_refs: Mapping[str, str] = field(default_factory=dict)
    metadata_tags: tuple[str, ...] = field(default_factory=tuple)
    provider_send_forbidden: bool = True
    network_egress_forbidden: bool = True
    non_sendable: bool = True


@dataclass(frozen=True)
class ProviderDryRunRequestEnvelope:
    dry_run_id: str
    dry_run_status: str
    provider_family_label: str
    model_family_label: str
    request_purpose: str
    dry_run_scope: str
    candidate_id: str
    candidate_digest: str
    display_receipt_id: str
    display_receipt_digest: str
    preflight_id: str
    preflight_digest: str
    review_receipt_id: str
    review_digest: str
    packet_id: str
    packet_scope: str
    candidate_text_digest: str
    candidate_text_length: int
    dry_run_payload_shape: ProviderDryRunPayload
    dry_run_prompt_text: str
    metadata_parameters: Mapping[str, Any]
    findings: tuple[ProviderDryRunFinding, ...]
    warnings: tuple[str, ...]
    constraints: tuple[ProviderDryRunConstraint, ...]
    rationale: str
    dry_run_digest: str
    provider_dry_run_only: bool = True
    non_sendable: bool = True
    provider_send_forbidden: bool = True
    network_egress_forbidden: bool = True
    credentials_forbidden: bool = True
    provider_client_absent: bool = True
    endpoint_absent: bool = True
    api_key_absent: bool = True
    tool_calls_forbidden: bool = True
    memory_forbidden: bool = True
    retention_forbidden: bool = True
    action_execution_forbidden: bool = True
    routing_forbidden: bool = True
    does_not_call_llm: bool = True
    does_not_send_to_provider: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True
    boundary: ProviderDryRunBoundary = field(default_factory=ProviderDryRunBoundary)


_KNOWN_PROVIDER_FAMILIES = frozenset(
    {
        ProviderDryRunProviderFamily.PROVIDER_FAMILY_OPENAI_LABEL_ONLY,
        ProviderDryRunProviderFamily.PROVIDER_FAMILY_LOCAL_LABEL_ONLY,
    }
)
_KNOWN_MODEL_FAMILIES = frozenset(
    {
        ProviderDryRunModelFamily.MODEL_FAMILY_REASONING_LABEL_ONLY,
        ProviderDryRunModelFamily.MODEL_FAMILY_CHAT_LABEL_ONLY,
    }
)
_READY_CANDIDATE_STATUSES = frozenset(
    {
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_READY,
        InternalPromptCandidateStatus.INTERNAL_PROMPT_CANDIDATE_READY_WITH_WARNINGS,
    }
)
_READY_DISPLAY_STATUSES = frozenset(
    {
        InternalPromptDisplayStatus.DISPLAY_ALLOWED,
        InternalPromptDisplayStatus.DISPLAY_ALLOWED_WITH_WARNINGS,
    }
)
_READY_PREFLIGHT_STATUSES = frozenset(
    {
        InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_FOR_REVIEW,
        InternalModelCallPreflightStatus.MODEL_CALL_PREFLIGHT_READY_WITH_WARNINGS,
    }
)
_READY_DRY_RUN_STATUSES = frozenset(
    {
        ProviderDryRunStatus.PROVIDER_DRY_RUN_READY,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_READY_WITH_WARNINGS,
    }
)
_CREDENTIAL_MARKERS = ("api_key", "apikey", "secret", "credential", "token", "authorization", "bearer", "auth", "header")
_NETWORK_MARKERS = ("endpoint", "url", "uri", "host", "base_url", "webhook", "http", "https")
_PROVIDER_OBJECT_MARKERS = ("client", "session", "transport", "sdk", "connection")
_RUNTIME_AUTHORITY_MARKERS = (
    "tool_call",
    "tool_schema",
    "function_call",
    "function_schema",
    "memory_handle",
    "action_handle",
    "retention_handle",
    "routing_handle",
    "retrieval_handle",
    "runtime_handle",
    "execution_handle",
    "runtime_authority",
)
_RAW_OR_PARAM_MARKERS = ("raw_payload", "provider_params", "model_params", "llm_params", "llm_parameters")
_TEXT_REQUIRED_MARKERS = ("internal no-llm candidate", "operator visible only")
_TEXT_NOT_SENT_MARKERS = ("not been sent to a model", "not sent to model")
_MARKER_FIELDS = tuple(ProviderDryRunBoundary.__dataclass_fields__.keys())


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
        return {str(k): _stable(v) for k, v in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(k): _stable(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_stable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_stable(item) for item in value)
    return value


def _walk(value: Any) -> tuple[tuple[str, Any], ...]:
    found: list[tuple[str, Any]] = []

    def visit(child: Any, parent_key: str = "") -> None:
        if _is_dataclass_instance(child):
            visit(asdict(child), parent_key)
        elif isinstance(child, Mapping):
            for key, nested in child.items():
                key_text = str(key)
                found.append((key_text, nested))
                visit(nested, key_text)
        elif isinstance(child, (tuple, list, set, frozenset)):
            for nested in child:
                visit(nested, parent_key)

    visit(value)
    return tuple(found)


def _truthy_forbidden(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and value.strip().lower() not in {"false", "none", "null", "0"}
    if isinstance(value, (tuple, list, set, frozenset, Mapping)):
        return bool(value)
    return bool(value)


def _contains_marker(value: Any, markers: Sequence[str], *, keys_only: bool = False) -> bool:
    for key, nested in _walk(value):
        lowered_key = key.lower()
        lowered_value = "" if keys_only else str(nested).lower()
        for marker in markers:
            if marker == "auth" and ("authority" in lowered_key or (not keys_only and "authority" in lowered_value)):
                continue
            if marker in lowered_key or (not keys_only and marker in lowered_value):
                if _truthy_forbidden(nested) or lowered_value:
                    return True
    if isinstance(value, str) and not keys_only:
        lowered = value.lower()
        return any(marker in lowered for marker in markers)
    return False


def _finding(code: str, detail: str, severity: str = "blocker") -> ProviderDryRunFinding:
    return ProviderDryRunFinding(code=code, detail=detail, severity=severity)


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _candidate_digest(candidate: Any) -> str:
    recorded = str(_mapping(candidate).get("candidate_digest", ""))
    if not recorded:
        return ""
    try:
        return compute_internal_prompt_candidate_digest(candidate)
    except Exception:
        return ""


def _preflight_digest(preflight: Any) -> str:
    recorded = str(_mapping(preflight).get("preflight_digest", ""))
    if not recorded:
        return ""
    try:
        return compute_internal_model_call_preflight_digest(preflight)
    except Exception:
        return ""


def _review_digest(review: Any) -> str:
    recorded = str(_mapping(review).get("review_digest", ""))
    if not recorded:
        return ""
    try:
        return compute_internal_model_call_review_digest(review)
    except Exception:
        return ""


def _base_constraints() -> tuple[ProviderDryRunConstraint, ...]:
    return (
        ProviderDryRunConstraint("non_sendable", "dry-run envelope cannot be sent to any provider"),
        ProviderDryRunConstraint("provider_send_forbidden", "provider/model egress remains forbidden"),
        ProviderDryRunConstraint("network_egress_forbidden", "network egress fields and calls are forbidden"),
        ProviderDryRunConstraint("credentials_forbidden", "credentials and provider clients are forbidden"),
        ProviderDryRunConstraint("runtime_authority_forbidden", "tools, memory, actions, retention, routing, and admission are forbidden"),
    )


def _metadata_parameters(max_output_tokens_metadata: int | None, temperature_metadata: float | None, extra_metadata: Mapping[str, Any] | None) -> Mapping[str, Any]:
    data: dict[str, Any] = {
        "parameter_metadata_only": True,
        "not_used_for_provider_call": True,
    }
    if max_output_tokens_metadata is not None:
        data["max_output_tokens_metadata"] = int(max_output_tokens_metadata)
    if temperature_metadata is not None:
        data["temperature_metadata"] = float(temperature_metadata)
    if extra_metadata:
        data.update({str(key): _stable(value) for key, value in extra_metadata.items()})
    return data


def _dry_run_text(candidate_text: str) -> str:
    return "\n".join(
        (
            "NON-SENDABLE PROVIDER DRY RUN — DO NOT SEND TO PROVIDER OR MODEL.",
            "Provider dry-run request envelope only; network egress, LLM calls, tools, memory, retention, actions, routing, admission, and feedback are forbidden.",
            "Dry-run internal candidate follows:",
            candidate_text,
        )
    )


def _payload_shape(dry_run_prompt_text: str, refs: Mapping[str, str]) -> ProviderDryRunPayload:
    return ProviderDryRunPayload(
        entries=(
            {
                "dry_run_label": "dry_run_boundary_notes",
                "content": "non-sendable provider dry-run only; provider roles and transport fields are intentionally absent",
            },
            {
                "dry_run_label": "dry_run_internal_candidate",
                "content": dry_run_prompt_text,
            },
            {
                "dry_run_label": "dry_run_caveats",
                "content": "metadata-only family labels; no provider SDK, no network egress, no runtime authority",
            },
        ),
        digest_refs=dict(refs),
        metadata_tags=("provider_dry_run_only", "non_sendable", "provider_send_forbidden", "network_egress_forbidden"),
    )


def _evaluate_findings(
    *,
    candidate: Any,
    display_receipt: Any,
    preflight: Any,
    review_receipt: Any | None,
    provider_family_label: str,
    model_family_label: str,
    request_purpose: str,
    dry_run_scope: str,
    metadata_parameters: Mapping[str, Any],
    dry_run_prompt_text: str,
    dry_run_payload_shape: ProviderDryRunPayload,
    marker_values: Mapping[str, bool],
) -> tuple[ProviderDryRunFinding, ...]:
    findings: list[ProviderDryRunFinding] = []
    candidate_data = _mapping(candidate)
    display_data = _mapping(display_receipt)
    preflight_data = _mapping(preflight)
    review_data = _mapping(review_receipt)

    if not candidate_data:
        findings.append(_finding("candidate_missing", "Phase 80 InternalPromptCandidate is required"))
    elif str(candidate_data.get("status", "")) not in _READY_CANDIDATE_STATUSES:
        findings.append(_finding("candidate_not_ready", "candidate status is not ready or ready-with-warnings"))
    elif str(candidate_data.get("candidate_digest", "")) != _candidate_digest(candidate):
        findings.append(_finding("candidate_digest_unstable", "candidate digest is missing or unstable"))

    candidate_text = str(candidate_data.get("internal_candidate_text", ""))
    lowered_text = candidate_text.lower()
    for marker in _TEXT_REQUIRED_MARKERS:
        if marker not in lowered_text:
            findings.append(_finding("candidate_text_marker_missing", f"candidate text lacks required marker {marker!r}"))
    if not any(marker in lowered_text for marker in _TEXT_NOT_SENT_MARKERS):
        findings.append(_finding("candidate_text_not_sent_marker_missing", "candidate text must state it was not sent to a model"))
    if _contains_marker(candidate_text, _RAW_OR_PARAM_MARKERS + _RUNTIME_AUTHORITY_MARKERS):
        findings.append(_finding("candidate_text_forbidden_marker", "candidate text contains raw/runtime/provider marker"))

    if not display_data:
        findings.append(_finding("display_receipt_missing", "Phase 81 display receipt is required"))
    elif str(display_data.get("display_status", "")) not in _READY_DISPLAY_STATUSES:
        findings.append(_finding("display_denied", "display receipt does not allow internal display"))
    elif not internal_prompt_candidate_may_be_displayed(display_receipt, candidate):
        findings.append(_finding("display_receipt_not_satisfied", "display receipt does not satisfy candidate display gate"))
    if display_data and str(display_data.get("display_receipt_digest", "")) != compute_internal_prompt_display_receipt_digest(display_receipt):
        findings.append(_finding("display_receipt_digest_unstable", "display receipt digest is unstable"))
    if display_data and not internal_prompt_display_has_no_model_egress(display_receipt):
        findings.append(_finding("display_model_egress_detected", "display receipt permits model/provider egress"))
    if display_data and not internal_prompt_display_has_no_runtime_authority(display_receipt):
        findings.append(_finding("display_runtime_authority_detected", "display receipt permits runtime authority"))

    if not preflight_data:
        findings.append(_finding("preflight_missing", "Phase 82 model-call preflight is required"))
    elif str(preflight_data.get("preflight_status", "")) not in _READY_PREFLIGHT_STATUSES:
        findings.append(_finding("preflight_not_ready", "preflight is not ready-for-review or ready-with-warnings"))
    elif str(preflight_data.get("preflight_digest", "")) != _preflight_digest(preflight):
        findings.append(_finding("preflight_digest_unstable", "preflight digest is missing or unstable"))
    if preflight_data and not internal_model_call_preflight_allows_review_gate(preflight):
        findings.append(_finding("preflight_review_gate_disallowed", "preflight does not allow future internal review gate"))
    if preflight_data and not internal_model_call_preflight_forbids_provider_call(preflight):
        findings.append(_finding("preflight_provider_forbidden_missing", "preflight does not preserve provider-forbidden markers"))
    if preflight_data and not internal_model_call_preflight_has_no_runtime_authority(preflight):
        findings.append(_finding("preflight_runtime_authority_detected", "preflight permits runtime authority"))

    if review_receipt is None:
        findings.append(_finding("review_missing", "Phase 83 model-call review receipt is required"))
    elif not review_data:
        findings.append(_finding("review_invalid", "review receipt is malformed"))
    elif str(review_data.get("review_digest", "")) != _review_digest(review_receipt):
        findings.append(_finding("review_digest_unstable", "review digest is missing or unstable"))
    elif not internal_model_call_review_satisfies_preflight(preflight, review_receipt):
        findings.append(_finding("review_does_not_satisfy_preflight", "review receipt does not satisfy preflight"))

    if provider_family_label not in _KNOWN_PROVIDER_FAMILIES:
        findings.append(_finding("provider_family_unknown", "provider family must be a known label-only value"))
    if model_family_label not in _KNOWN_MODEL_FAMILIES:
        findings.append(_finding("model_family_unknown", "model family must be a known label-only value"))
    if dry_run_scope != ProviderDryRunScope.INTERNAL_REVIEW_ONLY:
        findings.append(_finding("dry_run_scope_forbidden", "dry-run scope must be internal review only"))
    if not str(request_purpose).strip():
        findings.append(_finding("request_purpose_missing", "request_purpose is required as metadata"))

    inspected = (metadata_parameters, dry_run_payload_shape)
    if _contains_marker(inspected, _CREDENTIAL_MARKERS, keys_only=True):
        findings.append(_finding("credentials_detected", "credentials or authorization markers are forbidden"))
    if _contains_marker(inspected, _NETWORK_MARKERS, keys_only=True):
        findings.append(_finding("network_egress_detected", "endpoint, URL, or network markers are forbidden"))
    if _contains_marker(inspected, _PROVIDER_OBJECT_MARKERS, keys_only=True):
        findings.append(_finding("provider_client_detected", "provider client/session/transport markers are forbidden"))
    if _contains_marker(inspected, _RUNTIME_AUTHORITY_MARKERS, keys_only=True):
        findings.append(_finding("runtime_authority_detected", "tool/action/memory/retention/routing/runtime markers are forbidden"))
    if _contains_marker(inspected, _RAW_OR_PARAM_MARKERS, keys_only=True):
        findings.append(_finding("raw_or_parameter_marker_detected", "raw payload and provider/model/LLM parameter markers are forbidden"))

    payload_text = json.dumps(_stable(dry_run_payload_shape), sort_keys=True).lower()
    for forbidden_role in ('"role":"system"', '"role":"developer"', '"role":"assistant"', 'system role', 'developer role'):
        if forbidden_role in payload_text:
            findings.append(_finding("provider_role_detected", "payload shape must use dry-run labels, not provider roles"))
            break

    for marker in _MARKER_FIELDS:
        if marker_values.get(marker) is not True:
            findings.append(_finding("required_marker_false", f"{marker} must be true"))
    return tuple(findings)


def _status_for_findings(findings: Sequence[ProviderDryRunFinding], warnings: Sequence[str], candidate: Any, display_receipt: Any, preflight: Any) -> str:
    codes = {finding.code for finding in findings}
    if "review_missing" in codes:
        return ProviderDryRunStatus.PROVIDER_DRY_RUN_REVIEW_MISSING
    if any(code in codes for code in ("candidate_missing", "preflight_missing", "request_purpose_missing")):
        return ProviderDryRunStatus.PROVIDER_DRY_RUN_INVALID_INPUT
    if any("credentials" in code or "provider_client" in code for code in codes):
        return ProviderDryRunStatus.PROVIDER_DRY_RUN_CREDENTIALS_DETECTED
    if any("network" in code for code in codes):
        return ProviderDryRunStatus.PROVIDER_DRY_RUN_NETWORK_EGRESS_DETECTED
    if any("runtime" in code or "tool" in code or "action" in code or "raw_or_parameter" in code or code == "candidate_text_forbidden_marker" for code in codes):
        return ProviderDryRunStatus.PROVIDER_DRY_RUN_RUNTIME_AUTHORITY_DETECTED
    if "preflight_not_ready" in codes or "preflight_review_gate_disallowed" in codes:
        return ProviderDryRunStatus.PROVIDER_DRY_RUN_PREFLIGHT_NOT_READY
    if any(code in codes for code in ("required_marker_false", "preflight_provider_forbidden_missing")):
        return ProviderDryRunStatus.PROVIDER_DRY_RUN_SEND_FORBIDDEN
    if findings:
        return ProviderDryRunStatus.PROVIDER_DRY_RUN_BLOCKED
    statuses = {
        str(_mapping(candidate).get("status", "")),
        str(_mapping(display_receipt).get("display_status", "")),
        str(_mapping(preflight).get("preflight_status", "")),
    }
    if warnings or any("warnings" in status for status in statuses):
        return ProviderDryRunStatus.PROVIDER_DRY_RUN_READY_WITH_WARNINGS
    return ProviderDryRunStatus.PROVIDER_DRY_RUN_READY


def compute_provider_dry_run_digest(envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any]) -> str:
    data = dict(_mapping(envelope))
    data.pop("dry_run_digest", None)
    data.pop("dry_run_id", None)
    payload = {
        "dry_run_status": data.get("dry_run_status", ""),
        "provider_family_label": data.get("provider_family_label", ""),
        "model_family_label": data.get("model_family_label", ""),
        "request_purpose": data.get("request_purpose", ""),
        "dry_run_scope": data.get("dry_run_scope", ""),
        "candidate_id": data.get("candidate_id", ""),
        "candidate_digest": data.get("candidate_digest", ""),
        "display_receipt_id": data.get("display_receipt_id", ""),
        "display_receipt_digest": data.get("display_receipt_digest", ""),
        "preflight_id": data.get("preflight_id", ""),
        "preflight_digest": data.get("preflight_digest", ""),
        "review_receipt_id": data.get("review_receipt_id", ""),
        "review_digest": data.get("review_digest", ""),
        "packet_id": data.get("packet_id", ""),
        "packet_scope": data.get("packet_scope", ""),
        "candidate_text_digest": data.get("candidate_text_digest", ""),
        "candidate_text_length": int(data.get("candidate_text_length", 0) or 0),
        "dry_run_payload_shape": _stable(data.get("dry_run_payload_shape", {})),
        "dry_run_prompt_text": data.get("dry_run_prompt_text", ""),
        "metadata_parameters": _stable(data.get("metadata_parameters", {})),
        "findings": _stable(data.get("findings", ())),
        "warnings": _stable(data.get("warnings", ())),
        "constraints": _stable(data.get("constraints", ())),
        "rationale": data.get("rationale", ""),
        "markers": {marker: bool(data.get(marker, False)) for marker in _MARKER_FIELDS},
        "boundary": _stable(data.get("boundary", {})),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_provider_dry_run_request_envelope(
    candidate: InternalPromptCandidate | Mapping[str, Any] | None,
    display_receipt: InternalPromptDisplayReceipt | Mapping[str, Any] | None,
    preflight: InternalModelCallPreflight | Mapping[str, Any] | None,
    review_receipt: InternalModelCallReviewReceipt | Mapping[str, Any] | None,
    *,
    provider_family_label: str,
    model_family_label: str,
    request_purpose: str,
    dry_run_scope: str,
    max_output_tokens_metadata: int | None = None,
    temperature_metadata: float | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
    marker_overrides: Mapping[str, bool] | None = None,
) -> ProviderDryRunRequestEnvelope:
    candidate_data = _mapping(candidate)
    display_data = _mapping(display_receipt)
    preflight_data = _mapping(preflight)
    review_data = _mapping(review_receipt)
    candidate_text = str(candidate_data.get("internal_candidate_text", ""))
    dry_run_prompt_text = _dry_run_text(candidate_text)
    metadata = _metadata_parameters(max_output_tokens_metadata, temperature_metadata, extra_metadata)
    refs = {
        "candidate_digest": str(candidate_data.get("candidate_digest", "")),
        "display_receipt_digest": str(display_data.get("display_receipt_digest", "")),
        "preflight_digest": str(preflight_data.get("preflight_digest", "")),
        "review_digest": str(review_data.get("review_digest", "")),
    }
    dry_run_payload_shape = _payload_shape(dry_run_prompt_text, refs)
    marker_values = {field_name: True for field_name in _MARKER_FIELDS}
    if marker_overrides:
        marker_values.update({str(key): bool(value) for key, value in marker_overrides.items() if str(key) in marker_values})
    findings = _evaluate_findings(
        candidate=candidate,
        display_receipt=display_receipt,
        preflight=preflight,
        review_receipt=review_receipt,
        provider_family_label=str(provider_family_label),
        model_family_label=str(model_family_label),
        request_purpose=str(request_purpose),
        dry_run_scope=str(dry_run_scope),
        metadata_parameters=metadata,
        dry_run_prompt_text=dry_run_prompt_text,
        dry_run_payload_shape=dry_run_payload_shape,
        marker_values=marker_values,
    )
    warnings = tuple(str(item) for source in (candidate_data, display_data, preflight_data, review_data) for item in (source.get("warnings", ()) or ()))
    status = _status_for_findings(findings, warnings, candidate, display_receipt, preflight)
    constraints = _base_constraints()
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "provider-shaped dry-run envelope is non-sendable and eligible for internal review only"
    boundary = ProviderDryRunBoundary(**marker_values)
    envelope = ProviderDryRunRequestEnvelope(
        dry_run_id="",
        dry_run_status=status,
        provider_family_label=str(provider_family_label),
        model_family_label=str(model_family_label),
        request_purpose=str(request_purpose),
        dry_run_scope=str(dry_run_scope),
        candidate_id=str(candidate_data.get("candidate_id", "")),
        candidate_digest=str(candidate_data.get("candidate_digest", "")),
        display_receipt_id=str(display_data.get("display_receipt_id", "")),
        display_receipt_digest=str(display_data.get("display_receipt_digest", "")),
        preflight_id=str(preflight_data.get("preflight_id", "")),
        preflight_digest=str(preflight_data.get("preflight_digest", "")),
        review_receipt_id=str(review_data.get("review_receipt_id", "")),
        review_digest=str(review_data.get("review_digest", "")),
        packet_id=str(candidate_data.get("packet_id", preflight_data.get("packet_id", ""))),
        packet_scope=str(candidate_data.get("packet_scope", preflight_data.get("packet_scope", ""))),
        candidate_text_digest=_text_digest(candidate_text),
        candidate_text_length=len(candidate_text),
        dry_run_payload_shape=dry_run_payload_shape,
        dry_run_prompt_text=dry_run_prompt_text,
        metadata_parameters=metadata,
        findings=tuple(findings),
        warnings=warnings,
        constraints=constraints,
        rationale=rationale[:1000],
        dry_run_digest="",
        boundary=boundary,
        **marker_values,
    )
    digest = compute_provider_dry_run_digest(envelope)
    return replace(envelope, dry_run_id=f"provider-dry-run:{envelope.candidate_id or 'missing'}:{digest[:16]}", dry_run_digest=digest)


def validate_provider_dry_run_request_envelope(envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any]) -> tuple[ProviderDryRunFinding, ...]:
    data = _mapping(envelope)
    findings: list[ProviderDryRunFinding] = []
    if not data:
        return (_finding("dry_run_malformed", "provider dry-run envelope is malformed"),)
    expected = compute_provider_dry_run_digest(envelope)
    if str(data.get("dry_run_digest", "")) != expected:
        findings.append(_finding("dry_run_digest_mismatch", "dry-run digest does not match envelope-safe fields"))
    if str(data.get("dry_run_status", "")) in _READY_DRY_RUN_STATUSES and tuple(data.get("findings", ()) or ()): 
        findings.append(_finding("ready_with_blocking_findings", "ready dry-run envelopes must not contain findings"))
    if not provider_dry_run_has_no_provider_credentials(envelope):
        findings.append(_finding("credentials_detected", "credentials are present in dry-run envelope"))
    if not provider_dry_run_has_no_network_egress(envelope):
        findings.append(_finding("network_egress_detected", "network egress markers are present in dry-run envelope"))
    if not provider_dry_run_has_no_runtime_authority(envelope):
        findings.append(_finding("runtime_authority_detected", "runtime authority markers are present in dry-run envelope"))
    return tuple(findings)


def _finding_codes(envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any]) -> set[str]:
    return {str(_mapping(finding).get("code", "")) for finding in (_mapping(envelope).get("findings", ()) or ())}


def provider_dry_run_is_non_sendable(envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any]) -> bool:
    data = _mapping(envelope)
    if str(data.get("dry_run_status", "")) not in _READY_DRY_RUN_STATUSES:
        return False
    required = (
        "non_sendable",
        "provider_send_forbidden",
        "network_egress_forbidden",
        "provider_client_absent",
        "endpoint_absent",
        "api_key_absent",
        "does_not_send_to_provider",
        "does_not_call_llm",
    )
    codes = _finding_codes(envelope)
    return bool(all(data.get(marker) is True for marker in required) and not any(code in codes for code in ("credentials_detected", "network_egress_detected", "provider_client_detected")))


def provider_dry_run_has_no_provider_credentials(envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any]) -> bool:
    return not _contains_marker((_mapping(envelope).get("metadata_parameters", {}), _mapping(envelope).get("dry_run_payload_shape", {})), _CREDENTIAL_MARKERS, keys_only=True)


def provider_dry_run_has_no_network_egress(envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any]) -> bool:
    data = _mapping(envelope)
    return bool(data.get("network_egress_forbidden") is True and data.get("endpoint_absent") is True and not _contains_marker((data.get("metadata_parameters", {}), data.get("dry_run_payload_shape", {})), _NETWORK_MARKERS, keys_only=True))


def provider_dry_run_has_no_runtime_authority(envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any]) -> bool:
    data = _mapping(envelope)
    required = ("tool_calls_forbidden", "memory_forbidden", "retention_forbidden", "action_execution_forbidden", "routing_forbidden", "does_not_execute_or_route_work", "does_not_admit_work")
    return bool(all(data.get(marker) is True for marker in required) and not _contains_marker((data.get("metadata_parameters", {}), data.get("dry_run_payload_shape", {})), _RUNTIME_AUTHORITY_MARKERS + _RAW_OR_PARAM_MARKERS, keys_only=True))


def provider_dry_run_preserves_review_receipt(
    envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any],
    review_receipt: InternalModelCallReviewReceipt | Mapping[str, Any],
) -> bool:
    data = _mapping(envelope)
    review_data = _mapping(review_receipt)
    return bool(data.get("review_receipt_id") == review_data.get("review_receipt_id") and data.get("review_digest") == review_data.get("review_digest"))


def explain_provider_dry_run_findings(envelope_or_findings: ProviderDryRunRequestEnvelope | Mapping[str, Any] | Sequence[ProviderDryRunFinding]) -> tuple[str, ...]:
    if isinstance(envelope_or_findings, Sequence) and not isinstance(envelope_or_findings, (str, bytes, Mapping)):
        findings = envelope_or_findings
    else:
        findings = _mapping(envelope_or_findings).get("findings", ()) or ()
    return tuple(f"{_mapping(item).get('severity', '')}:{_mapping(item).get('code', '')}:{_mapping(item).get('detail', '')}" for item in findings)


def summarize_provider_dry_run_request_envelope(envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(envelope)
    return {
        "dry_run_id": str(data.get("dry_run_id", "")),
        "dry_run_status": str(data.get("dry_run_status", "")),
        "provider_family_label": str(data.get("provider_family_label", "")),
        "model_family_label": str(data.get("model_family_label", "")),
        "request_purpose": str(data.get("request_purpose", "")),
        "dry_run_scope": str(data.get("dry_run_scope", "")),
        "candidate_id": str(data.get("candidate_id", "")),
        "display_receipt_id": str(data.get("display_receipt_id", "")),
        "preflight_id": str(data.get("preflight_id", "")),
        "review_receipt_id": str(data.get("review_receipt_id", "")),
        "finding_count": len(data.get("findings", ()) or ()),
        "warning_count": len(data.get("warnings", ()) or ()),
        "dry_run_digest": str(data.get("dry_run_digest", "")),
        "provider_dry_run_only": bool(data.get("provider_dry_run_only", False)),
        "non_sendable": bool(data.get("non_sendable", False)),
        "does_not_call_llm": bool(data.get("does_not_call_llm", False)),
        "does_not_send_to_provider": bool(data.get("does_not_send_to_provider", False)),
    }
