
"""Deterministic metadata-only Final Live Memory Commit Review Gate.

The gate consumes a supplied Real Live Memory Commit Adapter Readiness Envelope
and explicit final-review-gate candidates.  It produces only reviewable metadata
for a later Real Memory Root Admission Gate rung.  It never executes, approves,
applies, admits, enables, invokes, locks, writes, discloses, or grants runtime
authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Mapping, Sequence

FinalLiveMemoryCommitReviewGateStatus = Literal[
    "final_live_memory_commit_review_gate_ready",
    "final_live_memory_commit_review_gate_ready_with_warnings",
    "final_live_memory_commit_review_gate_deferred_for_operator_review",
    "final_live_memory_commit_review_gate_rejected",
    "final_live_memory_commit_review_gate_blocked",
    "final_live_memory_commit_review_gate_noop",
    "final_live_memory_commit_review_gate_invalid",
    "final_live_memory_commit_review_gate_failed",
]
FinalLiveMemoryCommitReviewGateDecision = Literal[
    "final_live_memory_commit_review_gate_ready_for_later_real_memory_root_admission_gate",
    "final_live_memory_commit_review_gate_ready_with_warnings",
    "final_live_memory_commit_review_gate_deferred_for_operator_review",
    "final_live_memory_commit_review_gate_rejected",
    "final_live_memory_commit_review_gate_blocked",
    "final_live_memory_commit_review_gate_noop",
]

FINAL_LIVE_MEMORY_COMMIT_REVIEW_GATE_CANDIDATE_TYPES = frozenset({
    "ai_capsule_final_live_memory_commit_review_gate_candidate",
    "human_summary_final_live_memory_commit_review_gate_candidate",
    "dual_capsule_final_live_memory_commit_review_gate_candidate",
    "protect_receipt_final_live_memory_commit_review_gate_candidate",
    "merge_receipt_final_live_memory_commit_review_gate_candidate",
    "tomb_archive_final_live_memory_commit_review_gate_candidate",
    "tomb_deferred_final_live_memory_commit_review_gate_candidate",
    "operator_review_final_live_memory_commit_review_gate_candidate",
    "noop_final_live_memory_commit_review_gate_candidate",
    "mixed_final_live_memory_commit_review_gate_candidate",
})
READY_REAL_LIVE_MEMORY_COMMIT_ADAPTER_READINESS_ENVELOPE_DECISIONS = frozenset({
    "real_live_memory_commit_adapter_readiness_envelope_ready_for_later_final_live_memory_commit_review_gate",
    "real_live_memory_commit_adapter_readiness_envelope_ready_with_warnings",
    "real_live_memory_commit_adapter_readiness_envelope_noop",
})
FAIL_STATUSES = {
    "final_live_memory_commit_review_gate_blocked",
    "final_live_memory_commit_review_gate_invalid",
    "final_live_memory_commit_review_gate_failed",
}

CARRIED_EVIDENCE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("real_live_memory_commit_adapter_readiness_gate", "real_live_memory_commit_adapter_readiness_gate_digest", "real_live_memory_commit_adapter_readiness_gate_decision"),
    ("real_live_memory_commit_adapter_admission_packet", "real_live_memory_commit_adapter_admission_packet_digest", "real_live_memory_commit_adapter_admission_packet_decision"),
    ("real_live_memory_commit_adapter_admission_gate", "real_live_memory_commit_adapter_admission_gate_digest", "real_live_memory_commit_adapter_admission_gate_decision"),
    ("real_live_memory_commit_execution_packet", "real_live_memory_commit_execution_packet_digest", "real_live_memory_commit_execution_packet_decision"),
    ("real_live_memory_commit_execution_gate", "real_live_memory_commit_execution_gate_digest", "real_live_memory_commit_execution_gate_decision"),
    ("real_executor_execution_commit_window_packet", "real_executor_execution_commit_window_packet_digest", "real_executor_execution_commit_window_packet_decision"),
    ("real_executor_execution_commit_plan_gate", "real_executor_execution_commit_plan_gate_digest", "real_executor_execution_commit_plan_gate_decision"),
    ("real_executor_execution_commit_plan_packet", "real_executor_execution_commit_plan_packet_digest", "real_executor_execution_commit_plan_packet_decision"),
    ("real_executor_execution_lock_lease_gate", "real_executor_execution_lock_lease_gate_digest", "real_executor_execution_lock_lease_gate_decision"),
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
    ("real_executor_runtime_gate", "runtime_gate_digest", "runtime_gate_decision"),
    ("real_executor_runtime_enablement_packet", "runtime_enablement_packet_digest", "runtime_enablement_packet_decision"),
    ("live_commit_execution_packet", "live_commit_execution_packet_digest", "live_commit_execution_packet_decision"),
    ("future_live_memory_commit_execution_gate", "future_execution_gate_digest", "future_execution_gate_decision"),
    ("constrained_executor_enablement_path_packet", "constrained_enablement_path_digest", "constrained_enablement_path_decision"),
    ("real_live_memory_commit_executor_enablement_gate", "executor_enablement_gate_digest", "executor_enablement_gate_decision"),
    ("real_live_memory_commit_executor_implementation_skeleton", "executor_skeleton_digest", "executor_skeleton_decision"),
    ("live_executor_invocation_harness", "invocation_harness_digest", "invocation_harness_decision"),
    ("live_executor_activation_record", "activation_record_digest", "activation_record_decision"),
    ("live_executor_preflight_packet", "live_executor_preflight_packet_digest", "live_executor_preflight_packet_decision"),
    ("live_executor_lock_lease_gate", "live_executor_lock_lease_gate_digest", "live_executor_lock_lease_gate_decision"),
    ("real_live_memory_commit_executor_plan_packet", "executor_plan_packet_digest", "executor_plan_packet_decision"),
    ("explicit_live_memory_runtime_execution_gate", "runtime_authorization_packet_digest", "runtime_authorization_packet_decision"),
    ("final_live_memory_commit_review_gate", "final_review_digest", "final_review_decision"),
    ("real_memory_root_admission_gate", "real_root_admission_digest", "real_root_admission_decision"),
    ("sandboxed_live_memory_commit_adapter", "sandbox_commit_digest", "sandbox_commit_decision"),
)

NON_NOOP_METADATA_FIELDS = (
    "final_review_gate_readiness_metadata",
    "adapter_readiness_envelope_confirmation_metadata",
    "adapter_readiness_gate_confirmation_metadata",
    "adapter_admission_packet_confirmation_metadata",
    "adapter_admission_gate_confirmation_metadata",
    "live_memory_commit_execution_packet_confirmation_metadata",
    "live_memory_commit_execution_gate_confirmation_metadata",
    "commit_window_packet_confirmation_metadata",
    "commit_plan_gate_confirmation_metadata",
    "commit_plan_packet_confirmation_metadata",
    "lock_lease_gate_confirmation_metadata",
    "live_commit_execution_denial_metadata",
    "live_memory_write_denial_metadata",
    "real_memory_root_admission_deferral_metadata",
    "emergency_stop_confirmation_metadata",
    "rollback_readiness_metadata",
    "verification_readiness_metadata",
    "audit_readiness_metadata",
)

INVARIANTS: dict[str, bool] = {
    "final_review_gate_is_not_live_commit_execution": True,
    "final_review_gate_does_not_approve_live_execution": True,
    "final_review_gate_does_not_execute_a_commit": True,
    "final_review_gate_does_not_apply_a_commit": True,
    "final_review_gate_does_not_write_live_memory": True,
    "final_review_gate_is_not_enabled_commit_window_authority": True,
    "final_review_gate_does_not_open_a_live_commit_window": True,
    "final_review_gate_does_not_execute_a_commit_window": True,
    "final_review_gate_does_not_create_a_live_execution_adapter": True,
    "final_review_gate_does_not_create_a_live_adapter": True,
    "final_review_gate_does_not_admit_a_live_adapter": True,
    "final_review_gate_does_not_create_a_real_memory_root_admission_gate": True,
    "final_review_gate_does_not_admit_real_memory_roots": True,
    "final_review_gate_is_not_lock_acquisition": True,
    "final_review_gate_does_not_acquire_locks": True,
    "final_review_gate_does_not_create_real_lock_leases": True,
    "final_review_gate_does_not_create_lockfiles": True,
    "final_review_gate_is_not_preflight_execution": True,
    "final_review_gate_does_not_execute_preflight": True,
    "final_review_gate_is_not_executor_invocation": True,
    "final_review_gate_does_not_invoke_executor": True,
    "final_review_gate_is_not_executor_activation": True,
    "final_review_gate_does_not_activate_executor": True,
    "final_review_gate_is_not_execution_release": True,
    "final_review_gate_does_not_release_execution": True,
    "final_review_gate_is_not_execution_permit": True,
    "final_review_gate_does_not_issue_permit": True,
    "final_review_gate_is_not_execution_authorization": True,
    "final_review_gate_is_not_permission_to_execute": True,
    "final_review_gate_is_not_executor_execution": True,
    "final_review_gate_is_not_executor_run": True,
    "final_review_gate_is_not_runtime_enablement": True,
    "final_review_gate_is_not_runtime_flag_flip": True,
    "final_review_gate_is_not_enabled_executor": True,
    "final_review_gate_is_not_executor_enablement": True,
    "final_review_gate_is_not_memory_write_deletion_purge": True,
    "final_review_gate_is_not_index_mutation": True,
    "final_review_gate_is_not_capsule_persistence": True,
    "final_review_gate_is_not_tomb_completion": True,
    "final_review_gate_is_not_prompt_assembly": True,
    "final_review_gate_is_not_live_context_retrieval": True,
    "final_review_gate_is_not_action_execution": True,
    "final_review_gate_is_not_external_disclosure": True,
    "final_review_gate_is_not_truth_policy_authority_or_consent": True,
    "final_review_gate_readiness_is_metadata_only": True,
    "adapter_readiness_envelope_confirmation_is_metadata_only": True,
    "adapter_readiness_gate_confirmation_is_metadata_only": True,
    "adapter_admission_packet_confirmation_is_metadata_only": True,
    "adapter_admission_gate_confirmation_is_metadata_only": True,
    "live_memory_commit_execution_packet_confirmation_is_metadata_only": True,
    "live_memory_commit_execution_gate_confirmation_is_metadata_only": True,
    "commit_window_packet_confirmation_is_metadata_only": True,
    "commit_plan_gate_confirmation_is_metadata_only": True,
    "commit_plan_packet_confirmation_is_metadata_only": True,
    "lock_lease_gate_confirmation_is_metadata_only": True,
    "live_commit_execution_denial_is_metadata_only": True,
    "live_memory_write_denial_is_metadata_only": True,
    "real_memory_root_admission_deferral_is_metadata_only": True,
    "emergency_stop_confirmation_is_metadata_only": True,
    "rollback_readiness_is_metadata_only": True,
    "verification_readiness_is_metadata_only": True,
    "audit_readiness_is_metadata_only": True,
}

FORBIDDEN_CLAIMS = {
    "real_executor_enabled", "real_executor_run_enabled", "real_executor_execution_enabled",
    "real_executor_execution_authorized", "real_executor_authorization_gate_passed",
    "real_executor_execution_permit_issued", "real_executor_execution_permit_gate_passed",
    "real_executor_execution_released", "real_executor_execution_release_gate_passed",
    "real_executor_execution_activation_packet_created", "real_executor_execution_activation_gate_passed",
    "real_executor_execution_activation_enabled", "real_executor_activation_enabled",
    "real_executor_execution_invocation_packet_created", "real_executor_execution_invocation_gate_passed",
    "real_executor_execution_invocation_enabled", "real_executor_invocation_enabled", "real_executor_invoked",
    "real_executor_execution_preflight_packet_created", "real_executor_execution_preflight_gate_passed",
    "real_executor_execution_preflight_enabled", "real_executor_execution_preflight_executed",
    "real_executor_execution_lock_lease_packet_created", "real_executor_execution_lock_lease_gate_passed",
    "real_executor_execution_lock_lease_enabled", "real_executor_execution_lock_lease_created",
    "real_lock_acquisition_enabled", "real_lock_acquired", "lockfile_creation_enabled", "lockfile_created",
    "lock_lease_renewal_enabled", "lock_lease_release_enabled",
    "real_executor_execution_commit_plan_packet_created", "real_executor_execution_commit_plan_gate_passed",
    "real_executor_execution_commit_plan_enabled", "real_executor_execution_commit_window_packet_created",
    "real_executor_execution_commit_window_gate_passed", "real_executor_execution_commit_window_enabled",
    "commit_window_authority_enabled", "real_live_memory_commit_execution_gate_passed",
    "real_live_memory_commit_execution_enabled", "real_live_memory_commit_execution_packet_created",
    "live_execution_adapter_created", "live_adapter_created", "live_adapter_admitted",
    "live_adapter_admission_gate_passed", "live_adapter_admission_enabled",
    "real_live_memory_commit_adapter_admission_gate_passed", "real_live_memory_commit_adapter_admission_enabled",
    "real_live_memory_commit_adapter_admission_packet_created", "real_live_memory_commit_adapter_readiness_gate_passed",
    "real_live_memory_commit_adapter_readiness_enabled", "real_live_memory_commit_adapter_readiness_envelope_created",
    "final_live_memory_commit_review_gate_passed", "final_live_memory_commit_review_enabled",
    "real_memory_root_admission_gate_passed", "real_memory_root_admission_enabled", "real_memory_root_admitted",
    "live_commit_execution_enabled", "live_commit_executed", "live_commit_apply_enabled", "live_commit_applied",
    "real_memory_root_write_enabled", "live_memory_write_enabled", "prompt_materialization_enabled",
    "live_context_retrieval_enabled", "action_execution_enabled", "external_disclosure_enabled", "external_service_enabled",
}
FALSE_FLAGS = {name: False for name in sorted(FORBIDDEN_CLAIMS)}
FUTURE_FLAGS = {
    "future_real_memory_root_admission_gate_required": True,
    "future_real_live_memory_commit_execution_required": True,
    "future_post_execution_audit_required": True,
}

SAFE_NEXT_ACTIONS = (
    "review_final_live_memory_commit_review_gate_metadata",
    "prepare_later_real_memory_root_admission_gate_metadata_request",
    "sustain_default_deny",
)
FORBIDDEN_NEXT_STEPS = tuple(sorted(FORBIDDEN_CLAIMS | {
    "execute_final_review_gate", "treat_final_review_gate_as_permission_to_execute",
    "create_real_memory_root_admission_gate_now", "admit_real_memory_root_now",
}))

@dataclass(frozen=True)
class FinalLiveMemoryCommitReviewGateFinding:
    severity: str
    code: str
    message: str
    candidate_id: str = ""
    record_id: str = ""
    def to_dict(self) -> dict[str, str]:
        return asdict(self)

@dataclass(frozen=True)
class FinalLiveMemoryCommitReviewGatePolicy:
    schema_version: str = "final-live-memory-commit-review-gate/v1"
    metadata_only: bool = True
    default_deny: bool = True
    require_scope_alignment: bool = True
    allow_mixed_scope_diagnostic_packet: bool = True
    real_executor_enabled: bool = False
    real_lock_acquisition_enabled: bool = False
    lockfile_creation_enabled: bool = False
    real_memory_root_admission_enabled: bool = False
    live_memory_write_enabled: bool = False
    external_disclosure_enabled: bool = False
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class FinalLiveMemoryCommitReviewGateCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    operator_scope_keys: tuple[str, ...]
    is_noop: bool
    metadata: Mapping[str, Any]

@dataclass(frozen=True)
class FinalLiveMemoryCommitReviewGateMetadataRecord:
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
class FinalLiveMemoryCommitReviewGateRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    final_live_memory_commit_review_gate_decision: FinalLiveMemoryCommitReviewGateDecision
    real_live_memory_commit_adapter_readiness_envelope_digest: str
    real_live_memory_commit_adapter_readiness_envelope_decision: str
    real_live_memory_commit_adapter_readiness_gate_digest: str
    real_live_memory_commit_adapter_readiness_gate_decision: str
    real_live_memory_commit_adapter_admission_packet_digest: str
    real_live_memory_commit_adapter_admission_packet_decision: str
    real_live_memory_commit_adapter_admission_gate_digest: str
    real_live_memory_commit_adapter_admission_gate_decision: str
    real_live_memory_commit_execution_packet_digest: str
    real_live_memory_commit_execution_packet_decision: str
    real_live_memory_commit_execution_gate_digest: str
    real_live_memory_commit_execution_gate_decision: str
    real_executor_execution_commit_window_packet_digest: str
    real_executor_execution_commit_window_packet_decision: str
    real_executor_execution_commit_plan_gate_digest: str
    real_executor_execution_commit_plan_gate_decision: str
    real_executor_execution_commit_plan_packet_digest: str
    real_executor_execution_commit_plan_packet_decision: str
    real_executor_execution_lock_lease_gate_digest: str
    real_executor_execution_lock_lease_gate_decision: str
    carried_evidence: Mapping[str, Mapping[str, str]]
    operator_scope_keys: tuple[str, ...]
    final_review_gate_readiness_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    adapter_readiness_envelope_confirmation_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    adapter_readiness_gate_confirmation_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    adapter_admission_packet_confirmation_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    adapter_admission_gate_confirmation_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    live_memory_commit_execution_packet_confirmation_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    live_memory_commit_execution_gate_confirmation_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    commit_window_packet_confirmation_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    commit_plan_gate_confirmation_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    commit_plan_packet_confirmation_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    lock_lease_gate_confirmation_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    live_commit_execution_denial_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    live_memory_write_denial_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    real_memory_root_admission_deferral_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    emergency_stop_confirmation_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    rollback_readiness_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    verification_readiness_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    audit_readiness_records: tuple[FinalLiveMemoryCommitReviewGateMetadataRecord, ...]
    safe_next_actions: tuple[str, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(INVARIANTS)
        data.update(FALSE_FLAGS)
        data.update(FUTURE_FLAGS)
        return data
    def with_digest(self) -> "FinalLiveMemoryCommitReviewGateRecord":
        return replace(self, digest=_digest({k: v for k, v in self.to_dict().items() if k != "digest"}))

@dataclass(frozen=True)
class FinalLiveMemoryCommitReviewGate:
    schema_version: str
    records: tuple[FinalLiveMemoryCommitReviewGateRecord, ...]
    metadata_only: bool = True
    default_deny: bool = True
    not_permission_to_execute: bool = True
    digest: str = ""
    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "records": [r.to_dict() for r in self.records], "metadata_only": self.metadata_only, "default_deny": self.default_deny, "not_permission_to_execute": self.not_permission_to_execute, "digest": self.digest}
    def with_digest(self) -> "FinalLiveMemoryCommitReviewGate":
        return replace(self, digest=_digest({k: v for k, v in self.to_dict().items() if k != "digest"}))

@dataclass(frozen=True)
class FinalLiveMemoryCommitReviewGateReport:
    status: FinalLiveMemoryCommitReviewGateStatus
    findings: tuple[FinalLiveMemoryCommitReviewGateFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""
    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [f.to_dict() for f in self.findings], "summary_counts": dict(self.summary_counts), "digest": self.digest}

@dataclass(frozen=True)
class FinalLiveMemoryCommitReviewGateResult:
    status: FinalLiveMemoryCommitReviewGateStatus
    gate: FinalLiveMemoryCommitReviewGate | None
    report: FinalLiveMemoryCommitReviewGateReport
    digest: str
    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "gate": self.gate.to_dict() if self.gate else None, "report": self.report.to_dict(), "digest": self.digest}

def build_default_policy() -> FinalLiveMemoryCommitReviewGatePolicy:
    return FinalLiveMemoryCommitReviewGatePolicy()

def validate_policy(policy: FinalLiveMemoryCommitReviewGatePolicy | None = None) -> dict[str, Any]:
    active = policy or build_default_policy()
    findings: list[FinalLiveMemoryCommitReviewGateFinding] = []
    if not active.metadata_only or not active.default_deny:
        findings.append(FinalLiveMemoryCommitReviewGateFinding("error", "policy_not_metadata_only_default_deny", "policy must remain metadata-only and default-deny"))
    for name in ("real_executor_enabled", "real_lock_acquisition_enabled", "lockfile_creation_enabled", "real_memory_root_admission_enabled", "live_memory_write_enabled", "external_disclosure_enabled"):
        if bool(getattr(active, name)):
            findings.append(FinalLiveMemoryCommitReviewGateFinding("error", name, f"{name} must remain false"))
    return {"status": "valid" if not findings else "invalid", "policy": active.to_dict(), "findings": [f.to_dict() for f in findings]}

def _digest(data: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}

def _stable_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "record"

def _blocked(code: str, findings: Sequence[FinalLiveMemoryCommitReviewGateFinding] = ()) -> FinalLiveMemoryCommitReviewGateResult:
    all_findings = tuple(findings) or (FinalLiveMemoryCommitReviewGateFinding("error", code, code),)
    report = FinalLiveMemoryCommitReviewGateReport("final_live_memory_commit_review_gate_blocked", all_findings, {"blocked": 1})
    report = replace(report, digest=_digest(report.to_dict()))
    return FinalLiveMemoryCommitReviewGateResult("final_live_memory_commit_review_gate_blocked", None, report, _digest(report.to_dict()))

def _extract_envelope(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    envelope = _as_mapping(payload.get("real_live_memory_commit_adapter_readiness_envelope"))
    if envelope.get("gate"):
        envelope = _as_mapping(envelope.get("gate"))
    records = envelope.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records:
        raise ValueError("missing_real_live_memory_commit_adapter_readiness_envelope")
    record = _as_mapping(records[0])
    return envelope, record

def _extract_candidates(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candidates = payload.get("final_live_memory_commit_review_gate_candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)) or not candidates:
        raise ValueError("missing_final_live_memory_commit_review_gate_candidate")
    return [_as_mapping(c) for c in candidates]

def _candidate(raw: Mapping[str, Any]) -> FinalLiveMemoryCommitReviewGateCandidate:
    candidate_type = str(raw.get("candidate_type") or "")
    candidate_id = str(raw.get("candidate_id") or _stable_token(candidate_type))
    record_id = str(raw.get("record_id") or candidate_id)
    scope = raw.get("operator_scope_keys") or []
    if not isinstance(scope, Sequence) or isinstance(scope, (str, bytes)):
        scope = []
    metadata = _as_mapping(raw.get("metadata"))
    return FinalLiveMemoryCommitReviewGateCandidate(candidate_id, record_id, candidate_type, tuple(str(s) for s in scope), bool(raw.get("is_noop", False)), metadata)

def _metadata_record(record_type: str, candidate: FinalLiveMemoryCommitReviewGateCandidate, metadata: Mapping[str, Any]) -> FinalLiveMemoryCommitReviewGateMetadataRecord:
    return FinalLiveMemoryCommitReviewGateMetadataRecord(record_type, candidate.candidate_id, candidate.record_id, _digest(dict(sorted((str(k), v) for k, v in metadata.items()))))

def _carried_evidence(record: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    carried = _as_mapping(record.get("carried_evidence"))
    evidence: dict[str, dict[str, str]] = {}
    for name, digest_field, decision_field in CARRIED_EVIDENCE_FIELDS:
        sub = _as_mapping(carried.get(name))
        digest = str(record.get(digest_field) or sub.get("digest") or "")
        decision = str(record.get(decision_field) or sub.get("decision") or "")
        if digest or decision:
            evidence[name] = {"digest": digest, "decision": decision}
    return dict(sorted(evidence.items()))

def _decision(candidate: FinalLiveMemoryCommitReviewGateCandidate, findings: Sequence[FinalLiveMemoryCommitReviewGateFinding]) -> FinalLiveMemoryCommitReviewGateDecision:
    if candidate.is_noop or candidate.candidate_type == "noop_final_live_memory_commit_review_gate_candidate":
        return "final_live_memory_commit_review_gate_noop"
    if candidate.candidate_type == "operator_review_final_live_memory_commit_review_gate_candidate":
        return "final_live_memory_commit_review_gate_deferred_for_operator_review"
    if any(f.severity == "warning" for f in findings) or candidate.candidate_type == "mixed_final_live_memory_commit_review_gate_candidate":
        return "final_live_memory_commit_review_gate_ready_with_warnings"
    return "final_live_memory_commit_review_gate_ready_for_later_real_memory_root_admission_gate"

def _safe_actions(decision: str) -> tuple[str, ...]:
    if decision == "final_live_memory_commit_review_gate_noop":
        return ("no_action_allowed", "sustain_default_deny")
    if decision == "final_live_memory_commit_review_gate_deferred_for_operator_review":
        return ("operator_review_required", "sustain_default_deny")
    return SAFE_NEXT_ACTIONS

def _check_candidate(raw: Mapping[str, Any], candidate: FinalLiveMemoryCommitReviewGateCandidate, envelope: Mapping[str, Any], record: Mapping[str, Any], policy: FinalLiveMemoryCommitReviewGatePolicy) -> list[FinalLiveMemoryCommitReviewGateFinding]:
    findings: list[FinalLiveMemoryCommitReviewGateFinding] = []
    if candidate.candidate_type not in FINAL_LIVE_MEMORY_COMMIT_REVIEW_GATE_CANDIDATE_TYPES:
        return [FinalLiveMemoryCommitReviewGateFinding("error", "invalid_final_live_memory_commit_review_gate_candidate", "invalid final review gate candidate", candidate.candidate_id, candidate.record_id)]
    claims = _as_mapping(raw.get("final_live_memory_commit_review_gate_claims"))
    for name in sorted(FORBIDDEN_CLAIMS):
        if bool(claims.get(name)) or bool(raw.get(name)):
            return [FinalLiveMemoryCommitReviewGateFinding("error", name, f"{name} is forbidden", candidate.candidate_id, candidate.record_id)]
    gate_digest = str(envelope.get("digest") or "")
    record_decision = str(record.get("real_live_memory_commit_adapter_readiness_envelope_decision") or "")
    if record_decision not in READY_REAL_LIVE_MEMORY_COMMIT_ADAPTER_READINESS_ENVELOPE_DECISIONS:
        return [FinalLiveMemoryCommitReviewGateFinding("error", "real_live_memory_commit_adapter_readiness_envelope_not_ready", "adapter readiness envelope is not ready", candidate.candidate_id, candidate.record_id)]
    if str(raw.get("claimed_real_live_memory_commit_adapter_readiness_envelope_digest") or "") != gate_digest:
        return [FinalLiveMemoryCommitReviewGateFinding("error", "real_live_memory_commit_adapter_readiness_envelope_digest_mismatch", "adapter readiness envelope digest mismatch", candidate.candidate_id, candidate.record_id)]
    if str(raw.get("claimed_real_live_memory_commit_adapter_readiness_envelope_decision") or "") != record_decision:
        return [FinalLiveMemoryCommitReviewGateFinding("error", "real_live_memory_commit_adapter_readiness_envelope_decision_mismatch", "adapter readiness envelope decision mismatch", candidate.candidate_id, candidate.record_id)]
    if policy.require_scope_alignment and tuple(str(s) for s in record.get("operator_scope_keys") or ()) != candidate.operator_scope_keys:
        if candidate.candidate_type == "mixed_final_live_memory_commit_review_gate_candidate" and policy.allow_mixed_scope_diagnostic_packet:
            findings.append(FinalLiveMemoryCommitReviewGateFinding("warning", "mixed_scope_diagnostic", "mixed candidate scope mismatch is diagnostic only", candidate.candidate_id, candidate.record_id))
        else:
            return [FinalLiveMemoryCommitReviewGateFinding("error", "scope_mismatch", "candidate scope must match adapter readiness envelope scope", candidate.candidate_id, candidate.record_id)]
    if not candidate.is_noop:
        missing = [field for field in NON_NOOP_METADATA_FIELDS if not _as_mapping(raw.get(field))]
        if missing:
            return [FinalLiveMemoryCommitReviewGateFinding("error", f"missing_{missing[0]}", f"missing required metadata field {missing[0]}", candidate.candidate_id, candidate.record_id)]
    for name, digest_field, decision_field in CARRIED_EVIDENCE_FIELDS:
        claimed_digest = str(raw.get(f"claimed_{digest_field}") or "")
        claimed_decision = str(raw.get(f"claimed_{decision_field}") or "")
        actual_digest = str(record.get(digest_field) or _as_mapping(record.get("carried_evidence")).get(name, {}).get("digest") or "")
        actual_decision = str(record.get(decision_field) or _as_mapping(record.get("carried_evidence")).get(name, {}).get("decision") or "")
        if actual_digest and claimed_digest and claimed_digest != actual_digest:
            return [FinalLiveMemoryCommitReviewGateFinding("error", f"{digest_field}_mismatch", f"{name} digest mismatch", candidate.candidate_id, candidate.record_id)]
        if actual_decision and claimed_decision and claimed_decision != actual_decision:
            return [FinalLiveMemoryCommitReviewGateFinding("error", f"{decision_field}_mismatch", f"{name} decision mismatch", candidate.candidate_id, candidate.record_id)]
    return findings

def evaluate_final_live_memory_commit_review_gate(payload: Mapping[str, Any], policy: FinalLiveMemoryCommitReviewGatePolicy | None = None) -> FinalLiveMemoryCommitReviewGateResult:
    active_policy = policy or build_default_policy()
    validation = validate_policy(active_policy)
    if validation["status"] != "valid":
        return _blocked("invalid_policy", [FinalLiveMemoryCommitReviewGateFinding("error", "invalid_policy", "policy failed validation")])
    try:
        envelope, upstream = _extract_envelope(payload)
        raw_candidates = _extract_candidates(payload)
        records: list[FinalLiveMemoryCommitReviewGateRecord] = []
        findings: list[FinalLiveMemoryCommitReviewGateFinding] = []
        for raw in raw_candidates:
            candidate = _candidate(raw)
            candidate_findings = _check_candidate(raw, candidate, envelope, upstream, active_policy)
            if any(f.severity == "error" for f in candidate_findings):
                return _blocked(candidate_findings[0].code, candidate_findings)
            findings.extend(candidate_findings)
            decision = _decision(candidate, candidate_findings)
            carried = _carried_evidence(upstream)
            records.append(FinalLiveMemoryCommitReviewGateRecord(
                candidate.candidate_id,
                candidate.record_id,
                candidate.candidate_type,
                decision,
                str(envelope.get("digest") or ""),
                str(upstream.get("real_live_memory_commit_adapter_readiness_envelope_decision") or ""),
                str(upstream.get("real_live_memory_commit_adapter_readiness_gate_digest") or ""),
                str(upstream.get("real_live_memory_commit_adapter_readiness_gate_decision") or ""),
                str(upstream.get("real_live_memory_commit_adapter_admission_packet_digest") or ""),
                str(upstream.get("real_live_memory_commit_adapter_admission_packet_decision") or ""),
                str(upstream.get("real_live_memory_commit_adapter_admission_gate_digest") or carried.get("real_live_memory_commit_adapter_admission_gate", {}).get("digest") or ""),
                str(upstream.get("real_live_memory_commit_adapter_admission_gate_decision") or carried.get("real_live_memory_commit_adapter_admission_gate", {}).get("decision") or ""),
                str(upstream.get("real_live_memory_commit_execution_packet_digest") or ""),
                str(upstream.get("real_live_memory_commit_execution_packet_decision") or ""),
                str(upstream.get("real_live_memory_commit_execution_gate_digest") or ""),
                str(upstream.get("real_live_memory_commit_execution_gate_decision") or ""),
                str(upstream.get("real_executor_execution_commit_window_packet_digest") or ""),
                str(upstream.get("real_executor_execution_commit_window_packet_decision") or ""),
                str(upstream.get("real_executor_execution_commit_plan_gate_digest") or ""),
                str(upstream.get("real_executor_execution_commit_plan_gate_decision") or ""),
                str(upstream.get("real_executor_execution_commit_plan_packet_digest") or ""),
                str(upstream.get("real_executor_execution_commit_plan_packet_decision") or ""),
                str(upstream.get("real_executor_execution_lock_lease_gate_digest") or ""),
                str(upstream.get("real_executor_execution_lock_lease_gate_decision") or ""),
                carried,
                candidate.operator_scope_keys,
                (_metadata_record("final_review_gate_readiness", candidate, _as_mapping(raw.get("final_review_gate_readiness_metadata") or raw.get("metadata"))),),
                (_metadata_record("adapter_readiness_envelope_confirmation", candidate, _as_mapping(raw.get("adapter_readiness_envelope_confirmation_metadata") or raw.get("metadata"))),),
                (_metadata_record("adapter_readiness_gate_confirmation", candidate, _as_mapping(raw.get("adapter_readiness_gate_confirmation_metadata") or raw.get("metadata"))),),
                (_metadata_record("adapter_admission_packet_confirmation", candidate, _as_mapping(raw.get("adapter_admission_packet_confirmation_metadata") or raw.get("metadata"))),),
                (_metadata_record("adapter_admission_gate_confirmation", candidate, _as_mapping(raw.get("adapter_admission_gate_confirmation_metadata") or raw.get("metadata"))),),
                (_metadata_record("live_memory_commit_execution_packet_confirmation", candidate, _as_mapping(raw.get("live_memory_commit_execution_packet_confirmation_metadata") or raw.get("metadata"))),),
                (_metadata_record("live_memory_commit_execution_gate_confirmation", candidate, _as_mapping(raw.get("live_memory_commit_execution_gate_confirmation_metadata") or raw.get("metadata"))),),
                (_metadata_record("commit_window_packet_confirmation", candidate, _as_mapping(raw.get("commit_window_packet_confirmation_metadata") or raw.get("metadata"))),),
                (_metadata_record("commit_plan_gate_confirmation", candidate, _as_mapping(raw.get("commit_plan_gate_confirmation_metadata") or raw.get("metadata"))),),
                (_metadata_record("commit_plan_packet_confirmation", candidate, _as_mapping(raw.get("commit_plan_packet_confirmation_metadata") or raw.get("metadata"))),),
                (_metadata_record("lock_lease_gate_confirmation", candidate, _as_mapping(raw.get("lock_lease_gate_confirmation_metadata") or raw.get("metadata"))),),
                (_metadata_record("live_commit_execution_denial", candidate, _as_mapping(raw.get("live_commit_execution_denial_metadata") or raw.get("metadata"))),),
                (_metadata_record("live_memory_write_denial", candidate, _as_mapping(raw.get("live_memory_write_denial_metadata") or raw.get("metadata"))),),
                (_metadata_record("real_memory_root_admission_deferral", candidate, _as_mapping(raw.get("real_memory_root_admission_deferral_metadata") or raw.get("metadata"))),),
                (_metadata_record("emergency_stop_confirmation", candidate, _as_mapping(raw.get("emergency_stop_confirmation_metadata") or raw.get("metadata"))),),
                (_metadata_record("rollback_readiness", candidate, _as_mapping(raw.get("rollback_readiness_metadata") or raw.get("metadata"))),),
                (_metadata_record("verification_readiness", candidate, _as_mapping(raw.get("verification_readiness_metadata") or raw.get("metadata"))),),
                (_metadata_record("audit_readiness", candidate, _as_mapping(raw.get("audit_readiness_metadata") or raw.get("metadata"))),),
                _safe_actions(decision),
            ).with_digest())
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for f in findings if f.severity == "warning")}
        for record in records:
            counts[record.final_live_memory_commit_review_gate_decision] = counts.get(record.final_live_memory_commit_review_gate_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {r.final_live_memory_commit_review_gate_decision for r in records}
        if counts["warning_count"] or "final_live_memory_commit_review_gate_ready_with_warnings" in decisions:
            status: FinalLiveMemoryCommitReviewGateStatus = "final_live_memory_commit_review_gate_ready_with_warnings"
        elif decisions <= {"final_live_memory_commit_review_gate_noop"}:
            status = "final_live_memory_commit_review_gate_noop"
        elif decisions <= {"final_live_memory_commit_review_gate_deferred_for_operator_review"}:
            status = "final_live_memory_commit_review_gate_deferred_for_operator_review"
        else:
            status = "final_live_memory_commit_review_gate_ready"
        gate = FinalLiveMemoryCommitReviewGate(active_policy.schema_version, tuple(records)).with_digest()
        report = FinalLiveMemoryCommitReviewGateReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return FinalLiveMemoryCommitReviewGateResult(status, gate, report, _digest({"gate": gate.to_dict(), "report": report.to_dict()}))
    except ValueError as exc:
        return _blocked(str(exc))
    except Exception as exc:
        return _blocked("failed", [FinalLiveMemoryCommitReviewGateFinding("error", "failed", str(exc))])

def evaluate_gate(payload: Mapping[str, Any], policy: FinalLiveMemoryCommitReviewGatePolicy | None = None) -> FinalLiveMemoryCommitReviewGateResult:
    return evaluate_final_live_memory_commit_review_gate(payload, policy)

__all__ = [
    "CARRIED_EVIDENCE_FIELDS", "FAIL_STATUSES", "FALSE_FLAGS", "FORBIDDEN_CLAIMS", "FORBIDDEN_NEXT_STEPS",
    "FUTURE_FLAGS", "INVARIANTS", "NON_NOOP_METADATA_FIELDS", "FINAL_LIVE_MEMORY_COMMIT_REVIEW_GATE_CANDIDATE_TYPES",
    "READY_REAL_LIVE_MEMORY_COMMIT_ADAPTER_READINESS_ENVELOPE_DECISIONS",
    "FinalLiveMemoryCommitReviewGate", "FinalLiveMemoryCommitReviewGateCandidate", "FinalLiveMemoryCommitReviewGateFinding",
    "FinalLiveMemoryCommitReviewGateMetadataRecord", "FinalLiveMemoryCommitReviewGatePolicy", "FinalLiveMemoryCommitReviewGateRecord",
    "FinalLiveMemoryCommitReviewGateReport", "FinalLiveMemoryCommitReviewGateResult", "build_default_policy", "evaluate_gate",
    "evaluate_final_live_memory_commit_review_gate", "validate_policy",
]
