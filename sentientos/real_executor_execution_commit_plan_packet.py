"""Deterministic metadata-only real executor execution commit plan packet builder.

This module consumes supplied Real Executor Execution Lock Lease Gate evidence
and explicit Real Executor Execution Commit Plan Packet candidates. It emits
metadata for later Real Executor Execution Commit Plan Gate consideration only.
It never acquires locks, creates lockfiles, creates real lock leases, executes preflight, invokes, activates, releases, permits, authorizes,
enables, flips runtime flags, writes, deletes, purges, indexes, persists, executes, discloses,
calls external services, touches real memory roots, or grants authority, policy,
consent, or truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Mapping, Sequence

RealExecutorExecutionCommitPlanPacketStatus = Literal[
    "real_executor_execution_commit_plan_packet_ready",
    "real_executor_execution_commit_plan_packet_ready_with_warnings",
    "real_executor_execution_commit_plan_packet_deferred_for_operator_review",
    "real_executor_execution_commit_plan_packet_rejected",
    "real_executor_execution_commit_plan_packet_blocked",
    "real_executor_execution_commit_plan_packet_noop",
    "real_executor_execution_commit_plan_packet_invalid",
    "real_executor_execution_commit_plan_packet_failed",
]
RealExecutorExecutionCommitPlanPacketDecision = Literal[
    "real_executor_execution_commit_plan_packet_ready_for_later_real_executor_execution_commit_plan_gate",
    "real_executor_execution_commit_plan_packet_ready_with_warnings",
    "real_executor_execution_commit_plan_packet_deferred_for_operator_review",
    "real_executor_execution_commit_plan_packet_rejected",
    "real_executor_execution_commit_plan_packet_blocked",
    "real_executor_execution_commit_plan_packet_noop",
]

REAL_EXECUTOR_EXECUTION_COMMIT_PLAN_PACKET_CANDIDATE_TYPES = frozenset({
    "ai_capsule_real_executor_execution_commit_plan_packet_candidate",
    "human_summary_real_executor_execution_commit_plan_packet_candidate",
    "dual_capsule_real_executor_execution_commit_plan_packet_candidate",
    "protect_receipt_real_executor_execution_commit_plan_packet_candidate",
    "merge_receipt_real_executor_execution_commit_plan_packet_candidate",
    "tomb_archive_real_executor_execution_commit_plan_packet_candidate",
    "tomb_deferred_real_executor_execution_commit_plan_packet_candidate",
    "operator_review_real_executor_execution_commit_plan_packet_candidate",
    "noop_real_executor_execution_commit_plan_packet_candidate",
    "mixed_real_executor_execution_commit_plan_packet_candidate",
})
READY_REAL_EXECUTOR_EXECUTION_LOCK_LEASE_GATE_DECISIONS = frozenset({
    "real_executor_execution_lock_lease_gate_ready_for_later_real_executor_execution_commit_plan_packet",
    "real_executor_execution_lock_lease_gate_ready_with_warnings",
    "real_executor_execution_lock_lease_gate_noop",
})
FAIL_STATUSES = {
    "real_executor_execution_commit_plan_packet_blocked",
    "real_executor_execution_commit_plan_packet_invalid",
    "real_executor_execution_commit_plan_packet_failed",
}

CARRIED_EVIDENCE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("real_executor_execution_lock_lease_packet", "real_executor_execution_lock_lease_packet_digest", "real_executor_execution_lock_lease_packet_decision"),
    ("real_executor_execution_preflight_gate", "real_executor_execution_preflight_gate_digest", "real_executor_execution_preflight_gate_decision"),
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
    ("lock_lease_packet", "lock_lease_packet_digest", "lock_lease_packet_decision"),
    ("commit_plan_packet", "commit_plan_packet_digest", "commit_plan_packet_decision"),
    ("executor_plan_packet", "executor_plan_packet_digest", "executor_plan_decision"),
    ("runtime_authorization_packet", "runtime_authorization_packet_digest", "runtime_authorization_packet_decision"),
    ("readiness_envelope", "readiness_envelope_digest", "readiness_envelope_decision"),
    ("final_review", "final_review_digest", "final_review_decision"),
    ("real_root_admission", "real_root_admission_digest", "real_root_admission_decision"),
    ("sandbox_commit", "sandbox_commit_digest", "sandbox_commit_decision"),
)

NON_NOOP_METADATA_FIELDS = (
    "commit_plan_packet_readiness_metadata",
    "lock_lease_gate_confirmation_metadata",
    "live_commit_execution_denial_metadata",
    "live_memory_write_denial_metadata",
    "final_commit_plan_hold_point_metadata",
    "emergency_stop_confirmation_metadata",
    "rollback_readiness_metadata",
    "verification_readiness_metadata",
    "audit_readiness_metadata",
    "future_real_executor_execution_commit_plan_gate_requirement_metadata",
)

INVARIANTS: dict[str, bool] = {
    "real_executor_execution_commit_plan_packet_does_not_execute_a_commit": True,
    "real_executor_execution_commit_plan_packet_does_not_execute_commit": True,
    "real_executor_execution_commit_plan_packet_does_not_apply_a_commit": True,
    "real_executor_execution_commit_plan_packet_does_not_apply_commit": True,
    "real_executor_execution_commit_plan_packet_does_not_write_live_memory": True,
    "real_executor_execution_commit_plan_packet_is_not_preflight_execution": True,
    "real_executor_execution_commit_plan_packet_does_not_execute_preflight": True,
    "real_executor_execution_commit_plan_packet_is_not_executor_invocation": True,
    "real_executor_execution_commit_plan_packet_does_not_invoke_executor": True,
    "real_executor_execution_commit_plan_packet_is_not_executor_activation": True,
    "real_executor_execution_commit_plan_packet_does_not_activate_executor": True,
    "real_executor_execution_commit_plan_packet_is_not_execution_release": True,
    "real_executor_execution_commit_plan_packet_does_not_release_execution": True,
    "real_executor_execution_commit_plan_packet_is_not_execution_permit": True,
    "real_executor_execution_commit_plan_packet_does_not_issue_permit": True,
    "real_executor_execution_commit_plan_packet_is_not_execution_authorization": True,
    "real_executor_execution_commit_plan_packet_is_not_permission_to_execute": True,
    "real_executor_execution_commit_plan_packet_is_not_executor_execution": True,
    "real_executor_execution_commit_plan_packet_is_not_executor_run": True,
    "real_executor_execution_commit_plan_packet_is_not_runtime_enablement": True,
    "real_executor_execution_commit_plan_packet_is_not_runtime_flag_flip": True,
    "real_executor_execution_commit_plan_packet_is_not_live_commit_execution": True,
    "real_executor_execution_commit_plan_packet_is_not_enabled_executor": True,
    "real_executor_execution_commit_plan_packet_is_not_executor_enablement": True,
    "real_executor_execution_commit_plan_packet_is_not_lock_acquisition": True,
    "real_executor_execution_commit_plan_packet_does_not_acquire_locks": True,
    "real_executor_execution_commit_plan_packet_does_not_create_real_lock_leases": True,
    "real_executor_execution_commit_plan_packet_does_not_create_lockfiles": True,
    "real_executor_execution_commit_plan_packet_is_not_lockfile_creation": True,
    "real_executor_execution_commit_plan_packet_is_not_memory_write_deletion_purge": True,
    "real_executor_execution_commit_plan_packet_is_not_index_mutation": True,
    "real_executor_execution_commit_plan_packet_is_not_capsule_persistence": True,
    "real_executor_execution_commit_plan_packet_is_not_tomb_completion": True,
    "real_executor_execution_commit_plan_packet_is_not_prompt_assembly": True,
    "real_executor_execution_commit_plan_packet_is_not_live_context_retrieval": True,
    "real_executor_execution_commit_plan_packet_is_not_action_execution": True,
    "real_executor_execution_commit_plan_packet_is_not_external_disclosure": True,
    "real_executor_execution_commit_plan_packet_is_not_truth_policy_authority_or_consent": True,
    "commit_plan_packet_readiness_is_metadata_only": True,
    "lock_lease_gate_confirmation_is_metadata_only": True,
    "live_commit_execution_denial_is_metadata_only": True,
    "live_memory_write_denial_is_metadata_only": True,
    "final_commit_plan_hold_points_are_metadata_only": True,
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
    "real_executor_execution_lock_lease_packet_created": False,
    "real_executor_execution_lock_lease_gate_passed": False,
    "real_executor_execution_lock_lease_enabled": False,
    "real_executor_execution_lock_lease_created": False,
    "real_executor_execution_preflight_packet_created": False,
    "real_executor_execution_preflight_gate_passed": False,
    "real_executor_execution_preflight_enabled": False,
    "real_executor_execution_preflight_executed": False,

    "real_lock_acquisition_enabled": False,
    "real_lock_acquired": False,
    "lockfile_creation_enabled": False,
    "lockfile_created": False,
    "lock_lease_renewal_enabled": False,
    "lock_lease_release_enabled": False,
    "real_executor_execution_commit_plan_packet_created": False,
    "real_executor_execution_commit_plan_gate_passed": False,
    "live_commit_execution_enabled": False,
    "live_commit_executed": False,
    "live_commit_apply_enabled": False,
    "live_commit_applied": False,
    "real_executor_execution_commit_plan_enabled": False,
    "real_memory_root_write_enabled": False,
    "live_memory_write_enabled": False,
    "prompt_materialization_enabled": False,
    "live_context_retrieval_enabled": False,
    "action_execution_enabled": False,
    "external_disclosure_enabled": False,
    "external_service_enabled": False,
    "future_real_executor_execution_commit_plan_gate_required": True,
    "future_real_executor_execution_commit_window_packet_required": True,
    "future_real_live_memory_commit_execution_required": True,
    "future_post_execution_audit_required": True,
}
FORBIDDEN_NEXT_STEPS = (
    "preflight_execution", "enabled_preflight", "real_executor_invocation", "enabled_invocation", "real_executor_activation",
    "enabled_activation", "execution_release", "execution_permit", "execution_authorization", "executor_enablement",
    "runtime_flag_flipping", "live_commit_execution", "real_executor_run", "execution_plan_run", "commit_plan_gate_creation",
    "real_lock_acquisition", "lockfile_creation", "real_live_memory_write", "real_live_memory_delete", "real_live_memory_purge",
    "index_mutation", "capsule_persistence", "tomb_completion", "prompt_assembly", "live_context_retrieval",
    "action_execution", "external_disclosure", "external_service_call", "authority_grant",
)
FORBIDDEN_CLAIM_CODES = {
    "real_executor_run_executed": "executor_run_claim",
    "executor_enabled": "executor_enablement_claim",
    "executor_invoked": "executor_invocation_claim",
    "executor_activated": "executor_activation_claim",
    "runtime_enablement_claimed": "runtime_enablement_claim",
    "runtime_flags_flipped": "runtime_flag_flipping_claim",
    "runtime_flag_target_state_active": "runtime_flag_active_state_claim",
    "live_commit_executed": "live_execution_claim",
    "permission_to_execute_now": "executor_permission_claim",
    "real_executor_invocation_claimed": "executor_invocation_claim",
    "execution_hold_points_are_live_execution": "run_hold_point_live_run_claim",
    "operation_bundle_executed": "operation_bundle_execution_claim",
    "receipt_envelope_is_live_receipt": "live_receipt_claim",
    "rollback_readiness_applied": "applied_rollback_claim",
    "rollback_envelope_applied": "applied_rollback_claim",
    "live_memory_write_claimed": "live_write_claim",
    "live_memory_delete_claimed": "live_delete_claim",
    "live_memory_purge_claimed": "live_purge_claim",
    "live_index_mutation_claimed": "index_mutation_claim",
    "capsule_persistence_claimed": "capsule_persistence_claim",
    "tomb_completion_claimed": "tomb_completion_claim",
    "prompt_assembly_claimed": "prompt_materialization",
    "live_context_retrieval_claimed": "live_context_retrieval",
    "action_execution_claimed": "action_execution",
    "external_disclosure_claimed": "external_disclosure",
    "external_service_called": "external_service_call",
    "lockfile_creation_claimed": "lockfile_creation_claim",
    "real_lock_acquisition_claimed": "real_lock_acquisition_claim",
    "real_memory_root_access_claimed": "real_memory_root_access_claim",
    "authority_granted": "authority_smuggling",
    "consent_granted": "consent_smuggling",
    "policy_created": "policy_smuggling",
    "truth_asserted": "truth_smuggling",
    "raw_payload_included": "raw_payload_leakage",
    "private_payload_included": "raw_payload_leakage",
    "media_payload_included": "raw_payload_leakage",
    "secret_payload_included": "raw_payload_leakage",
}
_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class RealExecutorExecutionCommitPlanPacketFinding:
    severity: str
    code: str
    message: str
    candidate_id: str = ""
    record_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealExecutorExecutionCommitPlanPacketPolicy:
    schema_version: str = "real-executor-execution-commit-plan-packet.v1"
    default_deny: bool = True
    metadata_only: bool = True
    allow_mixed_diagnostics: bool = True
    require_scope_alignment: bool = True
    block_forbidden_claims: bool = True
    real_executor_enabled: bool = False
    real_executor_runtime_enablement_enabled: bool = False
    real_executor_enablement_enabled: bool = False
    real_executor_invocation_enabled: bool = False
    real_executor_run_enabled: bool = False
    real_executor_activation_enabled: bool = False
    real_lock_acquisition_enabled: bool = False
    real_lock_acquired: bool = False
    lockfile_creation_enabled: bool = False
    lockfile_created: bool = False
    lock_lease_renewal_enabled: bool = False
    lock_lease_release_enabled: bool = False
    real_executor_execution_commit_plan_packet_created: bool = False
    real_executor_execution_commit_plan_gate_passed: bool = False
    real_executor_execution_commit_plan_enabled: bool = False
    live_commit_execution_enabled: bool = False
    live_commit_executed: bool = False
    live_commit_apply_enabled: bool = False
    live_commit_applied: bool = False
    real_memory_root_access_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealExecutorExecutionCommitPlanPacketCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    operator_scope_keys: tuple[str, ...]
    metadata: Mapping[str, Any]
    claims: Mapping[str, Any]

    @staticmethod
    def from_mapping(payload: Mapping[str, Any]) -> "RealExecutorExecutionCommitPlanPacketCandidate":
        return RealExecutorExecutionCommitPlanPacketCandidate(
            str(payload.get("candidate_id") or ""),
            str(payload.get("record_id") or ""),
            str(payload.get("candidate_type") or ""),
            tuple(str(v) for v in payload.get("operator_scope_keys", ())),
            _as_mapping(payload.get("metadata")),
            _as_mapping(payload.get("real_executor_execution_commit_plan_packet_claims") or payload.get("claims")),
        )

    @property
    def is_noop(self) -> bool:
        return self.candidate_type == "noop_real_executor_execution_commit_plan_packet_candidate"


@dataclass(frozen=True)
class RealExecutorExecutionCommitPlanPacketMetadataRecord:
    record_type: str
    candidate_id: str
    record_id: str
    metadata_digest: str
    metadata_only: bool = True
    authoritative: bool = False
    runtime_enabled: bool = False
    runtime_flag_flipped: bool = False
    executed: bool = False
    permission_granted: bool = False
    active_runtime_state: bool = False
    executor_invoked: bool = False
    live_receipt: bool = False
    rollback_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealExecutorExecutionCommitPlanPacketRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    real_executor_execution_commit_plan_packet_decision: RealExecutorExecutionCommitPlanPacketDecision
    real_executor_execution_lock_lease_gate_digest: str
    real_executor_execution_lock_lease_gate_decision: str
    carried_evidence: Mapping[str, Mapping[str, str]]
    operator_scope_keys: tuple[str, ...]
    commit_plan_packet_readiness_records: tuple[RealExecutorExecutionCommitPlanPacketMetadataRecord, ...]
    lock_lease_gate_confirmation_records: tuple[RealExecutorExecutionCommitPlanPacketMetadataRecord, ...]
    live_commit_execution_denial_records: tuple[RealExecutorExecutionCommitPlanPacketMetadataRecord, ...]
    live_memory_write_denial_records: tuple[RealExecutorExecutionCommitPlanPacketMetadataRecord, ...]
    final_commit_plan_hold_point_records: tuple[RealExecutorExecutionCommitPlanPacketMetadataRecord, ...]
    emergency_stop_confirmation_records: tuple[RealExecutorExecutionCommitPlanPacketMetadataRecord, ...]
    rollback_readiness_records: tuple[RealExecutorExecutionCommitPlanPacketMetadataRecord, ...]
    verification_readiness_records: tuple[RealExecutorExecutionCommitPlanPacketMetadataRecord, ...]
    audit_readiness_records: tuple[RealExecutorExecutionCommitPlanPacketMetadataRecord, ...]
    safe_next_actions: tuple[str, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    real_executor_enabled: bool = False
    real_executor_run_enabled: bool = False
    real_executor_execution_enabled: bool = False
    real_executor_execution_authorized: bool = False
    real_executor_authorization_gate_passed: bool = False
    real_executor_execution_permit_issued: bool = False
    real_executor_execution_permit_gate_passed: bool = False
    real_executor_execution_released: bool = False
    real_executor_execution_release_gate_passed: bool = False
    real_executor_execution_activation_packet_created: bool = False
    real_executor_execution_activation_gate_passed: bool = False
    real_executor_execution_activation_enabled: bool = False
    real_executor_activation_enabled: bool = False
    real_executor_execution_invocation_packet_created: bool = False
    real_executor_execution_invocation_gate_passed: bool = False
    real_executor_execution_invocation_enabled: bool = False
    real_executor_invocation_enabled: bool = False
    real_executor_invoked: bool = False
    real_executor_execution_lock_lease_packet_created: bool = False
    real_executor_execution_commit_plan_packet_passed: bool = False
    real_executor_execution_lock_lease_enabled: bool = False
    real_executor_execution_lock_lease_created: bool = False
    real_executor_execution_preflight_packet_created: bool = False
    real_executor_execution_preflight_gate_passed: bool = False
    real_executor_execution_preflight_enabled: bool = False
    real_executor_execution_preflight_executed: bool = False
    real_lock_acquisition_enabled: bool = False
    real_lock_acquired: bool = False
    lockfile_creation_enabled: bool = False
    lockfile_created: bool = False
    lock_lease_renewal_enabled: bool = False
    lock_lease_release_enabled: bool = False
    real_executor_execution_commit_plan_packet_created: bool = False
    real_executor_execution_commit_plan_gate_passed: bool = False
    real_executor_execution_commit_plan_enabled: bool = False
    live_commit_execution_enabled: bool = False
    live_commit_executed: bool = False
    live_commit_apply_enabled: bool = False
    live_commit_applied: bool = False
    real_memory_root_write_enabled: bool = False
    live_memory_write_enabled: bool = False
    prompt_materialization_enabled: bool = False
    live_context_retrieval_enabled: bool = False
    action_execution_enabled: bool = False
    external_disclosure_enabled: bool = False
    external_service_enabled: bool = False
    future_real_executor_execution_commit_plan_gate_required: bool = True
    future_real_executor_execution_commit_window_packet_required: bool = True
    future_real_live_memory_commit_execution_required: bool = True
    future_post_execution_audit_required: bool = True
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(INVARIANTS)
        return data

    def with_digest(self) -> "RealExecutorExecutionCommitPlanPacketRecord":
        return replace(self, digest=_digest({k: v for k, v in self.to_dict().items() if k != "digest"}))


@dataclass(frozen=True)
class RealExecutorExecutionCommitPlanPacketPacket:
    schema_version: str
    records: tuple[RealExecutorExecutionCommitPlanPacketRecord, ...]
    metadata_only: bool = True
    default_deny: bool = True
    not_permission_to_execute: bool = True
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "records": [record.to_dict() for record in self.records],
            "metadata_only": self.metadata_only,
            "default_deny": self.default_deny,
            "not_permission_to_execute": self.not_permission_to_execute,
            "digest": self.digest,
        }

    def with_digest(self) -> "RealExecutorExecutionCommitPlanPacketPacket":
        return replace(self, digest=_digest({k: v for k, v in self.to_dict().items() if k != "digest"}))


@dataclass(frozen=True)
class RealExecutorExecutionCommitPlanPacketReport:
    status: RealExecutorExecutionCommitPlanPacketStatus
    findings: tuple[RealExecutorExecutionCommitPlanPacketFinding, ...]
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
class RealExecutorExecutionCommitPlanPacketResult:
    status: RealExecutorExecutionCommitPlanPacketStatus
    packet: RealExecutorExecutionCommitPlanPacketPacket | None
    report: RealExecutorExecutionCommitPlanPacketReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "packet": self.packet.to_dict() if self.packet else None,
            "report": self.report.to_dict(),
            "digest": self.digest,
        }


def build_default_policy() -> RealExecutorExecutionCommitPlanPacketPolicy:
    return RealExecutorExecutionCommitPlanPacketPolicy()


def validate_policy(policy: RealExecutorExecutionCommitPlanPacketPolicy | None = None) -> dict[str, Any]:
    active = policy or build_default_policy()
    findings: list[RealExecutorExecutionCommitPlanPacketFinding] = []
    if not active.default_deny or not active.metadata_only:
        findings.append(RealExecutorExecutionCommitPlanPacketFinding("error", "policy_not_metadata_only_default_deny", "policy must remain metadata-only and default-deny"))
    for name in (
        "real_executor_enabled",
        "real_executor_runtime_enablement_enabled",
        "real_executor_enablement_enabled",
        "real_executor_invocation_enabled",
        "real_executor_run_enabled",
        "real_executor_activation_enabled",
        "real_lock_acquisition_enabled",
        "lockfile_creation_enabled",
        "real_memory_root_access_enabled",
    ):
        if bool(getattr(active, name)):
            findings.append(RealExecutorExecutionCommitPlanPacketFinding("error", name, f"{name} must remain false"))
    return {"status": "valid" if not findings else "invalid", "policy": active.to_dict(), "findings": [f.to_dict() for f in findings]}


def _blocked(code: str, findings: Sequence[RealExecutorExecutionCommitPlanPacketFinding] = ()) -> RealExecutorExecutionCommitPlanPacketResult:
    all_findings = tuple(findings) or (RealExecutorExecutionCommitPlanPacketFinding("error", code, code),)
    report = RealExecutorExecutionCommitPlanPacketReport("real_executor_execution_commit_plan_packet_blocked", all_findings, {"blocked": 1})
    report = replace(report, digest=_digest(report.to_dict()))
    return RealExecutorExecutionCommitPlanPacketResult("real_executor_execution_commit_plan_packet_blocked", None, report, _digest(report.to_dict()))


def _metadata_record(kind: str, candidate: RealExecutorExecutionCommitPlanPacketCandidate, metadata: Mapping[str, Any]) -> RealExecutorExecutionCommitPlanPacketMetadataRecord:
    return RealExecutorExecutionCommitPlanPacketMetadataRecord(kind, candidate.candidate_id, candidate.record_id, _digest(dict(metadata)))


def _valid_candidate(candidate: RealExecutorExecutionCommitPlanPacketCandidate) -> bool:
    return bool(_ID_RE.match(candidate.candidate_id)) and bool(_ID_RE.match(candidate.record_id)) and candidate.candidate_type in REAL_EXECUTOR_EXECUTION_COMMIT_PLAN_PACKET_CANDIDATE_TYPES


def _lock_lease_gate_and_record(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]] | RealExecutorExecutionCommitPlanPacketResult:
    packet = _as_mapping(payload.get("real_executor_execution_lock_lease_gate"))
    if not packet:
        return _blocked("missing_real_executor_execution_lock_lease_gate")
    records = packet.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records:
        return _blocked("invalid_real_executor_execution_lock_lease_gate")
    record = _as_mapping(records[0])
    if not str(packet.get("digest") or "") or not str(record.get("digest") or ""):
        return _blocked("invalid_real_executor_execution_lock_lease_gate")
    return packet, record


def _candidate_list(payload: Mapping[str, Any]) -> Sequence[Any] | RealExecutorExecutionCommitPlanPacketResult:
    candidates = payload.get("real_executor_execution_commit_plan_packet_candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)) or not candidates:
        return _blocked("missing_real_executor_execution_commit_plan_packet_candidate")
    return candidates


def _check_required_metadata(raw: Mapping[str, Any], candidate: RealExecutorExecutionCommitPlanPacketCandidate) -> RealExecutorExecutionCommitPlanPacketResult | None:
    if candidate.is_noop:
        return None
    for field in NON_NOOP_METADATA_FIELDS:
        if not isinstance(raw.get(field), Mapping) or not raw.get(field):
            return _blocked(f"missing_{field}", [RealExecutorExecutionCommitPlanPacketFinding("error", f"missing_{field}", f"missing required non-noop metadata: {field}", candidate.candidate_id, candidate.record_id)])
    return None


def _check_scope(packet_record: Mapping[str, Any], candidate: RealExecutorExecutionCommitPlanPacketCandidate, policy: RealExecutorExecutionCommitPlanPacketPolicy) -> RealExecutorExecutionCommitPlanPacketResult | None:
    if not policy.require_scope_alignment or candidate.candidate_type == "mixed_real_executor_execution_commit_plan_packet_candidate":
        return None
    upstream = tuple(str(v) for v in packet_record.get("operator_scope_keys", ()))
    if upstream and candidate.operator_scope_keys != upstream:
        return _blocked("scope_mismatch", [RealExecutorExecutionCommitPlanPacketFinding("error", "scope_mismatch", "real executor execution commit plan packet candidate scope does not align with lock lease gate evidence", candidate.candidate_id, candidate.record_id)])
    return None


def _check_evidence(raw: Mapping[str, Any], packet: Mapping[str, Any], record: Mapping[str, Any], candidate: RealExecutorExecutionCommitPlanPacketCandidate) -> RealExecutorExecutionCommitPlanPacketResult | None:
    packet_decision = str(record.get("real_executor_execution_lock_lease_gate_decision") or "")
    if packet_decision not in READY_REAL_EXECUTOR_EXECUTION_LOCK_LEASE_GATE_DECISIONS:
        return _blocked("real_executor_execution_lock_lease_gate_not_ready", [RealExecutorExecutionCommitPlanPacketFinding("error", "real_executor_execution_lock_lease_gate_not_ready", "real executor execution lock lease gate is not ready by default", candidate.candidate_id, candidate.record_id)])
    if str(raw.get("claimed_real_executor_execution_lock_lease_gate_digest") or "") != str(packet.get("digest") or ""):
        return _blocked("real_executor_execution_lock_lease_gate_digest_mismatch", [RealExecutorExecutionCommitPlanPacketFinding("error", "real_executor_execution_lock_lease_gate_digest_mismatch", "real executor execution lock lease gate digest mismatch", candidate.candidate_id, candidate.record_id)])
    if str(raw.get("claimed_real_executor_execution_lock_lease_gate_decision") or "") != packet_decision:
        return _blocked("real_executor_execution_lock_lease_gate_decision_mismatch", [RealExecutorExecutionCommitPlanPacketFinding("error", "real_executor_execution_lock_lease_gate_decision_mismatch", "real executor execution lock lease gate decision mismatch", candidate.candidate_id, candidate.record_id)])
    carried_map = _as_mapping(record.get("carried_evidence"))
    for label, digest_field, decision_field in CARRIED_EVIDENCE_FIELDS:
        carried_record = _as_mapping(carried_map.get(label))
        actual_digest = str(record.get(digest_field) or carried_record.get("digest") or "")
        actual_decision = str(record.get(decision_field) or carried_record.get("decision") or "")
        claimed_digest = str(raw.get(f"claimed_{digest_field}") or "")
        claimed_decision = str(raw.get(f"claimed_{decision_field}") or "")
        if actual_digest and claimed_digest != actual_digest:
            return _blocked(f"{label}_digest_mismatch", [RealExecutorExecutionCommitPlanPacketFinding("error", f"{label}_digest_mismatch", f"{label} digest mismatch", candidate.candidate_id, candidate.record_id)])
        if actual_decision and claimed_decision != actual_decision:
            return _blocked(f"{label}_decision_mismatch", [RealExecutorExecutionCommitPlanPacketFinding("error", f"{label}_decision_mismatch", f"{label} decision mismatch", candidate.candidate_id, candidate.record_id)])
    return None


def _claims_findings(candidate: RealExecutorExecutionCommitPlanPacketCandidate) -> tuple[RealExecutorExecutionCommitPlanPacketFinding, ...]:
    return tuple(
        RealExecutorExecutionCommitPlanPacketFinding("error", code, f"forbidden real executor execution commit plan packet claim blocked: {key}", candidate.candidate_id, candidate.record_id)
        for key, code in FORBIDDEN_CLAIM_CODES.items()
        if candidate.claims.get(key) is True
    )


def _decision(candidate: RealExecutorExecutionCommitPlanPacketCandidate, findings: Sequence[RealExecutorExecutionCommitPlanPacketFinding]) -> RealExecutorExecutionCommitPlanPacketDecision:
    if candidate.is_noop:
        return "real_executor_execution_commit_plan_packet_noop"
    if candidate.candidate_type == "operator_review_real_executor_execution_commit_plan_packet_candidate":
        return "real_executor_execution_commit_plan_packet_deferred_for_operator_review"
    if any(f.severity == "warning" for f in findings) or candidate.candidate_type == "mixed_real_executor_execution_commit_plan_packet_candidate":
        return "real_executor_execution_commit_plan_packet_ready_with_warnings"
    return "real_executor_execution_commit_plan_packet_ready_for_later_real_executor_execution_commit_plan_gate"


def _safe_actions(decision: RealExecutorExecutionCommitPlanPacketDecision) -> tuple[str, ...]:
    if decision == "real_executor_execution_commit_plan_packet_noop":
        return ("record_noop_metadata", "continue_review_without_executor_authority")
    if decision == "real_executor_execution_commit_plan_packet_deferred_for_operator_review":
        return ("operator_review_metadata", "resolve_without_overriding_hard_blockers")
    return ("review_real_executor_execution_commit_plan_packet_metadata", "prepare_separate_future_real_executor_execution_commit_plan_gate_request")


def _carried_evidence(record: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    carried: dict[str, dict[str, str]] = {}
    carried_map = _as_mapping(record.get("carried_evidence"))
    for label, digest_field, decision_field in CARRIED_EVIDENCE_FIELDS:
        carried_record = _as_mapping(carried_map.get(label))
        carried[label] = {"digest": str(record.get(digest_field) or carried_record.get("digest") or ""), "decision": str(record.get(decision_field) or carried_record.get("decision") or "")}
    return carried


def evaluate_real_executor_execution_commit_plan_packet(payload: Mapping[str, Any], policy: RealExecutorExecutionCommitPlanPacketPolicy | None = None) -> RealExecutorExecutionCommitPlanPacketResult:
    active_policy = policy or build_default_policy()
    policy_validation = validate_policy(active_policy)
    if policy_validation["status"] != "valid":
        return _blocked("invalid_policy", tuple(RealExecutorExecutionCommitPlanPacketFinding(**f) for f in policy_validation["findings"]))
    pair = _lock_lease_gate_and_record(payload)
    if isinstance(pair, RealExecutorExecutionCommitPlanPacketResult):
        return pair
    lock_lease_gate, packet_record = pair
    candidates_raw = _candidate_list(payload)
    if isinstance(candidates_raw, RealExecutorExecutionCommitPlanPacketResult):
        return candidates_raw
    findings: list[RealExecutorExecutionCommitPlanPacketFinding] = []
    records: list[RealExecutorExecutionCommitPlanPacketRecord] = []
    try:
        for raw_value in candidates_raw:
            raw = _as_mapping(raw_value)
            candidate = RealExecutorExecutionCommitPlanPacketCandidate.from_mapping(raw)
            if not _valid_candidate(candidate):
                return _blocked("invalid_real_executor_execution_commit_plan_packet_candidate", [RealExecutorExecutionCommitPlanPacketFinding("error", "invalid_real_executor_execution_commit_plan_packet_candidate", "invalid real executor execution commit plan packet candidate", candidate.candidate_id, candidate.record_id)])
            claim_findings = _claims_findings(candidate) if active_policy.block_forbidden_claims else ()
            if claim_findings:
                return _blocked(claim_findings[0].code, claim_findings)
            for check in (
                _check_required_metadata(raw, candidate),
                _check_scope(packet_record, candidate, active_policy),
                _check_evidence(raw, lock_lease_gate, packet_record, candidate),
            ):
                if check is not None:
                    return check
            if candidate.candidate_type == "mixed_real_executor_execution_commit_plan_packet_candidate" and candidate.metadata.get("diagnostic_warning") is True:
                findings.append(RealExecutorExecutionCommitPlanPacketFinding("warning", "mixed_scope_diagnostic", "mixed real executor execution commit plan packet diagnostics allowed as warnings only", candidate.candidate_id, candidate.record_id))
            decision = _decision(candidate, findings)
            records.append(RealExecutorExecutionCommitPlanPacketRecord(
                candidate.candidate_id,
                candidate.record_id,
                candidate.candidate_type,
                decision,
                str(lock_lease_gate.get("digest") or ""),
                str(packet_record.get("real_executor_execution_lock_lease_gate_decision") or ""),
                _carried_evidence(packet_record),
                candidate.operator_scope_keys,
                (_metadata_record("commit_plan_packet_readiness", candidate, _as_mapping(raw.get("commit_plan_packet_readiness_metadata") or raw.get("metadata"))),),
                (_metadata_record("lock_lease_gate_confirmation", candidate, _as_mapping(raw.get("lock_lease_gate_confirmation_metadata") or raw.get("real_executor_execution_commit_plan_packet_prerequisite_metadata"))),),
                (_metadata_record("live_commit_execution_denial", candidate, _as_mapping(raw.get("live_commit_execution_denial_metadata") or raw.get("real_executor_execution_commit_plan_packet_hold_point_metadata"))),),
                (_metadata_record("live_memory_write_denial", candidate, _as_mapping(raw.get("live_memory_write_denial_metadata"))),),
                (_metadata_record("final_commit_plan_hold_point", candidate, _as_mapping(raw.get("final_commit_plan_hold_point_metadata") or raw.get("runtime_guard_verification_expectation_metadata"))),),
                (_metadata_record("emergency_stop_confirmation", candidate, _as_mapping(raw.get("emergency_stop_confirmation_metadata"))),),
                (_metadata_record("rollback_readiness", candidate, _as_mapping(raw.get("rollback_readiness_metadata"))),),
                (_metadata_record("verification_readiness", candidate, _as_mapping(raw.get("verification_readiness_metadata"))),),
                (_metadata_record("audit_readiness", candidate, _as_mapping(raw.get("audit_readiness_metadata"))),),
                _safe_actions(decision),
            ).with_digest())
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for f in findings if f.severity == "warning")}
        for record in records:
            counts[record.real_executor_execution_commit_plan_packet_decision] = counts.get(record.real_executor_execution_commit_plan_packet_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {r.real_executor_execution_commit_plan_packet_decision for r in records}
        if counts["warning_count"] or "real_executor_execution_commit_plan_packet_ready_with_warnings" in decisions:
            status: RealExecutorExecutionCommitPlanPacketStatus = "real_executor_execution_commit_plan_packet_ready_with_warnings"
        elif decisions <= {"real_executor_execution_commit_plan_packet_noop"}:
            status = "real_executor_execution_commit_plan_packet_noop"
        elif decisions <= {"real_executor_execution_commit_plan_packet_deferred_for_operator_review"}:
            status = "real_executor_execution_commit_plan_packet_deferred_for_operator_review"
        else:
            status = "real_executor_execution_commit_plan_packet_ready"
        packet = RealExecutorExecutionCommitPlanPacketPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = RealExecutorExecutionCommitPlanPacketReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return RealExecutorExecutionCommitPlanPacketResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("failed", [RealExecutorExecutionCommitPlanPacketFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: RealExecutorExecutionCommitPlanPacketPolicy | None = None) -> RealExecutorExecutionCommitPlanPacketResult:
    return evaluate_real_executor_execution_commit_plan_packet(payload, policy)


__all__ = [
    "CARRIED_EVIDENCE_FIELDS",
    "FAIL_STATUSES",
    "FORBIDDEN_NEXT_STEPS",
    "INVARIANTS",
    "NON_NOOP_METADATA_FIELDS",
    "READY_REAL_EXECUTOR_EXECUTION_LOCK_LEASE_GATE_DECISIONS",
    "REAL_EXECUTOR_EXECUTION_COMMIT_PLAN_PACKET_CANDIDATE_TYPES",
    "RealExecutorExecutionCommitPlanPacketCandidate",
    "RealExecutorExecutionCommitPlanPacketFinding",
    "RealExecutorExecutionCommitPlanPacketMetadataRecord",
    "RealExecutorExecutionCommitPlanPacketPacket",
    "RealExecutorExecutionCommitPlanPacketPolicy",
    "RealExecutorExecutionCommitPlanPacketRecord",
    "RealExecutorExecutionCommitPlanPacketReport",
    "RealExecutorExecutionCommitPlanPacketResult",
    "build_default_policy",
    "evaluate_packet",
    "evaluate_real_executor_execution_commit_plan_packet",
    "validate_policy",
]
