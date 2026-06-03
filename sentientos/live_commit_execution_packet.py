"""Metadata-only live commit execution packet builder.

This module evaluates supplied Future Live Memory Commit Execution Gate evidence
plus explicit live commit execution packet candidates. It produces only
reviewable metadata for a later real live-memory commit execution path. It never
enables, activates, invokes, locks, creates lockfiles, touches real memory roots,
mutates memory, assembles prompts, retrieves live context, executes actions,
calls remote services, discloses externally, or grants authority, policy,
consent, or truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Mapping, Sequence

LiveCommitExecutionPacketStatus = Literal[
    "live_commit_execution_packet_ready",
    "live_commit_execution_packet_ready_with_warnings",
    "live_commit_execution_packet_deferred_for_operator_review",
    "live_commit_execution_packet_rejected",
    "live_commit_execution_packet_blocked",
    "live_commit_execution_packet_noop",
    "live_commit_execution_packet_invalid",
    "live_commit_execution_packet_failed",
]
LiveCommitExecutionPacketDecision = Literal[
    "live_commit_execution_packet_ready_for_later_real_executor",
    "live_commit_execution_packet_ready_with_warnings",
    "live_commit_execution_packet_deferred_for_operator_review",
    "live_commit_execution_packet_rejected",
    "live_commit_execution_packet_blocked",
    "live_commit_execution_packet_noop",
]

LIVE_COMMIT_EXECUTION_PACKET_CANDIDATE_TYPES = frozenset(
    {
        "ai_capsule_live_commit_execution_packet_candidate",
        "human_summary_live_commit_execution_packet_candidate",
        "dual_capsule_live_commit_execution_packet_candidate",
        "protect_receipt_live_commit_execution_packet_candidate",
        "merge_receipt_live_commit_execution_packet_candidate",
        "tomb_archive_live_commit_execution_packet_candidate",
        "tomb_deferred_live_commit_execution_packet_candidate",
        "operator_review_live_commit_execution_packet_candidate",
        "noop_live_commit_execution_packet_candidate",
        "mixed_live_commit_execution_packet_candidate",
    }
)
READY_FUTURE_EXECUTION_GATE_DECISIONS = frozenset(
    {
        "future_execution_gate_ready_for_later_live_commit_execution_packet",
        "future_execution_gate_ready_with_warnings",
        "future_execution_gate_noop",
    }
)
FAIL_STATUSES = {
    "live_commit_execution_packet_blocked",
    "live_commit_execution_packet_invalid",
    "live_commit_execution_packet_failed",
}

INVARIANTS: dict[str, bool] = {
    "live_commit_execution_packet_is_not_live_commit_execution": True,
    "live_commit_execution_packet_is_not_enabled_executor": True,
    "live_commit_execution_packet_is_not_executor_enablement": True,
    "live_commit_execution_packet_is_not_executor_invocation": True,
    "live_commit_execution_packet_is_not_executor_activation": True,
    "live_commit_execution_packet_is_not_lock_acquisition": True,
    "live_commit_execution_packet_is_not_lockfile_creation": True,
    "live_commit_execution_packet_is_not_memory_write": True,
    "live_commit_execution_packet_is_not_memory_deletion": True,
    "live_commit_execution_packet_is_not_memory_purge": True,
    "live_commit_execution_packet_is_not_index_mutation": True,
    "live_commit_execution_packet_is_not_capsule_persistence": True,
    "live_commit_execution_packet_is_not_tomb_completion": True,
    "live_commit_execution_packet_is_not_prompt_assembly": True,
    "live_commit_execution_packet_is_not_live_context_retrieval": True,
    "live_commit_execution_packet_is_not_action_execution": True,
    "live_commit_execution_packet_is_not_external_disclosure": True,
    "live_commit_execution_packet_is_not_truth": True,
    "live_commit_execution_packet_is_not_policy": True,
    "live_commit_execution_packet_is_not_authority": True,
    "live_commit_execution_packet_is_not_consent": True,
    "packet_readiness_is_metadata_only": True,
    "operation_bundle_is_metadata_only": True,
    "operation_bundle_records_are_intents_only": True,
    "execution_preconditions_are_metadata_only": True,
    "emergency_stop_confirmation_is_metadata_only": True,
    "operator_execution_acknowledgement_is_metadata_only": True,
    "receipt_envelope_readiness_is_metadata_only": True,
    "rollback_readiness_is_metadata_only": True,
    "verification_readiness_is_metadata_only": True,
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
    "external_service_enabled": False,
    "future_real_live_memory_commit_execution_required": True,
    "future_post_execution_audit_required": True,
    "future_executor_runtime_enablement_required": True,
}
FORBIDDEN_NEXT_STEPS = (
    "execute_live_commit", "enable_executor", "invoke_executor", "activate_executor", "acquire_real_lock",
    "create_lockfile", "write_real_live_memory", "delete_real_live_memory", "purge_real_live_memory",
    "mutate_live_index", "persist_capsule", "complete_tomb", "apply_protection", "apply_merge",
    "assemble_prompt", "retrieve_live_context", "execute_action", "disclose_externally", "bypass_sandbox",
    "bypass_real_root_admission", "bypass_final_review", "bypass_readiness_envelope", "bypass_runtime_gate",
    "bypass_executor_plan", "bypass_lock_lease", "bypass_preflight", "bypass_activation_record",
    "bypass_invocation_harness", "bypass_executor_skeleton", "bypass_enablement_gate",
    "bypass_constrained_path", "bypass_future_execution_gate", "direct_executor_execution",
)

UPSTREAM_CHECKS = (
    ("future_execution_gate", "claimed_future_execution_gate_digest", "claimed_future_execution_gate_decision", "__packet_digest__", "future_execution_gate_decision"),
    ("constrained_enablement_path", "claimed_constrained_enablement_path_packet_digest", "claimed_constrained_enablement_path_decision", "constrained_enablement_path_packet_digest", "constrained_enablement_path_decision"),
    ("executor_enablement_gate", "claimed_executor_enablement_gate_digest", "claimed_executor_enablement_gate_decision", "executor_enablement_gate_digest", "executor_enablement_gate_decision"),
    ("executor_skeleton", "claimed_executor_skeleton_digest", "claimed_executor_skeleton_decision", "executor_skeleton_digest", "executor_skeleton_decision"),
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
    "future_execution_readiness_metadata", "constrained_path_confirmation_metadata", "emergency_stop_confirmation_metadata",
    "operator_execution_acknowledgement_metadata", "execution_precondition_metadata", "execution_abort_condition_metadata",
    "execution_rollback_condition_metadata", "execution_verification_expectation_metadata", "execution_audit_expectation_metadata",
    "enablement_path_readiness_metadata", "staged_enablement_requirements_metadata", "constrained_enable_path_metadata",
    "enablement_precondition_metadata", "enablement_abort_condition_metadata", "enablement_rollback_condition_metadata",
    "enablement_audit_expectation_metadata", "future_live_execution_gate_metadata", "enablement_readiness_metadata",
    "disabled_posture_confirmation_metadata", "operator_enablement_acknowledgement_metadata", "enablement_scope_metadata",
    "executor_api_metadata", "disabled_execution_posture_metadata", "receipt_envelope_schema_metadata",
    "rollback_envelope_schema_metadata", "abort_envelope_schema_metadata", "verification_envelope_schema_metadata",
    "audit_readiness_metadata", "invocation_readiness_metadata", "invocation_scope_metadata", "invocation_handoff_metadata",
    "invocation_disablement_metadata", "activation_readiness_metadata", "operator_acknowledgement_metadata",
    "activation_scope_metadata", "execution_handoff_metadata", "final_preflight_readiness_metadata",
    "operation_inventory_digest_metadata", "safety_checklist_digest_metadata", "verification_checklist_digest_metadata",
    "abort_readiness_metadata", "rollback_readiness_metadata", "lock_lease_readiness_metadata",
    "operator_identity_role_metadata", "execution_window_metadata", "idempotency_key_metadata", "atomicity_boundary_metadata",
    "dry_run_to_live_equivalence_metadata", "rollback_rehearsal_metadata", "post_execution_audit_metadata",
    "operation_bundle_metadata", "operation_bundle_digest_metadata", "receipt_envelope_readiness_metadata",
    "rollback_envelope_readiness_metadata", "verification_envelope_readiness_metadata", "audit_envelope_readiness_metadata",
    "final_execution_packet_scope_metadata", "future_real_executor_requirement_metadata",
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


def _flag(claims: Mapping[str, Any], *names: str) -> bool:
    return any(claims.get(name) is True for name in names)


@dataclass(frozen=True)
class LiveCommitExecutionPacketPolicy:
    schema_version: str = "sentientos.live_commit_execution_packet.v1"
    metadata_only: bool = True
    default_deny: bool = True
    allow_mixed_scope_diagnostic_packet: bool = True
    require_future_execution_gate_ready: bool = True
    block_executor_enablement_claims: bool = True
    block_executor_invocation_claims: bool = True
    block_executor_activation_claims: bool = True
    block_live_commit_execution_claims: bool = True
    block_executor_permission_claims: bool = True
    block_live_receipt_claims: bool = True
    block_applied_rollback_claims: bool = True
    block_live_memory_mutation_claims: bool = True
    block_prompt_materialization: bool = True
    block_live_context_retrieval: bool = True
    block_action_execution: bool = True
    block_external_disclosure: bool = True
    block_external_service_calls: bool = True
    block_authority_smuggling: bool = True
    block_consent_smuggling: bool = True
    block_policy_smuggling: bool = True
    block_truth_smuggling: bool = True
    block_raw_payload_leakage: bool = True
    real_executor_enabled: bool = False
    real_executor_enablement_enabled: bool = False
    real_executor_invocation_enabled: bool = False
    real_executor_activation_enabled: bool = False
    real_lock_acquisition_enabled: bool = False
    lockfile_creation_enabled: bool = False
    real_memory_root_write_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveCommitExecutionPacketCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    operator_scope_keys: tuple[str, ...]
    metadata: Mapping[str, Any]
    claims: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "LiveCommitExecutionPacketCandidate":
        return cls(
            candidate_id=str(raw.get("candidate_id") or ""),
            record_id=str(raw.get("record_id") or raw.get("candidate_id") or ""),
            candidate_type=str(raw.get("candidate_type") or ""),
            operator_scope_keys=_as_tuple(raw.get("operator_scope_keys")),
            metadata=_as_mapping(raw.get("metadata")),
            claims=_as_mapping(raw.get("live_commit_execution_packet_claims") or raw.get("claims")),
        )

    def is_noop(self, future_decision: str = "") -> bool:
        return self.candidate_type == "noop_live_commit_execution_packet_candidate" or future_decision == "future_execution_gate_noop"


@dataclass(frozen=True)
class LiveCommitExecutionPacketFinding:
    severity: str
    code: str
    message: str
    candidate_id: str = ""
    record_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MetadataRecord:
    record_type: str
    candidate_id: str
    record_id: str
    metadata_digest: str
    metadata_only: bool = True
    authoritative: bool = False
    executed: bool = False
    permission_granted: bool = False
    live_receipt: bool = False
    rollback_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveCommitExecutionPacketRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    live_commit_execution_packet_decision: LiveCommitExecutionPacketDecision
    future_execution_gate_digest: str
    future_execution_gate_decision: str
    constrained_enablement_path_packet_digest: str
    constrained_enablement_path_decision: str
    executor_enablement_gate_digest: str
    executor_enablement_gate_decision: str
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
    packet_readiness_records: tuple[MetadataRecord, ...]
    operation_bundle_records: tuple[MetadataRecord, ...]
    execution_precondition_records: tuple[MetadataRecord, ...]
    emergency_stop_confirmation_records: tuple[MetadataRecord, ...]
    operator_execution_acknowledgement_records: tuple[MetadataRecord, ...]
    receipt_envelope_readiness_records: tuple[MetadataRecord, ...]
    rollback_readiness_records: tuple[MetadataRecord, ...]
    verification_readiness_records: tuple[MetadataRecord, ...]
    audit_readiness_records: tuple[MetadataRecord, ...]
    safe_next_actions: tuple[str, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    real_executor_enabled: bool = False
    real_executor_enablement_enabled: bool = False
    real_executor_invocation_enabled: bool = False
    real_executor_activation_enabled: bool = False
    real_lock_acquisition_enabled: bool = False
    lockfile_created: bool = False
    live_commit_executed: bool = False
    live_execution_permission_granted: bool = False
    operation_bundle_records_are_intents_only: bool = True
    operator_review_cannot_override_hard_blockers: bool = True
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["packet_readiness_records"] = [record.to_dict() for record in self.packet_readiness_records]
        data["operation_bundle_records"] = [record.to_dict() for record in self.operation_bundle_records]
        data["execution_precondition_records"] = [record.to_dict() for record in self.execution_precondition_records]
        data["emergency_stop_confirmation_records"] = [record.to_dict() for record in self.emergency_stop_confirmation_records]
        data["operator_execution_acknowledgement_records"] = [record.to_dict() for record in self.operator_execution_acknowledgement_records]
        data["receipt_envelope_readiness_records"] = [record.to_dict() for record in self.receipt_envelope_readiness_records]
        data["rollback_readiness_records"] = [record.to_dict() for record in self.rollback_readiness_records]
        data["verification_readiness_records"] = [record.to_dict() for record in self.verification_readiness_records]
        data["audit_readiness_records"] = [record.to_dict() for record in self.audit_readiness_records]
        return data

    def with_digest(self) -> "LiveCommitExecutionPacketRecord":
        data = self.to_dict()
        data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class LiveCommitExecutionPacket:
    schema_version: str
    records: tuple[LiveCommitExecutionPacketRecord, ...]
    digest: str = ""
    live_commit_execution_packet_is_not_live_commit_execution: bool = True
    live_commit_execution_packet_is_not_enabled_executor: bool = True
    live_commit_execution_packet_is_not_executor_enablement: bool = True
    live_commit_execution_packet_is_not_executor_invocation: bool = True
    live_commit_execution_packet_is_not_executor_activation: bool = True
    live_commit_execution_packet_is_not_lock_acquisition: bool = True
    live_commit_execution_packet_is_not_lockfile_creation: bool = True
    live_commit_execution_packet_is_not_memory_write: bool = True
    live_commit_execution_packet_is_not_memory_deletion: bool = True
    live_commit_execution_packet_is_not_memory_purge: bool = True
    live_commit_execution_packet_is_not_index_mutation: bool = True
    live_commit_execution_packet_is_not_capsule_persistence: bool = True
    live_commit_execution_packet_is_not_tomb_completion: bool = True
    live_commit_execution_packet_is_not_prompt_assembly: bool = True
    live_commit_execution_packet_is_not_live_context_retrieval: bool = True
    live_commit_execution_packet_is_not_action_execution: bool = True
    live_commit_execution_packet_is_not_external_disclosure: bool = True
    live_commit_execution_packet_is_not_truth: bool = True
    live_commit_execution_packet_is_not_policy: bool = True
    live_commit_execution_packet_is_not_authority: bool = True
    live_commit_execution_packet_is_not_consent: bool = True
    packet_readiness_is_metadata_only: bool = True
    operation_bundle_is_metadata_only: bool = True
    operation_bundle_records_are_intents_only: bool = True
    execution_preconditions_are_metadata_only: bool = True
    emergency_stop_confirmation_is_metadata_only: bool = True
    operator_execution_acknowledgement_is_metadata_only: bool = True
    receipt_envelope_readiness_is_metadata_only: bool = True
    rollback_readiness_is_metadata_only: bool = True
    verification_readiness_is_metadata_only: bool = True
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
    external_service_enabled: bool = False
    future_real_live_memory_commit_execution_required: bool = True
    future_post_execution_audit_required: bool = True
    future_executor_runtime_enablement_required: bool = True
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["records"] = [record.to_dict() for record in self.records]
        return data

    def with_digest(self) -> "LiveCommitExecutionPacket":
        data = self.to_dict()
        data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class LiveCommitExecutionPacketReport:
    status: LiveCommitExecutionPacketStatus
    findings: tuple[LiveCommitExecutionPacketFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [f.to_dict() for f in self.findings], "summary_counts": dict(self.summary_counts), "digest": self.digest}


@dataclass(frozen=True)
class LiveCommitExecutionPacketResult:
    status: LiveCommitExecutionPacketStatus
    packet: LiveCommitExecutionPacket | None
    report: LiveCommitExecutionPacketReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> LiveCommitExecutionPacketPolicy:
    return LiveCommitExecutionPacketPolicy()


def validate_policy(policy: LiveCommitExecutionPacketPolicy | None = None) -> dict[str, Any]:
    active = policy or build_default_policy()
    findings: list[str] = []
    if not active.metadata_only:
        findings.append("metadata_only_must_be_true")
    if not active.default_deny:
        findings.append("default_deny_must_be_true")
    for key, expected in INVARIANTS.items():
        if key.endswith("_enabled") and getattr(active, key, expected) != expected:
            findings.append(f"{key}_must_remain_{expected}")
    return {"status": "valid" if not findings else "invalid", "findings": findings, "policy": active.to_dict(), "invariants": dict(INVARIANTS)}


def _blocked(code: str, findings: Sequence[LiveCommitExecutionPacketFinding] = ()) -> LiveCommitExecutionPacketResult:
    base = tuple(findings) or (LiveCommitExecutionPacketFinding("error", code, code.replace("_", " ")),)
    report = LiveCommitExecutionPacketReport("live_commit_execution_packet_blocked", base, {"error_count": sum(1 for f in base if f.severity == "error")})
    report = replace(report, digest=_digest(report.to_dict()))
    return LiveCommitExecutionPacketResult("live_commit_execution_packet_blocked", None, report, _digest({"status": "live_commit_execution_packet_blocked", "report": report.to_dict()}))


def _candidate_sequence(payload: Mapping[str, Any]) -> Sequence[Any]:
    raw = payload.get("live_commit_execution_packet_candidates", payload.get("live_commit_execution_packet_candidate", payload.get("candidates", ())))
    return _as_sequence(raw)


def _metadata_record(record_type: str, candidate: LiveCommitExecutionPacketCandidate, metadata: Mapping[str, Any]) -> MetadataRecord:
    return MetadataRecord(record_type, candidate.candidate_id, candidate.record_id, _digest(dict(metadata)))


def _scope_ok(candidate: LiveCommitExecutionPacketCandidate, gate_record: Mapping[str, Any], policy: LiveCommitExecutionPacketPolicy) -> bool:
    upstream_scope = _as_tuple(gate_record.get("operator_scope_keys"))
    if candidate.operator_scope_keys == upstream_scope:
        return True
    return policy.allow_mixed_scope_diagnostic_packet and candidate.candidate_type == "mixed_live_commit_execution_packet_candidate" and candidate.metadata.get("diagnostic_warning") is True


def _forbidden_claim_finding(candidate: LiveCommitExecutionPacketCandidate, policy: LiveCommitExecutionPacketPolicy) -> LiveCommitExecutionPacketFinding | None:
    claims = candidate.claims
    if policy.block_executor_enablement_claims and _flag(claims, "executor_enabled", "live_executor_enabled", "real_executor_enabled", "executor_enablement_enabled"):
        return LiveCommitExecutionPacketFinding("error", "executor_enablement_claim", "packet cannot claim executor enablement", candidate.candidate_id, candidate.record_id)
    if policy.block_executor_invocation_claims and _flag(claims, "executor_invoked", "live_executor_invoked", "real_executor_invocation_enabled"):
        return LiveCommitExecutionPacketFinding("error", "executor_invocation_claim", "packet cannot claim executor invocation", candidate.candidate_id, candidate.record_id)
    if policy.block_executor_activation_claims and _flag(claims, "executor_activated", "live_executor_activated", "real_executor_activation_enabled"):
        return LiveCommitExecutionPacketFinding("error", "executor_activation_claim", "packet cannot claim executor activation", candidate.candidate_id, candidate.record_id)
    if policy.block_live_commit_execution_claims and _flag(claims, "live_commit_executed", "live_execution_completed", "real_live_commit_executed"):
        return LiveCommitExecutionPacketFinding("error", "live_commit_execution_claim", "packet cannot claim live commit execution", candidate.candidate_id, candidate.record_id)
    if policy.block_executor_permission_claims and _flag(claims, "permission_to_execute_now", "authority_to_execute_now", "live_commit_execution_packet_grants_permission"):
        return LiveCommitExecutionPacketFinding("error", "executor_permission_claim", "packet cannot grant runtime execution permission", candidate.candidate_id, candidate.record_id)
    if policy.block_live_receipt_claims and _flag(claims, "receipt_envelope_is_live_receipt", "live_receipt_created", "sandbox_receipt_is_live_receipt"):
        return LiveCommitExecutionPacketFinding("error", "live_receipt_claim", "packet cannot claim live receipts", candidate.candidate_id, candidate.record_id)
    if policy.block_applied_rollback_claims and _flag(claims, "rollback_envelope_applied", "rollback_readiness_applied", "sandbox_rollback_manifest_applied"):
        return LiveCommitExecutionPacketFinding("error", "applied_rollback_claim", "packet cannot claim applied rollback", candidate.candidate_id, candidate.record_id)
    mutation_checks = [
        (("live_memory_write_claimed", "memory_written", "real_memory_root_write_enabled"), "live_write_claim"),
        (("live_memory_delete_claimed", "memory_deleted"), "live_delete_claim"),
        (("live_memory_purge_claimed", "memory_purged"), "live_purge_claim"),
        (("live_index_mutation_claimed", "index_mutated"), "index_mutation_claim"),
        (("capsule_persistence_claimed", "capsule_persisted"), "capsule_persistence_claim"),
        (("tomb_completion_claimed", "tomb_completed"), "tomb_completion_claim"),
        (("protection_application_claimed", "protection_applied"), "protection_application_claim"),
        (("merge_application_claimed", "merge_applied"), "merge_application_claim"),
    ]
    for names, code in mutation_checks:
        if policy.block_live_memory_mutation_claims and _flag(claims, *names):
            return LiveCommitExecutionPacketFinding("error", code, "packet cannot claim live memory mutation", candidate.candidate_id, candidate.record_id)
    if policy.block_prompt_materialization and _flag(claims, "prompt_assembly_claimed", "prompt_materialized"):
        return LiveCommitExecutionPacketFinding("error", "prompt_materialization", "packet cannot materialize prompts", candidate.candidate_id, candidate.record_id)
    if policy.block_live_context_retrieval and _flag(claims, "live_context_retrieval_claimed", "live_context_retrieved"):
        return LiveCommitExecutionPacketFinding("error", "live_context_retrieval", "packet cannot retrieve live context", candidate.candidate_id, candidate.record_id)
    if policy.block_action_execution and _flag(claims, "action_execution_claimed", "action_executed"):
        return LiveCommitExecutionPacketFinding("error", "action_execution", "packet cannot execute actions", candidate.candidate_id, candidate.record_id)
    if policy.block_external_disclosure and _flag(claims, "external_disclosure_claimed", "external_disclosed"):
        return LiveCommitExecutionPacketFinding("error", "external_disclosure", "packet cannot disclose externally", candidate.candidate_id, candidate.record_id)
    if policy.block_external_service_calls and _flag(claims, "remote_service_called", "external_service_called"):
        return LiveCommitExecutionPacketFinding("error", "remote_service_call", "packet cannot call external services", candidate.candidate_id, candidate.record_id)
    if _flag(claims, "lockfile_created", "lockfile_creation_enabled"):
        return LiveCommitExecutionPacketFinding("error", "lockfile_creation_claim", "packet cannot create lockfiles", candidate.candidate_id, candidate.record_id)
    if _flag(claims, "real_lock_acquired", "real_lock_acquisition_enabled"):
        return LiveCommitExecutionPacketFinding("error", "real_lock_acquisition_claim", "packet cannot acquire real locks", candidate.candidate_id, candidate.record_id)
    if _flag(claims, "real_memory_root_access_claimed", "real_memory_root_read", "real_memory_root_written"):
        return LiveCommitExecutionPacketFinding("error", "real_memory_root_access_claim", "packet cannot touch real memory roots", candidate.candidate_id, candidate.record_id)
    if policy.block_authority_smuggling and _flag(claims, "authority_granted", "authority_smuggled", "live_commit_execution_packet_is_authority"):
        return LiveCommitExecutionPacketFinding("error", "authority_smuggling", "packet cannot grant authority", candidate.candidate_id, candidate.record_id)
    if policy.block_consent_smuggling and _flag(claims, "consent_granted", "consent_smuggled", "live_commit_execution_packet_is_consent"):
        return LiveCommitExecutionPacketFinding("error", "consent_smuggling", "packet cannot infer consent", candidate.candidate_id, candidate.record_id)
    if policy.block_policy_smuggling and _flag(claims, "policy_created", "policy_smuggled", "live_commit_execution_packet_is_policy"):
        return LiveCommitExecutionPacketFinding("error", "policy_smuggling", "packet cannot create policy", candidate.candidate_id, candidate.record_id)
    if policy.block_truth_smuggling and _flag(claims, "truth_asserted", "truth_smuggled", "live_commit_execution_packet_is_truth"):
        return LiveCommitExecutionPacketFinding("error", "truth_smuggling", "packet cannot assert truth", candidate.candidate_id, candidate.record_id)
    return None


def _decision_for(candidate: LiveCommitExecutionPacketCandidate, future_decision: str, warning: bool) -> LiveCommitExecutionPacketDecision:
    if candidate.is_noop(future_decision):
        return "live_commit_execution_packet_noop"
    if candidate.candidate_type == "operator_review_live_commit_execution_packet_candidate":
        return "live_commit_execution_packet_deferred_for_operator_review"
    if warning:
        return "live_commit_execution_packet_ready_with_warnings"
    return "live_commit_execution_packet_ready_for_later_real_executor"


def _safe_actions(decision: str) -> tuple[str, ...]:
    if decision == "live_commit_execution_packet_noop":
        return ("record_noop_metadata", "keep_executor_disabled")
    if decision == "live_commit_execution_packet_deferred_for_operator_review":
        return ("operator_review_metadata_only", "repair_hard_blockers_before_any_future_path")
    if decision == "live_commit_execution_packet_ready_with_warnings":
        return ("review_warnings", "rerun_packet_after_metadata_repair", "keep_executor_disabled")
    return ("review_live_commit_execution_packet", "prepare_future_real_executor_runtime_enablement_later", "run_future_post_execution_audit_later")


def evaluate_live_commit_execution_packet(payload: Mapping[str, Any], policy: LiveCommitExecutionPacketPolicy | None = None) -> LiveCommitExecutionPacketResult:
    active_policy = policy or build_default_policy()
    validation = validate_policy(active_policy)
    if validation["status"] != "valid":
        return _blocked("invalid_policy", [LiveCommitExecutionPacketFinding("error", "invalid_policy", ",".join(validation["findings"]))])
    try:
        gate_packet = _as_mapping(payload.get("future_live_memory_commit_execution_gate_packet") or payload.get("future_execution_gate_packet"))
        gate_records = _as_sequence(gate_packet.get("records"))
        if not gate_packet or not gate_records:
            return _blocked("missing_future_execution_gate_packet")
        gate_digest = str(gate_packet.get("digest") or "")
        if not gate_digest:
            return _blocked("invalid_future_execution_gate_packet", [LiveCommitExecutionPacketFinding("error", "invalid_future_execution_gate_packet", "future execution gate packet digest is required")])
        candidates_raw = _candidate_sequence(payload)
        if not candidates_raw:
            return _blocked("missing_live_commit_execution_packet_candidate")
        findings: list[LiveCommitExecutionPacketFinding] = []
        records: list[LiveCommitExecutionPacketRecord] = []
        gate_record_by_id = {str(_as_mapping(r).get("record_id") or _as_mapping(r).get("candidate_id") or ""): _as_mapping(r) for r in gate_records}
        first_gate_record = _as_mapping(gate_records[0])
        for raw_any in candidates_raw:
            raw = _as_mapping(raw_any)
            candidate = LiveCommitExecutionPacketCandidate.from_mapping(raw)
            if not candidate.candidate_id or not candidate.record_id or candidate.candidate_type not in LIVE_COMMIT_EXECUTION_PACKET_CANDIDATE_TYPES:
                return _blocked("invalid_live_commit_execution_packet_candidate", [LiveCommitExecutionPacketFinding("error", "invalid_live_commit_execution_packet_candidate", "live commit execution packet candidate type/id is invalid", candidate.candidate_id, candidate.record_id)])
            gate_record = gate_record_by_id.get(str(raw.get("claimed_future_execution_gate_record_id") or raw.get("record_id") or ""), first_gate_record)
            future_decision = str(gate_record.get("future_execution_gate_decision") or "")
            if active_policy.require_future_execution_gate_ready and future_decision not in READY_FUTURE_EXECUTION_GATE_DECISIONS:
                return _blocked("future_execution_gate_not_ready", [LiveCommitExecutionPacketFinding("error", "future_execution_gate_not_ready", "future execution gate decision is not ready/noop", candidate.candidate_id, candidate.record_id)])
            for label, digest_field, decision_field, record_digest_field, record_decision_field in UPSTREAM_CHECKS:
                expected_digest = gate_digest if record_digest_field == "__packet_digest__" else str(gate_record.get(record_digest_field) or "")
                expected_decision = str(gate_record.get(record_decision_field) or "")
                if str(raw.get(digest_field) or "") != expected_digest:
                    return _blocked(f"{label}_digest_mismatch", [LiveCommitExecutionPacketFinding("error", f"{label}_digest_mismatch", f"{label} digest does not match", candidate.candidate_id, candidate.record_id)])
                if str(raw.get(decision_field) or "") != expected_decision:
                    return _blocked(f"{label}_decision_mismatch", [LiveCommitExecutionPacketFinding("error", f"{label}_decision_mismatch", f"{label} decision does not match", candidate.candidate_id, candidate.record_id)])
            if not candidate.is_noop(future_decision):
                for field in NON_NOOP_METADATA_FIELDS:
                    if not _as_mapping(raw.get(field)):
                        return _blocked(f"missing_{field}", [LiveCommitExecutionPacketFinding("error", f"missing_{field}", f"required non-noop metadata field {field} is missing", candidate.candidate_id, candidate.record_id)])
            forbidden = _forbidden_claim_finding(candidate, active_policy)
            if forbidden is not None:
                return _blocked(forbidden.code, [forbidden])
            if active_policy.block_raw_payload_leakage and any(re.search(r"(^raw_|_payload$|secret|private|media)", str(key)) for key in raw.keys()):
                return _blocked("raw_payload_leakage", [LiveCommitExecutionPacketFinding("error", "raw_payload_leakage", "candidate includes raw/private/media/secret payload material", candidate.candidate_id, candidate.record_id)])
            if not _scope_ok(candidate, gate_record, active_policy):
                return _blocked("scope_mismatch", [LiveCommitExecutionPacketFinding("error", "scope_mismatch", "candidate scope does not align with upstream evidence", candidate.candidate_id, candidate.record_id)])
            if candidate.candidate_type == "mixed_live_commit_execution_packet_candidate" and candidate.metadata.get("diagnostic_warning") is True:
                findings.append(LiveCommitExecutionPacketFinding("warning", "mixed_scope_diagnostic", "mixed diagnostic metadata accepted as warning", candidate.candidate_id, candidate.record_id))
            warning = bool(candidate.metadata.get("warning_only") or candidate.metadata.get("diagnostic_warning")) or future_decision.endswith("with_warnings") or any(f.severity == "warning" and f.candidate_id == candidate.candidate_id for f in findings)
            if warning:
                findings.append(LiveCommitExecutionPacketFinding("warning", "live_commit_execution_packet_warning", "candidate is warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
            decision = _decision_for(candidate, future_decision, warning)
            records.append(
                LiveCommitExecutionPacketRecord(
                    candidate.candidate_id,
                    candidate.record_id,
                    candidate.candidate_type,
                    decision,
                    gate_digest,
                    future_decision,
                    str(gate_record.get("constrained_enablement_path_packet_digest") or ""),
                    str(gate_record.get("constrained_enablement_path_decision") or ""),
                    str(gate_record.get("executor_enablement_gate_digest") or ""),
                    str(gate_record.get("executor_enablement_gate_decision") or ""),
                    str(gate_record.get("executor_skeleton_digest") or ""),
                    str(gate_record.get("executor_skeleton_decision") or ""),
                    str(gate_record.get("invocation_harness_digest") or ""),
                    str(gate_record.get("invocation_harness_decision") or ""),
                    str(gate_record.get("activation_record_digest") or ""),
                    str(gate_record.get("activation_record_decision") or ""),
                    str(gate_record.get("preflight_packet_digest") or ""),
                    str(gate_record.get("preflight_packet_decision") or ""),
                    str(gate_record.get("lock_lease_gate_digest") or ""),
                    str(gate_record.get("lock_lease_gate_decision") or ""),
                    str(gate_record.get("executor_plan_packet_digest") or ""),
                    str(gate_record.get("executor_plan_decision") or ""),
                    str(gate_record.get("runtime_execution_gate_digest") or ""),
                    str(gate_record.get("runtime_execution_gate_decision") or ""),
                    str(gate_record.get("readiness_envelope_digest") or ""),
                    str(gate_record.get("readiness_envelope_decision") or ""),
                    str(gate_record.get("final_review_digest") or ""),
                    str(gate_record.get("final_review_decision") or ""),
                    str(gate_record.get("real_root_admission_digest") or ""),
                    str(gate_record.get("real_root_admission_decision") or ""),
                    str(gate_record.get("sandbox_commit_digest") or ""),
                    str(gate_record.get("sandbox_commit_decision") or ""),
                    candidate.operator_scope_keys,
                    (_metadata_record("packet_readiness", candidate, _as_mapping(raw.get("future_execution_readiness_metadata"))),),
                    (_metadata_record("operation_bundle", candidate, _as_mapping(raw.get("operation_bundle_metadata"))),),
                    (_metadata_record("execution_precondition", candidate, _as_mapping(raw.get("execution_precondition_metadata"))),),
                    (_metadata_record("emergency_stop_confirmation", candidate, _as_mapping(raw.get("emergency_stop_confirmation_metadata"))),),
                    (_metadata_record("operator_execution_acknowledgement", candidate, _as_mapping(raw.get("operator_execution_acknowledgement_metadata"))),),
                    (_metadata_record("receipt_envelope_readiness", candidate, _as_mapping(raw.get("receipt_envelope_readiness_metadata"))),),
                    (_metadata_record("rollback_readiness", candidate, _as_mapping(raw.get("rollback_envelope_readiness_metadata") or raw.get("rollback_readiness_metadata"))),),
                    (_metadata_record("verification_readiness", candidate, _as_mapping(raw.get("verification_envelope_readiness_metadata"))),),
                    (_metadata_record("audit_readiness", candidate, _as_mapping(raw.get("audit_envelope_readiness_metadata") or raw.get("audit_readiness_metadata"))),),
                    _safe_actions(decision),
                ).with_digest()
            )
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for finding in findings if finding.severity == "warning")}
        for record in records:
            counts[record.live_commit_execution_packet_decision] = counts.get(record.live_commit_execution_packet_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {record.live_commit_execution_packet_decision for record in records}
        if counts["warning_count"] or "live_commit_execution_packet_ready_with_warnings" in decisions:
            status: LiveCommitExecutionPacketStatus = "live_commit_execution_packet_ready_with_warnings"
        elif decisions <= {"live_commit_execution_packet_noop"}:
            status = "live_commit_execution_packet_noop"
        elif decisions <= {"live_commit_execution_packet_deferred_for_operator_review"}:
            status = "live_commit_execution_packet_deferred_for_operator_review"
        else:
            status = "live_commit_execution_packet_ready"
        packet = LiveCommitExecutionPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = LiveCommitExecutionPacketReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return LiveCommitExecutionPacketResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("failed", [LiveCommitExecutionPacketFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: LiveCommitExecutionPacketPolicy | None = None) -> LiveCommitExecutionPacketResult:
    return evaluate_live_commit_execution_packet(payload, policy)


__all__ = [
    "FAIL_STATUSES", "FORBIDDEN_NEXT_STEPS", "INVARIANTS", "LIVE_COMMIT_EXECUTION_PACKET_CANDIDATE_TYPES",
    "NON_NOOP_METADATA_FIELDS", "READY_FUTURE_EXECUTION_GATE_DECISIONS", "LiveCommitExecutionPacketCandidate",
    "LiveCommitExecutionPacketFinding", "LiveCommitExecutionPacket", "LiveCommitExecutionPacketPolicy",
    "LiveCommitExecutionPacketRecord", "LiveCommitExecutionPacketReport", "LiveCommitExecutionPacketResult",
    "build_default_policy", "validate_policy", "evaluate_live_commit_execution_packet", "evaluate_packet",
]
