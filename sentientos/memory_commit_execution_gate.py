"""Deterministic metadata-only memory commit execution gate.

The gate evaluates explicit JSON metadata from a memory commit plan packet,
a memory commit operator approval packet, and execution-gate candidates. It is
only an eligibility gate for a possible future live memory commit adapter: it
never writes or deletes memory, mutates indexes, persists capsules, assembles
prompts, executes approvals or commit plans, invokes remote services, discloses
externally, creates policy, grants authority, infers consent, or asserts truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal, Mapping, Sequence

MemoryCommitExecutionGateStatus = Literal[
    "memory_commit_execution_gate_ready",
    "memory_commit_execution_gate_ready_with_warnings",
    "memory_commit_execution_gate_deferred_for_operator_review",
    "memory_commit_execution_gate_rejected",
    "memory_commit_execution_gate_noop",
    "memory_commit_execution_gate_blocked_missing_commit_plan_packet",
    "memory_commit_execution_gate_blocked_invalid_commit_plan_packet",
    "memory_commit_execution_gate_blocked_missing_operator_approval_packet",
    "memory_commit_execution_gate_blocked_invalid_operator_approval_packet",
    "memory_commit_execution_gate_blocked_missing_execution_candidate",
    "memory_commit_execution_gate_blocked_invalid_execution_candidate",
    "memory_commit_execution_gate_blocked_plan_not_ready",
    "memory_commit_execution_gate_blocked_approval_not_ready",
    "memory_commit_execution_gate_blocked_plan_digest_mismatch",
    "memory_commit_execution_gate_blocked_approval_digest_mismatch",
    "memory_commit_execution_gate_blocked_plan_decision_mismatch",
    "memory_commit_execution_gate_blocked_approval_decision_mismatch",
    "memory_commit_execution_gate_blocked_missing_gate_precondition",
    "memory_commit_execution_gate_blocked_precondition_mismatch",
    "memory_commit_execution_gate_blocked_missing_operator_scope",
    "memory_commit_execution_gate_blocked_scope_mismatch",
    "memory_commit_execution_gate_blocked_missing_rollback_expectation",
    "memory_commit_execution_gate_blocked_missing_receipt_expectation",
    "memory_commit_execution_gate_blocked_execution_overclaim",
    "memory_commit_execution_gate_blocked_execution_claim",
    "memory_commit_execution_gate_blocked_live_write_claim",
    "memory_commit_execution_gate_blocked_live_delete_claim",
    "memory_commit_execution_gate_blocked_index_mutation_claim",
    "memory_commit_execution_gate_blocked_capsule_persistence_claim",
    "memory_commit_execution_gate_blocked_prompt_materialization",
    "memory_commit_execution_gate_blocked_action_execution",
    "memory_commit_execution_gate_blocked_external_disclosure",
    "memory_commit_execution_gate_blocked_authority_smuggling",
    "memory_commit_execution_gate_blocked_raw_payload_leak",
    "memory_commit_execution_gate_invalid",
    "memory_commit_execution_gate_failed",
]

ExecutionGateDecision = Literal[
    "commit_execution_eligible_for_future_adapter",
    "commit_execution_eligible_for_future_adapter_with_warnings",
    "commit_execution_deferred_for_operator_review",
    "commit_execution_rejected",
    "commit_execution_blocked",
    "commit_execution_noop",
]

EXECUTION_CANDIDATE_TYPES = frozenset({
    "ai_capsule_commit_execution_candidate",
    "human_summary_commit_execution_candidate",
    "dual_capsule_commit_execution_candidate",
    "protect_receipt_commit_execution_candidate",
    "merge_receipt_commit_execution_candidate",
    "tomb_archive_commit_execution_candidate",
    "tomb_deferred_commit_execution_candidate",
    "operator_review_commit_execution_candidate",
    "noop_commit_execution_candidate",
    "warning_commit_execution_candidate",
    "mixed_commit_execution_candidate",
    "rejected_commit_execution_candidate",
})

READY_PLAN_DECISIONS = frozenset({
    "commit_plan_ready_for_review",
    "commit_plan_ready_for_review_with_warnings",
    "commit_plan_deferred_for_operator_review",
    "commit_plan_rejected",
    "commit_plan_noop",
})
READY_APPROVAL_DECISIONS = frozenset({
    "commit_approval_ready_for_future_adapter",
    "commit_approval_ready_for_future_adapter_with_warnings",
    "commit_approval_deferred_for_operator_review",
    "commit_approval_rejected",
    "commit_approval_noop",
})

SAFE_NEXT_ACTIONS = (
    "no_action_allowed",
    "inspect_memory_commit_execution_gate_packet",
    "operator_review_required",
    "prepare_live_memory_commit_adapter_later",
    "prepare_live_memory_dry_run_later",
    "prepare_commit_receipt_schema_later",
    "prepare_rollback_receipt_schema_later",
    "rerun_with_ready_commit_plan",
    "rerun_with_ready_operator_approval",
    "rerun_with_matching_plan_digest",
    "rerun_with_matching_approval_digest",
    "rerun_with_matching_decisions",
    "rerun_with_gate_preconditions",
    "rerun_with_operator_scope",
    "rerun_with_rollback_expectation",
    "rerun_with_receipt_expectation",
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
    "run_live_commit_now",
    "execute_commit_plan_now",
    "execute_operator_approval_now",
    "execute_memory_commit_execution_gate_now",
    "treat_gate_as_execution",
    "call_append_memory",
    "call_purge_memory",
    "call_apply_forgetting_curve",
    "call_curate_memory",
    "call_summarize_memory",
    "assemble_prompt_now",
    "retrieve_live_context",
    "execute_action_ingress",
    "infer_truth_from_execution_gate",
    "infer_authority_from_execution_gate",
    "infer_consent_from_execution_gate",
    "convert_execution_gate_to_policy",
    "convert_execution_gate_to_action",
    "bypass_commit_plan_packet",
    "bypass_operator_approval_packet",
    "bypass_live_boundary_admission",
    "bypass_governed_memory_writer_adapter",
    "bypass_tomb_verifier",
    "bypass_receipt_gate",
    "bypass_distillation_contract",
    "bypass_operator_review",
    "enable_external_disclosure",
)

INVARIANTS: dict[str, bool] = {
    "execution_gate_is_not_memory_write": True,
    "execution_gate_is_not_memory_deletion": True,
    "execution_gate_is_not_index_mutation": True,
    "execution_gate_is_not_capsule_persistence": True,
    "execution_gate_is_not_prompt_assembly": True,
    "execution_gate_is_not_execution": True,
    "execution_gate_is_not_live_commit": True,
    "execution_gate_is_not_truth": True,
    "execution_gate_is_not_policy": True,
    "execution_gate_is_not_authority": True,
    "execution_gate_is_not_consent": True,
    "execution_gate_does_not_execute_action": True,
    "execution_gate_does_not_disclose_externally": True,
    "live_memory_write_enabled": False,
    "live_memory_deletion_enabled": False,
    "live_index_mutation_enabled": False,
    "capsule_persistence_enabled": False,
    "prompt_materialization_enabled": False,
    "external_disclosure_enabled": False,
    "remote_service_enabled": False,
    "default_deny_live_commit": True,
    "future_commit_adapter_required": True,
    "future_live_dry_run_required": True,
    "rollback_expectation_required": True,
    "receipt_expectation_required": True,
    "operator_approval_required": True,
}

RAW_PAYLOAD_KEYS = frozenset({"raw_payload", "raw_transcript", "transcript", "secret", "secrets", "provider_prompt", "prompt", "image", "audio", "video", "screenshot", "thumbnail", "encoded_media", "base64_media", "private_payload"})
RAW_PAYLOAD_PATTERN = re.compile(r"(data:image|data:audio|data:video|begin private|provider prompt|secret-token|-----BEGIN|/home/|real operator home)", re.I)


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return tuple(str(item) for item in value)
    return ()


def _has_raw_payload(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in RAW_PAYLOAD_KEYS:
                return True
            if _has_raw_payload(item):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return any(_has_raw_payload(item) for item in value)
    elif isinstance(value, str):
        return bool(RAW_PAYLOAD_PATTERN.search(value))
    return False


@dataclass(frozen=True)
class MemoryCommitExecutionGatePolicy:
    schema_version: str = "memory-commit-execution-gate.v1"
    default_execution_posture: str = "deny"
    allow_future_adapter_eligibility: bool = True
    allow_warning_eligibility: bool = True
    allow_operator_review_deferrals: bool = True
    allow_noop: bool = True
    allow_rejections: bool = True
    allow_mixed_scope_diagnostic_packet: bool = False
    allow_missing_scope_diagnostic_warning: bool = False
    require_commit_plan_ready: bool = True
    require_operator_approval_ready: bool = True
    require_matching_plan_digest: bool = True
    require_matching_approval_digest: bool = True
    require_matching_plan_decision: bool = True
    require_matching_approval_decision: bool = True
    require_gate_preconditions: bool = True
    require_operator_scope: bool = True
    require_scope_alignment: bool = True
    require_rollback_expectation: bool = True
    require_receipt_expectation: bool = True
    block_execution_overclaims: bool = True
    block_execution_claims: bool = True
    block_live_write_claims: bool = True
    block_live_delete_claims: bool = True
    block_index_mutation_claims: bool = True
    block_capsule_persistence_claims: bool = True
    required_preconditions: tuple[str, ...] = ("default_deny_live_commit", "future_commit_adapter_required", "future_live_dry_run_required", "operator_approval_required")


@dataclass(frozen=True)
class MemoryCommitExecutionGateInput:
    commit_plan_packet: Mapping[str, Any]
    operator_approval_packet: Mapping[str, Any]
    execution_candidates: tuple[Mapping[str, Any], ...]
    policy: MemoryCommitExecutionGatePolicy = field(default_factory=MemoryCommitExecutionGatePolicy)


@dataclass(frozen=True)
class MemoryCommitExecutionGateFinding:
    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    candidate_id: str | None = None
    record_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemoryCommitExecutionGatePrecondition:
    key: str
    expected: bool = True
    actual: bool = True

    def satisfied(self) -> bool:
        return self.actual is self.expected

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemoryCommitExecutionGateCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    claimed_plan_digest: str
    claimed_approval_digest: str
    claimed_plan_decision: str
    claimed_approval_decision: str
    operator_scope_keys: tuple[str, ...]
    gate_preconditions: Mapping[str, Any]
    rollback_expectation: Mapping[str, Any]
    receipt_expectation: Mapping[str, Any]
    execution_claims: Mapping[str, Any]
    metadata: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "MemoryCommitExecutionGateCandidate | None":
        candidate_type = str(raw.get("candidate_type") or "")
        candidate_id = str(raw.get("candidate_id") or "")
        record_id = str(raw.get("record_id") or "")
        if not candidate_id or not record_id or candidate_type not in EXECUTION_CANDIDATE_TYPES:
            return None
        return cls(
            candidate_id=candidate_id,
            record_id=record_id,
            candidate_type=candidate_type,
            claimed_plan_digest=str(raw.get("claimed_plan_digest") or raw.get("plan_digest") or ""),
            claimed_approval_digest=str(raw.get("claimed_approval_digest") or raw.get("approval_digest") or ""),
            claimed_plan_decision=str(raw.get("claimed_plan_decision") or raw.get("plan_decision") or ""),
            claimed_approval_decision=str(raw.get("claimed_approval_decision") or raw.get("approval_decision") or ""),
            operator_scope_keys=_as_tuple(raw.get("operator_scope_keys") or _as_mapping(raw.get("operator_scope")).get("operator_scope_keys")),
            gate_preconditions=_as_mapping(raw.get("gate_preconditions")),
            rollback_expectation=_as_mapping(raw.get("rollback_expectation")),
            receipt_expectation=_as_mapping(raw.get("receipt_expectation")),
            execution_claims=_as_mapping(raw.get("execution_claims")),
            metadata=_as_mapping(raw.get("metadata")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemoryCommitExecutionGateRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    execution_decision: ExecutionGateDecision
    plan_decision: str
    approval_decision: str
    plan_digest: str
    approval_digest: str
    operator_scope_keys: tuple[str, ...]
    approval_scope_keys: tuple[str, ...]
    gate_preconditions: tuple[MemoryCommitExecutionGatePrecondition, ...]
    safe_next_actions: tuple[str, ...]
    rollback_expectation: Mapping[str, Any]
    receipt_expectation: Mapping[str, Any]
    execution_gate_future_consideration_only: bool = True
    execution_overclaim_detected: bool = False
    execution_claimed: bool = False
    live_memory_write_claimed: bool = False
    live_memory_delete_claimed: bool = False
    index_mutation_claimed: bool = False
    capsule_persistence_claimed: bool = False
    policy_authority_claimed: bool = False
    truth_claimed: bool = False
    consent_claimed: bool = False
    prompt_assembly_claimed: bool = False
    action_execution_claimed: bool = False
    external_disclosure_claimed: bool = False
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["gate_preconditions"] = [precondition.to_dict() for precondition in self.gate_preconditions]
        return data

    def with_digest(self) -> "MemoryCommitExecutionGateRecord":
        data = self.to_dict()
        data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class MemoryCommitExecutionGatePacket:
    schema_version: str
    records: tuple[MemoryCommitExecutionGateRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""
    execution_gate_is_not_memory_write: bool = True
    execution_gate_is_not_memory_deletion: bool = True
    execution_gate_is_not_index_mutation: bool = True
    execution_gate_is_not_capsule_persistence: bool = True
    execution_gate_is_not_prompt_assembly: bool = True
    execution_gate_is_not_execution: bool = True
    execution_gate_is_not_live_commit: bool = True
    execution_gate_is_not_truth: bool = True
    execution_gate_is_not_policy: bool = True
    execution_gate_is_not_authority: bool = True
    execution_gate_is_not_consent: bool = True
    execution_gate_does_not_execute_action: bool = True
    execution_gate_does_not_disclose_externally: bool = True
    live_memory_write_enabled: bool = False
    live_memory_deletion_enabled: bool = False
    live_index_mutation_enabled: bool = False
    capsule_persistence_enabled: bool = False
    prompt_materialization_enabled: bool = False
    external_disclosure_enabled: bool = False
    remote_service_enabled: bool = False
    default_deny_live_commit: bool = True
    future_commit_adapter_required: bool = True
    future_live_dry_run_required: bool = True
    rollback_expectation_required: bool = True
    receipt_expectation_required: bool = True
    operator_approval_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["records"] = [record.to_dict() for record in self.records]
        return data

    def with_digest(self) -> "MemoryCommitExecutionGatePacket":
        data = self.to_dict()
        data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class MemoryCommitExecutionGateReport:
    status: MemoryCommitExecutionGateStatus
    findings: tuple[MemoryCommitExecutionGateFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [finding.to_dict() for finding in self.findings], "summary_counts": dict(sorted(self.summary_counts.items())), "digest": self.digest}


@dataclass(frozen=True)
class MemoryCommitExecutionGateResult:
    status: MemoryCommitExecutionGateStatus
    packet: MemoryCommitExecutionGatePacket | None
    report: MemoryCommitExecutionGateReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> MemoryCommitExecutionGatePolicy:
    return MemoryCommitExecutionGatePolicy()


def validate_policy(policy: MemoryCommitExecutionGatePolicy | Mapping[str, Any]) -> dict[str, Any]:
    raw = asdict(policy) if isinstance(policy, MemoryCommitExecutionGatePolicy) else dict(policy)
    findings: list[dict[str, str]] = []
    if raw.get("default_execution_posture") != "deny":
        findings.append({"severity": "error", "code": "default_execution_posture_not_deny", "message": "execution gate must default deny"})
    for key, expected in INVARIANTS.items():
        if raw.get(key, expected) != expected:
            findings.append({"severity": "error", "code": f"invariant_{key}_changed", "message": f"{key} must remain {expected}"})
    status = "invalid" if findings else "valid"
    return {"status": status, "findings": findings, "policy": raw, "digest": _digest({"findings": findings, "policy": raw, "status": status})}


def _packet_records(packet: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    records = packet.get("records")
    if isinstance(records, Sequence) and not isinstance(records, (bytes, bytearray, str)):
        return tuple(item for item in records if isinstance(item, Mapping))
    return ()


def _first_record(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    records = _packet_records(packet)
    return records[0] if records else {}


def _input_candidates(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = payload.get("execution_candidates", payload.get("execution_candidate"))
    if isinstance(raw, Mapping):
        return (raw,)
    if isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray, str)):
        return tuple(item for item in raw if isinstance(item, Mapping))
    return ()


def _policy_from_payload(payload: Mapping[str, Any], policy: MemoryCommitExecutionGatePolicy | None) -> MemoryCommitExecutionGatePolicy:
    if policy is not None:
        return policy
    raw = payload.get("policy")
    if isinstance(raw, Mapping):
        allowed = set(MemoryCommitExecutionGatePolicy.__dataclass_fields__)
        values = {str(k): v for k, v in raw.items() if str(k) in allowed}
        if "required_preconditions" in values:
            values["required_preconditions"] = _as_tuple(values["required_preconditions"])
        return MemoryCommitExecutionGatePolicy(**values)
    return build_default_policy()


def _blocked(status: MemoryCommitExecutionGateStatus, findings: Sequence[MemoryCommitExecutionGateFinding]) -> MemoryCommitExecutionGateResult:
    report = MemoryCommitExecutionGateReport(status, tuple(findings), {"candidate_count": 0, "error_count": sum(1 for f in findings if f.severity == "error")})
    report = replace(report, digest=_digest(report.to_dict()))
    return MemoryCommitExecutionGateResult(status, None, report, _digest({"packet": None, "report": report.to_dict()}))


def _flag(claims: Mapping[str, Any], *names: str) -> bool:
    return any(claims.get(name) is True for name in names)


def _blocker_for_claims(candidate: MemoryCommitExecutionGateCandidate, policy: MemoryCommitExecutionGatePolicy) -> MemoryCommitExecutionGateStatus | None:
    claims = candidate.execution_claims
    metadata = candidate.metadata
    if _has_raw_payload(candidate.to_dict()):
        return "memory_commit_execution_gate_blocked_raw_payload_leak"
    if policy.block_execution_overclaims and _flag(claims, "execution_overclaim", "overclaims_execution", "future_adapter_not_required"):
        return "memory_commit_execution_gate_blocked_execution_overclaim"
    if policy.block_execution_claims and _flag(claims, "execution", "executes", "live_commit", "runs_live_commit", "executes_commit_plan", "executes_operator_approval"):
        return "memory_commit_execution_gate_blocked_execution_claim"
    if policy.block_live_write_claims and _flag(claims, "live_memory_write", "writes_memory", "write_live_memory"):
        return "memory_commit_execution_gate_blocked_live_write_claim"
    if policy.block_live_delete_claims and _flag(claims, "live_memory_delete", "deletes_memory", "purges_memory"):
        return "memory_commit_execution_gate_blocked_live_delete_claim"
    if policy.block_index_mutation_claims and _flag(claims, "index_mutation", "mutates_index", "vector_index_mutation"):
        return "memory_commit_execution_gate_blocked_index_mutation_claim"
    if policy.block_capsule_persistence_claims and _flag(claims, "capsule_persistence", "persists_capsule", "persist_capsule"):
        return "memory_commit_execution_gate_blocked_capsule_persistence_claim"
    if _flag(claims, "prompt_materialization", "prompt_assembly", "assembles_prompt"):
        return "memory_commit_execution_gate_blocked_prompt_materialization"
    if _flag(claims, "action_execution", "executes_action", "action_ingress"):
        return "memory_commit_execution_gate_blocked_action_execution"
    if _flag(claims, "external_disclosure", "discloses_externally", "remote_service"):
        return "memory_commit_execution_gate_blocked_external_disclosure"
    if _flag(claims, "authority", "policy_authority", "truth", "consent") or metadata.get("authority_smuggling") is True:
        return "memory_commit_execution_gate_blocked_authority_smuggling"
    return None


def _status_for_blocker(status: MemoryCommitExecutionGateStatus, candidate: MemoryCommitExecutionGateCandidate | None = None) -> MemoryCommitExecutionGateFinding:
    code = status.removeprefix("memory_commit_execution_gate_blocked_")
    return MemoryCommitExecutionGateFinding("error", code, code.replace("_", " "), candidate.candidate_id if candidate else None, candidate.record_id if candidate else None)


def _decision_for(candidate: MemoryCommitExecutionGateCandidate, plan_decision: str, approval_decision: str, warning: bool) -> ExecutionGateDecision:
    if candidate.candidate_type == "noop_commit_execution_candidate" or plan_decision == "commit_plan_noop" or approval_decision == "commit_approval_noop":
        return "commit_execution_noop"
    if candidate.candidate_type == "rejected_commit_execution_candidate" or plan_decision == "commit_plan_rejected" or approval_decision == "commit_approval_rejected":
        return "commit_execution_rejected"
    if candidate.candidate_type in {"tomb_deferred_commit_execution_candidate", "operator_review_commit_execution_candidate"} or plan_decision == "commit_plan_deferred_for_operator_review" or approval_decision == "commit_approval_deferred_for_operator_review":
        return "commit_execution_deferred_for_operator_review"
    if warning or candidate.candidate_type in {"warning_commit_execution_candidate", "mixed_commit_execution_candidate"}:
        return "commit_execution_eligible_for_future_adapter_with_warnings"
    return "commit_execution_eligible_for_future_adapter"


def _safe_actions(decision: str) -> tuple[str, ...]:
    actions = ["no_action_allowed", "inspect_memory_commit_execution_gate_packet", "sustain_default_deny"]
    if decision == "commit_execution_deferred_for_operator_review":
        actions.append("operator_review_required")
    if decision.startswith("commit_execution_eligible"):
        actions.extend(["prepare_live_memory_commit_adapter_later", "prepare_live_memory_dry_run_later"])
    return tuple(dict.fromkeys(actions))


def evaluate_memory_commit_execution_gate(payload: Mapping[str, Any], policy: MemoryCommitExecutionGatePolicy | None = None) -> MemoryCommitExecutionGateResult:
    try:
        active_policy = _policy_from_payload(payload, policy)
        plan_packet = _as_mapping(payload.get("commit_plan_packet"))
        approval_packet = _as_mapping(payload.get("operator_approval_packet"))
        if not plan_packet:
            return _blocked("memory_commit_execution_gate_blocked_missing_commit_plan_packet", [_status_for_blocker("memory_commit_execution_gate_blocked_missing_commit_plan_packet")])
        if not _packet_records(plan_packet) or not str(plan_packet.get("digest", "")).startswith("sha256:"):
            return _blocked("memory_commit_execution_gate_blocked_invalid_commit_plan_packet", [_status_for_blocker("memory_commit_execution_gate_blocked_invalid_commit_plan_packet")])
        if not approval_packet:
            return _blocked("memory_commit_execution_gate_blocked_missing_operator_approval_packet", [_status_for_blocker("memory_commit_execution_gate_blocked_missing_operator_approval_packet")])
        if not _packet_records(approval_packet) or not str(approval_packet.get("digest", "")).startswith("sha256:"):
            return _blocked("memory_commit_execution_gate_blocked_invalid_operator_approval_packet", [_status_for_blocker("memory_commit_execution_gate_blocked_invalid_operator_approval_packet")])
        candidate_payloads = _input_candidates(payload)
        if not candidate_payloads:
            return _blocked("memory_commit_execution_gate_blocked_missing_execution_candidate", [_status_for_blocker("memory_commit_execution_gate_blocked_missing_execution_candidate")])

        plan_record = _first_record(plan_packet)
        approval_record = _first_record(approval_packet)
        plan_digest = str(plan_packet.get("digest") or "")
        approval_digest = str(approval_packet.get("digest") or "")
        plan_decision = str(plan_record.get("plan_decision") or "")
        approval_decision = str(approval_record.get("approval_decision") or "")
        approval_scope = _as_tuple(_as_mapping(approval_record.get("operator_scope")).get("operator_scope_keys") or approval_record.get("operator_scope_keys"))
        findings: list[MemoryCommitExecutionGateFinding] = []
        records: list[MemoryCommitExecutionGateRecord] = []
        for raw in candidate_payloads:
            candidate = MemoryCommitExecutionGateCandidate.from_mapping(raw)
            if candidate is None:
                return _blocked("memory_commit_execution_gate_blocked_invalid_execution_candidate", [_status_for_blocker("memory_commit_execution_gate_blocked_invalid_execution_candidate")])
            blocker = _blocker_for_claims(candidate, active_policy)
            if blocker:
                return _blocked(blocker, [_status_for_blocker(blocker, candidate)])
            if active_policy.require_commit_plan_ready and plan_decision not in READY_PLAN_DECISIONS:
                return _blocked("memory_commit_execution_gate_blocked_plan_not_ready", [MemoryCommitExecutionGateFinding("error", "plan_not_ready", "commit plan packet is not ready", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_operator_approval_ready and approval_decision not in READY_APPROVAL_DECISIONS:
                return _blocked("memory_commit_execution_gate_blocked_approval_not_ready", [MemoryCommitExecutionGateFinding("error", "approval_not_ready", "operator approval packet is not ready", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_plan_digest and candidate.claimed_plan_digest != plan_digest:
                return _blocked("memory_commit_execution_gate_blocked_plan_digest_mismatch", [MemoryCommitExecutionGateFinding("error", "plan_digest_mismatch", "candidate plan digest does not match commit plan packet", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_approval_digest and candidate.claimed_approval_digest != approval_digest:
                return _blocked("memory_commit_execution_gate_blocked_approval_digest_mismatch", [MemoryCommitExecutionGateFinding("error", "approval_digest_mismatch", "candidate approval digest does not match operator approval packet", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_plan_decision and candidate.claimed_plan_decision != plan_decision:
                return _blocked("memory_commit_execution_gate_blocked_plan_decision_mismatch", [MemoryCommitExecutionGateFinding("error", "plan_decision_mismatch", "candidate plan decision does not match plan packet", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_approval_decision and candidate.claimed_approval_decision != approval_decision:
                return _blocked("memory_commit_execution_gate_blocked_approval_decision_mismatch", [MemoryCommitExecutionGateFinding("error", "approval_decision_mismatch", "candidate approval decision does not match approval packet", candidate.candidate_id, candidate.record_id)])
            preconditions: list[MemoryCommitExecutionGatePrecondition] = []
            if active_policy.require_gate_preconditions:
                for key in active_policy.required_preconditions:
                    if key not in candidate.gate_preconditions:
                        return _blocked("memory_commit_execution_gate_blocked_missing_gate_precondition", [MemoryCommitExecutionGateFinding("error", "missing_gate_precondition", f"missing gate precondition {key}", candidate.candidate_id, candidate.record_id)])
                    precondition = MemoryCommitExecutionGatePrecondition(key, True, candidate.gate_preconditions.get(key) is True)
                    if not precondition.satisfied():
                        return _blocked("memory_commit_execution_gate_blocked_precondition_mismatch", [MemoryCommitExecutionGateFinding("error", "precondition_mismatch", f"gate precondition {key} does not match", candidate.candidate_id, candidate.record_id)])
                    preconditions.append(precondition)
            if active_policy.require_operator_scope and not candidate.operator_scope_keys:
                if active_policy.allow_missing_scope_diagnostic_warning:
                    findings.append(MemoryCommitExecutionGateFinding("warning", "missing_operator_scope", "operator scope missing but allowed as diagnostic warning", candidate.candidate_id, candidate.record_id))
                else:
                    return _blocked("memory_commit_execution_gate_blocked_missing_operator_scope", [MemoryCommitExecutionGateFinding("error", "missing_operator_scope", "operator scope metadata is required", candidate.candidate_id, candidate.record_id)])
            mixed_scope_warning = False
            if active_policy.require_scope_alignment and candidate.operator_scope_keys and set(candidate.operator_scope_keys) != set(approval_scope):
                if active_policy.allow_mixed_scope_diagnostic_packet and candidate.metadata.get("diagnostic_warning") is True:
                    findings.append(MemoryCommitExecutionGateFinding("warning", "scope_mismatch_diagnostic", "operator scope mismatch allowed for diagnostic packet", candidate.candidate_id, candidate.record_id))
                    mixed_scope_warning = True
                else:
                    return _blocked("memory_commit_execution_gate_blocked_scope_mismatch", [MemoryCommitExecutionGateFinding("error", "scope_mismatch", "operator scope does not match approval scope", candidate.candidate_id, candidate.record_id)])
            non_noop = candidate.candidate_type != "noop_commit_execution_candidate" and plan_decision != "commit_plan_noop" and approval_decision != "commit_approval_noop"
            if non_noop and active_policy.require_rollback_expectation and not candidate.rollback_expectation:
                return _blocked("memory_commit_execution_gate_blocked_missing_rollback_expectation", [MemoryCommitExecutionGateFinding("error", "missing_rollback_expectation", "rollback expectation is required", candidate.candidate_id, candidate.record_id)])
            if non_noop and active_policy.require_receipt_expectation and not candidate.receipt_expectation:
                return _blocked("memory_commit_execution_gate_blocked_missing_receipt_expectation", [MemoryCommitExecutionGateFinding("error", "missing_receipt_expectation", "receipt expectation is required", candidate.candidate_id, candidate.record_id)])
            warning = mixed_scope_warning or bool(candidate.metadata.get("warning_only") or candidate.metadata.get("diagnostic_warning")) or plan_decision.endswith("with_warnings") or approval_decision.endswith("with_warnings")
            if warning:
                findings.append(MemoryCommitExecutionGateFinding("warning", "execution_gate_warning", "candidate is warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
            decision = _decision_for(candidate, plan_decision, approval_decision, warning)
            record = MemoryCommitExecutionGateRecord(
                candidate_id=candidate.candidate_id,
                record_id=candidate.record_id,
                candidate_type=candidate.candidate_type,
                execution_decision=decision,
                plan_decision=plan_decision,
                approval_decision=approval_decision,
                plan_digest=plan_digest,
                approval_digest=approval_digest,
                operator_scope_keys=candidate.operator_scope_keys,
                approval_scope_keys=approval_scope,
                gate_preconditions=tuple(preconditions),
                safe_next_actions=_safe_actions(decision),
                rollback_expectation=candidate.rollback_expectation,
                receipt_expectation=candidate.receipt_expectation,
            ).with_digest()
            records.append(record)
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for finding in findings if finding.severity == "warning")}
        for record in records:
            counts[record.execution_decision] = counts.get(record.execution_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {record.execution_decision for record in records}
        if counts["warning_count"]:
            status: MemoryCommitExecutionGateStatus = "memory_commit_execution_gate_ready_with_warnings"
        elif decisions <= {"commit_execution_deferred_for_operator_review"}:
            status = "memory_commit_execution_gate_deferred_for_operator_review"
        elif decisions <= {"commit_execution_rejected"}:
            status = "memory_commit_execution_gate_rejected"
        elif decisions <= {"commit_execution_noop"}:
            status = "memory_commit_execution_gate_noop"
        else:
            status = "memory_commit_execution_gate_ready"
        packet = MemoryCommitExecutionGatePacket(active_policy.schema_version, tuple(records)).with_digest()
        report = MemoryCommitExecutionGateReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return MemoryCommitExecutionGateResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("memory_commit_execution_gate_failed", [MemoryCommitExecutionGateFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: MemoryCommitExecutionGatePolicy | None = None) -> MemoryCommitExecutionGateResult:
    return evaluate_memory_commit_execution_gate(payload, policy)


__all__ = [
    "EXECUTION_CANDIDATE_TYPES",
    "FORBIDDEN_NEXT_STEPS",
    "INVARIANTS",
    "READY_APPROVAL_DECISIONS",
    "READY_PLAN_DECISIONS",
    "SAFE_NEXT_ACTIONS",
    "MemoryCommitExecutionGatePolicy",
    "MemoryCommitExecutionGateInput",
    "MemoryCommitExecutionGateCandidate",
    "MemoryCommitExecutionGateFinding",
    "MemoryCommitExecutionGatePrecondition",
    "MemoryCommitExecutionGateRecord",
    "MemoryCommitExecutionGatePacket",
    "MemoryCommitExecutionGateReport",
    "MemoryCommitExecutionGateResult",
    "build_default_policy",
    "validate_policy",
    "evaluate_memory_commit_execution_gate",
    "evaluate_packet",
]
