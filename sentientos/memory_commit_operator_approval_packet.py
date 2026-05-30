"""Deterministic metadata-only memory commit operator approval packet.

The packet evaluates explicit JSON metadata from a memory commit plan packet and
operator approval candidates. It is approval-only: it never writes live memory,
deletes memory, mutates indexes, persists capsules, assembles prompts, executes
actions, invokes remote services, discloses externally, creates policy, grants
authority, infers consent, or asserts truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal, Mapping, Sequence

MemoryCommitOperatorApprovalStatus = Literal[
    "memory_commit_operator_approval_ready",
    "memory_commit_operator_approval_ready_with_warnings",
    "memory_commit_operator_approval_deferred_for_operator_review",
    "memory_commit_operator_approval_rejected",
    "memory_commit_operator_approval_blocked_missing_commit_plan_packet",
    "memory_commit_operator_approval_blocked_invalid_commit_plan_packet",
    "memory_commit_operator_approval_blocked_missing_approval_candidate",
    "memory_commit_operator_approval_blocked_invalid_approval_candidate",
    "memory_commit_operator_approval_blocked_plan_not_ready",
    "memory_commit_operator_approval_blocked_plan_digest_mismatch",
    "memory_commit_operator_approval_blocked_plan_decision_mismatch",
    "memory_commit_operator_approval_blocked_missing_operator_scope",
    "memory_commit_operator_approval_blocked_scope_mismatch",
    "memory_commit_operator_approval_blocked_missing_rollback_expectation",
    "memory_commit_operator_approval_blocked_missing_receipt_expectation",
    "memory_commit_operator_approval_blocked_approval_overclaim",
    "memory_commit_operator_approval_blocked_execution_claim",
    "memory_commit_operator_approval_blocked_live_write_claim",
    "memory_commit_operator_approval_blocked_live_delete_claim",
    "memory_commit_operator_approval_blocked_index_mutation_claim",
    "memory_commit_operator_approval_blocked_capsule_persistence_claim",
    "memory_commit_operator_approval_blocked_prompt_materialization",
    "memory_commit_operator_approval_blocked_action_execution",
    "memory_commit_operator_approval_blocked_external_disclosure",
    "memory_commit_operator_approval_blocked_authority_smuggling",
    "memory_commit_operator_approval_blocked_raw_payload_leak",
    "memory_commit_operator_approval_invalid",
    "memory_commit_operator_approval_failed",
]

ApprovalDecision = Literal[
    "commit_approval_ready_for_future_adapter",
    "commit_approval_ready_for_future_adapter_with_warnings",
    "commit_approval_deferred_for_operator_review",
    "commit_approval_rejected",
    "commit_approval_blocked",
    "commit_approval_noop",
]

APPROVAL_CANDIDATE_TYPES = frozenset({
    "ai_capsule_commit_approval_candidate",
    "human_summary_commit_approval_candidate",
    "dual_capsule_commit_approval_candidate",
    "protect_receipt_commit_approval_candidate",
    "merge_receipt_commit_approval_candidate",
    "tomb_archive_commit_approval_candidate",
    "tomb_deferred_commit_approval_candidate",
    "operator_review_commit_approval_candidate",
    "noop_commit_approval_candidate",
    "mixed_commit_approval_candidate",
})

READY_PLAN_DECISIONS = frozenset({
    "commit_plan_ready_for_review",
    "commit_plan_ready_for_review_with_warnings",
    "commit_plan_deferred_for_operator_review",
    "commit_plan_rejected",
    "commit_plan_noop",
})

SAFE_NEXT_ACTIONS = (
    "no_action_allowed",
    "inspect_operator_approval_packet",
    "operator_review_required",
    "prepare_live_memory_commit_adapter_later",
    "prepare_commit_receipt_schema_later",
    "prepare_rollback_receipt_schema_later",
    "prepare_memory_commit_execution_gate_later",
    "rerun_with_ready_commit_plan",
    "rerun_with_matching_plan_digest",
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
    "execute_commit_plan_now",
    "execute_operator_approval_now",
    "treat_approval_as_execution",
    "call_append_memory",
    "call_purge_memory",
    "call_apply_forgetting_curve",
    "call_curate_memory",
    "call_summarize_memory",
    "assemble_prompt_now",
    "retrieve_live_context",
    "execute_action_ingress",
    "infer_truth_from_operator_approval",
    "infer_authority_from_operator_approval",
    "infer_consent_from_operator_approval",
    "convert_operator_approval_to_policy",
    "convert_operator_approval_to_action",
    "bypass_commit_plan_packet",
    "bypass_live_boundary_admission",
    "bypass_governed_writer_adapter",
    "bypass_tomb_verifier",
    "bypass_receipt_gate",
    "bypass_distillation_contract",
    "bypass_operator_review",
    "enable_external_disclosure",
)

INVARIANTS: dict[str, bool] = {
    "approval_is_not_memory_write": True,
    "approval_is_not_memory_deletion": True,
    "approval_is_not_index_mutation": True,
    "approval_is_not_capsule_persistence": True,
    "approval_is_not_prompt_assembly": True,
    "approval_is_not_execution": True,
    "approval_is_not_truth": True,
    "approval_is_not_policy": True,
    "approval_is_not_authority": True,
    "approval_is_not_consent": True,
    "approval_does_not_execute_action": True,
    "approval_does_not_disclose_externally": True,
    "live_memory_write_enabled": False,
    "live_memory_deletion_enabled": False,
    "live_index_mutation_enabled": False,
    "capsule_persistence_enabled": False,
    "prompt_materialization_enabled": False,
    "external_disclosure_enabled": False,
    "remote_service_enabled": False,
    "default_deny_live_commit": True,
    "future_commit_adapter_required": True,
    "future_execution_gate_required": True,
    "rollback_expectation_required": True,
    "receipt_expectation_required": True,
}

RAW_PAYLOAD_KEYS = frozenset({
    "raw_payload", "raw_transcript", "transcript", "secret", "secrets", "provider_prompt", "prompt", "image", "audio", "video", "screenshot", "thumbnail", "encoded_media", "base64_media", "private_payload"
})
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
class MemoryCommitOperatorApprovalPolicy:
    schema_version: str = "memory-commit-operator-approval-packet.v1"
    default_approval_posture: str = "deny"
    allow_approval_for_future_adapter: bool = True
    allow_warning_approvals: bool = True
    allow_operator_review_deferrals: bool = True
    allow_noop_approvals: bool = True
    allow_mixed_scope_diagnostic_packet: bool = False
    allow_missing_scope_diagnostic_warning: bool = False
    require_matching_plan_digest: bool = True
    require_matching_plan_decision: bool = True
    require_commit_plan_ready: bool = True
    require_operator_scope: bool = True
    require_scope_alignment: bool = True
    require_rollback_expectation: bool = True
    require_receipt_expectation: bool = True
    block_approval_overclaims: bool = True
    block_execution_claims: bool = True
    block_live_write_claims: bool = True
    block_live_delete_claims: bool = True
    block_index_mutation_claims: bool = True
    block_capsule_persistence_claims: bool = True
    block_hard_override_attempts: bool = True


@dataclass(frozen=True)
class MemoryCommitOperatorApprovalInput:
    commit_plan_packet: Mapping[str, Any]
    approval_candidates: tuple[Mapping[str, Any], ...]
    policy: MemoryCommitOperatorApprovalPolicy = field(default_factory=MemoryCommitOperatorApprovalPolicy)


@dataclass(frozen=True)
class MemoryCommitOperatorApprovalFinding:
    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    candidate_id: str | None = None
    record_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemoryCommitOperatorApprovalScope:
    operator_scope_keys: tuple[str, ...] = ()
    plan_scope_keys: tuple[str, ...] = ()

    def aligned(self) -> bool:
        return set(self.operator_scope_keys) == set(self.plan_scope_keys)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemoryCommitOperatorApprovalCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    claimed_plan_digest: str
    claimed_plan_decision: str
    operator_scope_keys: tuple[str, ...]
    rollback_expectation: Mapping[str, Any]
    receipt_expectation: Mapping[str, Any]
    approval_claims: Mapping[str, Any]
    metadata: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "MemoryCommitOperatorApprovalCandidate | None":
        candidate_type = str(raw.get("candidate_type") or "")
        candidate_id = str(raw.get("candidate_id") or "")
        record_id = str(raw.get("record_id") or "")
        if not candidate_id or not record_id or candidate_type not in APPROVAL_CANDIDATE_TYPES:
            return None
        return cls(
            candidate_id=candidate_id,
            record_id=record_id,
            candidate_type=candidate_type,
            claimed_plan_digest=str(raw.get("claimed_plan_digest") or raw.get("plan_digest") or ""),
            claimed_plan_decision=str(raw.get("claimed_plan_decision") or raw.get("plan_decision") or ""),
            operator_scope_keys=_as_tuple(raw.get("operator_scope_keys") or _as_mapping(raw.get("operator_scope")).get("operator_scope_keys")),
            rollback_expectation=_as_mapping(raw.get("rollback_expectation")),
            receipt_expectation=_as_mapping(raw.get("receipt_expectation")),
            approval_claims=_as_mapping(raw.get("approval_claims")),
            metadata=_as_mapping(raw.get("metadata")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemoryCommitOperatorApprovalRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    approval_decision: ApprovalDecision
    plan_decision: str
    plan_digest: str
    operator_scope: MemoryCommitOperatorApprovalScope
    safe_next_actions: tuple[str, ...]
    rollback_expectation: Mapping[str, Any]
    receipt_expectation: Mapping[str, Any]
    approval_future_consideration_only: bool = True
    approval_execution_claimed: bool = False
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
        data["operator_scope"] = self.operator_scope.to_dict()
        return data

    def with_digest(self) -> "MemoryCommitOperatorApprovalRecord":
        data = self.to_dict()
        data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class MemoryCommitOperatorApprovalPacket:
    schema_version: str
    records: tuple[MemoryCommitOperatorApprovalRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""
    approval_is_not_memory_write: bool = True
    approval_is_not_memory_deletion: bool = True
    approval_is_not_index_mutation: bool = True
    approval_is_not_capsule_persistence: bool = True
    approval_is_not_prompt_assembly: bool = True
    approval_is_not_execution: bool = True
    approval_is_not_truth: bool = True
    approval_is_not_policy: bool = True
    approval_is_not_authority: bool = True
    approval_is_not_consent: bool = True
    approval_does_not_execute_action: bool = True
    approval_does_not_disclose_externally: bool = True
    live_memory_write_enabled: bool = False
    live_memory_deletion_enabled: bool = False
    live_index_mutation_enabled: bool = False
    capsule_persistence_enabled: bool = False
    prompt_materialization_enabled: bool = False
    external_disclosure_enabled: bool = False
    remote_service_enabled: bool = False
    default_deny_live_commit: bool = True
    future_commit_adapter_required: bool = True
    future_execution_gate_required: bool = True
    rollback_expectation_required: bool = True
    receipt_expectation_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["records"] = [record.to_dict() for record in self.records]
        return data

    def with_digest(self) -> "MemoryCommitOperatorApprovalPacket":
        data = self.to_dict()
        data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class MemoryCommitOperatorApprovalReport:
    status: MemoryCommitOperatorApprovalStatus
    findings: tuple[MemoryCommitOperatorApprovalFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [finding.to_dict() for finding in self.findings], "summary_counts": dict(sorted(self.summary_counts.items())), "digest": self.digest}


@dataclass(frozen=True)
class MemoryCommitOperatorApprovalResult:
    status: MemoryCommitOperatorApprovalStatus
    packet: MemoryCommitOperatorApprovalPacket | None
    report: MemoryCommitOperatorApprovalReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> MemoryCommitOperatorApprovalPolicy:
    return MemoryCommitOperatorApprovalPolicy()


def validate_policy(policy: MemoryCommitOperatorApprovalPolicy | Mapping[str, Any]) -> dict[str, Any]:
    raw = asdict(policy) if isinstance(policy, MemoryCommitOperatorApprovalPolicy) else dict(policy)
    findings: list[dict[str, str]] = []
    if raw.get("default_approval_posture") != "deny":
        findings.append({"severity": "error", "code": "default_posture_not_deny", "message": "default approval posture must remain deny"})
    for key, expected in INVARIANTS.items():
        if raw.get(key, expected) is not expected:
            findings.append({"severity": "error", "code": f"unsafe_policy_{key}", "message": f"policy attempts to alter invariant {key}"})
    status = "valid" if not findings else "invalid"
    return {"status": status, "schema_version": str(raw.get("schema_version") or ""), "findings": findings, "digest": _digest(raw)}


def _blocked(status: MemoryCommitOperatorApprovalStatus, findings: Sequence[MemoryCommitOperatorApprovalFinding]) -> MemoryCommitOperatorApprovalResult:
    counts = {"candidate_count": 0, "warning_count": sum(1 for finding in findings if finding.severity == "warning"), "error_count": sum(1 for finding in findings if finding.severity == "error")}
    report = MemoryCommitOperatorApprovalReport(status, tuple(findings), counts, "")
    report = replace(report, digest=_digest(report.to_dict()))
    return MemoryCommitOperatorApprovalResult(status, None, report, _digest({"status": status, "report": report.to_dict()}))


def _policy_from_payload(payload: Mapping[str, Any], policy: MemoryCommitOperatorApprovalPolicy | None) -> MemoryCommitOperatorApprovalPolicy:
    if policy is not None:
        return policy
    raw = payload.get("policy")
    if isinstance(raw, Mapping):
        allowed = set(MemoryCommitOperatorApprovalPolicy.__dataclass_fields__)
        return MemoryCommitOperatorApprovalPolicy(**{str(k): v for k, v in raw.items() if str(k) in allowed})
    return build_default_policy()


def _records(packet: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw_records = packet.get("records")
    if not isinstance(raw_records, Sequence) or isinstance(raw_records, (bytes, bytearray, str)):
        return {}
    records: dict[str, Mapping[str, Any]] = {}
    for record in raw_records:
        if isinstance(record, Mapping) and record.get("record_id"):
            records[str(record["record_id"])] = record
    return records


def _packet_digest(packet: Mapping[str, Any]) -> str:
    explicit = str(packet.get("digest") or "")
    if explicit:
        return explicit
    return _digest(packet)


def _claim_blocker(candidate: MemoryCommitOperatorApprovalCandidate, payload: Mapping[str, Any], policy: MemoryCommitOperatorApprovalPolicy) -> str | None:
    checks = (candidate.approval_claims, candidate.metadata, payload)
    if _has_raw_payload(checks):
        return "raw_payload_leak"
    claims = {str(k): v for k, v in candidate.approval_claims.items()}
    text = _canonical({"claims": claims, "metadata": candidate.metadata}).lower()
    if policy.block_approval_overclaims and (claims.get("approval_equals_execution") is True or claims.get("approval_equals_live_commit") is True or "approval equals execution" in text or "approval equals live commit" in text or "proves truth" in text):
        return "approval_overclaim"
    if policy.block_execution_claims and (claims.get("executes_commit_plan") is True or claims.get("executes_operator_approval") is True or claims.get("execution_claimed") is True or "execute now" in text):
        return "execution_claim"
    if policy.block_live_write_claims and (claims.get("writes_live_memory") is True or claims.get("live_memory_write_enabled") is True):
        return "live_write_claim"
    if policy.block_live_delete_claims and (claims.get("deletes_live_memory") is True or claims.get("live_memory_deletion_enabled") is True):
        return "live_delete_claim"
    if policy.block_index_mutation_claims and (claims.get("mutates_index") is True or claims.get("live_index_mutation_enabled") is True):
        return "index_mutation_claim"
    if policy.block_capsule_persistence_claims and (claims.get("persists_capsule") is True or claims.get("capsule_persistence_enabled") is True):
        return "capsule_persistence_claim"
    if claims.get("assembles_prompt") is True or claims.get("prompt_materialization_enabled") is True:
        return "prompt_materialization"
    if claims.get("executes_action") is True or claims.get("action_execution_claimed") is True:
        return "action_execution"
    if claims.get("discloses_externally") is True or claims.get("external_disclosure_enabled") is True or claims.get("remote_service_enabled") is True:
        return "external_disclosure"
    if policy.block_hard_override_attempts and any(claims.get(key) is True for key in ("grants_authority", "authority_granted", "grants_consent", "creates_policy", "proves_truth", "converts_to_action", "hard_override")):
        return "authority_smuggling"
    return None


def _status_for_blocker(blocker: str) -> MemoryCommitOperatorApprovalStatus:
    return {
        "raw_payload_leak": "memory_commit_operator_approval_blocked_raw_payload_leak",
        "approval_overclaim": "memory_commit_operator_approval_blocked_approval_overclaim",
        "execution_claim": "memory_commit_operator_approval_blocked_execution_claim",
        "live_write_claim": "memory_commit_operator_approval_blocked_live_write_claim",
        "live_delete_claim": "memory_commit_operator_approval_blocked_live_delete_claim",
        "index_mutation_claim": "memory_commit_operator_approval_blocked_index_mutation_claim",
        "capsule_persistence_claim": "memory_commit_operator_approval_blocked_capsule_persistence_claim",
        "prompt_materialization": "memory_commit_operator_approval_blocked_prompt_materialization",
        "action_execution": "memory_commit_operator_approval_blocked_action_execution",
        "external_disclosure": "memory_commit_operator_approval_blocked_external_disclosure",
        "authority_smuggling": "memory_commit_operator_approval_blocked_authority_smuggling",
    }.get(blocker, "memory_commit_operator_approval_blocked_invalid_approval_candidate")  # type: ignore[return-value]


def _decision_for(candidate: MemoryCommitOperatorApprovalCandidate, plan_decision: str, warning: bool) -> ApprovalDecision:
    if candidate.candidate_type == "noop_commit_approval_candidate" or plan_decision == "commit_plan_noop":
        return "commit_approval_noop"
    if candidate.candidate_type == "operator_review_commit_approval_candidate" or plan_decision == "commit_plan_deferred_for_operator_review":
        return "commit_approval_deferred_for_operator_review"
    if plan_decision == "commit_plan_rejected":
        return "commit_approval_rejected"
    if warning or plan_decision == "commit_plan_ready_for_review_with_warnings":
        return "commit_approval_ready_for_future_adapter_with_warnings"
    return "commit_approval_ready_for_future_adapter"


def _safe_actions(decision: str) -> tuple[str, ...]:
    actions = ["no_action_allowed", "inspect_operator_approval_packet", "sustain_default_deny"]
    if decision == "commit_approval_ready_for_future_adapter":
        actions += ["prepare_live_memory_commit_adapter_later", "prepare_memory_commit_execution_gate_later", "prepare_commit_receipt_schema_later", "prepare_rollback_receipt_schema_later"]
    elif decision == "commit_approval_ready_for_future_adapter_with_warnings":
        actions += ["operator_review_required", "prepare_memory_commit_execution_gate_later"]
    elif decision == "commit_approval_deferred_for_operator_review":
        actions += ["operator_review_required", "defer_to_memory_runtime_boundary"]
    elif decision == "commit_approval_rejected":
        actions += ["operator_review_required", "defer_to_self_improvement_ingress"]
    return tuple(dict.fromkeys(actions))


def evaluate_memory_commit_operator_approval_packet(payload: Mapping[str, Any], policy: MemoryCommitOperatorApprovalPolicy | None = None) -> MemoryCommitOperatorApprovalResult:
    try:
        active_policy = _policy_from_payload(payload, policy)
        if validate_policy(active_policy)["status"] != "valid":
            return _blocked("memory_commit_operator_approval_invalid", [MemoryCommitOperatorApprovalFinding("error", "invalid_policy", "approval policy is invalid")])
        plan_packet = payload.get("commit_plan_packet")
        if plan_packet is None:
            return _blocked("memory_commit_operator_approval_blocked_missing_commit_plan_packet", [MemoryCommitOperatorApprovalFinding("error", "missing_commit_plan_packet", "commit plan packet is required")])
        if not isinstance(plan_packet, Mapping) or not _records(plan_packet):
            return _blocked("memory_commit_operator_approval_blocked_invalid_commit_plan_packet", [MemoryCommitOperatorApprovalFinding("error", "invalid_commit_plan_packet", "commit plan packet must contain records")])
        raw_candidates = payload.get("approval_candidates", payload.get("approval_candidate"))
        if raw_candidates is None:
            return _blocked("memory_commit_operator_approval_blocked_missing_approval_candidate", [MemoryCommitOperatorApprovalFinding("error", "missing_approval_candidate", "approval candidate is required")])
        candidate_items: Sequence[Any]
        if isinstance(raw_candidates, Mapping):
            candidate_items = (raw_candidates,)
        elif isinstance(raw_candidates, Sequence) and not isinstance(raw_candidates, (bytes, bytearray, str)):
            candidate_items = raw_candidates
        else:
            return _blocked("memory_commit_operator_approval_blocked_invalid_approval_candidate", [MemoryCommitOperatorApprovalFinding("error", "invalid_approval_candidate", "approval candidate must be an object or list")])
        candidates = [MemoryCommitOperatorApprovalCandidate.from_mapping(item) for item in candidate_items if isinstance(item, Mapping)]
        if not candidates or any(candidate is None for candidate in candidates):
            return _blocked("memory_commit_operator_approval_blocked_invalid_approval_candidate", [MemoryCommitOperatorApprovalFinding("error", "invalid_approval_candidate", "approval candidate has invalid metadata")])
        typed_candidates = [candidate for candidate in candidates if candidate is not None]
        plan_records = _records(plan_packet)
        plan_digest = _packet_digest(plan_packet)
        findings: list[MemoryCommitOperatorApprovalFinding] = []
        scope_sets = {_as_tuple(record.get("source_scope_keys")) for record in plan_records.values() if _as_tuple(record.get("source_scope_keys"))}
        mixed_scope_warning = False
        if len(scope_sets) > 1:
            if active_policy.allow_mixed_scope_diagnostic_packet:
                findings.append(MemoryCommitOperatorApprovalFinding("warning", "mixed_scope_diagnostic_packet", "packet contains multiple plan scopes"))
                mixed_scope_warning = True
            elif active_policy.require_scope_alignment:
                findings.append(MemoryCommitOperatorApprovalFinding("error", "scope_mismatch", "packet contains multiple plan scopes"))
                return _blocked("memory_commit_operator_approval_blocked_scope_mismatch", findings)
        records: list[MemoryCommitOperatorApprovalRecord] = []
        for candidate in typed_candidates:
            plan_record = plan_records.get(candidate.record_id)
            if plan_record is None:
                return _blocked("memory_commit_operator_approval_blocked_invalid_approval_candidate", [MemoryCommitOperatorApprovalFinding("error", "invalid_approval_candidate", "candidate references unknown plan record", candidate.candidate_id, candidate.record_id)])
            blocker = _claim_blocker(candidate, payload, active_policy)
            if blocker:
                findings.append(MemoryCommitOperatorApprovalFinding("error", blocker, f"approval candidate blocked: {blocker}", candidate.candidate_id, candidate.record_id))
                return _blocked(_status_for_blocker(blocker), findings)
            plan_decision = str(plan_record.get("plan_decision") or "")
            if active_policy.require_commit_plan_ready and plan_decision not in READY_PLAN_DECISIONS:
                return _blocked("memory_commit_operator_approval_blocked_plan_not_ready", [MemoryCommitOperatorApprovalFinding("error", "plan_not_ready", "commit plan decision is not ready for approval review", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_plan_digest and candidate.claimed_plan_digest != plan_digest:
                return _blocked("memory_commit_operator_approval_blocked_plan_digest_mismatch", [MemoryCommitOperatorApprovalFinding("error", "plan_digest_mismatch", "candidate plan digest does not match commit plan packet", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_plan_decision and candidate.claimed_plan_decision != plan_decision:
                return _blocked("memory_commit_operator_approval_blocked_plan_decision_mismatch", [MemoryCommitOperatorApprovalFinding("error", "plan_decision_mismatch", "candidate plan decision does not match commit plan record", candidate.candidate_id, candidate.record_id)])
            plan_scope = _as_tuple(plan_record.get("source_scope_keys"))
            if active_policy.require_operator_scope and not candidate.operator_scope_keys:
                if active_policy.allow_missing_scope_diagnostic_warning:
                    findings.append(MemoryCommitOperatorApprovalFinding("warning", "missing_operator_scope", "operator scope missing but allowed as diagnostic warning", candidate.candidate_id, candidate.record_id))
                else:
                    return _blocked("memory_commit_operator_approval_blocked_missing_operator_scope", [MemoryCommitOperatorApprovalFinding("error", "missing_operator_scope", "operator scope metadata is required", candidate.candidate_id, candidate.record_id)])
            scope = MemoryCommitOperatorApprovalScope(candidate.operator_scope_keys, plan_scope)
            if active_policy.require_scope_alignment and candidate.operator_scope_keys and not scope.aligned():
                if active_policy.allow_mixed_scope_diagnostic_packet and candidate.metadata.get("diagnostic_warning") is True:
                    findings.append(MemoryCommitOperatorApprovalFinding("warning", "scope_mismatch_diagnostic", "operator scope mismatch allowed for diagnostic packet", candidate.candidate_id, candidate.record_id))
                    mixed_scope_warning = True
                else:
                    return _blocked("memory_commit_operator_approval_blocked_scope_mismatch", [MemoryCommitOperatorApprovalFinding("error", "scope_mismatch", "operator scope does not match plan scope", candidate.candidate_id, candidate.record_id)])
            non_noop = candidate.candidate_type != "noop_commit_approval_candidate" and plan_decision != "commit_plan_noop"
            if non_noop and active_policy.require_rollback_expectation and not candidate.rollback_expectation:
                return _blocked("memory_commit_operator_approval_blocked_missing_rollback_expectation", [MemoryCommitOperatorApprovalFinding("error", "missing_rollback_expectation", "rollback expectation is required", candidate.candidate_id, candidate.record_id)])
            if non_noop and active_policy.require_receipt_expectation and not candidate.receipt_expectation:
                return _blocked("memory_commit_operator_approval_blocked_missing_receipt_expectation", [MemoryCommitOperatorApprovalFinding("error", "missing_receipt_expectation", "receipt expectation is required", candidate.candidate_id, candidate.record_id)])
            warning = mixed_scope_warning or bool(candidate.metadata.get("warning_only") or candidate.metadata.get("diagnostic_warning")) or plan_decision == "commit_plan_ready_for_review_with_warnings"
            if warning:
                findings.append(MemoryCommitOperatorApprovalFinding("warning", "operator_approval_warning", "candidate is warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
            decision = _decision_for(candidate, plan_decision, warning)
            record = MemoryCommitOperatorApprovalRecord(
                candidate_id=candidate.candidate_id,
                record_id=candidate.record_id,
                candidate_type=candidate.candidate_type,
                approval_decision=decision,
                plan_decision=plan_decision,
                plan_digest=plan_digest,
                operator_scope=scope,
                safe_next_actions=_safe_actions(decision),
                rollback_expectation=candidate.rollback_expectation,
                receipt_expectation=candidate.receipt_expectation,
            ).with_digest()
            records.append(record)
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for finding in findings if finding.severity == "warning")}
        for record in records:
            counts[record.approval_decision] = counts.get(record.approval_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {record.approval_decision for record in records}
        if counts["warning_count"]:
            status: MemoryCommitOperatorApprovalStatus = "memory_commit_operator_approval_ready_with_warnings"
        elif decisions <= {"commit_approval_deferred_for_operator_review"}:
            status = "memory_commit_operator_approval_deferred_for_operator_review"
        elif decisions <= {"commit_approval_rejected"}:
            status = "memory_commit_operator_approval_rejected"
        else:
            status = "memory_commit_operator_approval_ready"
        packet = MemoryCommitOperatorApprovalPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = MemoryCommitOperatorApprovalReport(status, tuple(findings), dict(sorted(counts.items())), "")
        report = replace(report, digest=_digest(report.to_dict()))
        return MemoryCommitOperatorApprovalResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("memory_commit_operator_approval_failed", [MemoryCommitOperatorApprovalFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: MemoryCommitOperatorApprovalPolicy | None = None) -> MemoryCommitOperatorApprovalResult:
    return evaluate_memory_commit_operator_approval_packet(payload, policy)


__all__ = [
    "APPROVAL_CANDIDATE_TYPES",
    "FORBIDDEN_NEXT_STEPS",
    "INVARIANTS",
    "READY_PLAN_DECISIONS",
    "SAFE_NEXT_ACTIONS",
    "MemoryCommitOperatorApprovalPolicy",
    "MemoryCommitOperatorApprovalInput",
    "MemoryCommitOperatorApprovalCandidate",
    "MemoryCommitOperatorApprovalFinding",
    "MemoryCommitOperatorApprovalScope",
    "MemoryCommitOperatorApprovalRecord",
    "MemoryCommitOperatorApprovalPacket",
    "MemoryCommitOperatorApprovalReport",
    "MemoryCommitOperatorApprovalResult",
    "build_default_policy",
    "validate_policy",
    "evaluate_memory_commit_operator_approval_packet",
    "evaluate_packet",
]
