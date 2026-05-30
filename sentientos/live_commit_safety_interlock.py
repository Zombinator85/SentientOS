"""Deterministic metadata-only live commit safety interlock.

The interlock consumes explicit live memory commit dry-run evidence, execution-gate
metadata, and interlock candidates to decide whether future live commit adapter
consideration is eligible, warning-only, deferred, rejected, noop, or blocked. It
never writes memory, deletes memory, mutates indexes, persists capsules, assembles
prompts, executes actions, discloses externally, grants authority, infers truth,
or performs a live commit.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal, Mapping, Sequence

LiveCommitSafetyInterlockStatus = Literal[
    "live_commit_safety_interlock_ready",
    "live_commit_safety_interlock_ready_with_warnings",
    "live_commit_safety_interlock_deferred_for_operator_review",
    "live_commit_safety_interlock_rejected",
    "live_commit_safety_interlock_noop",
    "live_commit_safety_interlock_blocked_missing_dry_run_packet",
    "live_commit_safety_interlock_blocked_invalid_dry_run_packet",
    "live_commit_safety_interlock_blocked_missing_execution_gate_packet",
    "live_commit_safety_interlock_blocked_invalid_execution_gate_packet",
    "live_commit_safety_interlock_blocked_missing_interlock_candidate",
    "live_commit_safety_interlock_blocked_invalid_interlock_candidate",
    "live_commit_safety_interlock_blocked_dry_run_not_ready",
    "live_commit_safety_interlock_blocked_execution_gate_not_ready",
    "live_commit_safety_interlock_blocked_dry_run_digest_mismatch",
    "live_commit_safety_interlock_blocked_execution_gate_digest_mismatch",
    "live_commit_safety_interlock_blocked_dry_run_decision_mismatch",
    "live_commit_safety_interlock_blocked_execution_gate_decision_mismatch",
    "live_commit_safety_interlock_blocked_missing_operation_preview",
    "live_commit_safety_interlock_blocked_missing_receipt_preview",
    "live_commit_safety_interlock_blocked_missing_rollback_preview",
    "live_commit_safety_interlock_blocked_missing_safety_precondition",
    "live_commit_safety_interlock_blocked_safety_precondition_mismatch",
    "live_commit_safety_interlock_blocked_live_write_claim",
    "live_commit_safety_interlock_blocked_live_delete_claim",
    "live_commit_safety_interlock_blocked_index_mutation_claim",
    "live_commit_safety_interlock_blocked_capsule_persistence_claim",
    "live_commit_safety_interlock_blocked_tomb_completion_claim",
    "live_commit_safety_interlock_blocked_prompt_materialization",
    "live_commit_safety_interlock_blocked_action_execution",
    "live_commit_safety_interlock_blocked_external_disclosure",
    "live_commit_safety_interlock_blocked_authority_smuggling",
    "live_commit_safety_interlock_blocked_raw_payload_leak",
    "live_commit_safety_interlock_blocked_scope_mismatch",
    "live_commit_safety_interlock_invalid",
    "live_commit_safety_interlock_failed",
]

LiveCommitAdapterDecision = Literal[
    "live_commit_adapter_consideration_eligible",
    "live_commit_adapter_consideration_eligible_with_warnings",
    "live_commit_adapter_consideration_deferred_for_operator_review",
    "live_commit_adapter_consideration_rejected",
    "live_commit_adapter_consideration_blocked",
    "live_commit_adapter_consideration_noop",
]

INTERLOCK_CANDIDATE_TYPES = frozenset({
    "ai_capsule_commit_interlock_candidate",
    "human_summary_commit_interlock_candidate",
    "dual_capsule_commit_interlock_candidate",
    "protect_receipt_commit_interlock_candidate",
    "merge_receipt_commit_interlock_candidate",
    "tomb_archive_commit_interlock_candidate",
    "tomb_deferred_commit_interlock_candidate",
    "operator_review_commit_interlock_candidate",
    "noop_commit_interlock_candidate",
    "mixed_commit_interlock_candidate",
})

READY_DRY_RUN_DECISIONS = frozenset({
    "dry_run_commit_preview_ready",
    "dry_run_commit_preview_ready_with_warnings",
    "dry_run_deferred_for_operator_review",
    "dry_run_rejected",
    "dry_run_noop",
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
    "inspect_safety_interlock_packet",
    "operator_review_required",
    "prepare_live_memory_commit_adapter_later",
    "prepare_live_commit_receipt_schema_later",
    "prepare_live_commit_rollback_schema_later",
    "prepare_final_live_commit_review_later",
    "rerun_with_ready_dry_run",
    "rerun_with_ready_execution_gate",
    "rerun_with_matching_dry_run_digest",
    "rerun_with_matching_execution_gate_digest",
    "rerun_with_operation_preview",
    "rerun_with_receipt_preview",
    "rerun_with_rollback_preview",
    "rerun_with_safety_preconditions",
    "rerun_with_scope_alignment",
    "sustain_default_deny",
    "defer_to_memory_runtime_boundary",
    "defer_to_self_improvement_ingress",
)

FORBIDDEN_NEXT_STEPS = (
    "write_live_memory_now", "delete_live_memory_now", "purge_live_memory_now", "mutate_raw_fragment",
    "mutate_vector_index", "mutate_distilled_memory", "persist_capsule_now", "persist_summary_now",
    "apply_protection_now", "apply_merge_now", "complete_tomb_now", "run_live_commit_now",
    "execute_dry_run_as_commit", "execute_interlock_as_commit", "execute_commit_plan_now",
    "execute_operator_approval_now", "treat_interlock_as_execution", "treat_interlock_as_live_commit",
    "call_append_memory", "call_purge_memory", "call_apply_forgetting_curve", "call_curate_memory",
    "call_summarize_memory", "assemble_prompt_now", "retrieve_live_context", "execute_action_ingress",
    "infer_truth_from_interlock", "infer_authority_from_interlock", "infer_consent_from_interlock",
    "convert_interlock_to_policy", "convert_interlock_to_action", "bypass_dry_run_adapter",
    "bypass_execution_gate", "bypass_operator_approval_packet", "bypass_commit_plan_packet",
    "bypass_live_boundary_admission", "bypass_governed_writer_adapter", "bypass_tomb_verifier",
    "bypass_receipt_gate", "bypass_distillation_contract", "bypass_operator_review",
    "enable_external_disclosure",
)

INVARIANTS: dict[str, bool] = {
    "interlock_is_not_memory_write": True,
    "interlock_is_not_memory_deletion": True,
    "interlock_is_not_index_mutation": True,
    "interlock_is_not_capsule_persistence": True,
    "interlock_is_not_prompt_assembly": True,
    "interlock_is_not_execution": True,
    "interlock_is_not_live_commit": True,
    "interlock_is_not_truth": True,
    "interlock_is_not_policy": True,
    "interlock_is_not_authority": True,
    "interlock_is_not_consent": True,
    "interlock_does_not_execute_action": True,
    "interlock_does_not_disclose_externally": True,
    "live_memory_write_enabled": False,
    "live_memory_deletion_enabled": False,
    "live_index_mutation_enabled": False,
    "capsule_persistence_enabled": False,
    "prompt_materialization_enabled": False,
    "external_disclosure_enabled": False,
    "remote_service_enabled": False,
    "default_deny_live_commit": True,
    "future_commit_adapter_required": True,
    "final_live_commit_review_required": True,
    "dry_run_adapter_required": True,
    "execution_gate_required": True,
    "receipt_preview_required": True,
    "rollback_preview_required": True,
    "safety_preconditions_required": True,
}

RAW_PAYLOAD_KEYS = frozenset({"raw", "payload", "transcript", "secret", "secrets", "provider_prompt", "prompt", "image", "audio", "video", "screenshot", "thumbnail", "encoded_media", "base64_media", "private_payload"})
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
class LiveCommitSafetyInterlockPolicy:
    schema_version: str = "live-commit-safety-interlock.v1"
    default_interlock_posture: str = "deny"
    allow_future_adapter_consideration: bool = True
    allow_warning_consideration: bool = True
    allow_operator_review_deferrals: bool = True
    allow_noop_consideration: bool = True
    allow_mixed_scope_diagnostic_packet: bool = False
    require_dry_run_ready: bool = True
    require_execution_gate_ready: bool = True
    require_matching_dry_run_digest: bool = True
    require_matching_execution_gate_digest: bool = True
    require_matching_dry_run_decision: bool = True
    require_matching_execution_gate_decision: bool = True
    require_operation_preview: bool = True
    require_receipt_preview: bool = True
    require_rollback_preview: bool = True
    require_safety_preconditions: bool = True
    require_scope_alignment: bool = True
    block_live_write_claims: bool = True
    block_live_delete_claims: bool = True
    block_index_mutation_claims: bool = True
    block_capsule_persistence_claims: bool = True
    block_tomb_completion_claims: bool = True
    block_hard_override_attempts: bool = True


@dataclass(frozen=True)
class LiveCommitSafetyInterlockInput:
    dry_run_packet: Mapping[str, Any]
    execution_gate_packet: Mapping[str, Any]
    interlock_candidates: tuple[Mapping[str, Any], ...]
    policy: LiveCommitSafetyInterlockPolicy = field(default_factory=LiveCommitSafetyInterlockPolicy)


@dataclass(frozen=True)
class LiveCommitSafetyInterlockFinding:
    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    candidate_id: str | None = None
    record_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveCommitSafetyInterlockPrecondition:
    precondition_id: str
    dry_run_digest: str
    execution_gate_digest: str
    operation_preview_digest: str
    receipt_preview_digest: str
    rollback_preview_digest: str
    scope_digest: str
    satisfied: bool = True
    digest: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "LiveCommitSafetyInterlockPrecondition | None":
        pid = str(raw.get("precondition_id") or raw.get("safety_precondition_id") or "")
        if not pid:
            return None
        return cls(pid, str(raw.get("dry_run_digest") or ""), str(raw.get("execution_gate_digest") or ""), str(raw.get("operation_preview_digest") or ""), str(raw.get("receipt_preview_digest") or ""), str(raw.get("rollback_preview_digest") or ""), str(raw.get("scope_digest") or ""), raw.get("satisfied", True) is True).with_digest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_digest(self) -> "LiveCommitSafetyInterlockPrecondition":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class LiveCommitSafetyInterlockSafetyNote:
    note_id: str
    note: str
    severity: Literal["info", "warning"] = "info"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveCommitSafetyInterlockCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    claimed_dry_run_digest: str
    claimed_execution_gate_digest: str
    claimed_dry_run_decision: str
    claimed_execution_gate_decision: str
    operator_scope_keys: tuple[str, ...]
    operation_preview: Mapping[str, Any]
    receipt_preview: Mapping[str, Any]
    rollback_preview: Mapping[str, Any]
    safety_preconditions: tuple[Mapping[str, Any], ...]
    interlock_claims: Mapping[str, Any]
    metadata: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "LiveCommitSafetyInterlockCandidate | None":
        candidate_type = str(raw.get("candidate_type") or "")
        candidate_id = str(raw.get("candidate_id") or "")
        record_id = str(raw.get("record_id") or "")
        if not candidate_id or not record_id or candidate_type not in INTERLOCK_CANDIDATE_TYPES:
            return None
        pres = raw.get("safety_preconditions", raw.get("safety_precondition"))
        preconditions: tuple[Mapping[str, Any], ...]
        if isinstance(pres, Mapping):
            preconditions = (pres,)
        elif isinstance(pres, Sequence) and not isinstance(pres, (bytes, bytearray, str)):
            preconditions = tuple(item for item in pres if isinstance(item, Mapping))
        else:
            preconditions = ()
        return cls(
            candidate_id,
            record_id,
            candidate_type,
            str(raw.get("claimed_dry_run_digest") or raw.get("dry_run_digest") or ""),
            str(raw.get("claimed_execution_gate_digest") or raw.get("execution_gate_digest") or ""),
            str(raw.get("claimed_dry_run_decision") or raw.get("dry_run_decision") or ""),
            str(raw.get("claimed_execution_gate_decision") or raw.get("execution_gate_decision") or ""),
            _as_tuple(raw.get("operator_scope_keys")),
            _as_mapping(raw.get("operation_preview")),
            _as_mapping(raw.get("receipt_preview")),
            _as_mapping(raw.get("rollback_preview")),
            preconditions,
            _as_mapping(raw.get("interlock_claims")),
            _as_mapping(raw.get("metadata")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveCommitSafetyInterlockRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    interlock_decision: LiveCommitAdapterDecision
    dry_run_decision: str
    execution_gate_decision: str
    dry_run_digest: str
    execution_gate_digest: str
    operator_scope_keys: tuple[str, ...]
    dry_run_scope_keys: tuple[str, ...]
    execution_gate_scope_keys: tuple[str, ...]
    safe_next_actions: tuple[str, ...]
    safety_preconditions: tuple[LiveCommitSafetyInterlockPrecondition, ...]
    safety_notes: tuple[LiveCommitSafetyInterlockSafetyNote, ...]
    operation_preview: Mapping[str, Any]
    receipt_preview: Mapping[str, Any]
    rollback_preview: Mapping[str, Any]
    future_adapter_eligibility_record: Mapping[str, Any]
    interlock_future_consideration_only: bool = True
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
        data["safety_preconditions"] = [item.to_dict() for item in self.safety_preconditions]
        data["safety_notes"] = [item.to_dict() for item in self.safety_notes]
        return data

    def with_digest(self) -> "LiveCommitSafetyInterlockRecord":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class LiveCommitSafetyInterlockPacket:
    schema_version: str
    records: tuple[LiveCommitSafetyInterlockRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""
    interlock_is_not_memory_write: bool = True
    interlock_is_not_memory_deletion: bool = True
    interlock_is_not_index_mutation: bool = True
    interlock_is_not_capsule_persistence: bool = True
    interlock_is_not_prompt_assembly: bool = True
    interlock_is_not_execution: bool = True
    interlock_is_not_live_commit: bool = True
    interlock_is_not_truth: bool = True
    interlock_is_not_policy: bool = True
    interlock_is_not_authority: bool = True
    interlock_is_not_consent: bool = True
    interlock_does_not_execute_action: bool = True
    interlock_does_not_disclose_externally: bool = True
    live_memory_write_enabled: bool = False
    live_memory_deletion_enabled: bool = False
    live_index_mutation_enabled: bool = False
    capsule_persistence_enabled: bool = False
    prompt_materialization_enabled: bool = False
    external_disclosure_enabled: bool = False
    remote_service_enabled: bool = False
    default_deny_live_commit: bool = True
    future_commit_adapter_required: bool = True
    final_live_commit_review_required: bool = True
    dry_run_adapter_required: bool = True
    execution_gate_required: bool = True
    receipt_preview_required: bool = True
    rollback_preview_required: bool = True
    safety_preconditions_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["records"] = [record.to_dict() for record in self.records]
        return data

    def with_digest(self) -> "LiveCommitSafetyInterlockPacket":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class LiveCommitSafetyInterlockReport:
    status: LiveCommitSafetyInterlockStatus
    findings: tuple[LiveCommitSafetyInterlockFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [finding.to_dict() for finding in self.findings], "summary_counts": dict(sorted(self.summary_counts.items())), "digest": self.digest}


@dataclass(frozen=True)
class LiveCommitSafetyInterlockResult:
    status: LiveCommitSafetyInterlockStatus
    packet: LiveCommitSafetyInterlockPacket | None
    report: LiveCommitSafetyInterlockReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> LiveCommitSafetyInterlockPolicy:
    return LiveCommitSafetyInterlockPolicy()


def validate_policy(policy: LiveCommitSafetyInterlockPolicy | Mapping[str, Any]) -> dict[str, Any]:
    raw = asdict(policy) if isinstance(policy, LiveCommitSafetyInterlockPolicy) else dict(policy)
    findings: list[dict[str, str]] = []
    if raw.get("default_interlock_posture") != "deny":
        findings.append({"severity": "error", "code": "default_interlock_posture_not_deny", "message": "interlock must default deny"})
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
    raw = payload.get("interlock_candidates", payload.get("interlock_candidate"))
    if isinstance(raw, Mapping):
        return (raw,)
    if isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray, str)):
        return tuple(item for item in raw if isinstance(item, Mapping))
    return ()


def _policy_from_payload(payload: Mapping[str, Any], policy: LiveCommitSafetyInterlockPolicy | None) -> LiveCommitSafetyInterlockPolicy:
    if policy is not None:
        return policy
    raw = payload.get("policy")
    if isinstance(raw, Mapping):
        allowed = set(LiveCommitSafetyInterlockPolicy.__dataclass_fields__)
        return LiveCommitSafetyInterlockPolicy(**{str(k): v for k, v in raw.items() if str(k) in allowed})
    return build_default_policy()


def _blocked(status: LiveCommitSafetyInterlockStatus, findings: Sequence[LiveCommitSafetyInterlockFinding]) -> LiveCommitSafetyInterlockResult:
    report = LiveCommitSafetyInterlockReport(status, tuple(findings), {"candidate_count": 0, "error_count": sum(1 for f in findings if f.severity == "error")})
    report = replace(report, digest=_digest(report.to_dict()))
    return LiveCommitSafetyInterlockResult(status, None, report, _digest({"packet": None, "report": report.to_dict()}))


def _status_for_blocker(status: LiveCommitSafetyInterlockStatus, candidate: LiveCommitSafetyInterlockCandidate | None = None) -> LiveCommitSafetyInterlockFinding:
    code = status.removeprefix("live_commit_safety_interlock_blocked_").removeprefix("live_commit_safety_interlock_")
    return LiveCommitSafetyInterlockFinding("error", code, code.replace("_", " "), candidate.candidate_id if candidate else None, candidate.record_id if candidate else None)


def _flag(claims: Mapping[str, Any], *names: str) -> bool:
    return any(claims.get(name) is True for name in names)


def _preview_digest(raw: Mapping[str, Any]) -> str:
    return str(raw.get("digest") or _digest(dict(raw))) if raw else ""


def _scope_digest(values: Sequence[str]) -> str:
    return _digest(tuple(sorted(values)))


def _claims_blocker(candidate: LiveCommitSafetyInterlockCandidate, policy: LiveCommitSafetyInterlockPolicy) -> LiveCommitSafetyInterlockStatus | None:
    claims = candidate.interlock_claims
    metadata = candidate.metadata
    operation = candidate.operation_preview
    if _has_raw_payload(candidate.to_dict()):
        return "live_commit_safety_interlock_blocked_raw_payload_leak"
    if policy.block_live_write_claims and (_flag(claims, "live_memory_write", "writes_memory", "write_live_memory") or operation.get("live_memory_write_claimed") is True or operation.get("writes_live_memory") is True):
        return "live_commit_safety_interlock_blocked_live_write_claim"
    if policy.block_live_delete_claims and (_flag(claims, "live_memory_delete", "deletes_memory", "purges_memory") or operation.get("live_memory_delete_claimed") is True or operation.get("deletes_live_memory") is True or operation.get("purges_live_memory") is True):
        return "live_commit_safety_interlock_blocked_live_delete_claim"
    if policy.block_index_mutation_claims and (_flag(claims, "index_mutation", "mutates_index", "vector_index_mutation") or operation.get("index_mutation_claimed") is True or operation.get("mutates_index") is True):
        return "live_commit_safety_interlock_blocked_index_mutation_claim"
    if policy.block_capsule_persistence_claims and (_flag(claims, "capsule_persistence", "persists_capsule", "persist_capsule") or operation.get("capsule_persistence_claimed") is True or operation.get("persists_capsule") is True):
        return "live_commit_safety_interlock_blocked_capsule_persistence_claim"
    if policy.block_tomb_completion_claims and (_flag(claims, "tomb_completion", "completes_tomb", "complete_tomb") or operation.get("tomb_completion_claimed") is True or operation.get("completes_tomb") is True):
        return "live_commit_safety_interlock_blocked_tomb_completion_claim"
    if _flag(claims, "prompt_materialization", "prompt_assembly", "assembles_prompt") or metadata.get("prompt_materialization_requested") is True:
        return "live_commit_safety_interlock_blocked_prompt_materialization"
    if _flag(claims, "action_execution", "executes_action", "action_ingress") or metadata.get("action_execution_requested") is True:
        return "live_commit_safety_interlock_blocked_action_execution"
    if _flag(claims, "external_disclosure", "discloses_externally", "remote_service") or metadata.get("external_disclosure_requested") is True:
        return "live_commit_safety_interlock_blocked_external_disclosure"
    if policy.block_hard_override_attempts and (_flag(claims, "authority", "grants_authority", "policy", "truth", "consent", "action_authority") or any(metadata.get(key) is True for key in ("authority_claimed", "policy_claimed", "truth_claimed", "consent_claimed", "interlock_is_authoritative", "override_hard_blocker"))):
        return "live_commit_safety_interlock_blocked_authority_smuggling"
    if operation and (operation.get("hypothetical_only", True) is not True or operation.get("applied") is True):
        return "live_commit_safety_interlock_blocked_live_write_claim"
    if candidate.receipt_preview and (candidate.receipt_preview.get("hypothetical_only", True) is not True or candidate.receipt_preview.get("receipt_emitted") is True or candidate.receipt_preview.get("emitted") is True):
        return "live_commit_safety_interlock_blocked_missing_receipt_preview"
    if candidate.rollback_preview and (candidate.rollback_preview.get("hypothetical_only", True) is not True or candidate.rollback_preview.get("rollback_applied") is True or candidate.rollback_preview.get("applied") is True):
        return "live_commit_safety_interlock_blocked_missing_rollback_preview"
    return None


def _decision_for(candidate: LiveCommitSafetyInterlockCandidate, dry_decision: str, gate_decision: str, warning: bool) -> LiveCommitAdapterDecision:
    if candidate.candidate_type == "noop_commit_interlock_candidate" or dry_decision == "dry_run_noop" or gate_decision == "commit_execution_noop":
        return "live_commit_adapter_consideration_noop"
    if candidate.candidate_type == "operator_review_commit_interlock_candidate" or dry_decision == "dry_run_deferred_for_operator_review" or gate_decision == "commit_execution_deferred_for_operator_review" or candidate.metadata.get("operator_review_requested") is True:
        return "live_commit_adapter_consideration_deferred_for_operator_review"
    if dry_decision == "dry_run_rejected" or gate_decision == "commit_execution_rejected" or candidate.metadata.get("rejected") is True:
        return "live_commit_adapter_consideration_rejected"
    if warning or dry_decision.endswith("with_warnings") or gate_decision.endswith("with_warnings"):
        return "live_commit_adapter_consideration_eligible_with_warnings"
    return "live_commit_adapter_consideration_eligible"


def _safe_actions(decision: LiveCommitAdapterDecision) -> tuple[str, ...]:
    actions = ["no_action_allowed", "inspect_safety_interlock_packet", "sustain_default_deny", "defer_to_memory_runtime_boundary", "defer_to_self_improvement_ingress"]
    if decision == "live_commit_adapter_consideration_deferred_for_operator_review":
        actions.append("operator_review_required")
    if decision in {"live_commit_adapter_consideration_eligible", "live_commit_adapter_consideration_eligible_with_warnings"}:
        actions.extend(["prepare_live_memory_commit_adapter_later", "prepare_live_commit_receipt_schema_later", "prepare_live_commit_rollback_schema_later", "prepare_final_live_commit_review_later"])
    return tuple(dict.fromkeys(actions))


def _precondition_mismatch(candidate: LiveCommitSafetyInterlockCandidate, precondition: LiveCommitSafetyInterlockPrecondition, dry_digest: str, gate_digest: str, scope_keys: tuple[str, ...]) -> bool:
    expected = {
        "dry_run_digest": dry_digest,
        "execution_gate_digest": gate_digest,
        "operation_preview_digest": _preview_digest(candidate.operation_preview),
        "receipt_preview_digest": _preview_digest(candidate.receipt_preview),
        "rollback_preview_digest": _preview_digest(candidate.rollback_preview),
        "scope_digest": _scope_digest(scope_keys),
    }
    return (not precondition.satisfied) or any(getattr(precondition, key) != value for key, value in expected.items())


def evaluate_live_commit_safety_interlock(payload: Mapping[str, Any], policy: LiveCommitSafetyInterlockPolicy | None = None) -> LiveCommitSafetyInterlockResult:
    try:
        active_policy = _policy_from_payload(payload, policy)
        dry_packet = _as_mapping(payload.get("dry_run_packet"))
        if not dry_packet:
            return _blocked("live_commit_safety_interlock_blocked_missing_dry_run_packet", [_status_for_blocker("live_commit_safety_interlock_blocked_missing_dry_run_packet")])
        if not _packet_records(dry_packet) or not str(dry_packet.get("digest") or ""):
            return _blocked("live_commit_safety_interlock_blocked_invalid_dry_run_packet", [_status_for_blocker("live_commit_safety_interlock_blocked_invalid_dry_run_packet")])
        gate_packet = _as_mapping(payload.get("execution_gate_packet"))
        if not gate_packet:
            return _blocked("live_commit_safety_interlock_blocked_missing_execution_gate_packet", [_status_for_blocker("live_commit_safety_interlock_blocked_missing_execution_gate_packet")])
        if not _packet_records(gate_packet) or not str(gate_packet.get("digest") or ""):
            return _blocked("live_commit_safety_interlock_blocked_invalid_execution_gate_packet", [_status_for_blocker("live_commit_safety_interlock_blocked_invalid_execution_gate_packet")])
        candidate_payloads = _input_candidates(payload)
        if not candidate_payloads:
            return _blocked("live_commit_safety_interlock_blocked_missing_interlock_candidate", [_status_for_blocker("live_commit_safety_interlock_blocked_missing_interlock_candidate")])

        dry_record = _first_record(dry_packet)
        gate_record = _first_record(gate_packet)
        dry_digest = str(dry_packet.get("digest") or "")
        gate_digest = str(gate_packet.get("digest") or "")
        dry_decision = str(dry_record.get("dry_run_decision") or "")
        gate_decision = str(gate_record.get("execution_decision") or "")
        dry_scope = _as_tuple(dry_record.get("operator_scope_keys") or dry_record.get("dry_run_scope_keys"))
        gate_scope = _as_tuple(gate_record.get("operator_scope_keys"))
        findings: list[LiveCommitSafetyInterlockFinding] = []
        records: list[LiveCommitSafetyInterlockRecord] = []

        for raw in candidate_payloads:
            candidate = LiveCommitSafetyInterlockCandidate.from_mapping(raw)
            if candidate is None:
                return _blocked("live_commit_safety_interlock_blocked_invalid_interlock_candidate", [_status_for_blocker("live_commit_safety_interlock_blocked_invalid_interlock_candidate")])
            blocker = _claims_blocker(candidate, active_policy)
            if blocker:
                return _blocked(blocker, [_status_for_blocker(blocker, candidate)])
            non_noop = candidate.candidate_type != "noop_commit_interlock_candidate" and dry_decision != "dry_run_noop" and gate_decision != "commit_execution_noop"
            if active_policy.require_dry_run_ready and dry_decision not in READY_DRY_RUN_DECISIONS:
                return _blocked("live_commit_safety_interlock_blocked_dry_run_not_ready", [LiveCommitSafetyInterlockFinding("error", "dry_run_not_ready", "dry-run packet is not ready", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_execution_gate_ready and gate_decision not in READY_EXECUTION_GATE_DECISIONS:
                return _blocked("live_commit_safety_interlock_blocked_execution_gate_not_ready", [LiveCommitSafetyInterlockFinding("error", "execution_gate_not_ready", "execution gate packet is not ready", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_dry_run_digest and candidate.claimed_dry_run_digest != dry_digest:
                return _blocked("live_commit_safety_interlock_blocked_dry_run_digest_mismatch", [LiveCommitSafetyInterlockFinding("error", "dry_run_digest_mismatch", "candidate dry-run digest does not match", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_execution_gate_digest and candidate.claimed_execution_gate_digest != gate_digest:
                return _blocked("live_commit_safety_interlock_blocked_execution_gate_digest_mismatch", [LiveCommitSafetyInterlockFinding("error", "execution_gate_digest_mismatch", "candidate execution gate digest does not match", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_dry_run_decision and candidate.claimed_dry_run_decision != dry_decision:
                return _blocked("live_commit_safety_interlock_blocked_dry_run_decision_mismatch", [LiveCommitSafetyInterlockFinding("error", "dry_run_decision_mismatch", "candidate dry-run decision does not match", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_execution_gate_decision and candidate.claimed_execution_gate_decision != gate_decision:
                return _blocked("live_commit_safety_interlock_blocked_execution_gate_decision_mismatch", [LiveCommitSafetyInterlockFinding("error", "execution_gate_decision_mismatch", "candidate execution gate decision does not match", candidate.candidate_id, candidate.record_id)])
            if non_noop and active_policy.require_operation_preview and not candidate.operation_preview:
                return _blocked("live_commit_safety_interlock_blocked_missing_operation_preview", [LiveCommitSafetyInterlockFinding("error", "missing_operation_preview", "operation preview is required", candidate.candidate_id, candidate.record_id)])
            if non_noop and active_policy.require_receipt_preview and not candidate.receipt_preview:
                return _blocked("live_commit_safety_interlock_blocked_missing_receipt_preview", [LiveCommitSafetyInterlockFinding("error", "missing_receipt_preview", "receipt preview is required", candidate.candidate_id, candidate.record_id)])
            if non_noop and active_policy.require_rollback_preview and not candidate.rollback_preview:
                return _blocked("live_commit_safety_interlock_blocked_missing_rollback_preview", [LiveCommitSafetyInterlockFinding("error", "missing_rollback_preview", "rollback preview is required", candidate.candidate_id, candidate.record_id)])
            preconditions = tuple(item for item in (LiveCommitSafetyInterlockPrecondition.from_mapping(pre) for pre in candidate.safety_preconditions) if item is not None)
            if non_noop and active_policy.require_safety_preconditions and not preconditions:
                return _blocked("live_commit_safety_interlock_blocked_missing_safety_precondition", [LiveCommitSafetyInterlockFinding("error", "missing_safety_precondition", "safety precondition is required", candidate.candidate_id, candidate.record_id)])
            scope_keys = candidate.operator_scope_keys or dry_scope or gate_scope
            if active_policy.require_safety_preconditions and any(_precondition_mismatch(candidate, item, dry_digest, gate_digest, scope_keys) for item in preconditions):
                return _blocked("live_commit_safety_interlock_blocked_safety_precondition_mismatch", [LiveCommitSafetyInterlockFinding("error", "safety_precondition_mismatch", "safety precondition does not match dry-run, gate, previews, and scope evidence", candidate.candidate_id, candidate.record_id)])
            mixed_scope_warning = False
            if active_policy.require_scope_alignment and candidate.operator_scope_keys and (set(candidate.operator_scope_keys) != set(dry_scope) or set(candidate.operator_scope_keys) != set(gate_scope)):
                if active_policy.allow_mixed_scope_diagnostic_packet and candidate.metadata.get("diagnostic_warning") is True:
                    findings.append(LiveCommitSafetyInterlockFinding("warning", "scope_mismatch_diagnostic", "scope mismatch allowed for diagnostic packet", candidate.candidate_id, candidate.record_id))
                    mixed_scope_warning = True
                else:
                    return _blocked("live_commit_safety_interlock_blocked_scope_mismatch", [LiveCommitSafetyInterlockFinding("error", "scope_mismatch", "candidate scope does not match dry-run and execution-gate scope", candidate.candidate_id, candidate.record_id)])
            warning = mixed_scope_warning or bool(candidate.metadata.get("warning_only") or candidate.metadata.get("diagnostic_warning")) or dry_decision.endswith("with_warnings") or gate_decision.endswith("with_warnings")
            if warning:
                findings.append(LiveCommitSafetyInterlockFinding("warning", "interlock_warning", "candidate is warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
            decision = _decision_for(candidate, dry_decision, gate_decision, warning)
            notes = (LiveCommitSafetyInterlockSafetyNote("default_deny", "Interlock is metadata-only and default-deny."), LiveCommitSafetyInterlockSafetyNote("future_review", "Future live commit adapter and final live commit review remain required."))
            future_record = {"candidate_id": candidate.candidate_id, "eligible_for_future_adapter_consideration": decision in {"live_commit_adapter_consideration_eligible", "live_commit_adapter_consideration_eligible_with_warnings"}, "decision": decision, "live_commit_performed": False, "final_live_commit_review_required": True}
            records.append(LiveCommitSafetyInterlockRecord(candidate.candidate_id, candidate.record_id, candidate.candidate_type, decision, dry_decision, gate_decision, dry_digest, gate_digest, candidate.operator_scope_keys, dry_scope, gate_scope, _safe_actions(decision), preconditions, notes, dict(candidate.operation_preview), dict(candidate.receipt_preview), dict(candidate.rollback_preview), future_record).with_digest())

        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for finding in findings if finding.severity == "warning")}
        for record in records:
            counts[record.interlock_decision] = counts.get(record.interlock_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {record.interlock_decision for record in records}
        if counts["warning_count"]:
            status: LiveCommitSafetyInterlockStatus = "live_commit_safety_interlock_ready_with_warnings"
        elif decisions <= {"live_commit_adapter_consideration_deferred_for_operator_review"}:
            status = "live_commit_safety_interlock_deferred_for_operator_review"
        elif decisions <= {"live_commit_adapter_consideration_rejected"}:
            status = "live_commit_safety_interlock_rejected"
        elif decisions <= {"live_commit_adapter_consideration_noop"}:
            status = "live_commit_safety_interlock_noop"
        else:
            status = "live_commit_safety_interlock_ready"
        packet = LiveCommitSafetyInterlockPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = LiveCommitSafetyInterlockReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return LiveCommitSafetyInterlockResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("live_commit_safety_interlock_failed", [LiveCommitSafetyInterlockFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: LiveCommitSafetyInterlockPolicy | None = None) -> LiveCommitSafetyInterlockResult:
    return evaluate_live_commit_safety_interlock(payload, policy)


__all__ = [
    "FORBIDDEN_NEXT_STEPS", "INVARIANTS", "INTERLOCK_CANDIDATE_TYPES", "READY_DRY_RUN_DECISIONS", "READY_EXECUTION_GATE_DECISIONS", "SAFE_NEXT_ACTIONS",
    "LiveCommitSafetyInterlockPolicy", "LiveCommitSafetyInterlockInput", "LiveCommitSafetyInterlockCandidate", "LiveCommitSafetyInterlockFinding", "LiveCommitSafetyInterlockPrecondition", "LiveCommitSafetyInterlockSafetyNote", "LiveCommitSafetyInterlockRecord", "LiveCommitSafetyInterlockPacket", "LiveCommitSafetyInterlockReport", "LiveCommitSafetyInterlockResult",
    "build_default_policy", "validate_policy", "evaluate_live_commit_safety_interlock", "evaluate_packet",
]
