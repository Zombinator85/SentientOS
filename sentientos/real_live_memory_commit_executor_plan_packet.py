"""Deterministic metadata-only real live-memory commit executor plan packets.

This module consumes supplied Explicit Live Memory Runtime Execution Gate packets
and explicit executor-plan candidates to build reviewable operation-intent plans
for a later real live-memory commit executor. It never writes, deletes, purges,
indexes, persists capsules, completes tombs, applies protection or merge
operations, assembles prompts, retrieves live context, executes actions,
discloses externally, invokes remote services, touches real memory roots, grants
truth, creates policy, infers consent, or grants authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Mapping, Sequence

ExecutorPlanStatus = Literal[
    "executor_plan_ready",
    "executor_plan_ready_with_warnings",
    "executor_plan_deferred_for_operator_review",
    "executor_plan_rejected",
    "executor_plan_blocked",
    "executor_plan_noop",
    "executor_plan_invalid",
    "executor_plan_failed",
]
ExecutorPlanDecision = Literal[
    "executor_plan_ready_for_later_live_executor",
    "executor_plan_ready_with_warnings",
    "executor_plan_deferred_for_operator_review",
    "executor_plan_rejected",
    "executor_plan_blocked",
    "executor_plan_noop",
]

EXECUTOR_PLAN_CANDIDATE_TYPES = frozenset({
    "ai_capsule_executor_plan_candidate",
    "human_summary_executor_plan_candidate",
    "dual_capsule_executor_plan_candidate",
    "protect_receipt_executor_plan_candidate",
    "merge_receipt_executor_plan_candidate",
    "tomb_archive_executor_plan_candidate",
    "tomb_deferred_executor_plan_candidate",
    "operator_review_executor_plan_candidate",
    "noop_executor_plan_candidate",
    "mixed_executor_plan_candidate",
})
READY_RUNTIME_EXECUTION_GATE_DECISIONS = frozenset({
    "runtime_execution_gate_ready_for_later_live_executor",
    "runtime_execution_gate_ready_with_warnings",
    "runtime_execution_gate_noop",
})

INVARIANTS: dict[str, bool] = {
    "executor_plan_is_not_memory_write": True,
    "executor_plan_is_not_memory_deletion": True,
    "executor_plan_is_not_memory_purge": True,
    "executor_plan_is_not_index_mutation": True,
    "executor_plan_is_not_capsule_persistence": True,
    "executor_plan_is_not_tomb_completion": True,
    "executor_plan_is_not_prompt_assembly": True,
    "executor_plan_is_not_live_context_retrieval": True,
    "executor_plan_is_not_action_execution": True,
    "executor_plan_is_not_external_disclosure": True,
    "executor_plan_is_not_live_commit_execution": True,
    "executor_plan_is_not_truth": True,
    "executor_plan_is_not_policy": True,
    "executor_plan_is_not_authority": True,
    "executor_plan_is_not_consent": True,
    "ordered_operations_are_intents_only": True,
    "receipt_targets_are_metadata_only": True,
    "rollback_targets_are_metadata_only": True,
    "verification_steps_are_metadata_only": True,
    "abort_conditions_are_metadata_only": True,
    "audit_expectations_are_metadata_only": True,
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
    "future_live_executor_lock_gate_required": True,
    "future_post_execution_audit_required": True,
}
SAFE_NEXT_ACTIONS = (
    "no_action_allowed", "inspect_executor_plan_packet", "inspect_explicit_live_memory_runtime_execution_gate_packet",
    "inspect_real_live_memory_commit_adapter_readiness_envelope_packet", "inspect_final_live_memory_commit_review_packet",
    "inspect_real_memory_root_admission_packet", "inspect_sandboxed_live_memory_commit_adapter_packet",
    "operator_review_required", "prepare_future_real_live_memory_commit_executor_later", "prepare_future_live_executor_lock_gate_later",
    "prepare_future_post_execution_audit_later", "rerun_with_ready_runtime_execution_gate_packet", "rerun_with_matching_runtime_execution_gate_digest",
    "rerun_with_matching_runtime_execution_gate_decision", "rerun_with_matching_readiness_envelope_digest", "rerun_with_matching_readiness_envelope_decision",
    "rerun_with_matching_final_review_digest", "rerun_with_matching_final_review_decision", "rerun_with_matching_real_root_admission_digest",
    "rerun_with_matching_real_root_admission_decision", "rerun_with_matching_sandbox_commit_digest", "rerun_with_matching_sandbox_commit_decision",
    "rerun_with_sandbox_receipt_manifest_digest", "rerun_with_sandbox_rollback_manifest_digest", "rerun_with_sandbox_artifact_plan",
    "rerun_with_live_receipt_schema_metadata", "rerun_with_live_rollback_schema_metadata", "rerun_with_post_commit_verification_plan",
    "rerun_with_abort_panic_stop_condition_metadata", "rerun_with_operator_runtime_confirmation_metadata", "rerun_with_operator_identity_role_metadata",
    "rerun_with_execution_window_metadata", "rerun_with_dry_run_to_live_equivalence_metadata", "rerun_with_rollback_rehearsal_metadata",
    "rerun_with_post_execution_audit_metadata", "rerun_with_executor_plan_operation_list", "rerun_with_operation_ordering_metadata",
    "rerun_with_per_operation_precondition_metadata", "rerun_with_receipt_target_metadata", "rerun_with_rollback_target_metadata",
    "rerun_with_lock_lease_expectation_metadata", "rerun_with_idempotency_key_metadata", "rerun_with_atomicity_boundary_metadata",
    "rerun_with_failure_mode_classification_metadata", "rerun_with_scope_alignment", "sustain_default_deny",
)
FORBIDDEN_NEXT_STEPS = (
    "write_live_memory_now", "delete_live_memory_now", "purge_live_memory_now", "mutate_vector_index", "mutate_live_index",
    "persist_capsule_now", "persist_summary_now", "apply_protection_now", "apply_merge_now", "complete_tomb_now",
    "run_real_live_commit_executor_now", "treat_executor_plan_as_permission_to_execute_now", "treat_ordered_operations_as_executed_operations",
    "treat_runtime_execution_gate_as_execution", "treat_runtime_execution_gate_as_permission_to_execute_now", "treat_readiness_envelope_as_runtime_execution_permission",
    "treat_final_review_as_execution_permission", "treat_real_root_admission_as_memory_root_access", "treat_sandbox_commit_as_real_commit",
    "treat_sandbox_receipt_as_live_receipt", "treat_sandbox_rollback_as_applied_rollback", "touch_real_memory_root",
    "open_real_memory_path_for_write", "assemble_prompt_now", "retrieve_live_context", "execute_action_ingress", "disclose_externally",
    "infer_truth_from_plan", "infer_authority_from_plan", "infer_consent_from_plan", "convert_plan_to_policy", "bypass_runtime_execution_gate",
    "bypass_readiness_envelope", "bypass_final_live_commit_review_gate", "bypass_real_root_admission_gate", "bypass_sandbox_commit_adapter",
    "direct_executor_invocation", "enable_external_disclosure",
)


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
class ExecutorPlanPolicy:
    schema_version: str = "real-live-memory-commit-executor-plan-packet/v1"
    default_posture: str = "deny"
    require_ready_runtime_execution_gate: bool = True
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
    require_non_noop_sandbox_receipt_manifest_digest: bool = True
    require_non_noop_sandbox_rollback_manifest_digest: bool = True
    require_non_noop_sandbox_artifact_plan: bool = True
    require_non_noop_live_receipt_schema_metadata: bool = True
    require_non_noop_live_rollback_schema_metadata: bool = True
    require_non_noop_post_commit_verification_plan: bool = True
    require_non_noop_abort_panic_stop_condition_metadata: bool = True
    require_non_noop_operator_runtime_confirmation_metadata: bool = True
    require_non_noop_operator_identity_role_metadata: bool = True
    require_non_noop_execution_window_metadata: bool = True
    require_non_noop_dry_run_to_live_equivalence_metadata: bool = True
    require_non_noop_rollback_rehearsal_metadata: bool = True
    require_non_noop_post_execution_audit_metadata: bool = True
    require_non_noop_executor_plan_operation_list: bool = True
    require_non_noop_operation_ordering_metadata: bool = True
    require_non_noop_per_operation_precondition_metadata: bool = True
    require_non_noop_per_operation_receipt_target_metadata: bool = True
    require_non_noop_per_operation_rollback_target_metadata: bool = True
    require_non_noop_lock_lease_expectation_metadata: bool = True
    require_non_noop_idempotency_key_metadata: bool = True
    require_non_noop_atomicity_boundary_metadata: bool = True
    require_non_noop_failure_mode_classification_metadata: bool = True
    require_scope_alignment: bool = True
    allow_mixed_scope_diagnostic_packet: bool = True
    block_live_mutation_claims: bool = True
    block_real_memory_root_access_claims: bool = True
    block_runtime_execution_claims: bool = True
    block_readiness_conversion_claims: bool = True
    block_final_review_conversion_claims: bool = True
    block_sandbox_conversion_claims: bool = True
    block_real_root_admission_conversion_claims: bool = True
    block_executor_permission_claims: bool = True
    block_prompt_materialization: bool = True
    block_live_context_retrieval: bool = True
    block_action_execution: bool = True
    block_external_disclosure: bool = True
    block_authority_smuggling: bool = True
    block_consent_smuggling: bool = True
    block_policy_smuggling: bool = True
    block_truth_smuggling: bool = True
    block_raw_payload_leakage: bool = True
    live_executor_enabled: bool = False
    future_live_executor_lock_gate_required: bool = True
    future_post_execution_audit_required: bool = True


@dataclass(frozen=True)
class ExecutorPlanFinding:
    severity: str
    code: str
    message: str
    candidate_id: str = ""
    record_id: str = ""
    operation_id: str = ""
    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class ExecutorPlanCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
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
    claimed_sandbox_receipt_manifest_digest: str
    claimed_sandbox_rollback_manifest_digest: str
    operator_scope_keys: tuple[str, ...]
    sandbox_artifact_plan: Mapping[str, Any]
    live_receipt_schema_metadata: Mapping[str, Any]
    live_rollback_schema_metadata: Mapping[str, Any]
    post_commit_verification_plan: Mapping[str, Any]
    abort_panic_stop_condition_metadata: Mapping[str, Any]
    operator_runtime_confirmation_metadata: Mapping[str, Any]
    operator_identity_role_metadata: Mapping[str, Any]
    execution_window_metadata: Mapping[str, Any]
    dry_run_to_live_equivalence_metadata: Mapping[str, Any]
    rollback_rehearsal_metadata: Mapping[str, Any]
    post_execution_audit_metadata: Mapping[str, Any]
    executor_plan_operations: tuple[Mapping[str, Any], ...]
    operation_ordering_metadata: Mapping[str, Any]
    lock_lease_expectation_metadata: Mapping[str, Any]
    idempotency_key_metadata: Mapping[str, Any]
    atomicity_boundary_metadata: Mapping[str, Any]
    failure_mode_classification_metadata: Mapping[str, Any]
    executor_plan_claims: Mapping[str, Any]
    metadata: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ExecutorPlanCandidate":
        return cls(
            candidate_id=str(raw.get("candidate_id") or ""), record_id=str(raw.get("record_id") or raw.get("candidate_id") or ""), candidate_type=str(raw.get("candidate_type") or ""),
            claimed_runtime_execution_gate_digest=str(raw.get("claimed_runtime_execution_gate_digest") or raw.get("runtime_execution_gate_digest") or ""),
            claimed_runtime_execution_gate_decision=str(raw.get("claimed_runtime_execution_gate_decision") or raw.get("runtime_execution_gate_decision") or ""),
            claimed_readiness_envelope_digest=str(raw.get("claimed_readiness_envelope_digest") or raw.get("readiness_envelope_digest") or ""),
            claimed_readiness_envelope_decision=str(raw.get("claimed_readiness_envelope_decision") or raw.get("readiness_decision") or raw.get("readiness_envelope_decision") or ""),
            claimed_final_review_digest=str(raw.get("claimed_final_review_digest") or raw.get("final_review_digest") or ""),
            claimed_final_review_decision=str(raw.get("claimed_final_review_decision") or raw.get("final_review_decision") or ""),
            claimed_real_root_admission_digest=str(raw.get("claimed_real_root_admission_digest") or raw.get("real_root_admission_digest") or ""),
            claimed_real_root_admission_decision=str(raw.get("claimed_real_root_admission_decision") or raw.get("real_root_admission_decision") or ""),
            claimed_sandbox_commit_digest=str(raw.get("claimed_sandbox_commit_digest") or raw.get("sandbox_commit_digest") or ""),
            claimed_sandbox_commit_decision=str(raw.get("claimed_sandbox_commit_decision") or raw.get("sandbox_commit_decision") or ""),
            claimed_sandbox_receipt_manifest_digest=str(raw.get("claimed_sandbox_receipt_manifest_digest") or raw.get("sandbox_receipt_manifest_digest") or ""),
            claimed_sandbox_rollback_manifest_digest=str(raw.get("claimed_sandbox_rollback_manifest_digest") or raw.get("sandbox_rollback_manifest_digest") or ""),
            operator_scope_keys=_as_tuple(raw.get("operator_scope_keys")), sandbox_artifact_plan=_as_mapping(raw.get("sandbox_artifact_plan")),
            live_receipt_schema_metadata=_as_mapping(raw.get("live_receipt_schema_metadata")), live_rollback_schema_metadata=_as_mapping(raw.get("live_rollback_schema_metadata")),
            post_commit_verification_plan=_as_mapping(raw.get("post_commit_verification_plan")), abort_panic_stop_condition_metadata=_as_mapping(raw.get("abort_panic_stop_condition_metadata") or raw.get("abort_panic_stop_condition_plan")),
            operator_runtime_confirmation_metadata=_as_mapping(raw.get("operator_runtime_confirmation_metadata")), operator_identity_role_metadata=_as_mapping(raw.get("operator_identity_role_metadata")),
            execution_window_metadata=_as_mapping(raw.get("execution_window_metadata")), dry_run_to_live_equivalence_metadata=_as_mapping(raw.get("dry_run_to_live_equivalence_metadata")),
            rollback_rehearsal_metadata=_as_mapping(raw.get("rollback_rehearsal_metadata")), post_execution_audit_metadata=_as_mapping(raw.get("post_execution_audit_metadata")),
            executor_plan_operations=tuple(item for item in _as_sequence(raw.get("executor_plan_operations") or raw.get("operations")) if isinstance(item, Mapping)),
            operation_ordering_metadata=_as_mapping(raw.get("operation_ordering_metadata")), lock_lease_expectation_metadata=_as_mapping(raw.get("lock_lease_expectation_metadata")),
            idempotency_key_metadata=_as_mapping(raw.get("idempotency_key_metadata")), atomicity_boundary_metadata=_as_mapping(raw.get("atomicity_boundary_metadata")),
            failure_mode_classification_metadata=_as_mapping(raw.get("failure_mode_classification_metadata")), executor_plan_claims=_as_mapping(raw.get("executor_plan_claims") or raw.get("claims")), metadata=_as_mapping(raw.get("metadata")),
        )
    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class ExecutorPlanRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    executor_plan_decision: ExecutorPlanDecision
    runtime_execution_gate_decision: str
    runtime_execution_gate_digest: str
    runtime_execution_gate_record_digest: str
    readiness_envelope_decision: str
    readiness_envelope_digest: str
    final_review_decision: str
    final_review_digest: str
    real_root_admission_decision: str
    real_root_admission_digest: str
    sandbox_commit_decision: str
    sandbox_commit_digest: str
    sandbox_receipt_manifest_digest: str
    sandbox_rollback_manifest_digest: str
    operator_scope_keys: tuple[str, ...]
    runtime_scope_keys: tuple[str, ...]
    readiness_scope_keys: tuple[str, ...]
    final_review_scope_keys: tuple[str, ...]
    real_root_admission_scope_keys: tuple[str, ...]
    sandbox_scope_keys: tuple[str, ...]
    sandbox_artifact_plan: Mapping[str, Any]
    ordered_operation_intent_records: tuple[Mapping[str, Any], ...]
    precondition_records: tuple[Mapping[str, Any], ...]
    receipt_target_records: tuple[Mapping[str, Any], ...]
    rollback_target_records: tuple[Mapping[str, Any], ...]
    verification_step_records: tuple[Mapping[str, Any], ...]
    abort_condition_records: tuple[Mapping[str, Any], ...]
    audit_expectation_records: tuple[Mapping[str, Any], ...]
    live_receipt_schema_metadata: Mapping[str, Any]
    live_rollback_schema_metadata: Mapping[str, Any]
    post_commit_verification_plan: Mapping[str, Any]
    abort_panic_stop_condition_metadata: Mapping[str, Any]
    operator_runtime_confirmation_metadata: Mapping[str, Any]
    operator_identity_role_metadata: Mapping[str, Any]
    execution_window_metadata: Mapping[str, Any]
    dry_run_to_live_equivalence_metadata: Mapping[str, Any]
    rollback_rehearsal_metadata: Mapping[str, Any]
    post_execution_audit_metadata: Mapping[str, Any]
    operation_ordering_metadata: Mapping[str, Any]
    lock_lease_expectation_metadata: Mapping[str, Any]
    idempotency_key_metadata: Mapping[str, Any]
    atomicity_boundary_metadata: Mapping[str, Any]
    failure_mode_classification_metadata: Mapping[str, Any]
    safe_next_actions: tuple[str, ...]
    future_live_executor_consideration_record: Mapping[str, Any]
    executor_plan_future_consideration_only: bool = True
    executor_plan_is_runtime_execution_permission: bool = False
    executor_plan_has_executed_live_commit: bool = False
    ordered_operations_are_intents_only: bool = True
    receipt_targets_are_metadata_only: bool = True
    rollback_targets_are_metadata_only: bool = True
    verification_steps_are_metadata_only: bool = True
    abort_conditions_are_metadata_only: bool = True
    audit_expectations_are_metadata_only: bool = True
    digest: str = ""
    def to_dict(self) -> dict[str, Any]: return asdict(self)
    def with_digest(self) -> "ExecutorPlanRecord":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class ExecutorPlanPacket:
    schema_version: str
    records: tuple[ExecutorPlanRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""
    executor_plan_is_not_memory_write: bool = True
    executor_plan_is_not_memory_deletion: bool = True
    executor_plan_is_not_memory_purge: bool = True
    executor_plan_is_not_index_mutation: bool = True
    executor_plan_is_not_capsule_persistence: bool = True
    executor_plan_is_not_tomb_completion: bool = True
    executor_plan_is_not_prompt_assembly: bool = True
    executor_plan_is_not_live_context_retrieval: bool = True
    executor_plan_is_not_action_execution: bool = True
    executor_plan_is_not_external_disclosure: bool = True
    executor_plan_is_not_live_commit_execution: bool = True
    executor_plan_is_not_truth: bool = True
    executor_plan_is_not_policy: bool = True
    executor_plan_is_not_authority: bool = True
    executor_plan_is_not_consent: bool = True
    ordered_operations_are_intents_only: bool = True
    receipt_targets_are_metadata_only: bool = True
    rollback_targets_are_metadata_only: bool = True
    verification_steps_are_metadata_only: bool = True
    abort_conditions_are_metadata_only: bool = True
    audit_expectations_are_metadata_only: bool = True
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
    future_live_executor_lock_gate_required: bool = True
    future_post_execution_audit_required: bool = True
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self); data["records"] = [record.to_dict() for record in self.records]; return data
    def with_digest(self) -> "ExecutorPlanPacket":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class ExecutorPlanReport:
    status: ExecutorPlanStatus
    findings: tuple[ExecutorPlanFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""
    def to_dict(self) -> dict[str, Any]: return {"status": self.status, "findings": [finding.to_dict() for finding in self.findings], "summary_counts": dict(sorted(self.summary_counts.items())), "digest": self.digest}


@dataclass(frozen=True)
class ExecutorPlanResult:
    status: ExecutorPlanStatus
    packet: ExecutorPlanPacket | None
    report: ExecutorPlanReport
    digest: str
    def to_dict(self) -> dict[str, Any]: return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> ExecutorPlanPolicy: return ExecutorPlanPolicy()


def validate_policy(policy: ExecutorPlanPolicy | Mapping[str, Any] | None = None) -> dict[str, Any]:
    raw = asdict(policy) if isinstance(policy, ExecutorPlanPolicy) else dict(policy or asdict(build_default_policy()))
    findings: list[dict[str, str]] = []
    if raw.get("default_posture") != "deny": findings.append({"severity": "error", "code": "default_posture_not_deny", "message": "executor plan packet must default deny"})
    for key, expected in INVARIANTS.items():
        if raw.get(key, expected) != expected: findings.append({"severity": "error", "code": f"invariant_{key}_changed", "message": f"{key} must remain {expected}"})
    if raw.get("live_executor_enabled") is not False: findings.append({"severity": "error", "code": "live_executor_enabled", "message": "live executor must remain disabled"})
    status = "invalid" if findings else "valid"
    return {"status": status, "findings": findings, "policy": raw, "digest": _digest({"status": status, "findings": findings, "policy": raw})}


def _policy_from_payload(payload: Mapping[str, Any], policy: ExecutorPlanPolicy | None) -> ExecutorPlanPolicy:
    if policy is not None:
        return policy
    raw_policy = payload.get("policy")
    if isinstance(raw_policy, Mapping):
        allowed = {field for field in ExecutorPlanPolicy.__dataclass_fields__}
        return ExecutorPlanPolicy(**{key: value for key, value in raw_policy.items() if key in allowed})
    return build_default_policy()


def _runtime_packet(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    return _as_mapping(payload.get("explicit_live_memory_runtime_execution_gate_packet") or payload.get("runtime_execution_gate_packet") or payload.get("packet"))


def _candidate_payloads(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = payload.get("executor_plan_candidates", payload.get("executor_plan_candidate", payload.get("candidates", ())))
    if isinstance(raw, Mapping):
        return (raw,)
    return tuple(item for item in _as_sequence(raw) if isinstance(item, Mapping))


def _blocked(code: str, findings: Sequence[ExecutorPlanFinding] = ()) -> ExecutorPlanResult:
    base = tuple(findings) or (ExecutorPlanFinding("error", code, code.replace("_", " ")),)
    report = ExecutorPlanReport("executor_plan_blocked", base, {"error_count": sum(1 for f in base if f.severity == "error")})
    report = replace(report, digest=_digest(report.to_dict()))
    return ExecutorPlanResult("executor_plan_blocked", None, report, _digest({"status": "executor_plan_blocked", "report": report.to_dict()}))


def _is_noop(candidate: ExecutorPlanCandidate, runtime_decision: str) -> bool:
    return candidate.candidate_type == "noop_executor_plan_candidate" or runtime_decision == "runtime_execution_gate_noop"


def _require_non_noop_metadata(candidate: ExecutorPlanCandidate, policy: ExecutorPlanPolicy) -> str | None:
    checks: tuple[tuple[bool, str, Any], ...] = (
        (policy.require_non_noop_sandbox_receipt_manifest_digest, "missing_sandbox_receipt_manifest_digest", candidate.claimed_sandbox_receipt_manifest_digest),
        (policy.require_non_noop_sandbox_rollback_manifest_digest, "missing_sandbox_rollback_manifest_digest", candidate.claimed_sandbox_rollback_manifest_digest),
        (policy.require_non_noop_sandbox_artifact_plan, "missing_sandbox_artifact_plan", candidate.sandbox_artifact_plan),
        (policy.require_non_noop_live_receipt_schema_metadata, "missing_live_receipt_schema_metadata", candidate.live_receipt_schema_metadata),
        (policy.require_non_noop_live_rollback_schema_metadata, "missing_live_rollback_schema_metadata", candidate.live_rollback_schema_metadata),
        (policy.require_non_noop_post_commit_verification_plan, "missing_post_commit_verification_plan", candidate.post_commit_verification_plan),
        (policy.require_non_noop_abort_panic_stop_condition_metadata, "missing_abort_panic_stop_condition_metadata", candidate.abort_panic_stop_condition_metadata),
        (policy.require_non_noop_operator_runtime_confirmation_metadata, "missing_operator_runtime_confirmation_metadata", candidate.operator_runtime_confirmation_metadata),
        (policy.require_non_noop_operator_identity_role_metadata, "missing_operator_identity_role_metadata", candidate.operator_identity_role_metadata),
        (policy.require_non_noop_execution_window_metadata, "missing_execution_window_metadata", candidate.execution_window_metadata),
        (policy.require_non_noop_dry_run_to_live_equivalence_metadata, "missing_dry_run_to_live_equivalence_metadata", candidate.dry_run_to_live_equivalence_metadata),
        (policy.require_non_noop_rollback_rehearsal_metadata, "missing_rollback_rehearsal_metadata", candidate.rollback_rehearsal_metadata),
        (policy.require_non_noop_post_execution_audit_metadata, "missing_post_execution_audit_metadata", candidate.post_execution_audit_metadata),
        (policy.require_non_noop_executor_plan_operation_list, "missing_executor_plan_operation_list", candidate.executor_plan_operations),
        (policy.require_non_noop_operation_ordering_metadata, "missing_operation_ordering_metadata", candidate.operation_ordering_metadata),
        (policy.require_non_noop_lock_lease_expectation_metadata, "missing_lock_lease_expectation_metadata", candidate.lock_lease_expectation_metadata),
        (policy.require_non_noop_idempotency_key_metadata, "missing_idempotency_key_metadata", candidate.idempotency_key_metadata),
        (policy.require_non_noop_atomicity_boundary_metadata, "missing_atomicity_boundary_metadata", candidate.atomicity_boundary_metadata),
        (policy.require_non_noop_failure_mode_classification_metadata, "missing_failure_mode_classification_metadata", candidate.failure_mode_classification_metadata),
    )
    for required, code, value in checks:
        if required and not value:
            return code
    for op in candidate.executor_plan_operations:
        operation_id = str(op.get("operation_id") or op.get("id") or "")
        if not operation_id:
            return "missing_operation_id"
        if policy.require_non_noop_per_operation_precondition_metadata and not _as_mapping(op.get("precondition_metadata") or op.get("preconditions")):
            return "missing_per_operation_precondition_metadata"
        if policy.require_non_noop_per_operation_receipt_target_metadata and not _as_mapping(op.get("receipt_target_metadata") or op.get("expected_receipt_target_metadata")):
            return "missing_receipt_target_metadata"
        if policy.require_non_noop_per_operation_rollback_target_metadata and not _as_mapping(op.get("rollback_target_metadata")):
            return "missing_rollback_target_metadata"
    return None


def _forbidden_claim(candidate: ExecutorPlanCandidate, policy: ExecutorPlanPolicy, raw: Mapping[str, Any]) -> str | None:
    claims = candidate.executor_plan_claims
    all_data = {"candidate": candidate.to_dict(), "claims": claims, "candidate_input": raw}
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
    if policy.block_executor_permission_claims and _flag(claims, "executor_plan_grants_permission", "permission_to_execute_now", "authority_to_execute_now"):
        return "executor_permission_claim"
    if policy.block_readiness_conversion_claims and _flag(claims, "readiness_envelope_is_runtime_permission", "readiness_envelope_is_execution_permission"):
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


def _decision_for(candidate: ExecutorPlanCandidate, runtime_decision: str, warning: bool) -> ExecutorPlanDecision:
    if _is_noop(candidate, runtime_decision): return "executor_plan_noop"
    if candidate.candidate_type == "operator_review_executor_plan_candidate": return "executor_plan_deferred_for_operator_review"
    if warning or runtime_decision == "runtime_execution_gate_ready_with_warnings": return "executor_plan_ready_with_warnings"
    return "executor_plan_ready_for_later_live_executor"


def _safe_actions(decision: str) -> tuple[str, ...]:
    base = ["no_action_allowed", "inspect_executor_plan_packet", "inspect_explicit_live_memory_runtime_execution_gate_packet", "sustain_default_deny"]
    if decision in {"executor_plan_ready_for_later_live_executor", "executor_plan_ready_with_warnings"}:
        base.extend(["prepare_future_real_live_memory_commit_executor_later", "prepare_future_live_executor_lock_gate_later", "prepare_future_post_execution_audit_later"])
    if decision == "executor_plan_deferred_for_operator_review": base.append("operator_review_required")
    return tuple(base)


def _operation_records(candidate: ExecutorPlanCandidate) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    ordered = sorted(candidate.executor_plan_operations, key=lambda op: (int(op.get("order", 0)), str(op.get("operation_id") or op.get("id") or "")))
    intents: list[Mapping[str, Any]] = []
    preconditions: list[Mapping[str, Any]] = []
    receipts: list[Mapping[str, Any]] = []
    rollbacks: list[Mapping[str, Any]] = []
    verifications: list[Mapping[str, Any]] = []
    aborts: list[Mapping[str, Any]] = []
    audits: list[Mapping[str, Any]] = []
    for index, op in enumerate(ordered, start=1):
        operation_id = str(op.get("operation_id") or op.get("id") or f"operation-{index}")
        base = {"operation_id": operation_id, "order": int(op.get("order", index)), "metadata_only": True, "executed": False}
        intents.append({**base, "operation_type": str(op.get("operation_type") or op.get("type") or "metadata_operation_intent"), "intent_only": True, "operation_metadata": dict(_as_mapping(op.get("operation_metadata") or op.get("metadata")))})
        preconditions.append({**base, "precondition_metadata": dict(_as_mapping(op.get("precondition_metadata") or op.get("preconditions")))})
        receipts.append({**base, "receipt_target_metadata": dict(_as_mapping(op.get("receipt_target_metadata") or op.get("expected_receipt_target_metadata"))), "live_receipt_emitted": False})
        rollbacks.append({**base, "rollback_target_metadata": dict(_as_mapping(op.get("rollback_target_metadata"))), "rollback_applied": False})
        verifications.append({**base, "verification_step_metadata": dict(_as_mapping(op.get("verification_step_metadata") or op.get("verification_metadata"))), "verification_performed": False})
        aborts.append({**base, "abort_condition_metadata": dict(_as_mapping(op.get("abort_condition_metadata") or op.get("abort_metadata"))), "abort_evaluated_at_runtime": False})
        audits.append({**base, "audit_expectation_metadata": dict(_as_mapping(op.get("audit_expectation_metadata") or op.get("audit_metadata"))), "audit_emitted": False})
    return tuple(intents), tuple(preconditions), tuple(receipts), tuple(rollbacks), tuple(verifications), tuple(aborts), tuple(audits)


def evaluate_real_live_memory_commit_executor_plan_packet(payload: Mapping[str, Any], policy: ExecutorPlanPolicy | None = None) -> ExecutorPlanResult:
    try:
        active_policy = _policy_from_payload(payload, policy)
        policy_validation = validate_policy(active_policy)
        if policy_validation["status"] != "valid":
            return _blocked("invalid_policy", tuple(ExecutorPlanFinding("error", f["code"], f["message"]) for f in policy_validation["findings"]))
        runtime_packet = _runtime_packet(payload)
        if not runtime_packet:
            return _blocked("missing_runtime_execution_gate_packet")
        runtime_records_raw = _as_sequence(runtime_packet.get("records"))
        if not runtime_packet.get("digest") or not runtime_records_raw:
            return _blocked("invalid_runtime_execution_gate_packet")
        candidates_raw = _candidate_payloads(payload)
        if not candidates_raw:
            return _blocked("missing_executor_plan_candidate")
        findings: list[ExecutorPlanFinding] = []
        records: list[ExecutorPlanRecord] = []
        runtime_records = {str(_as_mapping(record).get("record_id") or _as_mapping(record).get("candidate_id") or index): _as_mapping(record) for index, record in enumerate(runtime_records_raw)}
        for raw in candidates_raw:
            candidate = ExecutorPlanCandidate.from_mapping(raw)
            if not candidate.candidate_id or candidate.candidate_type not in EXECUTOR_PLAN_CANDIDATE_TYPES:
                return _blocked("invalid_executor_plan_candidate")
            runtime_record = runtime_records.get(candidate.record_id) or next(iter(runtime_records.values()))
            runtime_digest = str(runtime_packet.get("digest") or "")
            runtime_decision = str(runtime_record.get("execution_gate_decision") or runtime_record.get("runtime_execution_gate_decision") or runtime_record.get("decision") or "")
            if active_policy.require_ready_runtime_execution_gate and runtime_decision not in READY_RUNTIME_EXECUTION_GATE_DECISIONS:
                return _blocked("runtime_execution_gate_not_ready", [ExecutorPlanFinding("error", "runtime_execution_gate_not_ready", "runtime execution gate decision is not ready", candidate.candidate_id, candidate.record_id)])
            comparisons = (
                (active_policy.require_matching_runtime_execution_gate_digest, "runtime_execution_gate_digest_mismatch", candidate.claimed_runtime_execution_gate_digest, runtime_digest),
                (active_policy.require_matching_runtime_execution_gate_decision, "runtime_execution_gate_decision_mismatch", candidate.claimed_runtime_execution_gate_decision, runtime_decision),
                (active_policy.require_matching_readiness_envelope_digest, "readiness_envelope_digest_mismatch", candidate.claimed_readiness_envelope_digest, str(runtime_record.get("readiness_envelope_digest") or "")),
                (active_policy.require_matching_readiness_envelope_decision, "readiness_envelope_decision_mismatch", candidate.claimed_readiness_envelope_decision, str(runtime_record.get("readiness_envelope_decision") or "")),
                (active_policy.require_matching_final_review_digest, "final_review_digest_mismatch", candidate.claimed_final_review_digest, str(runtime_record.get("final_review_digest") or "")),
                (active_policy.require_matching_final_review_decision, "final_review_decision_mismatch", candidate.claimed_final_review_decision, str(runtime_record.get("final_review_decision") or "")),
                (active_policy.require_matching_real_root_admission_digest, "real_root_admission_digest_mismatch", candidate.claimed_real_root_admission_digest, str(runtime_record.get("real_root_admission_digest") or "")),
                (active_policy.require_matching_real_root_admission_decision, "real_root_admission_decision_mismatch", candidate.claimed_real_root_admission_decision, str(runtime_record.get("real_root_admission_decision") or "")),
                (active_policy.require_matching_sandbox_commit_digest, "sandbox_commit_digest_mismatch", candidate.claimed_sandbox_commit_digest, str(runtime_record.get("sandbox_commit_digest") or "")),
                (active_policy.require_matching_sandbox_commit_decision, "sandbox_commit_decision_mismatch", candidate.claimed_sandbox_commit_decision, str(runtime_record.get("sandbox_commit_decision") or "")),
            )
            for required, code, actual, expected in comparisons:
                if required and actual != expected:
                    return _blocked(code, [ExecutorPlanFinding("error", code, code.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            if not _is_noop(candidate, runtime_decision):
                missing = _require_non_noop_metadata(candidate, active_policy)
                if missing:
                    return _blocked(missing, [ExecutorPlanFinding("error", missing, missing.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            forbidden = _forbidden_claim(candidate, active_policy, raw)
            if forbidden:
                return _blocked(forbidden, [ExecutorPlanFinding("error", forbidden, forbidden.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            runtime_scope = _as_tuple(runtime_record.get("operator_scope_keys"))
            readiness_scope = _as_tuple(runtime_record.get("readiness_scope_keys"))
            final_scope = _as_tuple(runtime_record.get("final_review_scope_keys"))
            real_scope = _as_tuple(runtime_record.get("real_root_admission_scope_keys"))
            sandbox_scope = _as_tuple(runtime_record.get("sandbox_scope_keys"))
            if active_policy.require_scope_alignment:
                scopes = [scope for scope in (candidate.operator_scope_keys, runtime_scope, readiness_scope, final_scope, real_scope, sandbox_scope) if scope]
                aligned = all(scope == scopes[0] for scope in scopes) if scopes else False
                if not aligned:
                    if active_policy.allow_mixed_scope_diagnostic_packet and candidate.candidate_type == "mixed_executor_plan_candidate" and candidate.metadata.get("diagnostic_warning") is True:
                        findings.append(ExecutorPlanFinding("warning", "scope_mismatch_diagnostic", "scope mismatch allowed for diagnostic packet", candidate.candidate_id, candidate.record_id))
                    else:
                        return _blocked("scope_mismatch", [ExecutorPlanFinding("error", "scope_mismatch", "scope mismatch", candidate.candidate_id, candidate.record_id)])
            warning = bool(candidate.metadata.get("warning_only") or candidate.metadata.get("diagnostic_warning")) or runtime_decision.endswith("with_warnings") or any(f.severity == "warning" and f.candidate_id == candidate.candidate_id for f in findings)
            if warning:
                findings.append(ExecutorPlanFinding("warning", "executor_plan_warning", "candidate is warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
            decision = _decision_for(candidate, runtime_decision, warning)
            intents, preconditions, receipts, rollbacks, verifications, aborts, audits = _operation_records(candidate)
            future_record = {"candidate_id": candidate.candidate_id, "eligible_for_future_real_live_memory_commit_executor_consideration": decision in {"executor_plan_ready_for_later_live_executor", "executor_plan_ready_with_warnings"}, "decision": decision, "real_live_commit_performed": False, "real_memory_root_access_performed": False, "live_executor_enabled": False, "future_real_live_memory_commit_executor_required": True, "future_live_executor_lock_gate_required": True, "future_post_execution_audit_required": True, "operator_review_cannot_override_hard_blockers": True}
            records.append(ExecutorPlanRecord(candidate.candidate_id, candidate.record_id, candidate.candidate_type, decision, runtime_decision, runtime_digest, str(runtime_record.get("digest") or ""), candidate.claimed_readiness_envelope_decision, candidate.claimed_readiness_envelope_digest, candidate.claimed_final_review_decision, candidate.claimed_final_review_digest, candidate.claimed_real_root_admission_decision, candidate.claimed_real_root_admission_digest, candidate.claimed_sandbox_commit_decision, candidate.claimed_sandbox_commit_digest, candidate.claimed_sandbox_receipt_manifest_digest, candidate.claimed_sandbox_rollback_manifest_digest, candidate.operator_scope_keys, runtime_scope, readiness_scope, final_scope, real_scope, sandbox_scope, dict(candidate.sandbox_artifact_plan), intents, preconditions, receipts, rollbacks, verifications, aborts, audits, dict(candidate.live_receipt_schema_metadata), dict(candidate.live_rollback_schema_metadata), dict(candidate.post_commit_verification_plan), dict(candidate.abort_panic_stop_condition_metadata), dict(candidate.operator_runtime_confirmation_metadata), dict(candidate.operator_identity_role_metadata), dict(candidate.execution_window_metadata), dict(candidate.dry_run_to_live_equivalence_metadata), dict(candidate.rollback_rehearsal_metadata), dict(candidate.post_execution_audit_metadata), dict(candidate.operation_ordering_metadata), dict(candidate.lock_lease_expectation_metadata), dict(candidate.idempotency_key_metadata), dict(candidate.atomicity_boundary_metadata), dict(candidate.failure_mode_classification_metadata), _safe_actions(decision), future_record).with_digest())
        counts: dict[str, int] = {"candidate_count": len(records), "operation_count": sum(len(record.ordered_operation_intent_records) for record in records), "warning_count": sum(1 for finding in findings if finding.severity == "warning")}
        for record in records:
            counts[record.executor_plan_decision] = counts.get(record.executor_plan_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {record.executor_plan_decision for record in records}
        if counts["warning_count"] or "executor_plan_ready_with_warnings" in decisions: status: ExecutorPlanStatus = "executor_plan_ready_with_warnings"
        elif decisions <= {"executor_plan_noop"}: status = "executor_plan_noop"
        elif decisions <= {"executor_plan_deferred_for_operator_review"}: status = "executor_plan_deferred_for_operator_review"
        elif decisions <= {"executor_plan_rejected"}: status = "executor_plan_rejected"
        else: status = "executor_plan_ready"
        packet = ExecutorPlanPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = ExecutorPlanReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return ExecutorPlanResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("failed", [ExecutorPlanFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: ExecutorPlanPolicy | None = None) -> ExecutorPlanResult:
    return evaluate_real_live_memory_commit_executor_plan_packet(payload, policy)


__all__ = [
    "EXECUTOR_PLAN_CANDIDATE_TYPES", "FORBIDDEN_NEXT_STEPS", "INVARIANTS", "READY_RUNTIME_EXECUTION_GATE_DECISIONS", "SAFE_NEXT_ACTIONS",
    "ExecutorPlanCandidate", "ExecutorPlanFinding", "ExecutorPlanPacket", "ExecutorPlanPolicy", "ExecutorPlanRecord", "ExecutorPlanReport", "ExecutorPlanResult",
    "build_default_policy", "validate_policy", "evaluate_real_live_memory_commit_executor_plan_packet", "evaluate_packet",
]
