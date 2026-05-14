"""Metadata-only runtime supervisor scaffold for SentientOS.

The supervisor records supplied service telemetry and readiness evidence for
future host effects. It does not inspect privileged live services, restart or
stop services, kill processes, install packages, alter service managers, mutate
host state, or perform network activity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence

SERVICE_STATUSES = frozenset({"service_status_nominal", "service_status_degraded", "service_status_unknown", "service_status_unavailable", "service_status_blocked", "service_status_contradicted"})
SUPERVISOR_STATUSES = frozenset({"runtime_supervisor_snapshot_recorded", "runtime_supervisor_snapshot_recorded_with_warnings", "runtime_supervisor_snapshot_incomplete", "runtime_supervisor_snapshot_contradicted", "runtime_supervisor_readiness_ready_for_review", "runtime_supervisor_readiness_ready_with_conditions", "runtime_supervisor_readiness_blocked", "runtime_supervisor_readiness_incomplete", "runtime_supervisor_readiness_contradicted"})
REQUIRED_SUPERVISOR_GATES = ("runtime_supervisor_observation_required", "service_scope_required", "postcondition_check_required", "audit_receipt_required")

@dataclass(frozen=True)
class RuntimeSupervisorValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()

@dataclass(frozen=True)
class RuntimeServiceRecord:
    service_id: str
    service_label: str
    service_kind: str
    observed_status: str
    desired_status_label: str
    health_labels: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    restart_supported: bool = False
    restart_authorized: bool = False
    stop_authorized: bool = False
    kill_authorized: bool = False
    host_mutation_performed: bool = False
    telemetry_only: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class RuntimeSupervisorSnapshot:
    snapshot_id: str
    node_id: str
    host_id: str
    service_records: tuple[RuntimeServiceRecord, ...]
    observed_at: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    metadata_only: bool = True
    telemetry_only: bool = True
    host_mutation_performed: bool = False
    service_restart_performed: bool = False
    process_kill_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class RuntimeSupervisorReadinessReport:
    report_id: str
    snapshot_id: str
    related_execution_readiness_manifest_id: str | None
    service_summary_counts: Mapping[str, int]
    degraded_service_ids: tuple[str, ...]
    blocked_service_ids: tuple[str, ...]
    supervisor_status: str
    required_future_gates: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    readiness_only: bool = True
    restart_authorized: bool = False
    kill_authorized: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)

def _digest_payload(prefix: str, payload: Mapping[str, Any], length: int = 24) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:length]

def _record_digest(record: Any) -> str:
    payload = record.to_dict()
    if "digest" in payload:
        payload["digest"] = ""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

def build_runtime_supervisor_snapshot(*, service_records: Sequence[RuntimeServiceRecord], snapshot_id: str | None = None, node_id: str = "local-node", host_id: str = "local-host", observed_at: str = "1970-01-01T00:00:00+00:00", warning_codes: Sequence[str] = (), risk_codes: Sequence[str] = ()) -> RuntimeSupervisorSnapshot:
    records = tuple(service_records)
    warnings = set(str(code) for code in warning_codes)
    risks = set(str(code) for code in risk_codes)
    for record in records:
        warnings.update(record.warning_codes)
        risks.update(record.risk_codes)
        if record.observed_status in {"service_status_unknown", "service_status_unavailable"}:
            warnings.add(f"service_observation_{record.observed_status}:{record.service_id}")
        if record.observed_status in {"service_status_blocked", "service_status_contradicted"}:
            risks.add(f"service_observation_{record.observed_status}:{record.service_id}")
    material = {"node_id": node_id, "host_id": host_id, "records": [record.to_dict() for record in records], "observed_at": observed_at}
    return RuntimeSupervisorSnapshot(snapshot_id or _digest_payload("rss_", material), node_id, host_id, records, observed_at, tuple(sorted(warnings)), tuple(sorted(risks)))

def build_runtime_supervisor_readiness_report(snapshot: RuntimeSupervisorSnapshot, *, related_execution_readiness_manifest_id: str | None = None, created_at: str = "1970-01-01T00:00:00+00:00") -> RuntimeSupervisorReadinessReport:
    counts: dict[str, int] = {status: 0 for status in sorted(SERVICE_STATUSES)}
    degraded: list[str] = []
    blocked: list[str] = []
    warnings = set(snapshot.warning_codes)
    risks = set(snapshot.risk_codes)
    contradicted = False
    for record in snapshot.service_records:
        counts[record.observed_status] = counts.get(record.observed_status, 0) + 1
        if record.restart_authorized or record.stop_authorized or record.kill_authorized or record.host_mutation_performed:
            contradicted = True
            risks.add(f"service_record_claims_runtime_authority:{record.service_id}")
        if record.observed_status == "service_status_degraded":
            degraded.append(record.service_id)
        if record.observed_status in {"service_status_blocked", "service_status_unavailable"}:
            blocked.append(record.service_id)
        if record.observed_status == "service_status_unknown":
            warnings.add(f"service_status_unknown:{record.service_id}")
    if snapshot.host_mutation_performed or snapshot.service_restart_performed or snapshot.process_kill_performed:
        contradicted = True
        risks.add("snapshot_claims_host_mutation_or_service_action")
    if contradicted:
        status = "runtime_supervisor_readiness_contradicted"
    elif blocked:
        status = "runtime_supervisor_readiness_blocked"
    elif degraded or warnings:
        status = "runtime_supervisor_readiness_ready_with_conditions"
    else:
        status = "runtime_supervisor_readiness_ready_for_review"
    material = {"snapshot": snapshot.snapshot_id, "manifest": related_execution_readiness_manifest_id, "created_at": created_at, "status": status}
    provisional = RuntimeSupervisorReadinessReport(_digest_payload("rsr_", material), snapshot.snapshot_id, related_execution_readiness_manifest_id, counts, tuple(sorted(degraded)), tuple(sorted(blocked)), status, REQUIRED_SUPERVISOR_GATES, tuple(sorted(warnings)), tuple(sorted(risks)), created_at, "")
    return replace(provisional, digest=runtime_supervisor_readiness_digest(provisional))

def validate_runtime_service_record(record: RuntimeServiceRecord) -> RuntimeSupervisorValidationResult:
    findings: list[str] = []
    if not record.service_id: findings.append("missing_service_id")
    if record.observed_status not in SERVICE_STATUSES: findings.append("unknown_service_status")
    if not record.telemetry_only: findings.append("service_record_not_telemetry_only")
    if record.restart_authorized: findings.append("service_record_claims_restart_authorization")
    if record.stop_authorized: findings.append("service_record_claims_stop_authorization")
    if record.kill_authorized: findings.append("service_record_claims_kill_authorization")
    if record.host_mutation_performed: findings.append("service_record_claims_host_mutation")
    return RuntimeSupervisorValidationResult(not findings, tuple(findings))

def validate_runtime_supervisor_snapshot(snapshot: RuntimeSupervisorSnapshot) -> RuntimeSupervisorValidationResult:
    findings: list[str] = []
    if not snapshot.snapshot_id: findings.append("missing_snapshot_id")
    if not snapshot.metadata_only or not snapshot.telemetry_only: findings.append("snapshot_not_metadata_telemetry_only")
    if snapshot.host_mutation_performed: findings.append("snapshot_claims_host_mutation")
    if snapshot.service_restart_performed: findings.append("snapshot_claims_service_restart")
    if snapshot.process_kill_performed: findings.append("snapshot_claims_process_kill")
    for record in snapshot.service_records:
        result = validate_runtime_service_record(record)
        if not result.ok:
            findings.extend(f"service:{record.service_id}:{finding}" for finding in result.findings)
    return RuntimeSupervisorValidationResult(not findings, tuple(findings))

def validate_runtime_supervisor_readiness_report(report: RuntimeSupervisorReadinessReport) -> RuntimeSupervisorValidationResult:
    findings: list[str] = []
    if not report.report_id: findings.append("missing_report_id")
    if report.supervisor_status not in SUPERVISOR_STATUSES: findings.append("unknown_supervisor_status")
    if report.digest and report.digest != runtime_supervisor_readiness_digest(report): findings.append("runtime_supervisor_readiness_digest_mismatch")
    if not report.metadata_only or not report.readiness_only: findings.append("report_not_metadata_readiness_only")
    if report.restart_authorized: findings.append("report_claims_restart_authorization")
    if report.kill_authorized: findings.append("report_claims_kill_authorization")
    if report.host_mutation_performed: findings.append("report_claims_host_mutation")
    return RuntimeSupervisorValidationResult(not findings, tuple(findings))

def runtime_supervisor_snapshot_digest(snapshot: RuntimeSupervisorSnapshot) -> str:
    return _record_digest(snapshot)

def runtime_supervisor_readiness_digest(report: RuntimeSupervisorReadinessReport) -> str:
    return _record_digest(report)

def summarize_runtime_supervisor_snapshot(snapshot: RuntimeSupervisorSnapshot) -> dict[str, Any]:
    return {"snapshot_id": snapshot.snapshot_id, "node_id": snapshot.node_id, "host_id": snapshot.host_id, "service_count": len(snapshot.service_records), "metadata_only": snapshot.metadata_only, "telemetry_only": snapshot.telemetry_only, "host_mutation_performed": snapshot.host_mutation_performed, "service_restart_performed": snapshot.service_restart_performed, "process_kill_performed": snapshot.process_kill_performed}

def summarize_runtime_supervisor_readiness_report(report: RuntimeSupervisorReadinessReport) -> dict[str, Any]:
    return {"report_id": report.report_id, "snapshot_id": report.snapshot_id, "supervisor_status": report.supervisor_status, "degraded_service_ids": report.degraded_service_ids, "blocked_service_ids": report.blocked_service_ids, "metadata_only": report.metadata_only, "readiness_only": report.readiness_only, "restart_authorized": report.restart_authorized, "kill_authorized": report.kill_authorized, "host_mutation_performed": report.host_mutation_performed}
