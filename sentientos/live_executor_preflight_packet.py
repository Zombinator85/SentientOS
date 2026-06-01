"""Deterministic metadata-only live executor preflight packets.

This module consumes supplied Live Executor Lock Lease Gate evidence plus
explicit preflight candidates and emits deterministic review records for a
later real live-memory commit executor. It never performs preflight execution,
acquires locks, creates lockfiles, inspects real lockfiles, writes, deletes,
purges, indexes, persists capsules, completes tombs, applies protection or
merge operations, assembles prompts, retrieves live context, executes actions,
discloses externally, invokes remote services, touches real memory roots,
grants truth, creates policy, infers consent, or grants authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Mapping, Sequence

PreflightStatus = Literal[
    "preflight_ready",
    "preflight_ready_with_warnings",
    "preflight_deferred_for_operator_review",
    "preflight_rejected",
    "preflight_blocked",
    "preflight_noop",
    "preflight_invalid",
    "preflight_failed",
]
PreflightDecision = Literal[
    "preflight_ready_for_later_live_executor",
    "preflight_ready_with_warnings",
    "preflight_deferred_for_operator_review",
    "preflight_rejected",
    "preflight_blocked",
    "preflight_noop",
]

PREFLIGHT_CANDIDATE_TYPES = frozenset({
    "ai_capsule_preflight_candidate",
    "human_summary_preflight_candidate",
    "dual_capsule_preflight_candidate",
    "protect_receipt_preflight_candidate",
    "merge_receipt_preflight_candidate",
    "tomb_archive_preflight_candidate",
    "tomb_deferred_preflight_candidate",
    "operator_review_preflight_candidate",
    "noop_preflight_candidate",
    "mixed_preflight_candidate",
})
READY_LOCK_LEASE_DECISIONS = frozenset({
    "lock_lease_ready_for_later_live_executor",
    "lock_lease_ready_with_warnings",
    "lock_lease_noop",
})

INVARIANTS: dict[str, bool] = {
    "preflight_packet_is_not_lock_acquisition": True,
    "preflight_packet_is_not_lockfile_creation": True,
    "preflight_packet_is_not_memory_write": True,
    "preflight_packet_is_not_memory_deletion": True,
    "preflight_packet_is_not_memory_purge": True,
    "preflight_packet_is_not_index_mutation": True,
    "preflight_packet_is_not_capsule_persistence": True,
    "preflight_packet_is_not_tomb_completion": True,
    "preflight_packet_is_not_prompt_assembly": True,
    "preflight_packet_is_not_live_context_retrieval": True,
    "preflight_packet_is_not_action_execution": True,
    "preflight_packet_is_not_external_disclosure": True,
    "preflight_packet_is_not_live_commit_execution": True,
    "preflight_packet_is_not_truth": True,
    "preflight_packet_is_not_policy": True,
    "preflight_packet_is_not_authority": True,
    "preflight_packet_is_not_consent": True,
    "final_preflight_readiness_is_metadata_only": True,
    "operation_inventory_is_metadata_only": True,
    "safety_checklist_is_metadata_only": True,
    "verification_checklist_is_metadata_only": True,
    "abort_readiness_is_metadata_only": True,
    "rollback_readiness_is_metadata_only": True,
    "audit_readiness_is_metadata_only": True,
    "operation_inventory_records_are_intents_only": True,
    "receipt_targets_are_metadata_only": True,
    "rollback_targets_are_metadata_only": True,
    "real_lock_acquisition_enabled": False,
    "lockfile_creation_enabled": False,
    "real_memory_root_write_enabled": False,
    "live_memory_write_enabled": False,
    "live_memory_deletion_enabled": False,
    "live_memory_purge_enabled": False,
    "live_index_mutation_enabled": False,
    "capsule_persistence_enabled": False,
    "tomb_completion_enabled": False,
    "prompt_materialization_enabled": False,
    "live_context_retrieval_enabled": False,
    "action_execution_enabled": False,
    "external_disclosure_enabled": False,
    "remote_service_enabled": False,
    "live_executor_enabled": False,
    "future_real_live_memory_commit_executor_required": True,
    "future_executor_activation_record_required": True,
    "future_post_execution_audit_required": True,
}
FORBIDDEN_NEXT_STEPS = (
    "acquire_real_lock", "create_lockfile", "write_real_live_memory", "delete_real_live_memory",
    "purge_real_live_memory", "mutate_live_index", "persist_capsule", "complete_tomb", "apply_protection",
    "apply_merge", "assemble_prompt", "retrieve_live_context", "execute_action", "disclose_externally",
    "invoke_remote_service", "bypass_lock_lease_gate", "bypass_executor_plan_packet", "bypass_runtime_execution_gate",
    "bypass_readiness_envelope", "bypass_final_review", "bypass_real_root_admission", "bypass_sandbox_commit",
    "invoke_direct_live_executor_now",
)
FAIL_STATUSES = {"preflight_blocked", "preflight_invalid", "preflight_failed"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _as_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item) for item in value)
    return ()


def _flag(mapping: Mapping[str, Any], *keys: str) -> bool:
    return any(mapping.get(key) is True for key in keys)


def _has_raw_payload(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).lower()
            if re.search(r"(^|_)(raw|private|secret|media|provider_prompt)(_|$)", lowered):
                return True
            if _has_raw_payload(nested):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_has_raw_payload(item) for item in value)
    elif isinstance(value, str) and re.search(r"(begin private|secret:|data:(?:image|audio|video)|provider prompt text)", value, re.I):
        return True
    return False


@dataclass(frozen=True)
class PreflightPolicy:
    schema_version: str = "live-executor-preflight-packet/v1"
    default_posture: str = "deny"
    require_ready_lock_lease_gate_packet: bool = True
    require_matching_lock_lease_gate_digest: bool = True
    require_matching_lock_lease_gate_decision: bool = True
    require_matching_executor_plan_packet_digest: bool = True
    require_matching_executor_plan_decision: bool = True
    require_matching_runtime_execution_gate_digest: bool = True
    require_matching_runtime_execution_gate_decision: bool = True
    require_matching_readiness_envelope_digest: bool = True
    require_matching_readiness_envelope_decision: bool = True
    require_matching_final_review_digest: bool = True
    require_matching_final_review_decision: bool = True
    require_matching_real_root_admission_digest: bool = True
    require_matching_real_root_admission_decision: bool = True
    require_matching_sandbox_commit_digest: bool = True
    require_matching_sandbox_commit_decision: bool = True
    require_non_noop_operation_list_digest_metadata: bool = True
    require_non_noop_operation_inventory_metadata: bool = True
    require_non_noop_operation_ordering_metadata: bool = True
    require_non_noop_per_operation_precondition_metadata: bool = True
    require_non_noop_per_operation_receipt_target_metadata: bool = True
    require_non_noop_per_operation_rollback_target_metadata: bool = True
    require_non_noop_lock_lease_readiness_metadata: bool = True
    require_non_noop_lease_duration_metadata: bool = True
    require_non_noop_lock_owner_metadata: bool = True
    require_non_noop_operator_identity_role_metadata: bool = True
    require_non_noop_execution_window_metadata: bool = True
    require_non_noop_idempotency_key_metadata: bool = True
    require_non_noop_atomicity_boundary_metadata: bool = True
    require_non_noop_dry_run_to_live_equivalence_metadata: bool = True
    require_non_noop_rollback_rehearsal_metadata: bool = True
    require_non_noop_post_execution_audit_metadata: bool = True
    require_non_noop_verification_checklist_metadata: bool = True
    require_non_noop_abort_panic_stop_condition_metadata: bool = True
    require_non_noop_contamination_check_metadata: bool = True
    require_non_noop_generated_artifact_cleanup_expectation_metadata: bool = True
    require_non_noop_final_clean_tree_expectation_metadata: bool = True
    require_non_noop_future_executor_requirement_metadata: bool = True
    require_scope_alignment: bool = True
    allow_mixed_scope_diagnostic_packet: bool = True
    block_lock_acquisition_claims: bool = True
    block_lockfile_creation_claims: bool = True
    block_live_mutation_claims: bool = True
    block_real_memory_root_access_claims: bool = True
    block_preflight_execution_claims: bool = True
    block_runtime_execution_claims: bool = True
    block_executor_permission_claims: bool = True
    block_readiness_conversion_claims: bool = True
    block_final_review_conversion_claims: bool = True
    block_sandbox_conversion_claims: bool = True
    block_real_root_admission_conversion_claims: bool = True
    block_prompt_materialization: bool = True
    block_live_context_retrieval: bool = True
    block_action_execution: bool = True
    block_external_disclosure: bool = True
    block_authority_smuggling: bool = True
    block_consent_smuggling: bool = True
    block_policy_smuggling: bool = True
    block_truth_smuggling: bool = True
    block_raw_payload_leakage: bool = True
    real_lock_acquisition_enabled: bool = False
    lockfile_creation_enabled: bool = False
    live_executor_enabled: bool = False


@dataclass(frozen=True)
class PreflightFinding:
    severity: str
    code: str
    message: str
    candidate_id: str = ""
    record_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreflightCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    claimed_lock_lease_gate_packet_digest: str
    claimed_lock_lease_gate_decision: str
    claimed_executor_plan_packet_digest: str
    claimed_executor_plan_decision: str
    claimed_runtime_execution_gate_digest: str
    claimed_runtime_execution_gate_decision: str
    claimed_readiness_envelope_digest: str
    claimed_readiness_envelope_decision: str
    claimed_final_review_digest: str
    claimed_final_review_decision: str
    claimed_real_root_admission_digest: str
    claimed_real_root_admission_decision: str
    claimed_sandbox_commit_digest: str
    claimed_sandbox_commit_decision: str
    operator_scope_keys: tuple[str, ...]
    operation_list_digest_metadata: Mapping[str, Any]
    operation_inventory_metadata: Mapping[str, Any]
    operation_ordering_metadata: Mapping[str, Any]
    per_operation_precondition_metadata: Mapping[str, Any]
    per_operation_receipt_target_metadata: Mapping[str, Any]
    per_operation_rollback_target_metadata: Mapping[str, Any]
    lock_lease_readiness_metadata: Mapping[str, Any]
    lease_duration_metadata: Mapping[str, Any]
    lock_owner_metadata: Mapping[str, Any]
    operator_identity_role_metadata: Mapping[str, Any]
    execution_window_metadata: Mapping[str, Any]
    idempotency_key_metadata: Mapping[str, Any]
    atomicity_boundary_metadata: Mapping[str, Any]
    dry_run_to_live_equivalence_metadata: Mapping[str, Any]
    rollback_rehearsal_metadata: Mapping[str, Any]
    post_execution_audit_metadata: Mapping[str, Any]
    verification_checklist_metadata: Mapping[str, Any]
    abort_panic_stop_condition_metadata: Mapping[str, Any]
    contamination_check_metadata: Mapping[str, Any]
    generated_artifact_cleanup_expectation_metadata: Mapping[str, Any]
    final_clean_tree_expectation_metadata: Mapping[str, Any]
    future_executor_requirement_metadata: Mapping[str, Any]
    preflight_claims: Mapping[str, Any]
    metadata: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PreflightCandidate":
        return cls(
            candidate_id=str(raw.get("candidate_id") or ""),
            record_id=str(raw.get("record_id") or raw.get("candidate_id") or ""),
            candidate_type=str(raw.get("candidate_type") or ""),
            claimed_lock_lease_gate_packet_digest=str(raw.get("claimed_lock_lease_gate_packet_digest") or raw.get("lock_lease_gate_packet_digest") or ""),
            claimed_lock_lease_gate_decision=str(raw.get("claimed_lock_lease_gate_decision") or raw.get("lock_lease_gate_decision") or ""),
            claimed_executor_plan_packet_digest=str(raw.get("claimed_executor_plan_packet_digest") or raw.get("executor_plan_packet_digest") or ""),
            claimed_executor_plan_decision=str(raw.get("claimed_executor_plan_decision") or raw.get("executor_plan_decision") or ""),
            claimed_runtime_execution_gate_digest=str(raw.get("claimed_runtime_execution_gate_digest") or raw.get("runtime_execution_gate_digest") or ""),
            claimed_runtime_execution_gate_decision=str(raw.get("claimed_runtime_execution_gate_decision") or raw.get("runtime_execution_gate_decision") or ""),
            claimed_readiness_envelope_digest=str(raw.get("claimed_readiness_envelope_digest") or raw.get("readiness_envelope_digest") or ""),
            claimed_readiness_envelope_decision=str(raw.get("claimed_readiness_envelope_decision") or raw.get("readiness_envelope_decision") or ""),
            claimed_final_review_digest=str(raw.get("claimed_final_review_digest") or raw.get("final_review_digest") or ""),
            claimed_final_review_decision=str(raw.get("claimed_final_review_decision") or raw.get("final_review_decision") or ""),
            claimed_real_root_admission_digest=str(raw.get("claimed_real_root_admission_digest") or raw.get("real_root_admission_digest") or ""),
            claimed_real_root_admission_decision=str(raw.get("claimed_real_root_admission_decision") or raw.get("real_root_admission_decision") or ""),
            claimed_sandbox_commit_digest=str(raw.get("claimed_sandbox_commit_digest") or raw.get("sandbox_commit_digest") or ""),
            claimed_sandbox_commit_decision=str(raw.get("claimed_sandbox_commit_decision") or raw.get("sandbox_commit_decision") or ""),
            operator_scope_keys=_as_tuple(raw.get("operator_scope_keys")),
            operation_list_digest_metadata=_as_mapping(raw.get("operation_list_digest_metadata")),
            operation_inventory_metadata=_as_mapping(raw.get("operation_inventory_metadata")),
            operation_ordering_metadata=_as_mapping(raw.get("operation_ordering_metadata")),
            per_operation_precondition_metadata=_as_mapping(raw.get("per_operation_precondition_metadata")),
            per_operation_receipt_target_metadata=_as_mapping(raw.get("per_operation_receipt_target_metadata")),
            per_operation_rollback_target_metadata=_as_mapping(raw.get("per_operation_rollback_target_metadata")),
            lock_lease_readiness_metadata=_as_mapping(raw.get("lock_lease_readiness_metadata")),
            lease_duration_metadata=_as_mapping(raw.get("lease_duration_metadata")),
            lock_owner_metadata=_as_mapping(raw.get("lock_owner_metadata")),
            operator_identity_role_metadata=_as_mapping(raw.get("operator_identity_role_metadata")),
            execution_window_metadata=_as_mapping(raw.get("execution_window_metadata")),
            idempotency_key_metadata=_as_mapping(raw.get("idempotency_key_metadata")),
            atomicity_boundary_metadata=_as_mapping(raw.get("atomicity_boundary_metadata")),
            dry_run_to_live_equivalence_metadata=_as_mapping(raw.get("dry_run_to_live_equivalence_metadata")),
            rollback_rehearsal_metadata=_as_mapping(raw.get("rollback_rehearsal_metadata")),
            post_execution_audit_metadata=_as_mapping(raw.get("post_execution_audit_metadata")),
            verification_checklist_metadata=_as_mapping(raw.get("verification_checklist_metadata")),
            abort_panic_stop_condition_metadata=_as_mapping(raw.get("abort_panic_stop_condition_metadata")),
            contamination_check_metadata=_as_mapping(raw.get("contamination_check_metadata")),
            generated_artifact_cleanup_expectation_metadata=_as_mapping(raw.get("generated_artifact_cleanup_expectation_metadata")),
            final_clean_tree_expectation_metadata=_as_mapping(raw.get("final_clean_tree_expectation_metadata")),
            future_executor_requirement_metadata=_as_mapping(raw.get("future_executor_requirement_metadata")),
            preflight_claims=_as_mapping(raw.get("preflight_claims") or raw.get("claims")),
            metadata=_as_mapping(raw.get("metadata")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreflightRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    preflight_decision: PreflightDecision
    lock_lease_gate_packet_digest: str
    lock_lease_gate_decision: str
    lock_lease_gate_record_digest: str
    executor_plan_packet_digest: str
    executor_plan_decision: str
    runtime_execution_gate_digest: str
    runtime_execution_gate_decision: str
    readiness_envelope_digest: str
    readiness_envelope_decision: str
    final_review_digest: str
    final_review_decision: str
    real_root_admission_digest: str
    real_root_admission_decision: str
    sandbox_commit_digest: str
    sandbox_commit_decision: str
    operator_scope_keys: tuple[str, ...]
    lock_lease_scope_keys: tuple[str, ...]
    executor_plan_scope_keys: tuple[str, ...]
    runtime_scope_keys: tuple[str, ...]
    readiness_scope_keys: tuple[str, ...]
    final_review_scope_keys: tuple[str, ...]
    real_root_admission_scope_keys: tuple[str, ...]
    sandbox_scope_keys: tuple[str, ...]
    operation_list_digest_metadata: Mapping[str, Any]
    operation_inventory_metadata: Mapping[str, Any]
    operation_ordering_metadata: Mapping[str, Any]
    per_operation_precondition_metadata: Mapping[str, Any]
    per_operation_receipt_target_metadata: Mapping[str, Any]
    per_operation_rollback_target_metadata: Mapping[str, Any]
    lock_lease_readiness_metadata: Mapping[str, Any]
    lease_duration_metadata: Mapping[str, Any]
    lock_owner_metadata: Mapping[str, Any]
    operator_identity_role_metadata: Mapping[str, Any]
    execution_window_metadata: Mapping[str, Any]
    idempotency_key_metadata: Mapping[str, Any]
    atomicity_boundary_metadata: Mapping[str, Any]
    dry_run_to_live_equivalence_metadata: Mapping[str, Any]
    rollback_rehearsal_metadata: Mapping[str, Any]
    post_execution_audit_metadata: Mapping[str, Any]
    verification_checklist_metadata: Mapping[str, Any]
    abort_panic_stop_condition_metadata: Mapping[str, Any]
    contamination_check_metadata: Mapping[str, Any]
    generated_artifact_cleanup_expectation_metadata: Mapping[str, Any]
    final_clean_tree_expectation_metadata: Mapping[str, Any]
    future_executor_requirement_metadata: Mapping[str, Any]
    final_preflight_readiness_records: tuple[Mapping[str, Any], ...]
    operation_inventory_records: tuple[Mapping[str, Any], ...]
    safety_checklist_records: tuple[Mapping[str, Any], ...]
    verification_checklist_records: tuple[Mapping[str, Any], ...]
    abort_readiness_records: tuple[Mapping[str, Any], ...]
    rollback_readiness_records: tuple[Mapping[str, Any], ...]
    audit_readiness_records: tuple[Mapping[str, Any], ...]
    safe_next_actions: tuple[str, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    preflight_packet_future_consideration_only: bool = True
    preflight_execution_performed: bool = False
    lock_acquired: bool = False
    lockfile_created: bool = False
    live_commit_executed: bool = False
    live_execution_permission_granted: bool = False
    operator_review_cannot_override_hard_blockers: bool = True
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_digest(self) -> "PreflightRecord":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class PreflightPacket:
    schema_version: str
    records: tuple[PreflightRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""
    preflight_packet_is_not_lock_acquisition: bool = True
    preflight_packet_is_not_lockfile_creation: bool = True
    preflight_packet_is_not_memory_write: bool = True
    preflight_packet_is_not_memory_deletion: bool = True
    preflight_packet_is_not_memory_purge: bool = True
    preflight_packet_is_not_index_mutation: bool = True
    preflight_packet_is_not_capsule_persistence: bool = True
    preflight_packet_is_not_tomb_completion: bool = True
    preflight_packet_is_not_prompt_assembly: bool = True
    preflight_packet_is_not_live_context_retrieval: bool = True
    preflight_packet_is_not_action_execution: bool = True
    preflight_packet_is_not_external_disclosure: bool = True
    preflight_packet_is_not_live_commit_execution: bool = True
    preflight_packet_is_not_truth: bool = True
    preflight_packet_is_not_policy: bool = True
    preflight_packet_is_not_authority: bool = True
    preflight_packet_is_not_consent: bool = True
    final_preflight_readiness_is_metadata_only: bool = True
    operation_inventory_is_metadata_only: bool = True
    safety_checklist_is_metadata_only: bool = True
    verification_checklist_is_metadata_only: bool = True
    abort_readiness_is_metadata_only: bool = True
    rollback_readiness_is_metadata_only: bool = True
    audit_readiness_is_metadata_only: bool = True
    operation_inventory_records_are_intents_only: bool = True
    receipt_targets_are_metadata_only: bool = True
    rollback_targets_are_metadata_only: bool = True
    real_lock_acquisition_enabled: bool = False
    lockfile_creation_enabled: bool = False
    real_memory_root_write_enabled: bool = False
    live_memory_write_enabled: bool = False
    live_memory_deletion_enabled: bool = False
    live_memory_purge_enabled: bool = False
    live_index_mutation_enabled: bool = False
    capsule_persistence_enabled: bool = False
    tomb_completion_enabled: bool = False
    prompt_materialization_enabled: bool = False
    live_context_retrieval_enabled: bool = False
    action_execution_enabled: bool = False
    external_disclosure_enabled: bool = False
    remote_service_enabled: bool = False
    live_executor_enabled: bool = False
    future_real_live_memory_commit_executor_required: bool = True
    future_executor_activation_record_required: bool = True
    future_post_execution_audit_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_digest(self) -> "PreflightPacket":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class PreflightReport:
    status: PreflightStatus
    findings: tuple[PreflightFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [f.to_dict() for f in self.findings], "summary_counts": dict(self.summary_counts), "digest": self.digest}


@dataclass(frozen=True)
class PreflightResult:
    status: PreflightStatus
    packet: PreflightPacket | None
    report: PreflightReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> PreflightPolicy:
    return PreflightPolicy()


def validate_policy(policy: PreflightPolicy | None = None) -> dict[str, Any]:
    active = policy or build_default_policy()
    raw = asdict(active)
    findings: list[dict[str, str]] = []
    if active.default_posture != "deny":
        findings.append({"severity": "error", "code": "default_posture_not_deny", "message": "preflight packet must default deny"})
    for key, expected in INVARIANTS.items():
        if raw.get(key, expected) != expected:
            findings.append({"severity": "error", "code": f"invariant_{key}_changed", "message": f"{key} must remain {expected}"})
    if active.real_lock_acquisition_enabled:
        findings.append({"severity": "error", "code": "real_lock_acquisition_enabled", "message": "real lock acquisition must remain disabled"})
    if active.lockfile_creation_enabled:
        findings.append({"severity": "error", "code": "lockfile_creation_enabled", "message": "lockfile creation must remain disabled"})
    if active.live_executor_enabled:
        findings.append({"severity": "error", "code": "live_executor_enabled", "message": "live executor must remain disabled"})
    status = "invalid" if findings else "valid"
    return {"status": status, "findings": findings, "policy": raw, "digest": _digest({"status": status, "findings": findings, "policy": raw})}


def _policy_from_payload(payload: Mapping[str, Any], policy: PreflightPolicy | None) -> PreflightPolicy:
    if policy is not None:
        return policy
    raw_policy = payload.get("policy")
    if isinstance(raw_policy, Mapping):
        allowed = {field for field in PreflightPolicy.__dataclass_fields__}
        return PreflightPolicy(**{key: value for key, value in raw_policy.items() if key in allowed})
    return build_default_policy()


def _lock_lease_packet(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = _as_mapping(payload.get("live_executor_lock_lease_gate_packet") or payload.get("lock_lease_gate_packet") or payload.get("packet"))
    nested = _as_mapping(raw.get("packet"))
    return nested or raw


def _candidate_payloads(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = payload.get("preflight_candidates", payload.get("preflight_candidate", payload.get("candidates", ())))
    if isinstance(raw, Mapping):
        return (raw,)
    return tuple(item for item in _as_sequence(raw) if isinstance(item, Mapping))


def _blocked(code: str, findings: Sequence[PreflightFinding] = ()) -> PreflightResult:
    base = tuple(findings) or (PreflightFinding("error", code, code.replace("_", " ")),)
    report = PreflightReport("preflight_blocked", base, {"error_count": sum(1 for f in base if f.severity == "error")})
    report = replace(report, digest=_digest(report.to_dict()))
    return PreflightResult("preflight_blocked", None, report, _digest({"status": "preflight_blocked", "report": report.to_dict()}))


def _is_noop(candidate: PreflightCandidate, lock_decision: str) -> bool:
    return candidate.candidate_type == "noop_preflight_candidate" or lock_decision == "lock_lease_noop"


def _require_non_noop_metadata(candidate: PreflightCandidate, policy: PreflightPolicy) -> str | None:
    checks: tuple[tuple[bool, str, Any], ...] = (
        (policy.require_non_noop_operation_list_digest_metadata, "missing_operation_list_digest_metadata", candidate.operation_list_digest_metadata),
        (policy.require_non_noop_operation_inventory_metadata, "missing_operation_inventory_metadata", candidate.operation_inventory_metadata),
        (policy.require_non_noop_operation_ordering_metadata, "missing_operation_ordering_metadata", candidate.operation_ordering_metadata),
        (policy.require_non_noop_per_operation_precondition_metadata, "missing_per_operation_precondition_metadata", candidate.per_operation_precondition_metadata),
        (policy.require_non_noop_per_operation_receipt_target_metadata, "missing_receipt_target_metadata", candidate.per_operation_receipt_target_metadata),
        (policy.require_non_noop_per_operation_rollback_target_metadata, "missing_rollback_target_metadata", candidate.per_operation_rollback_target_metadata),
        (policy.require_non_noop_lock_lease_readiness_metadata, "missing_lock_lease_readiness_metadata", candidate.lock_lease_readiness_metadata),
        (policy.require_non_noop_lease_duration_metadata, "missing_lease_duration_metadata", candidate.lease_duration_metadata),
        (policy.require_non_noop_lock_owner_metadata, "missing_lock_owner_metadata", candidate.lock_owner_metadata),
        (policy.require_non_noop_operator_identity_role_metadata, "missing_operator_identity_role_metadata", candidate.operator_identity_role_metadata),
        (policy.require_non_noop_execution_window_metadata, "missing_execution_window_metadata", candidate.execution_window_metadata),
        (policy.require_non_noop_idempotency_key_metadata, "missing_idempotency_key_metadata", candidate.idempotency_key_metadata),
        (policy.require_non_noop_atomicity_boundary_metadata, "missing_atomicity_boundary_metadata", candidate.atomicity_boundary_metadata),
        (policy.require_non_noop_dry_run_to_live_equivalence_metadata, "missing_dry_run_to_live_equivalence_metadata", candidate.dry_run_to_live_equivalence_metadata),
        (policy.require_non_noop_rollback_rehearsal_metadata, "missing_rollback_rehearsal_metadata", candidate.rollback_rehearsal_metadata),
        (policy.require_non_noop_post_execution_audit_metadata, "missing_post_execution_audit_metadata", candidate.post_execution_audit_metadata),
        (policy.require_non_noop_verification_checklist_metadata, "missing_verification_checklist_metadata", candidate.verification_checklist_metadata),
        (policy.require_non_noop_abort_panic_stop_condition_metadata, "missing_abort_panic_stop_condition_metadata", candidate.abort_panic_stop_condition_metadata),
        (policy.require_non_noop_contamination_check_metadata, "missing_contamination_check_metadata", candidate.contamination_check_metadata),
        (policy.require_non_noop_generated_artifact_cleanup_expectation_metadata, "missing_generated_artifact_cleanup_expectation_metadata", candidate.generated_artifact_cleanup_expectation_metadata),
        (policy.require_non_noop_final_clean_tree_expectation_metadata, "missing_final_clean_tree_expectation_metadata", candidate.final_clean_tree_expectation_metadata),
        (policy.require_non_noop_future_executor_requirement_metadata, "missing_future_executor_requirement_metadata", candidate.future_executor_requirement_metadata),
    )
    for required, code, value in checks:
        if required and not value:
            return code
    return None


def _forbidden_claim(candidate: PreflightCandidate, policy: PreflightPolicy, raw: Mapping[str, Any]) -> str | None:
    claims = candidate.preflight_claims
    all_data = {"candidate": candidate.to_dict(), "claims": claims, "candidate_input": raw}
    if policy.block_preflight_execution_claims and _flag(claims, "preflight_execution_performed", "preflight_executed", "preflight_packet_performed_execution"):
        return "preflight_execution_claim"
    if policy.block_lock_acquisition_claims and _flag(claims, "lock_acquired", "real_lock_acquired", "real_lock_acquisition_enabled", "acquire_real_lock"):
        return "real_lock_acquisition_claim"
    if policy.block_lockfile_creation_claims and _flag(claims, "lockfile_created", "create_lockfile", "lockfile_creation_enabled"):
        return "lockfile_creation_claim"
    if policy.block_live_mutation_claims and _flag(claims, "live_memory_write_claimed", "live_memory_write_enabled", "live_memory_delete_claimed", "live_memory_deletion_enabled", "live_memory_purge_claimed", "live_memory_purge_enabled", "live_index_mutation_claimed", "live_index_mutation_enabled", "capsule_persistence_claimed", "capsule_persistence_enabled", "tomb_completion_claimed", "tomb_completion_enabled", "protection_application_claimed", "protection_application_enabled", "merge_application_claimed", "merge_application_enabled"):
        if _flag(claims, "live_memory_write_claimed", "live_memory_write_enabled"): return "live_write_claim"
        if _flag(claims, "live_memory_delete_claimed", "live_memory_deletion_enabled"): return "live_delete_claim"
        if _flag(claims, "live_memory_purge_claimed", "live_memory_purge_enabled"): return "live_purge_claim"
        if _flag(claims, "live_index_mutation_claimed", "live_index_mutation_enabled"): return "index_mutation_claim"
        if _flag(claims, "capsule_persistence_claimed", "capsule_persistence_enabled"): return "capsule_persistence_claim"
        if _flag(claims, "tomb_completion_claimed", "tomb_completion_enabled"): return "tomb_completion_claim"
        if _flag(claims, "protection_application_claimed", "protection_application_enabled"): return "protection_application_claim"
        if _flag(claims, "merge_application_claimed", "merge_application_enabled"): return "merge_application_claim"
        return "live_mutation_claim"
    if policy.block_real_memory_root_access_claims and _flag(claims, "real_memory_root_access_claimed", "real_memory_root_write_enabled", "touch_real_memory_root", "open_real_memory_path_for_write"):
        return "real_memory_root_access_claim"
    if policy.block_runtime_execution_claims and _flag(claims, "runtime_execution_claimed", "live_commit_execution_claimed", "live_executor_enabled", "live_commit_executed", "ordered_operations_executed"):
        return "runtime_execution_claim"
    if policy.block_executor_permission_claims and _flag(claims, "preflight_packet_grants_permission", "permission_to_execute_now", "authority_to_execute_now", "lock_lease_gate_grants_permission", "executor_plan_grants_permission"):
        return "executor_permission_claim"
    if policy.block_readiness_conversion_claims and _flag(claims, "readiness_envelope_is_runtime_permission", "readiness_envelope_is_execution_permission", "runtime_execution_gate_is_execution"):
        return "readiness_conversion_claim"
    if policy.block_final_review_conversion_claims and _flag(claims, "final_review_is_execution_permission", "final_review_is_real_commit"):
        return "final_review_conversion_claim"
    if policy.block_sandbox_conversion_claims and _flag(claims, "sandbox_commit_is_real_commit", "sandbox_receipt_is_live_receipt", "sandbox_rollback_is_applied_rollback"):
        return "sandbox_conversion_claim"
    if policy.block_real_root_admission_conversion_claims and _flag(claims, "real_root_admission_is_memory_root_access", "real_root_admission_grants_access"):
        return "real_root_admission_conversion_claim"
    if policy.block_prompt_materialization and _flag(claims, "prompt_assembly_claimed", "prompt_materialization_enabled", "assemble_prompt_now"):
        return "prompt_materialization"
    if policy.block_live_context_retrieval and _flag(claims, "live_context_retrieval_claimed", "live_context_retrieval_enabled"):
        return "live_context_retrieval"
    if policy.block_action_execution and _flag(claims, "action_execution_claimed", "action_execution_enabled", "execute_action_ingress"):
        return "action_execution"
    if policy.block_external_disclosure and _flag(claims, "external_disclosure_claimed", "external_disclosure_enabled", "remote_service_enabled"):
        return "external_disclosure"
    if policy.block_authority_smuggling and _flag(claims, "authority_claimed", "authority_granted"):
        return "authority_smuggling"
    if policy.block_consent_smuggling and _flag(claims, "consent_claimed", "consent_granted"):
        return "consent_smuggling"
    if policy.block_policy_smuggling and _flag(claims, "policy_claimed", "policy_created"):
        return "policy_smuggling"
    if policy.block_truth_smuggling and _flag(claims, "truth_claimed", "truth_created"):
        return "truth_smuggling"
    if policy.block_raw_payload_leakage and _has_raw_payload(all_data):
        return "raw_payload_leak"
    return None


def _decision_for(candidate: PreflightCandidate, lock_decision: str, warning: bool) -> PreflightDecision:
    if _is_noop(candidate, lock_decision):
        return "preflight_noop"
    if candidate.candidate_type == "operator_review_preflight_candidate":
        return "preflight_deferred_for_operator_review"
    if warning or lock_decision == "lock_lease_ready_with_warnings":
        return "preflight_ready_with_warnings"
    return "preflight_ready_for_later_live_executor"


def _safe_actions(decision: str) -> tuple[str, ...]:
    base = ["no_action_allowed", "inspect_live_executor_preflight_packet", "inspect_live_executor_lock_lease_gate_packet", "inspect_real_live_memory_commit_executor_plan_packet", "sustain_default_deny"]
    if decision in {"preflight_ready_for_later_live_executor", "preflight_ready_with_warnings"}:
        base.extend(["prepare_future_real_live_memory_commit_executor_later", "prepare_future_executor_activation_record_later", "prepare_future_post_execution_audit_later"])
    if decision == "preflight_deferred_for_operator_review":
        base.append("operator_review_required")
    return tuple(base)


def _metadata_record(kind: str, candidate: PreflightCandidate, metadata: Mapping[str, Any], *, ready_key: str) -> Mapping[str, Any]:
    return {
        "record_type": kind,
        "candidate_id": candidate.candidate_id,
        "record_id": candidate.record_id,
        "metadata_only": True,
        ready_key: True,
        "operation_intents_only": kind == "operation_inventory",
        "receipt_targets_are_metadata_only": kind in {"operation_inventory", "verification_checklist"},
        "rollback_targets_are_metadata_only": kind in {"operation_inventory", "rollback_readiness"},
        "preflight_execution_performed": False,
        "lock_acquired": False,
        "lockfile_created": False,
        "live_commit_executed": False,
        "real_memory_root_access_performed": False,
        "metadata": dict(metadata),
    }


def evaluate_live_executor_preflight_packet(payload: Mapping[str, Any], policy: PreflightPolicy | None = None) -> PreflightResult:
    try:
        active_policy = _policy_from_payload(payload, policy)
        policy_validation = validate_policy(active_policy)
        if policy_validation["status"] != "valid":
            return _blocked("invalid_policy", tuple(PreflightFinding("error", f["code"], f["message"]) for f in policy_validation["findings"]))
        lock_packet = _lock_lease_packet(payload)
        if not lock_packet:
            return _blocked("missing_lock_lease_gate_packet")
        records_raw = tuple(item for item in _as_sequence(lock_packet.get("records")) if isinstance(item, Mapping))
        if not records_raw or not str(lock_packet.get("digest") or "").startswith("sha256:"):
            return _blocked("invalid_lock_lease_gate_packet")
        candidates_raw = _candidate_payloads(payload)
        if not candidates_raw:
            return _blocked("missing_preflight_candidate")
        lock_digest = str(lock_packet.get("digest") or "")
        findings: list[PreflightFinding] = []
        records: list[PreflightRecord] = []
        for raw in candidates_raw:
            candidate = PreflightCandidate.from_mapping(raw)
            if not candidate.candidate_id or candidate.candidate_type not in PREFLIGHT_CANDIDATE_TYPES:
                return _blocked("invalid_preflight_candidate", [PreflightFinding("error", "invalid_preflight_candidate", "preflight candidate is missing an id or supported type", candidate.candidate_id, candidate.record_id)])
            lock_record = records_raw[0]
            lock_decision = str(lock_record.get("lock_lease_decision") or "")
            if active_policy.require_ready_lock_lease_gate_packet and lock_decision not in READY_LOCK_LEASE_DECISIONS:
                return _blocked("lock_lease_gate_not_ready", [PreflightFinding("error", "lock_lease_gate_not_ready", "lock lease gate packet is not ready for preflight consideration", candidate.candidate_id, candidate.record_id)])
            checks: tuple[tuple[bool, str, str, str], ...] = (
                (active_policy.require_matching_lock_lease_gate_digest, "lock_lease_gate_digest_mismatch", candidate.claimed_lock_lease_gate_packet_digest, lock_digest),
                (active_policy.require_matching_lock_lease_gate_decision, "lock_lease_gate_decision_mismatch", candidate.claimed_lock_lease_gate_decision, lock_decision),
                (active_policy.require_matching_executor_plan_packet_digest, "executor_plan_digest_mismatch", candidate.claimed_executor_plan_packet_digest, str(lock_record.get("executor_plan_packet_digest") or "")),
                (active_policy.require_matching_executor_plan_decision, "executor_plan_decision_mismatch", candidate.claimed_executor_plan_decision, str(lock_record.get("executor_plan_decision") or "")),
                (active_policy.require_matching_runtime_execution_gate_digest, "runtime_execution_gate_digest_mismatch", candidate.claimed_runtime_execution_gate_digest, str(lock_record.get("runtime_execution_gate_digest") or "")),
                (active_policy.require_matching_runtime_execution_gate_decision, "runtime_execution_gate_decision_mismatch", candidate.claimed_runtime_execution_gate_decision, str(lock_record.get("runtime_execution_gate_decision") or "")),
                (active_policy.require_matching_readiness_envelope_digest, "readiness_envelope_digest_mismatch", candidate.claimed_readiness_envelope_digest, str(lock_record.get("readiness_envelope_digest") or "")),
                (active_policy.require_matching_readiness_envelope_decision, "readiness_envelope_decision_mismatch", candidate.claimed_readiness_envelope_decision, str(lock_record.get("readiness_envelope_decision") or "")),
                (active_policy.require_matching_final_review_digest, "final_review_digest_mismatch", candidate.claimed_final_review_digest, str(lock_record.get("final_review_digest") or "")),
                (active_policy.require_matching_final_review_decision, "final_review_decision_mismatch", candidate.claimed_final_review_decision, str(lock_record.get("final_review_decision") or "")),
                (active_policy.require_matching_real_root_admission_digest, "real_root_admission_digest_mismatch", candidate.claimed_real_root_admission_digest, str(lock_record.get("real_root_admission_digest") or "")),
                (active_policy.require_matching_real_root_admission_decision, "real_root_admission_decision_mismatch", candidate.claimed_real_root_admission_decision, str(lock_record.get("real_root_admission_decision") or "")),
                (active_policy.require_matching_sandbox_commit_digest, "sandbox_commit_digest_mismatch", candidate.claimed_sandbox_commit_digest, str(lock_record.get("sandbox_commit_digest") or "")),
                (active_policy.require_matching_sandbox_commit_decision, "sandbox_commit_decision_mismatch", candidate.claimed_sandbox_commit_decision, str(lock_record.get("sandbox_commit_decision") or "")),
            )
            for required, code, actual, expected in checks:
                if required and actual != expected:
                    return _blocked(code, [PreflightFinding("error", code, f"{code}: expected {expected}", candidate.candidate_id, candidate.record_id)])
            if not _is_noop(candidate, lock_decision):
                missing = _require_non_noop_metadata(candidate, active_policy)
                if missing:
                    return _blocked(missing, [PreflightFinding("error", missing, missing.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            forbidden = _forbidden_claim(candidate, active_policy, raw)
            if forbidden:
                return _blocked(forbidden, [PreflightFinding("error", forbidden, forbidden.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            lock_scope = _as_tuple(lock_record.get("operator_scope_keys"))
            executor_scope = _as_tuple(lock_record.get("executor_plan_scope_keys"))
            runtime_scope = _as_tuple(lock_record.get("runtime_scope_keys"))
            readiness_scope = _as_tuple(lock_record.get("readiness_scope_keys"))
            final_scope = _as_tuple(lock_record.get("final_review_scope_keys"))
            real_scope = _as_tuple(lock_record.get("real_root_admission_scope_keys"))
            sandbox_scope = _as_tuple(lock_record.get("sandbox_scope_keys"))
            if active_policy.require_scope_alignment:
                scopes = [scope for scope in (candidate.operator_scope_keys, lock_scope, executor_scope, runtime_scope, readiness_scope, final_scope, real_scope, sandbox_scope) if scope]
                aligned = all(scope == scopes[0] for scope in scopes) if scopes else False
                if not aligned:
                    if active_policy.allow_mixed_scope_diagnostic_packet and candidate.candidate_type == "mixed_preflight_candidate" and candidate.metadata.get("diagnostic_warning") is True:
                        findings.append(PreflightFinding("warning", "scope_mismatch_diagnostic", "scope mismatch allowed for diagnostic packet", candidate.candidate_id, candidate.record_id))
                    else:
                        return _blocked("scope_mismatch", [PreflightFinding("error", "scope_mismatch", "scope mismatch", candidate.candidate_id, candidate.record_id)])
            warning = bool(candidate.metadata.get("warning_only") or candidate.metadata.get("diagnostic_warning")) or lock_decision.endswith("with_warnings") or any(f.severity == "warning" and f.candidate_id == candidate.candidate_id for f in findings)
            if warning:
                findings.append(PreflightFinding("warning", "preflight_warning", "candidate is warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
            decision = _decision_for(candidate, lock_decision, warning)
            records.append(PreflightRecord(
                candidate.candidate_id, candidate.record_id, candidate.candidate_type, decision, lock_digest, lock_decision,
                str(lock_record.get("digest") or ""), candidate.claimed_executor_plan_packet_digest, candidate.claimed_executor_plan_decision,
                candidate.claimed_runtime_execution_gate_digest, candidate.claimed_runtime_execution_gate_decision,
                candidate.claimed_readiness_envelope_digest, candidate.claimed_readiness_envelope_decision,
                candidate.claimed_final_review_digest, candidate.claimed_final_review_decision,
                candidate.claimed_real_root_admission_digest, candidate.claimed_real_root_admission_decision,
                candidate.claimed_sandbox_commit_digest, candidate.claimed_sandbox_commit_decision, candidate.operator_scope_keys,
                lock_scope, executor_scope, runtime_scope, readiness_scope, final_scope, real_scope, sandbox_scope,
                dict(candidate.operation_list_digest_metadata), dict(candidate.operation_inventory_metadata), dict(candidate.operation_ordering_metadata),
                dict(candidate.per_operation_precondition_metadata), dict(candidate.per_operation_receipt_target_metadata), dict(candidate.per_operation_rollback_target_metadata),
                dict(candidate.lock_lease_readiness_metadata), dict(candidate.lease_duration_metadata), dict(candidate.lock_owner_metadata),
                dict(candidate.operator_identity_role_metadata), dict(candidate.execution_window_metadata), dict(candidate.idempotency_key_metadata),
                dict(candidate.atomicity_boundary_metadata), dict(candidate.dry_run_to_live_equivalence_metadata), dict(candidate.rollback_rehearsal_metadata),
                dict(candidate.post_execution_audit_metadata), dict(candidate.verification_checklist_metadata), dict(candidate.abort_panic_stop_condition_metadata),
                dict(candidate.contamination_check_metadata), dict(candidate.generated_artifact_cleanup_expectation_metadata), dict(candidate.final_clean_tree_expectation_metadata),
                dict(candidate.future_executor_requirement_metadata),
                (_metadata_record("final_preflight_readiness", candidate, candidate.future_executor_requirement_metadata, ready_key="ready_for_later_executor_preflight_review"),),
                (_metadata_record("operation_inventory", candidate, candidate.operation_inventory_metadata, ready_key="operation_inventory_recorded"),),
                (_metadata_record("safety_checklist", candidate, candidate.contamination_check_metadata, ready_key="safety_checklist_recorded"),),
                (_metadata_record("verification_checklist", candidate, candidate.verification_checklist_metadata, ready_key="verification_checklist_recorded"),),
                (_metadata_record("abort_readiness", candidate, candidate.abort_panic_stop_condition_metadata, ready_key="abort_ready_for_later_executor_consideration"),),
                (_metadata_record("rollback_readiness", candidate, candidate.rollback_rehearsal_metadata, ready_key="rollback_ready_for_later_executor_consideration"),),
                (_metadata_record("audit_readiness", candidate, candidate.post_execution_audit_metadata, ready_key="audit_ready_for_later_executor_consideration"),),
                _safe_actions(decision),
            ).with_digest())
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for finding in findings if finding.severity == "warning")}
        for record in records:
            counts[record.preflight_decision] = counts.get(record.preflight_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {record.preflight_decision for record in records}
        if counts["warning_count"] or "preflight_ready_with_warnings" in decisions:
            status: PreflightStatus = "preflight_ready_with_warnings"
        elif decisions <= {"preflight_noop"}:
            status = "preflight_noop"
        elif decisions <= {"preflight_deferred_for_operator_review"}:
            status = "preflight_deferred_for_operator_review"
        else:
            status = "preflight_ready"
        packet = PreflightPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = PreflightReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return PreflightResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("failed", [PreflightFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: PreflightPolicy | None = None) -> PreflightResult:
    return evaluate_live_executor_preflight_packet(payload, policy)


__all__ = [
    "FAIL_STATUSES", "FORBIDDEN_NEXT_STEPS", "INVARIANTS", "PREFLIGHT_CANDIDATE_TYPES", "READY_LOCK_LEASE_DECISIONS",
    "PreflightCandidate", "PreflightFinding", "PreflightPacket", "PreflightPolicy", "PreflightRecord", "PreflightReport", "PreflightResult",
    "build_default_policy", "validate_policy", "evaluate_live_executor_preflight_packet", "evaluate_packet",
]
