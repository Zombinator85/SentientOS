"""Metadata-only real executor runtime enablement packet builder.

This module evaluates supplied Live Commit Execution Packet evidence plus
explicit runtime-enable candidates. It produces deterministic review metadata for
a later real executor runtime gate. It never enables an executor, flips runtime
flags, executes live commits, invokes or activates executors, acquires locks,
creates lockfiles, touches real memory roots, mutates memory, assembles prompts,
retrieves live context, executes actions, calls external services, discloses
externally, or grants authority, policy, consent, or truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Mapping, Sequence

RuntimeEnablementStatus = Literal[
    "runtime_enablement_packet_ready",
    "runtime_enablement_packet_ready_with_warnings",
    "runtime_enablement_packet_deferred_for_operator_review",
    "runtime_enablement_packet_rejected",
    "runtime_enablement_packet_blocked",
    "runtime_enablement_packet_noop",
    "runtime_enablement_packet_invalid",
    "runtime_enablement_packet_failed",
]
RuntimeEnablementDecision = Literal[
    "runtime_enablement_packet_ready_for_later_real_executor_runtime_gate",
    "runtime_enablement_packet_ready_with_warnings",
    "runtime_enablement_packet_deferred_for_operator_review",
    "runtime_enablement_packet_rejected",
    "runtime_enablement_packet_blocked",
    "runtime_enablement_packet_noop",
]

RUNTIME_ENABLEMENT_CANDIDATE_TYPES = frozenset({
    "ai_capsule_runtime_enablement_candidate",
    "human_summary_runtime_enablement_candidate",
    "dual_capsule_runtime_enablement_candidate",
    "protect_receipt_runtime_enablement_candidate",
    "merge_receipt_runtime_enablement_candidate",
    "tomb_archive_runtime_enablement_candidate",
    "tomb_deferred_runtime_enablement_candidate",
    "operator_review_runtime_enablement_candidate",
    "noop_runtime_enablement_candidate",
    "mixed_runtime_enablement_candidate",
})
READY_LIVE_COMMIT_EXECUTION_PACKET_DECISIONS = frozenset({
    "live_commit_execution_packet_ready_for_later_real_executor",
    "live_commit_execution_packet_ready_with_warnings",
    "live_commit_execution_packet_noop",
})
FAIL_STATUSES = {"runtime_enablement_packet_blocked", "runtime_enablement_packet_invalid", "runtime_enablement_packet_failed"}

EVIDENCE_MATCH_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    ("live_commit_execution_packet", "claimed_live_commit_execution_packet_digest", "digest", "claimed_live_commit_execution_packet_decision"),
    ("future_execution_gate", "claimed_future_execution_gate_digest", "future_execution_gate_digest", "claimed_future_execution_gate_decision"),
    ("constrained_enablement_path", "claimed_constrained_enablement_path_packet_digest", "constrained_enablement_path_packet_digest", "claimed_constrained_enablement_path_decision"),
    ("executor_enablement_gate", "claimed_executor_enablement_gate_digest", "executor_enablement_gate_digest", "claimed_executor_enablement_gate_decision"),
    ("executor_skeleton", "claimed_executor_skeleton_digest", "executor_skeleton_digest", "claimed_executor_skeleton_decision"),
    ("invocation_harness", "claimed_invocation_harness_digest", "invocation_harness_digest", "claimed_invocation_harness_decision"),
    ("activation_record", "claimed_activation_record_digest", "activation_record_digest", "claimed_activation_record_decision"),
    ("preflight_packet", "claimed_preflight_packet_digest", "preflight_packet_digest", "claimed_preflight_packet_decision"),
    ("lock_lease_gate", "claimed_lock_lease_gate_digest", "lock_lease_gate_digest", "claimed_lock_lease_gate_decision"),
    ("executor_plan_packet", "claimed_executor_plan_packet_digest", "executor_plan_packet_digest", "claimed_executor_plan_decision"),
    ("runtime_execution_gate", "claimed_runtime_execution_gate_digest", "runtime_execution_gate_digest", "claimed_runtime_execution_gate_decision"),
    ("readiness_envelope", "claimed_readiness_envelope_digest", "readiness_envelope_digest", "claimed_readiness_envelope_decision"),
    ("final_review", "claimed_final_review_digest", "final_review_digest", "claimed_final_review_decision"),
    ("real_root_admission", "claimed_real_root_admission_digest", "real_root_admission_digest", "claimed_real_root_admission_decision"),
    ("sandbox_commit", "claimed_sandbox_commit_digest", "sandbox_commit_digest", "claimed_sandbox_commit_decision"),
)
EVIDENCE_DECISION_RECORD_FIELDS = {
    "live_commit_execution_packet": "live_commit_execution_packet_decision",
    "future_execution_gate": "future_execution_gate_decision",
    "constrained_enablement_path": "constrained_enablement_path_decision",
    "executor_enablement_gate": "executor_enablement_gate_decision",
    "executor_skeleton": "executor_skeleton_decision",
    "invocation_harness": "invocation_harness_decision",
    "activation_record": "activation_record_decision",
    "preflight_packet": "preflight_packet_decision",
    "lock_lease_gate": "lock_lease_gate_decision",
    "executor_plan_packet": "executor_plan_decision",
    "runtime_execution_gate": "runtime_execution_gate_decision",
    "readiness_envelope": "readiness_envelope_decision",
    "final_review": "final_review_decision",
    "real_root_admission": "real_root_admission_decision",
    "sandbox_commit": "sandbox_commit_decision",
}

NON_NOOP_METADATA_FIELDS = (
    "packet_readiness_metadata", "operation_bundle_digest_metadata", "execution_precondition_metadata",
    "emergency_stop_confirmation_metadata", "operator_execution_acknowledgement_metadata",
    "receipt_envelope_readiness_metadata", "rollback_readiness_metadata", "verification_readiness_metadata",
    "audit_readiness_metadata", "final_execution_packet_scope_metadata", "future_real_executor_requirement_metadata",
    "future_execution_readiness_metadata", "constrained_path_confirmation_metadata", "execution_abort_condition_metadata",
    "execution_rollback_condition_metadata", "execution_verification_expectation_metadata", "execution_audit_expectation_metadata",
    "enablement_path_readiness_metadata", "staged_enablement_requirements_metadata", "constrained_enable_path_metadata",
    "enablement_precondition_metadata", "enablement_abort_condition_metadata", "enablement_rollback_condition_metadata",
    "enablement_audit_expectation_metadata", "future_live_execution_gate_metadata", "enablement_readiness_metadata",
    "disabled_posture_confirmation_metadata", "operator_enablement_acknowledgement_metadata", "enablement_scope_metadata",
    "executor_api_metadata", "disabled_execution_posture_metadata", "receipt_envelope_schema_metadata",
    "rollback_envelope_schema_metadata", "abort_envelope_schema_metadata", "verification_envelope_schema_metadata",
    "invocation_readiness_metadata", "invocation_scope_metadata", "invocation_handoff_metadata",
    "invocation_disablement_metadata", "activation_readiness_metadata", "activation_scope_metadata",
    "execution_handoff_metadata", "final_preflight_readiness_metadata", "operation_inventory_digest_metadata",
    "safety_checklist_digest_metadata", "lock_lease_readiness_metadata", "operator_identity_role_metadata",
    "operator_runtime_enable_acknowledgement_metadata", "execution_window_metadata", "idempotency_key_metadata",
    "atomicity_boundary_metadata", "dry_run_to_live_equivalence_metadata", "rollback_rehearsal_metadata",
    "post_execution_audit_metadata", "runtime_flag_precondition_metadata", "runtime_flag_target_state_metadata",
    "disabled_to_enabled_transition_metadata", "enablement_rollback_plan_metadata", "enablement_verification_plan_metadata",
    "enablement_audit_plan_metadata", "runtime_enable_hold_point_metadata", "runtime_enable_abort_condition_metadata",
)

INVARIANTS: dict[str, bool] = {
    "runtime_enablement_packet_is_not_runtime_enablement": True,
    "runtime_enablement_packet_is_not_runtime_flag_flip": True,
    "runtime_enablement_packet_is_not_live_commit_execution": True,
    "runtime_enablement_packet_is_not_enabled_executor": True,
    "runtime_enablement_packet_is_not_executor_enablement": True,
    "runtime_enablement_packet_is_not_executor_invocation": True,
    "runtime_enablement_packet_is_not_executor_activation": True,
    "runtime_enablement_packet_is_not_lock_acquisition": True,
    "runtime_enablement_packet_is_not_lockfile_creation": True,
    "runtime_enablement_packet_is_not_memory_write": True,
    "runtime_enablement_packet_is_not_memory_deletion": True,
    "runtime_enablement_packet_is_not_memory_purge": True,
    "runtime_enablement_packet_is_not_index_mutation": True,
    "runtime_enablement_packet_is_not_capsule_persistence": True,
    "runtime_enablement_packet_is_not_tomb_completion": True,
    "runtime_enablement_packet_is_not_prompt_assembly": True,
    "runtime_enablement_packet_is_not_live_context_retrieval": True,
    "runtime_enablement_packet_is_not_action_execution": True,
    "runtime_enablement_packet_is_not_external_disclosure": True,
    "runtime_enablement_packet_is_not_truth": True,
    "runtime_enablement_packet_is_not_policy": True,
    "runtime_enablement_packet_is_not_authority": True,
    "runtime_enablement_packet_is_not_consent": True,
    "runtime_enable_readiness_is_metadata_only": True,
    "disabled_to_enabled_transition_requirements_are_metadata_only": True,
    "runtime_flag_preconditions_are_metadata_only": True,
    "runtime_flag_target_state_is_metadata_only": True,
    "operator_runtime_acknowledgement_is_metadata_only": True,
    "emergency_stop_confirmation_is_metadata_only": True,
    "rollback_readiness_is_metadata_only": True,
    "verification_readiness_is_metadata_only": True,
    "audit_readiness_is_metadata_only": True,
    "real_executor_enabled": False,
    "real_executor_runtime_enablement_enabled": False,
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
    "future_real_executor_runtime_gate_required": True,
    "future_real_live_memory_commit_execution_required": True,
    "future_post_execution_audit_required": True,
}
FORBIDDEN_NEXT_STEPS = (
    "runtime_enablement", "runtime_flag_flipping", "live_execution", "executor_enablement", "executor_invocation",
    "executor_activation", "real_lock_acquisition", "lockfile_creation", "real_live_memory_write",
    "real_live_memory_delete", "real_live_memory_purge", "index_mutation", "prompt_assembly", "live_context_retrieval",
    "action_ingress", "sandbox_bypass", "real_root_admission_bypass", "final_review_bypass", "readiness_envelope_bypass",
    "runtime_gate_bypass", "executor_plan_bypass", "lock_lease_bypass", "preflight_bypass", "activation_record_bypass",
    "invocation_harness_bypass", "executor_skeleton_bypass", "enablement_gate_bypass", "constrained_path_bypass",
    "future_execution_gate_bypass", "live_commit_execution_packet_bypass", "direct_executor_execution", "external_disclosure",
)

FORBIDDEN_CLAIM_CODES = {
    "runtime_enablement_claimed": "runtime_enablement_claim",
    "runtime_flags_flipped": "runtime_flag_flipping_claim",
    "runtime_flag_target_state_active": "runtime_flag_active_state_claim",
    "executor_enabled": "executor_enablement_claim",
    "executor_invoked": "executor_invocation_claim",
    "executor_activated": "executor_activation_claim",
    "live_commit_executed": "live_execution_claim",
    "permission_to_execute_now": "executor_permission_claim",
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
    "protection_application_claimed": "protection_application_claim",
    "merge_application_claimed": "merge_application_claim",
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
class RuntimeEnablementFinding:
    severity: str
    code: str
    message: str
    candidate_id: str = ""
    record_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeEnablementPolicy:
    schema_version: str = "real-executor-runtime-enablement-packet.v1"
    default_deny: bool = True
    metadata_only: bool = True
    allow_mixed_diagnostics: bool = True
    require_scope_alignment: bool = True
    block_forbidden_claims: bool = True
    require_future_runtime_gate: bool = True
    real_executor_enabled: bool = False
    real_executor_runtime_enablement_enabled: bool = False
    real_executor_enablement_enabled: bool = False
    real_executor_invocation_enabled: bool = False
    real_executor_activation_enabled: bool = False
    real_lock_acquisition_enabled: bool = False
    lockfile_creation_enabled: bool = False
    real_memory_root_access_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeEnablementCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    operator_scope_keys: tuple[str, ...]
    metadata: Mapping[str, Any]
    claims: Mapping[str, Any]

    @staticmethod
    def from_mapping(payload: Mapping[str, Any]) -> "RuntimeEnablementCandidate":
        return RuntimeEnablementCandidate(
            candidate_id=str(payload.get("candidate_id") or ""),
            record_id=str(payload.get("record_id") or ""),
            candidate_type=str(payload.get("candidate_type") or ""),
            operator_scope_keys=tuple(str(v) for v in payload.get("operator_scope_keys", ())),
            metadata=_as_mapping(payload.get("metadata")),
            claims=_as_mapping(payload.get("runtime_enablement_claims") or payload.get("claims")),
        )

    @property
    def is_noop(self) -> bool:
        return self.candidate_type == "noop_runtime_enablement_candidate"


@dataclass(frozen=True)
class RuntimeEnablementMetadataRecord:
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
    live_receipt: bool = False
    rollback_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeEnablementRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    runtime_enablement_packet_decision: RuntimeEnablementDecision
    live_commit_execution_packet_digest: str
    live_commit_execution_packet_decision: str
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
    runtime_enable_readiness_records: tuple[RuntimeEnablementMetadataRecord, ...]
    disabled_to_enabled_transition_requirement_records: tuple[RuntimeEnablementMetadataRecord, ...]
    runtime_flag_precondition_records: tuple[RuntimeEnablementMetadataRecord, ...]
    runtime_flag_target_state_records: tuple[RuntimeEnablementMetadataRecord, ...]
    operator_runtime_acknowledgement_records: tuple[RuntimeEnablementMetadataRecord, ...]
    emergency_stop_confirmation_records: tuple[RuntimeEnablementMetadataRecord, ...]
    rollback_readiness_records: tuple[RuntimeEnablementMetadataRecord, ...]
    verification_readiness_records: tuple[RuntimeEnablementMetadataRecord, ...]
    audit_readiness_records: tuple[RuntimeEnablementMetadataRecord, ...]
    safe_next_actions: tuple[str, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    real_executor_enabled: bool = False
    real_executor_runtime_enablement_enabled: bool = False
    real_executor_enablement_enabled: bool = False
    real_executor_invocation_enabled: bool = False
    real_executor_activation_enabled: bool = False
    real_lock_acquisition_enabled: bool = False
    lockfile_created: bool = False
    runtime_flags_flipped: bool = False
    live_commit_executed: bool = False
    live_execution_permission_granted: bool = False
    runtime_flag_target_state_is_active_runtime_state: bool = False
    operator_review_cannot_override_hard_blockers: bool = True
    future_real_executor_runtime_gate_required: bool = True
    future_real_live_memory_commit_execution_required: bool = True
    future_post_execution_audit_required: bool = True
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_digest(self) -> "RuntimeEnablementRecord":
        return replace(self, digest=_digest({k: v for k, v in self.to_dict().items() if k != "digest"}))


@dataclass(frozen=True)
class RuntimeEnablementPacket:
    schema_version: str
    records: tuple[RuntimeEnablementRecord, ...]
    digest: str = ""
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    future_real_executor_runtime_gate_required: bool = True
    future_real_live_memory_commit_execution_required: bool = True
    future_post_execution_audit_required: bool = True
    runtime_enablement_packet_is_not_runtime_enablement: bool = True
    runtime_enablement_packet_is_not_runtime_flag_flip: bool = True
    real_executor_enabled: bool = False
    real_executor_runtime_enablement_enabled: bool = False
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
    prompt_materialization_enabled: bool = False
    live_context_retrieval_enabled: bool = False
    action_execution_enabled: bool = False
    external_disclosure_enabled: bool = False
    external_service_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(INVARIANTS)
        return payload

    def with_digest(self) -> "RuntimeEnablementPacket":
        return replace(self, digest=_digest({k: v for k, v in self.to_dict().items() if k != "digest"}))


@dataclass(frozen=True)
class RuntimeEnablementReport:
    status: RuntimeEnablementStatus
    findings: tuple[RuntimeEnablementFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [f.to_dict() for f in self.findings], "summary_counts": dict(self.summary_counts), "digest": self.digest}


@dataclass(frozen=True)
class RuntimeEnablementResult:
    status: RuntimeEnablementStatus
    packet: RuntimeEnablementPacket | None
    report: RuntimeEnablementReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> RuntimeEnablementPolicy:
    return RuntimeEnablementPolicy()


def validate_policy(policy: RuntimeEnablementPolicy | None = None) -> dict[str, Any]:
    active = policy or build_default_policy()
    findings: list[RuntimeEnablementFinding] = []
    if not active.default_deny or not active.metadata_only:
        findings.append(RuntimeEnablementFinding("error", "policy_not_metadata_only_default_deny", "policy must remain metadata-only and default-deny"))
    for name in ("real_executor_enabled", "real_executor_runtime_enablement_enabled", "real_executor_enablement_enabled", "real_executor_invocation_enabled", "real_executor_activation_enabled", "real_lock_acquisition_enabled", "lockfile_creation_enabled", "real_memory_root_access_enabled"):
        if bool(getattr(active, name)):
            findings.append(RuntimeEnablementFinding("error", name, f"{name} must remain false"))
    return {"status": "valid" if not findings else "invalid", "policy": active.to_dict(), "findings": [f.to_dict() for f in findings]}


def _blocked(code: str, findings: Sequence[RuntimeEnablementFinding] = ()) -> RuntimeEnablementResult:
    all_findings = tuple(findings) or (RuntimeEnablementFinding("error", code, code),)
    report = RuntimeEnablementReport("runtime_enablement_packet_blocked", all_findings, {"blocked": 1})
    report = replace(report, digest=_digest(report.to_dict()))
    return RuntimeEnablementResult("runtime_enablement_packet_blocked", None, report, _digest(report.to_dict()))


def _metadata_record(kind: str, candidate: RuntimeEnablementCandidate, metadata: Mapping[str, Any]) -> RuntimeEnablementMetadataRecord:
    return RuntimeEnablementMetadataRecord(kind, candidate.candidate_id, candidate.record_id, _digest(dict(metadata)))


def _valid_candidate(candidate: RuntimeEnablementCandidate) -> bool:
    return bool(_ID_RE.match(candidate.candidate_id)) and bool(_ID_RE.match(candidate.record_id)) and candidate.candidate_type in RUNTIME_ENABLEMENT_CANDIDATE_TYPES


def _claims_findings(candidate: RuntimeEnablementCandidate) -> tuple[RuntimeEnablementFinding, ...]:
    findings: list[RuntimeEnablementFinding] = []
    for key, code in FORBIDDEN_CLAIM_CODES.items():
        if candidate.claims.get(key) is True:
            findings.append(RuntimeEnablementFinding("error", code, f"forbidden runtime enablement claim blocked: {key}", candidate.candidate_id, candidate.record_id))
    return tuple(findings)


def _live_packet_and_record(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]] | RuntimeEnablementResult:
    packet = _as_mapping(payload.get("live_commit_execution_packet"))
    if not packet:
        return _blocked("missing_live_commit_execution_packet")
    records = packet.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records:
        return _blocked("invalid_live_commit_execution_packet")
    record = _as_mapping(records[0])
    if not str(packet.get("digest") or "") or not str(record.get("digest") or ""):
        return _blocked("invalid_live_commit_execution_packet")
    return packet, record


def _candidate_list(payload: Mapping[str, Any]) -> Sequence[Any] | RuntimeEnablementResult:
    candidates = payload.get("runtime_enablement_candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)) or not candidates:
        return _blocked("missing_runtime_enablement_candidate")
    return candidates


def _check_required_metadata(raw: Mapping[str, Any], candidate: RuntimeEnablementCandidate) -> RuntimeEnablementResult | None:
    if candidate.is_noop:
        return None
    for field in NON_NOOP_METADATA_FIELDS:
        if not isinstance(raw.get(field), Mapping) or not raw.get(field):
            return _blocked(f"missing_{field}", [RuntimeEnablementFinding("error", f"missing_{field}", f"missing required non-noop metadata: {field}", candidate.candidate_id, candidate.record_id)])
    return None


def _check_evidence(raw: Mapping[str, Any], packet: Mapping[str, Any], record: Mapping[str, Any], candidate: RuntimeEnablementCandidate) -> RuntimeEnablementResult | None:
    decision = str(record.get("live_commit_execution_packet_decision") or "")
    if decision not in READY_LIVE_COMMIT_EXECUTION_PACKET_DECISIONS:
        return _blocked("live_commit_execution_packet_not_ready", [RuntimeEnablementFinding("error", "live_commit_execution_packet_not_ready", "live commit execution packet is not ready by default", candidate.candidate_id, candidate.record_id)])
    for label, candidate_digest_field, record_digest_field, candidate_decision_field in EVIDENCE_MATCH_FIELDS:
        actual_digest = str(packet.get("digest") if label == "live_commit_execution_packet" else record.get(record_digest_field) or "")
        actual_decision = str(record.get(EVIDENCE_DECISION_RECORD_FIELDS[label]) or "")
        if str(raw.get(candidate_digest_field) or "") != actual_digest:
            return _blocked(f"{label}_digest_mismatch", [RuntimeEnablementFinding("error", f"{label}_digest_mismatch", f"{label} digest mismatch", candidate.candidate_id, candidate.record_id)])
        if str(raw.get(candidate_decision_field) or "") != actual_decision:
            return _blocked(f"{label}_decision_mismatch", [RuntimeEnablementFinding("error", f"{label}_decision_mismatch", f"{label} decision mismatch", candidate.candidate_id, candidate.record_id)])
    if tuple(str(v) for v in record.get("operator_scope_keys", ())) != candidate.operator_scope_keys and candidate.candidate_type != "mixed_runtime_enablement_candidate":
        return _blocked("scope_mismatch", [RuntimeEnablementFinding("error", "scope_mismatch", "runtime enablement candidate scope does not match live commit execution packet scope", candidate.candidate_id, candidate.record_id)])
    return None


def _decision(candidate: RuntimeEnablementCandidate, findings: Sequence[RuntimeEnablementFinding]) -> RuntimeEnablementDecision:
    if candidate.is_noop:
        return "runtime_enablement_packet_noop"
    if candidate.candidate_type == "operator_review_runtime_enablement_candidate":
        return "runtime_enablement_packet_deferred_for_operator_review"
    if candidate.candidate_type == "mixed_runtime_enablement_candidate" or any(f.severity == "warning" for f in findings):
        return "runtime_enablement_packet_ready_with_warnings"
    return "runtime_enablement_packet_ready_for_later_real_executor_runtime_gate"


def _safe_actions(decision: RuntimeEnablementDecision) -> tuple[str, ...]:
    if decision == "runtime_enablement_packet_noop":
        return ("record_noop_metadata",)
    if decision == "runtime_enablement_packet_deferred_for_operator_review":
        return ("operator_review_metadata", "keep_executor_disabled")
    if decision == "runtime_enablement_packet_ready_with_warnings":
        return ("review_runtime_enablement_warnings", "prepare_future_real_executor_runtime_gate_later")
    return ("review_runtime_enablement_packet", "prepare_future_real_executor_runtime_gate_later", "run_future_post_execution_audit_later")


def evaluate_real_executor_runtime_enablement_packet(payload: Mapping[str, Any], policy: RuntimeEnablementPolicy | None = None) -> RuntimeEnablementResult:
    active_policy = policy or build_default_policy()
    validation = validate_policy(active_policy)
    if validation["status"] != "valid":
        return _blocked("invalid_policy", [RuntimeEnablementFinding("error", "invalid_policy", "runtime enablement policy is invalid")])
    try:
        live = _live_packet_and_record(payload)
        if isinstance(live, RuntimeEnablementResult):
            return live
        live_packet, live_record = live
        candidates_obj = _candidate_list(payload)
        if isinstance(candidates_obj, RuntimeEnablementResult):
            return candidates_obj
        findings: list[RuntimeEnablementFinding] = []
        records: list[RuntimeEnablementRecord] = []
        for item in candidates_obj:
            raw = _as_mapping(item)
            candidate = RuntimeEnablementCandidate.from_mapping(raw)
            if not _valid_candidate(candidate):
                return _blocked("invalid_runtime_enablement_candidate", [RuntimeEnablementFinding("error", "invalid_runtime_enablement_candidate", "runtime enablement candidate type/id is invalid", candidate.candidate_id, candidate.record_id)])
            claim_findings = _claims_findings(candidate)
            if claim_findings:
                return _blocked(claim_findings[0].code, claim_findings)
            missing = _check_required_metadata(raw, candidate)
            if missing is not None:
                return missing
            evidence = _check_evidence(raw, live_packet, live_record, candidate)
            if evidence is not None:
                return evidence
            if candidate.candidate_type == "mixed_runtime_enablement_candidate" and candidate.metadata.get("diagnostic_warning") is True:
                findings.append(RuntimeEnablementFinding("warning", "mixed_scope_diagnostic", "mixed runtime enablement diagnostics allowed as warnings only", candidate.candidate_id, candidate.record_id))
            decision = _decision(candidate, findings)
            records.append(RuntimeEnablementRecord(
                candidate.candidate_id, candidate.record_id, candidate.candidate_type, decision,
                str(live_packet.get("digest") or ""), str(live_record.get("live_commit_execution_packet_decision") or ""),
                str(live_record.get("future_execution_gate_digest") or ""), str(live_record.get("future_execution_gate_decision") or ""),
                str(live_record.get("constrained_enablement_path_packet_digest") or ""), str(live_record.get("constrained_enablement_path_decision") or ""),
                str(live_record.get("executor_enablement_gate_digest") or ""), str(live_record.get("executor_enablement_gate_decision") or ""),
                str(live_record.get("executor_skeleton_digest") or ""), str(live_record.get("executor_skeleton_decision") or ""),
                str(live_record.get("invocation_harness_digest") or ""), str(live_record.get("invocation_harness_decision") or ""),
                str(live_record.get("activation_record_digest") or ""), str(live_record.get("activation_record_decision") or ""),
                str(live_record.get("preflight_packet_digest") or ""), str(live_record.get("preflight_packet_decision") or ""),
                str(live_record.get("lock_lease_gate_digest") or ""), str(live_record.get("lock_lease_gate_decision") or ""),
                str(live_record.get("executor_plan_packet_digest") or ""), str(live_record.get("executor_plan_decision") or ""),
                str(live_record.get("runtime_execution_gate_digest") or ""), str(live_record.get("runtime_execution_gate_decision") or ""),
                str(live_record.get("readiness_envelope_digest") or ""), str(live_record.get("readiness_envelope_decision") or ""),
                str(live_record.get("final_review_digest") or ""), str(live_record.get("final_review_decision") or ""),
                str(live_record.get("real_root_admission_digest") or ""), str(live_record.get("real_root_admission_decision") or ""),
                str(live_record.get("sandbox_commit_digest") or ""), str(live_record.get("sandbox_commit_decision") or ""),
                candidate.operator_scope_keys,
                (_metadata_record("runtime_enable_readiness", candidate, _as_mapping(raw.get("enablement_readiness_metadata") or raw.get("runtime_enable_readiness_metadata"))),),
                (_metadata_record("disabled_to_enabled_transition_requirements", candidate, _as_mapping(raw.get("disabled_to_enabled_transition_metadata"))),),
                (_metadata_record("runtime_flag_precondition", candidate, _as_mapping(raw.get("runtime_flag_precondition_metadata"))),),
                (_metadata_record("runtime_flag_target_state", candidate, _as_mapping(raw.get("runtime_flag_target_state_metadata"))),),
                (_metadata_record("operator_runtime_acknowledgement", candidate, _as_mapping(raw.get("operator_runtime_enable_acknowledgement_metadata"))),),
                (_metadata_record("emergency_stop_confirmation", candidate, _as_mapping(raw.get("emergency_stop_confirmation_metadata"))),),
                (_metadata_record("rollback_readiness", candidate, _as_mapping(raw.get("rollback_readiness_metadata"))),),
                (_metadata_record("verification_readiness", candidate, _as_mapping(raw.get("verification_readiness_metadata"))),),
                (_metadata_record("audit_readiness", candidate, _as_mapping(raw.get("audit_readiness_metadata"))),),
                _safe_actions(decision),
            ).with_digest())
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for f in findings if f.severity == "warning")}
        for record in records:
            counts[record.runtime_enablement_packet_decision] = counts.get(record.runtime_enablement_packet_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {r.runtime_enablement_packet_decision for r in records}
        if counts["warning_count"] or "runtime_enablement_packet_ready_with_warnings" in decisions:
            status: RuntimeEnablementStatus = "runtime_enablement_packet_ready_with_warnings"
        elif decisions <= {"runtime_enablement_packet_noop"}:
            status = "runtime_enablement_packet_noop"
        elif decisions <= {"runtime_enablement_packet_deferred_for_operator_review"}:
            status = "runtime_enablement_packet_deferred_for_operator_review"
        else:
            status = "runtime_enablement_packet_ready"
        packet = RuntimeEnablementPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = RuntimeEnablementReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return RuntimeEnablementResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("failed", [RuntimeEnablementFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: RuntimeEnablementPolicy | None = None) -> RuntimeEnablementResult:
    return evaluate_real_executor_runtime_enablement_packet(payload, policy)


__all__ = [
    "EVIDENCE_MATCH_FIELDS", "FAIL_STATUSES", "FORBIDDEN_NEXT_STEPS", "INVARIANTS", "NON_NOOP_METADATA_FIELDS",
    "READY_LIVE_COMMIT_EXECUTION_PACKET_DECISIONS", "RUNTIME_ENABLEMENT_CANDIDATE_TYPES",
    "RuntimeEnablementCandidate", "RuntimeEnablementFinding", "RuntimeEnablementMetadataRecord", "RuntimeEnablementPacket",
    "RuntimeEnablementPolicy", "RuntimeEnablementRecord", "RuntimeEnablementReport", "RuntimeEnablementResult",
    "build_default_policy", "evaluate_packet", "evaluate_real_executor_runtime_enablement_packet", "validate_policy",
]
