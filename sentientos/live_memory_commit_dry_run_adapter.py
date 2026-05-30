"""Deterministic metadata-only live memory commit dry-run adapter.

The adapter consumes explicit memory commit execution-gate evidence plus proposed
live-memory commit dry-run candidates and emits only hypothetical operation,
receipt, and rollback previews. It never writes or deletes live memory, mutates
indexes, persists capsules or summaries, completes tombs, assembles prompts,
executes actions, calls remote services, infers truth/consent/policy/authority,
or bypasses the upstream memory distillation, receipt, tomb, writer, boundary,
plan, approval, and execution-gate chain.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal, Mapping, Sequence

LiveMemoryCommitDryRunStatus = Literal[
    "live_memory_commit_dry_run_ready",
    "live_memory_commit_dry_run_ready_with_warnings",
    "live_memory_commit_dry_run_deferred_for_operator_review",
    "live_memory_commit_dry_run_rejected",
    "live_memory_commit_dry_run_noop",
    "live_memory_commit_dry_run_blocked_missing_execution_gate_packet",
    "live_memory_commit_dry_run_blocked_invalid_execution_gate_packet",
    "live_memory_commit_dry_run_blocked_missing_commit_candidate",
    "live_memory_commit_dry_run_blocked_invalid_commit_candidate",
    "live_memory_commit_dry_run_blocked_execution_gate_not_ready",
    "live_memory_commit_dry_run_blocked_execution_gate_digest_mismatch",
    "live_memory_commit_dry_run_blocked_execution_gate_decision_mismatch",
    "live_memory_commit_dry_run_blocked_missing_operation_preview",
    "live_memory_commit_dry_run_blocked_operation_preview_mismatch",
    "live_memory_commit_dry_run_blocked_missing_receipt_preview",
    "live_memory_commit_dry_run_blocked_missing_rollback_preview",
    "live_memory_commit_dry_run_blocked_live_write_claim",
    "live_memory_commit_dry_run_blocked_live_delete_claim",
    "live_memory_commit_dry_run_blocked_index_mutation_claim",
    "live_memory_commit_dry_run_blocked_capsule_persistence_claim",
    "live_memory_commit_dry_run_blocked_tomb_completion_claim",
    "live_memory_commit_dry_run_blocked_prompt_materialization",
    "live_memory_commit_dry_run_blocked_action_execution",
    "live_memory_commit_dry_run_blocked_external_disclosure",
    "live_memory_commit_dry_run_blocked_authority_smuggling",
    "live_memory_commit_dry_run_blocked_raw_payload_leak",
    "live_memory_commit_dry_run_blocked_scope_mismatch",
    "live_memory_commit_dry_run_invalid",
    "live_memory_commit_dry_run_failed",
]

DryRunDecision = Literal[
    "dry_run_commit_preview_ready",
    "dry_run_commit_preview_ready_with_warnings",
    "dry_run_deferred_for_operator_review",
    "dry_run_rejected",
    "dry_run_blocked",
    "dry_run_noop",
]

DRY_RUN_CANDIDATE_TYPES = frozenset({
    "ai_capsule_commit_dry_run_candidate",
    "human_summary_commit_dry_run_candidate",
    "dual_capsule_commit_dry_run_candidate",
    "protect_receipt_commit_dry_run_candidate",
    "merge_receipt_commit_dry_run_candidate",
    "tomb_archive_commit_dry_run_candidate",
    "tomb_deferred_commit_dry_run_candidate",
    "operator_review_commit_dry_run_candidate",
    "noop_commit_dry_run_candidate",
    "mixed_commit_dry_run_candidate",
})

READY_EXECUTION_GATE_DECISIONS = frozenset({
    "commit_execution_eligible_for_future_adapter",
    "commit_execution_eligible_for_future_adapter_with_warnings",
    "commit_execution_deferred_for_operator_review",
    "commit_execution_rejected",
    "commit_execution_noop",
})

SAFE_NEXT_ACTIONS = (
    "no_action_allowed",
    "inspect_dry_run_packet",
    "operator_review_required",
    "prepare_live_memory_commit_adapter_later",
    "prepare_commit_receipt_schema_later",
    "prepare_rollback_receipt_schema_later",
    "prepare_live_commit_safety_interlock_later",
    "rerun_with_ready_execution_gate",
    "rerun_with_matching_execution_gate_digest",
    "rerun_with_matching_execution_gate_decision",
    "rerun_with_operation_preview",
    "rerun_with_receipt_preview",
    "rerun_with_rollback_preview",
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
    "execute_dry_run_as_commit",
    "execute_commit_plan_now",
    "execute_operator_approval_now",
    "treat_dry_run_as_execution",
    "treat_dry_run_as_live_commit",
    "call_append_memory",
    "call_purge_memory",
    "call_apply_forgetting_curve",
    "call_curate_memory",
    "call_summarize_memory",
    "assemble_prompt_now",
    "retrieve_live_context",
    "execute_action_ingress",
    "infer_truth_from_dry_run",
    "infer_authority_from_dry_run",
    "infer_consent_from_dry_run",
    "convert_dry_run_to_policy",
    "convert_dry_run_to_action",
    "bypass_execution_gate",
    "bypass_operator_approval_packet",
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
    "dry_run_is_not_memory_write": True,
    "dry_run_is_not_memory_deletion": True,
    "dry_run_is_not_index_mutation": True,
    "dry_run_is_not_capsule_persistence": True,
    "dry_run_is_not_prompt_assembly": True,
    "dry_run_is_not_execution": True,
    "dry_run_is_not_live_commit": True,
    "dry_run_is_not_truth": True,
    "dry_run_is_not_policy": True,
    "dry_run_is_not_authority": True,
    "dry_run_is_not_consent": True,
    "dry_run_does_not_execute_action": True,
    "dry_run_does_not_disclose_externally": True,
    "live_memory_write_enabled": False,
    "live_memory_deletion_enabled": False,
    "live_index_mutation_enabled": False,
    "capsule_persistence_enabled": False,
    "prompt_materialization_enabled": False,
    "external_disclosure_enabled": False,
    "remote_service_enabled": False,
    "default_deny_live_commit": True,
    "future_commit_adapter_required": True,
    "future_safety_interlock_required": True,
    "receipt_preview_required": True,
    "rollback_preview_required": True,
    "execution_gate_required": True,
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
class LiveMemoryCommitDryRunPolicy:
    schema_version: str = "live-memory-commit-dry-run-adapter.v1"
    default_dry_run_posture: str = "deny"
    allow_dry_run_previews: bool = True
    allow_warning_previews: bool = True
    allow_operator_review_deferrals: bool = True
    allow_noop_previews: bool = True
    allow_rejections: bool = True
    allow_mixed_scope_diagnostic_packet: bool = False
    require_execution_gate_ready: bool = True
    require_matching_execution_gate_digest: bool = True
    require_matching_execution_gate_decision: bool = True
    require_operation_preview: bool = True
    require_receipt_preview: bool = True
    require_rollback_preview: bool = True
    require_scope_alignment: bool = True
    block_live_write_claims: bool = True
    block_live_delete_claims: bool = True
    block_index_mutation_claims: bool = True
    block_capsule_persistence_claims: bool = True
    block_tomb_completion_claims: bool = True
    block_hard_override_attempts: bool = True


@dataclass(frozen=True)
class LiveMemoryCommitDryRunInput:
    execution_gate_packet: Mapping[str, Any]
    commit_candidates: tuple[Mapping[str, Any], ...]
    policy: LiveMemoryCommitDryRunPolicy = field(default_factory=LiveMemoryCommitDryRunPolicy)


@dataclass(frozen=True)
class LiveMemoryCommitDryRunFinding:
    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    candidate_id: str | None = None
    record_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveMemoryCommitDryRunOperationPreview:
    preview_id: str
    operation_kind: str
    target_scope_keys: tuple[str, ...]
    hypothetical_only: bool = True
    applied: bool = False
    live_memory_write_claimed: bool = False
    live_memory_delete_claimed: bool = False
    index_mutation_claimed: bool = False
    capsule_persistence_claimed: bool = False
    tomb_completion_claimed: bool = False
    digest: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "LiveMemoryCommitDryRunOperationPreview | None":
        preview_id = str(raw.get("preview_id") or raw.get("operation_preview_id") or "")
        operation_kind = str(raw.get("operation_kind") or "")
        if not preview_id or not operation_kind:
            return None
        return cls(preview_id, operation_kind, _as_tuple(raw.get("target_scope_keys")), raw.get("hypothetical_only", True) is True, raw.get("applied") is True, raw.get("live_memory_write_claimed") is True or raw.get("writes_live_memory") is True, raw.get("live_memory_delete_claimed") is True or raw.get("deletes_live_memory") is True or raw.get("purges_live_memory") is True, raw.get("index_mutation_claimed") is True or raw.get("mutates_index") is True, raw.get("capsule_persistence_claimed") is True or raw.get("persists_capsule") is True, raw.get("tomb_completion_claimed") is True or raw.get("completes_tomb") is True).with_digest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_digest(self) -> "LiveMemoryCommitDryRunOperationPreview":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class LiveMemoryCommitDryRunReceiptPreview:
    preview_id: str
    receipt_kind: str
    hypothetical_only: bool = True
    receipt_emitted: bool = False
    digest: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "LiveMemoryCommitDryRunReceiptPreview | None":
        preview_id = str(raw.get("preview_id") or raw.get("receipt_preview_id") or "")
        receipt_kind = str(raw.get("receipt_kind") or "")
        if not preview_id or not receipt_kind:
            return None
        return cls(preview_id, receipt_kind, raw.get("hypothetical_only", True) is True, raw.get("receipt_emitted") is True or raw.get("emitted") is True).with_digest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_digest(self) -> "LiveMemoryCommitDryRunReceiptPreview":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class LiveMemoryCommitDryRunRollbackPreview:
    preview_id: str
    rollback_kind: str
    hypothetical_only: bool = True
    rollback_applied: bool = False
    digest: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "LiveMemoryCommitDryRunRollbackPreview | None":
        preview_id = str(raw.get("preview_id") or raw.get("rollback_preview_id") or "")
        rollback_kind = str(raw.get("rollback_kind") or "")
        if not preview_id or not rollback_kind:
            return None
        return cls(preview_id, rollback_kind, raw.get("hypothetical_only", True) is True, raw.get("rollback_applied") is True or raw.get("applied") is True).with_digest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_digest(self) -> "LiveMemoryCommitDryRunRollbackPreview":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class LiveMemoryCommitDryRunCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    claimed_execution_gate_digest: str
    claimed_execution_gate_decision: str
    operator_scope_keys: tuple[str, ...]
    operation_preview: Mapping[str, Any]
    receipt_preview: Mapping[str, Any]
    rollback_preview: Mapping[str, Any]
    dry_run_claims: Mapping[str, Any]
    metadata: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "LiveMemoryCommitDryRunCandidate | None":
        candidate_type = str(raw.get("candidate_type") or "")
        candidate_id = str(raw.get("candidate_id") or "")
        record_id = str(raw.get("record_id") or "")
        if not candidate_id or not record_id or candidate_type not in DRY_RUN_CANDIDATE_TYPES:
            return None
        return cls(
            candidate_id,
            record_id,
            candidate_type,
            str(raw.get("claimed_execution_gate_digest") or raw.get("execution_gate_digest") or ""),
            str(raw.get("claimed_execution_gate_decision") or raw.get("execution_gate_decision") or ""),
            _as_tuple(raw.get("operator_scope_keys")),
            _as_mapping(raw.get("operation_preview")),
            _as_mapping(raw.get("receipt_preview")),
            _as_mapping(raw.get("rollback_preview")),
            _as_mapping(raw.get("dry_run_claims")),
            _as_mapping(raw.get("metadata")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveMemoryCommitDryRunRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    dry_run_decision: DryRunDecision
    execution_gate_decision: str
    execution_gate_digest: str
    operator_scope_keys: tuple[str, ...]
    execution_gate_scope_keys: tuple[str, ...]
    safe_next_actions: tuple[str, ...]
    operation_preview: LiveMemoryCommitDryRunOperationPreview | None
    receipt_preview: LiveMemoryCommitDryRunReceiptPreview | None
    rollback_preview: LiveMemoryCommitDryRunRollbackPreview | None
    dry_run_future_consideration_only: bool = True
    live_memory_write_claimed: bool = False
    live_memory_delete_claimed: bool = False
    index_mutation_claimed: bool = False
    capsule_persistence_claimed: bool = False
    tomb_completion_claimed: bool = False
    policy_authority_claimed: bool = False
    truth_claimed: bool = False
    consent_claimed: bool = False
    prompt_assembly_claimed: bool = False
    action_execution_claimed: bool = False
    external_disclosure_claimed: bool = False
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["operation_preview"] = self.operation_preview.to_dict() if self.operation_preview else None
        data["receipt_preview"] = self.receipt_preview.to_dict() if self.receipt_preview else None
        data["rollback_preview"] = self.rollback_preview.to_dict() if self.rollback_preview else None
        return data

    def with_digest(self) -> "LiveMemoryCommitDryRunRecord":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class LiveMemoryCommitDryRunPacket:
    schema_version: str
    records: tuple[LiveMemoryCommitDryRunRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""
    dry_run_is_not_memory_write: bool = True
    dry_run_is_not_memory_deletion: bool = True
    dry_run_is_not_index_mutation: bool = True
    dry_run_is_not_capsule_persistence: bool = True
    dry_run_is_not_prompt_assembly: bool = True
    dry_run_is_not_execution: bool = True
    dry_run_is_not_live_commit: bool = True
    dry_run_is_not_truth: bool = True
    dry_run_is_not_policy: bool = True
    dry_run_is_not_authority: bool = True
    dry_run_is_not_consent: bool = True
    dry_run_does_not_execute_action: bool = True
    dry_run_does_not_disclose_externally: bool = True
    live_memory_write_enabled: bool = False
    live_memory_deletion_enabled: bool = False
    live_index_mutation_enabled: bool = False
    capsule_persistence_enabled: bool = False
    prompt_materialization_enabled: bool = False
    external_disclosure_enabled: bool = False
    remote_service_enabled: bool = False
    default_deny_live_commit: bool = True
    future_commit_adapter_required: bool = True
    future_safety_interlock_required: bool = True
    receipt_preview_required: bool = True
    rollback_preview_required: bool = True
    execution_gate_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["records"] = [record.to_dict() for record in self.records]
        return data

    def with_digest(self) -> "LiveMemoryCommitDryRunPacket":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class LiveMemoryCommitDryRunReport:
    status: LiveMemoryCommitDryRunStatus
    findings: tuple[LiveMemoryCommitDryRunFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [finding.to_dict() for finding in self.findings], "summary_counts": dict(sorted(self.summary_counts.items())), "digest": self.digest}


@dataclass(frozen=True)
class LiveMemoryCommitDryRunResult:
    status: LiveMemoryCommitDryRunStatus
    packet: LiveMemoryCommitDryRunPacket | None
    report: LiveMemoryCommitDryRunReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> LiveMemoryCommitDryRunPolicy:
    return LiveMemoryCommitDryRunPolicy()


def validate_policy(policy: LiveMemoryCommitDryRunPolicy | Mapping[str, Any]) -> dict[str, Any]:
    raw = asdict(policy) if isinstance(policy, LiveMemoryCommitDryRunPolicy) else dict(policy)
    findings: list[dict[str, str]] = []
    if raw.get("default_dry_run_posture") != "deny":
        findings.append({"severity": "error", "code": "default_dry_run_posture_not_deny", "message": "dry-run adapter must default deny"})
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
    raw = payload.get("commit_candidates", payload.get("commit_candidate"))
    if isinstance(raw, Mapping):
        return (raw,)
    if isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray, str)):
        return tuple(item for item in raw if isinstance(item, Mapping))
    return ()


def _policy_from_payload(payload: Mapping[str, Any], policy: LiveMemoryCommitDryRunPolicy | None) -> LiveMemoryCommitDryRunPolicy:
    if policy is not None:
        return policy
    raw = payload.get("policy")
    if isinstance(raw, Mapping):
        allowed = set(LiveMemoryCommitDryRunPolicy.__dataclass_fields__)
        return LiveMemoryCommitDryRunPolicy(**{str(k): v for k, v in raw.items() if str(k) in allowed})
    return build_default_policy()


def _blocked(status: LiveMemoryCommitDryRunStatus, findings: Sequence[LiveMemoryCommitDryRunFinding]) -> LiveMemoryCommitDryRunResult:
    report = LiveMemoryCommitDryRunReport(status, tuple(findings), {"candidate_count": 0, "error_count": sum(1 for f in findings if f.severity == "error")})
    report = replace(report, digest=_digest(report.to_dict()))
    return LiveMemoryCommitDryRunResult(status, None, report, _digest({"packet": None, "report": report.to_dict()}))


def _flag(claims: Mapping[str, Any], *names: str) -> bool:
    return any(claims.get(name) is True for name in names)


def _blocker_for_claims(candidate: LiveMemoryCommitDryRunCandidate, operation: LiveMemoryCommitDryRunOperationPreview | None, receipt: LiveMemoryCommitDryRunReceiptPreview | None, rollback: LiveMemoryCommitDryRunRollbackPreview | None, policy: LiveMemoryCommitDryRunPolicy) -> LiveMemoryCommitDryRunStatus | None:
    claims = candidate.dry_run_claims
    metadata = candidate.metadata
    if _has_raw_payload(candidate.to_dict()):
        return "live_memory_commit_dry_run_blocked_raw_payload_leak"
    if policy.block_live_write_claims and (_flag(claims, "live_memory_write", "writes_memory", "write_live_memory") or (operation is not None and operation.live_memory_write_claimed)):
        return "live_memory_commit_dry_run_blocked_live_write_claim"
    if policy.block_live_delete_claims and (_flag(claims, "live_memory_delete", "deletes_memory", "purges_memory") or (operation is not None and operation.live_memory_delete_claimed)):
        return "live_memory_commit_dry_run_blocked_live_delete_claim"
    if policy.block_index_mutation_claims and (_flag(claims, "index_mutation", "mutates_index", "vector_index_mutation") or (operation is not None and operation.index_mutation_claimed)):
        return "live_memory_commit_dry_run_blocked_index_mutation_claim"
    if policy.block_capsule_persistence_claims and (_flag(claims, "capsule_persistence", "persists_capsule", "persist_capsule") or (operation is not None and operation.capsule_persistence_claimed)):
        return "live_memory_commit_dry_run_blocked_capsule_persistence_claim"
    if policy.block_tomb_completion_claims and (_flag(claims, "tomb_completion", "complete_tomb", "completes_tomb") or (operation is not None and operation.tomb_completion_claimed)):
        return "live_memory_commit_dry_run_blocked_tomb_completion_claim"
    if _flag(claims, "prompt_materialization", "prompt_assembly", "assembles_prompt") or metadata.get("prompt_materialization_requested") is True:
        return "live_memory_commit_dry_run_blocked_prompt_materialization"
    if _flag(claims, "action_execution", "executes_action", "action_ingress") or metadata.get("action_execution_requested") is True:
        return "live_memory_commit_dry_run_blocked_action_execution"
    if _flag(claims, "external_disclosure", "discloses_externally", "remote_service") or metadata.get("external_disclosure_requested") is True:
        return "live_memory_commit_dry_run_blocked_external_disclosure"
    if policy.block_hard_override_attempts and (_flag(claims, "authority", "grants_authority", "policy", "truth", "consent", "action_authority") or any(metadata.get(key) is True for key in ("authority_claimed", "policy_claimed", "truth_claimed", "consent_claimed", "dry_run_is_authoritative", "override_hard_blocker"))):
        return "live_memory_commit_dry_run_blocked_authority_smuggling"
    if operation is not None and (not operation.hypothetical_only or operation.applied):
        return "live_memory_commit_dry_run_blocked_operation_preview_mismatch"
    if receipt is not None and (not receipt.hypothetical_only or receipt.receipt_emitted):
        return "live_memory_commit_dry_run_blocked_missing_receipt_preview"
    if rollback is not None and (not rollback.hypothetical_only or rollback.rollback_applied):
        return "live_memory_commit_dry_run_blocked_missing_rollback_preview"
    return None


def _status_for_blocker(status: LiveMemoryCommitDryRunStatus, candidate: LiveMemoryCommitDryRunCandidate | None = None) -> LiveMemoryCommitDryRunFinding:
    code = status.replace("live_memory_commit_dry_run_blocked_", "").replace("live_memory_commit_dry_run_", "")
    return LiveMemoryCommitDryRunFinding("error", code, code.replace("_", " "), candidate.candidate_id if candidate else None, candidate.record_id if candidate else None)


def _decision_for(candidate: LiveMemoryCommitDryRunCandidate, gate_decision: str, warning: bool) -> DryRunDecision:
    if candidate.candidate_type == "noop_commit_dry_run_candidate" or gate_decision == "commit_execution_noop":
        return "dry_run_noop"
    if candidate.candidate_type == "operator_review_commit_dry_run_candidate" or gate_decision == "commit_execution_deferred_for_operator_review" or candidate.metadata.get("operator_review_requested") is True:
        return "dry_run_deferred_for_operator_review"
    if gate_decision == "commit_execution_rejected" or candidate.metadata.get("rejected") is True:
        return "dry_run_rejected"
    if warning or gate_decision.endswith("with_warnings"):
        return "dry_run_commit_preview_ready_with_warnings"
    return "dry_run_commit_preview_ready"


def _safe_actions(decision: DryRunDecision) -> tuple[str, ...]:
    actions = ["no_action_allowed", "inspect_dry_run_packet", "sustain_default_deny", "defer_to_memory_runtime_boundary", "defer_to_self_improvement_ingress"]
    if decision == "dry_run_deferred_for_operator_review":
        actions.append("operator_review_required")
    if decision in {"dry_run_commit_preview_ready", "dry_run_commit_preview_ready_with_warnings"}:
        actions.extend(["prepare_live_memory_commit_adapter_later", "prepare_commit_receipt_schema_later", "prepare_rollback_receipt_schema_later", "prepare_live_commit_safety_interlock_later"])
    return tuple(dict.fromkeys(actions))


def evaluate_live_memory_commit_dry_run_adapter(payload: Mapping[str, Any], policy: LiveMemoryCommitDryRunPolicy | None = None) -> LiveMemoryCommitDryRunResult:
    try:
        active_policy = _policy_from_payload(payload, policy)
        gate_packet = _as_mapping(payload.get("execution_gate_packet"))
        if not gate_packet:
            return _blocked("live_memory_commit_dry_run_blocked_missing_execution_gate_packet", [_status_for_blocker("live_memory_commit_dry_run_blocked_missing_execution_gate_packet")])
        if not _packet_records(gate_packet) or not str(gate_packet.get("digest") or ""):
            return _blocked("live_memory_commit_dry_run_blocked_invalid_execution_gate_packet", [_status_for_blocker("live_memory_commit_dry_run_blocked_invalid_execution_gate_packet")])
        candidate_payloads = _input_candidates(payload)
        if not candidate_payloads:
            return _blocked("live_memory_commit_dry_run_blocked_missing_commit_candidate", [_status_for_blocker("live_memory_commit_dry_run_blocked_missing_commit_candidate")])
        gate_record = _first_record(gate_packet)
        gate_digest = str(gate_packet.get("digest") or "")
        gate_decision = str(gate_record.get("execution_decision") or "")
        gate_scope = _as_tuple(gate_record.get("operator_scope_keys"))
        findings: list[LiveMemoryCommitDryRunFinding] = []
        records: list[LiveMemoryCommitDryRunRecord] = []
        for raw in candidate_payloads:
            candidate = LiveMemoryCommitDryRunCandidate.from_mapping(raw)
            if candidate is None:
                return _blocked("live_memory_commit_dry_run_blocked_invalid_commit_candidate", [_status_for_blocker("live_memory_commit_dry_run_blocked_invalid_commit_candidate")])
            non_noop = candidate.candidate_type != "noop_commit_dry_run_candidate" and gate_decision != "commit_execution_noop"
            operation = LiveMemoryCommitDryRunOperationPreview.from_mapping(candidate.operation_preview) if candidate.operation_preview else None
            receipt = LiveMemoryCommitDryRunReceiptPreview.from_mapping(candidate.receipt_preview) if candidate.receipt_preview else None
            rollback = LiveMemoryCommitDryRunRollbackPreview.from_mapping(candidate.rollback_preview) if candidate.rollback_preview else None
            blocker = _blocker_for_claims(candidate, operation, receipt, rollback, active_policy)
            if blocker:
                return _blocked(blocker, [_status_for_blocker(blocker, candidate)])
            if active_policy.require_execution_gate_ready and gate_decision not in READY_EXECUTION_GATE_DECISIONS:
                return _blocked("live_memory_commit_dry_run_blocked_execution_gate_not_ready", [LiveMemoryCommitDryRunFinding("error", "execution_gate_not_ready", "execution gate packet is not ready", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_execution_gate_digest and candidate.claimed_execution_gate_digest != gate_digest:
                return _blocked("live_memory_commit_dry_run_blocked_execution_gate_digest_mismatch", [LiveMemoryCommitDryRunFinding("error", "execution_gate_digest_mismatch", "candidate execution gate digest does not match", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_execution_gate_decision and candidate.claimed_execution_gate_decision != gate_decision:
                return _blocked("live_memory_commit_dry_run_blocked_execution_gate_decision_mismatch", [LiveMemoryCommitDryRunFinding("error", "execution_gate_decision_mismatch", "candidate execution gate decision does not match", candidate.candidate_id, candidate.record_id)])
            if non_noop and active_policy.require_operation_preview and operation is None:
                return _blocked("live_memory_commit_dry_run_blocked_missing_operation_preview", [LiveMemoryCommitDryRunFinding("error", "missing_operation_preview", "operation preview is required", candidate.candidate_id, candidate.record_id)])
            if non_noop and active_policy.require_receipt_preview and receipt is None:
                return _blocked("live_memory_commit_dry_run_blocked_missing_receipt_preview", [LiveMemoryCommitDryRunFinding("error", "missing_receipt_preview", "receipt preview is required", candidate.candidate_id, candidate.record_id)])
            if non_noop and active_policy.require_rollback_preview and rollback is None:
                return _blocked("live_memory_commit_dry_run_blocked_missing_rollback_preview", [LiveMemoryCommitDryRunFinding("error", "missing_rollback_preview", "rollback preview is required", candidate.candidate_id, candidate.record_id)])
            mixed_scope_warning = False
            if active_policy.require_scope_alignment and candidate.operator_scope_keys and set(candidate.operator_scope_keys) != set(gate_scope):
                if active_policy.allow_mixed_scope_diagnostic_packet and candidate.metadata.get("diagnostic_warning") is True:
                    findings.append(LiveMemoryCommitDryRunFinding("warning", "scope_mismatch_diagnostic", "scope mismatch allowed for diagnostic packet", candidate.candidate_id, candidate.record_id))
                    mixed_scope_warning = True
                else:
                    return _blocked("live_memory_commit_dry_run_blocked_scope_mismatch", [LiveMemoryCommitDryRunFinding("error", "scope_mismatch", "candidate scope does not match execution gate scope", candidate.candidate_id, candidate.record_id)])
            warning = mixed_scope_warning or bool(candidate.metadata.get("warning_only") or candidate.metadata.get("diagnostic_warning")) or gate_decision.endswith("with_warnings")
            if warning:
                findings.append(LiveMemoryCommitDryRunFinding("warning", "dry_run_warning", "candidate is warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
            decision = _decision_for(candidate, gate_decision, warning)
            records.append(LiveMemoryCommitDryRunRecord(candidate.candidate_id, candidate.record_id, candidate.candidate_type, decision, gate_decision, gate_digest, candidate.operator_scope_keys, gate_scope, _safe_actions(decision), operation, receipt, rollback).with_digest())
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for finding in findings if finding.severity == "warning")}
        for record in records:
            counts[record.dry_run_decision] = counts.get(record.dry_run_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {record.dry_run_decision for record in records}
        if counts["warning_count"]:
            status: LiveMemoryCommitDryRunStatus = "live_memory_commit_dry_run_ready_with_warnings"
        elif decisions <= {"dry_run_deferred_for_operator_review"}:
            status = "live_memory_commit_dry_run_deferred_for_operator_review"
        elif decisions <= {"dry_run_rejected"}:
            status = "live_memory_commit_dry_run_rejected"
        elif decisions <= {"dry_run_noop"}:
            status = "live_memory_commit_dry_run_noop"
        else:
            status = "live_memory_commit_dry_run_ready"
        packet = LiveMemoryCommitDryRunPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = LiveMemoryCommitDryRunReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return LiveMemoryCommitDryRunResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("live_memory_commit_dry_run_failed", [LiveMemoryCommitDryRunFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: LiveMemoryCommitDryRunPolicy | None = None) -> LiveMemoryCommitDryRunResult:
    return evaluate_live_memory_commit_dry_run_adapter(payload, policy)


__all__ = [
    "DRY_RUN_CANDIDATE_TYPES", "FORBIDDEN_NEXT_STEPS", "INVARIANTS", "READY_EXECUTION_GATE_DECISIONS", "SAFE_NEXT_ACTIONS",
    "LiveMemoryCommitDryRunPolicy", "LiveMemoryCommitDryRunInput", "LiveMemoryCommitDryRunCandidate", "LiveMemoryCommitDryRunFinding", "LiveMemoryCommitDryRunOperationPreview", "LiveMemoryCommitDryRunReceiptPreview", "LiveMemoryCommitDryRunRollbackPreview", "LiveMemoryCommitDryRunRecord", "LiveMemoryCommitDryRunPacket", "LiveMemoryCommitDryRunReport", "LiveMemoryCommitDryRunResult",
    "build_default_policy", "validate_policy", "evaluate_live_memory_commit_dry_run_adapter", "evaluate_packet",
]
