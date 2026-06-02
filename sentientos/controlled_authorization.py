"""Controlled authorization grant contracts for host embodiment.

This wing is contract-only, ledger-only, and trace-safe. It defines the shape of
future controlled authorization grants without creating live authority. It never
executes host actions, mutates host state, writes fan/PWM controls, changes
thermal or power settings, kills processes, restarts services, installs packages
or drivers, deletes files, performs cleanup, opens network egress, invokes
providers, assembles prompts, transports federation state, or performs remote
execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, NamedTuple, Sequence

from sentientos.authorization_review import AuthorizationReviewReceipt, FutureAuthorizationGrantSchema

CONTROLLED_AUTHORIZATION_CONTRACT_STATUSES = frozenset({
    "controlled_authorization_contract_ready",
    "controlled_authorization_contract_ready_with_conditions",
    "controlled_authorization_contract_blocked",
    "controlled_authorization_contract_incomplete",
    "controlled_authorization_contract_contradicted",
})
CONTROLLED_AUTHORIZATION_GRANT_STATUSES = frozenset({
    "controlled_authorization_grant_schema_recorded",
    "controlled_authorization_grant_schema_recorded_with_warnings",
    "controlled_authorization_grant_blocked",
    "controlled_authorization_grant_incomplete",
    "controlled_authorization_grant_contradicted",
    "controlled_authorization_grant_revoked",
    "controlled_authorization_grant_expired",
})
CONTROLLED_AUTHORIZATION_REVOCATION_STATUSES = frozenset({
    "controlled_authorization_revocation_recorded",
    "controlled_authorization_revocation_blocked",
    "controlled_authorization_revocation_incomplete",
    "controlled_authorization_revocation_contradicted",
})
CONTROLLED_AUTHORIZATION_LEDGER_STATUSES = frozenset({
    "controlled_authorization_ledger_current",
    "controlled_authorization_ledger_current_with_warnings",
    "controlled_authorization_ledger_blocked",
    "controlled_authorization_ledger_incomplete",
    "controlled_authorization_ledger_contradicted",
})
AUTHORIZATION_SCOPES = frozenset({
    "diagnostics_only_scope",
    "operator_review_scope",
    "resource_pressure_review_scope",
    "thermal_safety_review_scope",
    "disk_safety_review_scope",
    "service_health_review_scope",
    "future_cooling_scope",
    "future_power_scope",
    "future_cleanup_scope",
    "future_service_scope",
})
REQUIRED_GRANT_GATES = frozenset({
    "source_authorization_review_receipt_required",
    "future_authorization_grant_schema_required",
    "operator_identity_required",
    "policy_identity_required",
    "explicit_scope_required",
    "time_bounds_required",
    "expiry_required",
    "revocation_path_required",
    "control_plane_admission_required",
    "audit_receipt_required",
    "rollback_plan_required",
    "rollback_receipt_required",
    "effect_receipt_required",
    "postcondition_check_required",
    "runtime_supervisor_observation_required",
    "immutable_trace_required",
    "panic_stop_required",
})
BLOCKED_ACTION_LABELS = frozenset({
    "live_authorization_grant",
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

_DOMAIN_SCOPE: Mapping[str, str] = {
    "diagnostics_authorization_review": "diagnostics_only_scope",
    "operator_review_authorization_review": "operator_review_scope",
    "resource_pressure_authorization_review": "resource_pressure_review_scope",
    "thermal_safety_authorization_review": "thermal_safety_review_scope",
    "disk_safety_authorization_review": "disk_safety_review_scope",
    "service_health_authorization_review": "service_health_review_scope",
    "future_cooling_authorization_review": "future_cooling_scope",
    "future_power_authorization_review": "future_power_scope",
    "future_cleanup_authorization_review": "future_cleanup_scope",
    "future_service_authorization_review": "future_service_scope",
}
_SCOPE_BLOCKS: Mapping[str, tuple[str, ...]] = {
    "future_cooling_scope": ("fan_pwm_write", "thermal_actuation"),
    "future_power_scope": ("power_profile_mutation",),
    "future_cleanup_scope": ("file_cleanup", "file_delete"),
    "future_service_scope": ("service_restart", "process_kill"),
    "service_health_review_scope": ("service_restart", "process_kill"),
}
_REQUIRED_SCOPE_GATES: Mapping[str, tuple[str, ...]] = {
    "future_cooling_scope": tuple(sorted(REQUIRED_GRANT_GATES)),
    "future_power_scope": tuple(sorted(REQUIRED_GRANT_GATES)),
    "future_cleanup_scope": tuple(sorted(REQUIRED_GRANT_GATES)),
    "future_service_scope": tuple(sorted(REQUIRED_GRANT_GATES)),
}

@dataclass(frozen=True)
class ControlledAuthorizationPolicy:
    policy_id: str
    required_grant_gates: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    domain_scopes: Mapping[str, str]
    metadata_only: bool = True
    contract_only: bool = True
    live_authorization_granted: bool = False

@dataclass(frozen=True)
class ControlledAuthorizationGrantContract:
    contract_id: str
    source_authorization_review_receipt_id: str
    source_authorization_review_receipt_digest: str
    future_authorization_grant_schema_id: str
    authorization_domain: str
    approval_class: str
    authorization_scope: str
    required_grant_gates: tuple[str, ...]
    required_operator_identity_labels: tuple[str, ...]
    required_policy_labels: tuple[str, ...]
    required_scope_labels: tuple[str, ...]
    required_time_bound_labels: tuple[str, ...]
    required_expiry_labels: tuple[str, ...]
    required_revocation_labels: tuple[str, ...]
    required_audit_labels: tuple[str, ...]
    required_control_plane_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    contract_only: bool = True
    live_authorization_granted: bool = False
    fulfillment_granted: bool = False
    effect_performed: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class ControlledAuthorizationGrantRecord:
    grant_record_id: str
    contract_id: str
    source_authorization_review_receipt_id: str
    source_authorization_review_receipt_digest: str
    authorization_domain: str
    approval_class: str
    authorization_scope: str
    grant_status: str
    grant_subject_labels: tuple[str, ...]
    grant_scope_labels: tuple[str, ...]
    grant_time_bounds: tuple[str, ...]
    grant_expiry_label: str
    revocation_path_labels: tuple[str, ...]
    required_future_gates: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    schema_only: bool = True
    future_use_only: bool = True
    live_authorization_granted: bool = False
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    does_not_authorize_fulfillment: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class ControlledAuthorizationRevocationRecord:
    revocation_id: str
    grant_record_id: str
    contract_id: str
    source_authorization_review_receipt_id: str
    revocation_status: str
    revocation_reason_codes: tuple[str, ...]
    revocation_effective_label: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    schema_only: bool = True
    future_use_only: bool = True
    live_revocation_performed: bool = False
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class ControlledAuthorizationLedger:
    ledger_id: str
    grant_records: tuple[ControlledAuthorizationGrantRecord, ...]
    revocation_records: tuple[ControlledAuthorizationRevocationRecord, ...]
    ledger_status: str
    active_schema_grant_count: int
    revoked_schema_grant_count: int
    expired_schema_grant_count: int
    blocked_schema_grant_count: int
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    ledger_only: bool = True
    live_authorization_granted: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class ControlledAuthorizationValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()

class ControlledAuthorizationWingRecords(NamedTuple):
    contract: ControlledAuthorizationGrantContract
    grant_record: ControlledAuthorizationGrantRecord
    revocation_record: ControlledAuthorizationRevocationRecord
    ledger: ControlledAuthorizationLedger


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest_payload(prefix: str, payload: Mapping[str, Any], length: int = 24) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:length]


def _record_digest(record: Any) -> str:
    payload = record.to_dict()
    if "digest" in payload:
        payload["digest"] = ""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def controlled_authorization_grant_contract_digest(contract: ControlledAuthorizationGrantContract) -> str: return _record_digest(contract)
def controlled_authorization_grant_record_digest(record: ControlledAuthorizationGrantRecord) -> str: return _record_digest(record)
def controlled_authorization_revocation_record_digest(record: ControlledAuthorizationRevocationRecord) -> str: return _record_digest(record)
def controlled_authorization_ledger_digest(ledger: ControlledAuthorizationLedger) -> str: return _record_digest(ledger)


def build_default_controlled_authorization_policy() -> ControlledAuthorizationPolicy:
    return ControlledAuthorizationPolicy(
        policy_id="sentientos-host-embodiment-controlled-authorization.v1",
        required_grant_gates=tuple(sorted(REQUIRED_GRANT_GATES)),
        blocked_actions=tuple(sorted(BLOCKED_ACTION_LABELS)),
        domain_scopes=dict(_DOMAIN_SCOPE),
    )


def _scope_for(receipt: AuthorizationReviewReceipt) -> str:
    return _DOMAIN_SCOPE.get(receipt.authorization_domain, "diagnostics_only_scope")


def _status_from_review(receipt_status: str, schema_status: str) -> tuple[str, str]:
    joined = f"{receipt_status} {schema_status}"
    if "contradicted" in joined:
        return "controlled_authorization_contract_contradicted", "controlled_authorization_grant_contradicted"
    if "incomplete" in joined:
        return "controlled_authorization_contract_incomplete", "controlled_authorization_grant_incomplete"
    if "blocked" in joined:
        return "controlled_authorization_contract_blocked", "controlled_authorization_grant_blocked"
    if "warning" in joined or "conditions" in joined:
        return "controlled_authorization_contract_ready_with_conditions", "controlled_authorization_grant_schema_recorded_with_warnings"
    return "controlled_authorization_contract_ready", "controlled_authorization_grant_schema_recorded"


def _blocked_for(scope: str, source_blocked: Sequence[str]) -> tuple[str, ...]:
    labels = set(BLOCKED_ACTION_LABELS)
    labels.update(_SCOPE_BLOCKS.get(scope, ()))
    labels.update(str(item) for item in source_blocked if str(item) in BLOCKED_ACTION_LABELS)
    return tuple(sorted(labels))


def build_controlled_authorization_grant_contract(
    receipt: AuthorizationReviewReceipt,
    future_schema: FutureAuthorizationGrantSchema,
    *,
    policy: ControlledAuthorizationPolicy | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> ControlledAuthorizationGrantContract:
    policy = policy or build_default_controlled_authorization_policy()
    scope = _scope_for(receipt)
    contract_status, _ = _status_from_review(receipt.receipt_status, future_schema.schema_status)
    missing: list[str] = []
    if future_schema.source_authorization_review_receipt_id != receipt.receipt_id:
        missing.append("future_schema_receipt_id_mismatch")
    if future_schema.source_authorization_review_receipt_digest != receipt.digest:
        missing.append("future_schema_receipt_digest_mismatch")
    if not receipt.authorization_not_granted:
        missing.append("source_review_must_not_grant_authorization")
    required_gates = tuple(sorted(set(policy.required_grant_gates) | set(_REQUIRED_SCOPE_GATES.get(scope, ())) | {"source_authorization_review_receipt_required", "future_authorization_grant_schema_required"}))
    provisional = ControlledAuthorizationGrantContract(
        contract_id=_digest_payload("cagc_", {"receipt": receipt.receipt_id, "schema": future_schema.schema_id, "scope": scope, "created_at": created_at}),
        source_authorization_review_receipt_id=receipt.receipt_id,
        source_authorization_review_receipt_digest=receipt.digest,
        future_authorization_grant_schema_id=future_schema.schema_id,
        authorization_domain=receipt.authorization_domain,
        approval_class=receipt.approval_class,
        authorization_scope=scope,
        required_grant_gates=required_gates,
        required_operator_identity_labels=tuple(sorted(set(future_schema.required_operator_identity_labels) | {"operator_identity_required"})),
        required_policy_labels=tuple(sorted(set(future_schema.required_policy_labels) | {"policy_identity_required"})),
        required_scope_labels=tuple(sorted(set(future_schema.required_scope_labels) | {"explicit_scope_required", scope})),
        required_time_bound_labels=tuple(sorted(set(future_schema.required_time_bounds) | {"time_bounds_required"})),
        required_expiry_labels=("expiry_required", "expires_at_required", "short_lived_authorization_required"),
        required_revocation_labels=tuple(sorted(set(future_schema.required_revocation_labels) | {"revocation_path_required"})),
        required_audit_labels=tuple(sorted(set(future_schema.required_audit_labels) | {"audit_receipt_required", "immutable_trace_required"})),
        required_control_plane_labels=tuple(sorted(set(future_schema.required_control_plane_labels) | {"control_plane_admission_required"})),
        blocked_actions=_blocked_for(scope, tuple(receipt.blocked_actions) + tuple(future_schema.blocked_actions)),
        missing_prerequisites=tuple(sorted(set(missing))),
        status="controlled_authorization_contract_incomplete" if missing and contract_status == "controlled_authorization_contract_ready" else contract_status,
        warning_codes=tuple(sorted(set(receipt.warning_codes) | set(future_schema.warning_codes))),
        risk_codes=tuple(sorted(set(receipt.risk_codes) | set(future_schema.risk_codes) | {"controlled_authorization_contract_is_not_live_grant"})),
        created_at=created_at,
        digest="",
    )
    return replace(provisional, digest=controlled_authorization_grant_contract_digest(provisional))


def build_controlled_authorization_grant_record(
    contract: ControlledAuthorizationGrantContract,
    *,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> ControlledAuthorizationGrantRecord:
    status_map = {
        "controlled_authorization_contract_ready": "controlled_authorization_grant_schema_recorded",
        "controlled_authorization_contract_ready_with_conditions": "controlled_authorization_grant_schema_recorded_with_warnings",
        "controlled_authorization_contract_blocked": "controlled_authorization_grant_blocked",
        "controlled_authorization_contract_incomplete": "controlled_authorization_grant_incomplete",
        "controlled_authorization_contract_contradicted": "controlled_authorization_grant_contradicted",
    }
    provisional = ControlledAuthorizationGrantRecord(
        grant_record_id=_digest_payload("cagr_", {"contract": contract.contract_id, "digest": contract.digest, "created_at": created_at}),
        contract_id=contract.contract_id,
        source_authorization_review_receipt_id=contract.source_authorization_review_receipt_id,
        source_authorization_review_receipt_digest=contract.source_authorization_review_receipt_digest,
        authorization_domain=contract.authorization_domain,
        approval_class=contract.approval_class,
        authorization_scope=contract.authorization_scope,
        grant_status=status_map.get(contract.status, "controlled_authorization_grant_incomplete"),
        grant_subject_labels=contract.required_operator_identity_labels,
        grant_scope_labels=contract.required_scope_labels,
        grant_time_bounds=contract.required_time_bound_labels,
        grant_expiry_label="expiry_required",
        revocation_path_labels=contract.required_revocation_labels,
        required_future_gates=contract.required_grant_gates,
        blocked_actions=contract.blocked_actions,
        warning_codes=contract.warning_codes,
        risk_codes=tuple(sorted(set(contract.risk_codes) | {"grant_record_schema_only_future_use_only"})),
        created_at=created_at,
        digest="",
    )
    return replace(provisional, digest=controlled_authorization_grant_record_digest(provisional))


def build_controlled_authorization_revocation_record(
    grant_record: ControlledAuthorizationGrantRecord,
    *,
    reason_codes: Sequence[str] = ("schema_revocation_path_documented",),
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> ControlledAuthorizationRevocationRecord:
    if grant_record.grant_status.endswith("contradicted"):
        status = "controlled_authorization_revocation_contradicted"
    elif grant_record.grant_status.endswith("incomplete"):
        status = "controlled_authorization_revocation_incomplete"
    elif grant_record.grant_status.endswith("blocked"):
        status = "controlled_authorization_revocation_blocked"
    else:
        status = "controlled_authorization_revocation_recorded"
    provisional = ControlledAuthorizationRevocationRecord(
        revocation_id=_digest_payload("carr_", {"grant": grant_record.grant_record_id, "created_at": created_at, "reasons": tuple(reason_codes)}),
        grant_record_id=grant_record.grant_record_id,
        contract_id=grant_record.contract_id,
        source_authorization_review_receipt_id=grant_record.source_authorization_review_receipt_id,
        revocation_status=status,
        revocation_reason_codes=tuple(str(code) for code in reason_codes),
        revocation_effective_label="future_schema_revocation_path_only_no_live_revocation",
        warning_codes=grant_record.warning_codes,
        risk_codes=tuple(sorted(set(grant_record.risk_codes) | {"revocation_record_schema_only_future_use_only"})),
        created_at=created_at,
        digest="",
    )
    return replace(provisional, digest=controlled_authorization_revocation_record_digest(provisional))


def build_controlled_authorization_ledger(
    grant_records: Sequence[ControlledAuthorizationGrantRecord],
    revocation_records: Sequence[ControlledAuthorizationRevocationRecord] = (),
    *,
    ledger_id: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> ControlledAuthorizationLedger:
    grants = tuple(grant_records)
    revocations = tuple(revocation_records)
    grant_statuses = {record.grant_status for record in grants}
    revocation_statuses = {record.revocation_status for record in revocations}
    if any("contradicted" in status for status in grant_statuses | revocation_statuses):
        ledger_status = "controlled_authorization_ledger_contradicted"
    elif any("incomplete" in status for status in grant_statuses | revocation_statuses):
        ledger_status = "controlled_authorization_ledger_incomplete"
    elif any("blocked" in status for status in grant_statuses | revocation_statuses):
        ledger_status = "controlled_authorization_ledger_blocked"
    elif any(record.warning_codes for record in grants) or any(record.warning_codes for record in revocations):
        ledger_status = "controlled_authorization_ledger_current_with_warnings"
    else:
        ledger_status = "controlled_authorization_ledger_current"
    revoked_ids = {record.grant_record_id for record in revocations if record.revocation_status == "controlled_authorization_revocation_recorded"}
    active = sum(1 for record in grants if record.grant_status.startswith("controlled_authorization_grant_schema_recorded") and record.grant_record_id not in revoked_ids)
    provisional = ControlledAuthorizationLedger(
        ledger_id=ledger_id or _digest_payload("cal_", {"grants": [g.grant_record_id for g in grants], "revocations": [r.revocation_id for r in revocations], "created_at": created_at}),
        grant_records=grants,
        revocation_records=revocations,
        ledger_status=ledger_status,
        active_schema_grant_count=active,
        revoked_schema_grant_count=len(revoked_ids),
        expired_schema_grant_count=sum(1 for record in grants if record.grant_status == "controlled_authorization_grant_expired"),
        blocked_schema_grant_count=sum(1 for record in grants if record.grant_status == "controlled_authorization_grant_blocked"),
        warning_codes=tuple(sorted({warning for record in grants for warning in record.warning_codes} | {warning for record in revocations for warning in record.warning_codes})),
        risk_codes=tuple(sorted({risk for record in grants for risk in record.risk_codes} | {risk for record in revocations for risk in record.risk_codes} | {"ledger_does_not_grant_live_authority"})),
        created_at=created_at,
        digest="",
    )
    return replace(provisional, digest=controlled_authorization_ledger_digest(provisional))


def _validate_non_authority(value: Any, prefix: str) -> list[str]:
    findings: list[str] = []
    for flag in ("live_authorization_granted", "fulfillment_granted", "effect_performed", "host_mutation_performed", "live_revocation_performed"):
        if getattr(value, flag, False):
            findings.append(f"{prefix}_forbidden_flag:{flag}")
    for flag in ("metadata_only", "contract_only", "schema_only", "future_use_only", "ledger_only", "does_not_execute", "does_not_mutate_host", "does_not_authorize_fulfillment"):
        if hasattr(value, flag) and not getattr(value, flag):
            findings.append(f"{prefix}_missing_non_authority_flag:{flag}")
    blocked = set(getattr(value, "blocked_actions", ()) or ())
    forbidden_core = {"live_authorization_grant", "host_mutation", "provider_invocation", "network_egress", "prompt_assembly"}
    if hasattr(value, "blocked_actions") and not forbidden_core.issubset(blocked):
        findings.append(f"{prefix}_missing_core_blocked_actions")
    return findings


def validate_controlled_authorization_grant_contract(contract: ControlledAuthorizationGrantContract) -> ControlledAuthorizationValidationResult:
    findings = _validate_non_authority(contract, "contract")
    if contract.status not in CONTROLLED_AUTHORIZATION_CONTRACT_STATUSES: findings.append("unknown_contract_status")
    if contract.authorization_scope not in AUTHORIZATION_SCOPES: findings.append("unknown_authorization_scope")
    if contract.digest and contract.digest != controlled_authorization_grant_contract_digest(contract): findings.append("contract_digest_mismatch")
    required = set(_SCOPE_BLOCKS.get(contract.authorization_scope, ()))
    if not required.issubset(set(contract.blocked_actions)): findings.append("contract_missing_scope_blocked_actions")
    return ControlledAuthorizationValidationResult(not findings, tuple(findings))


def validate_controlled_authorization_grant_record(record: ControlledAuthorizationGrantRecord) -> ControlledAuthorizationValidationResult:
    findings = _validate_non_authority(record, "grant_record")
    if record.grant_status not in CONTROLLED_AUTHORIZATION_GRANT_STATUSES: findings.append("unknown_grant_status")
    if not record.schema_only or not record.future_use_only: findings.append("grant_record_not_schema_only_future_use")
    if record.digest and record.digest != controlled_authorization_grant_record_digest(record): findings.append("grant_record_digest_mismatch")
    if set(_SCOPE_BLOCKS.get(record.authorization_scope, ())) - set(record.blocked_actions): findings.append("grant_record_missing_scope_blocked_actions")
    return ControlledAuthorizationValidationResult(not findings, tuple(findings))


def validate_controlled_authorization_revocation_record(record: ControlledAuthorizationRevocationRecord) -> ControlledAuthorizationValidationResult:
    findings = _validate_non_authority(record, "revocation_record")
    if record.revocation_status not in CONTROLLED_AUTHORIZATION_REVOCATION_STATUSES: findings.append("unknown_revocation_status")
    if not record.schema_only or not record.future_use_only: findings.append("revocation_record_not_schema_only_future_use")
    if record.live_revocation_performed: findings.append("revocation_record_claims_live_revocation")
    if record.digest and record.digest != controlled_authorization_revocation_record_digest(record): findings.append("revocation_record_digest_mismatch")
    return ControlledAuthorizationValidationResult(not findings, tuple(findings))


def validate_controlled_authorization_ledger(ledger: ControlledAuthorizationLedger) -> ControlledAuthorizationValidationResult:
    findings = _validate_non_authority(ledger, "ledger")
    if ledger.ledger_status not in CONTROLLED_AUTHORIZATION_LEDGER_STATUSES: findings.append("unknown_ledger_status")
    if not ledger.metadata_only or not ledger.ledger_only: findings.append("ledger_not_metadata_only")
    if ledger.live_authorization_granted: findings.append("ledger_claims_live_authorization")
    if ledger.host_mutation_performed: findings.append("ledger_claims_host_mutation")
    if ledger.digest and ledger.digest != controlled_authorization_ledger_digest(ledger): findings.append("ledger_digest_mismatch")
    for grant_record in ledger.grant_records:
        if not validate_controlled_authorization_grant_record(grant_record).ok: findings.append(f"ledger_invalid_grant_record:{grant_record.grant_record_id}")
    for revocation_record in ledger.revocation_records:
        if not validate_controlled_authorization_revocation_record(revocation_record).ok: findings.append(f"ledger_invalid_revocation_record:{revocation_record.revocation_id}")
    return ControlledAuthorizationValidationResult(not findings, tuple(findings))


def summarize_controlled_authorization_grant_contract(contract: ControlledAuthorizationGrantContract) -> dict[str, Any]:
    return {"contract_id": contract.contract_id, "source_authorization_review_receipt_id": contract.source_authorization_review_receipt_id, "future_authorization_grant_schema_id": contract.future_authorization_grant_schema_id, "authorization_domain": contract.authorization_domain, "authorization_scope": contract.authorization_scope, "status": contract.status, "metadata_only": contract.metadata_only, "contract_only": contract.contract_only, "live_authorization_granted": contract.live_authorization_granted, "fulfillment_granted": contract.fulfillment_granted, "effect_performed": contract.effect_performed, "host_mutation_performed": contract.host_mutation_performed, "blocked_action_count": len(contract.blocked_actions), "digest": contract.digest}


def summarize_controlled_authorization_grant_record(record: ControlledAuthorizationGrantRecord) -> dict[str, Any]:
    return {"grant_record_id": record.grant_record_id, "contract_id": record.contract_id, "authorization_scope": record.authorization_scope, "grant_status": record.grant_status, "schema_only": record.schema_only, "future_use_only": record.future_use_only, "live_authorization_granted": record.live_authorization_granted, "does_not_execute": record.does_not_execute, "does_not_mutate_host": record.does_not_mutate_host, "does_not_authorize_fulfillment": record.does_not_authorize_fulfillment, "digest": record.digest}


def summarize_controlled_authorization_revocation_record(record: ControlledAuthorizationRevocationRecord) -> dict[str, Any]:
    return {"revocation_id": record.revocation_id, "grant_record_id": record.grant_record_id, "revocation_status": record.revocation_status, "schema_only": record.schema_only, "future_use_only": record.future_use_only, "live_revocation_performed": record.live_revocation_performed, "does_not_execute": record.does_not_execute, "does_not_mutate_host": record.does_not_mutate_host, "digest": record.digest}


def summarize_controlled_authorization_ledger(ledger: ControlledAuthorizationLedger) -> dict[str, Any]:
    return {"ledger_id": ledger.ledger_id, "ledger_status": ledger.ledger_status, "active_schema_grant_count": ledger.active_schema_grant_count, "revoked_schema_grant_count": ledger.revoked_schema_grant_count, "expired_schema_grant_count": ledger.expired_schema_grant_count, "blocked_schema_grant_count": ledger.blocked_schema_grant_count, "metadata_only": ledger.metadata_only, "ledger_only": ledger.ledger_only, "live_authorization_granted": ledger.live_authorization_granted, "host_mutation_performed": ledger.host_mutation_performed, "digest": ledger.digest}


def build_controlled_authorization_wing_for_review_receipt(
    receipt: AuthorizationReviewReceipt,
    future_schema: FutureAuthorizationGrantSchema,
    *,
    policy: ControlledAuthorizationPolicy | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> ControlledAuthorizationWingRecords:
    contract = build_controlled_authorization_grant_contract(receipt, future_schema, policy=policy, created_at=created_at)
    grant_record = build_controlled_authorization_grant_record(contract, created_at=created_at)
    revocation_record = build_controlled_authorization_revocation_record(grant_record, created_at=created_at)
    ledger = build_controlled_authorization_ledger((grant_record,), (revocation_record,), created_at=created_at)
    return ControlledAuthorizationWingRecords(contract, grant_record, revocation_record, ledger)
