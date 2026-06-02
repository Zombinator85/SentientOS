"""Metadata-only real live-memory commit executor enablement gate.

The enablement gate consumes supplied Real Live Memory Commit Executor
Implementation Skeleton evidence and explicit enablement candidates to produce
only deterministic enablement-readiness metadata. It is default-deny and never
enables, activates, invokes, locks, creates lockfiles, touches real memory
roots, mutates memory, assembles prompts, retrieves live context, executes
actions, discloses externally, calls remote services, or grants authority,
policy, consent, or truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Mapping, Sequence

ExecutorEnablementStatus = Literal[
    "executor_enablement_ready",
    "executor_enablement_ready_with_warnings",
    "executor_enablement_deferred_for_operator_review",
    "executor_enablement_rejected",
    "executor_enablement_blocked",
    "executor_enablement_noop",
    "executor_enablement_invalid",
    "executor_enablement_failed",
]
ExecutorEnablementDecision = Literal[
    "executor_enablement_ready_for_later_constrained_enable_path",
    "executor_enablement_ready_with_warnings",
    "executor_enablement_deferred_for_operator_review",
    "executor_enablement_rejected",
    "executor_enablement_blocked",
    "executor_enablement_noop",
]

EXECUTOR_ENABLEMENT_CANDIDATE_TYPES = frozenset(
    {
        "ai_capsule_executor_enablement_candidate",
        "human_summary_executor_enablement_candidate",
        "dual_capsule_executor_enablement_candidate",
        "protect_receipt_executor_enablement_candidate",
        "merge_receipt_executor_enablement_candidate",
        "tomb_archive_executor_enablement_candidate",
        "tomb_deferred_executor_enablement_candidate",
        "operator_review_executor_enablement_candidate",
        "noop_executor_enablement_candidate",
        "mixed_executor_enablement_candidate",
    }
)
READY_SKELETON_DECISIONS = frozenset(
    {
        "executor_skeleton_ready_for_later_enablement_gate",
        "executor_skeleton_ready_with_warnings",
        "executor_skeleton_noop",
    }
)

INVARIANTS: dict[str, bool] = {
    "executor_enablement_gate_is_not_enabled_executor": True,
    "executor_enablement_gate_is_not_executor_enablement": True,
    "executor_enablement_gate_is_not_executor_invocation": True,
    "executor_enablement_gate_is_not_executor_activation": True,
    "executor_enablement_gate_is_not_lock_acquisition": True,
    "executor_enablement_gate_is_not_lockfile_creation": True,
    "executor_enablement_gate_is_not_memory_write": True,
    "executor_enablement_gate_is_not_memory_deletion": True,
    "executor_enablement_gate_is_not_memory_purge": True,
    "executor_enablement_gate_is_not_index_mutation": True,
    "executor_enablement_gate_is_not_capsule_persistence": True,
    "executor_enablement_gate_is_not_tomb_completion": True,
    "executor_enablement_gate_is_not_prompt_assembly": True,
    "executor_enablement_gate_is_not_live_context_retrieval": True,
    "executor_enablement_gate_is_not_action_execution": True,
    "executor_enablement_gate_is_not_external_disclosure": True,
    "executor_enablement_gate_is_not_live_commit_execution": True,
    "executor_enablement_gate_is_not_truth": True,
    "executor_enablement_gate_is_not_policy": True,
    "executor_enablement_gate_is_not_authority": True,
    "executor_enablement_gate_is_not_consent": True,
    "enablement_readiness_is_metadata_only": True,
    "disabled_posture_confirmation_is_metadata_only": True,
    "operator_enable_acknowledgement_is_metadata_only": True,
    "enablement_scope_is_metadata_only": True,
    "abort_readiness_is_metadata_only": True,
    "rollback_readiness_is_metadata_only": True,
    "post_enable_verification_is_metadata_only": True,
    "audit_readiness_is_metadata_only": True,
    "real_executor_enabled": False,
    "real_executor_enablement_enabled": False,
    "real_executor_invocation_enabled": False,
    "real_executor_activation_enabled": False,
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
    "future_constrained_executor_enable_path_required": True,
    "future_real_live_memory_commit_execution_required": True,
    "future_post_execution_audit_required": True,
}
FORBIDDEN_NEXT_STEPS = (
    "enable_executor",
    "invoke_executor",
    "activate_executor",
    "acquire_real_lock",
    "create_lockfile",
    "write_real_live_memory",
    "delete_real_live_memory",
    "purge_real_live_memory",
    "mutate_live_index",
    "persist_capsule",
    "complete_tomb",
    "apply_protection",
    "apply_merge",
    "assemble_prompt",
    "retrieve_live_context",
    "execute_action",
    "disclose_externally",
    "bypass_executor_skeleton",
    "bypass_invocation_harness",
    "bypass_activation_record",
    "bypass_preflight_packet",
    "bypass_lock_lease_gate",
    "bypass_executor_plan_packet",
    "bypass_runtime_execution_gate",
    "bypass_readiness_envelope",
    "bypass_final_review",
    "bypass_real_root_admission",
    "bypass_sandbox_commit",
    "direct_executor_execution",
)
FAIL_STATUSES = {"executor_enablement_blocked", "executor_enablement_invalid", "executor_enablement_failed"}

UPSTREAM_CHECKS = (
    ("executor_skeleton", "claimed_executor_skeleton_digest", "claimed_executor_skeleton_decision", "digest", "executor_skeleton_decision"),
    ("invocation_harness", "claimed_invocation_harness_digest", "claimed_invocation_harness_decision", "invocation_harness_digest", "invocation_harness_decision"),
    ("activation_record", "claimed_activation_record_digest", "claimed_activation_record_decision", "activation_record_digest", "activation_record_decision"),
    ("preflight_packet", "claimed_preflight_packet_digest", "claimed_preflight_packet_decision", "preflight_packet_digest", "preflight_packet_decision"),
    ("lock_lease_gate", "claimed_lock_lease_gate_digest", "claimed_lock_lease_gate_decision", "lock_lease_gate_digest", "lock_lease_gate_decision"),
    ("executor_plan_packet", "claimed_executor_plan_packet_digest", "claimed_executor_plan_decision", "executor_plan_packet_digest", "executor_plan_decision"),
    ("runtime_execution_gate", "claimed_runtime_execution_gate_digest", "claimed_runtime_execution_gate_decision", "runtime_execution_gate_digest", "runtime_execution_gate_decision"),
    ("readiness_envelope", "claimed_readiness_envelope_digest", "claimed_readiness_envelope_decision", "readiness_envelope_digest", "readiness_envelope_decision"),
    ("final_review", "claimed_final_review_digest", "claimed_final_review_decision", "final_review_digest", "final_review_decision"),
    ("real_root_admission", "claimed_real_root_admission_digest", "claimed_real_root_admission_decision", "real_root_admission_digest", "real_root_admission_decision"),
    ("sandbox_commit", "claimed_sandbox_commit_digest", "claimed_sandbox_commit_decision", "sandbox_commit_digest", "sandbox_commit_decision"),
)
NON_NOOP_METADATA_FIELDS = (
    "executor_api_metadata",
    "disabled_execution_posture_metadata",
    "receipt_envelope_schema_metadata",
    "rollback_envelope_schema_metadata",
    "abort_envelope_schema_metadata",
    "verification_envelope_schema_metadata",
    "audit_readiness_metadata",
    "invocation_readiness_metadata",
    "invocation_scope_metadata",
    "invocation_handoff_metadata",
    "invocation_disablement_metadata",
    "activation_readiness_metadata",
    "operator_acknowledgement_metadata",
    "operator_enablement_acknowledgement_metadata",
    "activation_scope_metadata",
    "execution_handoff_metadata",
    "final_preflight_readiness_metadata",
    "operation_inventory_digest_metadata",
    "safety_checklist_digest_metadata",
    "verification_checklist_digest_metadata",
    "abort_readiness_metadata",
    "rollback_readiness_metadata",
    "lock_lease_readiness_metadata",
    "operator_identity_role_metadata",
    "execution_window_metadata",
    "idempotency_key_metadata",
    "atomicity_boundary_metadata",
    "dry_run_to_live_equivalence_metadata",
    "rollback_rehearsal_metadata",
    "post_execution_audit_metadata",
    "constrained_enable_path_metadata",
    "future_live_execution_gate_metadata",
    "emergency_stop_metadata",
    "post_enable_verification_metadata",
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
class ExecutorEnablementPolicy:
    schema_version: str = "real-live-memory-commit-executor-enablement-gate/v1"
    default_posture: str = "deny"
    require_ready_executor_skeleton: bool = True
    require_scope_alignment: bool = True
    allow_mixed_scope_diagnostic_packet: bool = True
    block_forbidden_claims: bool = True
    real_executor_enabled: bool = False
    real_executor_enablement_enabled: bool = False
    real_executor_invocation_enabled: bool = False
    real_executor_activation_enabled: bool = False
    real_lock_acquisition_enabled: bool = False
    lockfile_creation_enabled: bool = False


@dataclass(frozen=True)
class ExecutorEnablementFinding:
    severity: str
    code: str
    message: str
    candidate_id: str = ""
    record_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutorEnablementCandidate:
    raw: Mapping[str, Any]
    candidate_id: str
    record_id: str
    candidate_type: str
    operator_scope_keys: tuple[str, ...]
    metadata: Mapping[str, Any]
    claims: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ExecutorEnablementCandidate":
        return cls(
            raw=raw,
            candidate_id=str(raw.get("candidate_id") or ""),
            record_id=str(raw.get("record_id") or raw.get("candidate_id") or ""),
            candidate_type=str(raw.get("candidate_type") or ""),
            operator_scope_keys=_as_tuple(raw.get("operator_scope_keys")),
            metadata=_as_mapping(raw.get("metadata")),
            claims=_as_mapping(raw.get("executor_enablement_claims") or raw.get("claims")),
        )


@dataclass(frozen=True)
class ExecutorEnablementRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    executor_enablement_decision: ExecutorEnablementDecision
    executor_skeleton_digest: str
    executor_skeleton_decision: str
    invocation_harness_digest: str
    invocation_harness_decision: str
    activation_record_digest: str
    activation_record_decision: str
    preflight_packet_digest: str
    preflight_packet_decision: str
    lock_lease_gate_digest: str
    lock_lease_gate_decision: str
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
    enablement_readiness_records: tuple[Mapping[str, Any], ...]
    disabled_posture_confirmation_records: tuple[Mapping[str, Any], ...]
    operator_enable_acknowledgement_records: tuple[Mapping[str, Any], ...]
    enablement_scope_records: tuple[Mapping[str, Any], ...]
    abort_readiness_records: tuple[Mapping[str, Any], ...]
    rollback_readiness_records: tuple[Mapping[str, Any], ...]
    post_enable_verification_records: tuple[Mapping[str, Any], ...]
    audit_readiness_records: tuple[Mapping[str, Any], ...]
    safe_next_actions: tuple[str, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    real_executor_enabled: bool = False
    real_executor_enablement_enabled: bool = False
    executor_invoked: bool = False
    executor_activated: bool = False
    lock_acquired: bool = False
    lockfile_created: bool = False
    live_commit_executed: bool = False
    live_execution_permission_granted: bool = False
    operator_review_cannot_override_hard_blockers: bool = True
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_digest(self) -> "ExecutorEnablementRecord":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class ExecutorEnablementPacket:
    schema_version: str
    records: tuple[ExecutorEnablementRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""
    executor_enablement_gate_is_not_enabled_executor: bool = True
    executor_enablement_gate_is_not_executor_enablement: bool = True
    executor_enablement_gate_is_not_executor_invocation: bool = True
    executor_enablement_gate_is_not_executor_activation: bool = True
    executor_enablement_gate_is_not_lock_acquisition: bool = True
    executor_enablement_gate_is_not_lockfile_creation: bool = True
    executor_enablement_gate_is_not_memory_write: bool = True
    executor_enablement_gate_is_not_memory_deletion: bool = True
    executor_enablement_gate_is_not_memory_purge: bool = True
    executor_enablement_gate_is_not_index_mutation: bool = True
    executor_enablement_gate_is_not_capsule_persistence: bool = True
    executor_enablement_gate_is_not_tomb_completion: bool = True
    executor_enablement_gate_is_not_prompt_assembly: bool = True
    executor_enablement_gate_is_not_live_context_retrieval: bool = True
    executor_enablement_gate_is_not_action_execution: bool = True
    executor_enablement_gate_is_not_external_disclosure: bool = True
    executor_enablement_gate_is_not_live_commit_execution: bool = True
    executor_enablement_gate_is_not_truth: bool = True
    executor_enablement_gate_is_not_policy: bool = True
    executor_enablement_gate_is_not_authority: bool = True
    executor_enablement_gate_is_not_consent: bool = True
    enablement_readiness_is_metadata_only: bool = True
    disabled_posture_confirmation_is_metadata_only: bool = True
    operator_enable_acknowledgement_is_metadata_only: bool = True
    enablement_scope_is_metadata_only: bool = True
    abort_readiness_is_metadata_only: bool = True
    rollback_readiness_is_metadata_only: bool = True
    post_enable_verification_is_metadata_only: bool = True
    audit_readiness_is_metadata_only: bool = True
    real_executor_enabled: bool = False
    real_executor_enablement_enabled: bool = False
    real_executor_invocation_enabled: bool = False
    real_executor_activation_enabled: bool = False
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
    future_constrained_executor_enable_path_required: bool = True
    future_real_live_memory_commit_execution_required: bool = True
    future_post_execution_audit_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_digest(self) -> "ExecutorEnablementPacket":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class ExecutorEnablementReport:
    status: ExecutorEnablementStatus
    findings: tuple[ExecutorEnablementFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [f.to_dict() for f in self.findings], "summary_counts": dict(self.summary_counts), "digest": self.digest}


@dataclass(frozen=True)
class ExecutorEnablementResult:
    status: ExecutorEnablementStatus
    packet: ExecutorEnablementPacket | None
    report: ExecutorEnablementReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> ExecutorEnablementPolicy:
    return ExecutorEnablementPolicy()


def validate_policy(policy: ExecutorEnablementPolicy | None = None) -> dict[str, Any]:
    active = policy or build_default_policy()
    raw = asdict(active)
    findings: list[dict[str, str]] = []
    if active.default_posture != "deny":
        findings.append({"severity": "error", "code": "default_posture_not_deny", "message": "executor enablement gate must default deny"})
    for key in ("real_executor_enabled", "real_executor_enablement_enabled", "real_executor_invocation_enabled", "real_executor_activation_enabled", "real_lock_acquisition_enabled", "lockfile_creation_enabled"):
        if raw.get(key) is not False:
            findings.append({"severity": "error", "code": key, "message": f"{key} must remain disabled"})
    status = "invalid" if findings else "valid"
    return {"status": status, "findings": findings, "policy": raw, "invariants": dict(INVARIANTS), "digest": _digest({"status": status, "findings": findings, "policy": raw, "invariants": INVARIANTS})}


def _policy_from_payload(payload: Mapping[str, Any], policy: ExecutorEnablementPolicy | None) -> ExecutorEnablementPolicy:
    if policy is not None:
        return policy
    raw_policy = payload.get("policy")
    if isinstance(raw_policy, Mapping):
        allowed = {field for field in ExecutorEnablementPolicy.__dataclass_fields__}
        return ExecutorEnablementPolicy(**{key: value for key, value in raw_policy.items() if key in allowed})
    return build_default_policy()


def _skeleton_packet(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = _as_mapping(payload.get("real_live_memory_commit_executor_implementation_skeleton") or payload.get("executor_skeleton") or payload.get("packet"))
    nested = _as_mapping(raw.get("packet"))
    return nested or raw


def _skeleton_record(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    records = _as_sequence(packet.get("records"))
    return _as_mapping(records[0]) if records else {}


def _packet_digest(packet: Mapping[str, Any]) -> str:
    return str(packet.get("digest") or _digest(packet))


def _packet_decision(record: Mapping[str, Any], packet: Mapping[str, Any]) -> str:
    return str(record.get("executor_skeleton_decision") or packet.get("decision") or packet.get("status") or "")


def _candidate_payloads(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = payload.get("executor_enablement_candidates", payload.get("executor_enablement_candidate", payload.get("candidates", ())))
    if isinstance(raw, Mapping):
        return (raw,)
    return tuple(item for item in _as_sequence(raw) if isinstance(item, Mapping))


def _blocked(code: str, findings: Sequence[ExecutorEnablementFinding] = ()) -> ExecutorEnablementResult:
    base = tuple(findings) or (ExecutorEnablementFinding("error", code, code.replace("_", " ")),)
    report = ExecutorEnablementReport("executor_enablement_blocked", base, {"error_count": sum(1 for f in base if f.severity == "error")})
    report = replace(report, digest=_digest(report.to_dict()))
    return ExecutorEnablementResult("executor_enablement_blocked", None, report, _digest({"status": "executor_enablement_blocked", "report": report.to_dict()}))


def _is_noop(candidate: ExecutorEnablementCandidate, skeleton_decision: str) -> bool:
    return candidate.candidate_type == "noop_executor_enablement_candidate" or skeleton_decision == "executor_skeleton_noop"


def _forbidden_claim(candidate: ExecutorEnablementCandidate, raw: Mapping[str, Any]) -> str | None:
    claims = candidate.claims
    if _flag(claims, "executor_enabled", "executor_enablement_enabled", "enablement_performed", "runtime_flag_flipped"):
        return "executor_enablement_claim"
    if _flag(claims, "executor_invoked", "live_executor_invoked", "executor_enablement_invoked_executor"):
        return "executor_invocation_claim"
    if _flag(claims, "executor_activated", "activation_execution_performed"):
        return "executor_activation_claim"
    if _flag(claims, "live_commit_executed", "runtime_execution_claimed", "direct_executor_execution_claimed"):
        return "live_commit_execution_claim"
    if _flag(claims, "permission_to_execute_now", "executor_enablement_grants_permission", "authority_to_execute_now"):
        return "executor_permission_claim"
    if _flag(claims, "receipt_envelope_is_live_receipt", "receipt_is_live_receipt"):
        return "live_receipt_claim"
    if _flag(claims, "rollback_envelope_applied", "rollback_applied"):
        return "applied_rollback_claim"
    if _flag(claims, "lock_acquired", "real_lock_acquired"):
        return "real_lock_acquisition_claim"
    if _flag(claims, "lockfile_created", "lockfile_creation_claimed"):
        return "lockfile_creation_claim"
    if _flag(claims, "real_memory_root_access_claimed", "real_memory_root_read_claimed", "real_memory_root_write_claimed"):
        return "real_memory_root_access_claim"
    if _flag(claims, "live_memory_write_claimed", "write_performed"):
        return "live_write_claim"
    if _flag(claims, "live_memory_delete_claimed", "delete_performed"):
        return "live_delete_claim"
    if _flag(claims, "live_memory_purge_claimed", "purge_performed"):
        return "live_purge_claim"
    if _flag(claims, "live_index_mutation_claimed", "index_mutation_performed"):
        return "index_mutation_claim"
    if _flag(claims, "capsule_persistence_claimed", "capsule_persisted"):
        return "capsule_persistence_claim"
    if _flag(claims, "tomb_completion_claimed", "tomb_completed"):
        return "tomb_completion_claim"
    if _flag(claims, "protection_application_claimed", "protection_applied"):
        return "protection_application_claim"
    if _flag(claims, "merge_application_claimed", "merge_applied"):
        return "merge_application_claim"
    if _flag(claims, "prompt_assembly_claimed", "prompt_materialized"):
        return "prompt_materialization"
    if _flag(claims, "live_context_retrieval_claimed", "live_context_retrieved"):
        return "live_context_retrieval"
    if _flag(claims, "action_execution_claimed", "action_executed"):
        return "action_execution"
    if _flag(claims, "external_disclosure_claimed", "disclosed_externally"):
        return "external_disclosure"
    if _flag(claims, "remote_service_called", "call_remote_service"):
        return "remote_service_call"
    if _flag(claims, "authority_granted"):
        return "authority_smuggling"
    if _flag(claims, "consent_granted"):
        return "consent_smuggling"
    if _flag(claims, "policy_created"):
        return "policy_smuggling"
    if _flag(claims, "truth_asserted"):
        return "truth_smuggling"
    if _has_raw_payload(raw):
        return "raw_payload_leakage"
    return None


def _metadata_record(kind: str, candidate: ExecutorEnablementCandidate, metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    record = {
        "kind": kind,
        "candidate_id": candidate.candidate_id,
        "record_id": candidate.record_id,
        "metadata": dict(metadata),
        "metadata_only": True,
        "executor_enabled": False,
        "live_execution_performed": False,
        "real_memory_mutation_performed": False,
    }
    return {**record, "digest": _digest(record)}


def _decision_for(candidate: ExecutorEnablementCandidate, skeleton_decision: str, warning: bool) -> ExecutorEnablementDecision:
    if _is_noop(candidate, skeleton_decision):
        return "executor_enablement_noop"
    if candidate.candidate_type == "operator_review_executor_enablement_candidate":
        return "executor_enablement_deferred_for_operator_review"
    if warning:
        return "executor_enablement_ready_with_warnings"
    return "executor_enablement_ready_for_later_constrained_enable_path"


def _safe_actions(decision: str) -> tuple[str, ...]:
    if decision == "executor_enablement_noop":
        return ("record_noop_metadata", "future_constrained_executor_enable_path_required")
    if decision == "executor_enablement_deferred_for_operator_review":
        return ("operator_review_metadata_only", "future_constrained_executor_enable_path_required", "future_real_live_memory_commit_execution_required")
    return ("archive_executor_enablement_gate_packet", "review_enablement_readiness_metadata", "future_constrained_executor_enable_path_required", "future_post_execution_audit_required")


def evaluate_real_live_memory_commit_executor_enablement_gate(payload: Mapping[str, Any], policy: ExecutorEnablementPolicy | None = None) -> ExecutorEnablementResult:
    try:
        active_policy = _policy_from_payload(payload, policy)
        policy_validation = validate_policy(active_policy)
        if policy_validation["status"] != "valid":
            return _blocked("invalid_policy", tuple(ExecutorEnablementFinding("error", f["code"], f["message"]) for f in policy_validation["findings"]))
        skeleton_packet = _skeleton_packet(payload)
        if not skeleton_packet:
            return _blocked("missing_executor_skeleton_packet")
        skeleton_record = _skeleton_record(skeleton_packet)
        if not skeleton_record:
            return _blocked("invalid_executor_skeleton_packet")
        skeleton_digest = _packet_digest(skeleton_packet)
        skeleton_decision = _packet_decision(skeleton_record, skeleton_packet)
        if active_policy.require_ready_executor_skeleton and skeleton_decision not in READY_SKELETON_DECISIONS:
            return _blocked("executor_skeleton_not_ready")
        raws = _candidate_payloads(payload)
        if not raws:
            return _blocked("missing_executor_enablement_candidate")
        records: list[ExecutorEnablementRecord] = []
        findings: list[ExecutorEnablementFinding] = []
        for raw in raws:
            candidate = ExecutorEnablementCandidate.from_mapping(raw)
            if not candidate.candidate_id or candidate.candidate_type not in EXECUTOR_ENABLEMENT_CANDIDATE_TYPES:
                return _blocked("invalid_executor_enablement_candidate", [ExecutorEnablementFinding("error", "invalid_executor_enablement_candidate", "candidate id and supported candidate type are required", candidate.candidate_id, candidate.record_id)])
            for label, digest_field, decision_field, expected_digest_field, expected_decision_field in UPSTREAM_CHECKS:
                expected_digest = skeleton_digest if label == "executor_skeleton" else str(skeleton_record.get(expected_digest_field) or "")
                expected_decision = skeleton_decision if label == "executor_skeleton" else str(skeleton_record.get(expected_decision_field) or "")
                if str(raw.get(digest_field) or raw.get(expected_digest_field) or "") != expected_digest:
                    code = f"{label}_digest_mismatch"
                    return _blocked(code, [ExecutorEnablementFinding("error", code, f"{code}: expected {expected_digest}", candidate.candidate_id, candidate.record_id)])
                if str(raw.get(decision_field) or raw.get(expected_decision_field) or "") != expected_decision:
                    code = f"{label}_decision_mismatch"
                    return _blocked(code, [ExecutorEnablementFinding("error", code, f"{code}: expected {expected_decision}", candidate.candidate_id, candidate.record_id)])
            if not _is_noop(candidate, skeleton_decision):
                for field in NON_NOOP_METADATA_FIELDS:
                    if not _as_mapping(raw.get(field)):
                        return _blocked(f"missing_{field}", [ExecutorEnablementFinding("error", f"missing_{field}", field.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            forbidden = _forbidden_claim(candidate, raw)
            if forbidden:
                return _blocked(forbidden, [ExecutorEnablementFinding("error", forbidden, forbidden.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            if active_policy.require_scope_alignment:
                scopes = [scope for scope in (candidate.operator_scope_keys, _as_tuple(skeleton_record.get("operator_scope_keys")), _as_tuple(skeleton_record.get("invocation_scope_keys")), _as_tuple(skeleton_record.get("lock_lease_scope_keys") or skeleton_record.get("lock_scope_keys")), _as_tuple(skeleton_record.get("executor_plan_scope_keys")), _as_tuple(skeleton_record.get("runtime_scope_keys")), _as_tuple(skeleton_record.get("readiness_scope_keys")), _as_tuple(skeleton_record.get("final_review_scope_keys")), _as_tuple(skeleton_record.get("real_root_admission_scope_keys")), _as_tuple(skeleton_record.get("sandbox_scope_keys"))) if scope]
                aligned = all(scope == scopes[0] for scope in scopes) if scopes else False
                if not aligned:
                    if active_policy.allow_mixed_scope_diagnostic_packet and candidate.candidate_type == "mixed_executor_enablement_candidate" and candidate.metadata.get("diagnostic_warning") is True:
                        findings.append(ExecutorEnablementFinding("warning", "scope_mismatch_diagnostic", "scope mismatch allowed for diagnostic packet", candidate.candidate_id, candidate.record_id))
                    else:
                        return _blocked("scope_mismatch", [ExecutorEnablementFinding("error", "scope_mismatch", "scope keys must align across upstream evidence and candidate", candidate.candidate_id, candidate.record_id)])
            warning = bool(candidate.metadata.get("warning_only") or candidate.metadata.get("diagnostic_warning")) or skeleton_decision.endswith("with_warnings") or any(f.severity == "warning" and f.candidate_id == candidate.candidate_id for f in findings)
            if warning:
                findings.append(ExecutorEnablementFinding("warning", "executor_enablement_warning", "candidate is warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
            decision = _decision_for(candidate, skeleton_decision, warning)
            records.append(
                ExecutorEnablementRecord(
                    candidate.candidate_id,
                    candidate.record_id,
                    candidate.candidate_type,
                    decision,
                    skeleton_digest,
                    skeleton_decision,
                    str(skeleton_record.get("invocation_harness_digest") or ""),
                    str(skeleton_record.get("invocation_harness_decision") or ""),
                    str(skeleton_record.get("activation_record_digest") or ""),
                    str(skeleton_record.get("activation_record_decision") or ""),
                    str(skeleton_record.get("preflight_packet_digest") or ""),
                    str(skeleton_record.get("preflight_packet_decision") or ""),
                    str(skeleton_record.get("lock_lease_gate_digest") or ""),
                    str(skeleton_record.get("lock_lease_gate_decision") or ""),
                    str(skeleton_record.get("executor_plan_packet_digest") or ""),
                    str(skeleton_record.get("executor_plan_decision") or ""),
                    str(skeleton_record.get("runtime_execution_gate_digest") or ""),
                    str(skeleton_record.get("runtime_execution_gate_decision") or ""),
                    str(skeleton_record.get("readiness_envelope_digest") or ""),
                    str(skeleton_record.get("readiness_envelope_decision") or ""),
                    str(skeleton_record.get("final_review_digest") or ""),
                    str(skeleton_record.get("final_review_decision") or ""),
                    str(skeleton_record.get("real_root_admission_digest") or ""),
                    str(skeleton_record.get("real_root_admission_decision") or ""),
                    str(skeleton_record.get("sandbox_commit_digest") or ""),
                    str(skeleton_record.get("sandbox_commit_decision") or ""),
                    candidate.operator_scope_keys,
                    (_metadata_record("enablement_readiness", candidate, _as_mapping(raw.get("constrained_enable_path_metadata"))),),
                    (_metadata_record("disabled_posture_confirmation", candidate, _as_mapping(raw.get("disabled_execution_posture_metadata"))),),
                    (_metadata_record("operator_enable_acknowledgement", candidate, _as_mapping(raw.get("operator_enablement_acknowledgement_metadata"))),),
                    (_metadata_record("enablement_scope", candidate, _as_mapping(raw.get("activation_scope_metadata") or raw.get("invocation_scope_metadata"))),),
                    (_metadata_record("abort_readiness", candidate, _as_mapping(raw.get("abort_readiness_metadata"))),),
                    (_metadata_record("rollback_readiness", candidate, _as_mapping(raw.get("rollback_readiness_metadata"))),),
                    (_metadata_record("post_enable_verification", candidate, _as_mapping(raw.get("post_enable_verification_metadata"))),),
                    (_metadata_record("audit_readiness", candidate, _as_mapping(raw.get("audit_readiness_metadata"))),),
                    _safe_actions(decision),
                ).with_digest()
            )
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for finding in findings if finding.severity == "warning")}
        for record in records:
            counts[record.executor_enablement_decision] = counts.get(record.executor_enablement_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {record.executor_enablement_decision for record in records}
        if counts["warning_count"] or "executor_enablement_ready_with_warnings" in decisions:
            status: ExecutorEnablementStatus = "executor_enablement_ready_with_warnings"
        elif decisions <= {"executor_enablement_noop"}:
            status = "executor_enablement_noop"
        elif decisions <= {"executor_enablement_deferred_for_operator_review"}:
            status = "executor_enablement_deferred_for_operator_review"
        else:
            status = "executor_enablement_ready"
        packet = ExecutorEnablementPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = ExecutorEnablementReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return ExecutorEnablementResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:  # fail closed for malformed metadata
        return _blocked("failed", [ExecutorEnablementFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: ExecutorEnablementPolicy | None = None) -> ExecutorEnablementResult:
    return evaluate_real_live_memory_commit_executor_enablement_gate(payload, policy)


__all__ = [
    "FAIL_STATUSES",
    "FORBIDDEN_NEXT_STEPS",
    "INVARIANTS",
    "EXECUTOR_ENABLEMENT_CANDIDATE_TYPES",
    "READY_SKELETON_DECISIONS",
    "ExecutorEnablementCandidate",
    "ExecutorEnablementFinding",
    "ExecutorEnablementPacket",
    "ExecutorEnablementPolicy",
    "ExecutorEnablementRecord",
    "ExecutorEnablementReport",
    "ExecutorEnablementResult",
    "build_default_policy",
    "validate_policy",
    "evaluate_real_live_memory_commit_executor_enablement_gate",
    "evaluate_packet",
]
