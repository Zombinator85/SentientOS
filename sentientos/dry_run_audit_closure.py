"""Metadata-only dry-run verification and audit closure records.

This wing verifies dry-run execution receipts without converting them into real
fulfillment, real effect receipts, real postcondition checks, real rollback, or
production audit receipts. It does not mutate host state, write fan/PWM controls,
change thermal or power settings, kill processes, restart services, install
packages or drivers, delete or clean files, perform network calls, invoke
providers, assemble prompts, spawn subprocess execution, run shell execution,
invoke OS backends, or call control-plane admission/execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, NamedTuple, Sequence

from sentientos.dry_run_execution_harness import DryRunExecutionReceipt

VERIFICATION_STATUSES = frozenset({
    "dry_run_verification_recorded",
    "dry_run_verification_recorded_with_warnings",
    "dry_run_verification_blocked",
    "dry_run_verification_incomplete",
    "dry_run_verification_contradicted",
})
POSTCONDITION_STATUSES = frozenset({
    "dry_run_postcondition_verified",
    "dry_run_postcondition_verified_with_warnings",
    "dry_run_postcondition_blocked",
    "dry_run_postcondition_incomplete",
    "dry_run_postcondition_contradicted",
})
ROLLBACK_STATUSES = frozenset({
    "dry_run_rollback_rehearsed",
    "dry_run_rollback_rehearsed_with_warnings",
    "dry_run_rollback_blocked",
    "dry_run_rollback_incomplete",
    "dry_run_rollback_contradicted",
})
AUDIT_CLOSURE_STATUSES = frozenset({
    "dry_run_audit_closure_recorded",
    "dry_run_audit_closure_recorded_with_warnings",
    "dry_run_audit_closure_blocked",
    "dry_run_audit_closure_incomplete",
    "dry_run_audit_closure_contradicted",
})
BUNDLE_STATUSES = frozenset({
    "dry_run_closure_bundle_ready",
    "dry_run_closure_bundle_ready_with_warnings",
    "dry_run_closure_bundle_blocked",
    "dry_run_closure_bundle_incomplete",
    "dry_run_closure_bundle_contradicted",
})
CLOSURE_DOMAINS = frozenset({
    "diagnostics_dry_run_closure",
    "operator_review_dry_run_closure",
    "resource_pressure_dry_run_closure",
    "thermal_safety_dry_run_closure",
    "future_cooling_dry_run_closure",
    "future_power_dry_run_closure",
    "future_cleanup_dry_run_closure",
    "future_service_dry_run_closure",
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
    "subprocess_execution",
    "shell_execution",
    "os_backend_invocation",
    "control_plane_admission_execution",
    "real_effect_receipt",
    "real_postcondition_check",
    "real_rollback_execution",
    "production_audit_receipt",
})
_DOMAIN_BLOCKS = {
    "future_cooling_dry_run_closure": ("fan_pwm_write", "thermal_actuation"),
    "future_power_dry_run_closure": ("power_profile_mutation",),
    "future_cleanup_dry_run_closure": ("file_cleanup", "file_delete"),
    "future_service_dry_run_closure": ("service_restart", "process_kill"),
}
_FORBIDDEN_TRUE_FLAGS = (
    "real_effect_receipt_created",
    "real_postcondition_check_performed",
    "real_rollback_performed",
    "production_audit_receipt_created",
    "real_fulfillment_performed",
    "real_effect_performed",
    "real_backend_invoked",
    "host_mutation_performed",
    "fan_pwm_write_performed",
    "thermal_actuation_performed",
    "power_profile_mutation_performed",
    "process_kill_performed",
    "service_restart_performed",
    "package_install_performed",
    "driver_install_performed",
    "file_cleanup_performed",
    "file_delete_performed",
    "provider_invocation_performed",
    "network_performed",
    "prompt_assembly_performed",
    "subprocess_execution_performed",
    "shell_execution_performed",
    "os_backend_invoked",
    "control_plane_admission_execution_performed",
)


@dataclass(frozen=True)
class DryRunAuditClosurePolicy:
    policy_id: str
    supported_closure_domains: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    metadata_only: bool = True
    dry_run_audit_closure_only: bool = True
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DryRunEffectVerification:
    verification_id: str
    source_dry_run_receipt_id: str
    source_dry_run_receipt_digest: str
    dry_run_domain: str
    simulated_backend_class: str
    verification_status: str
    simulated_effect_labels: tuple[str, ...]
    verified_no_effect_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    dry_run_verification_only: bool = True
    real_effect_receipt_created: bool = False
    real_effect_performed: bool = False
    real_backend_invoked: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DryRunPostconditionVerification:
    verification_id: str
    source_dry_run_receipt_id: str
    source_effect_verification_id: str
    dry_run_domain: str
    postcondition_status: str
    expected_simulated_postcondition_labels: tuple[str, ...]
    observed_simulated_postcondition_labels: tuple[str, ...]
    missing_simulated_postcondition_labels: tuple[str, ...]
    contradicted_simulated_postcondition_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    dry_run_postcondition_only: bool = True
    real_postcondition_check_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DryRunRollbackRehearsal:
    rehearsal_id: str
    source_dry_run_receipt_id: str
    source_effect_verification_id: str
    dry_run_domain: str
    rollback_status: str
    simulated_rollback_labels: tuple[str, ...]
    rollback_precondition_labels: tuple[str, ...]
    rollback_postcondition_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    dry_run_rollback_only: bool = True
    real_rollback_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DryRunAuditClosureReceipt:
    receipt_id: str
    source_dry_run_receipt_id: str
    source_effect_verification_id: str
    source_postcondition_verification_id: str
    source_rollback_rehearsal_id: str
    dry_run_domain: str
    audit_closure_status: str
    evidence_summary: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    dry_run_audit_only: bool = True
    production_audit_receipt_created: bool = False
    real_effect_receipt_created: bool = False
    real_postcondition_check_performed: bool = False
    real_rollback_performed: bool = False
    real_fulfillment_performed: bool = False
    real_effect_performed: bool = False
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
class DryRunClosureBundle:
    bundle_id: str
    source_dry_run_receipt_id: str
    effect_verification_id: str
    postcondition_verification_id: str
    rollback_rehearsal_id: str
    audit_closure_receipt_id: str
    closure_domain: str
    bundle_status: str
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    dry_run_closure_only: bool = True
    real_fulfillment_performed: bool = False
    real_effect_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DryRunAuditClosureValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


class DryRunAuditClosureWingRecords(NamedTuple):
    effect_verification: DryRunEffectVerification
    postcondition_verification: DryRunPostconditionVerification
    rollback_rehearsal: DryRunRollbackRehearsal
    audit_closure_receipt: DryRunAuditClosureReceipt
    closure_bundle: DryRunClosureBundle


def _tuple(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


def _source_payload(source: Any) -> Mapping[str, Any]:
    return source.to_dict() if hasattr(source, "to_dict") else dict(source)


def _payload(record_or_payload: Any) -> dict[str, Any]:
    payload = dict(_source_payload(record_or_payload))
    payload["digest"] = ""
    return payload


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def dry_run_audit_closure_digest(record_or_payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(_payload(record_or_payload)).encode("utf-8")).hexdigest()


dry_run_effect_verification_digest = dry_run_audit_closure_digest
dry_run_postcondition_verification_digest = dry_run_audit_closure_digest
dry_run_rollback_rehearsal_digest = dry_run_audit_closure_digest
dry_run_audit_closure_receipt_digest = dry_run_audit_closure_digest
dry_run_closure_bundle_digest = dry_run_audit_closure_digest


def _digest_id(prefix: str, payload: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:24]


def _closure_domain(dry_run_domain: str) -> str:
    candidate = dry_run_domain.replace("_dry_run", "_dry_run_closure")
    return candidate if candidate in CLOSURE_DOMAINS else "operator_review_dry_run_closure"


def _blocked_actions(closure_domain: str, extra: Sequence[str] | None = None) -> tuple[str, ...]:
    return tuple(sorted(set(BLOCKED_ACTION_LABELS) | set(_DOMAIN_BLOCKS.get(closure_domain, ())) | set(_tuple(extra))))


def _receipt_status(receipt: Mapping[str, Any]) -> str:
    status = str(receipt.get("receipt_status", ""))
    if any(receipt.get(flag, False) for flag in _FORBIDDEN_TRUE_FLAGS if flag in receipt):
        return "contradicted"
    if receipt.get("dry_run_executed") is not True:
        return "incomplete"
    if status == "dry_run_execution_receipt_recorded":
        return "recorded"
    if status == "dry_run_execution_receipt_recorded_with_warnings":
        return "recorded_with_warnings"
    if status == "dry_run_execution_receipt_blocked":
        return "blocked"
    if status == "dry_run_execution_receipt_contradicted":
        return "contradicted"
    return "incomplete"


def _status(kind: str, base: str) -> str:
    table = {
        "effect": {
            "recorded": "dry_run_verification_recorded",
            "recorded_with_warnings": "dry_run_verification_recorded_with_warnings",
            "blocked": "dry_run_verification_blocked",
            "incomplete": "dry_run_verification_incomplete",
            "contradicted": "dry_run_verification_contradicted",
        },
        "postcondition": {
            "recorded": "dry_run_postcondition_verified",
            "recorded_with_warnings": "dry_run_postcondition_verified_with_warnings",
            "blocked": "dry_run_postcondition_blocked",
            "incomplete": "dry_run_postcondition_incomplete",
            "contradicted": "dry_run_postcondition_contradicted",
        },
        "rollback": {
            "recorded": "dry_run_rollback_rehearsed",
            "recorded_with_warnings": "dry_run_rollback_rehearsed_with_warnings",
            "blocked": "dry_run_rollback_blocked",
            "incomplete": "dry_run_rollback_incomplete",
            "contradicted": "dry_run_rollback_contradicted",
        },
        "audit": {
            "recorded": "dry_run_audit_closure_recorded",
            "recorded_with_warnings": "dry_run_audit_closure_recorded_with_warnings",
            "blocked": "dry_run_audit_closure_blocked",
            "incomplete": "dry_run_audit_closure_incomplete",
            "contradicted": "dry_run_audit_closure_contradicted",
        },
        "bundle": {
            "recorded": "dry_run_closure_bundle_ready",
            "recorded_with_warnings": "dry_run_closure_bundle_ready_with_warnings",
            "blocked": "dry_run_closure_bundle_blocked",
            "incomplete": "dry_run_closure_bundle_incomplete",
            "contradicted": "dry_run_closure_bundle_contradicted",
        },
    }
    return table[kind].get(base, table[kind]["incomplete"])


def build_default_dry_run_audit_closure_policy() -> DryRunAuditClosurePolicy:
    return DryRunAuditClosurePolicy(
        "dry-run-audit-closure-policy-v1",
        tuple(sorted(CLOSURE_DOMAINS)),
        tuple(sorted(BLOCKED_ACTION_LABELS)),
        (),
        ("dry_run_verification_not_real_effect", "real_audit_closure_deferred"),
    )


def build_dry_run_effect_verification(
    dry_run_receipt: DryRunExecutionReceipt | Mapping[str, Any],
    *,
    verification_id: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> DryRunEffectVerification:
    receipt = _source_payload(dry_run_receipt)
    base = _receipt_status(receipt)
    closure_domain = _closure_domain(str(receipt.get("dry_run_domain", "")))
    blocked = _blocked_actions(closure_domain, receipt.get("blocked_actions"))
    risks = tuple(sorted(set(_tuple(receipt.get("risk_codes"))) | {"dry_run_effect_verification_is_not_real_effect_receipt"}))
    provisional = DryRunEffectVerification(
        verification_id or _digest_id("dry-run-effect-verification-", {"receipt": receipt.get("receipt_id"), "status": base}),
        str(receipt.get("receipt_id", "")),
        str(receipt.get("digest", "")),
        closure_domain,
        str(receipt.get("simulated_backend_class", "")),
        _status("effect", base),
        _tuple(receipt.get("simulated_step_labels")) or ("simulated_dry_run_effect_metadata",),
        ("real_effect_receipt_created_false", "real_effect_performed_false", "host_mutation_performed_false"),
        blocked,
        _tuple(receipt.get("warning_codes")),
        risks,
        created_at,
        "",
    )
    return replace(provisional, digest=dry_run_effect_verification_digest(provisional))


def build_dry_run_postcondition_verification(
    dry_run_receipt: DryRunExecutionReceipt | Mapping[str, Any],
    effect_verification: DryRunEffectVerification | Mapping[str, Any],
    *,
    verification_id: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> DryRunPostconditionVerification:
    receipt = _source_payload(dry_run_receipt)
    effect = _source_payload(effect_verification)
    base = _receipt_status(receipt)
    expected = _tuple(receipt.get("simulated_postcondition_labels")) or ("dry_run_metadata_present",)
    observed = expected if base in {"recorded", "recorded_with_warnings"} else ()
    missing = tuple(label for label in expected if label not in observed)
    contradicted = ("real_postcondition_claim_present",) if base == "contradicted" else ()
    if missing and base in {"recorded", "recorded_with_warnings"}:
        base = "incomplete"
    risks = tuple(sorted(set(_tuple(receipt.get("risk_codes"))) | {"dry_run_postcondition_is_not_real_host_postcondition_check"}))
    provisional = DryRunPostconditionVerification(
        verification_id or _digest_id("dry-run-postcondition-verification-", {"receipt": receipt.get("receipt_id"), "effect": effect.get("verification_id"), "status": base}),
        str(receipt.get("receipt_id", "")),
        str(effect.get("verification_id", "")),
        str(effect.get("dry_run_domain", _closure_domain(str(receipt.get("dry_run_domain", ""))))),
        _status("postcondition", base),
        expected,
        observed,
        missing,
        contradicted,
        _blocked_actions(str(effect.get("dry_run_domain", "operator_review_dry_run_closure")), receipt.get("blocked_actions")),
        _tuple(receipt.get("warning_codes")),
        risks,
        created_at,
        "",
    )
    return replace(provisional, digest=dry_run_postcondition_verification_digest(provisional))


def build_dry_run_rollback_rehearsal(
    dry_run_receipt: DryRunExecutionReceipt | Mapping[str, Any],
    effect_verification: DryRunEffectVerification | Mapping[str, Any],
    *,
    rehearsal_id: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> DryRunRollbackRehearsal:
    receipt = _source_payload(dry_run_receipt)
    effect = _source_payload(effect_verification)
    base = _receipt_status(receipt)
    labels = _tuple(receipt.get("simulated_rollback_labels")) or ("rollback_not_required_no_real_effect",)
    risks = tuple(sorted(set(_tuple(receipt.get("risk_codes"))) | {"dry_run_rollback_rehearsal_is_not_real_rollback"}))
    provisional = DryRunRollbackRehearsal(
        rehearsal_id or _digest_id("dry-run-rollback-rehearsal-", {"receipt": receipt.get("receipt_id"), "effect": effect.get("verification_id"), "status": base}),
        str(receipt.get("receipt_id", "")),
        str(effect.get("verification_id", "")),
        str(effect.get("dry_run_domain", _closure_domain(str(receipt.get("dry_run_domain", ""))))),
        _status("rollback", base),
        labels,
        ("real_effect_performed_false", "real_rollback_not_required_for_dry_run", "future_real_rollback_deferred"),
        ("real_rollback_performed_false", "host_mutation_performed_false"),
        _blocked_actions(str(effect.get("dry_run_domain", "operator_review_dry_run_closure")), receipt.get("blocked_actions")),
        _tuple(receipt.get("warning_codes")),
        risks,
        created_at,
        "",
    )
    return replace(provisional, digest=dry_run_rollback_rehearsal_digest(provisional))


def build_dry_run_audit_closure_receipt(
    dry_run_receipt: DryRunExecutionReceipt | Mapping[str, Any],
    effect_verification: DryRunEffectVerification | Mapping[str, Any],
    postcondition_verification: DryRunPostconditionVerification | Mapping[str, Any],
    rollback_rehearsal: DryRunRollbackRehearsal | Mapping[str, Any],
    *,
    receipt_id: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> DryRunAuditClosureReceipt:
    receipt = _source_payload(dry_run_receipt)
    effect = _source_payload(effect_verification)
    post = _source_payload(postcondition_verification)
    rollback = _source_payload(rollback_rehearsal)
    base = _receipt_status(receipt)
    evidence = (
        "dry_run_effect_verification_recorded_without_real_effect_receipt",
        "dry_run_postcondition_verification_recorded_without_real_host_check",
        "dry_run_rollback_rehearsal_recorded_without_real_rollback",
        "dry_run_audit_closure_is_not_production_audit_receipt",
        "real_fulfillment_performed_false",
        "host_mutation_performed_false",
    )
    risks = tuple(sorted(set(_tuple(receipt.get("risk_codes"))) | {"dry_run_audit_closure_is_not_production_audit_receipt"}))
    provisional = DryRunAuditClosureReceipt(
        receipt_id or _digest_id("dry-run-audit-closure-receipt-", {"receipt": receipt.get("receipt_id"), "effect": effect.get("verification_id"), "status": base}),
        str(receipt.get("receipt_id", "")),
        str(effect.get("verification_id", "")),
        str(post.get("verification_id", "")),
        str(rollback.get("rehearsal_id", "")),
        str(effect.get("dry_run_domain", _closure_domain(str(receipt.get("dry_run_domain", ""))))),
        _status("audit", base),
        evidence,
        _blocked_actions(str(effect.get("dry_run_domain", "operator_review_dry_run_closure")), receipt.get("blocked_actions")),
        _tuple(receipt.get("warning_codes")),
        risks,
        created_at,
        "",
    )
    return replace(provisional, digest=dry_run_audit_closure_receipt_digest(provisional))


def build_dry_run_closure_bundle(
    dry_run_receipt: DryRunExecutionReceipt | Mapping[str, Any],
    effect_verification: DryRunEffectVerification | Mapping[str, Any],
    postcondition_verification: DryRunPostconditionVerification | Mapping[str, Any],
    rollback_rehearsal: DryRunRollbackRehearsal | Mapping[str, Any],
    audit_closure_receipt: DryRunAuditClosureReceipt | Mapping[str, Any],
    *,
    bundle_id: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> DryRunClosureBundle:
    receipt = _source_payload(dry_run_receipt)
    effect = _source_payload(effect_verification)
    post = _source_payload(postcondition_verification)
    rollback = _source_payload(rollback_rehearsal)
    audit = _source_payload(audit_closure_receipt)
    base = _receipt_status(receipt)
    risks = tuple(sorted(set(_tuple(receipt.get("risk_codes"))) | {"dry_run_closure_bundle_is_not_real_fulfillment"}))
    provisional = DryRunClosureBundle(
        bundle_id or _digest_id("dry-run-closure-bundle-", {"receipt": receipt.get("receipt_id"), "audit": audit.get("receipt_id"), "status": base}),
        str(receipt.get("receipt_id", "")),
        str(effect.get("verification_id", "")),
        str(post.get("verification_id", "")),
        str(rollback.get("rehearsal_id", "")),
        str(audit.get("receipt_id", "")),
        str(effect.get("dry_run_domain", _closure_domain(str(receipt.get("dry_run_domain", ""))))),
        _status("bundle", base),
        _blocked_actions(str(effect.get("dry_run_domain", "operator_review_dry_run_closure")), receipt.get("blocked_actions")),
        _tuple(receipt.get("warning_codes")),
        risks,
        created_at,
        "",
    )
    return replace(provisional, digest=dry_run_closure_bundle_digest(provisional))


def _validate_common(payload: Mapping[str, Any], *, prefix: str, status_field: str, statuses: frozenset[str], only_field: str, digest_fn: Any) -> list[str]:
    findings: list[str] = []
    if not payload.get("metadata_only", False):
        findings.append(prefix + "not_metadata_only")
    if not payload.get(only_field, False):
        findings.append(prefix + f"missing_{only_field}")
    if payload.get(status_field) not in statuses:
        findings.append(prefix + f"unknown_{status_field}")
    for flag in _FORBIDDEN_TRUE_FLAGS:
        if flag in payload and payload.get(flag, False):
            findings.append(prefix + f"forbidden_flag:{flag}")
    if payload.get("digest") and payload.get("digest") != digest_fn(payload):
        findings.append(prefix + "digest_mismatch")
    return findings


def validate_dry_run_effect_verification(record: DryRunEffectVerification | Mapping[str, Any]) -> DryRunAuditClosureValidationResult:
    p = _source_payload(record)
    f = _validate_common(p, prefix="effect_verification:", status_field="verification_status", statuses=VERIFICATION_STATUSES, only_field="dry_run_verification_only", digest_fn=dry_run_effect_verification_digest)
    if p.get("dry_run_domain") not in CLOSURE_DOMAINS:
        f.append("effect_verification:unknown_dry_run_domain")
    return DryRunAuditClosureValidationResult(not f, tuple(f))


def validate_dry_run_postcondition_verification(record: DryRunPostconditionVerification | Mapping[str, Any]) -> DryRunAuditClosureValidationResult:
    p = _source_payload(record)
    f = _validate_common(p, prefix="postcondition_verification:", status_field="postcondition_status", statuses=POSTCONDITION_STATUSES, only_field="dry_run_postcondition_only", digest_fn=dry_run_postcondition_verification_digest)
    if p.get("dry_run_domain") not in CLOSURE_DOMAINS:
        f.append("postcondition_verification:unknown_dry_run_domain")
    return DryRunAuditClosureValidationResult(not f, tuple(f))


def validate_dry_run_rollback_rehearsal(record: DryRunRollbackRehearsal | Mapping[str, Any]) -> DryRunAuditClosureValidationResult:
    p = _source_payload(record)
    f = _validate_common(p, prefix="rollback_rehearsal:", status_field="rollback_status", statuses=ROLLBACK_STATUSES, only_field="dry_run_rollback_only", digest_fn=dry_run_rollback_rehearsal_digest)
    if p.get("dry_run_domain") not in CLOSURE_DOMAINS:
        f.append("rollback_rehearsal:unknown_dry_run_domain")
    return DryRunAuditClosureValidationResult(not f, tuple(f))


def validate_dry_run_audit_closure_receipt(record: DryRunAuditClosureReceipt | Mapping[str, Any]) -> DryRunAuditClosureValidationResult:
    p = _source_payload(record)
    f = _validate_common(p, prefix="audit_closure:", status_field="audit_closure_status", statuses=AUDIT_CLOSURE_STATUSES, only_field="dry_run_audit_only", digest_fn=dry_run_audit_closure_receipt_digest)
    if p.get("dry_run_domain") not in CLOSURE_DOMAINS:
        f.append("audit_closure:unknown_dry_run_domain")
    return DryRunAuditClosureValidationResult(not f, tuple(f))


def validate_dry_run_closure_bundle(record: DryRunClosureBundle | Mapping[str, Any]) -> DryRunAuditClosureValidationResult:
    p = _source_payload(record)
    f = _validate_common(p, prefix="closure_bundle:", status_field="bundle_status", statuses=BUNDLE_STATUSES, only_field="dry_run_closure_only", digest_fn=dry_run_closure_bundle_digest)
    if p.get("closure_domain") not in CLOSURE_DOMAINS:
        f.append("closure_bundle:unknown_closure_domain")
    return DryRunAuditClosureValidationResult(not f, tuple(f))


def summarize_dry_run_effect_verification(record: DryRunEffectVerification | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("verification_id", "source_dry_run_receipt_id", "dry_run_domain", "simulated_backend_class", "verification_status", "metadata_only", "dry_run_verification_only", "real_effect_receipt_created", "real_effect_performed", "real_backend_invoked", "host_mutation_performed", "digest")}


def summarize_dry_run_postcondition_verification(record: DryRunPostconditionVerification | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("verification_id", "source_dry_run_receipt_id", "source_effect_verification_id", "dry_run_domain", "postcondition_status", "metadata_only", "dry_run_postcondition_only", "real_postcondition_check_performed", "host_mutation_performed", "digest")}


def summarize_dry_run_rollback_rehearsal(record: DryRunRollbackRehearsal | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("rehearsal_id", "source_dry_run_receipt_id", "source_effect_verification_id", "dry_run_domain", "rollback_status", "metadata_only", "dry_run_rollback_only", "real_rollback_performed", "host_mutation_performed", "digest")}


def summarize_dry_run_audit_closure_receipt(record: DryRunAuditClosureReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("receipt_id", "source_dry_run_receipt_id", "source_effect_verification_id", "source_postcondition_verification_id", "source_rollback_rehearsal_id", "dry_run_domain", "audit_closure_status", "metadata_only", "dry_run_audit_only", "production_audit_receipt_created", "real_effect_receipt_created", "real_postcondition_check_performed", "real_rollback_performed", "real_fulfillment_performed", "real_effect_performed", "host_mutation_performed", "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed", "service_restart_performed", "file_cleanup_performed", "provider_invocation_performed", "network_performed", "prompt_assembly_performed", "digest")}


def summarize_dry_run_closure_bundle(record: DryRunClosureBundle | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("bundle_id", "source_dry_run_receipt_id", "effect_verification_id", "postcondition_verification_id", "rollback_rehearsal_id", "audit_closure_receipt_id", "closure_domain", "bundle_status", "metadata_only", "dry_run_closure_only", "real_fulfillment_performed", "real_effect_performed", "host_mutation_performed", "digest")}


def build_dry_run_audit_closure_wing(
    dry_run_receipt: DryRunExecutionReceipt | Mapping[str, Any],
    *,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> DryRunAuditClosureWingRecords:
    effect = build_dry_run_effect_verification(dry_run_receipt, created_at=created_at)
    postcondition = build_dry_run_postcondition_verification(dry_run_receipt, effect, created_at=created_at)
    rollback = build_dry_run_rollback_rehearsal(dry_run_receipt, effect, created_at=created_at)
    audit = build_dry_run_audit_closure_receipt(dry_run_receipt, effect, postcondition, rollback, created_at=created_at)
    bundle = build_dry_run_closure_bundle(dry_run_receipt, effect, postcondition, rollback, audit, created_at=created_at)
    return DryRunAuditClosureWingRecords(effect, postcondition, rollback, audit, bundle)
