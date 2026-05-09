from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import hashlib
import json
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.prompt_provider_dry_run import (
    ProviderDryRunRequestEnvelope,
    ProviderDryRunStatus,
    compute_provider_dry_run_digest,
    provider_dry_run_has_no_network_egress,
    provider_dry_run_has_no_provider_credentials,
    provider_dry_run_has_no_runtime_authority,
    provider_dry_run_is_non_sendable,
)
from sentientos.context_hygiene.prompt_provider_dry_run_review import (
    ProviderDryRunEgressReviewReceipt,
    compute_provider_dry_run_egress_review_digest,
    provider_dry_run_review_approves_future_egress_review_gate,
    provider_dry_run_review_approves_future_simulation_gate,
    provider_dry_run_review_satisfies_envelope,
)


class ProviderSimulationStatus:
    PROVIDER_SIMULATION_READY = "provider_simulation_ready"
    PROVIDER_SIMULATION_READY_WITH_WARNINGS = "provider_simulation_ready_with_warnings"
    PROVIDER_SIMULATION_BLOCKED = "provider_simulation_blocked"
    PROVIDER_SIMULATION_INVALID_INPUT = "provider_simulation_invalid_input"
    PROVIDER_SIMULATION_REVIEW_MISSING = "provider_simulation_review_missing"
    PROVIDER_SIMULATION_DRY_RUN_NOT_READY = "provider_simulation_dry_run_not_ready"
    PROVIDER_SIMULATION_NETWORK_FORBIDDEN = "provider_simulation_network_forbidden"
    PROVIDER_SIMULATION_CREDENTIALS_DETECTED = "provider_simulation_credentials_detected"
    PROVIDER_SIMULATION_RUNTIME_AUTHORITY_DETECTED = "provider_simulation_runtime_authority_detected"
    PROVIDER_SIMULATION_SEMANTIC_GENERATION_FORBIDDEN = "provider_simulation_semantic_generation_forbidden"


class ProviderSimulationMode:
    SIMULATION_MODE_FIXED_STUB = "simulation_mode_fixed_stub"
    SIMULATION_MODE_ECHO_METADATA_ONLY = "simulation_mode_echo_metadata_only"
    SIMULATION_MODE_TRANSPORT_SHAPE_ONLY = "simulation_mode_transport_shape_only"
    SIMULATION_MODE_UNKNOWN_FORBIDDEN = "simulation_mode_unknown_forbidden"


class ProviderSimulationScope:
    INTERNAL_SIMULATION_ONLY = "internal_simulation_only"


@dataclass(frozen=True)
class ProviderSimulationFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderSimulationConstraint:
    code: str
    detail: str
    required: bool = True


@dataclass(frozen=True)
class ProviderSimulationBoundary:
    provider_simulation_only: bool = True
    fixed_stub_or_metadata_only: bool = True
    semantic_generation_forbidden: bool = True
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
    does_not_make_network_calls: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True


@dataclass(frozen=True)
class ProviderSimulationResultPayload:
    payload_kind: str = "non_sendable_provider_simulation_shape"
    simulation_label: str = "simulated_no_network_boundary"
    result_label: str = "simulated_provider_stub"
    transport_label: str = "simulated_transport_metadata"
    fixed_stub_label: str = "provider_simulation_fixed_stub"
    digest_refs: Mapping[str, str] = field(default_factory=dict)
    usage_placeholder: Mapping[str, int | None] = field(default_factory=lambda: {"input_units": 0, "output_units": 0, "total_units": 0, "provider_billed_units": None})
    metadata_tags: tuple[str, ...] = field(default_factory=lambda: ("provider_simulation_only", "fixed_stub_or_metadata_only", "no_network_egress"))
    provider_send_forbidden: bool = True
    network_egress_forbidden: bool = True
    provider_client_absent: bool = True
    fixed_stub_or_metadata_only: bool = True


@dataclass(frozen=True)
class ProviderSimulationResultEnvelope:
    simulation_id: str
    simulation_status: str
    simulation_mode: str
    simulation_scope: str
    simulation_reason: str
    dry_run_id: str
    dry_run_status: str
    dry_run_digest: str
    dry_run_prompt_text_digest: str
    dry_run_prompt_text_length: int
    egress_review_receipt_id: str
    egress_review_status: str
    egress_review_digest: str
    provider_family_label: str
    model_family_label: str
    candidate_id: str
    candidate_digest: str
    preflight_id: str
    preflight_digest: str
    packet_id: str
    packet_scope: str
    simulated_payload_shape: ProviderSimulationResultPayload
    simulated_result_stub: str
    simulated_result_digest: str
    findings: tuple[ProviderSimulationFinding, ...]
    warnings: tuple[str, ...]
    constraints: tuple[ProviderSimulationConstraint, ...]
    rationale: str
    simulation_digest: str
    provider_simulation_only: bool = True
    fixed_stub_or_metadata_only: bool = True
    semantic_generation_forbidden: bool = True
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
    does_not_make_network_calls: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True
    boundary: ProviderSimulationBoundary = field(default_factory=ProviderSimulationBoundary)


_ALLOWED_MODES = frozenset(
    {
        ProviderSimulationMode.SIMULATION_MODE_FIXED_STUB,
        ProviderSimulationMode.SIMULATION_MODE_ECHO_METADATA_ONLY,
        ProviderSimulationMode.SIMULATION_MODE_TRANSPORT_SHAPE_ONLY,
    }
)
_READY_DRY_RUN_STATUSES = frozenset(
    {
        ProviderDryRunStatus.PROVIDER_DRY_RUN_READY,
        ProviderDryRunStatus.PROVIDER_DRY_RUN_READY_WITH_WARNINGS,
    }
)
_READY_SIMULATION_STATUSES = frozenset(
    {
        ProviderSimulationStatus.PROVIDER_SIMULATION_READY,
        ProviderSimulationStatus.PROVIDER_SIMULATION_READY_WITH_WARNINGS,
    }
)
_MARKER_FIELDS = tuple(ProviderSimulationBoundary.__dataclass_fields__.keys())
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
_MODEL_OUTPUT_MARKERS = ("model_output", "assistant", "generated_content", "semantic_generation", "completion")
_NO_MODEL_MARKER = "NO MODEL CALLED"
_NO_NETWORK_MARKER = "NO NETWORK EGRESS"
_STUB_PREFIX = "PROVIDER SIMULATION RESULT"


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


def _walk(value: Any) -> tuple[tuple[str, Any], ...]:
    found: list[tuple[str, Any]] = []

    def visit(child: Any) -> None:
        if _is_dataclass_instance(child):
            visit(asdict(child))
        elif isinstance(child, Mapping):
            for key, nested in child.items():
                found.append((str(key), nested))
                visit(nested)
        elif isinstance(child, (tuple, list, set, frozenset)):
            for nested in child:
                visit(nested)

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


def _negative_or_simulation_label(text: str) -> bool:
    return (
        text.endswith("_absent")
        or text.endswith("_forbidden")
        or text.startswith("does_not_")
        or text.startswith("no_")
        or text.startswith("non_")
        or text.startswith("simulated_")
        or text in {"transport_label", "result_label", "simulation_label"}
    )


def _contains_marker(value: Any, markers: Sequence[str], *, keys_only: bool = False) -> bool:
    for key, nested in _walk(value):
        lowered_key = key.lower()
        lowered_value = "" if keys_only else str(nested).lower()
        for marker in markers:
            if _negative_or_simulation_label(lowered_key):
                continue
            if marker == "auth" and ("authority" in lowered_key or (not keys_only and "authority" in lowered_value)):
                continue
            if marker in lowered_key or (not keys_only and marker in lowered_value):
                if _truthy_forbidden(nested) or lowered_value:
                    return True
    if isinstance(value, str) and not keys_only:
        lowered = value.lower()
        return any(marker in lowered for marker in markers)
    return False


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _finding(code: str, detail: str, severity: str = "blocker") -> ProviderSimulationFinding:
    return ProviderSimulationFinding(code=code, detail=detail, severity=severity)


def _base_constraints() -> tuple[ProviderSimulationConstraint, ...]:
    return (
        ProviderSimulationConstraint("provider_simulation_only", "artifact is a provider simulation result only"),
        ProviderSimulationConstraint("fixed_stub_or_metadata_only", "result content is fixed-stub or metadata-only"),
        ProviderSimulationConstraint("semantic_generation_forbidden", "semantic generation and assistant-like output are forbidden"),
        ProviderSimulationConstraint("provider_send_forbidden", "provider/model egress remains forbidden"),
        ProviderSimulationConstraint("network_egress_forbidden", "network egress, endpoints, clients, and credentials are forbidden"),
        ProviderSimulationConstraint("runtime_authority_forbidden", "tools, memory, actions, retention, routing, and admission are forbidden"),
    )


def _stub(*, dry_run_id: str, dry_run_digest: str, review_digest: str, simulation_mode: str, fixed_stub_label: str) -> str:
    return " | ".join(
        (
            f"{_STUB_PREFIX} - {_NO_MODEL_MARKER} - {_NO_NETWORK_MARKER}",
            f"label={fixed_stub_label or 'provider_simulation_fixed_stub'}",
            f"mode={simulation_mode}",
            f"dry_run_id={dry_run_id}",
            f"dry_run_digest={dry_run_digest}",
            f"egress_review_digest={review_digest}",
            "non_runtime=true",
        )
    )


def _payload_shape(*, fixed_stub_label: str, simulation_status: str, dry_run_digest: str, review_digest: str, simulated_result_digest: str, provider_family_label: str, model_family_label: str) -> ProviderSimulationResultPayload:
    return ProviderSimulationResultPayload(
        fixed_stub_label=fixed_stub_label or "provider_simulation_fixed_stub",
        digest_refs={
            "dry_run_digest": dry_run_digest,
            "egress_review_digest": review_digest,
            "simulated_result_digest": simulated_result_digest,
        },
        metadata_tags=(
            "provider_simulation_only",
            "fixed_stub_or_metadata_only",
            "no_network_egress",
            "no_model_called",
            f"status:{simulation_status}",
            f"provider_label:{provider_family_label}",
            f"model_label:{model_family_label}",
        ),
    )


def _review_digest(review_receipt: Any | None) -> str:
    data = _mapping(review_receipt)
    if not data:
        return ""
    try:
        computed = compute_provider_dry_run_egress_review_digest(review_receipt)  # type: ignore[arg-type]
    except Exception:
        computed = ""
    return computed or str(data.get("review_digest", ""))


def _dry_run_digest(envelope: Any) -> str:
    data = _mapping(envelope)
    if not data:
        return ""
    try:
        computed = compute_provider_dry_run_digest(envelope)  # type: ignore[arg-type]
    except Exception:
        computed = ""
    return computed or str(data.get("dry_run_digest", ""))


def _clean_review(envelope: Any, review_receipt: Any | None) -> bool:
    return bool(
        review_receipt is not None
        and provider_dry_run_review_satisfies_envelope(envelope, review_receipt)  # type: ignore[arg-type]
        and (
            provider_dry_run_review_approves_future_simulation_gate(review_receipt)  # type: ignore[arg-type]
            or provider_dry_run_review_approves_future_egress_review_gate(review_receipt)  # type: ignore[arg-type]
        )
    )


def _evaluate_findings(
    *,
    dry_run_envelope: Any,
    egress_review_receipt: Any | None,
    simulation_mode: str,
    simulation_scope: str,
    expected_dry_run_digest: str | None,
    expected_review_digest: str | None,
    simulated_payload_shape: ProviderSimulationResultPayload,
    simulated_result_stub: str,
    marker_values: Mapping[str, bool],
) -> tuple[ProviderSimulationFinding, ...]:
    findings: list[ProviderSimulationFinding] = []
    dry_data = _mapping(dry_run_envelope)
    review_data = _mapping(egress_review_receipt)
    if not dry_data:
        findings.append(_finding("dry_run_missing", "Phase 84 ProviderDryRunRequestEnvelope is required"))
    if egress_review_receipt is None or not review_data:
        findings.append(_finding("egress_review_missing", "Phase 85 ProviderDryRunEgressReviewReceipt is required"))
    if simulation_mode not in _ALLOWED_MODES:
        findings.append(_finding("simulation_mode_forbidden", "simulation mode must be fixed-stub, metadata-only, or transport-shape-only"))
    if simulation_scope != ProviderSimulationScope.INTERNAL_SIMULATION_ONLY:
        findings.append(_finding("simulation_scope_forbidden", "simulation scope must be internal simulation only"))
    dry_status = str(dry_data.get("dry_run_status", ""))
    if dry_data and dry_status not in _READY_DRY_RUN_STATUSES:
        findings.append(_finding("dry_run_not_ready", f"dry-run status {dry_status!r} is not eligible for provider simulation"))
    if dry_data and not provider_dry_run_is_non_sendable(dry_run_envelope):
        findings.append(_finding("dry_run_send_forbidden_not_preserved", "dry-run envelope must remain non-sendable"))
    if dry_data and not provider_dry_run_has_no_provider_credentials(dry_run_envelope):
        findings.append(_finding("credentials_detected", "credential markers are present in dry-run metadata"))
    if dry_data and not provider_dry_run_has_no_network_egress(dry_run_envelope):
        findings.append(_finding("network_egress_detected", "network or endpoint markers are present in dry-run metadata"))
    if dry_data and not provider_dry_run_has_no_runtime_authority(dry_run_envelope):
        findings.append(_finding("runtime_authority_detected", "runtime authority markers are present in dry-run metadata"))
    if dry_data and expected_dry_run_digest is not None and str(expected_dry_run_digest) != str(dry_data.get("dry_run_digest", "")):
        findings.append(_finding("expected_dry_run_digest_mismatch", "expected dry-run digest does not match envelope"))
    if review_data and expected_review_digest is not None and str(expected_review_digest) != str(review_data.get("review_digest", "")):
        findings.append(_finding("expected_review_digest_mismatch", "expected review digest does not match receipt"))
    if review_data and not _clean_review(dry_run_envelope, egress_review_receipt):
        findings.append(_finding("egress_review_not_satisfied", "egress review does not approve a future simulation or egress-review gate for this dry-run"))
    if _contains_marker((simulated_payload_shape,), _CREDENTIAL_MARKERS, keys_only=True):
        findings.append(_finding("payload_credentials_detected", "simulated payload shape contains credential-like fields"))
    if _contains_marker((simulated_payload_shape,), _NETWORK_MARKERS, keys_only=True):
        findings.append(_finding("payload_network_detected", "simulated payload shape contains endpoint or network-like fields"))
    if _contains_marker((simulated_payload_shape,), _PROVIDER_OBJECT_MARKERS, keys_only=True):
        findings.append(_finding("payload_provider_object_detected", "simulated payload shape contains provider client/session/transport-like fields"))
    if _contains_marker((simulated_payload_shape,), _RUNTIME_AUTHORITY_MARKERS + _RAW_OR_PARAM_MARKERS, keys_only=True):
        findings.append(_finding("payload_runtime_authority_detected", "simulated payload shape contains runtime/raw/model parameter markers"))
    if _contains_marker((simulated_payload_shape,), _MODEL_OUTPUT_MARKERS, keys_only=False):
        findings.append(_finding("model_output_marker_detected", "simulated payload shape must not contain assistant/generated content markers"))
    for marker in _MARKER_FIELDS:
        if marker_values.get(marker) is not True:
            code = "network_marker_false" if marker in {"network_egress_forbidden", "does_not_make_network_calls", "endpoint_absent"} else "required_marker_false"
            findings.append(_finding(code, f"required provider simulation marker {marker} must be true"))
    if _STUB_PREFIX not in simulated_result_stub or _NO_MODEL_MARKER not in simulated_result_stub or _NO_NETWORK_MARKER not in simulated_result_stub:
        findings.append(_finding("fixed_stub_marker_missing", "simulated result stub must contain provider-simulation, no-model, and no-network markers"))
    if _contains_marker(simulated_result_stub, _MODEL_OUTPUT_MARKERS, keys_only=False):
        findings.append(_finding("semantic_generation_marker_detected", "simulated result stub must not contain model output markers"))
    return tuple(findings)


def _status_for_findings(findings: Sequence[ProviderSimulationFinding], warnings: Sequence[str], dry_run_status: str, review_present: bool) -> str:
    codes = {finding.code for finding in findings}
    if "dry_run_missing" in codes:
        return ProviderSimulationStatus.PROVIDER_SIMULATION_INVALID_INPUT
    if "egress_review_missing" in codes or not review_present:
        return ProviderSimulationStatus.PROVIDER_SIMULATION_REVIEW_MISSING
    if any("credentials" in code for code in codes) or dry_run_status == ProviderDryRunStatus.PROVIDER_DRY_RUN_CREDENTIALS_DETECTED:
        return ProviderSimulationStatus.PROVIDER_SIMULATION_CREDENTIALS_DETECTED
    if any("network" in code or "endpoint" in code for code in codes) or dry_run_status == ProviderDryRunStatus.PROVIDER_DRY_RUN_NETWORK_EGRESS_DETECTED:
        return ProviderSimulationStatus.PROVIDER_SIMULATION_NETWORK_FORBIDDEN
    if any("runtime" in code or "provider_object" in code for code in codes) or dry_run_status == ProviderDryRunStatus.PROVIDER_DRY_RUN_RUNTIME_AUTHORITY_DETECTED:
        return ProviderSimulationStatus.PROVIDER_SIMULATION_RUNTIME_AUTHORITY_DETECTED
    if "dry_run_not_ready" in codes:
        return ProviderSimulationStatus.PROVIDER_SIMULATION_DRY_RUN_NOT_READY
    if any("semantic" in code or "model_output" in code or "fixed_stub" in code for code in codes):
        return ProviderSimulationStatus.PROVIDER_SIMULATION_SEMANTIC_GENERATION_FORBIDDEN
    if findings:
        return ProviderSimulationStatus.PROVIDER_SIMULATION_BLOCKED
    if warnings or dry_run_status == ProviderDryRunStatus.PROVIDER_DRY_RUN_READY_WITH_WARNINGS:
        return ProviderSimulationStatus.PROVIDER_SIMULATION_READY_WITH_WARNINGS
    return ProviderSimulationStatus.PROVIDER_SIMULATION_READY


def compute_provider_simulation_digest(envelope: ProviderSimulationResultEnvelope | Mapping[str, Any]) -> str:
    data = dict(_mapping(envelope))
    data.pop("simulation_digest", None)
    data.pop("simulation_id", None)
    payload = {
        "simulation_status": data.get("simulation_status", ""),
        "simulation_mode": data.get("simulation_mode", ""),
        "simulation_scope": data.get("simulation_scope", ""),
        "simulation_reason": data.get("simulation_reason", ""),
        "dry_run_id": data.get("dry_run_id", ""),
        "dry_run_status": data.get("dry_run_status", ""),
        "dry_run_digest": data.get("dry_run_digest", ""),
        "dry_run_prompt_text_digest": data.get("dry_run_prompt_text_digest", ""),
        "dry_run_prompt_text_length": int(data.get("dry_run_prompt_text_length", 0) or 0),
        "egress_review_receipt_id": data.get("egress_review_receipt_id", ""),
        "egress_review_status": data.get("egress_review_status", ""),
        "egress_review_digest": data.get("egress_review_digest", ""),
        "provider_family_label": data.get("provider_family_label", ""),
        "model_family_label": data.get("model_family_label", ""),
        "candidate_id": data.get("candidate_id", ""),
        "candidate_digest": data.get("candidate_digest", ""),
        "preflight_id": data.get("preflight_id", ""),
        "preflight_digest": data.get("preflight_digest", ""),
        "packet_id": data.get("packet_id", ""),
        "packet_scope": data.get("packet_scope", ""),
        "simulated_payload_shape": _stable(data.get("simulated_payload_shape", {})),
        "simulated_result_stub": data.get("simulated_result_stub", ""),
        "simulated_result_digest": data.get("simulated_result_digest", ""),
        "findings": _stable(data.get("findings", ())),
        "warnings": _stable(data.get("warnings", ())),
        "constraints": _stable(data.get("constraints", ())),
        "rationale": data.get("rationale", ""),
        "markers": {marker: bool(data.get(marker, False)) for marker in _MARKER_FIELDS},
        "boundary": _stable(data.get("boundary", {})),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_provider_simulation_result_envelope(
    dry_run_envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any] | None,
    egress_review_receipt: ProviderDryRunEgressReviewReceipt | Mapping[str, Any] | None,
    *,
    simulation_mode: str,
    simulation_scope: str,
    simulation_reason: str = "",
    fixed_stub_label: str = "provider_simulation_fixed_stub",
    expected_dry_run_digest: str | None = None,
    expected_review_digest: str | None = None,
    marker_overrides: Mapping[str, bool] | None = None,
) -> ProviderSimulationResultEnvelope:
    dry_data = _mapping(dry_run_envelope)
    review_data = _mapping(egress_review_receipt)
    dry_digest = str(dry_data.get("dry_run_digest", ""))
    review_digest = str(review_data.get("review_digest", ""))
    dry_run_text = str(dry_data.get("dry_run_prompt_text", ""))
    stub = _stub(
        dry_run_id=str(dry_data.get("dry_run_id", "")),
        dry_run_digest=dry_digest,
        review_digest=review_digest,
        simulation_mode=str(simulation_mode),
        fixed_stub_label=str(fixed_stub_label),
    )
    stub_digest = _text_digest(stub)
    marker_values = {field_name: True for field_name in _MARKER_FIELDS}
    if marker_overrides:
        marker_values.update({str(key): bool(value) for key, value in marker_overrides.items() if str(key) in marker_values})
    preliminary_payload = _payload_shape(
        fixed_stub_label=str(fixed_stub_label),
        simulation_status="pending",
        dry_run_digest=dry_digest,
        review_digest=review_digest,
        simulated_result_digest=stub_digest,
        provider_family_label=str(dry_data.get("provider_family_label", review_data.get("provider_family_label", ""))),
        model_family_label=str(dry_data.get("model_family_label", review_data.get("model_family_label", ""))),
    )
    preliminary_findings = _evaluate_findings(
        dry_run_envelope=dry_run_envelope,
        egress_review_receipt=egress_review_receipt,
        simulation_mode=str(simulation_mode),
        simulation_scope=str(simulation_scope),
        expected_dry_run_digest=expected_dry_run_digest,
        expected_review_digest=expected_review_digest,
        simulated_payload_shape=preliminary_payload,
        simulated_result_stub=stub,
        marker_values=marker_values,
    )
    warnings = tuple(str(item) for source in (dry_data, review_data) for item in (source.get("warnings", ()) or ()))
    status = _status_for_findings(preliminary_findings, warnings, str(dry_data.get("dry_run_status", "")), bool(review_data))
    payload = _payload_shape(
        fixed_stub_label=str(fixed_stub_label),
        simulation_status=status,
        dry_run_digest=dry_digest,
        review_digest=review_digest,
        simulated_result_digest=stub_digest,
        provider_family_label=str(dry_data.get("provider_family_label", review_data.get("provider_family_label", ""))),
        model_family_label=str(dry_data.get("model_family_label", review_data.get("model_family_label", ""))),
    )
    findings = _evaluate_findings(
        dry_run_envelope=dry_run_envelope,
        egress_review_receipt=egress_review_receipt,
        simulation_mode=str(simulation_mode),
        simulation_scope=str(simulation_scope),
        expected_dry_run_digest=expected_dry_run_digest,
        expected_review_digest=expected_review_digest,
        simulated_payload_shape=payload,
        simulated_result_stub=stub,
        marker_values=marker_values,
    )
    status = _status_for_findings(findings, warnings, str(dry_data.get("dry_run_status", "")), bool(review_data))
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "provider simulation result is fixed-stub/metadata-only; provider invocation and network egress remain forbidden"
    boundary = ProviderSimulationBoundary(**marker_values)
    envelope = ProviderSimulationResultEnvelope(
        simulation_id="",
        simulation_status=status,
        simulation_mode=str(simulation_mode),
        simulation_scope=str(simulation_scope),
        simulation_reason=str(simulation_reason),
        dry_run_id=str(dry_data.get("dry_run_id", "")),
        dry_run_status=str(dry_data.get("dry_run_status", "")),
        dry_run_digest=dry_digest,
        dry_run_prompt_text_digest=_text_digest(dry_run_text),
        dry_run_prompt_text_length=len(dry_run_text),
        egress_review_receipt_id=str(review_data.get("review_receipt_id", "")),
        egress_review_status=str(review_data.get("review_status", "")),
        egress_review_digest=review_digest,
        provider_family_label=str(dry_data.get("provider_family_label", review_data.get("provider_family_label", ""))),
        model_family_label=str(dry_data.get("model_family_label", review_data.get("model_family_label", ""))),
        candidate_id=str(dry_data.get("candidate_id", review_data.get("candidate_id", ""))),
        candidate_digest=str(dry_data.get("candidate_digest", review_data.get("candidate_digest", ""))),
        preflight_id=str(dry_data.get("preflight_id", review_data.get("preflight_id", ""))),
        preflight_digest=str(dry_data.get("preflight_digest", review_data.get("preflight_digest", ""))),
        packet_id=str(dry_data.get("packet_id", review_data.get("packet_id", ""))),
        packet_scope=str(dry_data.get("packet_scope", review_data.get("packet_scope", ""))),
        simulated_payload_shape=payload,
        simulated_result_stub=stub,
        simulated_result_digest=stub_digest,
        findings=tuple(findings),
        warnings=warnings,
        constraints=_base_constraints(),
        rationale=rationale[:1000],
        simulation_digest="",
        boundary=boundary,
        **marker_values,
    )
    digest = compute_provider_simulation_digest(envelope)
    return replace(envelope, simulation_id=f"provider-simulation:{envelope.dry_run_id or 'missing'}:{digest[:16]}", simulation_digest=digest)


def validate_provider_simulation_result_envelope(envelope: ProviderSimulationResultEnvelope | Mapping[str, Any]) -> tuple[ProviderSimulationFinding, ...]:
    data = _mapping(envelope)
    findings: list[ProviderSimulationFinding] = []
    if not data:
        return (_finding("simulation_malformed", "provider simulation envelope is malformed"),)
    expected = compute_provider_simulation_digest(envelope)
    if str(data.get("simulation_digest", "")) != expected:
        findings.append(_finding("simulation_digest_mismatch", "simulation digest does not match envelope-safe fields"))
    if str(data.get("simulation_status", "")) in _READY_SIMULATION_STATUSES and tuple(data.get("findings", ()) or ()): 
        findings.append(_finding("ready_with_blocking_findings", "ready provider simulations must not contain findings"))
    if not provider_simulation_is_no_network(envelope):
        findings.append(_finding("no_network_proof_failed", "provider simulation no-network proof failed"))
    if not provider_simulation_is_not_model_output(envelope):
        findings.append(_finding("not_model_output_proof_failed", "provider simulation fixed-stub/non-semantic proof failed"))
    if not provider_simulation_has_no_provider_credentials(envelope):
        findings.append(_finding("credentials_detected", "provider simulation contains credential markers"))
    if not provider_simulation_has_no_runtime_authority(envelope):
        findings.append(_finding("runtime_authority_detected", "provider simulation contains runtime authority markers"))
    return tuple(findings)


def _finding_codes(envelope: ProviderSimulationResultEnvelope | Mapping[str, Any]) -> set[str]:
    return {str(_mapping(finding).get("code", "")) for finding in (_mapping(envelope).get("findings", ()) or ())}


def provider_simulation_is_no_network(envelope: ProviderSimulationResultEnvelope | Mapping[str, Any]) -> bool:
    data = _mapping(envelope)
    codes = _finding_codes(envelope)
    return bool(
        str(data.get("simulation_status", "")) in _READY_SIMULATION_STATUSES
        and data.get("network_egress_forbidden") is True
        and data.get("does_not_make_network_calls") is True
        and data.get("endpoint_absent") is True
        and data.get("provider_client_absent") is True
        and data.get("api_key_absent") is True
        and not any("network" in code or "endpoint" in code or "client" in code for code in codes)
    )


def provider_simulation_is_not_model_output(envelope: ProviderSimulationResultEnvelope | Mapping[str, Any]) -> bool:
    data = _mapping(envelope)
    stub = str(data.get("simulated_result_stub", ""))
    codes = _finding_codes(envelope)
    return bool(
        data.get("semantic_generation_forbidden") is True
        and data.get("fixed_stub_or_metadata_only") is True
        and data.get("does_not_call_llm") is True
        and _STUB_PREFIX in stub
        and _NO_MODEL_MARKER in stub
        and _NO_NETWORK_MARKER in stub
        and not any("model_output" in code or "assistant" in code or "generated" in code for code in codes)
    )


def provider_simulation_has_no_provider_credentials(envelope: ProviderSimulationResultEnvelope | Mapping[str, Any]) -> bool:
    data = _mapping(envelope)
    return bool(
        data.get("credentials_forbidden") is True
        and data.get("api_key_absent") is True
        and not _contains_marker((data.get("simulated_payload_shape", {}),), _CREDENTIAL_MARKERS, keys_only=True)
    )


def provider_simulation_has_no_runtime_authority(envelope: ProviderSimulationResultEnvelope | Mapping[str, Any]) -> bool:
    data = _mapping(envelope)
    required = ("tool_calls_forbidden", "memory_forbidden", "retention_forbidden", "action_execution_forbidden", "routing_forbidden", "does_not_execute_or_route_work", "does_not_admit_work")
    return bool(
        all(data.get(marker) is True for marker in required)
        and not _contains_marker((data.get("simulated_payload_shape", {}),), _RUNTIME_AUTHORITY_MARKERS + _RAW_OR_PARAM_MARKERS, keys_only=True)
    )


def provider_simulation_preserves_dry_run_review(
    envelope: ProviderSimulationResultEnvelope | Mapping[str, Any],
    dry_run_envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any],
    egress_review_receipt: ProviderDryRunEgressReviewReceipt | Mapping[str, Any],
) -> bool:
    data = _mapping(envelope)
    dry_data = _mapping(dry_run_envelope)
    review_data = _mapping(egress_review_receipt)
    return bool(
        data.get("dry_run_id") == dry_data.get("dry_run_id")
        and data.get("dry_run_digest") == dry_data.get("dry_run_digest")
        and data.get("egress_review_receipt_id") == review_data.get("review_receipt_id")
        and data.get("egress_review_digest") == review_data.get("review_digest")
    )


def explain_provider_simulation_findings(envelope_or_findings: ProviderSimulationResultEnvelope | Mapping[str, Any] | Sequence[ProviderSimulationFinding]) -> tuple[str, ...]:
    if isinstance(envelope_or_findings, Sequence) and not isinstance(envelope_or_findings, (str, bytes, Mapping)):
        findings = envelope_or_findings
    else:
        findings = _mapping(envelope_or_findings).get("findings", ()) or ()
    return tuple(f"{_mapping(item).get('severity', '')}:{_mapping(item).get('code', '')}:{_mapping(item).get('detail', '')}" for item in findings)


def summarize_provider_simulation_result_envelope(envelope: ProviderSimulationResultEnvelope | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(envelope)
    return {
        "simulation_id": str(data.get("simulation_id", "")),
        "simulation_status": str(data.get("simulation_status", "")),
        "simulation_mode": str(data.get("simulation_mode", "")),
        "simulation_scope": str(data.get("simulation_scope", "")),
        "dry_run_id": str(data.get("dry_run_id", "")),
        "dry_run_digest": str(data.get("dry_run_digest", "")),
        "egress_review_receipt_id": str(data.get("egress_review_receipt_id", "")),
        "egress_review_digest": str(data.get("egress_review_digest", "")),
        "provider_family_label": str(data.get("provider_family_label", "")),
        "model_family_label": str(data.get("model_family_label", "")),
        "finding_count": len(data.get("findings", ()) or ()),
        "warning_count": len(data.get("warnings", ()) or ()),
        "simulation_digest": str(data.get("simulation_digest", "")),
        "provider_simulation_only": bool(data.get("provider_simulation_only", False)),
        "fixed_stub_or_metadata_only": bool(data.get("fixed_stub_or_metadata_only", False)),
        "does_not_call_llm": bool(data.get("does_not_call_llm", False)),
        "does_not_send_to_provider": bool(data.get("does_not_send_to_provider", False)),
        "does_not_make_network_calls": bool(data.get("does_not_make_network_calls", False)),
    }
