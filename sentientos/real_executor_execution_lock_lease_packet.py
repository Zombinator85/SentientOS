"""Deterministic metadata-only real executor execution lock lease packet builder.

This module consumes supplied Real Executor Execution Preflight Gate evidence and
explicit Real Executor Execution Lock Lease Packet candidates. It emits metadata
for later Real Executor Execution Lock Lease Gate consideration only. It never
acquires locks, creates real lock leases, creates lockfiles, executes preflight,
invokes, activates, releases, permits, authorizes, enables, writes, deletes,
purges, indexes, persists, executes, discloses, calls external services, touches
real memory roots, or grants authority, policy, consent, or truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Mapping, Sequence

RealExecutorExecutionLockLeasePacketStatus = Literal[
    "real_executor_execution_lock_lease_packet_ready",
    "real_executor_execution_lock_lease_packet_ready_with_warnings",
    "real_executor_execution_lock_lease_packet_deferred_for_operator_review",
    "real_executor_execution_lock_lease_packet_rejected",
    "real_executor_execution_lock_lease_packet_blocked",
    "real_executor_execution_lock_lease_packet_noop",
    "real_executor_execution_lock_lease_packet_invalid",
    "real_executor_execution_lock_lease_packet_failed",
]
RealExecutorExecutionLockLeasePacketDecision = Literal[
    "real_executor_execution_lock_lease_packet_ready_for_later_real_executor_execution_lock_lease_gate",
    "real_executor_execution_lock_lease_packet_ready_with_warnings",
    "real_executor_execution_lock_lease_packet_deferred_for_operator_review",
    "real_executor_execution_lock_lease_packet_rejected",
    "real_executor_execution_lock_lease_packet_blocked",
    "real_executor_execution_lock_lease_packet_noop",
]

REAL_EXECUTOR_EXECUTION_LOCK_LEASE_PACKET_CANDIDATE_TYPES = frozenset({
    "ai_capsule_real_executor_execution_lock_lease_packet_candidate",
    "human_summary_real_executor_execution_lock_lease_packet_candidate",
    "dual_capsule_real_executor_execution_lock_lease_packet_candidate",
    "protect_receipt_real_executor_execution_lock_lease_packet_candidate",
    "merge_receipt_real_executor_execution_lock_lease_packet_candidate",
    "tomb_archive_real_executor_execution_lock_lease_packet_candidate",
    "tomb_deferred_real_executor_execution_lock_lease_packet_candidate",
    "operator_review_real_executor_execution_lock_lease_packet_candidate",
    "noop_real_executor_execution_lock_lease_packet_candidate",
    "mixed_real_executor_execution_lock_lease_packet_candidate",
})
READY_REAL_EXECUTOR_EXECUTION_PREFLIGHT_GATE_DECISIONS = frozenset({
    "real_executor_execution_preflight_gate_ready_for_later_real_executor_execution_lock_lease_packet",
    "real_executor_execution_preflight_gate_ready_with_warnings",
    "real_executor_execution_preflight_gate_noop",
})
FAIL_STATUSES = {
    "real_executor_execution_lock_lease_packet_blocked",
    "real_executor_execution_lock_lease_packet_invalid",
    "real_executor_execution_lock_lease_packet_failed",
}

CARRIED_EVIDENCE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("real_executor_execution_preflight_packet", "real_executor_execution_preflight_packet_digest", "real_executor_execution_preflight_packet_decision"),
    ("real_executor_execution_invocation_gate", "real_executor_execution_invocation_gate_digest", "real_executor_execution_invocation_gate_decision"),
    ("real_executor_execution_invocation_packet", "real_executor_execution_invocation_packet_digest", "real_executor_execution_invocation_packet_decision"),
    ("real_executor_execution_activation_gate", "real_executor_execution_activation_gate_digest", "real_executor_execution_activation_gate_decision"),
    ("real_executor_execution_activation_packet", "real_executor_execution_activation_packet_digest", "real_executor_execution_activation_packet_decision"),
    ("real_executor_execution_release_gate", "real_executor_execution_release_gate_digest", "real_executor_execution_release_gate_decision"),
    ("real_executor_execution_release_packet", "real_executor_execution_release_packet_digest", "real_executor_execution_release_packet_decision"),
    ("real_executor_execution_permit_gate", "real_executor_execution_permit_gate_digest", "real_executor_execution_permit_gate_decision"),
    ("real_executor_execution_permit_packet", "real_executor_execution_permit_packet_digest", "real_executor_execution_permit_packet_decision"),
    ("real_executor_execution_authorization_gate", "real_executor_execution_authorization_gate_digest", "real_executor_execution_authorization_gate_decision"),
    ("real_executor_execution_authorization_packet", "real_executor_execution_authorization_packet_digest", "real_executor_execution_authorization_packet_decision"),
    ("real_executor_execution_gate", "real_executor_execution_gate_digest", "real_executor_execution_gate_decision"),
    ("real_executor_execution_plan", "real_executor_execution_plan_digest", "real_executor_execution_plan_decision"),
    ("real_executor_run_gate", "real_executor_run_gate_digest", "real_executor_run_gate_decision"),
    ("real_executor_run_packet", "real_executor_run_packet_digest", "real_executor_run_packet_decision"),
    ("real_executor_invocation_gate", "real_executor_invocation_gate_digest", "real_executor_invocation_gate_decision"),
    ("guarded_executor_invocation_packet", "guarded_executor_invocation_packet_digest", "guarded_executor_invocation_packet_decision"),
    ("guarded_executor_path_packet", "guarded_executor_path_packet_digest", "guarded_executor_path_packet_decision"),
    ("runtime_gate", "runtime_gate_digest", "runtime_gate_decision"),
    ("runtime_enablement_packet", "runtime_enablement_packet_digest", "runtime_enablement_packet_decision"),
    ("live_commit_execution_packet", "live_commit_execution_packet_digest", "live_commit_execution_packet_decision"),
    ("future_execution_gate", "future_execution_gate_digest", "future_execution_gate_decision"),
    ("constrained_enablement_path", "constrained_enablement_path_packet_digest", "constrained_enablement_path_decision"),
    ("executor_enablement_gate", "executor_enablement_gate_digest", "executor_enablement_gate_decision"),
    ("executor_skeleton", "executor_skeleton_digest", "executor_skeleton_decision"),
    ("invocation_harness", "invocation_harness_digest", "invocation_harness_decision"),
    ("activation_record", "activation_record_digest", "activation_record_decision"),
    ("preflight_packet", "preflight_packet_digest", "preflight_packet_decision"),
    ("lock_lease_gate", "lock_lease_gate_digest", "lock_lease_gate_decision"),
    ("executor_plan", "executor_plan_packet_digest", "executor_plan_decision"),
    ("runtime_authorization_packet", "runtime_authorization_packet_digest", "runtime_authorization_packet_decision"),
    ("readiness_envelope", "readiness_envelope_digest", "readiness_envelope_decision"),
    ("final_review", "final_review_digest", "final_review_decision"),
    ("real_root_admission", "real_root_admission_digest", "real_root_admission_decision"),
    ("sandbox_commit", "sandbox_commit_digest", "sandbox_commit_decision"),
)

NON_NOOP_METADATA_FIELDS = (
    "lock_lease_packet_readiness_metadata",
    "preflight_gate_confirmation_metadata",
    "lock_acquisition_denial_metadata",
    "lockfile_creation_denial_metadata",
    "final_lock_hold_point_metadata",
    "emergency_stop_confirmation_metadata",
    "rollback_readiness_metadata",
    "verification_readiness_metadata",
    "audit_readiness_metadata",
)

BOUNDARY_INVARIANTS: Mapping[str, bool] = {
    "real_executor_execution_lock_lease_packet_is_not_lock_acquisition": True,
    "real_executor_execution_lock_lease_packet_does_not_acquire_locks": True,
    "real_executor_execution_lock_lease_packet_does_not_create_real_lock_leases": True,
    "real_executor_execution_lock_lease_packet_does_not_create_lockfiles": True,
    "real_executor_execution_lock_lease_packet_is_not_preflight_execution": True,
    "real_executor_execution_lock_lease_packet_does_not_execute_preflight": True,
    "real_executor_execution_lock_lease_packet_is_not_executor_invocation": True,
    "real_executor_execution_lock_lease_packet_does_not_invoke_executor": True,
    "real_executor_execution_lock_lease_packet_is_not_executor_activation": True,
    "real_executor_execution_lock_lease_packet_does_not_activate_executor": True,
    "real_executor_execution_lock_lease_packet_is_not_execution_release": True,
    "real_executor_execution_lock_lease_packet_does_not_release_execution": True,
    "real_executor_execution_lock_lease_packet_is_not_execution_permit": True,
    "real_executor_execution_lock_lease_packet_does_not_issue_permit": True,
    "real_executor_execution_lock_lease_packet_is_not_execution_authorization": True,
    "real_executor_execution_lock_lease_packet_is_not_permission_to_execute": True,
    "real_executor_execution_lock_lease_packet_is_not_executor_execution": True,
    "real_executor_execution_lock_lease_packet_is_not_executor_run": True,
    "real_executor_execution_lock_lease_packet_is_not_runtime_enablement": True,
    "real_executor_execution_lock_lease_packet_is_not_runtime_flag_flip": True,
    "real_executor_execution_lock_lease_packet_is_not_live_commit_execution": True,
    "real_executor_execution_lock_lease_packet_is_not_enabled_executor": True,
    "real_executor_execution_lock_lease_packet_is_not_executor_enablement": True,
    "real_executor_execution_lock_lease_packet_is_not_memory_write_deletion_purge": True,
    "real_executor_execution_lock_lease_packet_is_not_index_mutation": True,
    "real_executor_execution_lock_lease_packet_is_not_capsule_persistence": True,
    "real_executor_execution_lock_lease_packet_is_not_tomb_completion": True,
    "real_executor_execution_lock_lease_packet_is_not_prompt_assembly": True,
    "real_executor_execution_lock_lease_packet_is_not_live_context_retrieval": True,
    "real_executor_execution_lock_lease_packet_is_not_action_execution": True,
    "real_executor_execution_lock_lease_packet_is_not_external_disclosure": True,
    "real_executor_execution_lock_lease_packet_is_not_truth_policy_authority_or_consent": True,
    "lock_lease_packet_readiness_is_metadata_only": True,
    "preflight_gate_confirmation_is_metadata_only": True,
    "lock_acquisition_denial_is_metadata_only": True,
    "lockfile_creation_denial_is_metadata_only": True,
    "final_lock_hold_points_are_metadata_only": True,
    "emergency_stop_confirmation_is_metadata_only": True,
    "rollback_readiness_is_metadata_only": True,
    "verification_readiness_is_metadata_only": True,
    "audit_readiness_is_metadata_only": True,
    "real_executor_enabled": False,
    "real_executor_run_enabled": False,
    "real_executor_execution_enabled": False,
    "real_executor_execution_authorized": False,
    "real_executor_authorization_gate_passed": False,
    "real_executor_execution_permit_issued": False,
    "real_executor_execution_permit_gate_passed": False,
    "real_executor_execution_released": False,
    "real_executor_execution_release_gate_passed": False,
    "real_executor_execution_activation_packet_created": False,
    "real_executor_execution_activation_gate_passed": False,
    "real_executor_execution_activation_enabled": False,
    "real_executor_activation_enabled": False,
    "real_executor_execution_invocation_packet_created": False,
    "real_executor_execution_invocation_gate_passed": False,
    "real_executor_execution_invocation_enabled": False,
    "real_executor_invocation_enabled": False,
    "real_executor_invoked": False,
    "real_executor_execution_preflight_packet_created": False,
    "real_executor_execution_preflight_gate_passed": False,
    "real_executor_execution_preflight_enabled": False,
    "real_executor_execution_preflight_executed": False,
    "real_executor_execution_lock_lease_packet_created": False,
    "real_executor_execution_lock_lease_gate_passed": False,
    "real_executor_execution_lock_lease_enabled": False,
    "real_executor_execution_lock_lease_created": False,
    "real_lock_acquisition_enabled": False,
    "real_lock_acquired": False,
    "lockfile_creation_enabled": False,
    "lockfile_created": False,
    "lock_lease_renewal_enabled": False,
    "lock_lease_release_enabled": False,
    "real_memory_root_write_enabled": False,
    "live_memory_write_enabled": False,
    "prompt_materialization_enabled": False,
    "live_context_retrieval_enabled": False,
    "action_execution_enabled": False,
    "external_disclosure_enabled": False,
    "external_service_enabled": False,
    "future_real_executor_execution_lock_lease_gate_required": True,
    "future_real_live_memory_commit_execution_required": True,
    "future_post_execution_audit_required": True,
}
FORBIDDEN_NEXT_STEPS = (
    "lock_acquisition", "lock_lease_creation", "lockfile_creation", "enabled_lock_acquisition", "preflight_execution",
    "enabled_preflight", "real_executor_invocation", "enabled_invocation", "real_executor_activation", "enabled_activation",
    "execution_release", "execution_permit", "execution_authorization", "executor_enablement", "runtime_flag_flipping",
    "live_commit_execution", "real_executor_run", "execution_plan_run", "lock_lease_gate_creation", "real_live_memory_write",
    "real_live_memory_delete", "real_live_memory_purge", "index_mutation", "capsule_persistence", "tomb_completion",
    "prompt_assembly", "live_context_retrieval", "action_execution", "external_disclosure", "external_service_call", "authority_grant",
)
FORBIDDEN_CLAIM_CODES = {
    "real_lock_acquired": "lock_acquisition_claim",
    "real_lock_lease_created": "lock_lease_creation_claim",
    "lockfile_created": "lockfile_creation_claim",
    "real_executor_run_executed": "executor_run_claim",
    "executor_enabled": "executor_enablement_claim",
    "executor_invoked": "executor_invocation_claim",
    "executor_activated": "executor_activation_claim",
    "preflight_executed": "preflight_execution_claim",
    "runtime_enablement_claimed": "runtime_enablement_claim",
    "runtime_flags_flipped": "runtime_flag_flipping_claim",
    "live_commit_executed": "live_execution_claim",
    "permission_to_execute_now": "executor_permission_claim",
    "execution_released": "execution_release_claim",
    "execution_permit_issued": "execution_permit_claim",
    "execution_authorized": "execution_authorization_claim",
    "live_memory_write_claimed": "live_write_claim",
    "live_memory_delete_claimed": "live_delete_claim",
    "live_memory_purge_claimed": "live_purge_claim",
    "live_index_mutation_claimed": "index_mutation_claim",
    "capsule_persistence_claimed": "capsule_persistence_claim",
    "tomb_completed": "tomb_completion_claim",
    "prompt_assembly_claimed": "prompt_assembly_claim",
    "live_context_retrieval_claimed": "live_context_retrieval_claim",
    "action_execution_claimed": "action_execution_claim",
    "external_disclosure_claimed": "external_disclosure_claim",
    "external_service_called": "external_service_claim",
    "authority_granted": "authority_grant_claim",
}
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{1,127}$")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class RealExecutorExecutionLockLeasePacketFinding:
    severity: str
    code: str
    message: str
    candidate_id: str = ""
    record_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class RealExecutorExecutionLockLeasePacketPolicy:
    metadata_only: bool = True
    default_deny: bool = True
    require_scope_alignment: bool = True
    require_preflight_gate_decision_match: bool = True
    require_carried_evidence_match: bool = True
    block_forbidden_claims: bool = True
    real_executor_enabled: bool = False
    real_executor_runtime_enablement_enabled: bool = False
    real_executor_enablement_enabled: bool = False
    real_executor_invocation_enabled: bool = False
    real_executor_run_enabled: bool = False
    real_executor_activation_enabled: bool = False
    real_lock_acquisition_enabled: bool = False
    lockfile_creation_enabled: bool = False
    real_lock_lease_creation_enabled: bool = False
    real_memory_root_access_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealExecutorExecutionLockLeasePacketCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    operator_scope_keys: tuple[str, ...]
    metadata: Mapping[str, Any]
    claims: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RealExecutorExecutionLockLeasePacketCandidate":
        return cls(
            candidate_id=str(raw.get("candidate_id") or ""),
            record_id=str(raw.get("record_id") or raw.get("candidate_id") or ""),
            candidate_type=str(raw.get("candidate_type") or ""),
            operator_scope_keys=tuple(str(item) for item in raw.get("operator_scope_keys", ()) if isinstance(item, str)),
            metadata=_as_mapping(raw.get("metadata")),
            claims=_as_mapping(raw.get("real_executor_execution_lock_lease_packet_claims")),
        )

    @property
    def is_noop(self) -> bool:
        return self.candidate_type == "noop_real_executor_execution_lock_lease_packet_candidate"


@dataclass(frozen=True)
class RealExecutorExecutionLockLeasePacketMetadataRecord:
    kind: str
    candidate_id: str
    record_id: str
    digest: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class RealExecutorExecutionLockLeasePacketRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    real_executor_execution_lock_lease_packet_decision: RealExecutorExecutionLockLeasePacketDecision
    real_executor_execution_preflight_gate_digest: str
    real_executor_execution_preflight_gate_decision: str
    carried_evidence: Mapping[str, Mapping[str, str]]
    operator_scope_keys: tuple[str, ...]
    metadata_records: tuple[RealExecutorExecutionLockLeasePacketMetadataRecord, ...]
    safe_next_steps: tuple[str, ...]
    forbidden_next_steps: tuple[str, ...]
    boundary_invariants: Mapping[str, bool]
    metadata_only: bool = True
    default_deny: bool = True
    not_permission_to_execute: bool = True
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "record_id": self.record_id,
            "candidate_type": self.candidate_type,
            "real_executor_execution_lock_lease_packet_decision": self.real_executor_execution_lock_lease_packet_decision,
            "real_executor_execution_preflight_gate_digest": self.real_executor_execution_preflight_gate_digest,
            "real_executor_execution_preflight_gate_decision": self.real_executor_execution_preflight_gate_decision,
            "carried_evidence": {key: dict(value) for key, value in sorted(self.carried_evidence.items())},
            "operator_scope_keys": list(self.operator_scope_keys),
            "metadata_records": [record.to_dict() for record in self.metadata_records],
            "safe_next_steps": list(self.safe_next_steps),
            "forbidden_next_steps": list(self.forbidden_next_steps),
            "boundary_invariants": dict(sorted(self.boundary_invariants.items())),
            "metadata_only": self.metadata_only,
            "default_deny": self.default_deny,
            "not_permission_to_execute": self.not_permission_to_execute,
            "digest": self.digest,
        }

    def with_digest(self) -> "RealExecutorExecutionLockLeasePacketRecord":
        return replace(self, digest=_digest({k: v for k, v in self.to_dict().items() if k != "digest"}))


@dataclass(frozen=True)
class RealExecutorExecutionLockLeasePacket:
    packet_id: str
    status: RealExecutorExecutionLockLeasePacketStatus
    records: tuple[RealExecutorExecutionLockLeasePacketRecord, ...]
    metadata_only: bool = True
    default_deny: bool = True
    not_permission_to_execute: bool = True
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "packet_id": self.packet_id,
            "status": self.status,
            "records": [record.to_dict() for record in self.records],
            "metadata_only": self.metadata_only,
            "default_deny": self.default_deny,
            "not_permission_to_execute": self.not_permission_to_execute,
            "digest": self.digest,
        }

    def with_digest(self) -> "RealExecutorExecutionLockLeasePacket":
        return replace(self, digest=_digest({k: v for k, v in self.to_dict().items() if k != "digest"}))


@dataclass(frozen=True)
class RealExecutorExecutionLockLeasePacketReport:
    status: RealExecutorExecutionLockLeasePacketStatus
    findings: tuple[RealExecutorExecutionLockLeasePacketFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "findings": [finding.to_dict() for finding in self.findings],
            "summary_counts": dict(self.summary_counts),
            "digest": self.digest,
        }


@dataclass(frozen=True)
class RealExecutorExecutionLockLeasePacketResult:
    status: RealExecutorExecutionLockLeasePacketStatus
    packet: RealExecutorExecutionLockLeasePacket | None
    report: RealExecutorExecutionLockLeasePacketReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> RealExecutorExecutionLockLeasePacketPolicy:
    return RealExecutorExecutionLockLeasePacketPolicy()


def validate_policy(policy: RealExecutorExecutionLockLeasePacketPolicy | None = None) -> dict[str, Any]:
    active = policy or build_default_policy()
    findings: list[RealExecutorExecutionLockLeasePacketFinding] = []
    if not active.default_deny or not active.metadata_only:
        findings.append(RealExecutorExecutionLockLeasePacketFinding("error", "policy_not_metadata_only_default_deny", "policy must remain metadata-only and default-deny"))
    for name in (
        "real_executor_enabled", "real_executor_runtime_enablement_enabled", "real_executor_enablement_enabled",
        "real_executor_invocation_enabled", "real_executor_run_enabled", "real_executor_activation_enabled",
        "real_lock_acquisition_enabled", "lockfile_creation_enabled", "real_lock_lease_creation_enabled", "real_memory_root_access_enabled",
    ):
        if bool(getattr(active, name)):
            findings.append(RealExecutorExecutionLockLeasePacketFinding("error", name, f"{name} must remain false"))
    return {"status": "valid" if not findings else "invalid", "policy": active.to_dict(), "findings": [f.to_dict() for f in findings]}


def _blocked(code: str, findings: Sequence[RealExecutorExecutionLockLeasePacketFinding] = ()) -> RealExecutorExecutionLockLeasePacketResult:
    all_findings = tuple(findings) or (RealExecutorExecutionLockLeasePacketFinding("error", code, code),)
    report = RealExecutorExecutionLockLeasePacketReport("real_executor_execution_lock_lease_packet_blocked", all_findings, {"blocked": 1})
    report = replace(report, digest=_digest(report.to_dict()))
    return RealExecutorExecutionLockLeasePacketResult("real_executor_execution_lock_lease_packet_blocked", None, report, _digest(report.to_dict()))


def _metadata_record(kind: str, candidate: RealExecutorExecutionLockLeasePacketCandidate, metadata: Mapping[str, Any]) -> RealExecutorExecutionLockLeasePacketMetadataRecord:
    return RealExecutorExecutionLockLeasePacketMetadataRecord(kind, candidate.candidate_id, candidate.record_id, _digest(dict(metadata)))


def _valid_candidate(candidate: RealExecutorExecutionLockLeasePacketCandidate) -> bool:
    return bool(_ID_RE.match(candidate.candidate_id)) and bool(_ID_RE.match(candidate.record_id)) and candidate.candidate_type in REAL_EXECUTOR_EXECUTION_LOCK_LEASE_PACKET_CANDIDATE_TYPES


def _preflight_gate_and_record(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]] | RealExecutorExecutionLockLeasePacketResult:
    packet = _as_mapping(payload.get("real_executor_execution_preflight_gate"))
    if not packet:
        return _blocked("missing_real_executor_execution_preflight_gate")
    records = packet.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records:
        return _blocked("invalid_real_executor_execution_preflight_gate")
    record = _as_mapping(records[0])
    decision = str(record.get("real_executor_execution_preflight_gate_decision") or "")
    if not str(packet.get("digest") or "") or not str(record.get("digest") or "") or decision not in READY_REAL_EXECUTOR_EXECUTION_PREFLIGHT_GATE_DECISIONS:
        return _blocked("invalid_real_executor_execution_preflight_gate")
    return packet, record


def _candidate_list(payload: Mapping[str, Any]) -> Sequence[Any] | RealExecutorExecutionLockLeasePacketResult:
    candidates = payload.get("real_executor_execution_lock_lease_packet_candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)) or not candidates:
        return _blocked("missing_real_executor_execution_lock_lease_packet_candidate")
    return candidates


def _check_required_metadata(raw: Mapping[str, Any], candidate: RealExecutorExecutionLockLeasePacketCandidate) -> RealExecutorExecutionLockLeasePacketResult | None:
    if candidate.is_noop:
        return None
    for field in NON_NOOP_METADATA_FIELDS:
        if not isinstance(raw.get(field), Mapping) or not raw.get(field):
            return _blocked(f"missing_{field}", [RealExecutorExecutionLockLeasePacketFinding("error", f"missing_{field}", f"missing required non-noop metadata: {field}", candidate.candidate_id, candidate.record_id)])
    return None


def _check_scope(gate_record: Mapping[str, Any], candidate: RealExecutorExecutionLockLeasePacketCandidate, policy: RealExecutorExecutionLockLeasePacketPolicy) -> RealExecutorExecutionLockLeasePacketResult | None:
    if not policy.require_scope_alignment or candidate.candidate_type == "mixed_real_executor_execution_lock_lease_packet_candidate":
        return None
    expected = tuple(str(item) for item in gate_record.get("operator_scope_keys", ()) if isinstance(item, str))
    if tuple(sorted(expected)) != tuple(sorted(candidate.operator_scope_keys)):
        return _blocked("scope_mismatch", [RealExecutorExecutionLockLeasePacketFinding("error", "scope_mismatch", "operator scope keys must match preflight gate evidence", candidate.candidate_id, candidate.record_id)])
    return None


def _check_evidence(raw: Mapping[str, Any], preflight_gate: Mapping[str, Any], gate_record: Mapping[str, Any], candidate: RealExecutorExecutionLockLeasePacketCandidate) -> RealExecutorExecutionLockLeasePacketResult | None:
    if str(raw.get("claimed_real_executor_execution_preflight_gate_digest") or "") != str(preflight_gate.get("digest") or ""):
        return _blocked("real_executor_execution_preflight_gate_digest_mismatch", [RealExecutorExecutionLockLeasePacketFinding("error", "real_executor_execution_preflight_gate_digest_mismatch", "preflight gate digest mismatch", candidate.candidate_id, candidate.record_id)])
    if str(raw.get("claimed_real_executor_execution_preflight_gate_decision") or "") != str(gate_record.get("real_executor_execution_preflight_gate_decision") or ""):
        return _blocked("real_executor_execution_preflight_gate_decision_mismatch", [RealExecutorExecutionLockLeasePacketFinding("error", "real_executor_execution_preflight_gate_decision_mismatch", "preflight gate decision mismatch", candidate.candidate_id, candidate.record_id)])
    carried = _as_mapping(gate_record.get("carried_evidence"))
    for label, digest_field, decision_field in CARRIED_EVIDENCE_FIELDS:
        evidence = _as_mapping(carried.get(label))
        actual_digest = str(evidence.get("digest") or gate_record.get(digest_field) or "")
        actual_decision = str(evidence.get("decision") or gate_record.get(decision_field) or "")
        claimed_digest = str(raw.get(f"claimed_{digest_field}") or "")
        claimed_decision = str(raw.get(f"claimed_{decision_field}") or "")
        if actual_digest and claimed_digest != actual_digest:
            return _blocked(f"{label}_digest_mismatch", [RealExecutorExecutionLockLeasePacketFinding("error", f"{label}_digest_mismatch", f"{label} digest mismatch", candidate.candidate_id, candidate.record_id)])
        if actual_decision and claimed_decision != actual_decision:
            return _blocked(f"{label}_decision_mismatch", [RealExecutorExecutionLockLeasePacketFinding("error", f"{label}_decision_mismatch", f"{label} decision mismatch", candidate.candidate_id, candidate.record_id)])
    return None


def _claims_findings(candidate: RealExecutorExecutionLockLeasePacketCandidate) -> tuple[RealExecutorExecutionLockLeasePacketFinding, ...]:
    return tuple(
        RealExecutorExecutionLockLeasePacketFinding("error", code, f"forbidden real executor execution lock lease packet claim blocked: {key}", candidate.candidate_id, candidate.record_id)
        for key, code in FORBIDDEN_CLAIM_CODES.items()
        if candidate.claims.get(key) is True
    )


def _decision(candidate: RealExecutorExecutionLockLeasePacketCandidate, findings: Sequence[RealExecutorExecutionLockLeasePacketFinding]) -> RealExecutorExecutionLockLeasePacketDecision:
    if candidate.is_noop:
        return "real_executor_execution_lock_lease_packet_noop"
    if candidate.candidate_type == "operator_review_real_executor_execution_lock_lease_packet_candidate":
        return "real_executor_execution_lock_lease_packet_deferred_for_operator_review"
    if any(f.severity == "warning" for f in findings) or candidate.candidate_type == "mixed_real_executor_execution_lock_lease_packet_candidate":
        return "real_executor_execution_lock_lease_packet_ready_with_warnings"
    return "real_executor_execution_lock_lease_packet_ready_for_later_real_executor_execution_lock_lease_gate"


def _safe_actions(decision: RealExecutorExecutionLockLeasePacketDecision) -> tuple[str, ...]:
    if decision == "real_executor_execution_lock_lease_packet_noop":
        return ("record_noop_metadata", "continue_review_without_executor_authority")
    if decision == "real_executor_execution_lock_lease_packet_deferred_for_operator_review":
        return ("operator_review_metadata", "resolve_without_overriding_hard_blockers")
    return ("review_real_executor_execution_lock_lease_packet_metadata", "prepare_separate_future_real_executor_execution_lock_lease_gate_request")


def _carried_evidence(record: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    carried_record = _as_mapping(record.get("carried_evidence"))
    carried: dict[str, dict[str, str]] = {}
    for label, digest_field, decision_field in CARRIED_EVIDENCE_FIELDS:
        evidence = _as_mapping(carried_record.get(label))
        carried[label] = {"digest": str(evidence.get("digest") or record.get(digest_field) or ""), "decision": str(evidence.get("decision") or record.get(decision_field) or "")}
    return carried


def evaluate_real_executor_execution_lock_lease_packet(payload: Mapping[str, Any], policy: RealExecutorExecutionLockLeasePacketPolicy | None = None) -> RealExecutorExecutionLockLeasePacketResult:
    active_policy = policy or build_default_policy()
    policy_validation = validate_policy(active_policy)
    if policy_validation["status"] != "valid":
        return _blocked("invalid_policy", tuple(RealExecutorExecutionLockLeasePacketFinding(**f) for f in policy_validation["findings"]))
    pair = _preflight_gate_and_record(payload)
    if isinstance(pair, RealExecutorExecutionLockLeasePacketResult):
        return pair
    preflight_gate, gate_record = pair
    candidates_raw = _candidate_list(payload)
    if isinstance(candidates_raw, RealExecutorExecutionLockLeasePacketResult):
        return candidates_raw
    findings: list[RealExecutorExecutionLockLeasePacketFinding] = []
    records: list[RealExecutorExecutionLockLeasePacketRecord] = []
    try:
        for raw_value in candidates_raw:
            raw = _as_mapping(raw_value)
            candidate = RealExecutorExecutionLockLeasePacketCandidate.from_mapping(raw)
            if not _valid_candidate(candidate):
                return _blocked("invalid_real_executor_execution_lock_lease_packet_candidate", [RealExecutorExecutionLockLeasePacketFinding("error", "invalid_real_executor_execution_lock_lease_packet_candidate", "invalid real executor execution lock lease packet candidate", candidate.candidate_id, candidate.record_id)])
            claim_findings = _claims_findings(candidate) if active_policy.block_forbidden_claims else ()
            if claim_findings:
                return _blocked(claim_findings[0].code, claim_findings)
            for check in (_check_required_metadata(raw, candidate), _check_scope(gate_record, candidate, active_policy), _check_evidence(raw, preflight_gate, gate_record, candidate)):
                if check is not None:
                    return check
            local_findings = list(findings)
            if candidate.candidate_type == "mixed_real_executor_execution_lock_lease_packet_candidate" and candidate.metadata.get("diagnostic_warning") is True:
                local_findings.append(RealExecutorExecutionLockLeasePacketFinding("warning", "mixed_scope_diagnostic", "mixed real executor execution lock lease packet diagnostics allowed as warnings only", candidate.candidate_id, candidate.record_id))
            decision = _decision(candidate, local_findings)
            metadata_records = tuple(_metadata_record(field, candidate, _as_mapping(raw.get(field))) for field in NON_NOOP_METADATA_FIELDS if isinstance(raw.get(field), Mapping))
            record = RealExecutorExecutionLockLeasePacketRecord(
                candidate.candidate_id,
                candidate.record_id,
                candidate.candidate_type,
                decision,
                str(preflight_gate.get("digest") or ""),
                str(gate_record.get("real_executor_execution_preflight_gate_decision") or ""),
                _carried_evidence(gate_record),
                tuple(sorted(candidate.operator_scope_keys)),
                metadata_records,
                _safe_actions(decision),
                FORBIDDEN_NEXT_STEPS,
                BOUNDARY_INVARIANTS,
            ).with_digest()
            records.append(record)
            findings = local_findings
    except Exception as exc:  # deterministic validation failure surface, not import wrapping
        return _blocked("invalid_payload", [RealExecutorExecutionLockLeasePacketFinding("error", "invalid_payload", str(exc))])
    status: RealExecutorExecutionLockLeasePacketStatus = "real_executor_execution_lock_lease_packet_ready"
    decisions = {record.real_executor_execution_lock_lease_packet_decision for record in records}
    if decisions == {"real_executor_execution_lock_lease_packet_noop"}:
        status = "real_executor_execution_lock_lease_packet_noop"
    elif "real_executor_execution_lock_lease_packet_deferred_for_operator_review" in decisions:
        status = "real_executor_execution_lock_lease_packet_deferred_for_operator_review"
    elif any(decision == "real_executor_execution_lock_lease_packet_ready_with_warnings" for decision in decisions):
        status = "real_executor_execution_lock_lease_packet_ready_with_warnings"
    counts = {"candidate_count": len(records), "finding_count": len(findings), "warning_count": sum(1 for finding in findings if finding.severity == "warning")}
    packet = RealExecutorExecutionLockLeasePacket("real-executor-execution-lock-lease-packet", status, tuple(records)).with_digest()
    report = RealExecutorExecutionLockLeasePacketReport(status, tuple(findings), counts)
    report = replace(report, digest=_digest(report.to_dict()))
    return RealExecutorExecutionLockLeasePacketResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))


__all__ = [
    "BOUNDARY_INVARIANTS",
    "FAIL_STATUSES",
    "REAL_EXECUTOR_EXECUTION_LOCK_LEASE_PACKET_CANDIDATE_TYPES",
    "RealExecutorExecutionLockLeasePacketPolicy",
    "build_default_policy",
    "evaluate_real_executor_execution_lock_lease_packet",
    "validate_policy",
]
