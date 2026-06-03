"""Metadata-only real executor runtime gate builder.

The gate consumes supplied Real Executor Runtime Enablement Packet evidence and
explicit runtime-gate candidates.  It emits deterministic metadata records that
can be reviewed before a later guarded real executor path is even considered.
It never enables an executor, flips runtime flags, executes live commits,
invokes or activates executors, acquires locks, creates lockfiles, touches real
memory roots, mutates memory, assembles prompts, retrieves live context,
executes actions, calls external services, discloses externally, or grants
authority, policy, consent, or truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Mapping, Sequence

RuntimeGateStatus = Literal[
    "runtime_gate_ready",
    "runtime_gate_ready_with_warnings",
    "runtime_gate_deferred_for_operator_review",
    "runtime_gate_rejected",
    "runtime_gate_blocked",
    "runtime_gate_noop",
    "runtime_gate_invalid",
    "runtime_gate_failed",
]
RuntimeGateDecision = Literal[
    "runtime_gate_ready_for_later_guarded_executor_path",
    "runtime_gate_ready_with_warnings",
    "runtime_gate_deferred_for_operator_review",
    "runtime_gate_rejected",
    "runtime_gate_blocked",
    "runtime_gate_noop",
]

RUNTIME_GATE_CANDIDATE_TYPES = frozenset({
    "ai_capsule_runtime_gate_candidate",
    "human_summary_runtime_gate_candidate",
    "dual_capsule_runtime_gate_candidate",
    "protect_receipt_runtime_gate_candidate",
    "merge_receipt_runtime_gate_candidate",
    "tomb_archive_runtime_gate_candidate",
    "tomb_deferred_runtime_gate_candidate",
    "operator_review_runtime_gate_candidate",
    "noop_runtime_gate_candidate",
    "mixed_runtime_gate_candidate",
})
READY_RUNTIME_ENABLEMENT_PACKET_DECISIONS = frozenset({
    "runtime_enablement_packet_ready_for_later_real_executor_runtime_gate",
    "runtime_enablement_packet_ready_with_warnings",
    "runtime_enablement_packet_noop",
})
FAIL_STATUSES = {"runtime_gate_blocked", "runtime_gate_invalid", "runtime_gate_failed"}

EVIDENCE_MATCH_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    ("runtime_enablement_packet", "claimed_runtime_enablement_packet_digest", "digest", "claimed_runtime_enablement_packet_decision"),
    ("live_commit_execution_packet", "claimed_live_commit_execution_packet_digest", "live_commit_execution_packet_digest", "claimed_live_commit_execution_packet_decision"),
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
    "runtime_enablement_packet": "runtime_enablement_packet_decision",
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
    "runtime_enable_readiness_metadata", "disabled_to_enabled_transition_metadata",
    "runtime_flag_precondition_metadata", "runtime_flag_target_state_metadata",
    "operator_runtime_acknowledgement_metadata", "emergency_stop_confirmation_metadata",
    "rollback_readiness_metadata", "verification_readiness_metadata", "audit_readiness_metadata",
    "runtime_enable_hold_point_metadata", "runtime_enable_abort_condition_metadata",
    "enablement_rollback_plan_metadata", "enablement_verification_plan_metadata", "enablement_audit_plan_metadata",
    "packet_readiness_metadata", "operation_bundle_digest_metadata", "execution_precondition_metadata",
    "operator_execution_acknowledgement_metadata", "receipt_envelope_readiness_metadata",
    "final_execution_packet_scope_metadata", "future_real_executor_requirement_metadata",
    "future_execution_readiness_metadata", "constrained_path_confirmation_metadata",
    "execution_abort_condition_metadata", "execution_rollback_condition_metadata",
    "execution_verification_expectation_metadata", "execution_audit_expectation_metadata",
    "enablement_path_readiness_metadata", "staged_enablement_requirements_metadata",
    "constrained_enable_path_metadata", "enablement_precondition_metadata",
    "enablement_abort_condition_metadata", "enablement_rollback_condition_metadata",
    "enablement_audit_expectation_metadata", "future_live_execution_gate_metadata",
    "enablement_readiness_metadata", "disabled_posture_confirmation_metadata",
    "operator_enablement_acknowledgement_metadata", "enablement_scope_metadata",
    "executor_api_metadata", "disabled_execution_posture_metadata", "receipt_envelope_schema_metadata",
    "rollback_envelope_schema_metadata", "abort_envelope_schema_metadata", "verification_envelope_schema_metadata",
    "invocation_readiness_metadata", "invocation_scope_metadata", "invocation_handoff_metadata",
    "invocation_disablement_metadata", "activation_readiness_metadata", "activation_scope_metadata",
    "execution_handoff_metadata", "final_preflight_readiness_metadata",
    "operation_inventory_digest_metadata", "safety_checklist_digest_metadata",
    "lock_lease_readiness_metadata", "operator_identity_role_metadata", "execution_window_metadata",
    "idempotency_key_metadata", "atomicity_boundary_metadata", "dry_run_to_live_equivalence_metadata",
    "rollback_rehearsal_metadata", "post_execution_audit_metadata",
    "guarded_executor_path_prerequisite_metadata", "runtime_guard_hold_point_metadata",
    "runtime_guard_abort_condition_metadata", "runtime_guard_verification_expectation_metadata",
    "runtime_guard_audit_expectation_metadata",
)

INVARIANTS: dict[str, bool] = {
    "runtime_gate_is_not_runtime_enablement": True,
    "runtime_gate_is_not_runtime_flag_flip": True,
    "runtime_gate_is_not_live_commit_execution": True,
    "runtime_gate_is_not_enabled_executor": True,
    "runtime_gate_is_not_executor_enablement": True,
    "runtime_gate_is_not_executor_invocation": True,
    "runtime_gate_is_not_executor_activation": True,
    "runtime_gate_is_not_lock_acquisition": True,
    "runtime_gate_is_not_lockfile_creation": True,
    "runtime_gate_is_not_memory_write": True,
    "runtime_gate_is_not_memory_deletion": True,
    "runtime_gate_is_not_memory_purge": True,
    "runtime_gate_is_not_index_mutation": True,
    "runtime_gate_is_not_capsule_persistence": True,
    "runtime_gate_is_not_tomb_completion": True,
    "runtime_gate_is_not_prompt_assembly": True,
    "runtime_gate_is_not_live_context_retrieval": True,
    "runtime_gate_is_not_action_execution": True,
    "runtime_gate_is_not_external_disclosure": True,
    "runtime_gate_is_not_truth": True,
    "runtime_gate_is_not_policy": True,
    "runtime_gate_is_not_authority": True,
    "runtime_gate_is_not_consent": True,
    "runtime_gate_readiness_is_metadata_only": True,
    "runtime_enable_confirmation_is_metadata_only": True,
    "runtime_flag_confirmation_is_metadata_only": True,
    "guarded_executor_path_prerequisites_are_metadata_only": True,
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
    "future_guarded_executor_path_required": True,
    "future_real_live_memory_commit_execution_required": True,
    "future_post_execution_audit_required": True,
}
FORBIDDEN_NEXT_STEPS = (
    "runtime_enablement", "runtime_flag_flipping", "guarded_executor_invocation", "live_execution",
    "executor_enablement", "executor_invocation", "executor_activation", "real_lock_acquisition",
    "lockfile_creation", "real_live_memory_write", "real_live_memory_delete", "real_live_memory_purge",
    "index_mutation", "prompt_assembly", "live_context_retrieval", "action_ingress", "sandbox_bypass",
    "real_root_admission_bypass", "final_review_bypass", "readiness_envelope_bypass", "runtime_gate_bypass",
    "executor_plan_bypass", "lock_lease_bypass", "preflight_bypass", "activation_record_bypass",
    "invocation_harness_bypass", "executor_skeleton_bypass", "enablement_gate_bypass",
    "constrained_path_bypass", "future_execution_gate_bypass", "live_commit_execution_packet_bypass",
    "runtime_enablement_packet_bypass", "direct_executor_execution", "external_disclosure",
)
FORBIDDEN_CLAIM_CODES = {
    "runtime_enablement_claimed": "runtime_enablement_claim",
    "runtime_flags_flipped": "runtime_flag_flipping_claim",
    "runtime_flag_target_state_active": "runtime_flag_active_state_claim",
    "guarded_executor_path_invoked": "guarded_executor_invocation_claim",
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
class RuntimeGateFinding:
    severity: str
    code: str
    message: str
    candidate_id: str = ""
    record_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeGatePolicy:
    schema_version: str = "real-executor-runtime-gate.v1"
    default_deny: bool = True
    metadata_only: bool = True
    allow_mixed_diagnostics: bool = True
    require_scope_alignment: bool = True
    block_forbidden_claims: bool = True
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
class RuntimeGateCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    operator_scope_keys: tuple[str, ...]
    metadata: Mapping[str, Any]
    claims: Mapping[str, Any]

    @staticmethod
    def from_mapping(payload: Mapping[str, Any]) -> "RuntimeGateCandidate":
        return RuntimeGateCandidate(
            candidate_id=str(payload.get("candidate_id") or ""),
            record_id=str(payload.get("record_id") or ""),
            candidate_type=str(payload.get("candidate_type") or ""),
            operator_scope_keys=tuple(str(v) for v in payload.get("operator_scope_keys", ())),
            metadata=_as_mapping(payload.get("metadata")),
            claims=_as_mapping(payload.get("runtime_gate_claims") or payload.get("claims")),
        )

    @property
    def is_noop(self) -> bool:
        return self.candidate_type == "noop_runtime_gate_candidate"


@dataclass(frozen=True)
class RuntimeGateMetadataRecord:
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
class RuntimeGateRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    runtime_gate_decision: RuntimeGateDecision
    runtime_enablement_packet_digest: str
    runtime_enablement_packet_decision: str
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
    runtime_gate_readiness_records: tuple[RuntimeGateMetadataRecord, ...]
    runtime_enable_confirmation_records: tuple[RuntimeGateMetadataRecord, ...]
    runtime_flag_confirmation_records: tuple[RuntimeGateMetadataRecord, ...]
    guarded_executor_path_prerequisite_records: tuple[RuntimeGateMetadataRecord, ...]
    emergency_stop_confirmation_records: tuple[RuntimeGateMetadataRecord, ...]
    rollback_readiness_records: tuple[RuntimeGateMetadataRecord, ...]
    verification_readiness_records: tuple[RuntimeGateMetadataRecord, ...]
    audit_readiness_records: tuple[RuntimeGateMetadataRecord, ...]
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
    guarded_executor_path_prerequisites_are_executor_invocation: bool = False
    operator_review_cannot_override_hard_blockers: bool = True
    future_guarded_executor_path_required: bool = True
    future_real_live_memory_commit_execution_required: bool = True
    future_post_execution_audit_required: bool = True
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_digest(self) -> "RuntimeGateRecord":
        return replace(self, digest=_digest({k: v for k, v in self.to_dict().items() if k != "digest"}))


@dataclass(frozen=True)
class RuntimeGatePacket:
    schema_version: str
    records: tuple[RuntimeGateRecord, ...]
    digest: str = ""
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(INVARIANTS)
        return payload

    def with_digest(self) -> "RuntimeGatePacket":
        return replace(self, digest=_digest({k: v for k, v in self.to_dict().items() if k != "digest"}))


@dataclass(frozen=True)
class RuntimeGateReport:
    status: RuntimeGateStatus
    findings: tuple[RuntimeGateFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [f.to_dict() for f in self.findings], "summary_counts": dict(self.summary_counts), "digest": self.digest}


@dataclass(frozen=True)
class RuntimeGateResult:
    status: RuntimeGateStatus
    packet: RuntimeGatePacket | None
    report: RuntimeGateReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> RuntimeGatePolicy:
    return RuntimeGatePolicy()


def validate_policy(policy: RuntimeGatePolicy | None = None) -> dict[str, Any]:
    active = policy or build_default_policy()
    findings: list[RuntimeGateFinding] = []
    if not active.default_deny or not active.metadata_only:
        findings.append(RuntimeGateFinding("error", "policy_not_metadata_only_default_deny", "policy must remain metadata-only and default-deny"))
    for name in ("real_executor_enabled", "real_executor_runtime_enablement_enabled", "real_executor_enablement_enabled", "real_executor_invocation_enabled", "real_executor_activation_enabled", "real_lock_acquisition_enabled", "lockfile_creation_enabled", "real_memory_root_access_enabled"):
        if bool(getattr(active, name)):
            findings.append(RuntimeGateFinding("error", name, f"{name} must remain false"))
    return {"status": "valid" if not findings else "invalid", "policy": active.to_dict(), "findings": [f.to_dict() for f in findings]}


def _blocked(code: str, findings: Sequence[RuntimeGateFinding] = ()) -> RuntimeGateResult:
    all_findings = tuple(findings) or (RuntimeGateFinding("error", code, code),)
    report = RuntimeGateReport("runtime_gate_blocked", all_findings, {"blocked": 1})
    report = replace(report, digest=_digest(report.to_dict()))
    return RuntimeGateResult("runtime_gate_blocked", None, report, _digest(report.to_dict()))


def _metadata_record(kind: str, candidate: RuntimeGateCandidate, metadata: Mapping[str, Any]) -> RuntimeGateMetadataRecord:
    return RuntimeGateMetadataRecord(kind, candidate.candidate_id, candidate.record_id, _digest(dict(metadata)))


def _valid_candidate(candidate: RuntimeGateCandidate) -> bool:
    return bool(_ID_RE.match(candidate.candidate_id)) and bool(_ID_RE.match(candidate.record_id)) and candidate.candidate_type in RUNTIME_GATE_CANDIDATE_TYPES


def _claims_findings(candidate: RuntimeGateCandidate) -> tuple[RuntimeGateFinding, ...]:
    findings: list[RuntimeGateFinding] = []
    for key, code in FORBIDDEN_CLAIM_CODES.items():
        if candidate.claims.get(key) is True:
            findings.append(RuntimeGateFinding("error", code, f"forbidden runtime gate claim blocked: {key}", candidate.candidate_id, candidate.record_id))
    return tuple(findings)


def _runtime_enablement_packet_and_record(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]] | RuntimeGateResult:
    packet = _as_mapping(payload.get("runtime_enablement_packet"))
    if not packet:
        return _blocked("missing_runtime_enablement_packet")
    records = packet.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records:
        return _blocked("invalid_runtime_enablement_packet")
    record = _as_mapping(records[0])
    if not str(packet.get("digest") or "") or not str(record.get("digest") or ""):
        return _blocked("invalid_runtime_enablement_packet")
    return packet, record


def _candidate_list(payload: Mapping[str, Any]) -> Sequence[Any] | RuntimeGateResult:
    candidates = payload.get("runtime_gate_candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)) or not candidates:
        return _blocked("missing_runtime_gate_candidate")
    return candidates


def _check_required_metadata(raw: Mapping[str, Any], candidate: RuntimeGateCandidate) -> RuntimeGateResult | None:
    if candidate.is_noop:
        return None
    for field in NON_NOOP_METADATA_FIELDS:
        if not isinstance(raw.get(field), Mapping) or not raw.get(field):
            return _blocked(f"missing_{field}", [RuntimeGateFinding("error", f"missing_{field}", f"missing required non-noop metadata: {field}", candidate.candidate_id, candidate.record_id)])
    return None


def _check_evidence(raw: Mapping[str, Any], packet: Mapping[str, Any], record: Mapping[str, Any], candidate: RuntimeGateCandidate) -> RuntimeGateResult | None:
    decision = str(record.get("runtime_enablement_packet_decision") or "")
    if decision not in READY_RUNTIME_ENABLEMENT_PACKET_DECISIONS:
        return _blocked("runtime_enablement_packet_not_ready", [RuntimeGateFinding("error", "runtime_enablement_packet_not_ready", "runtime enablement packet is not ready by default", candidate.candidate_id, candidate.record_id)])
    for label, candidate_digest_field, record_digest_field, candidate_decision_field in EVIDENCE_MATCH_FIELDS:
        actual_digest = str(packet.get("digest") if label == "runtime_enablement_packet" else record.get(record_digest_field) or "")
        actual_decision = str(record.get(EVIDENCE_DECISION_RECORD_FIELDS[label]) or "")
        if str(raw.get(candidate_digest_field) or "") != actual_digest:
            return _blocked(f"{label}_digest_mismatch", [RuntimeGateFinding("error", f"{label}_digest_mismatch", f"{label} digest mismatch", candidate.candidate_id, candidate.record_id)])
        if str(raw.get(candidate_decision_field) or "") != actual_decision:
            return _blocked(f"{label}_decision_mismatch", [RuntimeGateFinding("error", f"{label}_decision_mismatch", f"{label} decision mismatch", candidate.candidate_id, candidate.record_id)])
    return None


def _check_scope(packet_record: Mapping[str, Any], candidate: RuntimeGateCandidate, policy: RuntimeGatePolicy) -> RuntimeGateResult | None:
    if not policy.require_scope_alignment or candidate.candidate_type == "mixed_runtime_gate_candidate":
        return None
    upstream = tuple(str(v) for v in packet_record.get("operator_scope_keys", ()))
    if upstream and candidate.operator_scope_keys != upstream:
        return _blocked("scope_mismatch", [RuntimeGateFinding("error", "scope_mismatch", "runtime gate candidate scope does not align with upstream evidence", candidate.candidate_id, candidate.record_id)])
    return None


def _decision(candidate: RuntimeGateCandidate, findings: Sequence[RuntimeGateFinding]) -> RuntimeGateDecision:
    if candidate.is_noop:
        return "runtime_gate_noop"
    if candidate.candidate_type == "operator_review_runtime_gate_candidate":
        return "runtime_gate_deferred_for_operator_review"
    if any(f.severity == "warning" for f in findings) or candidate.candidate_type == "mixed_runtime_gate_candidate":
        return "runtime_gate_ready_with_warnings"
    return "runtime_gate_ready_for_later_guarded_executor_path"


def _safe_actions(decision: RuntimeGateDecision) -> tuple[str, ...]:
    if decision == "runtime_gate_noop":
        return ("record_noop_metadata", "continue_review_without_runtime_authority")
    if decision == "runtime_gate_deferred_for_operator_review":
        return ("operator_review_metadata", "resolve_without_overriding_hard_blockers")
    return ("review_runtime_gate_packet", "prepare_separate_future_guarded_executor_path_request")


def evaluate_real_executor_runtime_gate(payload: Mapping[str, Any], policy: RuntimeGatePolicy | None = None) -> RuntimeGateResult:
    active_policy = policy or build_default_policy()
    policy_validation = validate_policy(active_policy)
    if policy_validation["status"] != "valid":
        return _blocked("invalid_policy", tuple(RuntimeGateFinding(**f) for f in policy_validation["findings"]))
    pair = _runtime_enablement_packet_and_record(payload)
    if isinstance(pair, RuntimeGateResult):
        return pair
    runtime_packet, runtime_record = pair
    candidates_raw = _candidate_list(payload)
    if isinstance(candidates_raw, RuntimeGateResult):
        return candidates_raw
    findings: list[RuntimeGateFinding] = []
    records: list[RuntimeGateRecord] = []
    try:
        for raw_value in candidates_raw:
            raw = _as_mapping(raw_value)
            candidate = RuntimeGateCandidate.from_mapping(raw)
            if not _valid_candidate(candidate):
                return _blocked("invalid_runtime_gate_candidate", [RuntimeGateFinding("error", "invalid_runtime_gate_candidate", "invalid runtime gate candidate", candidate.candidate_id, candidate.record_id)])
            claim_findings = _claims_findings(candidate) if active_policy.block_forbidden_claims else ()
            if claim_findings:
                return _blocked(claim_findings[0].code, claim_findings)
            required = _check_required_metadata(raw, candidate)
            if required is not None:
                return required
            scope = _check_scope(runtime_record, candidate, active_policy)
            if scope is not None:
                return scope
            evidence = _check_evidence(raw, runtime_packet, runtime_record, candidate)
            if evidence is not None:
                return evidence
            if candidate.candidate_type == "mixed_runtime_gate_candidate" and candidate.metadata.get("diagnostic_warning") is True:
                findings.append(RuntimeGateFinding("warning", "mixed_scope_diagnostic", "mixed runtime gate diagnostics allowed as warnings only", candidate.candidate_id, candidate.record_id))
            decision = _decision(candidate, findings)
            records.append(RuntimeGateRecord(
                candidate.candidate_id, candidate.record_id, candidate.candidate_type, decision,
                str(runtime_packet.get("digest") or ""), str(runtime_record.get("runtime_enablement_packet_decision") or ""),
                str(runtime_record.get("live_commit_execution_packet_digest") or ""), str(runtime_record.get("live_commit_execution_packet_decision") or ""),
                str(runtime_record.get("future_execution_gate_digest") or ""), str(runtime_record.get("future_execution_gate_decision") or ""),
                str(runtime_record.get("constrained_enablement_path_packet_digest") or ""), str(runtime_record.get("constrained_enablement_path_decision") or ""),
                str(runtime_record.get("executor_enablement_gate_digest") or ""), str(runtime_record.get("executor_enablement_gate_decision") or ""),
                str(runtime_record.get("executor_skeleton_digest") or ""), str(runtime_record.get("executor_skeleton_decision") or ""),
                str(runtime_record.get("invocation_harness_digest") or ""), str(runtime_record.get("invocation_harness_decision") or ""),
                str(runtime_record.get("activation_record_digest") or ""), str(runtime_record.get("activation_record_decision") or ""),
                str(runtime_record.get("preflight_packet_digest") or ""), str(runtime_record.get("preflight_packet_decision") or ""),
                str(runtime_record.get("lock_lease_gate_digest") or ""), str(runtime_record.get("lock_lease_gate_decision") or ""),
                str(runtime_record.get("executor_plan_packet_digest") or ""), str(runtime_record.get("executor_plan_decision") or ""),
                str(runtime_record.get("runtime_execution_gate_digest") or ""), str(runtime_record.get("runtime_execution_gate_decision") or ""),
                str(runtime_record.get("readiness_envelope_digest") or ""), str(runtime_record.get("readiness_envelope_decision") or ""),
                str(runtime_record.get("final_review_digest") or ""), str(runtime_record.get("final_review_decision") or ""),
                str(runtime_record.get("real_root_admission_digest") or ""), str(runtime_record.get("real_root_admission_decision") or ""),
                str(runtime_record.get("sandbox_commit_digest") or ""), str(runtime_record.get("sandbox_commit_decision") or ""),
                candidate.operator_scope_keys,
                (_metadata_record("runtime_gate_readiness", candidate, _as_mapping(raw.get("runtime_guard_verification_expectation_metadata") or raw.get("metadata"))),),
                (_metadata_record("runtime_enable_confirmation", candidate, _as_mapping(raw.get("runtime_enable_readiness_metadata") or raw.get("enablement_readiness_metadata"))),),
                (_metadata_record("runtime_flag_confirmation", candidate, _as_mapping(raw.get("runtime_flag_target_state_metadata"))),),
                (_metadata_record("guarded_executor_path_prerequisite", candidate, _as_mapping(raw.get("guarded_executor_path_prerequisite_metadata"))),),
                (_metadata_record("emergency_stop_confirmation", candidate, _as_mapping(raw.get("emergency_stop_confirmation_metadata"))),),
                (_metadata_record("rollback_readiness", candidate, _as_mapping(raw.get("rollback_readiness_metadata"))),),
                (_metadata_record("verification_readiness", candidate, _as_mapping(raw.get("verification_readiness_metadata"))),),
                (_metadata_record("audit_readiness", candidate, _as_mapping(raw.get("audit_readiness_metadata"))),),
                _safe_actions(decision),
            ).with_digest())
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for f in findings if f.severity == "warning")}
        for record in records:
            counts[record.runtime_gate_decision] = counts.get(record.runtime_gate_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {r.runtime_gate_decision for r in records}
        if counts["warning_count"] or "runtime_gate_ready_with_warnings" in decisions:
            status: RuntimeGateStatus = "runtime_gate_ready_with_warnings"
        elif decisions <= {"runtime_gate_noop"}:
            status = "runtime_gate_noop"
        elif decisions <= {"runtime_gate_deferred_for_operator_review"}:
            status = "runtime_gate_deferred_for_operator_review"
        else:
            status = "runtime_gate_ready"
        packet = RuntimeGatePacket(active_policy.schema_version, tuple(records)).with_digest()
        report = RuntimeGateReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return RuntimeGateResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("failed", [RuntimeGateFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: RuntimeGatePolicy | None = None) -> RuntimeGateResult:
    return evaluate_real_executor_runtime_gate(payload, policy)


__all__ = [
    "EVIDENCE_MATCH_FIELDS", "FAIL_STATUSES", "FORBIDDEN_NEXT_STEPS", "INVARIANTS", "NON_NOOP_METADATA_FIELDS",
    "READY_RUNTIME_ENABLEMENT_PACKET_DECISIONS", "RUNTIME_GATE_CANDIDATE_TYPES",
    "RuntimeGateCandidate", "RuntimeGateFinding", "RuntimeGateMetadataRecord", "RuntimeGatePacket",
    "RuntimeGatePolicy", "RuntimeGateRecord", "RuntimeGateReport", "RuntimeGateResult",
    "build_default_policy", "evaluate_packet", "evaluate_real_executor_runtime_gate", "validate_policy",
]
