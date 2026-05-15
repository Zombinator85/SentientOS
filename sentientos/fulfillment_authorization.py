"""Metadata-only fulfillment authorization consumption records.

This wing follows local authorization grants and records whether a future
fulfillment request fits an active local authorization grant. It is strictly
pre-fulfillment: it does not execute, fulfill, mutate host state, write fan/PWM
controls, change thermal or power settings, restart services, clean files, make
network calls, invoke providers, or assemble prompts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, NamedTuple, Sequence

REQUEST_STATUSES = frozenset({
    "fulfillment_authorization_request_recorded",
    "fulfillment_authorization_request_recorded_with_warnings",
    "fulfillment_authorization_request_blocked",
    "fulfillment_authorization_request_incomplete",
    "fulfillment_authorization_request_contradicted",
})
CONSUMPTION_VERIFICATION_STATUSES = frozenset({
    "grant_consumption_verified",
    "grant_consumption_verified_with_conditions",
    "grant_consumption_blocked",
    "grant_consumption_expired",
    "grant_consumption_revoked",
    "grant_consumption_out_of_scope",
    "grant_consumption_incomplete",
    "grant_consumption_contradicted",
})
SCOPE_MATCH_STATUSES = frozenset({
    "fulfillment_scope_match",
    "fulfillment_scope_match_with_conditions",
    "fulfillment_scope_mismatch",
    "fulfillment_scope_missing",
    "fulfillment_scope_contradicted",
})
CONSUMPTION_RECEIPT_STATUSES = frozenset({
    "fulfillment_authorization_consumption_recorded",
    "fulfillment_authorization_consumption_recorded_with_warnings",
    "fulfillment_authorization_consumption_blocked",
    "fulfillment_authorization_consumption_expired",
    "fulfillment_authorization_consumption_revoked",
    "fulfillment_authorization_consumption_out_of_scope",
    "fulfillment_authorization_consumption_incomplete",
    "fulfillment_authorization_consumption_contradicted",
})
DENIAL_RECEIPT_STATUSES = frozenset({
    "fulfillment_authorization_denial_recorded",
    "fulfillment_authorization_denial_blocked",
    "fulfillment_authorization_denial_incomplete",
    "fulfillment_authorization_denial_contradicted",
})
FULFILLMENT_DOMAINS = frozenset({
    "diagnostics_fulfillment_authorization",
    "operator_review_fulfillment_authorization",
    "resource_pressure_fulfillment_authorization",
    "thermal_safety_fulfillment_authorization",
    "future_cooling_fulfillment_authorization",
    "future_power_fulfillment_authorization",
    "future_cleanup_fulfillment_authorization",
    "future_service_fulfillment_authorization",
})
REQUIRED_REQUEST_LABELS = frozenset({
    "local_authorization_grant_required",
    "local_authorization_verification_required",
    "grant_not_expired_required",
    "grant_not_revoked_required",
    "grant_scope_match_required",
    "fulfillment_domain_declared",
    "fulfillment_backend_declared",
    "effect_receipt_contract_required",
    "postcondition_plan_required",
    "rollback_plan_required",
    "runtime_supervisor_observation_required",
    "control_plane_admission_required_for_fulfillment",
    "audit_receipt_required_for_fulfillment",
    "effect_receipt_required_for_fulfillment",
    "postcondition_check_required_for_fulfillment",
    "rollback_receipt_required_for_fulfillment",
    "immutable_trace_required_for_fulfillment",
})
BLOCKED_ACTION_LABELS = frozenset({
    "host_mutation",
    "fan_pwm_write",
    "thermal_actuation",
    "power_profile_mutation",
    "process_kill",
    "service_restart",
    "package_install",
    "driver_install",
    "file_cleanup",
    "file_delete",
    "provider_invocation",
    "network_egress",
    "prompt_assembly",
    "federation_transport",
    "remote_execution",
})
_DOMAIN_SCOPE = {
    "diagnostics_fulfillment_authorization": "diagnostics_only_scope",
    "operator_review_fulfillment_authorization": "operator_review_scope",
    "resource_pressure_fulfillment_authorization": "resource_pressure_review_scope",
    "thermal_safety_fulfillment_authorization": "thermal_safety_review_scope",
    "future_cooling_fulfillment_authorization": "future_cooling_scope",
    "future_power_fulfillment_authorization": "future_power_scope",
    "future_cleanup_fulfillment_authorization": "future_cleanup_scope",
    "future_service_fulfillment_authorization": "future_service_scope",
}
_DOMAIN_BLOCKS = {
    "future_cooling_fulfillment_authorization": ("fan_pwm_write", "thermal_actuation"),
    "future_power_fulfillment_authorization": ("power_profile_mutation",),
    "future_cleanup_fulfillment_authorization": ("file_cleanup", "file_delete"),
    "future_service_fulfillment_authorization": ("service_restart", "process_kill"),
}
_FUTURE_GATES = tuple(sorted({
    "control_plane_admission_required_for_fulfillment",
    "audit_receipt_required_for_fulfillment",
    "effect_receipt_required_for_fulfillment",
    "postcondition_check_required_for_fulfillment",
    "rollback_receipt_required_for_fulfillment",
    "runtime_supervisor_observation_required",
    "immutable_trace_required_for_fulfillment",
    "safety_gates_required_for_fulfillment",
}))
_FORBIDDEN_TRUE_FLAGS = (
    "fulfillment_granted",
    "effect_performed",
    "host_mutation_performed",
    "fan_pwm_write_performed",
    "thermal_actuation_performed",
    "power_profile_mutation_performed",
    "process_kill_performed",
    "service_restart_performed",
    "package_install_performed",
    "driver_install_performed",
    "file_cleanup_performed",
    "provider_invocation_performed",
    "network_performed",
    "prompt_assembly_performed",
)


@dataclass(frozen=True)
class FulfillmentAuthorizationPolicy:
    policy_id: str
    required_request_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    metadata_only: bool = True
    pre_fulfillment_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FulfillmentAuthorizationRequest:
    request_id: str
    source_local_authorization_grant_id: str
    source_local_authorization_grant_digest: str
    source_grant_verification_id: str | None
    requested_fulfillment_domain: str
    requested_backend_class: str
    requested_scope_labels: tuple[str, ...]
    requested_time_label: str
    required_request_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    request_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    request_only: bool = True
    fulfillment_requested: bool = True
    fulfillment_granted: bool = False
    effect_performed: bool = False
    host_mutation_performed: bool = False
    does_not_execute: bool = True
    does_not_mutate_host: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GrantConsumptionVerification:
    verification_id: str
    request_id: str
    grant_id: str
    grant_status: str
    grant_verification_status: str
    consumption_status: str
    checked_scope_labels: tuple[str, ...]
    checked_time_label: str
    checked_revocation_labels: tuple[str, ...]
    missing_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    digest: str
    metadata_only: bool = True
    verification_only: bool = True
    authorizes_fulfillment: bool = False
    does_not_execute: bool = True
    does_not_mutate_host: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FulfillmentScopeMatchAssessment:
    assessment_id: str
    request_id: str
    grant_id: str
    requested_scope_labels: tuple[str, ...]
    granted_scope_labels: tuple[str, ...]
    matched_scope_labels: tuple[str, ...]
    missing_scope_labels: tuple[str, ...]
    extra_scope_labels: tuple[str, ...]
    scope_match_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    digest: str
    metadata_only: bool = True
    assessment_only: bool = True
    authorizes_fulfillment: bool = False
    does_not_execute: bool = True
    does_not_mutate_host: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FulfillmentAuthorizationConsumptionReceipt:
    receipt_id: str
    request_id: str
    grant_id: str
    grant_consumption_verification_id: str
    scope_match_assessment_id: str
    requested_fulfillment_domain: str
    requested_backend_class: str
    consumption_status: str
    evidence_summary: tuple[str, ...]
    required_future_fulfillment_gates: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    consumption_receipt_only: bool = True
    authorization_consumed_for_future_fulfillment: bool = False
    fulfillment_granted: bool = False
    effect_performed: bool = False
    host_mutation_performed: bool = False
    fan_pwm_write_performed: bool = False
    thermal_actuation_performed: bool = False
    power_profile_mutation_performed: bool = False
    process_kill_performed: bool = False
    service_restart_performed: bool = False
    package_install_performed: bool = False
    driver_install_performed: bool = False
    file_cleanup_performed: bool = False
    provider_invocation_performed: bool = False
    network_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FulfillmentAuthorizationDenialReceipt:
    receipt_id: str
    request_id: str
    grant_id: str | None
    denial_status: str
    denial_reason_codes: tuple[str, ...]
    missing_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    denial_receipt_only: bool = True
    authorization_consumed_for_future_fulfillment: bool = False
    fulfillment_granted: bool = False
    effect_performed: bool = False
    host_mutation_performed: bool = False
    does_not_execute: bool = True
    does_not_mutate_host: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FulfillmentAuthorizationValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


class FulfillmentAuthorizationWingRecords(NamedTuple):
    request: FulfillmentAuthorizationRequest
    grant_consumption_verification: GrantConsumptionVerification
    scope_match_assessment: FulfillmentScopeMatchAssessment
    consumption_receipt: FulfillmentAuthorizationConsumptionReceipt | None
    denial_receipt: FulfillmentAuthorizationDenialReceipt | None


def _tuple(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


def _source_payload(source: Any) -> Mapping[str, Any]:
    return source.to_dict() if hasattr(source, "to_dict") else dict(source)


def _payload(record_or_payload: Any) -> dict[str, Any]:
    payload = record_or_payload.to_dict() if hasattr(record_or_payload, "to_dict") else dict(record_or_payload)
    payload["digest"] = ""
    return payload


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def fulfillment_authorization_digest(record_or_payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(_payload(record_or_payload)).encode("utf-8")).hexdigest()


fulfillment_authorization_request_digest = fulfillment_authorization_digest
grant_consumption_verification_digest = fulfillment_authorization_digest
fulfillment_scope_match_assessment_digest = fulfillment_authorization_digest
fulfillment_authorization_consumption_receipt_digest = fulfillment_authorization_digest
fulfillment_authorization_denial_receipt_digest = fulfillment_authorization_digest


def _digest_id(prefix: str, payload: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:24]


def build_default_fulfillment_authorization_policy() -> FulfillmentAuthorizationPolicy:
    return FulfillmentAuthorizationPolicy(
        "fulfillment-authorization-consumption-policy-v1",
        tuple(sorted(REQUIRED_REQUEST_LABELS)),
        tuple(sorted(BLOCKED_ACTION_LABELS)),
    )


def _domain_blocks(domain: str) -> tuple[str, ...]:
    return tuple(sorted(set(BLOCKED_ACTION_LABELS) | set(_DOMAIN_BLOCKS.get(domain, ()))))


def build_fulfillment_authorization_request(
    grant: Any,
    grant_verification: Any | None,
    *,
    requested_fulfillment_domain: str,
    requested_backend_class: str,
    requested_scope_labels: Sequence[str] | None = None,
    requested_time_label: str = "1970-01-01T00:00:00+00:00",
    required_request_labels: Sequence[str] | None = None,
    blocked_actions: Sequence[str] | None = None,
    request_id: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> FulfillmentAuthorizationRequest:
    g = _source_payload(grant)
    v = _source_payload(grant_verification) if grant_verification is not None else {}
    labels = _tuple(requested_scope_labels) or tuple(sorted({_DOMAIN_SCOPE.get(requested_fulfillment_domain, "")} - {""}))
    required = _tuple(required_request_labels) or tuple(sorted(REQUIRED_REQUEST_LABELS))
    blocked = tuple(sorted(set(_tuple(blocked_actions)) | set(_tuple(g.get("blocked_actions"))) | set(_domain_blocks(requested_fulfillment_domain))))
    missing = sorted(REQUIRED_REQUEST_LABELS - set(required))
    warnings: set[str] = set()
    risks = {"fulfillment_authorization_consumption_is_not_fulfillment"}
    status = "fulfillment_authorization_request_recorded"
    if requested_fulfillment_domain not in FULFILLMENT_DOMAINS:
        status = "fulfillment_authorization_request_contradicted"
        risks.add("unknown_fulfillment_domain")
    elif not requested_backend_class:
        status = "fulfillment_authorization_request_incomplete"
        warnings.add("fulfillment_backend_missing")
    elif missing or not g.get("grant_id") or not v.get("verification_id"):
        status = "fulfillment_authorization_request_incomplete"
        warnings.update(missing)
    elif blocked:
        status = "fulfillment_authorization_request_recorded_with_warnings"
        warnings.add("blocked_actions_preserved_for_future_fulfillment")
    rid = request_id or _digest_id("fulfillment-auth-request-", {"grant": g.get("grant_id"), "verification": v.get("verification_id"), "domain": requested_fulfillment_domain, "backend": requested_backend_class, "scope": labels, "time": requested_time_label})
    provisional = FulfillmentAuthorizationRequest(
        rid,
        str(g.get("grant_id", "")),
        str(g.get("digest", "")),
        str(v.get("verification_id")) if v.get("verification_id") else None,
        requested_fulfillment_domain,
        requested_backend_class,
        labels,
        requested_time_label,
        required,
        blocked,
        status,
        tuple(sorted(warnings)),
        tuple(sorted(risks)),
        created_at,
        "",
    )
    return replace(provisional, digest=fulfillment_authorization_request_digest(provisional))


def _consumption_status(grant: Mapping[str, Any], grant_verification: Mapping[str, Any], request: Mapping[str, Any]) -> str:
    gstatus = str(grant.get("grant_status", ""))
    vstatus = str(grant_verification.get("verification_status", ""))
    if "contradicted" in gstatus or "contradicted" in vstatus or "contradicted" in str(request.get("request_status", "")):
        return "grant_consumption_contradicted"
    if "blocked" in gstatus or "blocked" in vstatus or "blocked" in str(request.get("request_status", "")):
        return "grant_consumption_blocked"
    if "revoked" in gstatus or "revoked" in vstatus:
        return "grant_consumption_revoked"
    if "expired" in gstatus or "expired" in vstatus:
        return "grant_consumption_expired"
    if "incomplete" in gstatus or "incomplete" in vstatus or "incomplete" in str(request.get("request_status", "")):
        return "grant_consumption_incomplete"
    if set(_tuple(request.get("requested_scope_labels"))) - set(_tuple(grant.get("granted_scope_labels"))):
        return "grant_consumption_out_of_scope"
    if gstatus == "local_authorization_grant_active_with_conditions" or vstatus == "local_authorization_verification_valid_with_conditions":
        return "grant_consumption_verified_with_conditions"
    if gstatus == "local_authorization_grant_active" and vstatus == "local_authorization_verification_valid":
        return "grant_consumption_verified"
    return "grant_consumption_incomplete"


def verify_grant_consumption_for_fulfillment(grant: Any, grant_verification: Any, request: Any) -> GrantConsumptionVerification:
    g = _source_payload(grant)
    v = _source_payload(grant_verification)
    r = _source_payload(request)
    requested = _tuple(r.get("requested_scope_labels"))
    missing = tuple(sorted((set(requested) - set(_tuple(g.get("granted_scope_labels")))) | set(_tuple(v.get("missing_labels")))))
    status = _consumption_status(g, v, r)
    provisional = GrantConsumptionVerification(
        _digest_id("grant-consumption-verification-", {"request": r.get("request_id"), "grant": g.get("grant_id"), "status": status, "scope": requested}),
        str(r.get("request_id", "")),
        str(g.get("grant_id", "")),
        str(g.get("grant_status", "")),
        str(v.get("verification_status", "")),
        status,
        requested,
        str(r.get("requested_time_label", v.get("checked_time_label", ""))),
        _tuple(v.get("checked_revocation_labels")),
        missing,
        tuple(sorted(set(_tuple(r.get("blocked_actions"))) | set(_tuple(g.get("blocked_actions"))))),
        tuple(sorted(set(_tuple(r.get("warning_codes"))) | set(_tuple(v.get("warning_codes"))))),
        tuple(sorted(set(_tuple(r.get("risk_codes"))) | set(_tuple(v.get("risk_codes"))) | {"grant_consumption_verification_is_not_fulfillment_authorization"})),
        "",
    )
    return replace(provisional, digest=grant_consumption_verification_digest(provisional))


def assess_fulfillment_scope_match(grant: Any, request: Any) -> FulfillmentScopeMatchAssessment:
    g = _source_payload(grant)
    r = _source_payload(request)
    requested = set(_tuple(r.get("requested_scope_labels")))
    granted = set(_tuple(g.get("granted_scope_labels")))
    matched = requested & granted
    missing = requested - granted
    extra = granted - requested
    if "contradicted" in str(r.get("request_status", "")) or "contradicted" in str(g.get("grant_status", "")):
        status = "fulfillment_scope_contradicted"
    elif not requested or not granted:
        status = "fulfillment_scope_missing"
    elif missing:
        status = "fulfillment_scope_mismatch"
    elif extra or str(g.get("grant_status")) == "local_authorization_grant_active_with_conditions":
        status = "fulfillment_scope_match_with_conditions"
    else:
        status = "fulfillment_scope_match"
    provisional = FulfillmentScopeMatchAssessment(
        _digest_id("fulfillment-scope-match-", {"request": r.get("request_id"), "grant": g.get("grant_id"), "requested": sorted(requested), "granted": sorted(granted)}),
        str(r.get("request_id", "")),
        str(g.get("grant_id", "")),
        tuple(sorted(requested)),
        tuple(sorted(granted)),
        tuple(sorted(matched)),
        tuple(sorted(missing)),
        tuple(sorted(extra)),
        status,
        tuple(sorted(set(_tuple(r.get("warning_codes"))))),
        ("scope_match_is_not_execution",),
        "",
    )
    return replace(provisional, digest=fulfillment_scope_match_assessment_digest(provisional))


def _receipt_status(consumption_status: str, scope_status: str) -> str:
    if consumption_status == "grant_consumption_verified" and scope_status == "fulfillment_scope_match":
        return "fulfillment_authorization_consumption_recorded"
    if consumption_status == "grant_consumption_verified_with_conditions" and scope_status in {"fulfillment_scope_match", "fulfillment_scope_match_with_conditions"}:
        return "fulfillment_authorization_consumption_recorded_with_warnings"
    if consumption_status.endswith("expired"):
        return "fulfillment_authorization_consumption_expired"
    if consumption_status.endswith("revoked"):
        return "fulfillment_authorization_consumption_revoked"
    if consumption_status.endswith("out_of_scope") or scope_status == "fulfillment_scope_mismatch":
        return "fulfillment_authorization_consumption_out_of_scope"
    if consumption_status.endswith("contradicted") or scope_status == "fulfillment_scope_contradicted":
        return "fulfillment_authorization_consumption_contradicted"
    if consumption_status.endswith("incomplete") or scope_status == "fulfillment_scope_missing":
        return "fulfillment_authorization_consumption_incomplete"
    return "fulfillment_authorization_consumption_blocked"


def build_fulfillment_authorization_consumption_receipt(request: Any, verification: Any, assessment: Any, *, receipt_id: str | None = None, created_at: str = "1970-01-01T00:00:00+00:00") -> FulfillmentAuthorizationConsumptionReceipt:
    r = _source_payload(request)
    v = _source_payload(verification)
    a = _source_payload(assessment)
    status = _receipt_status(str(v.get("consumption_status", "")), str(a.get("scope_match_status", "")))
    consumed = status in {"fulfillment_authorization_consumption_recorded", "fulfillment_authorization_consumption_recorded_with_warnings"}
    provisional = FulfillmentAuthorizationConsumptionReceipt(
        receipt_id or _digest_id("fulfillment-auth-consumption-", {"request": r.get("request_id"), "verification": v.get("verification_id"), "assessment": a.get("assessment_id"), "status": status}),
        str(r.get("request_id", "")),
        str(v.get("grant_id", "")),
        str(v.get("verification_id", "")),
        str(a.get("assessment_id", "")),
        str(r.get("requested_fulfillment_domain", "")),
        str(r.get("requested_backend_class", "")),
        status,
        (
            f"grant_status:{v.get('grant_status', '')}",
            f"grant_verification_status:{v.get('grant_verification_status', '')}",
            f"scope_match_status:{a.get('scope_match_status', '')}",
            "consumption_receipt_does_not_execute",
            "real_fulfillment_remains_deferred",
        ),
        _FUTURE_GATES,
        tuple(sorted(set(_tuple(r.get("blocked_actions"))) | set(_tuple(v.get("blocked_actions"))))),
        tuple(sorted(set(_tuple(r.get("warning_codes"))) | set(_tuple(v.get("warning_codes"))) | set(_tuple(a.get("warning_codes"))))),
        tuple(sorted(set(_tuple(r.get("risk_codes"))) | set(_tuple(v.get("risk_codes"))) | set(_tuple(a.get("risk_codes"))) | {"consumption_receipt_is_not_fulfillment"})),
        created_at,
        "",
        authorization_consumed_for_future_fulfillment=consumed,
    )
    return replace(provisional, digest=fulfillment_authorization_consumption_receipt_digest(provisional))


def build_fulfillment_authorization_denial_receipt(request: Any, verification: Any | None = None, assessment: Any | None = None, *, receipt_id: str | None = None, created_at: str = "1970-01-01T00:00:00+00:00") -> FulfillmentAuthorizationDenialReceipt:
    r = _source_payload(request)
    v = _source_payload(verification) if verification is not None else {}
    a = _source_payload(assessment) if assessment is not None else {}
    reasons = set()
    for status in (r.get("request_status"), v.get("consumption_status"), a.get("scope_match_status")):
        if status:
            reasons.add(str(status))
    if not reasons:
        reasons.add("fulfillment_authorization_denied")
    if any("contradicted" in reason for reason in reasons):
        status = "fulfillment_authorization_denial_contradicted"
    elif any("incomplete" in reason or "missing" in reason for reason in reasons):
        status = "fulfillment_authorization_denial_incomplete"
    elif any("blocked" in reason for reason in reasons):
        status = "fulfillment_authorization_denial_blocked"
    else:
        status = "fulfillment_authorization_denial_recorded"
    missing = tuple(sorted(set(_tuple(v.get("missing_labels"))) | set(_tuple(a.get("missing_scope_labels"))) | (REQUIRED_REQUEST_LABELS - set(_tuple(r.get("required_request_labels"))))))
    provisional = FulfillmentAuthorizationDenialReceipt(
        receipt_id or _digest_id("fulfillment-auth-denial-", {"request": r.get("request_id"), "grant": v.get("grant_id"), "reasons": sorted(reasons)}),
        str(r.get("request_id", "")),
        str(v.get("grant_id")) if v.get("grant_id") else None,
        status,
        tuple(sorted(reasons | {"denial_receipt_does_not_execute"})),
        missing,
        tuple(sorted(set(_tuple(r.get("blocked_actions"))) | set(_tuple(v.get("blocked_actions"))))),
        tuple(sorted(set(_tuple(r.get("warning_codes"))) | set(_tuple(v.get("warning_codes"))) | set(_tuple(a.get("warning_codes"))))),
        tuple(sorted(set(_tuple(r.get("risk_codes"))) | set(_tuple(v.get("risk_codes"))) | set(_tuple(a.get("risk_codes"))) | {"denial_is_not_fulfillment"})),
        created_at,
        "",
    )
    return replace(provisional, digest=fulfillment_authorization_denial_receipt_digest(provisional))


def _validate_common(payload: Mapping[str, Any], prefix: str) -> list[str]:
    findings: list[str] = []
    if not payload.get("metadata_only", False):
        findings.append(prefix + "not_metadata_only")
    for flag in ("does_not_execute", "does_not_mutate_host"):
        if flag in payload and not payload.get(flag, False):
            findings.append(prefix + flag + "_false")
    return findings


def validate_fulfillment_authorization_request(request: FulfillmentAuthorizationRequest | Mapping[str, Any]) -> FulfillmentAuthorizationValidationResult:
    p = _source_payload(request)
    f = _validate_common(p, "request:")
    if p.get("request_status") not in REQUEST_STATUSES:
        f.append("request:unknown_status")
    if p.get("requested_fulfillment_domain") not in FULFILLMENT_DOMAINS:
        f.append("request:unknown_domain")
    if not p.get("request_only", False):
        f.append("request:not_request_only")
    for flag in ("fulfillment_granted", "effect_performed", "host_mutation_performed"):
        if p.get(flag, False):
            f.append(f"request:forbidden_flag:{flag}")
    if p.get("digest") and p.get("digest") != fulfillment_authorization_request_digest(p):
        f.append("request:digest_mismatch")
    return FulfillmentAuthorizationValidationResult(not f, tuple(f))


def validate_grant_consumption_verification(verification: GrantConsumptionVerification | Mapping[str, Any]) -> FulfillmentAuthorizationValidationResult:
    p = _source_payload(verification)
    f = _validate_common(p, "verification:")
    if p.get("consumption_status") not in CONSUMPTION_VERIFICATION_STATUSES:
        f.append("verification:unknown_status")
    if not p.get("verification_only", False):
        f.append("verification:not_verification_only")
    if p.get("authorizes_fulfillment", False):
        f.append("verification:authorizes_fulfillment")
    if p.get("digest") and p.get("digest") != grant_consumption_verification_digest(p):
        f.append("verification:digest_mismatch")
    return FulfillmentAuthorizationValidationResult(not f, tuple(f))


def validate_fulfillment_scope_match_assessment(assessment: FulfillmentScopeMatchAssessment | Mapping[str, Any]) -> FulfillmentAuthorizationValidationResult:
    p = _source_payload(assessment)
    f = _validate_common(p, "scope:")
    if p.get("scope_match_status") not in SCOPE_MATCH_STATUSES:
        f.append("scope:unknown_status")
    if not p.get("assessment_only", False):
        f.append("scope:not_assessment_only")
    if p.get("authorizes_fulfillment", False):
        f.append("scope:authorizes_fulfillment")
    if p.get("digest") and p.get("digest") != fulfillment_scope_match_assessment_digest(p):
        f.append("scope:digest_mismatch")
    return FulfillmentAuthorizationValidationResult(not f, tuple(f))


def validate_fulfillment_authorization_consumption_receipt(receipt: FulfillmentAuthorizationConsumptionReceipt | Mapping[str, Any]) -> FulfillmentAuthorizationValidationResult:
    p = _source_payload(receipt)
    f: list[str] = []
    if not p.get("metadata_only", False):
        f.append("receipt:not_metadata_only")
    if not p.get("consumption_receipt_only", False):
        f.append("receipt:not_consumption_receipt_only")
    if p.get("consumption_status") not in CONSUMPTION_RECEIPT_STATUSES:
        f.append("receipt:unknown_status")
    if p.get("authorization_consumed_for_future_fulfillment", False) and p.get("consumption_status") not in {"fulfillment_authorization_consumption_recorded", "fulfillment_authorization_consumption_recorded_with_warnings"}:
        f.append("receipt:consumed_without_verified_scope_match")
    for flag in _FORBIDDEN_TRUE_FLAGS:
        if p.get(flag, False):
            f.append(f"receipt:forbidden_flag:{flag}")
    if p.get("digest") and p.get("digest") != fulfillment_authorization_consumption_receipt_digest(p):
        f.append("receipt:digest_mismatch")
    return FulfillmentAuthorizationValidationResult(not f, tuple(f))


def validate_fulfillment_authorization_denial_receipt(receipt: FulfillmentAuthorizationDenialReceipt | Mapping[str, Any]) -> FulfillmentAuthorizationValidationResult:
    p = _source_payload(receipt)
    f = _validate_common(p, "denial:")
    if p.get("denial_status") not in DENIAL_RECEIPT_STATUSES:
        f.append("denial:unknown_status")
    if not p.get("denial_receipt_only", False):
        f.append("denial:not_denial_receipt_only")
    for flag in ("authorization_consumed_for_future_fulfillment", "fulfillment_granted", "effect_performed", "host_mutation_performed"):
        if p.get(flag, False):
            f.append(f"denial:forbidden_flag:{flag}")
    if p.get("digest") and p.get("digest") != fulfillment_authorization_denial_receipt_digest(p):
        f.append("denial:digest_mismatch")
    return FulfillmentAuthorizationValidationResult(not f, tuple(f))


def summarize_fulfillment_authorization_request(request: FulfillmentAuthorizationRequest | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(request)
    return {k: p.get(k) for k in ("request_id", "source_local_authorization_grant_id", "requested_fulfillment_domain", "requested_backend_class", "request_status", "metadata_only", "request_only", "fulfillment_requested", "fulfillment_granted", "effect_performed", "host_mutation_performed", "does_not_execute", "does_not_mutate_host", "digest")}


def summarize_grant_consumption_verification(verification: GrantConsumptionVerification | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(verification)
    return {k: p.get(k) for k in ("verification_id", "request_id", "grant_id", "grant_status", "grant_verification_status", "consumption_status", "metadata_only", "verification_only", "authorizes_fulfillment", "does_not_execute", "does_not_mutate_host", "digest")}


def summarize_fulfillment_scope_match_assessment(assessment: FulfillmentScopeMatchAssessment | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(assessment)
    return {k: p.get(k) for k in ("assessment_id", "request_id", "grant_id", "scope_match_status", "matched_scope_labels", "missing_scope_labels", "metadata_only", "assessment_only", "authorizes_fulfillment", "does_not_execute", "does_not_mutate_host", "digest")}


def summarize_fulfillment_authorization_consumption_receipt(receipt: FulfillmentAuthorizationConsumptionReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(receipt)
    return {k: p.get(k) for k in ("receipt_id", "request_id", "grant_id", "consumption_status", "metadata_only", "consumption_receipt_only", "authorization_consumed_for_future_fulfillment", "fulfillment_granted", "effect_performed", "host_mutation_performed", "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed", "service_restart_performed", "file_cleanup_performed", "provider_invocation_performed", "network_performed", "prompt_assembly_performed", "digest")}


def summarize_fulfillment_authorization_denial_receipt(receipt: FulfillmentAuthorizationDenialReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(receipt)
    return {k: p.get(k) for k in ("receipt_id", "request_id", "grant_id", "denial_status", "metadata_only", "denial_receipt_only", "authorization_consumed_for_future_fulfillment", "fulfillment_granted", "effect_performed", "host_mutation_performed", "does_not_execute", "does_not_mutate_host", "digest")}


def build_fulfillment_authorization_wing(
    grant: Any,
    grant_verification: Any,
    *,
    requested_fulfillment_domain: str,
    requested_backend_class: str,
    requested_scope_labels: Sequence[str] | None = None,
    requested_time_label: str = "1970-01-01T00:00:00+00:00",
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> FulfillmentAuthorizationWingRecords:
    request = build_fulfillment_authorization_request(
        grant,
        grant_verification,
        requested_fulfillment_domain=requested_fulfillment_domain,
        requested_backend_class=requested_backend_class,
        requested_scope_labels=requested_scope_labels,
        requested_time_label=requested_time_label,
        created_at=created_at,
    )
    verification = verify_grant_consumption_for_fulfillment(grant, grant_verification, request)
    assessment = assess_fulfillment_scope_match(grant, request)
    receipt = build_fulfillment_authorization_consumption_receipt(request, verification, assessment, created_at=created_at)
    if receipt.authorization_consumed_for_future_fulfillment:
        return FulfillmentAuthorizationWingRecords(request, verification, assessment, receipt, None)
    denial = build_fulfillment_authorization_denial_receipt(request, verification, assessment, created_at=created_at)
    return FulfillmentAuthorizationWingRecords(request, verification, assessment, None, denial)
