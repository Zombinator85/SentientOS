"""Deterministic metadata-only Sandboxed Live Memory Commit Adapter.

The packet consumes supplied Real Memory Root Admission Gate evidence and
explicit sandboxed-live-memory-commit-adapter candidates.  It produces only
reviewable metadata for a later Sandboxed Live Memory Commit Adapter rung.  It
never admits roots, creates an admission packet, approves live execution,
executes, applies, enables, invokes, locks, writes, creates/admitted adapters,
discloses, or grants authority or permission to execute.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Mapping, Sequence

SandboxedLiveMemoryCommitAdapterStatus = Literal[
    "sandboxed_live_memory_commit_adapter_ready",
    "sandboxed_live_memory_commit_adapter_ready_with_warnings",
    "sandboxed_live_memory_commit_adapter_deferred_for_operator_review",
    "sandboxed_live_memory_commit_adapter_rejected",
    "sandboxed_live_memory_commit_adapter_blocked",
    "sandboxed_live_memory_commit_adapter_noop",
    "sandboxed_live_memory_commit_adapter_invalid",
    "sandboxed_live_memory_commit_adapter_failed",
]
SandboxedLiveMemoryCommitAdapterDecision = Literal[
    "sandboxed_live_memory_commit_adapter_ready_for_later_sandboxed_live_memory_commit_adapter_gate",
    "sandboxed_live_memory_commit_adapter_ready_with_warnings",
    "sandboxed_live_memory_commit_adapter_deferred_for_operator_review",
    "sandboxed_live_memory_commit_adapter_rejected",
    "sandboxed_live_memory_commit_adapter_blocked",
    "sandboxed_live_memory_commit_adapter_noop",
]

SANDBOXED_LIVE_MEMORY_COMMIT_ADAPTER_CANDIDATE_TYPES = frozenset({
    "ai_capsule_sandboxed_live_memory_commit_adapter_candidate",
    "human_summary_sandboxed_live_memory_commit_adapter_candidate",
    "dual_capsule_sandboxed_live_memory_commit_adapter_candidate",
    "protect_receipt_sandboxed_live_memory_commit_adapter_candidate",
    "merge_receipt_sandboxed_live_memory_commit_adapter_candidate",
    "tomb_archive_sandboxed_live_memory_commit_adapter_candidate",
    "tomb_deferred_sandboxed_live_memory_commit_adapter_candidate",
    "operator_review_sandboxed_live_memory_commit_adapter_candidate",
    "noop_sandboxed_live_memory_commit_adapter_candidate",
    "mixed_sandboxed_live_memory_commit_adapter_candidate",
})
COMPATIBILITY_CANDIDATE_TYPES = frozenset({name.replace("sandboxed_live_memory_commit_adapter", "real_root_admission") for name in SANDBOXED_LIVE_MEMORY_COMMIT_ADAPTER_CANDIDATE_TYPES})
ALL_CANDIDATE_TYPES = SANDBOXED_LIVE_MEMORY_COMMIT_ADAPTER_CANDIDATE_TYPES | COMPATIBILITY_CANDIDATE_TYPES
READY_REAL_MEMORY_ROOT_ADMISSION_PACKET_DECISIONS = frozenset({
    "real_memory_root_admission_packet_ready_for_later_sandboxed_live_memory_commit_adapter",
    "real_memory_root_admission_packet_ready_with_warnings",
    "real_memory_root_admission_packet_noop",
})
FAIL_STATUSES = {
    "sandboxed_live_memory_commit_adapter_blocked",
    "sandboxed_live_memory_commit_adapter_invalid",
    "sandboxed_live_memory_commit_adapter_failed",
}

CARRIED_EVIDENCE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("real_memory_root_admission_packet", "real_memory_root_admission_packet_digest", "real_memory_root_admission_packet_decision"),
    ("final_live_memory_commit_review_gate", "final_live_memory_commit_review_gate_digest", "final_live_memory_commit_review_gate_decision"),
    ("real_live_memory_commit_adapter_readiness_envelope", "real_live_memory_commit_adapter_readiness_envelope_digest", "real_live_memory_commit_adapter_readiness_envelope_decision"),
    ("real_live_memory_commit_adapter_readiness_gate", "real_live_memory_commit_adapter_readiness_gate_digest", "real_live_memory_commit_adapter_readiness_gate_decision"),
    ("real_live_memory_commit_adapter_admission_packet", "real_live_memory_commit_adapter_admission_packet_digest", "real_live_memory_commit_adapter_admission_packet_decision"),
    ("real_live_memory_commit_adapter_admission_gate", "real_live_memory_commit_adapter_admission_gate_digest", "real_live_memory_commit_adapter_admission_gate_decision"),
    ("real_live_memory_commit_execution_packet", "real_live_memory_commit_execution_packet_digest", "real_live_memory_commit_execution_packet_decision"),
    ("real_live_memory_commit_execution_gate", "real_live_memory_commit_execution_gate_digest", "real_live_memory_commit_execution_gate_decision"),
    ("real_executor_execution_commit_window_packet", "real_executor_execution_commit_window_packet_digest", "real_executor_execution_commit_window_packet_decision"),
    ("real_executor_execution_commit_plan_gate", "real_executor_execution_commit_plan_gate_digest", "real_executor_execution_commit_plan_gate_decision"),
    ("real_executor_execution_commit_plan_packet", "real_executor_execution_commit_plan_packet_digest", "real_executor_execution_commit_plan_packet_decision"),
)
NON_NOOP_METADATA_FIELDS = (
    "sandboxed_adapter_readiness_metadata",
    "packet_confirmation_metadata",
    "adapter_readiness_envelope_confirmation_metadata",
    "adapter_readiness_gate_confirmation_metadata",
    "adapter_admission_packet_confirmation_metadata",
    "adapter_admission_gate_confirmation_metadata",
    "live_memory_commit_execution_packet_confirmation_metadata",
    "live_memory_commit_execution_gate_confirmation_metadata",
    "commit_window_packet_confirmation_metadata",
    "commit_plan_gate_confirmation_metadata",
    "commit_plan_packet_confirmation_metadata",
    "live_commit_execution_denial_metadata",
    "live_memory_write_denial_metadata",
    "real_memory_root_admission_deferral_metadata",
    "emergency_stop_confirmation_metadata",
    "rollback_readiness_metadata",
    "verification_readiness_metadata",
    "audit_readiness_metadata",
)
INVARIANTS: dict[str, bool] = {
    "sandboxed_live_memory_commit_adapter_is_not_live_commit_execution": True,
    "sandboxed_live_memory_commit_adapter_does_not_approve_live_execution": True,
    "sandboxed_live_memory_commit_adapter_does_not_execute_a_commit": True,
    "sandboxed_live_memory_commit_adapter_does_not_apply_a_commit": True,
    "sandboxed_live_memory_commit_adapter_does_not_write_live_memory": True,
    "sandboxed_live_memory_commit_adapter_does_not_create_sandboxed_live_memory_commit_adapter": True,
    "sandboxed_live_memory_commit_adapter_does_not_admit_real_memory_roots": True,
    "sandboxed_live_memory_commit_adapter_is_not_lock_acquisition": True,
    "sandboxed_live_memory_commit_adapter_does_not_acquire_locks": True,
    "sandboxed_live_memory_commit_adapter_does_not_create_lockfiles": True,
    "sandboxed_live_memory_commit_adapter_is_not_executor_invocation": True,
    "sandboxed_live_memory_commit_adapter_does_not_invoke_executor": True,
    "sandboxed_live_memory_commit_adapter_is_not_executor_activation": True,
    "sandboxed_live_memory_commit_adapter_does_not_activate_executor": True,
    "sandboxed_live_memory_commit_adapter_is_not_execution_release": True,
    "sandboxed_live_memory_commit_adapter_does_not_release_execution": True,
    "sandboxed_live_memory_commit_adapter_is_not_execution_permit": True,
    "sandboxed_live_memory_commit_adapter_does_not_issue_permit": True,
    "sandboxed_live_memory_commit_adapter_is_not_execution_authorization": True,
    "sandboxed_live_memory_commit_adapter_is_not_permission_to_execute": True,
    "sandboxed_live_memory_commit_adapter_is_not_runtime_enablement": True,
    "sandboxed_live_memory_commit_adapter_does_not_create_a_live_adapter": True,
    "sandboxed_live_memory_commit_adapter_does_not_admit_a_live_adapter": True,
    "sandboxed_live_memory_commit_adapter_readiness_is_metadata_only": True,
    "final_review_gate_confirmation_is_metadata_only": True,
    "live_commit_execution_denial_is_metadata_only": True,
    "live_memory_write_denial_is_metadata_only": True,
    "real_memory_root_admission_deferral_is_metadata_only": True,
    "emergency_stop_confirmation_is_metadata_only": True,
    "rollback_readiness_is_metadata_only": True,
    "verification_readiness_is_metadata_only": True,
    "audit_readiness_is_metadata_only": True,
}
FORBIDDEN_CLAIMS = {
    "sandboxed_live_memory_commit_adapter_passed", "real_memory_root_admission_enabled", "sandboxed_live_memory_commit_adapter_created", "real_memory_root_admitted",
    "live_memory_write_enabled", "live_commit_execution_enabled", "live_commit_executed", "live_commit_applied", "live_commit_apply_enabled",
    "live_adapter_created", "live_adapter_admitted", "live_adapter_admission_enabled", "live_adapter_admission_gate_passed",
    "real_executor_enabled", "real_executor_run_enabled", "real_executor_invoked", "real_executor_invocation_enabled", "real_executor_activation_enabled",
    "real_executor_execution_enabled", "real_executor_execution_authorized", "real_executor_execution_permit_issued", "real_executor_execution_released",
    "real_lock_acquisition_enabled", "real_lock_acquired", "lockfile_creation_enabled", "lockfile_created", "lock_lease_renewal_enabled", "lock_lease_release_enabled",
    "runtime_enabled", "runtime_flag_flipped", "prompt_materialization_enabled", "live_context_retrieval_enabled", "action_execution_enabled",
    "external_disclosure_enabled", "external_service_enabled", "real_memory_root_write_enabled", "real_memory_root_access_enabled",
}
FALSE_FLAGS = {name: False for name in sorted(FORBIDDEN_CLAIMS)}
FUTURE_FLAGS = {"future_sandboxed_live_memory_commit_adapter_gate_required": True, "future_real_live_memory_commit_execution_required": True, "future_post_execution_audit_required": True}
SAFE_NEXT_ACTIONS = ("review_sandboxed_live_memory_commit_adapter_metadata", "prepare_later_sandboxed_live_memory_commit_adapter_metadata_request", "sustain_default_deny")
FORBIDDEN_NEXT_STEPS = tuple(sorted(FORBIDDEN_CLAIMS | {"admit_real_memory_root_now", "create_sandboxed_live_memory_commit_adapter_now", "treat_sandboxed_live_memory_commit_adapter_as_permission_to_execute"}))

@dataclass(frozen=True)
class SandboxedLiveMemoryCommitAdapterFinding:
    severity: str
    code: str
    message: str
    candidate_id: str = ""
    record_id: str = ""
    def to_dict(self) -> dict[str, str]:
        return asdict(self)

@dataclass(frozen=True)
class SandboxedLiveMemoryCommitAdapterPolicy:
    schema_version: str = "sandboxed-live-memory-commit-adapter/v1"
    metadata_only: bool = True
    default_deny: bool = True
    require_scope_alignment: bool = True
    allow_mixed_scope_diagnostic_packet: bool = True
    real_memory_root_admission_enabled: bool = False
    sandboxed_live_memory_commit_adapter_created: bool = False
    live_memory_write_enabled: bool = False
    real_executor_enabled: bool = False
    real_lock_acquisition_enabled: bool = False
    lockfile_creation_enabled: bool = False
    live_adapter_created: bool = False
    live_adapter_admitted: bool = False
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class SandboxedLiveMemoryCommitAdapterCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    operator_scope_keys: tuple[str, ...]
    is_noop: bool
    metadata: Mapping[str, Any]

@dataclass(frozen=True)
class SandboxedLiveMemoryCommitAdapterMetadataRecord:
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
    real_memory_root_admitted: bool = False
    admission_packet_created: bool = False
    live_receipt: bool = False
    rollback_applied: bool = False
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class SandboxedLiveMemoryCommitAdapterRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    sandboxed_live_memory_commit_adapter_decision: SandboxedLiveMemoryCommitAdapterDecision
    final_live_memory_commit_review_gate_digest: str
    final_live_memory_commit_review_gate_decision: str
    carried_evidence: Mapping[str, Mapping[str, str]]
    operator_scope_keys: tuple[str, ...]
    final_review_scope_keys: tuple[str, ...]
    readiness_records: tuple[SandboxedLiveMemoryCommitAdapterMetadataRecord, ...]
    confirmation_records: tuple[SandboxedLiveMemoryCommitAdapterMetadataRecord, ...]
    deferral_records: tuple[SandboxedLiveMemoryCommitAdapterMetadataRecord, ...]
    emergency_stop_records: tuple[SandboxedLiveMemoryCommitAdapterMetadataRecord, ...]
    rollback_records: tuple[SandboxedLiveMemoryCommitAdapterMetadataRecord, ...]
    verification_records: tuple[SandboxedLiveMemoryCommitAdapterMetadataRecord, ...]
    audit_records: tuple[SandboxedLiveMemoryCommitAdapterMetadataRecord, ...]
    safe_next_actions: tuple[str, ...]
    future_sandboxed_live_memory_commit_adapter_gate_required: bool = True
    future_real_live_memory_commit_execution_required: bool = True
    future_post_execution_audit_required: bool = True
    real_memory_root_admission_packet_confirmed_metadata_only: bool = True
    real_memory_root_admission_packet_passed: bool = False
    sandboxed_live_memory_commit_adapter_authority_created: bool = False
    real_memory_root_admission_enabled: bool = False
    sandboxed_live_memory_commit_adapter_created: bool = False
    real_memory_root_admitted: bool = False
    live_memory_write_enabled: bool = False
    live_commit_execution_enabled: bool = False
    live_commit_applied: bool = False
    live_adapter_created: bool = False
    live_adapter_admitted: bool = False
    real_executor_enabled: bool = False
    real_executor_invoked: bool = False
    runtime_enabled: bool = False
    real_lock_acquisition_enabled: bool = False
    real_lock_acquired: bool = False
    lockfile_creation_enabled: bool = False
    lockfile_created: bool = False
    digest: str = ""
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
    def with_digest(self) -> "SandboxedLiveMemoryCommitAdapterRecord":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))

@dataclass(frozen=True)
class SandboxedLiveMemoryCommitAdapter:
    schema_version: str
    records: tuple[SandboxedLiveMemoryCommitAdapterRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["records"] = [record.to_dict() for record in self.records]
        data.update(INVARIANTS)
        data.update(FALSE_FLAGS)
        data.update(FUTURE_FLAGS)
        return data
    def with_digest(self) -> "SandboxedLiveMemoryCommitAdapter":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))

@dataclass(frozen=True)
class SandboxedLiveMemoryCommitAdapterReport:
    status: SandboxedLiveMemoryCommitAdapterStatus
    findings: tuple[SandboxedLiveMemoryCommitAdapterFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""
    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [f.to_dict() for f in self.findings], "summary_counts": dict(self.summary_counts), "digest": self.digest}

@dataclass(frozen=True)
class SandboxedLiveMemoryCommitAdapterResult:
    status: SandboxedLiveMemoryCommitAdapterStatus
    packet: SandboxedLiveMemoryCommitAdapter | None
    report: SandboxedLiveMemoryCommitAdapterReport
    digest: str
    @property
    def gate(self) -> SandboxedLiveMemoryCommitAdapter | None:
        return self.packet
    def to_dict(self) -> dict[str, Any]:
        packet = self.packet.to_dict() if self.packet else None
        return {"status": self.status, "packet": packet, "gate": packet, "report": self.report.to_dict(), "digest": self.digest}

def build_default_policy() -> SandboxedLiveMemoryCommitAdapterPolicy:
    return SandboxedLiveMemoryCommitAdapterPolicy()

def validate_policy(policy: SandboxedLiveMemoryCommitAdapterPolicy | None = None) -> dict[str, Any]:
    active = policy or build_default_policy()
    findings: list[SandboxedLiveMemoryCommitAdapterFinding] = []
    if not active.metadata_only or not active.default_deny:
        findings.append(SandboxedLiveMemoryCommitAdapterFinding("error", "policy_not_metadata_only_default_deny", "policy must remain metadata-only and default-deny"))
    for name in ("real_memory_root_admission_enabled", "sandboxed_live_memory_commit_adapter_created", "live_memory_write_enabled", "real_executor_enabled", "real_lock_acquisition_enabled", "lockfile_creation_enabled", "live_adapter_created", "live_adapter_admitted"):
        if bool(getattr(active, name)):
            findings.append(SandboxedLiveMemoryCommitAdapterFinding("error", name, f"{name} must remain false"))
    return {"status": "valid" if not findings else "invalid", "policy": active.to_dict(), "findings": [f.to_dict() for f in findings]}

def _digest(data: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}

def _as_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()

def _blocked(code: str, findings: Sequence[SandboxedLiveMemoryCommitAdapterFinding] = ()) -> SandboxedLiveMemoryCommitAdapterResult:
    all_findings = tuple(findings) or (SandboxedLiveMemoryCommitAdapterFinding("error", code, code),)
    report = SandboxedLiveMemoryCommitAdapterReport("sandboxed_live_memory_commit_adapter_blocked", all_findings, {"blocked": 1})
    report = replace(report, digest=_digest(report.to_dict()))
    return SandboxedLiveMemoryCommitAdapterResult("sandboxed_live_memory_commit_adapter_blocked", None, report, _digest(report.to_dict()))

def _extract_upstream_gate(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    gate = _as_mapping(payload.get("real_memory_root_admission_packet"))
    if gate.get("gate"):
        gate = _as_mapping(gate.get("gate"))
    records = _as_sequence(gate.get("records"))
    if not records:
        raise ValueError("missing_real_memory_root_admission_packet")
    return gate, _as_mapping(records[0])

def _extract_candidates(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candidates = payload.get("sandboxed_live_memory_commit_adapter_candidates", payload.get("real_root_admission_candidates"))
    if not _as_sequence(candidates):
        raise ValueError("missing_sandboxed_live_memory_commit_adapter_candidate")
    return [_as_mapping(c) for c in _as_sequence(candidates)]

def _candidate(raw: Mapping[str, Any]) -> SandboxedLiveMemoryCommitAdapterCandidate:
    ctype = str(raw.get("candidate_type") or "")
    cid = str(raw.get("candidate_id") or ctype or "candidate")
    rid = str(raw.get("record_id") or cid)
    scope = raw.get("operator_scope_keys") or []
    if not _as_sequence(scope):
        scope = []
    return SandboxedLiveMemoryCommitAdapterCandidate(cid, rid, ctype, tuple(str(s) for s in scope), bool(raw.get("is_noop", False)), _as_mapping(raw.get("metadata")))

def _metadata_record(record_type: str, candidate: SandboxedLiveMemoryCommitAdapterCandidate, metadata: Mapping[str, Any]) -> SandboxedLiveMemoryCommitAdapterMetadataRecord:
    return SandboxedLiveMemoryCommitAdapterMetadataRecord(record_type, candidate.candidate_id, candidate.record_id, _digest(dict(sorted((str(k), v) for k, v in metadata.items()))))

def _carried_evidence(gate: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    carried = _as_mapping(record.get("carried_evidence"))
    evidence: dict[str, dict[str, str]] = {"real_memory_root_admission_packet": {"digest": str(gate.get("digest") or ""), "decision": str(record.get("real_memory_root_admission_packet_decision") or "")}}
    for name, digest_field, decision_field in CARRIED_EVIDENCE_FIELDS[1:]:
        sub = _as_mapping(carried.get(name))
        digest = str(record.get(digest_field) or sub.get("digest") or "")
        decision = str(record.get(decision_field) or sub.get("decision") or "")
        if digest or decision:
            evidence[name] = {"digest": digest, "decision": decision}
    return dict(sorted(evidence.items()))

def _decision(candidate: SandboxedLiveMemoryCommitAdapterCandidate, findings: Sequence[SandboxedLiveMemoryCommitAdapterFinding]) -> SandboxedLiveMemoryCommitAdapterDecision:
    if candidate.is_noop or candidate.candidate_type in {"noop_sandboxed_live_memory_commit_adapter_candidate", "noop_real_root_admission_candidate"}:
        return "sandboxed_live_memory_commit_adapter_noop"
    if candidate.candidate_type in {"operator_review_sandboxed_live_memory_commit_adapter_candidate", "operator_review_real_root_admission_candidate"}:
        return "sandboxed_live_memory_commit_adapter_deferred_for_operator_review"
    if any(f.severity == "warning" for f in findings) or candidate.candidate_type in {"mixed_sandboxed_live_memory_commit_adapter_candidate", "mixed_real_root_admission_candidate"}:
        return "sandboxed_live_memory_commit_adapter_ready_with_warnings"
    return "sandboxed_live_memory_commit_adapter_ready_for_later_sandboxed_live_memory_commit_adapter_gate"

def _safe_actions(decision: str) -> tuple[str, ...]:
    if decision == "sandboxed_live_memory_commit_adapter_noop":
        return ("no_action_allowed", "sustain_default_deny")
    if decision == "sandboxed_live_memory_commit_adapter_deferred_for_operator_review":
        return ("operator_review_required", "sustain_default_deny")
    return SAFE_NEXT_ACTIONS

def _claim(raw: Mapping[str, Any], name: str) -> bool:
    claims = _as_mapping(raw.get("sandboxed_live_memory_commit_adapter_claims", raw.get("admission_claims")))
    return bool(raw.get(name)) or bool(claims.get(name))

def _check_candidate(raw: Mapping[str, Any], candidate: SandboxedLiveMemoryCommitAdapterCandidate, gate: Mapping[str, Any], record: Mapping[str, Any], policy: SandboxedLiveMemoryCommitAdapterPolicy) -> list[SandboxedLiveMemoryCommitAdapterFinding]:
    if candidate.candidate_type not in ALL_CANDIDATE_TYPES:
        return [SandboxedLiveMemoryCommitAdapterFinding("error", "invalid_sandboxed_live_memory_commit_adapter_candidate", "invalid sandboxed live memory commit adapter candidate", candidate.candidate_id, candidate.record_id)]
    for name in sorted(FORBIDDEN_CLAIMS):
        if _claim(raw, name):
            return [SandboxedLiveMemoryCommitAdapterFinding("error", name, f"{name} is forbidden", candidate.candidate_id, candidate.record_id)]
    upstream_digest = str(gate.get("digest") or "")
    upstream_decision = str(record.get("real_memory_root_admission_packet_decision") or "")
    if upstream_decision not in READY_REAL_MEMORY_ROOT_ADMISSION_PACKET_DECISIONS:
        return [SandboxedLiveMemoryCommitAdapterFinding("error", "real_memory_root_admission_packet_not_ready", "real memory root admission packet is not ready", candidate.candidate_id, candidate.record_id)]
    if str(raw.get("claimed_real_memory_root_admission_packet_digest") or raw.get("claimed_upstream_digest") or "") != upstream_digest:
        return [SandboxedLiveMemoryCommitAdapterFinding("error", "real_memory_root_admission_packet_digest_mismatch", "real memory root admission packet digest mismatch", candidate.candidate_id, candidate.record_id)]
    if str(raw.get("claimed_real_memory_root_admission_packet_decision") or raw.get("claimed_upstream_decision") or "") != upstream_decision:
        return [SandboxedLiveMemoryCommitAdapterFinding("error", "real_memory_root_admission_packet_decision_mismatch", "real memory root admission packet decision mismatch", candidate.candidate_id, candidate.record_id)]
    final_scope = tuple(str(s) for s in record.get("operator_scope_keys") or ())
    if policy.require_scope_alignment and final_scope != candidate.operator_scope_keys:
        if candidate.candidate_type in {"mixed_sandboxed_live_memory_commit_adapter_candidate", "mixed_real_root_admission_candidate"} and policy.allow_mixed_scope_diagnostic_packet:
            return [SandboxedLiveMemoryCommitAdapterFinding("warning", "mixed_scope_diagnostic", "mixed candidate scope mismatch is diagnostic only", candidate.candidate_id, candidate.record_id)]
        return [SandboxedLiveMemoryCommitAdapterFinding("error", "scope_mismatch", "candidate scope must match final review gate scope", candidate.candidate_id, candidate.record_id)]
    if not candidate.is_noop and candidate.candidate_type not in {"noop_sandboxed_live_memory_commit_adapter_candidate", "noop_real_root_admission_candidate"}:
        for field in NON_NOOP_METADATA_FIELDS:
            if not _as_mapping(raw.get(field)):
                return [SandboxedLiveMemoryCommitAdapterFinding("error", f"missing_{field}", f"missing required metadata field {field}", candidate.candidate_id, candidate.record_id)]
    carried = _carried_evidence(gate, record)
    for name, digest_field, decision_field in CARRIED_EVIDENCE_FIELDS:
        claimed_digest = str(raw.get(f"claimed_{digest_field}") or "")
        claimed_decision = str(raw.get(f"claimed_{decision_field}") or "")
        actual_digest = str(carried.get(name, {}).get("digest") or "")
        actual_decision = str(carried.get(name, {}).get("decision") or "")
        if actual_digest and claimed_digest and claimed_digest != actual_digest:
            return [SandboxedLiveMemoryCommitAdapterFinding("error", f"{digest_field}_mismatch", f"{name} digest mismatch", candidate.candidate_id, candidate.record_id)]
        if actual_decision and claimed_decision and claimed_decision != actual_decision:
            return [SandboxedLiveMemoryCommitAdapterFinding("error", f"{decision_field}_mismatch", f"{name} decision mismatch", candidate.candidate_id, candidate.record_id)]
    return []

def evaluate_sandboxed_live_memory_commit_adapter(payload: Mapping[str, Any], policy: SandboxedLiveMemoryCommitAdapterPolicy | None = None) -> SandboxedLiveMemoryCommitAdapterResult:
    active_policy = policy or build_default_policy()
    validation = validate_policy(active_policy)
    if validation["status"] != "valid":
        return _blocked("invalid_policy", [SandboxedLiveMemoryCommitAdapterFinding("error", "invalid_policy", "policy failed validation")])
    try:
        gate, upstream = _extract_upstream_gate(payload)
        raw_candidates = _extract_candidates(payload)
        records: list[SandboxedLiveMemoryCommitAdapterRecord] = []
        findings: list[SandboxedLiveMemoryCommitAdapterFinding] = []
        for raw in raw_candidates:
            candidate = _candidate(raw)
            candidate_findings = _check_candidate(raw, candidate, gate, upstream, active_policy)
            if any(f.severity == "error" for f in candidate_findings):
                return _blocked(candidate_findings[0].code, candidate_findings)
            findings.extend(candidate_findings)
            decision = _decision(candidate, candidate_findings)
            records.append(SandboxedLiveMemoryCommitAdapterRecord(
                candidate.candidate_id,
                candidate.record_id,
                candidate.candidate_type,
                decision,
                str(gate.get("digest") or ""),
                str(upstream.get("real_memory_root_admission_packet_decision") or ""),
                _carried_evidence(gate, upstream),
                candidate.operator_scope_keys,
                tuple(str(s) for s in upstream.get("operator_scope_keys") or ()),
                (_metadata_record("real_memory_root_admission_readiness", candidate, _as_mapping(raw.get("sandboxed_adapter_readiness_metadata") or raw.get("metadata"))),),
                tuple(_metadata_record(name.removesuffix("_metadata"), candidate, _as_mapping(raw.get(name) or raw.get("metadata"))) for name in NON_NOOP_METADATA_FIELDS if "confirmation" in name),
                (_metadata_record("real_memory_root_admission_deferral", candidate, _as_mapping(raw.get("real_memory_root_admission_deferral_metadata") or raw.get("metadata"))),),
                (_metadata_record("emergency_stop_confirmation", candidate, _as_mapping(raw.get("emergency_stop_confirmation_metadata") or raw.get("metadata"))),),
                (_metadata_record("rollback_readiness", candidate, _as_mapping(raw.get("rollback_readiness_metadata") or raw.get("metadata"))),),
                (_metadata_record("verification_readiness", candidate, _as_mapping(raw.get("verification_readiness_metadata") or raw.get("metadata"))),),
                (_metadata_record("audit_readiness", candidate, _as_mapping(raw.get("audit_readiness_metadata") or raw.get("metadata"))),),
                _safe_actions(decision),
            ).with_digest())
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for f in findings if f.severity == "warning")}
        for record in records:
            counts[record.sandboxed_live_memory_commit_adapter_decision] = counts.get(record.sandboxed_live_memory_commit_adapter_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {r.sandboxed_live_memory_commit_adapter_decision for r in records}
        if counts["warning_count"] or "sandboxed_live_memory_commit_adapter_ready_with_warnings" in decisions:
            status: SandboxedLiveMemoryCommitAdapterStatus = "sandboxed_live_memory_commit_adapter_ready_with_warnings"
        elif decisions <= {"sandboxed_live_memory_commit_adapter_noop"}:
            status = "sandboxed_live_memory_commit_adapter_noop"
        elif decisions <= {"sandboxed_live_memory_commit_adapter_deferred_for_operator_review"}:
            status = "sandboxed_live_memory_commit_adapter_deferred_for_operator_review"
        else:
            status = "sandboxed_live_memory_commit_adapter_ready"
        out_packet = SandboxedLiveMemoryCommitAdapter(active_policy.schema_version, tuple(records)).with_digest()
        report = SandboxedLiveMemoryCommitAdapterReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return SandboxedLiveMemoryCommitAdapterResult(status, out_packet, report, _digest({"gate": out_packet.to_dict(), "report": report.to_dict()}))
    except ValueError as exc:
        return _blocked(str(exc))
    except Exception as exc:
        return _blocked("failed", [SandboxedLiveMemoryCommitAdapterFinding("error", "failed", str(exc))])

def evaluate_gate(payload: Mapping[str, Any], policy: SandboxedLiveMemoryCommitAdapterPolicy | None = None) -> SandboxedLiveMemoryCommitAdapterResult:
    return evaluate_sandboxed_live_memory_commit_adapter(payload, policy)

def evaluate_packet(payload: Mapping[str, Any], policy: SandboxedLiveMemoryCommitAdapterPolicy | None = None) -> SandboxedLiveMemoryCommitAdapterResult:
    return evaluate_sandboxed_live_memory_commit_adapter(payload, policy)

# Backward-compatible aliases for the preexisting compatibility naming surface.
RealRootAdmissionStatus = SandboxedLiveMemoryCommitAdapterStatus
RealRootAdmissionDecision = SandboxedLiveMemoryCommitAdapterDecision
RealRootAdmissionFinding = SandboxedLiveMemoryCommitAdapterFinding
RealRootAdmissionReport = SandboxedLiveMemoryCommitAdapterReport
RealRootAdmissionResult = SandboxedLiveMemoryCommitAdapterResult
RealMemoryRootAdmissionPolicy = SandboxedLiveMemoryCommitAdapterPolicy

__all__ = [
    "CARRIED_EVIDENCE_FIELDS", "FAIL_STATUSES", "FALSE_FLAGS", "FORBIDDEN_CLAIMS", "FORBIDDEN_NEXT_STEPS", "FUTURE_FLAGS", "INVARIANTS", "NON_NOOP_METADATA_FIELDS",
    "SANDBOXED_LIVE_MEMORY_COMMIT_ADAPTER_CANDIDATE_TYPES", "READY_REAL_MEMORY_ROOT_ADMISSION_PACKET_DECISIONS", "SAFE_NEXT_ACTIONS",
    "SandboxedLiveMemoryCommitAdapter", "SandboxedLiveMemoryCommitAdapterCandidate", "SandboxedLiveMemoryCommitAdapterFinding", "SandboxedLiveMemoryCommitAdapterMetadataRecord",
    "SandboxedLiveMemoryCommitAdapterPolicy", "SandboxedLiveMemoryCommitAdapterRecord", "SandboxedLiveMemoryCommitAdapterReport", "SandboxedLiveMemoryCommitAdapterResult",
    "RealMemoryRootAdmissionPolicy", "RealRootAdmissionFinding", "RealRootAdmissionReport", "RealRootAdmissionResult", "build_default_policy", "evaluate_gate", "evaluate_packet",
    "evaluate_sandboxed_live_memory_commit_adapter", "validate_policy",
]
