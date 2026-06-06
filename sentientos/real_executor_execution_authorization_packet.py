"""Deterministic metadata-only real executor execution authorization packet builder.

This module consumes supplied Real Executor Execution Gate evidence and explicit
Real Executor Execution Authorization Packet candidates. It emits review metadata
for a later Real Executor Execution Authorization Gate only. It never enables, activates, invokes, locks, writes,
deletes, purges, indexes, persists, executes, discloses, calls external
services, touches real memory roots, or grants authority, policy, consent, or
truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Mapping, Sequence

RealExecutorExecutionAuthorizationPacketStatus = Literal[
    "real_executor_execution_authorization_packet_ready",
    "real_executor_execution_authorization_packet_ready_with_warnings",
    "real_executor_execution_authorization_packet_deferred_for_operator_review",
    "real_executor_execution_authorization_packet_rejected",
    "real_executor_execution_authorization_packet_blocked",
    "real_executor_execution_authorization_packet_noop",
    "real_executor_execution_authorization_packet_invalid",
    "real_executor_execution_authorization_packet_failed",
]
RealExecutorExecutionAuthorizationPacketDecision = Literal[
    "real_executor_execution_authorization_packet_ready_for_later_real_executor_execution_authorization_gate",
    "real_executor_execution_authorization_packet_ready_with_warnings",
    "real_executor_execution_authorization_packet_deferred_for_operator_review",
    "real_executor_execution_authorization_packet_rejected",
    "real_executor_execution_authorization_packet_blocked",
    "real_executor_execution_authorization_packet_noop",
]

REAL_EXECUTOR_EXECUTION_AUTHORIZATION_PACKET_CANDIDATE_TYPES = frozenset({
    "ai_capsule_real_executor_execution_authorization_packet_candidate",
    "human_summary_real_executor_execution_authorization_packet_candidate",
    "dual_capsule_real_executor_execution_authorization_packet_candidate",
    "protect_receipt_real_executor_execution_authorization_packet_candidate",
    "merge_receipt_real_executor_execution_authorization_packet_candidate",
    "tomb_archive_real_executor_execution_authorization_packet_candidate",
    "tomb_deferred_real_executor_execution_authorization_packet_candidate",
    "operator_review_real_executor_execution_authorization_packet_candidate",
    "noop_real_executor_execution_authorization_packet_candidate",
    "mixed_real_executor_execution_authorization_packet_candidate",
})
READY_REAL_EXECUTOR_EXECUTION_GATE_DECISIONS = frozenset({
    "real_executor_execution_gate_ready_for_later_real_executor_execution_authorization_packet",
    "real_executor_execution_gate_ready_with_warnings",
    "real_executor_execution_gate_noop",
})
FAIL_STATUSES = {"real_executor_execution_authorization_packet_blocked", "real_executor_execution_authorization_packet_invalid", "real_executor_execution_authorization_packet_failed"}

EVIDENCE_MATCH_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    ("real_executor_execution_gate", "claimed_real_executor_execution_gate_digest", "digest", "claimed_real_executor_execution_gate_decision"),
    ("real_executor_run_gate", "claimed_real_executor_run_gate_digest", "real_executor_run_gate_digest", "claimed_real_executor_run_gate_decision"),
    ("real_executor_run_packet", "claimed_real_executor_run_packet_digest", "real_executor_run_packet_digest", "claimed_real_executor_run_packet_decision"),
    ("real_executor_invocation_gate", "claimed_real_executor_invocation_gate_digest", "real_executor_invocation_gate_digest", "claimed_real_executor_invocation_gate_decision"),
    ("guarded_executor_invocation_packet", "claimed_guarded_executor_invocation_packet_digest", "guarded_executor_invocation_packet_digest", "claimed_guarded_executor_invocation_packet_decision"),
    ("guarded_executor_path_packet", "claimed_guarded_executor_path_packet_digest", "guarded_executor_path_packet_digest", "claimed_guarded_executor_path_packet_decision"),
    ("runtime_gate", "claimed_runtime_gate_digest", "runtime_gate_digest", "claimed_runtime_gate_decision"),
    ("runtime_enablement_packet", "claimed_runtime_enablement_packet_digest", "runtime_enablement_packet_digest", "claimed_runtime_enablement_packet_decision"),
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
    "real_executor_execution_gate": "real_executor_execution_gate_decision",
    "real_executor_run_gate": "real_executor_run_gate_decision",
    "real_executor_run_packet": "real_executor_run_packet_decision",
    "real_executor_invocation_gate": "real_executor_invocation_gate_decision",
    "guarded_executor_invocation_packet": "guarded_executor_invocation_packet_decision",
    "guarded_executor_path_packet": "guarded_executor_path_packet_decision",
    "runtime_gate": "runtime_gate_decision",
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
    "authorization_packet_readiness_metadata",
    "execution_gate_confirmation_metadata",
    "execution_authority_denial_metadata",
    "final_authorization_hold_point_metadata",
    "emergency_stop_confirmation_metadata",
    "rollback_readiness_metadata",
    "verification_readiness_metadata",
    "audit_readiness_metadata",
    "future_real_executor_execution_authorization_packet_requirement_metadata",
)

INVARIANTS: dict[str, bool] = {
    "real_executor_execution_authorization_packet_is_not_execution_authorization": True,
    "real_executor_execution_authorization_packet_is_not_permission_to_execute": True,
    "real_executor_execution_authorization_packet_is_not_executor_run": True,
    "real_executor_execution_authorization_packet_is_not_executor_execution": True,
    "real_executor_execution_authorization_packet_is_not_executor_invocation": True,
    "real_executor_execution_authorization_packet_is_not_runtime_enablement": True,
    "real_executor_execution_authorization_packet_is_not_runtime_flag_flip": True,
    "real_executor_execution_authorization_packet_is_not_live_commit_execution": True,
    "real_executor_execution_authorization_packet_is_not_enabled_executor": True,
    "real_executor_execution_authorization_packet_is_not_executor_enablement": True,
    "real_executor_execution_authorization_packet_is_not_executor_activation": True,
    "real_executor_execution_authorization_packet_is_not_lock_acquisition": True,
    "real_executor_execution_authorization_packet_is_not_lockfile_creation": True,
    "real_executor_execution_authorization_packet_is_not_memory_write": True,
    "real_executor_execution_authorization_packet_is_not_memory_deletion": True,
    "real_executor_execution_authorization_packet_is_not_memory_purge": True,
    "real_executor_execution_authorization_packet_is_not_index_mutation": True,
    "real_executor_execution_authorization_packet_is_not_capsule_persistence": True,
    "real_executor_execution_authorization_packet_is_not_tomb_completion": True,
    "real_executor_execution_authorization_packet_is_not_prompt_assembly": True,
    "real_executor_execution_authorization_packet_is_not_live_context_retrieval": True,
    "real_executor_execution_authorization_packet_is_not_action_execution": True,
    "real_executor_execution_authorization_packet_is_not_external_disclosure": True,
    "real_executor_execution_authorization_packet_is_not_truth": True,
    "real_executor_execution_authorization_packet_is_not_policy": True,
    "real_executor_execution_authorization_packet_is_not_authority": True,
    "real_executor_execution_authorization_packet_is_not_consent": True,
    "authorization_packet_readiness_is_metadata_only": True,
    "execution_gate_confirmation_is_metadata_only": True,
    "execution_authority_denial_is_metadata_only": True,
    "final_authorization_hold_points_are_metadata_only": True,
    "emergency_stop_confirmation_is_metadata_only": True,
    "rollback_readiness_is_metadata_only": True,
    "verification_readiness_is_metadata_only": True,
    "audit_readiness_is_metadata_only": True,
    "real_executor_enabled": False,
    "real_executor_runtime_enablement_enabled": False,
    "real_executor_enablement_enabled": False,
    "real_executor_invocation_enabled": False,
    "real_executor_run_enabled": False,
    "real_executor_execution_enabled": False,
    "real_executor_execution_authorized": False,
    "real_executor_authorization_gate_passed": False,
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
    "future_real_executor_execution_authorization_gate_required": True,
    "future_real_live_memory_commit_execution_required": True,
    "future_post_execution_audit_required": True,
}
FORBIDDEN_NEXT_STEPS = (
    "real_executor_execution", "real_executor_run", "runtime_enablement", "runtime_flag_flipping", "live_execution", "executor_enablement",
    "executor_run", "executor_activation", "real_lock_acquisition", "lockfile_creation", "real_live_memory_write",
    "real_live_memory_delete", "real_live_memory_purge", "index_mutation", "prompt_assembly", "live_context_retrieval",
    "action_ingress", "sandbox_bypass", "real_root_admission_bypass", "final_review_bypass", "readiness_envelope_bypass",
    "runtime_gate_bypass", "executor_plan_bypass", "lock_lease_bypass", "preflight_bypass", "activation_record_bypass",
    "invocation_harness_bypass", "executor_skeleton_bypass", "enablement_gate_bypass", "constrained_path_bypass",
    "future_execution_gate_bypass", "live_commit_execution_packet_bypass", "runtime_enablement_packet_bypass",
    "real_executor_runtime_gate_bypass", "direct_executor_execution", "external_disclosure",
)
FORBIDDEN_CLAIM_CODES = {
    "real_executor_run_executed": "executor_run_claim",
    "executor_enabled": "executor_enablement_claim", "executor_invoked": "executor_run_claim",
    "executor_activated": "executor_activation_claim", "runtime_enablement_claimed": "runtime_enablement_claim",
    "runtime_flags_flipped": "runtime_flag_flipping_claim", "runtime_flag_target_state_active": "runtime_flag_active_state_claim",
    "live_commit_executed": "live_execution_claim", "permission_to_execute_now": "executor_permission_claim",
    "guarded_executor_prerequisites_are_run": "guarded_executor_prerequisite_run_claim",
    "real_executor_invocation_claimed": "executor_invocation_claim",
    "execution_hold_points_are_live_execution": "run_hold_point_live_run_claim",
    "operation_bundle_executed": "operation_bundle_execution_claim", "receipt_envelope_is_live_receipt": "live_receipt_claim",
    "rollback_readiness_applied": "applied_rollback_claim", "rollback_envelope_applied": "applied_rollback_claim",
    "live_memory_write_claimed": "live_write_claim", "live_memory_delete_claimed": "live_delete_claim",
    "live_memory_purge_claimed": "live_purge_claim", "live_index_mutation_claimed": "index_mutation_claim",
    "capsule_persistence_claimed": "capsule_persistence_claim", "tomb_completion_claimed": "tomb_completion_claim",
    "protection_application_claimed": "protection_application_claim", "merge_application_claimed": "merge_application_claim",
    "prompt_assembly_claimed": "prompt_materialization", "live_context_retrieval_claimed": "live_context_retrieval",
    "action_execution_claimed": "action_execution", "external_disclosure_claimed": "external_disclosure",
    "external_service_called": "external_service_call", "lockfile_creation_claimed": "lockfile_creation_claim",
    "real_lock_acquisition_claimed": "real_lock_acquisition_claim", "real_memory_root_access_claimed": "real_memory_root_access_claim",
    "authority_granted": "authority_smuggling", "consent_granted": "consent_smuggling", "policy_created": "policy_smuggling",
    "truth_asserted": "truth_smuggling", "raw_payload_included": "raw_payload_leakage", "private_payload_included": "raw_payload_leakage",
    "media_payload_included": "raw_payload_leakage", "secret_payload_included": "raw_payload_leakage",
}
_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")

def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()

def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}

@dataclass(frozen=True)
class RealExecutorExecutionAuthorizationPacketFinding:
    severity: str; code: str; message: str; candidate_id: str = ""; record_id: str = ""
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class RealExecutorExecutionAuthorizationPacketPolicy:
    schema_version: str = "real-executor-authorization-packet.v1"
    default_deny: bool = True; metadata_only: bool = True; allow_mixed_diagnostics: bool = True
    require_scope_alignment: bool = True; block_forbidden_claims: bool = True
    real_executor_enabled: bool = False; real_executor_runtime_enablement_enabled: bool = False
    real_executor_enablement_enabled: bool = False; real_executor_invocation_enabled: bool = False; real_executor_run_enabled: bool = False
    real_executor_activation_enabled: bool = False; real_lock_acquisition_enabled: bool = False
    lockfile_creation_enabled: bool = False; real_memory_root_access_enabled: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class RealExecutorExecutionAuthorizationPacketCandidate:
    candidate_id: str; record_id: str; candidate_type: str; operator_scope_keys: tuple[str, ...]
    metadata: Mapping[str, Any]; claims: Mapping[str, Any]
    @staticmethod
    def from_mapping(payload: Mapping[str, Any]) -> "RealExecutorExecutionAuthorizationPacketCandidate":
        return RealExecutorExecutionAuthorizationPacketCandidate(str(payload.get("candidate_id") or ""), str(payload.get("record_id") or ""), str(payload.get("candidate_type") or ""), tuple(str(v) for v in payload.get("operator_scope_keys", ())), _as_mapping(payload.get("metadata")), _as_mapping(payload.get("real_executor_execution_authorization_packet_claims") or payload.get("claims")))
    @property
    def is_noop(self) -> bool: return self.candidate_type in {"noop_real_executor_execution_authorization_packet_candidate", "noop_real_executor_execution_authorization_packet_candidate"}

@dataclass(frozen=True)
class RealExecutorExecutionAuthorizationPacketMetadataRecord:
    record_type: str; candidate_id: str; record_id: str; metadata_digest: str
    metadata_only: bool = True; authoritative: bool = False; runtime_enabled: bool = False
    runtime_flag_flipped: bool = False; executed: bool = False; permission_granted: bool = False
    active_runtime_state: bool = False; executor_invoked: bool = False; live_receipt: bool = False; rollback_applied: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class RealExecutorExecutionAuthorizationPacketRecord:
    candidate_id: str; record_id: str; candidate_type: str; real_executor_execution_authorization_packet_decision: RealExecutorExecutionAuthorizationPacketDecision
    real_executor_execution_gate_digest: str; real_executor_execution_gate_decision: str
    real_executor_run_gate_digest: str; real_executor_run_gate_decision: str
    real_executor_run_packet_digest: str; real_executor_run_packet_decision: str
    real_executor_invocation_gate_digest: str; real_executor_invocation_gate_decision: str
    guarded_executor_invocation_packet_digest: str; guarded_executor_invocation_packet_decision: str
    guarded_executor_path_packet_digest: str; guarded_executor_path_packet_decision: str
    runtime_gate_digest: str; runtime_gate_decision: str; runtime_enablement_packet_digest: str; runtime_enablement_packet_decision: str
    live_commit_execution_packet_digest: str; live_commit_execution_packet_decision: str; future_execution_gate_digest: str; future_execution_gate_decision: str
    constrained_enablement_path_packet_digest: str; constrained_enablement_path_decision: str; executor_enablement_gate_digest: str; executor_enablement_gate_decision: str
    executor_skeleton_digest: str; executor_skeleton_decision: str; invocation_harness_digest: str; invocation_harness_decision: str
    activation_record_digest: str; activation_record_decision: str; preflight_packet_digest: str; preflight_packet_decision: str
    lock_lease_gate_digest: str; lock_lease_gate_decision: str; executor_plan_packet_digest: str; executor_plan_decision: str
    runtime_execution_gate_digest: str; runtime_execution_gate_decision: str; readiness_envelope_digest: str; readiness_envelope_decision: str
    final_review_digest: str; final_review_decision: str; real_root_admission_digest: str; real_root_admission_decision: str
    sandbox_commit_digest: str; sandbox_commit_decision: str; operator_scope_keys: tuple[str, ...]
    authorization_packet_readiness_records: tuple[RealExecutorExecutionAuthorizationPacketMetadataRecord, ...]
    execution_gate_confirmation_records: tuple[RealExecutorExecutionAuthorizationPacketMetadataRecord, ...]
    execution_authority_denial_records: tuple[RealExecutorExecutionAuthorizationPacketMetadataRecord, ...]
    final_authorization_hold_point_records: tuple[RealExecutorExecutionAuthorizationPacketMetadataRecord, ...]
    emergency_stop_confirmation_records: tuple[RealExecutorExecutionAuthorizationPacketMetadataRecord, ...]
    rollback_readiness_records: tuple[RealExecutorExecutionAuthorizationPacketMetadataRecord, ...]
    verification_readiness_records: tuple[RealExecutorExecutionAuthorizationPacketMetadataRecord, ...]
    audit_readiness_records: tuple[RealExecutorExecutionAuthorizationPacketMetadataRecord, ...]
    safe_next_actions: tuple[str, ...]; forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    real_executor_enabled: bool = False; real_executor_runtime_enablement_enabled: bool = False; real_executor_enablement_enabled: bool = False
    real_executor_invocation_enabled: bool = False; real_executor_run_enabled: bool = False; real_executor_execution_enabled: bool = False; real_executor_activation_enabled: bool = False; real_lock_acquisition_enabled: bool = False
    lockfile_created: bool = False; runtime_flags_flipped: bool = False; live_commit_executed: bool = False; live_execution_permission_granted: bool = False
    runtime_flag_target_state_is_active_runtime_state: bool = False; execution_gate_confirmation_is_not_executor_execution: bool = False
    execution_hold_points_are_live_execution: bool = False; operator_review_cannot_override_hard_blockers: bool = True
    future_real_executor_execution_authorization_gate_required: bool = True; future_real_live_memory_commit_execution_required: bool = True; future_post_execution_audit_required: bool = True
    digest: str = ""
    def to_dict(self) -> dict[str, Any]: return asdict(self)
    def with_digest(self) -> "RealExecutorExecutionAuthorizationPacketRecord": return replace(self, digest=_digest({k: v for k, v in self.to_dict().items() if k != "digest"}))

@dataclass(frozen=True)
class RealExecutorExecutionAuthorizationPacketPacket:
    schema_version: str; records: tuple[RealExecutorExecutionAuthorizationPacketRecord, ...]; digest: str = ""; forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self); payload.update(INVARIANTS); return payload
    def with_digest(self) -> "RealExecutorExecutionAuthorizationPacketPacket": return replace(self, digest=_digest({k: v for k, v in self.to_dict().items() if k != "digest"}))

@dataclass(frozen=True)
class RealExecutorExecutionAuthorizationPacketReport:
    status: RealExecutorExecutionAuthorizationPacketStatus; findings: tuple[RealExecutorExecutionAuthorizationPacketFinding, ...]; summary_counts: Mapping[str, int]; digest: str = ""
    def to_dict(self) -> dict[str, Any]: return {"status": self.status, "findings": [f.to_dict() for f in self.findings], "summary_counts": dict(self.summary_counts), "digest": self.digest}

@dataclass(frozen=True)
class RealExecutorExecutionAuthorizationPacketResult:
    status: RealExecutorExecutionAuthorizationPacketStatus; packet: RealExecutorExecutionAuthorizationPacketPacket | None; report: RealExecutorExecutionAuthorizationPacketReport; digest: str
    def to_dict(self) -> dict[str, Any]: return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}

def build_default_policy() -> RealExecutorExecutionAuthorizationPacketPolicy: return RealExecutorExecutionAuthorizationPacketPolicy()

def validate_policy(policy: RealExecutorExecutionAuthorizationPacketPolicy | None = None) -> dict[str, Any]:
    active = policy or build_default_policy(); findings: list[RealExecutorExecutionAuthorizationPacketFinding] = []
    if not active.default_deny or not active.metadata_only:
        findings.append(RealExecutorExecutionAuthorizationPacketFinding("error", "policy_not_metadata_only_default_deny", "policy must remain metadata-only and default-deny"))
    for name in ("real_executor_enabled", "real_executor_runtime_enablement_enabled", "real_executor_enablement_enabled", "real_executor_invocation_enabled", "real_executor_run_enabled", "real_executor_activation_enabled", "real_lock_acquisition_enabled", "lockfile_creation_enabled", "real_memory_root_access_enabled"):
        if bool(getattr(active, name)):
            findings.append(RealExecutorExecutionAuthorizationPacketFinding("error", name, f"{name} must remain false"))
    return {"status": "valid" if not findings else "invalid", "policy": active.to_dict(), "findings": [f.to_dict() for f in findings]}

def _blocked(code: str, findings: Sequence[RealExecutorExecutionAuthorizationPacketFinding] = ()) -> RealExecutorExecutionAuthorizationPacketResult:
    all_findings = tuple(findings) or (RealExecutorExecutionAuthorizationPacketFinding("error", code, code),)
    report = RealExecutorExecutionAuthorizationPacketReport("real_executor_execution_authorization_packet_blocked", all_findings, {"blocked": 1})
    report = replace(report, digest=_digest(report.to_dict()))
    return RealExecutorExecutionAuthorizationPacketResult("real_executor_execution_authorization_packet_blocked", None, report, _digest(report.to_dict()))

def _metadata_record(kind: str, candidate: RealExecutorExecutionAuthorizationPacketCandidate, metadata: Mapping[str, Any]) -> RealExecutorExecutionAuthorizationPacketMetadataRecord:
    return RealExecutorExecutionAuthorizationPacketMetadataRecord(kind, candidate.candidate_id, candidate.record_id, _digest(dict(metadata)))

def _valid_candidate(candidate: RealExecutorExecutionAuthorizationPacketCandidate) -> bool:
    return bool(_ID_RE.match(candidate.candidate_id)) and bool(_ID_RE.match(candidate.record_id)) and candidate.candidate_type in REAL_EXECUTOR_EXECUTION_AUTHORIZATION_PACKET_CANDIDATE_TYPES

def _real_executor_execution_gate_and_record(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]] | RealExecutorExecutionAuthorizationPacketResult:
    packet = _as_mapping(payload.get("real_executor_execution_gate"))
    if not packet: return _blocked("missing_real_executor_execution_gate")
    records = packet.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records: return _blocked("invalid_real_executor_execution_gate")
    record = _as_mapping(records[0])
    if not str(packet.get("digest") or "") or not str(record.get("digest") or ""): return _blocked("invalid_real_executor_execution_gate")
    return packet, record

def _candidate_list(payload: Mapping[str, Any]) -> Sequence[Any] | RealExecutorExecutionAuthorizationPacketResult:
    candidates = payload.get("real_executor_execution_authorization_packet_candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)) or not candidates: return _blocked("missing_real_executor_execution_authorization_packet_candidate")
    return candidates

def _check_required_metadata(raw: Mapping[str, Any], candidate: RealExecutorExecutionAuthorizationPacketCandidate) -> RealExecutorExecutionAuthorizationPacketResult | None:
    if candidate.is_noop: return None
    for field in NON_NOOP_METADATA_FIELDS:
        if not isinstance(raw.get(field), Mapping) or not raw.get(field):
            return _blocked(f"missing_{field}", [RealExecutorExecutionAuthorizationPacketFinding("error", f"missing_{field}", f"missing required non-noop metadata: {field}", candidate.candidate_id, candidate.record_id)])
    return None

def _check_evidence(raw: Mapping[str, Any], packet: Mapping[str, Any], record: Mapping[str, Any], candidate: RealExecutorExecutionAuthorizationPacketCandidate) -> RealExecutorExecutionAuthorizationPacketResult | None:
    decision = str(record.get("real_executor_execution_gate_decision") or "")
    if decision not in READY_REAL_EXECUTOR_EXECUTION_GATE_DECISIONS:
        return _blocked("real_executor_execution_gate_not_ready", [RealExecutorExecutionAuthorizationPacketFinding("error", "real_executor_execution_gate_not_ready", "real executor execution gate is not ready by default", candidate.candidate_id, candidate.record_id)])
    for label, candidate_digest_field, record_digest_field, candidate_decision_field in EVIDENCE_MATCH_FIELDS:
        actual_digest = str(packet.get("digest") if label == "real_executor_execution_gate" else record.get(record_digest_field) or "")
        actual_decision = str(record.get(EVIDENCE_DECISION_RECORD_FIELDS[label]) or "")
        if str(raw.get(candidate_digest_field) or "") != actual_digest:
            return _blocked(f"{label}_digest_mismatch", [RealExecutorExecutionAuthorizationPacketFinding("error", f"{label}_digest_mismatch", f"{label} digest mismatch", candidate.candidate_id, candidate.record_id)])
        if str(raw.get(candidate_decision_field) or "") != actual_decision:
            return _blocked(f"{label}_decision_mismatch", [RealExecutorExecutionAuthorizationPacketFinding("error", f"{label}_decision_mismatch", f"{label} decision mismatch", candidate.candidate_id, candidate.record_id)])
    return None

def _check_scope(packet_record: Mapping[str, Any], candidate: RealExecutorExecutionAuthorizationPacketCandidate, policy: RealExecutorExecutionAuthorizationPacketPolicy) -> RealExecutorExecutionAuthorizationPacketResult | None:
    if not policy.require_scope_alignment or candidate.candidate_type in {"mixed_real_executor_execution_authorization_packet_candidate", "mixed_real_executor_execution_authorization_packet_candidate"}: return None
    upstream = tuple(str(v) for v in packet_record.get("operator_scope_keys", ()))
    if upstream and candidate.operator_scope_keys != upstream:
        return _blocked("scope_mismatch", [RealExecutorExecutionAuthorizationPacketFinding("error", "scope_mismatch", "real executor execution authorization packet candidate scope does not align with upstream evidence", candidate.candidate_id, candidate.record_id)])
    return None

def _claims_findings(candidate: RealExecutorExecutionAuthorizationPacketCandidate) -> tuple[RealExecutorExecutionAuthorizationPacketFinding, ...]:
    return tuple(RealExecutorExecutionAuthorizationPacketFinding("error", code, f"forbidden real executor execution authorization packet claim blocked: {key}", candidate.candidate_id, candidate.record_id) for key, code in FORBIDDEN_CLAIM_CODES.items() if candidate.claims.get(key) is True)

def _decision(candidate: RealExecutorExecutionAuthorizationPacketCandidate, findings: Sequence[RealExecutorExecutionAuthorizationPacketFinding]) -> RealExecutorExecutionAuthorizationPacketDecision:
    if candidate.is_noop: return "real_executor_execution_authorization_packet_noop"
    if candidate.candidate_type in {"operator_review_real_executor_execution_authorization_packet_candidate", "operator_review_real_executor_execution_authorization_packet_candidate"}: return "real_executor_execution_authorization_packet_deferred_for_operator_review"
    if any(f.severity == "warning" for f in findings) or candidate.candidate_type in {"mixed_real_executor_execution_authorization_packet_candidate", "mixed_real_executor_execution_authorization_packet_candidate"}: return "real_executor_execution_authorization_packet_ready_with_warnings"
    return "real_executor_execution_authorization_packet_ready_for_later_real_executor_execution_authorization_gate"

def _safe_actions(decision: RealExecutorExecutionAuthorizationPacketDecision) -> tuple[str, ...]:
    if decision == "real_executor_execution_authorization_packet_noop": return ("record_noop_metadata", "continue_review_without_executor_authority")
    if decision == "real_executor_execution_authorization_packet_deferred_for_operator_review": return ("operator_review_metadata", "resolve_without_overriding_hard_blockers")
    return ("review_real_executor_execution_authorization_packet_metadata", "prepare_separate_future_real_executor_execution_authorization_gate_request")

def evaluate_real_executor_execution_authorization_packet(payload: Mapping[str, Any], policy: RealExecutorExecutionAuthorizationPacketPolicy | None = None) -> RealExecutorExecutionAuthorizationPacketResult:
    active_policy = policy or build_default_policy(); policy_validation = validate_policy(active_policy)
    if policy_validation["status"] != "valid": return _blocked("invalid_policy", tuple(RealExecutorExecutionAuthorizationPacketFinding(**f) for f in policy_validation["findings"]))
    pair = _real_executor_execution_gate_and_record(payload)
    if isinstance(pair, RealExecutorExecutionAuthorizationPacketResult): return pair
    execution_gate, gate_record = pair
    candidates_raw = _candidate_list(payload)
    if isinstance(candidates_raw, RealExecutorExecutionAuthorizationPacketResult): return candidates_raw
    findings: list[RealExecutorExecutionAuthorizationPacketFinding] = []; records: list[RealExecutorExecutionAuthorizationPacketRecord] = []
    try:
        for raw_value in candidates_raw:
            raw = _as_mapping(raw_value); candidate = RealExecutorExecutionAuthorizationPacketCandidate.from_mapping(raw)
            if not _valid_candidate(candidate): return _blocked("invalid_real_executor_execution_authorization_packet_candidate", [RealExecutorExecutionAuthorizationPacketFinding("error", "invalid_real_executor_execution_authorization_packet_candidate", "invalid real executor execution authorization packet candidate", candidate.candidate_id, candidate.record_id)])
            claim_findings = _claims_findings(candidate) if active_policy.block_forbidden_claims else ()
            if claim_findings: return _blocked(claim_findings[0].code, claim_findings)
            for check in (_check_required_metadata(raw, candidate), _check_scope(gate_record, candidate, active_policy), _check_evidence(raw, execution_gate, gate_record, candidate)):
                if check is not None: return check
            if candidate.candidate_type in {"mixed_real_executor_execution_authorization_packet_candidate", "mixed_real_executor_execution_authorization_packet_candidate"} and candidate.metadata.get("diagnostic_warning") is True:
                findings.append(RealExecutorExecutionAuthorizationPacketFinding("warning", "mixed_scope_diagnostic", "mixed real executor execution authorization packet diagnostics allowed as warnings only", candidate.candidate_id, candidate.record_id))
            decision = _decision(candidate, findings)
            records.append(RealExecutorExecutionAuthorizationPacketRecord(
                candidate.candidate_id, candidate.record_id, candidate.candidate_type, decision,
                str(execution_gate.get("digest") or ""), str(gate_record.get("real_executor_execution_gate_decision") or ""),
                str(gate_record.get("real_executor_run_gate_digest") or ""), str(gate_record.get("real_executor_run_gate_decision") or ""),
                str(gate_record.get("real_executor_run_packet_digest") or ""), str(gate_record.get("real_executor_run_packet_decision") or ""),
                str(gate_record.get("real_executor_invocation_gate_digest") or ""), str(gate_record.get("real_executor_invocation_gate_decision") or ""),
                str(gate_record.get("guarded_executor_invocation_packet_digest") or ""), str(gate_record.get("guarded_executor_invocation_packet_decision") or ""),
                str(gate_record.get("guarded_executor_path_packet_digest") or ""), str(gate_record.get("guarded_executor_path_packet_decision") or ""),
                str(gate_record.get("runtime_gate_digest") or ""), str(gate_record.get("runtime_gate_decision") or ""),
                str(gate_record.get("runtime_enablement_packet_digest") or ""), str(gate_record.get("runtime_enablement_packet_decision") or ""),
                str(gate_record.get("live_commit_execution_packet_digest") or ""), str(gate_record.get("live_commit_execution_packet_decision") or ""),
                str(gate_record.get("future_execution_gate_digest") or ""), str(gate_record.get("future_execution_gate_decision") or ""),
                str(gate_record.get("constrained_enablement_path_packet_digest") or ""), str(gate_record.get("constrained_enablement_path_decision") or ""),
                str(gate_record.get("executor_enablement_gate_digest") or ""), str(gate_record.get("executor_enablement_gate_decision") or ""),
                str(gate_record.get("executor_skeleton_digest") or ""), str(gate_record.get("executor_skeleton_decision") or ""),
                str(gate_record.get("invocation_harness_digest") or ""), str(gate_record.get("invocation_harness_decision") or ""),
                str(gate_record.get("activation_record_digest") or ""), str(gate_record.get("activation_record_decision") or ""),
                str(gate_record.get("preflight_packet_digest") or ""), str(gate_record.get("preflight_packet_decision") or ""),
                str(gate_record.get("lock_lease_gate_digest") or ""), str(gate_record.get("lock_lease_gate_decision") or ""),
                str(gate_record.get("executor_plan_packet_digest") or ""), str(gate_record.get("executor_plan_decision") or ""),
                str(gate_record.get("runtime_execution_gate_digest") or ""), str(gate_record.get("runtime_execution_gate_decision") or ""),
                str(gate_record.get("readiness_envelope_digest") or ""), str(gate_record.get("readiness_envelope_decision") or ""),
                str(gate_record.get("final_review_digest") or ""), str(gate_record.get("final_review_decision") or ""),
                str(gate_record.get("real_root_admission_digest") or ""), str(gate_record.get("real_root_admission_decision") or ""),
                str(gate_record.get("sandbox_commit_digest") or ""), str(gate_record.get("sandbox_commit_decision") or ""),
                candidate.operator_scope_keys,
                (_metadata_record("authorization_packet_readiness", candidate, _as_mapping(raw.get("authorization_packet_readiness_metadata") or raw.get("metadata"))),),
                (_metadata_record("execution_gate_confirmation", candidate, _as_mapping(raw.get("execution_gate_confirmation_metadata") or raw.get("real_executor_execution_authorization_packet_prerequisite_metadata"))),),
                (_metadata_record("execution_authority_denial", candidate, _as_mapping(raw.get("execution_authority_denial_metadata") or raw.get("real_executor_execution_authorization_packet_hold_point_metadata"))),),
                (_metadata_record("final_authorization_hold_point", candidate, _as_mapping(raw.get("final_authorization_hold_point_metadata") or raw.get("runtime_guard_verification_expectation_metadata"))),),
                (_metadata_record("emergency_stop_confirmation", candidate, _as_mapping(raw.get("emergency_stop_confirmation_metadata"))),),
                (_metadata_record("rollback_readiness", candidate, _as_mapping(raw.get("rollback_readiness_metadata"))),),
                (_metadata_record("verification_readiness", candidate, _as_mapping(raw.get("verification_readiness_metadata"))),),
                (_metadata_record("audit_readiness", candidate, _as_mapping(raw.get("audit_readiness_metadata"))),),
                _safe_actions(decision),
            ).with_digest())
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for f in findings if f.severity == "warning")}
        for record in records:
            counts[record.real_executor_execution_authorization_packet_decision] = counts.get(record.real_executor_execution_authorization_packet_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {r.real_executor_execution_authorization_packet_decision for r in records}
        if counts["warning_count"] or "real_executor_execution_authorization_packet_ready_with_warnings" in decisions: status: RealExecutorExecutionAuthorizationPacketStatus = "real_executor_execution_authorization_packet_ready_with_warnings"
        elif decisions <= {"real_executor_execution_authorization_packet_noop"}: status = "real_executor_execution_authorization_packet_noop"
        elif decisions <= {"real_executor_execution_authorization_packet_deferred_for_operator_review"}: status = "real_executor_execution_authorization_packet_deferred_for_operator_review"
        else: status = "real_executor_execution_authorization_packet_ready"
        packet = RealExecutorExecutionAuthorizationPacketPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = RealExecutorExecutionAuthorizationPacketReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return RealExecutorExecutionAuthorizationPacketResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("failed", [RealExecutorExecutionAuthorizationPacketFinding("error", "failed", str(exc))])

def evaluate_packet(payload: Mapping[str, Any], policy: RealExecutorExecutionAuthorizationPacketPolicy | None = None) -> RealExecutorExecutionAuthorizationPacketResult:
    return evaluate_real_executor_execution_authorization_packet(payload, policy)

__all__ = [
    "EVIDENCE_MATCH_FIELDS", "FAIL_STATUSES", "FORBIDDEN_NEXT_STEPS", "INVARIANTS", "NON_NOOP_METADATA_FIELDS",
    "READY_REAL_EXECUTOR_EXECUTION_GATE_DECISIONS", "REAL_EXECUTOR_EXECUTION_AUTHORIZATION_PACKET_CANDIDATE_TYPES", "RealExecutorExecutionAuthorizationPacketCandidate",
    "RealExecutorExecutionAuthorizationPacketFinding", "RealExecutorExecutionAuthorizationPacketMetadataRecord", "RealExecutorExecutionAuthorizationPacketPacket", "RealExecutorExecutionAuthorizationPacketPolicy",
    "RealExecutorExecutionAuthorizationPacketRecord", "RealExecutorExecutionAuthorizationPacketReport", "RealExecutorExecutionAuthorizationPacketResult", "build_default_policy",
    "evaluate_packet", "evaluate_real_executor_execution_authorization_packet", "validate_policy",
]
