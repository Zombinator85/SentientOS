"""Deterministic metadata-only explicit live-memory runtime execution gate.

This gate consumes supplied Real Live Memory Commit Adapter Readiness Envelope
packets and explicit operator runtime execution candidates. It only decides
whether a future real live-memory commit executor may be considered later. It
never writes, deletes, purges, indexes, persists capsules, completes tombs,
assembles prompts, retrieves live context, executes actions, discloses
externally, invokes remote services, touches real memory roots, grants truth,
creates policy, infers consent, or grants authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Mapping, Sequence

RuntimeExecutionGateStatus = Literal[
    "runtime_execution_gate_ready",
    "runtime_execution_gate_ready_with_warnings",
    "runtime_execution_gate_deferred_for_operator_review",
    "runtime_execution_gate_rejected",
    "runtime_execution_gate_blocked",
    "runtime_execution_gate_noop",
    "runtime_execution_gate_invalid",
    "runtime_execution_gate_failed",
]
RuntimeExecutionGateDecision = Literal[
    "runtime_execution_gate_ready_for_later_live_executor",
    "runtime_execution_gate_ready_with_warnings",
    "runtime_execution_gate_deferred_for_operator_review",
    "runtime_execution_gate_rejected",
    "runtime_execution_gate_blocked",
    "runtime_execution_gate_noop",
]

RUNTIME_EXECUTION_GATE_CANDIDATE_TYPES = frozenset({
    "ai_capsule_runtime_execution_gate_candidate",
    "human_summary_runtime_execution_gate_candidate",
    "dual_capsule_runtime_execution_gate_candidate",
    "protect_receipt_runtime_execution_gate_candidate",
    "merge_receipt_runtime_execution_gate_candidate",
    "tomb_archive_runtime_execution_gate_candidate",
    "tomb_deferred_runtime_execution_gate_candidate",
    "operator_review_runtime_execution_gate_candidate",
    "noop_runtime_execution_gate_candidate",
    "mixed_runtime_execution_gate_candidate",
})
READY_READINESS_DECISIONS = frozenset({
    "live_adapter_readiness_ready_for_later_runtime_gate",
    "live_adapter_readiness_ready_with_warnings",
    "live_adapter_readiness_noop",
})
INVARIANTS: dict[str, bool] = {
    "runtime_execution_gate_is_not_memory_write": True,
    "runtime_execution_gate_is_not_memory_deletion": True,
    "runtime_execution_gate_is_not_memory_purge": True,
    "runtime_execution_gate_is_not_index_mutation": True,
    "runtime_execution_gate_is_not_capsule_persistence": True,
    "runtime_execution_gate_is_not_tomb_completion": True,
    "runtime_execution_gate_is_not_prompt_assembly": True,
    "runtime_execution_gate_is_not_live_context_retrieval": True,
    "runtime_execution_gate_is_not_action_execution": True,
    "runtime_execution_gate_is_not_external_disclosure": True,
    "runtime_execution_gate_is_not_live_commit_execution": True,
    "runtime_execution_gate_is_not_truth": True,
    "runtime_execution_gate_is_not_policy": True,
    "runtime_execution_gate_is_not_authority": True,
    "runtime_execution_gate_is_not_consent": True,
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
    "future_operator_runtime_confirmation_required": True,
    "future_post_execution_audit_required": True,
}
SAFE_NEXT_ACTIONS = (
    "no_action_allowed", "inspect_runtime_execution_gate_packet", "inspect_real_live_memory_commit_adapter_readiness_envelope_packet",
    "inspect_final_live_memory_commit_review_packet", "operator_review_required", "prepare_future_real_live_memory_commit_executor_later",
    "prepare_future_operator_runtime_confirmation_later", "prepare_future_post_execution_audit_later", "rerun_with_ready_readiness_envelope_packet",
    "rerun_with_matching_readiness_envelope_digest", "rerun_with_matching_readiness_envelope_decision", "rerun_with_matching_final_review_digest",
    "rerun_with_matching_final_review_decision", "rerun_with_matching_real_root_admission_digest", "rerun_with_matching_real_root_admission_decision",
    "rerun_with_matching_sandbox_commit_digest", "rerun_with_matching_sandbox_commit_decision", "rerun_with_sandbox_receipt_manifest_digest",
    "rerun_with_sandbox_rollback_manifest_digest", "rerun_with_sandbox_artifact_plan", "rerun_with_live_receipt_schema_metadata",
    "rerun_with_live_rollback_schema_metadata", "rerun_with_post_commit_verification_plan", "rerun_with_abort_panic_stop_condition_metadata",
    "rerun_with_operator_runtime_confirmation_metadata", "rerun_with_operator_identity_role_metadata", "rerun_with_execution_window_metadata",
    "rerun_with_dry_run_to_live_equivalence_metadata", "rerun_with_rollback_rehearsal_metadata", "rerun_with_post_execution_audit_metadata",
    "rerun_with_scope_alignment", "sustain_default_deny",
)
FORBIDDEN_NEXT_STEPS = (
    "write_live_memory_now", "delete_live_memory_now", "purge_live_memory_now", "mutate_vector_index", "mutate_live_index",
    "persist_capsule_now", "persist_summary_now", "apply_protection_now", "apply_merge_now", "complete_tomb_now",
    "run_real_live_commit_executor_now", "treat_runtime_execution_gate_as_permission_to_execute_now", "treat_readiness_envelope_as_runtime_execution_permission",
    "treat_final_review_as_execution_permission", "treat_real_root_admission_as_memory_root_access", "treat_sandbox_commit_as_real_commit",
    "treat_sandbox_receipt_as_live_receipt", "treat_sandbox_rollback_as_applied_rollback", "touch_real_memory_root",
    "open_real_memory_path_for_write", "assemble_prompt_now", "retrieve_live_context", "execute_action_ingress", "disclose_externally",
    "infer_truth_from_gate", "infer_authority_from_gate", "infer_consent_from_gate", "convert_gate_to_policy", "bypass_readiness_envelope",
    "bypass_final_live_commit_review_gate", "bypass_real_root_admission_gate", "bypass_sandbox_commit_adapter", "direct_executor_invocation",
    "enable_external_disclosure",
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
            if re.search(r"(^|_)(raw|private|secret|media|provider_prompt|payload)(_|$)", lowered):
                return True
            if _has_raw_payload(nested):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_has_raw_payload(item) for item in value)
    return False


@dataclass(frozen=True)
class RuntimeExecutionGatePolicy:
    schema_version: str = "explicit-live-memory-runtime-execution-gate/v1"
    default_posture: str = "deny"
    require_ready_readiness_envelope: bool = True
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
    require_scope_alignment: bool = True
    allow_mixed_scope_diagnostic_packet: bool = True
    block_live_mutation_claims: bool = True
    block_real_memory_root_access_claims: bool = True
    block_runtime_execution_claims: bool = True
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
    live_executor_enabled: bool = False
    future_post_execution_audit_required: bool = True


@dataclass(frozen=True)
class RuntimeExecutionGateFinding:
    severity: str
    code: str
    message: str
    candidate_id: str = ""
    record_id: str = ""
    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class RuntimeExecutionGateCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
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
    runtime_execution_claims: Mapping[str, Any]
    metadata: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RuntimeExecutionGateCandidate":
        return cls(
            candidate_id=str(raw.get("candidate_id") or ""), record_id=str(raw.get("record_id") or raw.get("candidate_id") or ""), candidate_type=str(raw.get("candidate_type") or ""),
            claimed_readiness_envelope_digest=str(raw.get("claimed_readiness_envelope_digest") or raw.get("readiness_envelope_digest") or ""),
            claimed_readiness_envelope_decision=str(raw.get("claimed_readiness_envelope_decision") or raw.get("readiness_decision") or ""),
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
            runtime_execution_claims=_as_mapping(raw.get("runtime_execution_claims") or raw.get("claims")), metadata=_as_mapping(raw.get("metadata")),
        )
    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class RuntimeExecutionGateRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    execution_gate_decision: RuntimeExecutionGateDecision
    readiness_envelope_decision: str
    readiness_envelope_digest: str
    readiness_envelope_record_digest: str
    final_review_decision: str
    final_review_digest: str
    real_root_admission_decision: str
    real_root_admission_digest: str
    sandbox_commit_decision: str
    sandbox_commit_digest: str
    sandbox_receipt_manifest_digest: str
    sandbox_rollback_manifest_digest: str
    operator_scope_keys: tuple[str, ...]
    readiness_scope_keys: tuple[str, ...]
    final_review_scope_keys: tuple[str, ...]
    real_root_admission_scope_keys: tuple[str, ...]
    sandbox_scope_keys: tuple[str, ...]
    sandbox_artifact_plan: Mapping[str, Any]
    execution_precondition_record: Mapping[str, Any]
    verification_readiness_record: Mapping[str, Any]
    abort_readiness_record: Mapping[str, Any]
    rollback_readiness_record: Mapping[str, Any]
    operator_runtime_confirmation_metadata: Mapping[str, Any]
    operator_identity_role_metadata: Mapping[str, Any]
    execution_window_metadata: Mapping[str, Any]
    dry_run_to_live_equivalence_metadata: Mapping[str, Any]
    rollback_rehearsal_metadata: Mapping[str, Any]
    post_execution_audit_metadata: Mapping[str, Any]
    safe_next_actions: tuple[str, ...]
    future_live_executor_consideration_record: Mapping[str, Any]
    runtime_execution_gate_future_consideration_only: bool = True
    runtime_execution_gate_is_runtime_execution_permission: bool = False
    runtime_execution_gate_has_executed_live_commit: bool = False
    readiness_envelope_is_runtime_execution_permission: bool = False
    final_review_is_execution_permission: bool = False
    real_root_admission_is_memory_root_access: bool = False
    sandbox_commit_is_real_commit: bool = False
    sandbox_receipt_is_live_receipt: bool = False
    sandbox_rollback_is_applied_rollback: bool = False
    real_memory_root_access_performed: bool = False
    live_memory_write_claimed: bool = False
    live_memory_delete_claimed: bool = False
    live_memory_purge_claimed: bool = False
    live_index_mutation_claimed: bool = False
    capsule_persistence_claimed: bool = False
    tomb_completion_claimed: bool = False
    protection_application_claimed: bool = False
    merge_application_claimed: bool = False
    prompt_assembly_claimed: bool = False
    live_context_retrieval_claimed: bool = False
    action_execution_claimed: bool = False
    external_disclosure_claimed: bool = False
    authority_claimed: bool = False
    consent_claimed: bool = False
    policy_claimed: bool = False
    truth_claimed: bool = False
    digest: str = ""
    def to_dict(self) -> dict[str, Any]: return asdict(self)
    def with_digest(self) -> "RuntimeExecutionGateRecord":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class RuntimeExecutionGatePacket:
    schema_version: str
    records: tuple[RuntimeExecutionGateRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""
    runtime_execution_gate_is_not_memory_write: bool = True
    runtime_execution_gate_is_not_memory_deletion: bool = True
    runtime_execution_gate_is_not_memory_purge: bool = True
    runtime_execution_gate_is_not_index_mutation: bool = True
    runtime_execution_gate_is_not_capsule_persistence: bool = True
    runtime_execution_gate_is_not_tomb_completion: bool = True
    runtime_execution_gate_is_not_prompt_assembly: bool = True
    runtime_execution_gate_is_not_live_context_retrieval: bool = True
    runtime_execution_gate_is_not_action_execution: bool = True
    runtime_execution_gate_is_not_external_disclosure: bool = True
    runtime_execution_gate_is_not_live_commit_execution: bool = True
    runtime_execution_gate_is_not_truth: bool = True
    runtime_execution_gate_is_not_policy: bool = True
    runtime_execution_gate_is_not_authority: bool = True
    runtime_execution_gate_is_not_consent: bool = True
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
    future_operator_runtime_confirmation_required: bool = True
    future_post_execution_audit_required: bool = True
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self); data["records"] = [record.to_dict() for record in self.records]; return data
    def with_digest(self) -> "RuntimeExecutionGatePacket":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class RuntimeExecutionGateReport:
    status: RuntimeExecutionGateStatus
    findings: tuple[RuntimeExecutionGateFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""
    def to_dict(self) -> dict[str, Any]: return {"status": self.status, "findings": [finding.to_dict() for finding in self.findings], "summary_counts": dict(sorted(self.summary_counts.items())), "digest": self.digest}


@dataclass(frozen=True)
class RuntimeExecutionGateResult:
    status: RuntimeExecutionGateStatus
    packet: RuntimeExecutionGatePacket | None
    report: RuntimeExecutionGateReport
    digest: str
    def to_dict(self) -> dict[str, Any]: return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> RuntimeExecutionGatePolicy: return RuntimeExecutionGatePolicy()


def validate_policy(policy: RuntimeExecutionGatePolicy | Mapping[str, Any] | None = None) -> dict[str, Any]:
    raw = asdict(policy) if isinstance(policy, RuntimeExecutionGatePolicy) else dict(policy or asdict(build_default_policy()))
    findings: list[dict[str, str]] = []
    if raw.get("default_posture") != "deny": findings.append({"severity": "error", "code": "default_posture_not_deny", "message": "runtime execution gate must default deny"})
    for key, expected in INVARIANTS.items():
        if raw.get(key, expected) != expected: findings.append({"severity": "error", "code": f"invariant_{key}_changed", "message": f"{key} must remain {expected}"})
    status = "invalid" if findings else "valid"
    return {"status": status, "findings": findings, "policy": raw, "digest": _digest({"status": status, "findings": findings, "policy": raw})}


def _policy_from_payload(payload: Mapping[str, Any], policy: RuntimeExecutionGatePolicy | None) -> RuntimeExecutionGatePolicy:
    if policy is not None:
        return policy
    raw = _as_mapping(payload.get("policy"))
    if raw:
        allowed = set(RuntimeExecutionGatePolicy.__dataclass_fields__)
        return RuntimeExecutionGatePolicy(**{key: value for key, value in raw.items() if key in allowed})
    return build_default_policy()


def _readiness_packet(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    return _as_mapping(payload.get("real_live_memory_commit_adapter_readiness_envelope_packet") or payload.get("readiness_envelope_packet") or payload.get("packet"))


def _candidate_payloads(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = payload.get("runtime_execution_gate_candidates", payload.get("runtime_execution_gate_candidate", payload.get("candidates", ())))
    if isinstance(raw, Mapping):
        return (raw,)
    return tuple(item for item in _as_sequence(raw) if isinstance(item, Mapping))


def _blocked(code: str, findings: Sequence[RuntimeExecutionGateFinding] | None = None) -> RuntimeExecutionGateResult:
    finding_list = tuple(findings or (RuntimeExecutionGateFinding("error", code, code.replace("_", " ")),))
    report = RuntimeExecutionGateReport("runtime_execution_gate_blocked", finding_list, {"candidate_count": 0, "error_count": sum(1 for finding in finding_list if finding.severity == "error")})
    report = replace(report, digest=_digest(report.to_dict()))
    return RuntimeExecutionGateResult("runtime_execution_gate_blocked", None, report, _digest({"packet": None, "report": report.to_dict()}))


def _claims_blocker(candidate: RuntimeExecutionGateCandidate, policy: RuntimeExecutionGatePolicy) -> str | None:
    claims, metadata = candidate.runtime_execution_claims, candidate.metadata
    all_data = {"claims": claims, "metadata": metadata, "sandbox_artifact_plan": candidate.sandbox_artifact_plan, "live_receipt_schema_metadata": candidate.live_receipt_schema_metadata, "live_rollback_schema_metadata": candidate.live_rollback_schema_metadata, "post_commit_verification_plan": candidate.post_commit_verification_plan, "abort_panic_stop_condition_metadata": candidate.abort_panic_stop_condition_metadata, "operator_runtime_confirmation_metadata": candidate.operator_runtime_confirmation_metadata, "operator_identity_role_metadata": candidate.operator_identity_role_metadata, "execution_window_metadata": candidate.execution_window_metadata, "dry_run_to_live_equivalence_metadata": candidate.dry_run_to_live_equivalence_metadata, "rollback_rehearsal_metadata": candidate.rollback_rehearsal_metadata, "post_execution_audit_metadata": candidate.post_execution_audit_metadata}
    if policy.block_real_memory_root_access_claims and (_flag(claims, "real_memory_root_access_performed", "real_memory_root_write_enabled", "touch_real_memory_root") or metadata.get("real_memory_root_access_performed") is True): return "real_memory_root_access_claim"
    if policy.block_live_mutation_claims:
        if _flag(claims, "live_memory_write_claimed", "live_memory_write_enabled", "write_live_memory_now"): return "live_write_claim"
        if _flag(claims, "live_memory_delete_claimed", "live_memory_deletion_enabled", "delete_live_memory_now"): return "live_delete_claim"
        if _flag(claims, "live_memory_purge_claimed", "live_memory_purge_enabled", "purge_live_memory_now"): return "live_purge_claim"
        if _flag(claims, "live_index_mutation_claimed", "live_index_mutation_enabled", "mutate_live_index"): return "index_mutation_claim"
        if _flag(claims, "capsule_persistence_claimed", "capsule_persistence_enabled", "persist_capsule_now"): return "capsule_persistence_claim"
        if _flag(claims, "tomb_completion_claimed", "tomb_completion_enabled", "complete_tomb_now"): return "tomb_completion_claim"
        if _flag(claims, "protection_application_claimed", "apply_protection_now"): return "protection_application_claim"
        if _flag(claims, "merge_application_claimed", "apply_merge_now"): return "merge_application_claim"
    if policy.block_runtime_execution_claims and (_flag(claims, "runtime_execution_gate_has_executed_live_commit", "permission_to_execute_live_commit_now", "live_executor_enabled", "run_real_live_commit_executor_now") or metadata.get("runtime_execution_gate_has_executed_live_commit") is True): return "runtime_execution_claim"
    if policy.block_readiness_conversion_claims and _flag(claims, "readiness_envelope_is_runtime_execution_permission", "readiness_envelope_executed_live_commit"): return "readiness_envelope_conversion_claim"
    if policy.block_final_review_conversion_claims and _flag(claims, "final_review_is_execution_permission", "final_review_is_real_commit"): return "final_review_conversion_claim"
    if policy.block_sandbox_conversion_claims and _flag(claims, "sandbox_commit_is_real_commit", "sandbox_receipt_is_live_receipt", "sandbox_rollback_is_applied_rollback"): return "sandbox_conversion_claim"
    if policy.block_real_root_admission_conversion_claims and _flag(claims, "real_root_admission_is_memory_root_access"): return "real_root_admission_conversion_claim"
    if policy.block_prompt_materialization and _flag(claims, "prompt_assembly_claimed", "prompt_materialization_enabled", "assemble_prompt_now"): return "prompt_materialization"
    if policy.block_live_context_retrieval and _flag(claims, "live_context_retrieval_claimed", "live_context_retrieval_enabled"): return "live_context_retrieval"
    if policy.block_action_execution and _flag(claims, "action_execution_claimed", "action_execution_enabled", "execute_action_ingress"): return "action_execution"
    if policy.block_external_disclosure and _flag(claims, "external_disclosure_claimed", "external_disclosure_enabled", "remote_service_enabled"): return "external_disclosure"
    if policy.block_authority_smuggling and _flag(claims, "authority_claimed", "authority_granted"): return "authority_smuggling"
    if policy.block_consent_smuggling and _flag(claims, "consent_claimed", "consent_granted"): return "consent_smuggling"
    if policy.block_policy_smuggling and _flag(claims, "policy_claimed", "policy_created"): return "policy_smuggling"
    if policy.block_truth_smuggling and _flag(claims, "truth_claimed", "truth_created"): return "truth_smuggling"
    if policy.block_raw_payload_leakage and _has_raw_payload(all_data): return "raw_payload_leak"
    return None


def _decision_for(candidate: RuntimeExecutionGateCandidate, readiness_decision: str, warning: bool) -> RuntimeExecutionGateDecision:
    if candidate.candidate_type == "noop_runtime_execution_gate_candidate" or readiness_decision == "live_adapter_readiness_noop": return "runtime_execution_gate_noop"
    if candidate.candidate_type == "operator_review_runtime_execution_gate_candidate": return "runtime_execution_gate_deferred_for_operator_review"
    if warning or readiness_decision == "live_adapter_readiness_ready_with_warnings": return "runtime_execution_gate_ready_with_warnings"
    return "runtime_execution_gate_ready_for_later_live_executor"


def _safe_actions(decision: str) -> tuple[str, ...]:
    base = ["no_action_allowed", "inspect_runtime_execution_gate_packet", "inspect_real_live_memory_commit_adapter_readiness_envelope_packet", "sustain_default_deny"]
    if decision in {"runtime_execution_gate_ready_for_later_live_executor", "runtime_execution_gate_ready_with_warnings"}:
        base.extend(["prepare_future_real_live_memory_commit_executor_later", "prepare_future_operator_runtime_confirmation_later", "prepare_future_post_execution_audit_later"])
    if decision == "runtime_execution_gate_deferred_for_operator_review": base.append("operator_review_required")
    return tuple(base)


def evaluate_explicit_live_memory_runtime_execution_gate(payload: Mapping[str, Any], policy: RuntimeExecutionGatePolicy | None = None) -> RuntimeExecutionGateResult:
    try:
        active_policy = _policy_from_payload(payload, policy)
        policy_validation = validate_policy(active_policy)
        if policy_validation["status"] != "valid":
            return _blocked("invalid_policy", tuple(RuntimeExecutionGateFinding("error", f["code"], f["message"]) for f in policy_validation["findings"]))
        readiness_packet = _readiness_packet(payload)
        if not readiness_packet:
            return _blocked("missing_readiness_envelope_packet")
        readiness_records_raw = _as_sequence(readiness_packet.get("records"))
        if not readiness_packet.get("digest") or not readiness_records_raw:
            return _blocked("invalid_readiness_envelope_packet")
        candidates_raw = _candidate_payloads(payload)
        if not candidates_raw:
            return _blocked("missing_runtime_execution_gate_candidate")
        findings: list[RuntimeExecutionGateFinding] = []
        records: list[RuntimeExecutionGateRecord] = []
        readiness_records = {str(_as_mapping(record).get("record_id") or _as_mapping(record).get("candidate_id") or index): _as_mapping(record) for index, record in enumerate(readiness_records_raw)}
        for raw in candidates_raw:
            candidate = RuntimeExecutionGateCandidate.from_mapping(raw)
            if not candidate.candidate_id or candidate.candidate_type not in RUNTIME_EXECUTION_GATE_CANDIDATE_TYPES:
                return _blocked("invalid_runtime_execution_gate_candidate")
            readiness_record = readiness_records.get(candidate.record_id) or next(iter(readiness_records.values()))
            readiness_digest = str(readiness_packet.get("digest") or "")
            readiness_decision = str(readiness_record.get("readiness_decision") or readiness_record.get("decision") or "")
            if active_policy.require_ready_readiness_envelope and readiness_decision not in READY_READINESS_DECISIONS:
                return _blocked("readiness_envelope_not_ready", [RuntimeExecutionGateFinding("error", "readiness_envelope_not_ready", "readiness envelope decision is not ready", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_readiness_envelope_digest and candidate.claimed_readiness_envelope_digest != readiness_digest:
                return _blocked("readiness_envelope_digest_mismatch", [RuntimeExecutionGateFinding("error", "readiness_envelope_digest_mismatch", "readiness envelope digest mismatch", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_readiness_envelope_decision and candidate.claimed_readiness_envelope_decision != readiness_decision:
                return _blocked("readiness_envelope_decision_mismatch", [RuntimeExecutionGateFinding("error", "readiness_envelope_decision_mismatch", "readiness envelope decision mismatch", candidate.candidate_id, candidate.record_id)])
            final_digest = str(readiness_record.get("final_review_digest") or "")
            final_decision = str(readiness_record.get("final_review_decision") or "")
            real_digest = str(readiness_record.get("real_root_admission_digest") or "")
            real_decision = str(readiness_record.get("real_root_admission_decision") or "")
            sandbox_digest = str(readiness_record.get("sandbox_commit_digest") or "")
            sandbox_decision = str(readiness_record.get("sandbox_commit_decision") or "")
            comparisons = [
                (active_policy.require_matching_final_review_digest, candidate.claimed_final_review_digest, final_digest, "final_review_digest_mismatch"),
                (active_policy.require_matching_final_review_decision, candidate.claimed_final_review_decision, final_decision, "final_review_decision_mismatch"),
                (active_policy.require_matching_real_root_admission_digest, candidate.claimed_real_root_admission_digest, real_digest, "real_root_admission_digest_mismatch"),
                (active_policy.require_matching_real_root_admission_decision, candidate.claimed_real_root_admission_decision, real_decision, "real_root_admission_decision_mismatch"),
                (active_policy.require_matching_sandbox_commit_digest, candidate.claimed_sandbox_commit_digest, sandbox_digest, "sandbox_commit_digest_mismatch"),
                (active_policy.require_matching_sandbox_commit_decision, candidate.claimed_sandbox_commit_decision, sandbox_decision, "sandbox_commit_decision_mismatch"),
            ]
            for enabled, claimed, actual, code in comparisons:
                if enabled and claimed != actual:
                    return _blocked(code, [RuntimeExecutionGateFinding("error", code, code.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            blocker = _claims_blocker(candidate, active_policy)
            if blocker:
                return _blocked(blocker, [RuntimeExecutionGateFinding("error", blocker, blocker.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            is_noop = candidate.candidate_type == "noop_runtime_execution_gate_candidate" or readiness_decision == "live_adapter_readiness_noop"
            if not is_noop:
                required = [
                    (candidate.claimed_sandbox_receipt_manifest_digest, "missing_sandbox_receipt_manifest_digest"),
                    (candidate.claimed_sandbox_rollback_manifest_digest, "missing_sandbox_rollback_manifest_digest"),
                    (candidate.sandbox_artifact_plan, "missing_sandbox_artifact_plan"),
                    (candidate.live_receipt_schema_metadata, "missing_live_receipt_schema_metadata"),
                    (candidate.live_rollback_schema_metadata, "missing_live_rollback_schema_metadata"),
                    (candidate.post_commit_verification_plan, "missing_post_commit_verification_plan"),
                    (candidate.abort_panic_stop_condition_metadata, "missing_abort_panic_stop_condition_metadata"),
                    (candidate.operator_runtime_confirmation_metadata, "missing_operator_runtime_confirmation_metadata"),
                    (candidate.operator_identity_role_metadata, "missing_operator_identity_role_metadata"),
                    (candidate.execution_window_metadata, "missing_execution_window_metadata"),
                    (candidate.dry_run_to_live_equivalence_metadata, "missing_dry_run_to_live_equivalence_metadata"),
                    (candidate.rollback_rehearsal_metadata, "missing_rollback_rehearsal_metadata"),
                    (candidate.post_execution_audit_metadata, "missing_post_execution_audit_metadata"),
                ]
                for value, code in required:
                    if not value:
                        return _blocked(code, [RuntimeExecutionGateFinding("error", code, code.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            readiness_scope = _as_tuple(readiness_record.get("operator_scope_keys"))
            final_scope = _as_tuple(readiness_record.get("final_review_scope_keys")) or readiness_scope
            real_scope = _as_tuple(readiness_record.get("real_root_admission_scope_keys"))
            sandbox_scope = _as_tuple(readiness_record.get("sandbox_scope_keys"))
            if active_policy.require_scope_alignment:
                scope_sets = [set(scope) for scope in (candidate.operator_scope_keys, readiness_scope, final_scope, real_scope, sandbox_scope) if scope]
                aligned = not scope_sets or all(scope == scope_sets[0] for scope in scope_sets)
                if not aligned:
                    if active_policy.allow_mixed_scope_diagnostic_packet and candidate.candidate_type == "mixed_runtime_execution_gate_candidate" and candidate.metadata.get("diagnostic_warning") is True:
                        findings.append(RuntimeExecutionGateFinding("warning", "scope_mismatch_diagnostic", "scope mismatch allowed for diagnostic packet", candidate.candidate_id, candidate.record_id))
                    else:
                        return _blocked("scope_mismatch", [RuntimeExecutionGateFinding("error", "scope_mismatch", "scope mismatch", candidate.candidate_id, candidate.record_id)])
            warning = bool(candidate.metadata.get("warning_only") or candidate.metadata.get("diagnostic_warning")) or readiness_decision.endswith("with_warnings") or any(f.severity == "warning" and f.candidate_id == candidate.candidate_id for f in findings)
            if warning:
                findings.append(RuntimeExecutionGateFinding("warning", "runtime_execution_gate_warning", "candidate is warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
            decision = _decision_for(candidate, readiness_decision, warning)
            precondition = {"metadata_only": True, "execution_performed": False, "live_executor_enabled": False, "operator_confirmation_required_later": True, "execution_window": dict(candidate.execution_window_metadata)}
            verification = {"post_commit_verification_performed": False, "post_execution_audit_required_later": True, "post_commit_verification_plan": dict(candidate.post_commit_verification_plan), "post_execution_audit_metadata": dict(candidate.post_execution_audit_metadata)}
            abort = {"abort_ready_metadata_only": True, "panic_stop_required": bool(candidate.abort_panic_stop_condition_metadata), "abort_panic_stop_condition_metadata": dict(candidate.abort_panic_stop_condition_metadata)}
            rollback = {"rollback_applied": False, "rollback_manifest_digest": candidate.claimed_sandbox_rollback_manifest_digest, "rollback_rehearsal_metadata": dict(candidate.rollback_rehearsal_metadata), "live_rollback_schema_metadata": dict(candidate.live_rollback_schema_metadata)}
            future_record = {"candidate_id": candidate.candidate_id, "eligible_for_future_real_live_memory_commit_executor_consideration": decision in {"runtime_execution_gate_ready_for_later_live_executor", "runtime_execution_gate_ready_with_warnings"}, "decision": decision, "real_live_commit_performed": False, "real_memory_root_access_performed": False, "live_executor_enabled": False, "future_real_live_memory_commit_executor_required": True, "future_operator_runtime_confirmation_required": True, "future_post_execution_audit_required": True, "operator_review_cannot_override_hard_blockers": True}
            records.append(RuntimeExecutionGateRecord(candidate.candidate_id, candidate.record_id, candidate.candidate_type, decision, readiness_decision, readiness_digest, str(readiness_record.get("digest") or ""), final_decision, final_digest, real_decision, real_digest, sandbox_decision, sandbox_digest, candidate.claimed_sandbox_receipt_manifest_digest, candidate.claimed_sandbox_rollback_manifest_digest, candidate.operator_scope_keys, readiness_scope, final_scope, real_scope, sandbox_scope, dict(candidate.sandbox_artifact_plan), precondition, verification, abort, rollback, dict(candidate.operator_runtime_confirmation_metadata), dict(candidate.operator_identity_role_metadata), dict(candidate.execution_window_metadata), dict(candidate.dry_run_to_live_equivalence_metadata), dict(candidate.rollback_rehearsal_metadata), dict(candidate.post_execution_audit_metadata), _safe_actions(decision), future_record).with_digest())
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for finding in findings if finding.severity == "warning")}
        for record in records:
            counts[record.execution_gate_decision] = counts.get(record.execution_gate_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {record.execution_gate_decision for record in records}
        if counts["warning_count"] or "runtime_execution_gate_ready_with_warnings" in decisions: status: RuntimeExecutionGateStatus = "runtime_execution_gate_ready_with_warnings"
        elif decisions <= {"runtime_execution_gate_noop"}: status = "runtime_execution_gate_noop"
        elif decisions <= {"runtime_execution_gate_deferred_for_operator_review"}: status = "runtime_execution_gate_deferred_for_operator_review"
        elif decisions <= {"runtime_execution_gate_rejected"}: status = "runtime_execution_gate_rejected"
        else: status = "runtime_execution_gate_ready"
        packet = RuntimeExecutionGatePacket(active_policy.schema_version, tuple(records)).with_digest()
        report = RuntimeExecutionGateReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return RuntimeExecutionGateResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("failed", [RuntimeExecutionGateFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: RuntimeExecutionGatePolicy | None = None) -> RuntimeExecutionGateResult:
    return evaluate_explicit_live_memory_runtime_execution_gate(payload, policy)


__all__ = [
    "FORBIDDEN_NEXT_STEPS", "INVARIANTS", "READY_READINESS_DECISIONS", "RUNTIME_EXECUTION_GATE_CANDIDATE_TYPES", "SAFE_NEXT_ACTIONS",
    "RuntimeExecutionGateCandidate", "RuntimeExecutionGateFinding", "RuntimeExecutionGatePacket", "RuntimeExecutionGatePolicy", "RuntimeExecutionGateRecord", "RuntimeExecutionGateReport", "RuntimeExecutionGateResult",
    "build_default_policy", "validate_policy", "evaluate_explicit_live_memory_runtime_execution_gate", "evaluate_packet",
]
