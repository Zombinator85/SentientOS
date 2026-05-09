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
    ProviderDryRunEgressReviewStatus,
    compute_provider_dry_run_egress_review_digest,
    provider_dry_run_review_approves_future_egress_review_gate,
    provider_dry_run_review_approves_future_simulation_gate,
    provider_dry_run_review_satisfies_envelope,
)
from sentientos.context_hygiene.prompt_provider_simulation import (
    ProviderSimulationResultEnvelope,
    ProviderSimulationStatus,
    compute_provider_simulation_digest,
    provider_simulation_has_no_provider_credentials,
    provider_simulation_has_no_runtime_authority,
    provider_simulation_is_no_network,
    provider_simulation_is_not_model_output,
    provider_simulation_preserves_dry_run_review,
)


class ProviderNetworkEgressPreflightStatus:
    NETWORK_EGRESS_PREFLIGHT_DENIED = "network_egress_preflight_denied"
    NETWORK_EGRESS_PREFLIGHT_READY_FOR_REVIEW = "network_egress_preflight_ready_for_review"
    NETWORK_EGRESS_PREFLIGHT_READY_WITH_WARNINGS = "network_egress_preflight_ready_with_warnings"
    NETWORK_EGRESS_PREFLIGHT_REVIEW_REQUIRED = "network_egress_preflight_review_required"
    NETWORK_EGRESS_PREFLIGHT_INVALID_INPUT = "network_egress_preflight_invalid_input"
    NETWORK_EGRESS_PREFLIGHT_SIMULATION_INVALID = "network_egress_preflight_simulation_invalid"
    NETWORK_EGRESS_PREFLIGHT_DRY_RUN_INVALID = "network_egress_preflight_dry_run_invalid"
    NETWORK_EGRESS_PREFLIGHT_REVIEW_INVALID = "network_egress_preflight_review_invalid"
    NETWORK_EGRESS_PREFLIGHT_CREDENTIALS_DETECTED = "network_egress_preflight_credentials_detected"
    NETWORK_EGRESS_PREFLIGHT_NETWORK_FORBIDDEN = "network_egress_preflight_network_forbidden"
    NETWORK_EGRESS_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED = "network_egress_preflight_runtime_authority_detected"


class ProviderNetworkEgressPreflightDecision:
    DENY = "deny"
    READY_FOR_FUTURE_REVIEW = "ready_for_future_review"
    REVIEW_REQUIRED = "review_required"
    READY_WITH_WARNINGS = "ready_with_warnings"


class ProviderNetworkEgressPreflightRing:
    NETWORK_EGRESS_REVIEW_PREFLIGHT_ONLY = "network_egress_review_preflight_only"
    FUTURE_NETWORK_EGRESS_REVIEW_GATE = "future_network_egress_review_gate"
    FUTURE_PROVIDER_CALL_DRY_RUN_GATE = "future_provider_call_dry_run_gate"
    LIVE_PROVIDER_SEND_FORBIDDEN = "live_provider_send_forbidden"


@dataclass(frozen=True)
class ProviderNetworkEgressPreflightFinding:
    code: str
    detail: str
    severity: str = "blocker"


@dataclass(frozen=True)
class ProviderNetworkEgressPreflightConstraint:
    code: str
    detail: str
    required: bool = True


@dataclass(frozen=True)
class ProviderNetworkEgressAuditChain:
    dry_run_id: str = ""
    dry_run_digest: str = ""
    egress_review_receipt_id: str = ""
    egress_review_digest: str = ""
    simulation_id: str = ""
    simulation_digest: str = ""
    candidate_id: str = ""
    candidate_digest: str = ""
    display_receipt_id: str = ""
    display_receipt_digest: str = ""
    model_call_preflight_id: str = ""
    model_call_preflight_digest: str = ""
    model_call_review_receipt_id: str = ""
    model_call_review_digest: str = ""
    packet_id: str = ""
    packet_scope: str = ""
    complete: bool = False
    mismatches: tuple[str, ...] = field(default_factory=tuple)
    missing: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProviderNetworkEgressPreflight:
    preflight_id: str
    preflight_status: str
    requested_ring: str
    effective_ring: str
    dry_run_id: str
    dry_run_status: str
    dry_run_digest: str
    egress_review_receipt_id: str
    egress_review_status: str
    egress_review_digest: str
    simulation_id: str
    simulation_status: str
    simulation_digest: str
    provider_family_label: str
    model_family_label: str
    candidate_id: str
    candidate_digest: str
    preflight_model_call_id: str
    preflight_model_call_digest: str
    packet_id: str
    packet_scope: str
    audit_chain: ProviderNetworkEgressAuditChain
    digest_chain_complete: bool
    network_egress_allowed: bool
    provider_send_allowed: bool
    credentials_allowed: bool
    provider_client_allowed: bool
    llm_call_allowed: bool
    semantic_generation_allowed: bool
    tool_calls_allowed: bool
    memory_retrieval_allowed: bool
    memory_write_allowed: bool
    retention_allowed: bool
    action_execution_allowed: bool
    routing_allowed: bool
    findings: tuple[ProviderNetworkEgressPreflightFinding, ...]
    warnings: tuple[str, ...]
    required_mitigations: tuple[str, ...]
    rationale: str
    preflight_digest: str
    network_egress_preflight_only: bool = True
    network_egress_forbidden: bool = True
    provider_send_forbidden: bool = True
    credentials_forbidden: bool = True
    provider_client_forbidden: bool = True
    llm_call_forbidden: bool = True
    semantic_generation_forbidden: bool = True
    does_not_make_network_calls: bool = True
    does_not_send_to_provider: bool = True
    does_not_call_llm: bool = True
    does_not_retrieve_memory: bool = True
    does_not_write_memory: bool = True
    does_not_trigger_feedback: bool = True
    does_not_commit_retention: bool = True
    does_not_execute_or_route_work: bool = True
    does_not_admit_work: bool = True


_READY_DRY_RUN_STATUSES = frozenset({ProviderDryRunStatus.PROVIDER_DRY_RUN_READY, ProviderDryRunStatus.PROVIDER_DRY_RUN_READY_WITH_WARNINGS})
_READY_REVIEW_STATUSES = frozenset({ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_APPROVED, ProviderDryRunEgressReviewStatus.PROVIDER_DRY_RUN_REVIEW_APPROVED_WITH_CONSTRAINTS})
_READY_SIMULATION_STATUSES = frozenset({ProviderSimulationStatus.PROVIDER_SIMULATION_READY, ProviderSimulationStatus.PROVIDER_SIMULATION_READY_WITH_WARNINGS})
_ALLOWED_RINGS = frozenset(
    {
        ProviderNetworkEgressPreflightRing.NETWORK_EGRESS_REVIEW_PREFLIGHT_ONLY,
        ProviderNetworkEgressPreflightRing.FUTURE_NETWORK_EGRESS_REVIEW_GATE,
        ProviderNetworkEgressPreflightRing.FUTURE_PROVIDER_CALL_DRY_RUN_GATE,
        ProviderNetworkEgressPreflightRing.LIVE_PROVIDER_SEND_FORBIDDEN,
    }
)
_ALLOWANCE_FIELDS = (
    "network_egress_allowed",
    "provider_send_allowed",
    "credentials_allowed",
    "provider_client_allowed",
    "llm_call_allowed",
    "semantic_generation_allowed",
    "tool_calls_allowed",
    "memory_retrieval_allowed",
    "memory_write_allowed",
    "retention_allowed",
    "action_execution_allowed",
    "routing_allowed",
)
_MARKER_FIELDS = (
    "network_egress_preflight_only",
    "network_egress_forbidden",
    "provider_send_forbidden",
    "credentials_forbidden",
    "provider_client_forbidden",
    "llm_call_forbidden",
    "semantic_generation_forbidden",
    "does_not_make_network_calls",
    "does_not_send_to_provider",
    "does_not_call_llm",
    "does_not_retrieve_memory",
    "does_not_write_memory",
    "does_not_trigger_feedback",
    "does_not_commit_retention",
    "does_not_execute_or_route_work",
    "does_not_admit_work",
)
_CREDENTIAL_MARKERS = ("api_key", "apikey", "secret", "credential", "token", "authorization", "bearer", "auth", "header")
_NETWORK_MARKERS = ("endpoint", "url", "uri", "host", "base_url", "webhook", "http", "https", "network_handle", "request_handle", "response_handle")
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


def _negative_or_absence_label(text: str) -> bool:
    return (
        text.endswith("_absent")
        or text.endswith("_forbidden")
        or text.startswith("does_not_")
        or text.startswith("no_")
        or text.startswith("non_")
        or text.startswith("not_")
        or text in {"network_egress_preflight_only", "future_network_egress_review_gate", "future_provider_call_dry_run_gate", "transport_label", "simulation_label", "result_label"}
    )


def _contains_marker(value: Any, markers: Sequence[str], *, keys_only: bool = False) -> bool:
    for key, nested in _walk(value):
        lowered_key = key.lower()
        lowered_value = "" if keys_only else str(nested).lower()
        if _negative_or_absence_label(lowered_key):
            continue
        if lowered_key.endswith("_allowed") and nested is False:
            continue
        for marker in markers:
            if marker == "auth" and ("authority" in lowered_key or (not keys_only and "authority" in lowered_value)):
                continue
            if marker in lowered_key or (not keys_only and marker in lowered_value):
                return True
    return False


def _feature_enabled(feature_flag_state: Mapping[str, Any] | None) -> bool:
    flags = _mapping(feature_flag_state)
    return flags.get("network_egress_preflight") is True


def _finding(code: str, detail: str, severity: str = "blocker") -> ProviderNetworkEgressPreflightFinding:
    return ProviderNetworkEgressPreflightFinding(code=code, detail=detail, severity=severity)


def _constraints() -> tuple[ProviderNetworkEgressPreflightConstraint, ...]:
    return (
        ProviderNetworkEgressPreflightConstraint("network_egress_preflight_only", "Phase 87 is audit/preflight metadata only"),
        ProviderNetworkEgressPreflightConstraint("provider_send_forbidden", "provider invocation remains forbidden"),
        ProviderNetworkEgressPreflightConstraint("network_egress_forbidden", "network egress remains forbidden"),
        ProviderNetworkEgressPreflightConstraint("credentials_forbidden", "credentials and authorization material remain forbidden"),
        ProviderNetworkEgressPreflightConstraint("no_runtime_authority", "tools, memory, retention, action, routing, admission, and execution remain forbidden"),
        ProviderNetworkEgressPreflightConstraint("semantic_generation_forbidden", "semantic generation and model outputs remain forbidden"),
    )


def _digest_or_stored(value: Any, stored_field: str, compute: Any) -> str:
    data = _mapping(value)
    if not data:
        return ""
    try:
        computed = compute(value)
    except Exception:
        computed = ""
    return str(computed or data.get(stored_field, ""))


def _build_audit_chain(
    dry_run_envelope: Any,
    egress_review_receipt: Any,
    simulation_envelope: Any,
) -> ProviderNetworkEgressAuditChain:
    dry = _mapping(dry_run_envelope)
    review = _mapping(egress_review_receipt)
    sim = _mapping(simulation_envelope)
    missing: list[str] = []
    mismatches: list[str] = []
    required = {
        "dry_run_id": dry.get("dry_run_id", ""),
        "dry_run_digest": dry.get("dry_run_digest", ""),
        "egress_review_receipt_id": review.get("review_receipt_id", ""),
        "egress_review_digest": review.get("review_digest", ""),
        "simulation_id": sim.get("simulation_id", ""),
        "simulation_digest": sim.get("simulation_digest", ""),
        "candidate_id": dry.get("candidate_id", sim.get("candidate_id", "")),
        "candidate_digest": dry.get("candidate_digest", sim.get("candidate_digest", "")),
    }
    for key, value in required.items():
        if not value:
            missing.append(key)
    if dry and str(dry.get("dry_run_digest", "")) != _digest_or_stored(dry_run_envelope, "dry_run_digest", compute_provider_dry_run_digest):
        mismatches.append("dry_run_digest")
    if review and str(review.get("review_digest", "")) != _digest_or_stored(egress_review_receipt, "review_digest", compute_provider_dry_run_egress_review_digest):
        mismatches.append("egress_review_digest")
    if sim and str(sim.get("simulation_digest", "")) != _digest_or_stored(simulation_envelope, "simulation_digest", compute_provider_simulation_digest):
        mismatches.append("simulation_digest")
    if dry and review:
        if dry.get("dry_run_id") != review.get("dry_run_id"):
            mismatches.append("review_dry_run_id")
        if dry.get("dry_run_digest") != review.get("dry_run_digest"):
            mismatches.append("review_dry_run_digest")
    if dry and sim:
        if dry.get("dry_run_id") != sim.get("dry_run_id"):
            mismatches.append("simulation_dry_run_id")
        if dry.get("dry_run_digest") != sim.get("dry_run_digest"):
            mismatches.append("simulation_dry_run_digest")
    if review and sim:
        if review.get("review_receipt_id") != sim.get("egress_review_receipt_id"):
            mismatches.append("simulation_review_receipt_id")
        if review.get("review_digest") != sim.get("egress_review_digest"):
            mismatches.append("simulation_review_digest")
    return ProviderNetworkEgressAuditChain(
        dry_run_id=str(dry.get("dry_run_id", sim.get("dry_run_id", ""))),
        dry_run_digest=str(dry.get("dry_run_digest", sim.get("dry_run_digest", ""))),
        egress_review_receipt_id=str(review.get("review_receipt_id", sim.get("egress_review_receipt_id", ""))),
        egress_review_digest=str(review.get("review_digest", sim.get("egress_review_digest", ""))),
        simulation_id=str(sim.get("simulation_id", "")),
        simulation_digest=str(sim.get("simulation_digest", "")),
        candidate_id=str(dry.get("candidate_id", sim.get("candidate_id", review.get("candidate_id", "")))),
        candidate_digest=str(dry.get("candidate_digest", sim.get("candidate_digest", review.get("candidate_digest", "")))),
        display_receipt_id=str(dry.get("display_receipt_id", review.get("display_receipt_id", ""))),
        display_receipt_digest=str(dry.get("display_receipt_digest", review.get("display_receipt_digest", ""))),
        model_call_preflight_id=str(dry.get("preflight_id", sim.get("preflight_id", review.get("preflight_id", "")))),
        model_call_preflight_digest=str(dry.get("preflight_digest", sim.get("preflight_digest", review.get("preflight_digest", "")))),
        model_call_review_receipt_id=str(dry.get("review_receipt_id", review.get("model_call_review_receipt_id", ""))),
        model_call_review_digest=str(dry.get("review_digest", review.get("model_call_review_digest", ""))),
        packet_id=str(dry.get("packet_id", sim.get("packet_id", review.get("packet_id", "")))),
        packet_scope=str(dry.get("packet_scope", sim.get("packet_scope", review.get("packet_scope", "")))),
        complete=not missing and not mismatches,
        mismatches=tuple(sorted(set(mismatches))),
        missing=tuple(sorted(set(missing))),
    )


def _evaluate_findings(
    *,
    dry_run_envelope: Any,
    egress_review_receipt: Any,
    simulation_envelope: Any,
    requested_ring: str,
    feature_flag_state: Mapping[str, Any] | None,
    audit_chain: ProviderNetworkEgressAuditChain,
    internal_only: bool,
    no_network: bool,
    no_provider_send: bool,
    no_credentials: bool,
    no_provider_client: bool,
    no_tools: bool,
    no_memory: bool,
    no_retention: bool,
    no_actions: bool,
    no_routing: bool,
    no_semantic_generation: bool,
    marker_evidence: Mapping[str, Any] | None,
    allowance_overrides: Mapping[str, bool] | None,
    marker_overrides: Mapping[str, bool] | None,
) -> tuple[ProviderNetworkEgressPreflightFinding, ...]:
    findings: list[ProviderNetworkEgressPreflightFinding] = []
    dry = _mapping(dry_run_envelope)
    review = _mapping(egress_review_receipt)
    sim = _mapping(simulation_envelope)
    marker_evidence = _mapping(marker_evidence)
    allowance_overrides = _mapping(allowance_overrides)
    marker_overrides = _mapping(marker_overrides)

    if not dry:
        findings.append(_finding("dry_run_missing", "Phase 84 ProviderDryRunRequestEnvelope is required"))
    elif str(dry.get("dry_run_status", "")) not in _READY_DRY_RUN_STATUSES:
        findings.append(_finding("dry_run_not_ready", f"dry-run status {dry.get('dry_run_status', '')!r} is not eligible"))
    if dry and not provider_dry_run_is_non_sendable(dry_run_envelope):
        findings.append(_finding("dry_run_not_non_sendable", "dry-run envelope must remain non-sendable"))
    if dry and not provider_dry_run_has_no_provider_credentials(dry_run_envelope):
        findings.append(_finding("dry_run_credentials_detected", "dry-run contains credential markers"))
    if dry and not provider_dry_run_has_no_network_egress(dry_run_envelope):
        findings.append(_finding("dry_run_network_detected", "dry-run contains network markers"))
    if dry and not provider_dry_run_has_no_runtime_authority(dry_run_envelope):
        findings.append(_finding("dry_run_runtime_authority_detected", "dry-run contains runtime authority markers"))

    if not review:
        findings.append(_finding("egress_review_missing", "Phase 85 ProviderDryRunEgressReviewReceipt is required"))
    elif str(review.get("review_status", "")) not in _READY_REVIEW_STATUSES:
        findings.append(_finding("egress_review_not_ready", f"egress review status {review.get('review_status', '')!r} is not eligible"))
    if review and dry and not provider_dry_run_review_satisfies_envelope(dry_run_envelope, egress_review_receipt):
        findings.append(_finding("egress_review_not_satisfying_dry_run", "egress review does not satisfy the dry-run envelope"))
    if review and not (provider_dry_run_review_approves_future_simulation_gate(egress_review_receipt) or provider_dry_run_review_approves_future_egress_review_gate(egress_review_receipt)):
        findings.append(_finding("egress_review_gate_not_approved", "egress review must approve a future simulation or future egress-review gate"))

    if not sim:
        findings.append(_finding("simulation_missing", "Phase 86 ProviderSimulationResultEnvelope is required"))
    elif str(sim.get("simulation_status", "")) not in _READY_SIMULATION_STATUSES:
        findings.append(_finding("simulation_not_ready", f"simulation status {sim.get('simulation_status', '')!r} is not eligible"))
    if sim and dry and review and not provider_simulation_preserves_dry_run_review(simulation_envelope, dry_run_envelope, egress_review_receipt):
        findings.append(_finding("simulation_dry_run_review_not_preserved", "simulation does not preserve dry-run/review IDs and digests"))
    if sim and not provider_simulation_is_no_network(simulation_envelope):
        findings.append(_finding("simulation_no_network_proof_failed", "simulation no-network proof failed"))
    if sim and not provider_simulation_is_not_model_output(simulation_envelope):
        findings.append(_finding("simulation_not_model_output_proof_failed", "simulation fixed-stub/non-semantic proof failed"))
    if sim and not provider_simulation_has_no_provider_credentials(simulation_envelope):
        findings.append(_finding("simulation_credentials_detected", "simulation contains credential markers"))
    if sim and not provider_simulation_has_no_runtime_authority(simulation_envelope):
        findings.append(_finding("simulation_runtime_authority_detected", "simulation contains runtime authority markers"))

    if not audit_chain.complete:
        findings.append(_finding("digest_chain_incomplete", f"audit chain missing={audit_chain.missing!r} mismatches={audit_chain.mismatches!r}"))
    if requested_ring not in _ALLOWED_RINGS:
        findings.append(_finding("requested_ring_unknown", "requested network-egress preflight ring is unknown"))
    if requested_ring == ProviderNetworkEgressPreflightRing.LIVE_PROVIDER_SEND_FORBIDDEN:
        findings.append(_finding("live_provider_send_forbidden", "live provider send remains explicitly denied in Phase 87"))
    if not _feature_enabled(feature_flag_state):
        findings.append(_finding("feature_flag_disabled", "network_egress_preflight feature flag must be explicitly enabled"))

    combined_marker_evidence = (marker_evidence, dry, review, sim)
    if _contains_marker(combined_marker_evidence, _CREDENTIAL_MARKERS, keys_only=True):
        findings.append(_finding("credentials_marker_detected", "credential/API-key/authorization marker detected"))
    if _contains_marker(combined_marker_evidence, _NETWORK_MARKERS, keys_only=True):
        findings.append(_finding("network_marker_detected", "network/address/request marker detected"))
    if _contains_marker(combined_marker_evidence, _PROVIDER_OBJECT_MARKERS, keys_only=True):
        findings.append(_finding("provider_runtime_object_marker_detected", "provider client/session/transport marker detected"))
    if _contains_marker(combined_marker_evidence, _RUNTIME_AUTHORITY_MARKERS, keys_only=True):
        findings.append(_finding("runtime_handle_marker_detected", "runtime/tool/memory/action/retention/routing handle marker detected"))
    if _contains_marker(combined_marker_evidence, _RAW_OR_PARAM_MARKERS, keys_only=True):
        findings.append(_finding("raw_or_provider_param_marker_detected", "raw payload or model/provider parameter marker detected"))

    for field_name in _ALLOWANCE_FIELDS:
        if bool(allowance_overrides.get(field_name, False)):
            findings.append(_finding("forbidden_allowance_requested", f"{field_name} must remain false"))
    for field_name, value in marker_overrides.items():
        if field_name in _MARKER_FIELDS and value is not True:
            findings.append(_finding("required_marker_false", f"{field_name} must remain true"))
    required_flags = {
        "internal_only": internal_only,
        "no_network": no_network,
        "no_provider_send": no_provider_send,
        "no_credentials": no_credentials,
        "no_provider_client": no_provider_client,
        "no_tools": no_tools,
        "no_memory": no_memory,
        "no_retention": no_retention,
        "no_actions": no_actions,
        "no_routing": no_routing,
        "no_semantic_generation": no_semantic_generation,
    }
    for flag_name, flag_value in required_flags.items():
        if flag_value is not True:
            findings.append(_finding("required_no_runtime_flag_false", f"{flag_name} must be true for Phase 87"))
    return tuple(findings)


def _status_for_findings(findings: Sequence[ProviderNetworkEgressPreflightFinding], requested_ring: str, warnings: Sequence[str]) -> str:
    codes = {finding.code for finding in findings}
    if "dry_run_missing" in codes or "simulation_missing" in codes:
        return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_INVALID_INPUT
    if any(code.startswith("dry_run") for code in codes):
        if any("credentials" in code for code in codes):
            return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_CREDENTIALS_DETECTED
        if any("network" in code for code in codes):
            return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_NETWORK_FORBIDDEN
        if any("runtime" in code for code in codes):
            return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED
        return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_DRY_RUN_INVALID
    if any(code.startswith("egress_review") for code in codes):
        return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_REVIEW_INVALID
    if any(code.startswith("simulation") for code in codes):
        if any("credentials" in code for code in codes):
            return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_CREDENTIALS_DETECTED
        if any("network" in code for code in codes):
            return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_NETWORK_FORBIDDEN
        if any("runtime" in code for code in codes):
            return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED
        return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_SIMULATION_INVALID
    if any("credentials" in code for code in codes):
        return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_CREDENTIALS_DETECTED
    if any("network" in code or "provider_runtime_object" in code for code in codes):
        return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_NETWORK_FORBIDDEN
    if any("runtime" in code or "allowance" in code or "raw_or_provider" in code for code in codes):
        return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED
    if findings:
        return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_DENIED
    if requested_ring == ProviderNetworkEgressPreflightRing.NETWORK_EGRESS_REVIEW_PREFLIGHT_ONLY:
        return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_FOR_REVIEW
    if requested_ring == ProviderNetworkEgressPreflightRing.FUTURE_NETWORK_EGRESS_REVIEW_GATE:
        return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_REVIEW_REQUIRED
    if requested_ring == ProviderNetworkEgressPreflightRing.FUTURE_PROVIDER_CALL_DRY_RUN_GATE:
        return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_WITH_WARNINGS
    return ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_DENIED


def _decision_for_status(status: str) -> str:
    if status == ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_FOR_REVIEW:
        return ProviderNetworkEgressPreflightDecision.READY_FOR_FUTURE_REVIEW
    if status == ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_REVIEW_REQUIRED:
        return ProviderNetworkEgressPreflightDecision.REVIEW_REQUIRED
    if status == ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_WITH_WARNINGS:
        return ProviderNetworkEgressPreflightDecision.READY_WITH_WARNINGS
    return ProviderNetworkEgressPreflightDecision.DENY


def compute_provider_network_egress_preflight_digest(preflight: ProviderNetworkEgressPreflight | Mapping[str, Any]) -> str:
    data = dict(_mapping(preflight))
    data.pop("preflight_digest", None)
    data.pop("preflight_id", None)
    payload = {
        "preflight_status": data.get("preflight_status", ""),
        "requested_ring": data.get("requested_ring", ""),
        "effective_ring": data.get("effective_ring", ""),
        "dry_run_id": data.get("dry_run_id", ""),
        "dry_run_status": data.get("dry_run_status", ""),
        "dry_run_digest": data.get("dry_run_digest", ""),
        "egress_review_receipt_id": data.get("egress_review_receipt_id", ""),
        "egress_review_status": data.get("egress_review_status", ""),
        "egress_review_digest": data.get("egress_review_digest", ""),
        "simulation_id": data.get("simulation_id", ""),
        "simulation_status": data.get("simulation_status", ""),
        "simulation_digest": data.get("simulation_digest", ""),
        "provider_family_label": data.get("provider_family_label", ""),
        "model_family_label": data.get("model_family_label", ""),
        "candidate_id": data.get("candidate_id", ""),
        "candidate_digest": data.get("candidate_digest", ""),
        "preflight_model_call_id": data.get("preflight_model_call_id", ""),
        "preflight_model_call_digest": data.get("preflight_model_call_digest", ""),
        "packet_id": data.get("packet_id", ""),
        "packet_scope": data.get("packet_scope", ""),
        "audit_chain": _stable(data.get("audit_chain", {})),
        "digest_chain_complete": bool(data.get("digest_chain_complete", False)),
        "allowances": {field_name: bool(data.get(field_name, True)) for field_name in _ALLOWANCE_FIELDS},
        "findings": _stable(data.get("findings", ())),
        "warnings": _stable(data.get("warnings", ())),
        "required_mitigations": _stable(data.get("required_mitigations", ())),
        "rationale": data.get("rationale", ""),
        "markers": {field_name: bool(data.get(field_name, False)) for field_name in _MARKER_FIELDS},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_provider_network_egress_preflight(
    dry_run_envelope: ProviderDryRunRequestEnvelope | Mapping[str, Any] | None,
    egress_review_receipt: ProviderDryRunEgressReviewReceipt | Mapping[str, Any] | None,
    simulation_envelope: ProviderSimulationResultEnvelope | Mapping[str, Any] | None,
    *,
    requested_ring: str,
    feature_flag_state: Mapping[str, Any] | None,
    internal_only: bool = True,
    no_network: bool = True,
    no_provider_send: bool = True,
    no_credentials: bool = True,
    no_provider_client: bool = True,
    no_tools: bool = True,
    no_memory: bool = True,
    no_retention: bool = True,
    no_actions: bool = True,
    no_routing: bool = True,
    no_semantic_generation: bool = True,
    marker_evidence: Mapping[str, Any] | None = None,
    allowance_overrides: Mapping[str, bool] | None = None,
    marker_overrides: Mapping[str, bool] | None = None,
) -> ProviderNetworkEgressPreflight:
    dry = _mapping(dry_run_envelope)
    review = _mapping(egress_review_receipt)
    sim = _mapping(simulation_envelope)
    audit_chain = _build_audit_chain(dry_run_envelope, egress_review_receipt, simulation_envelope)
    findings = _evaluate_findings(
        dry_run_envelope=dry_run_envelope,
        egress_review_receipt=egress_review_receipt,
        simulation_envelope=simulation_envelope,
        requested_ring=str(requested_ring),
        feature_flag_state=feature_flag_state,
        audit_chain=audit_chain,
        internal_only=internal_only,
        no_network=no_network,
        no_provider_send=no_provider_send,
        no_credentials=no_credentials,
        no_provider_client=no_provider_client,
        no_tools=no_tools,
        no_memory=no_memory,
        no_retention=no_retention,
        no_actions=no_actions,
        no_routing=no_routing,
        no_semantic_generation=no_semantic_generation,
        marker_evidence=marker_evidence,
        allowance_overrides=allowance_overrides,
        marker_overrides=marker_overrides,
    )
    upstream_warnings = tuple(str(item) for source in (dry, review, sim) for item in (source.get("warnings", ()) or ()))
    warnings = upstream_warnings
    if not findings and requested_ring == ProviderNetworkEgressPreflightRing.FUTURE_PROVIDER_CALL_DRY_RUN_GATE:
        warnings = warnings + ("future provider-call dry-run gate remains metadata-only; network egress and provider send are still forbidden",)
    if not findings and requested_ring == ProviderNetworkEgressPreflightRing.FUTURE_NETWORK_EGRESS_REVIEW_GATE:
        warnings = warnings + ("future network-egress review receipt is required before any later phase",)
    status = _status_for_findings(findings, str(requested_ring), warnings)
    required_mitigations = tuple(f"mitigate:{finding.code}" for finding in findings if finding.severity == "blocker")
    marker_values = {field_name: True for field_name in _MARKER_FIELDS}
    if marker_overrides:
        marker_values.update({str(key): bool(value) for key, value in marker_overrides.items() if str(key) in marker_values})
    rationale = "; ".join(f"{finding.code}: {finding.detail}" for finding in findings[:4]) or "provider simulation audit chain is ready for a future review gate; network egress and provider send remain forbidden"
    preflight = ProviderNetworkEgressPreflight(
        preflight_id="",
        preflight_status=status,
        requested_ring=str(requested_ring),
        effective_ring=str(requested_ring) if str(requested_ring) in _ALLOWED_RINGS else ProviderNetworkEgressPreflightRing.LIVE_PROVIDER_SEND_FORBIDDEN,
        dry_run_id=str(dry.get("dry_run_id", sim.get("dry_run_id", ""))),
        dry_run_status=str(dry.get("dry_run_status", sim.get("dry_run_status", ""))),
        dry_run_digest=str(dry.get("dry_run_digest", sim.get("dry_run_digest", ""))),
        egress_review_receipt_id=str(review.get("review_receipt_id", sim.get("egress_review_receipt_id", ""))),
        egress_review_status=str(review.get("review_status", sim.get("egress_review_status", ""))),
        egress_review_digest=str(review.get("review_digest", sim.get("egress_review_digest", ""))),
        simulation_id=str(sim.get("simulation_id", "")),
        simulation_status=str(sim.get("simulation_status", "")),
        simulation_digest=str(sim.get("simulation_digest", "")),
        provider_family_label=str(dry.get("provider_family_label", sim.get("provider_family_label", review.get("provider_family_label", "")))),
        model_family_label=str(dry.get("model_family_label", sim.get("model_family_label", review.get("model_family_label", "")))),
        candidate_id=str(dry.get("candidate_id", sim.get("candidate_id", review.get("candidate_id", "")))),
        candidate_digest=str(dry.get("candidate_digest", sim.get("candidate_digest", review.get("candidate_digest", "")))),
        preflight_model_call_id=str(dry.get("preflight_id", sim.get("preflight_id", review.get("preflight_id", "")))),
        preflight_model_call_digest=str(dry.get("preflight_digest", sim.get("preflight_digest", review.get("preflight_digest", "")))),
        packet_id=str(dry.get("packet_id", sim.get("packet_id", review.get("packet_id", "")))),
        packet_scope=str(dry.get("packet_scope", sim.get("packet_scope", review.get("packet_scope", "")))),
        audit_chain=audit_chain,
        digest_chain_complete=audit_chain.complete,
        network_egress_allowed=False,
        provider_send_allowed=False,
        credentials_allowed=False,
        provider_client_allowed=False,
        llm_call_allowed=False,
        semantic_generation_allowed=False,
        tool_calls_allowed=False,
        memory_retrieval_allowed=False,
        memory_write_allowed=False,
        retention_allowed=False,
        action_execution_allowed=False,
        routing_allowed=False,
        findings=tuple(findings),
        warnings=tuple(warnings),
        required_mitigations=required_mitigations,
        rationale=rationale[:1000],
        preflight_digest="",
        **marker_values,
    )
    digest = compute_provider_network_egress_preflight_digest(preflight)
    return replace(preflight, preflight_id=f"provider-network-egress-preflight:{preflight.dry_run_id or 'missing'}:{digest[:16]}", preflight_digest=digest)


def validate_provider_network_egress_preflight(preflight: ProviderNetworkEgressPreflight | Mapping[str, Any]) -> tuple[ProviderNetworkEgressPreflightFinding, ...]:
    data = _mapping(preflight)
    findings: list[ProviderNetworkEgressPreflightFinding] = []
    if not data:
        return (_finding("preflight_missing", "ProviderNetworkEgressPreflight is required"),)
    if str(data.get("preflight_status", "")) not in {
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_DENIED,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_FOR_REVIEW,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_WITH_WARNINGS,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_REVIEW_REQUIRED,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_INVALID_INPUT,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_SIMULATION_INVALID,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_DRY_RUN_INVALID,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_REVIEW_INVALID,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_CREDENTIALS_DETECTED,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_NETWORK_FORBIDDEN,
        ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_RUNTIME_AUTHORITY_DETECTED,
    }:
        findings.append(_finding("preflight_status_unknown", "preflight status is unknown"))
    expected = compute_provider_network_egress_preflight_digest(preflight)
    if str(data.get("preflight_digest", "")) != expected:
        findings.append(_finding("preflight_digest_mismatch", "preflight digest does not match stable fields"))
    if not provider_network_egress_preflight_forbids_network(preflight):
        findings.append(_finding("network_forbidden_markers_missing", "network-forbidden markers or allowances are not preserved"))
    if not provider_network_egress_preflight_forbids_provider_send(preflight):
        findings.append(_finding("provider_send_forbidden_markers_missing", "provider-send forbidden markers or allowances are not preserved"))
    if not provider_network_egress_preflight_has_no_credentials(preflight):
        findings.append(_finding("credentials_forbidden_markers_missing", "credential-forbidden markers or allowances are not preserved"))
    if not provider_network_egress_preflight_has_no_runtime_authority(preflight):
        findings.append(_finding("runtime_authority_markers_missing", "runtime authority forbidden markers or allowances are not preserved"))
    return tuple(findings)


def provider_network_egress_preflight_allows_future_review_gate(preflight: ProviderNetworkEgressPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(
        data.get("preflight_status")
        in {
            ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_FOR_REVIEW,
            ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_READY_WITH_WARNINGS,
            ProviderNetworkEgressPreflightStatus.NETWORK_EGRESS_PREFLIGHT_REVIEW_REQUIRED,
        }
        and provider_network_egress_preflight_forbids_network(preflight)
        and provider_network_egress_preflight_forbids_provider_send(preflight)
        and provider_network_egress_preflight_has_no_credentials(preflight)
        and provider_network_egress_preflight_has_no_runtime_authority(preflight)
    )


def provider_network_egress_preflight_forbids_network(preflight: ProviderNetworkEgressPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(data.get("network_egress_allowed") is False and data.get("network_egress_forbidden") is True and data.get("does_not_make_network_calls") is True)


def provider_network_egress_preflight_forbids_provider_send(preflight: ProviderNetworkEgressPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(data.get("provider_send_allowed") is False and data.get("provider_send_forbidden") is True and data.get("does_not_send_to_provider") is True)


def provider_network_egress_preflight_has_no_credentials(preflight: ProviderNetworkEgressPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(data.get("credentials_allowed") is False and data.get("credentials_forbidden") is True)


def provider_network_egress_preflight_has_no_runtime_authority(preflight: ProviderNetworkEgressPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    return bool(
        data.get("provider_client_allowed") is False
        and data.get("llm_call_allowed") is False
        and data.get("semantic_generation_allowed") is False
        and data.get("tool_calls_allowed") is False
        and data.get("memory_retrieval_allowed") is False
        and data.get("memory_write_allowed") is False
        and data.get("retention_allowed") is False
        and data.get("action_execution_allowed") is False
        and data.get("routing_allowed") is False
        and data.get("provider_client_forbidden") is True
        and data.get("llm_call_forbidden") is True
        and data.get("semantic_generation_forbidden") is True
        and data.get("does_not_call_llm") is True
        and data.get("does_not_retrieve_memory") is True
        and data.get("does_not_write_memory") is True
        and data.get("does_not_trigger_feedback") is True
        and data.get("does_not_commit_retention") is True
        and data.get("does_not_execute_or_route_work") is True
        and data.get("does_not_admit_work") is True
    )


def provider_network_egress_preflight_digest_chain_complete(preflight: ProviderNetworkEgressPreflight | Mapping[str, Any]) -> bool:
    data = _mapping(preflight)
    chain = _mapping(data.get("audit_chain", {}))
    return bool(data.get("digest_chain_complete") is True and chain.get("complete") is True and not chain.get("missing", ()) and not chain.get("mismatches", ()))


def explain_provider_network_egress_preflight_findings(preflight_or_findings: ProviderNetworkEgressPreflight | Mapping[str, Any] | Sequence[ProviderNetworkEgressPreflightFinding]) -> tuple[str, ...]:
    if isinstance(preflight_or_findings, Sequence) and not isinstance(preflight_or_findings, (str, bytes, Mapping)):
        findings = preflight_or_findings
    else:
        findings = _mapping(preflight_or_findings).get("findings", ()) or ()
    return tuple(f"{_mapping(item).get('severity', '')}:{_mapping(item).get('code', '')}:{_mapping(item).get('detail', '')}" for item in findings)


def summarize_provider_network_egress_preflight(preflight: ProviderNetworkEgressPreflight | Mapping[str, Any]) -> Mapping[str, Any]:
    data = _mapping(preflight)
    return {
        "preflight_id": str(data.get("preflight_id", "")),
        "preflight_status": str(data.get("preflight_status", "")),
        "decision": _decision_for_status(str(data.get("preflight_status", ""))),
        "requested_ring": str(data.get("requested_ring", "")),
        "effective_ring": str(data.get("effective_ring", "")),
        "dry_run_id": str(data.get("dry_run_id", "")),
        "egress_review_receipt_id": str(data.get("egress_review_receipt_id", "")),
        "simulation_id": str(data.get("simulation_id", "")),
        "digest_chain_complete": bool(data.get("digest_chain_complete", False)),
        "finding_count": len(data.get("findings", ()) or ()),
        "warning_count": len(data.get("warnings", ()) or ()),
        "network_egress_allowed": bool(data.get("network_egress_allowed", True)),
        "provider_send_allowed": bool(data.get("provider_send_allowed", True)),
        "credentials_allowed": bool(data.get("credentials_allowed", True)),
        "provider_client_allowed": bool(data.get("provider_client_allowed", True)),
        "preflight_digest": str(data.get("preflight_digest", "")),
        "network_egress_preflight_only": bool(data.get("network_egress_preflight_only", False)),
        "does_not_call_llm": bool(data.get("does_not_call_llm", False)),
        "does_not_send_to_provider": bool(data.get("does_not_send_to_provider", False)),
        "does_not_make_network_calls": bool(data.get("does_not_make_network_calls", False)),
    }
