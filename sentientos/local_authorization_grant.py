"""Metadata-only local authorization grant records.

This wing follows live-grant readiness and records bounded local authorization
metadata. It does not fulfill actions, execute host changes, perform provider
work, assemble prompts, or mutate host state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, NamedTuple, Sequence

GRANT_STATUSES = frozenset({
    "local_authorization_grant_active",
    "local_authorization_grant_active_with_conditions",
    "local_authorization_grant_blocked",
    "local_authorization_grant_incomplete",
    "local_authorization_grant_contradicted",
    "local_authorization_grant_revoked",
    "local_authorization_grant_expired",
})
APPROVAL_EVIDENCE_STATUSES = frozenset({
    "approval_evidence_present",
    "approval_evidence_present_with_conditions",
    "approval_evidence_missing",
    "approval_evidence_blocked",
    "approval_evidence_contradicted",
})
LEDGER_STATUSES = frozenset({
    "local_authorization_grant_ledger_current",
    "local_authorization_grant_ledger_current_with_warnings",
    "local_authorization_grant_ledger_blocked",
    "local_authorization_grant_ledger_incomplete",
    "local_authorization_grant_ledger_contradicted",
})
REVOCATION_STATUSES = frozenset({
    "local_authorization_revocation_recorded",
    "local_authorization_revocation_blocked",
    "local_authorization_revocation_incomplete",
    "local_authorization_revocation_contradicted",
})
EXPIRY_STATUSES = frozenset({
    "local_authorization_expiry_not_expired",
    "local_authorization_expiry_expired",
    "local_authorization_expiry_missing_bounds",
    "local_authorization_expiry_contradicted",
})
VERIFICATION_STATUSES = frozenset({
    "local_authorization_verification_valid",
    "local_authorization_verification_valid_with_conditions",
    "local_authorization_verification_blocked",
    "local_authorization_verification_expired",
    "local_authorization_verification_revoked",
    "local_authorization_verification_incomplete",
    "local_authorization_verification_contradicted",
})
AUTHORIZATION_DOMAINS = frozenset({
    "diagnostics_local_authorization",
    "operator_review_local_authorization",
    "resource_pressure_local_authorization",
    "thermal_safety_local_authorization",
    "future_cooling_local_authorization",
    "future_power_local_authorization",
    "future_cleanup_local_authorization",
    "future_service_local_authorization",
})
GRANT_SCOPES = frozenset({
    "diagnostics_only_scope",
    "operator_review_scope",
    "resource_pressure_review_scope",
    "thermal_safety_review_scope",
    "future_cooling_scope",
    "future_power_scope",
    "future_cleanup_scope",
    "future_service_scope",
})
REQUIRED_GRANT_PREREQUISITES = frozenset({
    "live_grant_readiness_preflight_required",
    "operator_approval_evidence_required",
    "policy_approval_evidence_required",
    "explicit_scope_required",
    "time_bounds_required",
    "expiry_required",
    "revocation_path_required",
    "control_plane_admission_required_for_future_fulfillment",
    "audit_receipt_required_for_future_fulfillment",
    "rollback_receipt_required_for_future_fulfillment",
    "effect_receipt_required_for_future_fulfillment",
    "postcondition_check_required_for_future_fulfillment",
    "runtime_supervisor_observation_required_for_future_fulfillment",
    "immutable_trace_required_for_future_fulfillment",
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
    "diagnostics_local_authorization": "diagnostics_only_scope",
    "operator_review_local_authorization": "operator_review_scope",
    "resource_pressure_local_authorization": "resource_pressure_review_scope",
    "thermal_safety_local_authorization": "thermal_safety_review_scope",
    "future_cooling_local_authorization": "future_cooling_scope",
    "future_power_local_authorization": "future_power_scope",
    "future_cleanup_local_authorization": "future_cleanup_scope",
    "future_service_local_authorization": "future_service_scope",
}
_READINESS_DOMAIN = {
    "diagnostics_live_grant_review": "diagnostics_local_authorization",
    "operator_review_live_grant_review": "operator_review_local_authorization",
    "resource_pressure_live_grant_review": "resource_pressure_local_authorization",
    "thermal_safety_live_grant_review": "thermal_safety_local_authorization",
    "future_cooling_live_grant_review": "future_cooling_local_authorization",
    "future_power_live_grant_review": "future_power_local_authorization",
    "future_cleanup_live_grant_review": "future_cleanup_local_authorization",
    "future_service_live_grant_review": "future_service_local_authorization",
}
_DOMAIN_BLOCKS = {
    "future_cooling_local_authorization": ("fan_pwm_write", "thermal_actuation"),
    "future_power_local_authorization": ("power_profile_mutation",),
    "future_cleanup_local_authorization": ("file_cleanup", "file_delete"),
    "future_service_local_authorization": ("service_restart", "process_kill"),
}
_FORBIDDEN_TRUE_FLAGS = (
    "fulfillment_granted", "effect_performed", "host_mutation_performed", "fan_pwm_write_performed",
    "thermal_actuation_performed", "power_profile_mutation_performed", "process_kill_performed",
    "service_restart_performed", "package_install_performed", "driver_install_performed",
    "file_cleanup_performed", "provider_invocation_performed", "network_performed", "prompt_assembly_performed",
)

@dataclass(frozen=True)
class LocalAuthorizationPolicy:
    policy_id: str
    required_prerequisites: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    metadata_only: bool = True
    authorization_record_only: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class OperatorApprovalEvidence:
    evidence_id: str
    operator_identity_label: str
    approval_scope_labels: tuple[str, ...]
    approval_time_bounds: tuple[str, ...]
    approval_expiry_label: str
    approval_revocation_label: str
    approval_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    approval_evidence_only: bool = True
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class PolicyApprovalEvidence:
    evidence_id: str
    policy_identity_label: str
    policy_scope_labels: tuple[str, ...]
    policy_time_bounds: tuple[str, ...]
    policy_expiry_label: str
    policy_revocation_label: str
    approval_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    approval_evidence_only: bool = True
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class LocalAuthorizationGrant:
    grant_id: str
    source_live_grant_preflight_receipt_id: str
    source_live_grant_preflight_receipt_digest: str
    source_prerequisite_matrix_id: str
    operator_approval_evidence_id: str
    operator_approval_evidence_digest: str
    policy_approval_evidence_id: str
    policy_approval_evidence_digest: str
    authorization_domain: str
    grant_scope: str
    grant_status: str
    granted_scope_labels: tuple[str, ...]
    granted_time_bounds: tuple[str, ...]
    expiry_label: str
    revocation_path_labels: tuple[str, ...]
    required_future_fulfillment_gates: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    authorization_record_only: bool = True
    live_authorization_granted: bool = False
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
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class LocalAuthorizationGrantRevocationReceipt:
    receipt_id: str
    grant_id: str
    revocation_status: str
    revocation_reason_codes: tuple[str, ...]
    revocation_effective_label: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    revocation_record_only: bool = True
    live_authorization_revoked: bool = False
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class LocalAuthorizationGrantExpiryEvaluation:
    evaluation_id: str
    grant_id: str
    expiry_status: str
    evaluated_at: str
    expiry_label: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    digest: str
    metadata_only: bool = True
    expiry_evaluation_only: bool = True
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class LocalAuthorizationGrantVerification:
    verification_id: str
    grant_id: str
    verification_status: str
    checked_scope_labels: tuple[str, ...]
    checked_time_label: str
    checked_revocation_labels: tuple[str, ...]
    missing_labels: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    digest: str
    metadata_only: bool = True
    verification_only: bool = True
    authorizes_fulfillment: bool = False
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class LocalAuthorizationGrantLedger:
    ledger_id: str
    grant_records: tuple[LocalAuthorizationGrant, ...]
    revocation_receipts: tuple[LocalAuthorizationGrantRevocationReceipt, ...]
    expiry_evaluations: tuple[LocalAuthorizationGrantExpiryEvaluation, ...]
    ledger_status: str
    active_grant_count: int
    revoked_grant_count: int
    expired_grant_count: int
    blocked_grant_count: int
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    authorization_ledger_only: bool = True
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class LocalAuthorizationGrantValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()

class LocalAuthorizationGrantWingRecords(NamedTuple):
    grant: LocalAuthorizationGrant
    expiry_evaluation: LocalAuthorizationGrantExpiryEvaluation
    verification: LocalAuthorizationGrantVerification
    revocation_receipt: LocalAuthorizationGrantRevocationReceipt
    ledger: LocalAuthorizationGrantLedger


def _tuple(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))

def _payload(record_or_payload: Any) -> dict[str, Any]:
    payload = record_or_payload.to_dict() if hasattr(record_or_payload, "to_dict") else dict(record_or_payload)
    payload["digest"] = ""
    return payload

def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)

def local_authorization_grant_digest(record_or_payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(_payload(record_or_payload)).encode("utf-8")).hexdigest()

operator_approval_evidence_digest = local_authorization_grant_digest
policy_approval_evidence_digest = local_authorization_grant_digest
local_authorization_grant_revocation_receipt_digest = local_authorization_grant_digest
local_authorization_grant_expiry_evaluation_digest = local_authorization_grant_digest
local_authorization_grant_verification_digest = local_authorization_grant_digest
local_authorization_grant_ledger_digest = local_authorization_grant_digest

def _digest_id(prefix: str, payload: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:24]

def build_default_local_authorization_policy() -> LocalAuthorizationPolicy:
    return LocalAuthorizationPolicy("local-authorization-grant-policy-v1", tuple(sorted(REQUIRED_GRANT_PREREQUISITES)), tuple(sorted(BLOCKED_ACTION_LABELS)))

def build_operator_approval_evidence(*, evidence_id: str | None = None, operator_identity_label: str = "sample_operator", approval_scope_labels: Sequence[str] = ("future_cooling_scope",), approval_time_bounds: Sequence[str] = ("not_before:1970-01-01T00:00:00+00:00", "not_after:1970-01-02T00:00:00+00:00"), approval_expiry_label: str = "expires:1970-01-02T00:00:00+00:00", approval_revocation_label: str = "revocable:local_authorization_revocation_receipt", approval_status: str = "approval_evidence_present", warning_codes: Sequence[str] = (), risk_codes: Sequence[str] = (), created_at: str = "1970-01-01T00:00:00+00:00") -> OperatorApprovalEvidence:
    eid = evidence_id or _digest_id("operator-approval-", {"operator": operator_identity_label, "scope": _tuple(approval_scope_labels), "created_at": created_at})
    provisional = OperatorApprovalEvidence(eid, operator_identity_label, _tuple(approval_scope_labels), _tuple(approval_time_bounds), approval_expiry_label, approval_revocation_label, approval_status, _tuple(warning_codes), _tuple(risk_codes), created_at, "")
    return replace(provisional, digest=operator_approval_evidence_digest(provisional))

def build_policy_approval_evidence(*, evidence_id: str | None = None, policy_identity_label: str = "sample_policy", policy_scope_labels: Sequence[str] = ("future_cooling_scope",), policy_time_bounds: Sequence[str] = ("not_before:1970-01-01T00:00:00+00:00", "not_after:1970-01-02T00:00:00+00:00"), policy_expiry_label: str = "expires:1970-01-02T00:00:00+00:00", policy_revocation_label: str = "revocable:local_authorization_revocation_receipt", approval_status: str = "approval_evidence_present", warning_codes: Sequence[str] = (), risk_codes: Sequence[str] = (), created_at: str = "1970-01-01T00:00:00+00:00") -> PolicyApprovalEvidence:
    eid = evidence_id or _digest_id("policy-approval-", {"policy": policy_identity_label, "scope": _tuple(policy_scope_labels), "created_at": created_at})
    provisional = PolicyApprovalEvidence(eid, policy_identity_label, _tuple(policy_scope_labels), _tuple(policy_time_bounds), policy_expiry_label, policy_revocation_label, approval_status, _tuple(warning_codes), _tuple(risk_codes), created_at, "")
    return replace(provisional, digest=policy_approval_evidence_digest(provisional))

def _source_payload(source: Any) -> Mapping[str, Any]:
    return source.to_dict() if hasattr(source, "to_dict") else dict(source)

def _grant_status(preflight: Mapping[str, Any], operator: OperatorApprovalEvidence | Mapping[str, Any] | None, policy: PolicyApprovalEvidence | Mapping[str, Any] | None) -> str:
    pstatus = str(preflight.get("preflight_status", ""))
    rstatus = str(preflight.get("readiness_status", ""))
    op = _source_payload(operator) if operator is not None else {"approval_status": "approval_evidence_missing"}
    pol = _source_payload(policy) if policy is not None else {"approval_status": "approval_evidence_missing"}
    statuses = (str(op.get("approval_status", "")), str(pol.get("approval_status", "")))
    if "contradicted" in pstatus or "contradicted" in rstatus or any("contradicted" in s for s in statuses):
        return "local_authorization_grant_contradicted"
    if "blocked" in pstatus or "blocked" in rstatus or any("blocked" in s for s in statuses):
        return "local_authorization_grant_blocked"
    if "incomplete" in pstatus or "incomplete" in rstatus or any("missing" in s for s in statuses):
        return "local_authorization_grant_incomplete"
    if pstatus == "grant_issue_preflight_recorded_with_warnings" or rstatus == "live_grant_readiness_ready_with_conditions" or any(s == "approval_evidence_present_with_conditions" for s in statuses):
        return "local_authorization_grant_active_with_conditions"
    if pstatus == "grant_issue_preflight_recorded" and rstatus == "live_grant_readiness_ready_for_operator_policy_review" and all(s == "approval_evidence_present" for s in statuses):
        return "local_authorization_grant_active"
    return "local_authorization_grant_incomplete"

def build_local_authorization_grant(preflight_receipt: Any, prerequisite_matrix: Any, operator_approval_evidence: OperatorApprovalEvidence | Mapping[str, Any] | None, policy_approval_evidence: PolicyApprovalEvidence | Mapping[str, Any] | None, *, authorization_domain: str | None = None, grant_scope: str | None = None, grant_id: str | None = None, created_at: str = "1970-01-01T00:00:00+00:00") -> LocalAuthorizationGrant:
    preflight = _source_payload(preflight_receipt)
    matrix = _source_payload(prerequisite_matrix)
    op = _source_payload(operator_approval_evidence) if operator_approval_evidence is not None else {}
    pol = _source_payload(policy_approval_evidence) if policy_approval_evidence is not None else {}
    domain = authorization_domain or _READINESS_DOMAIN.get(str(preflight.get("readiness_domain") or matrix.get("readiness_domain")), "future_cooling_local_authorization")
    scope = grant_scope or _DOMAIN_SCOPE.get(domain, "future_cooling_scope")
    status = _grant_status(preflight, operator_approval_evidence, policy_approval_evidence)
    blocked = tuple(sorted(set(BLOCKED_ACTION_LABELS) | set(_tuple(preflight.get("blocked_actions"))) | set(_tuple(matrix.get("blocked_actions"))) | set(_DOMAIN_BLOCKS.get(domain, ()))) )
    warnings = set(_tuple(preflight.get("warning_codes"))) | set(_tuple(matrix.get("warning_codes"))) | set(_tuple(op.get("warning_codes"))) | set(_tuple(pol.get("warning_codes")))
    risks = set(_tuple(preflight.get("risk_codes"))) | set(_tuple(matrix.get("risk_codes"))) | set(_tuple(op.get("risk_codes"))) | set(_tuple(pol.get("risk_codes"))) | {"local_authorization_is_not_fulfillment"}
    if not op:
        warnings.add("operator_approval_evidence_missing")
    if not pol:
        warnings.add("policy_approval_evidence_missing")
    gid = grant_id or _digest_id("local-auth-grant-", {"preflight": preflight.get("receipt_id"), "operator": op.get("evidence_id"), "policy": pol.get("evidence_id"), "domain": domain, "scope": scope})
    provisional = LocalAuthorizationGrant(
        gid, str(preflight.get("receipt_id", "")), str(preflight.get("digest", "")), str(matrix.get("matrix_id", preflight.get("source_prerequisite_matrix_id", ""))),
        str(op.get("evidence_id", "")), str(op.get("digest", "")), str(pol.get("evidence_id", "")), str(pol.get("digest", "")), domain, scope, status,
        tuple(sorted(set(_tuple(op.get("approval_scope_labels"))) | set(_tuple(pol.get("policy_scope_labels"))) | {scope})),
        tuple(sorted(set(_tuple(op.get("approval_time_bounds"))) | set(_tuple(pol.get("policy_time_bounds"))))),
        str(op.get("approval_expiry_label") or pol.get("policy_expiry_label") or ""),
        tuple(sorted({str(op.get("approval_revocation_label", "")), str(pol.get("policy_revocation_label", ""))} - {""})),
        tuple(sorted(REQUIRED_GRANT_PREREQUISITES)), blocked, tuple(sorted(warnings)), tuple(sorted(risks)), created_at, "",
        live_authorization_granted=status in {"local_authorization_grant_active", "local_authorization_grant_active_with_conditions"},
    )
    return replace(provisional, digest=local_authorization_grant_digest(provisional))

def build_local_authorization_grant_revocation_receipt(grant: LocalAuthorizationGrant | Mapping[str, Any], *, receipt_id: str | None = None, revocation_status: str = "local_authorization_revocation_recorded", revocation_reason_codes: Sequence[str] = ("operator_or_policy_revocation_recorded",), revocation_effective_label: str = "effective:immediate", warning_codes: Sequence[str] = (), risk_codes: Sequence[str] = (), created_at: str = "1970-01-01T00:00:00+00:00") -> LocalAuthorizationGrantRevocationReceipt:
    g = _source_payload(grant)
    rid = receipt_id or _digest_id("local-auth-revocation-", {"grant": g.get("grant_id"), "status": revocation_status, "created_at": created_at})
    provisional = LocalAuthorizationGrantRevocationReceipt(rid, str(g.get("grant_id", "")), revocation_status, _tuple(revocation_reason_codes), revocation_effective_label, _tuple(warning_codes), _tuple(risk_codes), created_at, "", live_authorization_revoked=revocation_status == "local_authorization_revocation_recorded")
    return replace(provisional, digest=local_authorization_grant_revocation_receipt_digest(provisional))

def build_local_authorization_grant_expiry_evaluation(grant: LocalAuthorizationGrant | Mapping[str, Any], *, evaluated_at: str = "1970-01-01T00:00:00+00:00", expiry_status: str | None = None, warning_codes: Sequence[str] = (), risk_codes: Sequence[str] = ()) -> LocalAuthorizationGrantExpiryEvaluation:
    g = _source_payload(grant)
    expiry = str(g.get("expiry_label", ""))
    status = expiry_status or ("local_authorization_expiry_missing_bounds" if not expiry else ("local_authorization_expiry_expired" if expiry.startswith("expired") or (expiry.startswith("expires:") and evaluated_at > expiry.removeprefix("expires:")) else "local_authorization_expiry_not_expired"))
    provisional = LocalAuthorizationGrantExpiryEvaluation(_digest_id("local-auth-expiry-", {"grant": g.get("grant_id"), "evaluated_at": evaluated_at, "expiry": expiry}), str(g.get("grant_id", "")), status, evaluated_at, expiry, _tuple(warning_codes), _tuple(risk_codes), "")
    return replace(provisional, digest=local_authorization_grant_expiry_evaluation_digest(provisional))

def verify_local_authorization_grant(grant: LocalAuthorizationGrant | Mapping[str, Any], *, checked_scope_labels: Sequence[str] | None = None, checked_time_label: str = "1970-01-01T00:00:00+00:00", checked_revocation_labels: Sequence[str] = (), expiry_evaluation: LocalAuthorizationGrantExpiryEvaluation | Mapping[str, Any] | None = None, revocation_receipts: Sequence[LocalAuthorizationGrantRevocationReceipt | Mapping[str, Any]] = ()) -> LocalAuthorizationGrantVerification:
    g = _source_payload(grant)
    checked = _tuple(checked_scope_labels) or _tuple(g.get("granted_scope_labels"))
    missing = tuple(sorted(set(checked) - set(_tuple(g.get("granted_scope_labels")))))
    status = "local_authorization_verification_valid"
    if str(g.get("grant_status", "")).endswith("contradicted"):
        status = "local_authorization_verification_contradicted"
    elif str(g.get("grant_status", "")).endswith("blocked"):
        status = "local_authorization_verification_blocked"
    elif str(g.get("grant_status", "")).endswith("incomplete") or missing:
        status = "local_authorization_verification_incomplete"
    elif str(g.get("grant_status", "")).endswith("expired") or (expiry_evaluation is not None and "expired" in str(_source_payload(expiry_evaluation).get("expiry_status"))):
        status = "local_authorization_verification_expired"
    elif str(g.get("grant_status", "")).endswith("revoked") or any(_source_payload(r).get("revocation_status") == "local_authorization_revocation_recorded" for r in revocation_receipts):
        status = "local_authorization_verification_revoked"
    elif str(g.get("grant_status")) == "local_authorization_grant_active_with_conditions":
        status = "local_authorization_verification_valid_with_conditions"
    provisional = LocalAuthorizationGrantVerification(_digest_id("local-auth-verification-", {"grant": g.get("grant_id"), "scope": checked, "time": checked_time_label, "rev": _tuple(checked_revocation_labels)}), str(g.get("grant_id", "")), status, checked, checked_time_label, _tuple(checked_revocation_labels), missing, (), ("verification_is_not_fulfillment_authorization",), "")
    return replace(provisional, digest=local_authorization_grant_verification_digest(provisional))

def build_local_authorization_grant_ledger(grant_records: Sequence[LocalAuthorizationGrant], revocation_receipts: Sequence[LocalAuthorizationGrantRevocationReceipt] = (), expiry_evaluations: Sequence[LocalAuthorizationGrantExpiryEvaluation] = (), *, ledger_id: str | None = None, created_at: str = "1970-01-01T00:00:00+00:00") -> LocalAuthorizationGrantLedger:
    grants = tuple(grant_records); revocations = tuple(revocation_receipts); expiries = tuple(expiry_evaluations)
    statuses = {g.grant_status for g in grants} | {r.revocation_status for r in revocations} | {e.expiry_status for e in expiries}
    if any("contradicted" in s for s in statuses): ledger_status = "local_authorization_grant_ledger_contradicted"
    elif any("incomplete" in s or "missing" in s for s in statuses): ledger_status = "local_authorization_grant_ledger_incomplete"
    elif any("blocked" in s for s in statuses): ledger_status = "local_authorization_grant_ledger_blocked"
    elif any(g.warning_codes for g in grants) or any(r.warning_codes for r in revocations) or any(e.warning_codes for e in expiries): ledger_status = "local_authorization_grant_ledger_current_with_warnings"
    else: ledger_status = "local_authorization_grant_ledger_current"
    revoked_ids = {r.grant_id for r in revocations if r.revocation_status == "local_authorization_revocation_recorded"}
    expired_ids = {e.grant_id for e in expiries if e.expiry_status == "local_authorization_expiry_expired"}
    provisional = LocalAuthorizationGrantLedger(ledger_id or _digest_id("local-auth-ledger-", {"grants": [g.grant_id for g in grants], "revocations": [r.receipt_id for r in revocations], "expiries": [e.evaluation_id for e in expiries]}), grants, revocations, expiries, ledger_status, sum(1 for g in grants if g.grant_status.startswith("local_authorization_grant_active") and g.grant_id not in revoked_ids and g.grant_id not in expired_ids), len(revoked_ids), len(expired_ids), sum(1 for g in grants if g.grant_status == "local_authorization_grant_blocked"), tuple(sorted({w for g in grants for w in g.warning_codes})), tuple(sorted({r for g in grants for r in g.risk_codes} | {"ledger_does_not_mutate_host"})), created_at, "")
    return replace(provisional, digest=local_authorization_grant_ledger_digest(provisional))

def _validate_common(payload: Mapping[str, Any], prefix: str) -> list[str]:
    findings: list[str] = []
    if not payload.get("metadata_only", False): findings.append(prefix + "not_metadata_only")
    for flag in ("does_not_execute", "does_not_mutate_host"):
        if flag in payload and not payload.get(flag, False): findings.append(prefix + flag + "_false")
    return findings

def validate_operator_approval_evidence(evidence: OperatorApprovalEvidence | Mapping[str, Any]) -> LocalAuthorizationGrantValidationResult:
    p = _source_payload(evidence); f = _validate_common(p, "operator_approval:")
    if p.get("approval_status") not in APPROVAL_EVIDENCE_STATUSES: f.append("operator_approval:unknown_status")
    if not p.get("approval_evidence_only", False): f.append("operator_approval:not_evidence_only")
    if p.get("digest") and p.get("digest") != operator_approval_evidence_digest(p): f.append("operator_approval:digest_mismatch")
    return LocalAuthorizationGrantValidationResult(not f, tuple(f))

def validate_policy_approval_evidence(evidence: PolicyApprovalEvidence | Mapping[str, Any]) -> LocalAuthorizationGrantValidationResult:
    p = _source_payload(evidence); f = _validate_common(p, "policy_approval:")
    if p.get("approval_status") not in APPROVAL_EVIDENCE_STATUSES: f.append("policy_approval:unknown_status")
    if not p.get("approval_evidence_only", False): f.append("policy_approval:not_evidence_only")
    if p.get("digest") and p.get("digest") != policy_approval_evidence_digest(p): f.append("policy_approval:digest_mismatch")
    return LocalAuthorizationGrantValidationResult(not f, tuple(f))

def validate_local_authorization_grant(grant: LocalAuthorizationGrant | Mapping[str, Any]) -> LocalAuthorizationGrantValidationResult:
    p = _source_payload(grant); f = _validate_common(p, "grant:")
    if p.get("grant_status") not in GRANT_STATUSES: f.append("grant:unknown_status")
    if p.get("authorization_domain") not in AUTHORIZATION_DOMAINS: f.append("grant:unknown_domain")
    if p.get("grant_scope") not in GRANT_SCOPES: f.append("grant:unknown_scope")
    if not p.get("authorization_record_only", False): f.append("grant:not_authorization_record_only")
    for flag in _FORBIDDEN_TRUE_FLAGS:
        if p.get(flag, False): f.append(f"grant:forbidden_flag:{flag}")
    if p.get("live_authorization_granted", False) and p.get("grant_status") not in {"local_authorization_grant_active", "local_authorization_grant_active_with_conditions"}: f.append("grant:live_authorization_without_active_status")
    if p.get("digest") and p.get("digest") != local_authorization_grant_digest(p): f.append("grant:digest_mismatch")
    return LocalAuthorizationGrantValidationResult(not f, tuple(f))

def validate_local_authorization_grant_revocation_receipt(receipt: LocalAuthorizationGrantRevocationReceipt | Mapping[str, Any]) -> LocalAuthorizationGrantValidationResult:
    p = _source_payload(receipt); f = _validate_common(p, "revocation:")
    if p.get("revocation_status") not in REVOCATION_STATUSES: f.append("revocation:unknown_status")
    if p.get("live_authorization_revoked", False) and p.get("revocation_status") != "local_authorization_revocation_recorded": f.append("revocation:revoked_flag_without_recorded_status")
    if p.get("digest") and p.get("digest") != local_authorization_grant_revocation_receipt_digest(p): f.append("revocation:digest_mismatch")
    return LocalAuthorizationGrantValidationResult(not f, tuple(f))

def validate_local_authorization_grant_expiry_evaluation(evaluation: LocalAuthorizationGrantExpiryEvaluation | Mapping[str, Any]) -> LocalAuthorizationGrantValidationResult:
    p = _source_payload(evaluation); f = _validate_common(p, "expiry:")
    if p.get("expiry_status") not in EXPIRY_STATUSES: f.append("expiry:unknown_status")
    if not p.get("expiry_evaluation_only", False): f.append("expiry:not_evaluation_only")
    if p.get("digest") and p.get("digest") != local_authorization_grant_expiry_evaluation_digest(p): f.append("expiry:digest_mismatch")
    return LocalAuthorizationGrantValidationResult(not f, tuple(f))

def validate_local_authorization_grant_verification(verification: LocalAuthorizationGrantVerification | Mapping[str, Any]) -> LocalAuthorizationGrantValidationResult:
    p = _source_payload(verification); f = _validate_common(p, "verification:")
    if p.get("verification_status") not in VERIFICATION_STATUSES: f.append("verification:unknown_status")
    if p.get("authorizes_fulfillment", False): f.append("verification:authorizes_fulfillment")
    if p.get("digest") and p.get("digest") != local_authorization_grant_verification_digest(p): f.append("verification:digest_mismatch")
    return LocalAuthorizationGrantValidationResult(not f, tuple(f))

def validate_local_authorization_grant_ledger(ledger: LocalAuthorizationGrantLedger | Mapping[str, Any]) -> LocalAuthorizationGrantValidationResult:
    p = _source_payload(ledger); f: list[str] = []
    if not p.get("metadata_only", False): f.append("ledger:not_metadata_only")
    if not p.get("authorization_ledger_only", False): f.append("ledger:not_authorization_ledger_only")
    if p.get("host_mutation_performed", False): f.append("ledger:host_mutation_performed")
    if p.get("ledger_status") not in LEDGER_STATUSES: f.append("ledger:unknown_status")
    if p.get("digest") and p.get("digest") != local_authorization_grant_ledger_digest(p): f.append("ledger:digest_mismatch")
    return LocalAuthorizationGrantValidationResult(not f, tuple(f))

def summarize_operator_approval_evidence(evidence: OperatorApprovalEvidence | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(evidence); return {k: p.get(k) for k in ("evidence_id", "operator_identity_label", "approval_status", "metadata_only", "approval_evidence_only", "does_not_execute", "does_not_mutate_host", "digest")}

def summarize_policy_approval_evidence(evidence: PolicyApprovalEvidence | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(evidence); return {k: p.get(k) for k in ("evidence_id", "policy_identity_label", "approval_status", "metadata_only", "approval_evidence_only", "does_not_execute", "does_not_mutate_host", "digest")}

def summarize_local_authorization_grant(grant: LocalAuthorizationGrant | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(grant); return {k: p.get(k) for k in ("grant_id", "authorization_domain", "grant_scope", "grant_status", "metadata_only", "authorization_record_only", "live_authorization_granted", "fulfillment_granted", "effect_performed", "host_mutation_performed", "digest")}

def summarize_local_authorization_grant_revocation_receipt(receipt: LocalAuthorizationGrantRevocationReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(receipt); return {k: p.get(k) for k in ("receipt_id", "grant_id", "revocation_status", "metadata_only", "revocation_record_only", "live_authorization_revoked", "does_not_execute", "does_not_mutate_host", "digest")}

def summarize_local_authorization_grant_expiry_evaluation(evaluation: LocalAuthorizationGrantExpiryEvaluation | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(evaluation); return {k: p.get(k) for k in ("evaluation_id", "grant_id", "expiry_status", "metadata_only", "expiry_evaluation_only", "does_not_execute", "does_not_mutate_host", "digest")}

def summarize_local_authorization_grant_verification(verification: LocalAuthorizationGrantVerification | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(verification); return {k: p.get(k) for k in ("verification_id", "grant_id", "verification_status", "metadata_only", "verification_only", "authorizes_fulfillment", "does_not_execute", "does_not_mutate_host", "digest")}

def summarize_local_authorization_grant_ledger(ledger: LocalAuthorizationGrantLedger | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(ledger); return {k: p.get(k) for k in ("ledger_id", "ledger_status", "active_grant_count", "revoked_grant_count", "expired_grant_count", "blocked_grant_count", "metadata_only", "authorization_ledger_only", "host_mutation_performed", "digest")}

def build_local_authorization_grant_wing(preflight_receipt: Any, prerequisite_matrix: Any, operator_approval_evidence: OperatorApprovalEvidence, policy_approval_evidence: PolicyApprovalEvidence, *, authorization_domain: str | None = None, grant_scope: str | None = None, created_at: str = "1970-01-01T00:00:00+00:00") -> LocalAuthorizationGrantWingRecords:
    grant = build_local_authorization_grant(preflight_receipt, prerequisite_matrix, operator_approval_evidence, policy_approval_evidence, authorization_domain=authorization_domain, grant_scope=grant_scope, created_at=created_at)
    expiry = build_local_authorization_grant_expiry_evaluation(grant, evaluated_at=created_at)
    verification = verify_local_authorization_grant(grant, checked_scope_labels=grant.granted_scope_labels, checked_time_label=created_at, expiry_evaluation=expiry)
    revocation = build_local_authorization_grant_revocation_receipt(grant, revocation_status="local_authorization_revocation_incomplete", revocation_reason_codes=("example_revocation_schema_not_exercised",), created_at=created_at)
    ledger = build_local_authorization_grant_ledger((grant,), (), (expiry,), created_at=created_at)
    return LocalAuthorizationGrantWingRecords(grant, expiry, verification, revocation, ledger)
