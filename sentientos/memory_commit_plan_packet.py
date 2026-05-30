"""Deterministic metadata-only memory commit plan packet.

The packet evaluates explicit JSON metadata from the selective memory
 distillation contract, receipt gate, tomb verifier, governed writer adapter,
and live memory boundary admission gate. It is plan-only: it never writes live
memory, deletes memory, mutates indexes, persists capsules, assembles prompts,
executes actions, invokes remote services, discloses externally, creates policy,
grants authority, infers consent, or asserts truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal, Mapping, Sequence

MemoryCommitPlanStatus = Literal[
    "memory_commit_plan_ready",
    "memory_commit_plan_ready_with_warnings",
    "memory_commit_plan_deferred_for_operator_review",
    "memory_commit_plan_blocked_missing_distillation_packet",
    "memory_commit_plan_blocked_invalid_distillation_packet",
    "memory_commit_plan_blocked_missing_receipt_gate_packet",
    "memory_commit_plan_blocked_invalid_receipt_gate_packet",
    "memory_commit_plan_blocked_missing_tomb_verifier_packet",
    "memory_commit_plan_blocked_invalid_tomb_verifier_packet",
    "memory_commit_plan_blocked_missing_writer_packet",
    "memory_commit_plan_blocked_invalid_writer_packet",
    "memory_commit_plan_blocked_missing_boundary_admission_packet",
    "memory_commit_plan_blocked_invalid_boundary_admission_packet",
    "memory_commit_plan_blocked_missing_plan_candidate",
    "memory_commit_plan_blocked_invalid_plan_candidate",
    "memory_commit_plan_blocked_digest_mismatch",
    "memory_commit_plan_blocked_decision_mismatch",
    "memory_commit_plan_blocked_boundary_not_ready",
    "memory_commit_plan_blocked_writer_not_ready",
    "memory_commit_plan_blocked_tomb_not_verified",
    "memory_commit_plan_blocked_live_write_claim",
    "memory_commit_plan_blocked_live_delete_claim",
    "memory_commit_plan_blocked_index_mutation_claim",
    "memory_commit_plan_blocked_capsule_persistence_claim",
    "memory_commit_plan_blocked_prompt_materialization",
    "memory_commit_plan_blocked_action_execution",
    "memory_commit_plan_blocked_external_disclosure",
    "memory_commit_plan_blocked_authority_smuggling",
    "memory_commit_plan_blocked_raw_payload_leak",
    "memory_commit_plan_blocked_scope_mismatch",
    "memory_commit_plan_invalid",
    "memory_commit_plan_failed",
]

PlanDecision = Literal[
    "commit_plan_ready_for_review",
    "commit_plan_ready_for_review_with_warnings",
    "commit_plan_deferred_for_operator_review",
    "commit_plan_blocked",
    "commit_plan_rejected",
    "commit_plan_noop",
]

PLAN_CANDIDATE_TYPES = frozenset({
    "ai_capsule_commit_plan_candidate",
    "human_summary_commit_plan_candidate",
    "dual_capsule_commit_plan_candidate",
    "protect_receipt_commit_plan_candidate",
    "merge_receipt_commit_plan_candidate",
    "tomb_archive_commit_plan_candidate",
    "tomb_deferred_commit_plan_candidate",
    "operator_review_commit_plan_candidate",
    "noop_commit_plan_candidate",
    "mixed_commit_plan_candidate",
})
TOMB_CANDIDATE_TYPES = frozenset({"tomb_archive_commit_plan_candidate", "tomb_deferred_commit_plan_candidate"})
PLAN_OPERATION_TYPES = frozenset({
    "propose_capsule_commit",
    "propose_summary_commit",
    "propose_dual_capsule_commit",
    "propose_protect_receipt_commit",
    "propose_merge_receipt_commit",
    "propose_tomb_archive_commit",
    "propose_tomb_deferral_commit",
    "propose_operator_review_archive",
    "propose_noop",
    "propose_mixed_commit_plan",
})
READY_WRITER_DECISIONS = frozenset({"writer_preview_ready", "writer_artifact_ready", "writer_artifact_ready_with_warnings"})
NON_BLOCKING_WRITER_DECISIONS = READY_WRITER_DECISIONS | frozenset({"writer_deferred_for_operator_review", "writer_rejected", "writer_noop"})
READY_TOMB_OUTCOMES = frozenset({"tomb_receipt_verified", "tomb_receipt_verified_with_warnings", "tomb_receipt_deferred_for_operator_review", "tomb_receipt_rejected", "tomb_receipt_noop"})
READY_BOUNDARY_DECISIONS = frozenset({"boundary_review_candidate_ready", "boundary_review_candidate_ready_with_warnings", "boundary_review_deferred_for_operator_review", "boundary_review_rejected", "boundary_review_noop"})
SAFE_NEXT_ACTIONS = (
    "no_action_allowed",
    "inspect_commit_plan_packet",
    "operator_review_required",
    "prepare_live_memory_commit_adapter_later",
    "prepare_commit_receipt_schema_later",
    "prepare_rollback_receipt_schema_later",
    "prepare_tomb_archive_adapter_later",
    "prepare_capsule_commit_adapter_later",
    "rerun_with_matching_digest",
    "rerun_with_ready_boundary_admission",
    "rerun_with_ready_writer_packet",
    "rerun_with_verified_tomb_receipt",
    "rerun_with_scope_alignment",
    "sustain_default_deny",
    "defer_to_memory_runtime_boundary",
    "defer_to_self_improvement_ingress",
)
FORBIDDEN_NEXT_STEPS = (
    "write_live_memory_now",
    "delete_live_memory_now",
    "purge_live_memory_now",
    "mutate_raw_fragment",
    "mutate_vector_index",
    "mutate_distilled_memory",
    "persist_capsule_now",
    "persist_summary_now",
    "apply_protection_now",
    "apply_merge_now",
    "complete_tomb_now",
    "execute_commit_plan_now",
    "call_append_memory",
    "call_purge_memory",
    "call_apply_forgetting_curve",
    "call_curate_memory",
    "call_summarize_memory",
    "assemble_prompt_now",
    "retrieve_live_context",
    "execute_action_ingress",
    "infer_truth_from_commit_plan",
    "infer_authority_from_commit_plan",
    "infer_consent_from_commit_plan",
    "convert_commit_plan_to_policy",
    "convert_commit_plan_to_action",
    "bypass_distillation_contract",
    "bypass_receipt_gate",
    "bypass_tomb_verifier",
    "bypass_governed_writer_adapter",
    "bypass_live_boundary_admission",
    "bypass_operator_review",
    "enable_external_disclosure",
)
INVARIANTS: dict[str, bool] = {
    "commit_plan_is_not_memory_write": True,
    "commit_plan_is_not_memory_deletion": True,
    "commit_plan_is_not_index_mutation": True,
    "commit_plan_is_not_capsule_persistence": True,
    "commit_plan_is_not_prompt_assembly": True,
    "commit_plan_is_not_truth": True,
    "commit_plan_is_not_policy": True,
    "commit_plan_is_not_authority": True,
    "commit_plan_is_not_consent": True,
    "commit_plan_does_not_execute_action": True,
    "commit_plan_does_not_disclose_externally": True,
    "live_memory_write_enabled": False,
    "live_memory_deletion_enabled": False,
    "live_index_mutation_enabled": False,
    "capsule_persistence_enabled": False,
    "prompt_materialization_enabled": False,
    "external_disclosure_enabled": False,
    "remote_service_enabled": False,
    "default_deny_live_commit": True,
    "future_commit_adapter_required": True,
    "rollback_expectation_required": True,
    "receipt_expectation_required": True,
}
_RAW_KEYS = frozenset({"raw_payload", "raw_private_payload", "private_payload", "raw_transcript", "transcript", "provider_prompt", "secret", "api_key", "password", "token", "encoded_media", "media_payload", "base64", "image", "audio", "video", "screenshot", "thumbnail"})
_MEDIA_RE = re.compile(r"(?:data:(?:image|audio|video)/|base64|[A-Za-z0-9+/]{120,}={0,2})")
_AUTHORITY_RE = re.compile(r"\b(authority|authorize|grant permission|policy now|consent granted|infer consent|infer authority|infer truth|convert.*policy|approved to act|override blocker|bypass)\b", re.I)
_PROMPT_RE = re.compile(r"\b(assemble prompt|prompt materialization|provider prompt|system prompt|retrieve live context)\b", re.I)
_ACTION_RE = re.compile(r"\b(execute action|action ingress|execute_commit_plan|call_append_memory|call_purge_memory|mutate_vector_index|write_live_memory|delete_live_memory|delete memory|purge_live_memory|apply_forgetting_curve|curate_memory|summarize_memory)\b", re.I)
_EXTERNAL_RE = re.compile(r"\b(external disclosure|send externally|remote service|network egress|provider invocation|upload)\b", re.I)


def _json_data(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json_data(value).encode("utf-8")).hexdigest()


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(str(v) for v in value)
    return (str(value),)


@dataclass(frozen=True)
class MemoryCommitPlanPolicy:
    schema_version: str = "memory-commit-plan-packet.v1"
    default_commit_posture: str = "deny"
    allow_commit_review_plans: bool = True
    allow_warning_plans: bool = True
    allow_operator_review_plans: bool = True
    allow_noop_plans: bool = True
    allow_mixed_scope_diagnostic_packet: bool = False
    require_matching_source_digest: bool = True
    require_receipt_gate_admissible: bool = True
    require_writer_ready: bool = True
    require_boundary_admission_ready: bool = True
    require_tomb_verifier_for_tomb_candidates: bool = True
    require_scope_alignment: bool = True
    require_rollback_expectation: bool = True
    require_receipt_expectation: bool = True
    block_live_write_claims: bool = True
    block_live_delete_claims: bool = True
    block_index_mutation_claims: bool = True
    block_capsule_persistence_claims: bool = True
    block_hard_override_attempts: bool = True


@dataclass(frozen=True)
class MemoryCommitPlanOperation:
    operation_type: str
    target_ref: str
    future_only: bool = True
    applied: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "MemoryCommitPlanOperation":
        return cls(
            operation_type=str(payload["operation_type"]),
            target_ref=str(payload.get("target_ref") or payload.get("record_id") or "future-memory-target"),
            future_only=bool(payload.get("future_only", True)),
            applied=bool(payload.get("applied") or payload.get("performed") or payload.get("completed") or payload.get("executed")),
            metadata=dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata") or {}, Mapping) else {},
        )


@dataclass(frozen=True)
class MemoryCommitPlanRollbackExpectation:
    expectation_id: str
    required: bool = True
    future_receipt_required: bool = True
    rollback_not_performed: bool = True

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "MemoryCommitPlanRollbackExpectation":
        return cls(str(payload.get("expectation_id") or payload.get("id") or "rollback_expectation"), bool(payload.get("required", True)), bool(payload.get("future_receipt_required", True)), bool(payload.get("rollback_not_performed", True)))


@dataclass(frozen=True)
class MemoryCommitPlanReceiptExpectation:
    expectation_id: str
    required: bool = True
    future_receipt_required: bool = True
    receipt_not_written: bool = True

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "MemoryCommitPlanReceiptExpectation":
        return cls(str(payload.get("expectation_id") or payload.get("id") or "receipt_expectation"), bool(payload.get("required", True)), bool(payload.get("future_receipt_required", True)), bool(payload.get("receipt_not_written", True)))


@dataclass(frozen=True)
class MemoryCommitPlanCandidate:
    candidate_id: str
    candidate_type: str
    record_id: str
    source_digest: str
    claimed_distillation_decision: str
    claimed_receipt_gate_decision: str
    claimed_writer_decision: str
    claimed_boundary_admission_decision: str
    claimed_tomb_verifier_outcome: str | None = None
    source_scope_keys: tuple[str, ...] = ()
    operations: tuple[MemoryCommitPlanOperation, ...] = ()
    rollback_expectation: MemoryCommitPlanRollbackExpectation | None = None
    receipt_expectation: MemoryCommitPlanReceiptExpectation | None = None
    requested_next_actions: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    hard_override_requested: bool = False
    prompt_materialization_requested: bool = False
    action_execution_requested: bool = False
    external_disclosure_requested: bool = False
    authority_grant_claimed: bool = False
    policy_creation_claimed: bool = False
    consent_inference_claimed: bool = False
    truth_inference_claimed: bool = False
    live_memory_write_requested: bool = False
    live_memory_deletion_requested: bool = False
    live_index_mutation_requested: bool = False
    capsule_persistence_requested: bool = False
    protection_apply_requested: bool = False
    merge_apply_requested: bool = False
    tomb_completion_requested: bool = False

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "MemoryCommitPlanCandidate":
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, Mapping):
            metadata = {}
        raw_ops = payload.get("operations") or payload.get("plan_operations") or ()
        if isinstance(raw_ops, Mapping):
            raw_ops = (raw_ops,)
        operations: list[MemoryCommitPlanOperation] = []
        if isinstance(raw_ops, Sequence) and not isinstance(raw_ops, (str, bytes, bytearray)):
            for raw in raw_ops:
                if not isinstance(raw, Mapping):
                    raise ValueError("operation must be a mapping")
                operations.append(MemoryCommitPlanOperation.from_mapping(raw))
        else:
            raise ValueError("operations must be a sequence")
        rollback = payload.get("rollback_expectation")
        receipt = payload.get("receipt_expectation")
        return cls(
            candidate_id=str(payload["candidate_id"]),
            candidate_type=str(payload["candidate_type"]),
            record_id=str(payload["record_id"]),
            source_digest=str(payload["source_digest"]),
            claimed_distillation_decision=str(payload["claimed_distillation_decision"]),
            claimed_receipt_gate_decision=str(payload["claimed_receipt_gate_decision"]),
            claimed_writer_decision=str(payload["claimed_writer_decision"]),
            claimed_boundary_admission_decision=str(payload["claimed_boundary_admission_decision"]),
            claimed_tomb_verifier_outcome=str(payload["claimed_tomb_verifier_outcome"]) if payload.get("claimed_tomb_verifier_outcome") is not None else None,
            source_scope_keys=_as_tuple(payload.get("source_scope_keys")),
            operations=tuple(operations),
            rollback_expectation=MemoryCommitPlanRollbackExpectation.from_mapping(rollback) if isinstance(rollback, Mapping) else None,
            receipt_expectation=MemoryCommitPlanReceiptExpectation.from_mapping(receipt) if isinstance(receipt, Mapping) else None,
            requested_next_actions=_as_tuple(payload.get("requested_next_actions")),
            metadata=dict(metadata),
            hard_override_requested=bool(payload.get("hard_override_requested") or payload.get("override_hard_blocker")),
            prompt_materialization_requested=bool(payload.get("prompt_materialization_requested")),
            action_execution_requested=bool(payload.get("action_execution_requested") or payload.get("execute_commit_plan_now")),
            external_disclosure_requested=bool(payload.get("external_disclosure_requested")),
            authority_grant_claimed=bool(payload.get("authority_grant_claimed") or payload.get("grants_authority")),
            policy_creation_claimed=bool(payload.get("policy_creation_claimed") or payload.get("claim_policy_created")),
            consent_inference_claimed=bool(payload.get("consent_inference_claimed") or payload.get("infers_consent")),
            truth_inference_claimed=bool(payload.get("truth_inference_claimed") or payload.get("infers_truth")),
            live_memory_write_requested=bool(payload.get("live_memory_write_requested") or payload.get("write_live_memory_now")),
            live_memory_deletion_requested=bool(payload.get("live_memory_deletion_requested") or payload.get("delete_live_memory_now")),
            live_index_mutation_requested=bool(payload.get("live_index_mutation_requested") or payload.get("index_mutation_requested")),
            capsule_persistence_requested=bool(payload.get("capsule_persistence_requested") or payload.get("persist_capsule_now")),
            protection_apply_requested=bool(payload.get("protection_apply_requested") or payload.get("apply_protection_now")),
            merge_apply_requested=bool(payload.get("merge_apply_requested") or payload.get("apply_merge_now")),
            tomb_completion_requested=bool(payload.get("tomb_completion_requested") or payload.get("complete_tomb_now")),
        )


@dataclass(frozen=True)
class MemoryCommitPlanInput:
    distillation_packet: Mapping[str, Any]
    receipt_gate_packet: Mapping[str, Any]
    writer_packet: Mapping[str, Any]
    boundary_admission_packet: Mapping[str, Any]
    plan_candidates: tuple[MemoryCommitPlanCandidate, ...]
    tomb_verifier_packet: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class MemoryCommitPlanFinding:
    severity: str
    code: str
    message: str
    candidate_id: str | None = None
    record_id: str | None = None


@dataclass(frozen=True)
class MemoryCommitPlanRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    plan_decision: str
    operation_types: tuple[str, ...]
    distillation_decision: str
    receipt_gate_decision: str
    writer_decision: str
    boundary_admission_decision: str
    tomb_verifier_outcome: str | None = None
    safe_next_actions: tuple[str, ...] = ()
    rollback_expectation: MemoryCommitPlanRollbackExpectation | None = None
    receipt_expectation: MemoryCommitPlanReceiptExpectation | None = None
    digest: str = ""

    def with_digest(self) -> "MemoryCommitPlanRecord":
        data = asdict(self)
        data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class MemoryCommitPlanPacket:
    schema_version: str
    records: tuple[MemoryCommitPlanRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        out = {"schema_version": self.schema_version, "records": [asdict(r) for r in self.records], "forbidden_next_steps": list(self.forbidden_next_steps), **INVARIANTS}
        out["digest"] = self.digest
        return out

    def with_digest(self) -> "MemoryCommitPlanPacket":
        data = self.to_dict()
        data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class MemoryCommitPlanReport:
    status: MemoryCommitPlanStatus
    findings: tuple[MemoryCommitPlanFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [asdict(f) for f in self.findings], "summary_counts": dict(self.summary_counts), "digest": self.digest}


@dataclass(frozen=True)
class MemoryCommitPlanResult:
    status: MemoryCommitPlanStatus
    packet: MemoryCommitPlanPacket | None
    report: MemoryCommitPlanReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> MemoryCommitPlanPolicy:
    return MemoryCommitPlanPolicy()


def validate_policy(policy: MemoryCommitPlanPolicy) -> dict[str, Any]:
    findings: list[str] = []
    if policy.default_commit_posture != "deny":
        findings.append("default_commit_posture must be deny")
    if not policy.schema_version:
        findings.append("schema_version is required")
    return {"ok": not findings, "findings": findings, "digest": _digest(asdict(policy))}


def _packet(payload: Mapping[str, Any], primary: str, aliases: tuple[str, ...] = ()) -> Mapping[str, Any] | None:
    for key in (primary, *aliases):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return value
    return None


def _records(packet: Mapping[str, Any], required_fields: tuple[str, ...]) -> dict[str, Mapping[str, Any]] | None:
    raw = packet.get("records")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)) or not raw:
        return None
    out: dict[str, Mapping[str, Any]] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            return None
        record_id = str(item.get("record_id") or "")
        if not record_id or any(not str(item.get(field) or "") for field in required_fields):
            return None
        out[record_id] = item
    return out


def _candidate_payloads(payload: Mapping[str, Any]) -> Sequence[Any] | None:
    raw = payload.get("plan_candidates") or payload.get("plan_candidate") or payload.get("candidate")
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        return (raw,)
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        return raw
    return None


def _contains_forbidden_payload(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in _RAW_KEYS:
                return True
            if _contains_forbidden_payload(child):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_forbidden_payload(child) for child in value)
    elif isinstance(value, str):
        return bool(_MEDIA_RE.search(value))
    return False


def _text(value: Any) -> str:
    try:
        return _json_data(value)
    except TypeError:
        return str(value)


def _blocked(status: MemoryCommitPlanStatus, findings: Sequence[MemoryCommitPlanFinding]) -> MemoryCommitPlanResult:
    counts = {"candidate_count": 0, "warning_count": sum(1 for f in findings if f.severity == "warning"), "error_count": sum(1 for f in findings if f.severity == "error")}
    report = MemoryCommitPlanReport(status, tuple(findings), counts)
    report = replace(report, digest=_digest(report.to_dict()))
    return MemoryCommitPlanResult(status, None, report, _digest({"packet": None, "report": report.to_dict()}))


def _status_for_blocker(blocker: str) -> MemoryCommitPlanStatus:
    mapping: dict[str, MemoryCommitPlanStatus] = {
        "digest_mismatch": "memory_commit_plan_blocked_digest_mismatch",
        "decision_mismatch": "memory_commit_plan_blocked_decision_mismatch",
        "boundary_not_ready": "memory_commit_plan_blocked_boundary_not_ready",
        "writer_not_ready": "memory_commit_plan_blocked_writer_not_ready",
        "tomb_not_verified": "memory_commit_plan_blocked_tomb_not_verified",
        "missing_rollback_expectation": "memory_commit_plan_blocked_invalid_plan_candidate",
        "missing_receipt_expectation": "memory_commit_plan_blocked_invalid_plan_candidate",
        "live_write_claim": "memory_commit_plan_blocked_live_write_claim",
        "live_delete_claim": "memory_commit_plan_blocked_live_delete_claim",
        "index_mutation_claim": "memory_commit_plan_blocked_index_mutation_claim",
        "capsule_persistence_claim": "memory_commit_plan_blocked_capsule_persistence_claim",
        "prompt_materialization": "memory_commit_plan_blocked_prompt_materialization",
        "action_execution": "memory_commit_plan_blocked_action_execution",
        "external_disclosure": "memory_commit_plan_blocked_external_disclosure",
        "authority_smuggling": "memory_commit_plan_blocked_authority_smuggling",
        "raw_payload_leak": "memory_commit_plan_blocked_raw_payload_leak",
        "scope_mismatch": "memory_commit_plan_blocked_scope_mismatch",
    }
    return mapping.get(blocker, "memory_commit_plan_blocked_invalid_plan_candidate")


def _operation_blocker(candidate: MemoryCommitPlanCandidate) -> str | None:
    if not candidate.operations:
        return "invalid_operation"
    for operation in candidate.operations:
        if operation.operation_type not in PLAN_OPERATION_TYPES:
            return "invalid_operation"
        if not operation.future_only or operation.applied:
            return "action_execution"
        if _contains_forbidden_payload(operation.metadata):
            return "raw_payload_leak"
    return None


def _candidate_blocker(candidate: MemoryCommitPlanCandidate, dist: Mapping[str, Any], gate: Mapping[str, Any], writer: Mapping[str, Any], boundary: Mapping[str, Any], tomb: Mapping[str, Any] | None, payload: Mapping[str, Any], policy: MemoryCommitPlanPolicy) -> str | None:
    if _contains_forbidden_payload(candidate.metadata) or _contains_forbidden_payload(payload.get("metadata") or {}):
        return "raw_payload_leak"
    text = _text({"candidate": asdict(candidate), "metadata": payload.get("metadata") or {}})
    if policy.block_hard_override_attempts and (candidate.hard_override_requested or _AUTHORITY_RE.search(text) or candidate.authority_grant_claimed or candidate.policy_creation_claimed or candidate.consent_inference_claimed or candidate.truth_inference_claimed):
        return "authority_smuggling"
    if candidate.prompt_materialization_requested or _PROMPT_RE.search(text):
        return "prompt_materialization"
    if candidate.action_execution_requested or _ACTION_RE.search(text):
        return "action_execution"
    if candidate.external_disclosure_requested or _EXTERNAL_RE.search(text):
        return "external_disclosure"
    if policy.block_live_write_claims and (candidate.live_memory_write_requested or candidate.protection_apply_requested or candidate.merge_apply_requested):
        return "live_write_claim"
    if policy.block_live_delete_claims and (candidate.live_memory_deletion_requested or candidate.tomb_completion_requested):
        return "live_delete_claim"
    if policy.block_index_mutation_claims and candidate.live_index_mutation_requested:
        return "index_mutation_claim"
    if policy.block_capsule_persistence_claims and candidate.capsule_persistence_requested:
        return "capsule_persistence_claim"
    operation_blocker = _operation_blocker(candidate)
    if operation_blocker:
        return operation_blocker
    is_noop = candidate.candidate_type == "noop_commit_plan_candidate"
    if not is_noop and policy.require_rollback_expectation and candidate.rollback_expectation is None:
        return "missing_rollback_expectation"
    if not is_noop and policy.require_receipt_expectation and candidate.receipt_expectation is None:
        return "missing_receipt_expectation"
    if policy.require_scope_alignment and not policy.allow_mixed_scope_diagnostic_packet:
        scopes = [_as_tuple(dist.get("source_scope_keys")), _as_tuple(gate.get("source_scope_keys")), _as_tuple(writer.get("source_scope_keys")), _as_tuple(boundary.get("source_scope_keys")), candidate.source_scope_keys]
        if tomb is not None:
            scopes.append(_as_tuple(tomb.get("source_scope_keys")))
        non_empty = {scope for scope in scopes if scope}
        if len(non_empty) > 1:
            return "scope_mismatch"
    if policy.require_matching_source_digest:
        expected = {str(dist.get("source_digest") or ""), str(gate.get("source_digest") or ""), str(writer.get("source_digest") or ""), str(boundary.get("source_digest") or "")}
        if tomb is not None:
            expected.add(str(tomb.get("source_digest") or ""))
        if not expected or {candidate.source_digest} != expected:
            return "digest_mismatch"
    if candidate.claimed_distillation_decision != str(dist.get("distillation_decision") or ""):
        return "decision_mismatch"
    if candidate.claimed_receipt_gate_decision != str(gate.get("gate_decision") or gate.get("receipt_gate_decision") or ""):
        return "decision_mismatch"
    writer_decision = str(writer.get("writer_decision") or "")
    if candidate.claimed_writer_decision != writer_decision:
        return "decision_mismatch"
    boundary_decision = str(boundary.get("admission_decision") or boundary.get("boundary_admission_decision") or "")
    if candidate.claimed_boundary_admission_decision != boundary_decision:
        return "decision_mismatch"
    if policy.require_writer_ready and writer_decision not in NON_BLOCKING_WRITER_DECISIONS:
        return "writer_not_ready"
    if policy.require_boundary_admission_ready and boundary_decision not in READY_BOUNDARY_DECISIONS:
        return "boundary_not_ready"
    if candidate.candidate_type == "noop_commit_plan_candidate" and boundary_decision != "boundary_review_noop":
        return "decision_mismatch"
    if candidate.candidate_type in {"operator_review_commit_plan_candidate", "tomb_deferred_commit_plan_candidate"} and boundary_decision != "boundary_review_deferred_for_operator_review":
        return "decision_mismatch"
    if candidate.candidate_type not in {"noop_commit_plan_candidate", "operator_review_commit_plan_candidate", "tomb_deferred_commit_plan_candidate"} and boundary_decision not in {"boundary_review_candidate_ready", "boundary_review_candidate_ready_with_warnings", "boundary_review_rejected"}:
        return "boundary_not_ready"
    if candidate.candidate_type in TOMB_CANDIDATE_TYPES:
        if tomb is None:
            return "tomb_not_verified"
        tomb_outcome = str(tomb.get("verification_outcome") or tomb.get("tomb_verifier_outcome") or "")
        if candidate.claimed_tomb_verifier_outcome != tomb_outcome:
            return "decision_mismatch"
        if tomb_outcome not in READY_TOMB_OUTCOMES:
            return "tomb_not_verified"
    return None


def _decision_for(candidate: MemoryCommitPlanCandidate, boundary_decision: str, writer_decision: str, warning: bool) -> PlanDecision:
    if candidate.candidate_type == "noop_commit_plan_candidate" or boundary_decision == "boundary_review_noop" or writer_decision == "writer_noop":
        return "commit_plan_noop"
    if boundary_decision == "boundary_review_rejected" or writer_decision == "writer_rejected":
        return "commit_plan_rejected"
    if candidate.candidate_type in {"operator_review_commit_plan_candidate", "tomb_deferred_commit_plan_candidate"} or boundary_decision == "boundary_review_deferred_for_operator_review" or writer_decision == "writer_deferred_for_operator_review":
        return "commit_plan_deferred_for_operator_review"
    if warning or boundary_decision == "boundary_review_candidate_ready_with_warnings" or writer_decision == "writer_artifact_ready_with_warnings":
        return "commit_plan_ready_for_review_with_warnings"
    return "commit_plan_ready_for_review"


def _safe_actions_for(decision: str, candidate_type: str) -> tuple[str, ...]:
    actions = ["no_action_allowed", "inspect_commit_plan_packet", "sustain_default_deny", "defer_to_memory_runtime_boundary", "defer_to_self_improvement_ingress"]
    if decision == "commit_plan_deferred_for_operator_review":
        actions.append("operator_review_required")
    if decision in {"commit_plan_ready_for_review", "commit_plan_ready_for_review_with_warnings"}:
        actions.extend(["prepare_live_memory_commit_adapter_later", "prepare_commit_receipt_schema_later", "prepare_rollback_receipt_schema_later"])
    if candidate_type in TOMB_CANDIDATE_TYPES:
        actions.append("prepare_tomb_archive_adapter_later")
    elif "capsule" in candidate_type:
        actions.append("prepare_capsule_commit_adapter_later")
    return tuple(dict.fromkeys(actions))


def _policy_from_payload(payload: Mapping[str, Any], policy: MemoryCommitPlanPolicy | None) -> MemoryCommitPlanPolicy:
    if policy is not None:
        return policy
    raw = payload.get("policy")
    if isinstance(raw, Mapping):
        allowed = set(MemoryCommitPlanPolicy.__dataclass_fields__)
        return MemoryCommitPlanPolicy(**{str(k): v for k, v in raw.items() if str(k) in allowed})
    return build_default_policy()


def evaluate_memory_commit_plan_packet(payload: Mapping[str, Any], policy: MemoryCommitPlanPolicy | None = None) -> MemoryCommitPlanResult:
    try:
        active_policy = _policy_from_payload(payload, policy)
        validation = validate_policy(active_policy)
        if not validation["ok"]:
            return _blocked("memory_commit_plan_invalid", [MemoryCommitPlanFinding("error", "invalid_policy", "; ".join(validation["findings"]))])
        if _contains_forbidden_payload(payload):
            return _blocked("memory_commit_plan_blocked_raw_payload_leak", [MemoryCommitPlanFinding("error", "raw_payload_leak", "input contains raw/private/media/secret/provider-prompt payload markers")])
        dist_packet = _packet(payload, "distillation_packet")
        if dist_packet is None:
            return _blocked("memory_commit_plan_blocked_missing_distillation_packet", [MemoryCommitPlanFinding("error", "missing_distillation_packet", "distillation packet is required")])
        dist_records = _records(dist_packet, ("distillation_decision", "source_digest"))
        if dist_records is None:
            return _blocked("memory_commit_plan_blocked_invalid_distillation_packet", [MemoryCommitPlanFinding("error", "invalid_distillation_packet", "distillation packet records are invalid")])
        gate_packet = _packet(payload, "receipt_gate_packet")
        if gate_packet is None:
            return _blocked("memory_commit_plan_blocked_missing_receipt_gate_packet", [MemoryCommitPlanFinding("error", "missing_receipt_gate_packet", "receipt gate packet is required")])
        gate_records = _records(gate_packet, ("source_digest",))
        if gate_records is None or any(not (r.get("gate_decision") or r.get("receipt_gate_decision")) for r in gate_records.values()):
            return _blocked("memory_commit_plan_blocked_invalid_receipt_gate_packet", [MemoryCommitPlanFinding("error", "invalid_receipt_gate_packet", "receipt gate packet records are invalid")])
        writer_packet = _packet(payload, "writer_packet", ("governed_writer_packet",))
        if writer_packet is None:
            return _blocked("memory_commit_plan_blocked_missing_writer_packet", [MemoryCommitPlanFinding("error", "missing_writer_packet", "governed writer packet is required")])
        writer_records = _records(writer_packet, ("writer_decision", "source_digest"))
        if writer_records is None:
            return _blocked("memory_commit_plan_blocked_invalid_writer_packet", [MemoryCommitPlanFinding("error", "invalid_writer_packet", "writer packet records are invalid")])
        boundary_packet = _packet(payload, "boundary_admission_packet", ("live_boundary_admission_packet",))
        if boundary_packet is None:
            return _blocked("memory_commit_plan_blocked_missing_boundary_admission_packet", [MemoryCommitPlanFinding("error", "missing_boundary_admission_packet", "boundary admission packet is required")])
        boundary_records = _records(boundary_packet, ("source_digest",))
        if boundary_records is None or any(not (r.get("admission_decision") or r.get("boundary_admission_decision")) for r in boundary_records.values()):
            return _blocked("memory_commit_plan_blocked_invalid_boundary_admission_packet", [MemoryCommitPlanFinding("error", "invalid_boundary_admission_packet", "boundary admission packet records are invalid")])
        raw_candidates = _candidate_payloads(payload)
        if raw_candidates is None or not raw_candidates:
            return _blocked("memory_commit_plan_blocked_missing_plan_candidate", [MemoryCommitPlanFinding("error", "missing_plan_candidate", "plan candidate is required")])
        candidates: list[MemoryCommitPlanCandidate] = []
        needs_tomb = False
        for raw in raw_candidates:
            if not isinstance(raw, Mapping):
                return _blocked("memory_commit_plan_blocked_invalid_plan_candidate", [MemoryCommitPlanFinding("error", "invalid_plan_candidate", "candidate must be a mapping")])
            try:
                candidate = MemoryCommitPlanCandidate.from_mapping(raw)
            except (KeyError, TypeError, ValueError) as exc:
                return _blocked("memory_commit_plan_blocked_invalid_plan_candidate", [MemoryCommitPlanFinding("error", "invalid_plan_candidate", str(exc))])
            if candidate.candidate_type not in PLAN_CANDIDATE_TYPES:
                return _blocked("memory_commit_plan_blocked_invalid_plan_candidate", [MemoryCommitPlanFinding("error", "invalid_plan_candidate", "unknown candidate type", candidate.candidate_id, candidate.record_id)])
            needs_tomb = needs_tomb or candidate.candidate_type in TOMB_CANDIDATE_TYPES
            candidates.append(candidate)
        tomb_records: dict[str, Mapping[str, Any]] = {}
        tomb_packet = _packet(payload, "tomb_verifier_packet")
        if needs_tomb and active_policy.require_tomb_verifier_for_tomb_candidates:
            if tomb_packet is None:
                return _blocked("memory_commit_plan_blocked_missing_tomb_verifier_packet", [MemoryCommitPlanFinding("error", "missing_tomb_verifier_packet", "tomb verifier packet is required for tomb candidates")])
            parsed_tomb = _records(tomb_packet, ("source_digest",))
            if parsed_tomb is None or any(not (r.get("verification_outcome") or r.get("tomb_verifier_outcome")) for r in parsed_tomb.values()):
                return _blocked("memory_commit_plan_blocked_invalid_tomb_verifier_packet", [MemoryCommitPlanFinding("error", "invalid_tomb_verifier_packet", "tomb verifier packet records are invalid")])
            tomb_records = parsed_tomb
        findings: list[MemoryCommitPlanFinding] = []
        scope_sets = {_as_tuple(r.get("source_scope_keys")) for packet_records in (dist_records, gate_records, writer_records, boundary_records, tomb_records) for r in packet_records.values() if _as_tuple(r.get("source_scope_keys"))}
        mixed_scope_warning = False
        if len(scope_sets) > 1:
            if active_policy.allow_mixed_scope_diagnostic_packet:
                findings.append(MemoryCommitPlanFinding("warning", "mixed_scope_diagnostic_packet", "packet contains multiple source scopes"))
                mixed_scope_warning = True
            elif active_policy.require_scope_alignment:
                findings.append(MemoryCommitPlanFinding("error", "scope_mismatch", "packet contains multiple source scopes"))
                return _blocked("memory_commit_plan_blocked_scope_mismatch", findings)
        records: list[MemoryCommitPlanRecord] = []
        for candidate in candidates:
            dist = dist_records.get(candidate.record_id)
            gate = gate_records.get(candidate.record_id)
            writer = writer_records.get(candidate.record_id)
            boundary = boundary_records.get(candidate.record_id)
            tomb = tomb_records.get(candidate.record_id) if tomb_records else None
            if dist is None or gate is None or writer is None or boundary is None:
                return _blocked("memory_commit_plan_blocked_invalid_plan_candidate", [MemoryCommitPlanFinding("error", "invalid_plan_candidate", "candidate references unknown upstream evidence", candidate.candidate_id, candidate.record_id)])
            blocker = _candidate_blocker(candidate, dist, gate, writer, boundary, tomb, payload, active_policy)
            if blocker:
                findings.append(MemoryCommitPlanFinding("error", blocker, f"plan candidate blocked: {blocker}", candidate.candidate_id, candidate.record_id))
                return _blocked(_status_for_blocker(blocker), findings)
            boundary_decision = str(boundary.get("admission_decision") or boundary.get("boundary_admission_decision") or "")
            writer_decision = str(writer.get("writer_decision") or "")
            warning = mixed_scope_warning or bool(candidate.metadata.get("warning_only") or candidate.metadata.get("diagnostic_warning")) or boundary_decision == "boundary_review_candidate_ready_with_warnings" or writer_decision == "writer_artifact_ready_with_warnings"
            if warning:
                findings.append(MemoryCommitPlanFinding("warning", "commit_plan_warning", "candidate is warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
            decision = _decision_for(candidate, boundary_decision, writer_decision, warning)
            record = MemoryCommitPlanRecord(
                candidate_id=candidate.candidate_id,
                record_id=candidate.record_id,
                candidate_type=candidate.candidate_type,
                plan_decision=decision,
                operation_types=tuple(op.operation_type for op in candidate.operations),
                distillation_decision=str(dist.get("distillation_decision") or ""),
                receipt_gate_decision=str(gate.get("gate_decision") or gate.get("receipt_gate_decision") or ""),
                writer_decision=writer_decision,
                boundary_admission_decision=boundary_decision,
                tomb_verifier_outcome=str(tomb.get("verification_outcome") or tomb.get("tomb_verifier_outcome") or "") if tomb is not None else None,
                safe_next_actions=_safe_actions_for(decision, candidate.candidate_type),
                rollback_expectation=candidate.rollback_expectation,
                receipt_expectation=candidate.receipt_expectation,
            ).with_digest()
            records.append(record)
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for f in findings if f.severity == "warning")}
        for rec in records:
            counts[rec.plan_decision] = counts.get(rec.plan_decision, 0) + 1
            counts[rec.candidate_type] = counts.get(rec.candidate_type, 0) + 1
            for op_type in rec.operation_types:
                counts[op_type] = counts.get(op_type, 0) + 1
        decisions = {rec.plan_decision for rec in records}
        if counts["warning_count"]:
            status: MemoryCommitPlanStatus = "memory_commit_plan_ready_with_warnings"
        elif decisions <= {"commit_plan_deferred_for_operator_review"}:
            status = "memory_commit_plan_deferred_for_operator_review"
        elif decisions <= {"commit_plan_noop"}:
            status = "memory_commit_plan_ready"
        elif decisions <= {"commit_plan_rejected"}:
            status = "memory_commit_plan_deferred_for_operator_review"
        else:
            status = "memory_commit_plan_ready"
        packet = MemoryCommitPlanPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = MemoryCommitPlanReport(status, tuple(findings), dict(sorted(counts.items())), "")
        report = replace(report, digest=_digest(report.to_dict()))
        return MemoryCommitPlanResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("memory_commit_plan_failed", [MemoryCommitPlanFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: MemoryCommitPlanPolicy | None = None) -> MemoryCommitPlanResult:
    return evaluate_memory_commit_plan_packet(payload, policy)


__all__ = [
    "FORBIDDEN_NEXT_STEPS",
    "INVARIANTS",
    "PLAN_CANDIDATE_TYPES",
    "PLAN_OPERATION_TYPES",
    "SAFE_NEXT_ACTIONS",
    "MemoryCommitPlanPolicy",
    "MemoryCommitPlanInput",
    "MemoryCommitPlanCandidate",
    "MemoryCommitPlanFinding",
    "MemoryCommitPlanOperation",
    "MemoryCommitPlanRollbackExpectation",
    "MemoryCommitPlanReceiptExpectation",
    "MemoryCommitPlanRecord",
    "MemoryCommitPlanPacket",
    "MemoryCommitPlanReport",
    "MemoryCommitPlanResult",
    "build_default_policy",
    "validate_policy",
    "evaluate_memory_commit_plan_packet",
    "evaluate_packet",
]
