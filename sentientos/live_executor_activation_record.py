"""Deterministic metadata-only live executor activation records.

This module consumes supplied Live Executor Preflight Packet evidence plus
explicit activation candidates and emits deterministic activation-readiness
records for a later real live-memory commit executor. It never activates an
executor, acquires locks, creates lockfiles, inspects real lockfiles, writes,
deletes, purges, indexes, persists capsules, completes tombs, applies
protection or merge operations, assembles prompts, retrieves live context,
executes actions, discloses externally, invokes remote services, touches real
memory roots, grants truth, creates policy, infers consent, or grants authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Mapping, Sequence

ActivationStatus = Literal[
    "activation_ready", "activation_ready_with_warnings", "activation_deferred_for_operator_review",
    "activation_rejected", "activation_blocked", "activation_noop", "activation_invalid", "activation_failed",
]
ActivationDecision = Literal[
    "activation_record_ready_for_later_live_executor", "activation_record_ready_with_warnings",
    "activation_record_deferred_for_operator_review", "activation_record_rejected", "activation_record_blocked",
    "activation_record_noop",
]

ACTIVATION_CANDIDATE_TYPES = frozenset({
    "ai_capsule_activation_candidate", "human_summary_activation_candidate", "dual_capsule_activation_candidate",
    "protect_receipt_activation_candidate", "merge_receipt_activation_candidate", "tomb_archive_activation_candidate",
    "tomb_deferred_activation_candidate", "operator_review_activation_candidate", "noop_activation_candidate",
    "mixed_activation_candidate",
})
READY_PREFLIGHT_DECISIONS = frozenset({"preflight_ready_for_later_live_executor", "preflight_ready_with_warnings", "preflight_noop"})

INVARIANTS: dict[str, bool] = {
    "activation_record_is_not_executor_activation": True,
    "activation_record_is_not_lock_acquisition": True,
    "activation_record_is_not_lockfile_creation": True,
    "activation_record_is_not_memory_write": True,
    "activation_record_is_not_memory_deletion": True,
    "activation_record_is_not_memory_purge": True,
    "activation_record_is_not_index_mutation": True,
    "activation_record_is_not_capsule_persistence": True,
    "activation_record_is_not_tomb_completion": True,
    "activation_record_is_not_prompt_assembly": True,
    "activation_record_is_not_live_context_retrieval": True,
    "activation_record_is_not_action_execution": True,
    "activation_record_is_not_external_disclosure": True,
    "activation_record_is_not_live_commit_execution": True,
    "activation_record_is_not_truth": True,
    "activation_record_is_not_policy": True,
    "activation_record_is_not_authority": True,
    "activation_record_is_not_consent": True,
    "activation_readiness_is_metadata_only": True,
    "operator_acknowledgement_is_metadata_only": True,
    "activation_scope_is_metadata_only": True,
    "execution_handoff_is_metadata_only": True,
    "abort_readiness_is_metadata_only": True,
    "rollback_readiness_is_metadata_only": True,
    "audit_readiness_is_metadata_only": True,
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
    "live_executor_enabled": False,
    "future_real_live_memory_commit_executor_required": True,
    "future_live_executor_invocation_harness_required": True,
    "future_post_execution_audit_required": True,
}
FORBIDDEN_NEXT_STEPS = (
    "activate_executor", "acquire_real_lock", "create_lockfile", "write_real_live_memory", "delete_real_live_memory",
    "purge_real_live_memory", "mutate_live_index", "persist_capsule", "complete_tomb", "apply_protection",
    "apply_merge", "assemble_prompt", "retrieve_live_context", "execute_action", "disclose_externally",
    "invoke_remote_service", "bypass_preflight_packet", "bypass_lock_lease_gate", "bypass_executor_plan_packet",
    "bypass_runtime_execution_gate", "bypass_readiness_envelope", "bypass_final_review", "bypass_real_root_admission",
    "bypass_sandbox_commit", "direct_executor_invocation",
)
FAIL_STATUSES = {"activation_blocked", "activation_invalid", "activation_failed"}


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
class ActivationPolicy:
    schema_version: str = "live-executor-activation-record/v1"
    default_posture: str = "deny"
    require_ready_preflight_packet: bool = True
    require_matching_preflight_packet_digest: bool = True
    require_matching_preflight_packet_decision: bool = True
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
    require_non_noop_final_preflight_readiness_metadata: bool = True
    require_non_noop_operation_inventory_digest_metadata: bool = True
    require_non_noop_safety_checklist_digest_metadata: bool = True
    require_non_noop_verification_checklist_digest_metadata: bool = True
    require_non_noop_abort_readiness_metadata: bool = True
    require_non_noop_rollback_readiness_metadata: bool = True
    require_non_noop_audit_readiness_metadata: bool = True
    require_non_noop_lock_lease_readiness_metadata: bool = True
    require_non_noop_operator_identity_role_metadata: bool = True
    require_non_noop_operator_activation_acknowledgement_metadata: bool = True
    require_non_noop_execution_window_metadata: bool = True
    require_non_noop_idempotency_key_metadata: bool = True
    require_non_noop_atomicity_boundary_metadata: bool = True
    require_non_noop_dry_run_to_live_equivalence_metadata: bool = True
    require_non_noop_rollback_rehearsal_metadata: bool = True
    require_non_noop_post_execution_audit_metadata: bool = True
    require_non_noop_activation_scope_metadata: bool = True
    require_non_noop_execution_handoff_metadata: bool = True
    require_non_noop_future_executor_requirement_metadata: bool = True
    require_scope_alignment: bool = True
    allow_mixed_scope_diagnostic_packet: bool = True
    block_executor_activation_claims: bool = True
    block_preflight_execution_claims: bool = True
    block_lock_acquisition_claims: bool = True
    block_lockfile_creation_claims: bool = True
    block_live_mutation_claims: bool = True
    block_real_memory_root_access_claims: bool = True
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
    real_executor_activation_enabled: bool = False
    real_lock_acquisition_enabled: bool = False
    lockfile_creation_enabled: bool = False
    live_executor_enabled: bool = False


@dataclass(frozen=True)
class ActivationFinding:
    severity: str
    code: str
    message: str
    candidate_id: str = ""
    record_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActivationCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    claimed_preflight_packet_digest: str
    claimed_preflight_packet_decision: str
    claimed_lock_lease_gate_digest: str
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
    final_preflight_readiness_metadata: Mapping[str, Any]
    operation_inventory_digest_metadata: Mapping[str, Any]
    safety_checklist_digest_metadata: Mapping[str, Any]
    verification_checklist_digest_metadata: Mapping[str, Any]
    abort_readiness_metadata: Mapping[str, Any]
    rollback_readiness_metadata: Mapping[str, Any]
    audit_readiness_metadata: Mapping[str, Any]
    lock_lease_readiness_metadata: Mapping[str, Any]
    operator_identity_role_metadata: Mapping[str, Any]
    operator_activation_acknowledgement_metadata: Mapping[str, Any]
    execution_window_metadata: Mapping[str, Any]
    idempotency_key_metadata: Mapping[str, Any]
    atomicity_boundary_metadata: Mapping[str, Any]
    dry_run_to_live_equivalence_metadata: Mapping[str, Any]
    rollback_rehearsal_metadata: Mapping[str, Any]
    post_execution_audit_metadata: Mapping[str, Any]
    activation_scope_metadata: Mapping[str, Any]
    execution_handoff_metadata: Mapping[str, Any]
    future_executor_requirement_metadata: Mapping[str, Any]
    activation_claims: Mapping[str, Any]
    metadata: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ActivationCandidate":
        return cls(
            candidate_id=str(raw.get("candidate_id") or ""),
            record_id=str(raw.get("record_id") or raw.get("candidate_id") or ""),
            candidate_type=str(raw.get("candidate_type") or ""),
            claimed_preflight_packet_digest=str(raw.get("claimed_preflight_packet_digest") or raw.get("preflight_packet_digest") or ""),
            claimed_preflight_packet_decision=str(raw.get("claimed_preflight_packet_decision") or raw.get("preflight_packet_decision") or ""),
            claimed_lock_lease_gate_digest=str(raw.get("claimed_lock_lease_gate_digest") or raw.get("lock_lease_gate_digest") or raw.get("lock_lease_gate_packet_digest") or ""),
            claimed_lock_lease_gate_decision=str(raw.get("claimed_lock_lease_gate_decision") or raw.get("lock_lease_gate_decision") or raw.get("lock_lease_decision") or ""),
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
            final_preflight_readiness_metadata=_as_mapping(raw.get("final_preflight_readiness_metadata")),
            operation_inventory_digest_metadata=_as_mapping(raw.get("operation_inventory_digest_metadata")),
            safety_checklist_digest_metadata=_as_mapping(raw.get("safety_checklist_digest_metadata")),
            verification_checklist_digest_metadata=_as_mapping(raw.get("verification_checklist_digest_metadata")),
            abort_readiness_metadata=_as_mapping(raw.get("abort_readiness_metadata")),
            rollback_readiness_metadata=_as_mapping(raw.get("rollback_readiness_metadata")),
            audit_readiness_metadata=_as_mapping(raw.get("audit_readiness_metadata")),
            lock_lease_readiness_metadata=_as_mapping(raw.get("lock_lease_readiness_metadata")),
            operator_identity_role_metadata=_as_mapping(raw.get("operator_identity_role_metadata")),
            operator_activation_acknowledgement_metadata=_as_mapping(raw.get("operator_activation_acknowledgement_metadata")),
            execution_window_metadata=_as_mapping(raw.get("execution_window_metadata")),
            idempotency_key_metadata=_as_mapping(raw.get("idempotency_key_metadata")),
            atomicity_boundary_metadata=_as_mapping(raw.get("atomicity_boundary_metadata")),
            dry_run_to_live_equivalence_metadata=_as_mapping(raw.get("dry_run_to_live_equivalence_metadata")),
            rollback_rehearsal_metadata=_as_mapping(raw.get("rollback_rehearsal_metadata")),
            post_execution_audit_metadata=_as_mapping(raw.get("post_execution_audit_metadata")),
            activation_scope_metadata=_as_mapping(raw.get("activation_scope_metadata")),
            execution_handoff_metadata=_as_mapping(raw.get("execution_handoff_metadata")),
            future_executor_requirement_metadata=_as_mapping(raw.get("future_executor_requirement_metadata")),
            activation_claims=_as_mapping(raw.get("activation_claims") or raw.get("claims")),
            metadata=_as_mapping(raw.get("metadata")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActivationRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    activation_decision: ActivationDecision
    preflight_packet_digest: str
    preflight_packet_decision: str
    preflight_record_digest: str
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
    preflight_scope_keys: tuple[str, ...]
    lock_lease_scope_keys: tuple[str, ...]
    executor_plan_scope_keys: tuple[str, ...]
    runtime_scope_keys: tuple[str, ...]
    readiness_scope_keys: tuple[str, ...]
    final_review_scope_keys: tuple[str, ...]
    real_root_admission_scope_keys: tuple[str, ...]
    sandbox_scope_keys: tuple[str, ...]
    final_preflight_readiness_metadata: Mapping[str, Any]
    operation_inventory_digest_metadata: Mapping[str, Any]
    safety_checklist_digest_metadata: Mapping[str, Any]
    verification_checklist_digest_metadata: Mapping[str, Any]
    abort_readiness_metadata: Mapping[str, Any]
    rollback_readiness_metadata: Mapping[str, Any]
    audit_readiness_metadata: Mapping[str, Any]
    lock_lease_readiness_metadata: Mapping[str, Any]
    operator_identity_role_metadata: Mapping[str, Any]
    operator_activation_acknowledgement_metadata: Mapping[str, Any]
    execution_window_metadata: Mapping[str, Any]
    idempotency_key_metadata: Mapping[str, Any]
    atomicity_boundary_metadata: Mapping[str, Any]
    dry_run_to_live_equivalence_metadata: Mapping[str, Any]
    rollback_rehearsal_metadata: Mapping[str, Any]
    post_execution_audit_metadata: Mapping[str, Any]
    activation_scope_metadata: Mapping[str, Any]
    execution_handoff_metadata: Mapping[str, Any]
    future_executor_requirement_metadata: Mapping[str, Any]
    activation_readiness_records: tuple[Mapping[str, Any], ...]
    operator_acknowledgement_records: tuple[Mapping[str, Any], ...]
    activation_scope_records: tuple[Mapping[str, Any], ...]
    execution_handoff_records: tuple[Mapping[str, Any], ...]
    abort_readiness_records: tuple[Mapping[str, Any], ...]
    rollback_readiness_records: tuple[Mapping[str, Any], ...]
    audit_readiness_records: tuple[Mapping[str, Any], ...]
    safe_next_actions: tuple[str, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    activation_record_future_consideration_only: bool = True
    executor_activated: bool = False
    preflight_execution_performed: bool = False
    lock_acquired: bool = False
    lockfile_created: bool = False
    live_commit_executed: bool = False
    live_execution_permission_granted: bool = False
    operator_review_cannot_override_hard_blockers: bool = True
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_digest(self) -> "ActivationRecord":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class ActivationPacket:
    schema_version: str
    records: tuple[ActivationRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""
    activation_record_is_not_executor_activation: bool = True
    activation_record_is_not_lock_acquisition: bool = True
    activation_record_is_not_lockfile_creation: bool = True
    activation_record_is_not_memory_write: bool = True
    activation_record_is_not_memory_deletion: bool = True
    activation_record_is_not_memory_purge: bool = True
    activation_record_is_not_index_mutation: bool = True
    activation_record_is_not_capsule_persistence: bool = True
    activation_record_is_not_tomb_completion: bool = True
    activation_record_is_not_prompt_assembly: bool = True
    activation_record_is_not_live_context_retrieval: bool = True
    activation_record_is_not_action_execution: bool = True
    activation_record_is_not_external_disclosure: bool = True
    activation_record_is_not_live_commit_execution: bool = True
    activation_record_is_not_truth: bool = True
    activation_record_is_not_policy: bool = True
    activation_record_is_not_authority: bool = True
    activation_record_is_not_consent: bool = True
    activation_readiness_is_metadata_only: bool = True
    operator_acknowledgement_is_metadata_only: bool = True
    activation_scope_is_metadata_only: bool = True
    execution_handoff_is_metadata_only: bool = True
    abort_readiness_is_metadata_only: bool = True
    rollback_readiness_is_metadata_only: bool = True
    audit_readiness_is_metadata_only: bool = True
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
    live_executor_enabled: bool = False
    future_real_live_memory_commit_executor_required: bool = True
    future_live_executor_invocation_harness_required: bool = True
    future_post_execution_audit_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_digest(self) -> "ActivationPacket":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class ActivationReport:
    status: ActivationStatus
    findings: tuple[ActivationFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [f.to_dict() for f in self.findings], "summary_counts": dict(self.summary_counts), "digest": self.digest}


@dataclass(frozen=True)
class ActivationResult:
    status: ActivationStatus
    packet: ActivationPacket | None
    report: ActivationReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> ActivationPolicy:
    return ActivationPolicy()


def validate_policy(policy: ActivationPolicy | None = None) -> dict[str, Any]:
    active = policy or build_default_policy()
    raw = asdict(active)
    findings: list[dict[str, str]] = []
    if active.default_posture != "deny":
        findings.append({"severity": "error", "code": "default_posture_not_deny", "message": "activation record must default deny"})
    for key, expected in INVARIANTS.items():
        if raw.get(key, expected) != expected:
            findings.append({"severity": "error", "code": f"invariant_{key}_changed", "message": f"{key} must remain {expected}"})
    if active.real_executor_activation_enabled:
        findings.append({"severity": "error", "code": "real_executor_activation_enabled", "message": "real executor activation must remain disabled"})
    if active.real_lock_acquisition_enabled:
        findings.append({"severity": "error", "code": "real_lock_acquisition_enabled", "message": "real lock acquisition must remain disabled"})
    if active.lockfile_creation_enabled:
        findings.append({"severity": "error", "code": "lockfile_creation_enabled", "message": "lockfile creation must remain disabled"})
    if active.live_executor_enabled:
        findings.append({"severity": "error", "code": "live_executor_enabled", "message": "live executor must remain disabled"})
    status = "invalid" if findings else "valid"
    return {"status": status, "findings": findings, "policy": raw, "digest": _digest({"status": status, "findings": findings, "policy": raw})}


def _policy_from_payload(payload: Mapping[str, Any], policy: ActivationPolicy | None) -> ActivationPolicy:
    if policy is not None:
        return policy
    raw_policy = payload.get("policy")
    if isinstance(raw_policy, Mapping):
        allowed = {field for field in ActivationPolicy.__dataclass_fields__}
        return ActivationPolicy(**{key: value for key, value in raw_policy.items() if key in allowed})
    return build_default_policy()


def _preflight_packet(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = _as_mapping(payload.get("live_executor_preflight_packet") or payload.get("preflight_packet") or payload.get("packet"))
    nested = _as_mapping(raw.get("packet"))
    return nested or raw


def _candidate_payloads(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = payload.get("activation_candidates", payload.get("activation_candidate", payload.get("candidates", ())))
    if isinstance(raw, Mapping):
        return (raw,)
    return tuple(item for item in _as_sequence(raw) if isinstance(item, Mapping))


def _blocked(code: str, findings: Sequence[ActivationFinding] = ()) -> ActivationResult:
    base = tuple(findings) or (ActivationFinding("error", code, code.replace("_", " ")),)
    report = ActivationReport("activation_blocked", base, {"error_count": sum(1 for f in base if f.severity == "error")})
    report = replace(report, digest=_digest(report.to_dict()))
    return ActivationResult("activation_blocked", None, report, _digest({"status": "activation_blocked", "report": report.to_dict()}))


def _is_noop(candidate: ActivationCandidate, preflight_decision: str) -> bool:
    return candidate.candidate_type == "noop_activation_candidate" or preflight_decision == "preflight_noop"


def _require_non_noop_metadata(candidate: ActivationCandidate, policy: ActivationPolicy) -> str | None:
    checks: tuple[tuple[bool, str, Any], ...] = (
        (policy.require_non_noop_final_preflight_readiness_metadata, "missing_final_preflight_readiness_metadata", candidate.final_preflight_readiness_metadata),
        (policy.require_non_noop_operation_inventory_digest_metadata, "missing_operation_inventory_digest_metadata", candidate.operation_inventory_digest_metadata),
        (policy.require_non_noop_safety_checklist_digest_metadata, "missing_safety_checklist_digest_metadata", candidate.safety_checklist_digest_metadata),
        (policy.require_non_noop_verification_checklist_digest_metadata, "missing_verification_checklist_digest_metadata", candidate.verification_checklist_digest_metadata),
        (policy.require_non_noop_abort_readiness_metadata, "missing_abort_readiness_metadata", candidate.abort_readiness_metadata),
        (policy.require_non_noop_rollback_readiness_metadata, "missing_rollback_readiness_metadata", candidate.rollback_readiness_metadata),
        (policy.require_non_noop_audit_readiness_metadata, "missing_audit_readiness_metadata", candidate.audit_readiness_metadata),
        (policy.require_non_noop_lock_lease_readiness_metadata, "missing_lock_lease_readiness_metadata", candidate.lock_lease_readiness_metadata),
        (policy.require_non_noop_operator_identity_role_metadata, "missing_operator_identity_role_metadata", candidate.operator_identity_role_metadata),
        (policy.require_non_noop_operator_activation_acknowledgement_metadata, "missing_operator_activation_acknowledgement_metadata", candidate.operator_activation_acknowledgement_metadata),
        (policy.require_non_noop_execution_window_metadata, "missing_execution_window_metadata", candidate.execution_window_metadata),
        (policy.require_non_noop_idempotency_key_metadata, "missing_idempotency_key_metadata", candidate.idempotency_key_metadata),
        (policy.require_non_noop_atomicity_boundary_metadata, "missing_atomicity_boundary_metadata", candidate.atomicity_boundary_metadata),
        (policy.require_non_noop_dry_run_to_live_equivalence_metadata, "missing_dry_run_to_live_equivalence_metadata", candidate.dry_run_to_live_equivalence_metadata),
        (policy.require_non_noop_rollback_rehearsal_metadata, "missing_rollback_rehearsal_metadata", candidate.rollback_rehearsal_metadata),
        (policy.require_non_noop_post_execution_audit_metadata, "missing_post_execution_audit_metadata", candidate.post_execution_audit_metadata),
        (policy.require_non_noop_activation_scope_metadata, "missing_activation_scope_metadata", candidate.activation_scope_metadata),
        (policy.require_non_noop_execution_handoff_metadata, "missing_execution_handoff_metadata", candidate.execution_handoff_metadata),
        (policy.require_non_noop_future_executor_requirement_metadata, "missing_future_executor_requirement_metadata", candidate.future_executor_requirement_metadata),
    )
    for required, code, value in checks:
        if required and not value:
            return code
    return None


def _forbidden_claim(candidate: ActivationCandidate, policy: ActivationPolicy, raw: Mapping[str, Any]) -> str | None:
    claims = candidate.activation_claims
    all_data = {"candidate": candidate.to_dict(), "claims": claims, "candidate_input": raw}
    if policy.block_executor_activation_claims and _flag(claims, "executor_activated", "live_executor_activated", "activation_record_activated_executor", "real_executor_activation_enabled", "live_executor_enabled"):
        return "executor_activation_claim"
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
    if policy.block_runtime_execution_claims and _flag(claims, "runtime_execution_claimed", "live_commit_execution_claimed", "live_commit_executed", "ordered_operations_executed"):
        return "runtime_execution_claim"
    if policy.block_executor_permission_claims and _flag(claims, "activation_record_grants_permission", "permission_to_execute_now", "authority_to_execute_now", "preflight_packet_grants_permission", "lock_lease_gate_grants_permission", "executor_plan_grants_permission"):
        return "executor_permission_claim"
    if policy.block_readiness_conversion_claims and _flag(claims, "activation_readiness_is_live_execution", "preflight_readiness_is_live_execution", "readiness_envelope_is_runtime_permission", "readiness_envelope_is_execution_permission", "runtime_execution_gate_is_execution"):
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
    if policy.block_external_disclosure and _flag(claims, "external_disclosure_claimed", "external_disclosure_enabled", "disclose_externally"):
        return "external_disclosure"
    if policy.block_authority_smuggling and _flag(claims, "authority_granted", "authority_smuggled", "activation_record_is_authority"):
        return "authority_smuggling"
    if policy.block_consent_smuggling and _flag(claims, "consent_granted", "consent_smuggled", "activation_record_is_consent"):
        return "consent_smuggling"
    if policy.block_policy_smuggling and _flag(claims, "policy_created", "policy_smuggled", "activation_record_is_policy"):
        return "policy_smuggling"
    if policy.block_truth_smuggling and _flag(claims, "truth_asserted", "truth_smuggled", "activation_record_is_truth"):
        return "truth_smuggling"
    if policy.block_raw_payload_leakage and _has_raw_payload(all_data):
        return "raw_payload_leakage"
    return None


def _metadata_record(kind: str, candidate: ActivationCandidate, metadata: Mapping[str, Any], *, ready_key: str) -> Mapping[str, Any]:
    return {
        "record_type": kind,
        "candidate_id": candidate.candidate_id,
        "record_id": candidate.record_id,
        "metadata": dict(metadata),
        ready_key: True,
        "metadata_only": True,
        "executor_activated": False,
        "lock_acquired": False,
        "lockfile_created": False,
        "live_commit_executed": False,
        "real_memory_root_access_performed": False,
    }


def _decision_for(candidate: ActivationCandidate, preflight_decision: str, warning: bool) -> ActivationDecision:
    if _is_noop(candidate, preflight_decision):
        return "activation_record_noop"
    if candidate.candidate_type == "operator_review_activation_candidate":
        return "activation_record_deferred_for_operator_review"
    if warning:
        return "activation_record_ready_with_warnings"
    return "activation_record_ready_for_later_live_executor"


def _safe_actions(decision: str) -> tuple[str, ...]:
    if decision == "activation_record_noop":
        return ("record_noop_metadata", "retain_for_reviewer_trace")
    if decision == "activation_record_deferred_for_operator_review":
        return ("review_activation_metadata", "resolve_operator_review_before_future_executor")
    if decision == "activation_record_ready_with_warnings":
        return ("review_warnings", "rerun_activation_record_after_metadata_repair")
    return ("review_activation_record", "build_future_executor_invocation_harness_later", "run_future_post_execution_audit_later")


def evaluate_live_executor_activation_record(payload: Mapping[str, Any], policy: ActivationPolicy | None = None) -> ActivationResult:
    active_policy = _policy_from_payload(payload, policy)
    policy_check = validate_policy(active_policy)
    if policy_check["status"] != "valid":
        return _blocked("invalid_policy", tuple(ActivationFinding("error", str(f["code"]), str(f["message"])) for f in policy_check["findings"]))
    preflight = _preflight_packet(payload)
    if not preflight:
        return _blocked("missing_preflight_packet")
    candidates_raw = _candidate_payloads(payload)
    if not candidates_raw:
        return _blocked("missing_activation_candidate")
    preflight_digest = str(preflight.get("digest") or "")
    records_raw = tuple(item for item in _as_sequence(preflight.get("records")) if isinstance(item, Mapping))
    if not preflight_digest or not records_raw:
        return _blocked("invalid_preflight_packet")
    findings: list[ActivationFinding] = []
    records: list[ActivationRecord] = []
    try:
        by_record = {str(record.get("record_id") or record.get("candidate_id") or ""): record for record in records_raw}
        by_candidate = {str(record.get("candidate_id") or ""): record for record in records_raw}
        for raw in candidates_raw:
            candidate = ActivationCandidate.from_mapping(raw)
            if candidate.candidate_type not in ACTIVATION_CANDIDATE_TYPES or not candidate.candidate_id:
                return _blocked("invalid_activation_candidate", [ActivationFinding("error", "invalid_activation_candidate", "activation candidate type/id is invalid", candidate.candidate_id, candidate.record_id)])
            preflight_record = by_record.get(candidate.record_id) or by_candidate.get(candidate.candidate_id) or (records_raw[0] if len(records_raw) == 1 else {})
            if not preflight_record:
                return _blocked("missing_preflight_record", [ActivationFinding("error", "missing_preflight_record", "no matching preflight record", candidate.candidate_id, candidate.record_id)])
            preflight_decision = str(preflight_record.get("preflight_decision") or "")
            if active_policy.require_ready_preflight_packet and preflight_decision not in READY_PREFLIGHT_DECISIONS:
                return _blocked("preflight_packet_not_ready", [ActivationFinding("error", "preflight_packet_not_ready", "preflight packet decision is not ready/noop", candidate.candidate_id, candidate.record_id)])
            checks = (
                (active_policy.require_matching_preflight_packet_digest, "preflight_packet_digest_mismatch", candidate.claimed_preflight_packet_digest, preflight_digest),
                (active_policy.require_matching_preflight_packet_decision, "preflight_packet_decision_mismatch", candidate.claimed_preflight_packet_decision, preflight_decision),
                (active_policy.require_matching_lock_lease_gate_digest, "lock_lease_gate_digest_mismatch", candidate.claimed_lock_lease_gate_digest, str(preflight_record.get("lock_lease_gate_packet_digest") or preflight_record.get("preflight_packet_digest") or "")),
                (active_policy.require_matching_lock_lease_gate_decision, "lock_lease_gate_decision_mismatch", candidate.claimed_lock_lease_gate_decision, str(preflight_record.get("lock_lease_gate_decision") or preflight_record.get("preflight_decision") or "")),
                (active_policy.require_matching_executor_plan_packet_digest, "executor_plan_packet_digest_mismatch", candidate.claimed_executor_plan_packet_digest, str(preflight_record.get("executor_plan_packet_digest") or "")),
                (active_policy.require_matching_executor_plan_decision, "executor_plan_decision_mismatch", candidate.claimed_executor_plan_decision, str(preflight_record.get("executor_plan_decision") or "")),
                (active_policy.require_matching_runtime_execution_gate_digest, "runtime_execution_gate_digest_mismatch", candidate.claimed_runtime_execution_gate_digest, str(preflight_record.get("runtime_execution_gate_digest") or "")),
                (active_policy.require_matching_runtime_execution_gate_decision, "runtime_execution_gate_decision_mismatch", candidate.claimed_runtime_execution_gate_decision, str(preflight_record.get("runtime_execution_gate_decision") or "")),
                (active_policy.require_matching_readiness_envelope_digest, "readiness_envelope_digest_mismatch", candidate.claimed_readiness_envelope_digest, str(preflight_record.get("readiness_envelope_digest") or "")),
                (active_policy.require_matching_readiness_envelope_decision, "readiness_envelope_decision_mismatch", candidate.claimed_readiness_envelope_decision, str(preflight_record.get("readiness_envelope_decision") or "")),
                (active_policy.require_matching_final_review_digest, "final_review_digest_mismatch", candidate.claimed_final_review_digest, str(preflight_record.get("final_review_digest") or "")),
                (active_policy.require_matching_final_review_decision, "final_review_decision_mismatch", candidate.claimed_final_review_decision, str(preflight_record.get("final_review_decision") or "")),
                (active_policy.require_matching_real_root_admission_digest, "real_root_admission_digest_mismatch", candidate.claimed_real_root_admission_digest, str(preflight_record.get("real_root_admission_digest") or "")),
                (active_policy.require_matching_real_root_admission_decision, "real_root_admission_decision_mismatch", candidate.claimed_real_root_admission_decision, str(preflight_record.get("real_root_admission_decision") or "")),
                (active_policy.require_matching_sandbox_commit_digest, "sandbox_commit_digest_mismatch", candidate.claimed_sandbox_commit_digest, str(preflight_record.get("sandbox_commit_digest") or "")),
                (active_policy.require_matching_sandbox_commit_decision, "sandbox_commit_decision_mismatch", candidate.claimed_sandbox_commit_decision, str(preflight_record.get("sandbox_commit_decision") or "")),
            )
            for required, code, actual, expected in checks:
                if required and actual != expected:
                    return _blocked(code, [ActivationFinding("error", code, f"{code}: expected {expected}", candidate.candidate_id, candidate.record_id)])
            if not _is_noop(candidate, preflight_decision):
                missing = _require_non_noop_metadata(candidate, active_policy)
                if missing:
                    return _blocked(missing, [ActivationFinding("error", missing, missing.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            forbidden = _forbidden_claim(candidate, active_policy, raw)
            if forbidden:
                return _blocked(forbidden, [ActivationFinding("error", forbidden, forbidden.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            preflight_scope = _as_tuple(preflight_record.get("operator_scope_keys"))
            lock_scope = _as_tuple(preflight_record.get("lock_lease_scope_keys") or preflight_record.get("lock_scope_keys"))
            executor_scope = _as_tuple(preflight_record.get("executor_plan_scope_keys"))
            runtime_scope = _as_tuple(preflight_record.get("runtime_scope_keys"))
            readiness_scope = _as_tuple(preflight_record.get("readiness_scope_keys"))
            final_scope = _as_tuple(preflight_record.get("final_review_scope_keys"))
            real_scope = _as_tuple(preflight_record.get("real_root_admission_scope_keys"))
            sandbox_scope = _as_tuple(preflight_record.get("sandbox_scope_keys"))
            if active_policy.require_scope_alignment:
                scopes = [scope for scope in (candidate.operator_scope_keys, preflight_scope, lock_scope, executor_scope, runtime_scope, readiness_scope, final_scope, real_scope, sandbox_scope) if scope]
                aligned = all(scope == scopes[0] for scope in scopes) if scopes else False
                if not aligned:
                    if active_policy.allow_mixed_scope_diagnostic_packet and candidate.candidate_type == "mixed_activation_candidate" and candidate.metadata.get("diagnostic_warning") is True:
                        findings.append(ActivationFinding("warning", "scope_mismatch_diagnostic", "scope mismatch allowed for diagnostic packet", candidate.candidate_id, candidate.record_id))
                    else:
                        return _blocked("scope_mismatch", [ActivationFinding("error", "scope_mismatch", "scope mismatch", candidate.candidate_id, candidate.record_id)])
            warning = bool(candidate.metadata.get("warning_only") or candidate.metadata.get("diagnostic_warning")) or preflight_decision.endswith("with_warnings") or any(f.severity == "warning" and f.candidate_id == candidate.candidate_id for f in findings)
            if warning:
                findings.append(ActivationFinding("warning", "activation_warning", "candidate is warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
            decision = _decision_for(candidate, preflight_decision, warning)
            records.append(ActivationRecord(
                candidate.candidate_id, candidate.record_id, candidate.candidate_type, decision, preflight_digest, preflight_decision,
                str(preflight_record.get("digest") or ""), candidate.claimed_lock_lease_gate_digest, candidate.claimed_lock_lease_gate_decision,
                candidate.claimed_executor_plan_packet_digest, candidate.claimed_executor_plan_decision,
                candidate.claimed_runtime_execution_gate_digest, candidate.claimed_runtime_execution_gate_decision,
                candidate.claimed_readiness_envelope_digest, candidate.claimed_readiness_envelope_decision,
                candidate.claimed_final_review_digest, candidate.claimed_final_review_decision,
                candidate.claimed_real_root_admission_digest, candidate.claimed_real_root_admission_decision,
                candidate.claimed_sandbox_commit_digest, candidate.claimed_sandbox_commit_decision, candidate.operator_scope_keys,
                preflight_scope, lock_scope, executor_scope, runtime_scope, readiness_scope, final_scope, real_scope, sandbox_scope,
                dict(candidate.final_preflight_readiness_metadata), dict(candidate.operation_inventory_digest_metadata),
                dict(candidate.safety_checklist_digest_metadata), dict(candidate.verification_checklist_digest_metadata),
                dict(candidate.abort_readiness_metadata), dict(candidate.rollback_readiness_metadata), dict(candidate.audit_readiness_metadata),
                dict(candidate.lock_lease_readiness_metadata), dict(candidate.operator_identity_role_metadata),
                dict(candidate.operator_activation_acknowledgement_metadata), dict(candidate.execution_window_metadata),
                dict(candidate.idempotency_key_metadata), dict(candidate.atomicity_boundary_metadata), dict(candidate.dry_run_to_live_equivalence_metadata),
                dict(candidate.rollback_rehearsal_metadata), dict(candidate.post_execution_audit_metadata), dict(candidate.activation_scope_metadata),
                dict(candidate.execution_handoff_metadata), dict(candidate.future_executor_requirement_metadata),
                (_metadata_record("activation_readiness", candidate, candidate.final_preflight_readiness_metadata, ready_key="activation_ready_for_later_executor_consideration"),),
                (_metadata_record("operator_acknowledgement", candidate, candidate.operator_activation_acknowledgement_metadata, ready_key="operator_acknowledgement_recorded"),),
                (_metadata_record("activation_scope", candidate, candidate.activation_scope_metadata, ready_key="activation_scope_recorded"),),
                (_metadata_record("execution_handoff", candidate, candidate.execution_handoff_metadata, ready_key="execution_handoff_recorded"),),
                (_metadata_record("abort_readiness", candidate, candidate.abort_readiness_metadata, ready_key="abort_ready_for_later_executor_consideration"),),
                (_metadata_record("rollback_readiness", candidate, candidate.rollback_readiness_metadata, ready_key="rollback_ready_for_later_executor_consideration"),),
                (_metadata_record("audit_readiness", candidate, candidate.audit_readiness_metadata, ready_key="audit_ready_for_later_executor_consideration"),),
                _safe_actions(decision),
            ).with_digest())
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for finding in findings if finding.severity == "warning")}
        for record in records:
            counts[record.activation_decision] = counts.get(record.activation_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {record.activation_decision for record in records}
        if counts["warning_count"] or "activation_record_ready_with_warnings" in decisions:
            status: ActivationStatus = "activation_ready_with_warnings"
        elif decisions <= {"activation_record_noop"}:
            status = "activation_noop"
        elif decisions <= {"activation_record_deferred_for_operator_review"}:
            status = "activation_deferred_for_operator_review"
        else:
            status = "activation_ready"
        packet = ActivationPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = ActivationReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return ActivationResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("failed", [ActivationFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: ActivationPolicy | None = None) -> ActivationResult:
    return evaluate_live_executor_activation_record(payload, policy)


__all__ = [
    "FAIL_STATUSES", "FORBIDDEN_NEXT_STEPS", "INVARIANTS", "ACTIVATION_CANDIDATE_TYPES", "READY_PREFLIGHT_DECISIONS",
    "ActivationCandidate", "ActivationFinding", "ActivationPacket", "ActivationPolicy", "ActivationRecord", "ActivationReport", "ActivationResult",
    "build_default_policy", "validate_policy", "evaluate_live_executor_activation_record", "evaluate_packet",
]
