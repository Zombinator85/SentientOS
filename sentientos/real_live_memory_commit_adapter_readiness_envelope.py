"""Deterministic disabled-by-default real live-memory adapter readiness envelope.

This module consumes supplied Final Live Memory Commit Review Gate packet evidence
and explicit adapter-readiness candidates. It emits metadata-only readiness,
hypothetical live receipt, rollback, abort, and post-commit verification
envelopes. It never writes, deletes, purges, indexes, persists, applies, merges,
completes tombs, assembles prompts, retrieves live context, executes actions,
discloses externally, touches real memory roots, invokes remote services, or
grants truth, policy, consent, or authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Mapping, Sequence

LiveAdapterReadinessStatus = Literal[
    "live_adapter_readiness_ready",
    "live_adapter_readiness_ready_with_warnings",
    "live_adapter_readiness_deferred_for_operator_review",
    "live_adapter_readiness_rejected",
    "live_adapter_readiness_blocked",
    "live_adapter_readiness_noop",
    "live_adapter_readiness_invalid",
    "live_adapter_readiness_failed",
]
LiveAdapterReadinessDecision = Literal[
    "live_adapter_readiness_ready_for_later_runtime_gate",
    "live_adapter_readiness_ready_with_warnings",
    "live_adapter_readiness_deferred_for_operator_review",
    "live_adapter_readiness_rejected",
    "live_adapter_readiness_blocked",
    "live_adapter_readiness_noop",
]

LIVE_ADAPTER_READINESS_CANDIDATE_TYPES = frozenset({
    "ai_capsule_live_adapter_readiness_candidate",
    "human_summary_live_adapter_readiness_candidate",
    "dual_capsule_live_adapter_readiness_candidate",
    "protect_receipt_live_adapter_readiness_candidate",
    "merge_receipt_live_adapter_readiness_candidate",
    "tomb_archive_live_adapter_readiness_candidate",
    "tomb_deferred_live_adapter_readiness_candidate",
    "operator_review_live_adapter_readiness_candidate",
    "noop_live_adapter_readiness_candidate",
    "mixed_live_adapter_readiness_candidate",
})
READY_FINAL_REVIEW_DECISIONS = frozenset({
    "final_live_commit_review_ready_for_future_adapter_implementation",
    "final_live_commit_review_ready_with_warnings",
    "final_live_commit_review_deferred_for_operator_review",
    "final_live_commit_review_rejected",
    "final_live_commit_review_noop",
})
INVARIANTS: dict[str, bool] = {
    "live_adapter_readiness_is_not_memory_write": True,
    "live_adapter_readiness_is_not_memory_deletion": True,
    "live_adapter_readiness_is_not_memory_purge": True,
    "live_adapter_readiness_is_not_index_mutation": True,
    "live_adapter_readiness_is_not_capsule_persistence": True,
    "live_adapter_readiness_is_not_tomb_completion": True,
    "live_adapter_readiness_is_not_prompt_assembly": True,
    "live_adapter_readiness_is_not_live_context_retrieval": True,
    "live_adapter_readiness_is_not_action_execution": True,
    "live_adapter_readiness_is_not_external_disclosure": True,
    "live_adapter_readiness_is_not_live_commit_execution": True,
    "live_adapter_readiness_is_not_truth": True,
    "live_adapter_readiness_is_not_policy": True,
    "live_adapter_readiness_is_not_authority": True,
    "live_adapter_readiness_is_not_consent": True,
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
    "remote_service_enabled": False,
    "adapter_runtime_execution_enabled": False,
    "future_explicit_runtime_execution_gate_required": True,
    "future_operator_runtime_confirmation_required": True,
}
SAFE_NEXT_ACTIONS = (
    "no_action_allowed",
    "inspect_live_adapter_readiness_packet",
    "inspect_final_live_memory_commit_review_packet",
    "operator_review_required",
    "prepare_future_explicit_runtime_execution_gate_later",
    "prepare_future_operator_runtime_confirmation_later",
    "rerun_with_ready_final_review_packet",
    "rerun_with_matching_final_review_digest",
    "rerun_with_matching_final_review_decision",
    "rerun_with_matching_real_root_admission_digest",
    "rerun_with_matching_real_root_admission_decision",
    "rerun_with_matching_sandbox_commit_digest",
    "rerun_with_matching_sandbox_commit_decision",
    "rerun_with_sandbox_receipt_manifest_digest",
    "rerun_with_sandbox_rollback_manifest_digest",
    "rerun_with_sandbox_artifact_plan",
    "rerun_with_live_receipt_schema_metadata",
    "rerun_with_live_rollback_schema_metadata",
    "rerun_with_post_commit_verification_plan",
    "rerun_with_abort_panic_stop_condition_metadata",
    "rerun_with_operator_runtime_confirmation_metadata",
    "rerun_with_real_adapter_implementation_metadata",
    "rerun_with_scope_alignment",
    "sustain_default_deny",
)
FORBIDDEN_NEXT_STEPS = (
    "write_live_memory_now", "delete_live_memory_now", "purge_live_memory_now", "mutate_vector_index", "mutate_live_index",
    "persist_capsule_now", "persist_summary_now", "apply_protection_now", "apply_merge_now", "complete_tomb_now",
    "run_real_live_commit_adapter_now", "treat_adapter_readiness_as_runtime_execution_permission", "treat_adapter_readiness_as_live_commit_execution",
    "treat_final_review_as_execution_permission", "treat_final_review_as_real_commit", "treat_sandbox_commit_as_real_commit",
    "treat_sandbox_receipt_as_live_receipt", "treat_sandbox_rollback_as_applied_rollback", "treat_real_root_admission_as_memory_root_access",
    "touch_real_memory_root", "open_real_memory_path_for_write", "assemble_prompt_now", "retrieve_live_context", "execute_action_ingress",
    "infer_truth_from_readiness", "infer_authority_from_readiness", "infer_consent_from_readiness", "convert_readiness_to_policy",
    "bypass_sandbox_commit_adapter", "bypass_real_root_admission_gate", "bypass_final_live_commit_review_gate", "bypass_future_explicit_runtime_execution_gate",
    "bypass_operator_runtime_confirmation", "direct_adapter_execution", "enable_external_disclosure",
)


def _digest(value: Mapping[str, Any] | Sequence[Any]) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item) for item in value)
    return ()


def _flag(mapping: Mapping[str, Any], *keys: str) -> bool:
    return any(mapping.get(key) is True for key in keys)


def _has_raw_payload(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).lower()
            if re.search(r"(^|_)(raw|private|secret|media|provider_prompt|payload)(_|$)", lowered):
                return True
            if _has_raw_payload(nested):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_has_raw_payload(item) for item in value)
    return False


@dataclass(frozen=True)
class LiveAdapterReadinessPolicy:
    schema_version: str = "real-live-memory-commit-adapter-readiness-envelope/v1"
    default_posture: str = "deny"
    require_ready_final_review: bool = True
    require_matching_final_review_digest: bool = True
    require_matching_final_review_decision: bool = True
    require_matching_real_root_admission_digest: bool = True
    require_matching_real_root_admission_decision: bool = True
    require_matching_sandbox_commit_digest: bool = True
    require_matching_sandbox_commit_decision: bool = True
    require_non_noop_sandbox_receipt_manifest_digest: bool = True
    require_non_noop_sandbox_rollback_manifest_digest: bool = True
    require_non_noop_sandbox_artifact_plan: bool = True
    require_non_noop_live_receipt_schema_metadata: bool = True
    require_non_noop_live_rollback_schema_metadata: bool = True
    require_non_noop_post_commit_verification_plan: bool = True
    require_non_noop_abort_panic_stop_condition_metadata: bool = True
    require_non_noop_operator_runtime_confirmation_metadata: bool = True
    require_non_noop_real_adapter_implementation_metadata: bool = True
    require_scope_alignment: bool = True
    allow_mixed_scope_diagnostic_packet: bool = True
    block_live_mutation_claims: bool = True
    block_real_memory_root_access_claims: bool = True
    block_readiness_execution_claims: bool = True
    block_final_review_conversion_claims: bool = True
    block_sandbox_conversion_claims: bool = True
    block_real_root_admission_conversion_claims: bool = True
    block_prompt_materialization: bool = True
    block_live_context_retrieval: bool = True
    block_action_execution: bool = True
    block_external_disclosure: bool = True
    block_authority_smuggling: bool = True
    block_consent_smuggling: bool = True
    block_policy_smuggling: bool = True
    block_truth_smuggling: bool = True
    block_raw_payload_leakage: bool = True
    adapter_runtime_execution_enabled: bool = False


@dataclass(frozen=True)
class LiveAdapterReadinessFinding:
    severity: str
    code: str
    message: str
    candidate_id: str = ""
    record_id: str = ""
    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class LiveAdapterReadinessCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    claimed_final_review_digest: str
    claimed_final_review_decision: str
    claimed_real_root_admission_digest: str
    claimed_real_root_admission_decision: str
    claimed_sandbox_commit_digest: str
    claimed_sandbox_commit_decision: str
    claimed_sandbox_receipt_manifest_digest: str
    claimed_sandbox_rollback_manifest_digest: str
    operator_scope_keys: tuple[str, ...]
    sandbox_artifact_plan: Mapping[str, Any]
    live_receipt_schema_metadata: Mapping[str, Any]
    live_rollback_schema_metadata: Mapping[str, Any]
    post_commit_verification_plan: Mapping[str, Any]
    abort_panic_stop_condition_metadata: Mapping[str, Any]
    operator_runtime_confirmation_metadata: Mapping[str, Any]
    real_adapter_implementation_metadata: Mapping[str, Any]
    readiness_claims: Mapping[str, Any]
    metadata: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "LiveAdapterReadinessCandidate":
        return cls(
            candidate_id=str(raw.get("candidate_id") or ""), record_id=str(raw.get("record_id") or raw.get("candidate_id") or ""), candidate_type=str(raw.get("candidate_type") or ""),
            claimed_final_review_digest=str(raw.get("claimed_final_review_digest") or raw.get("final_review_digest") or ""),
            claimed_final_review_decision=str(raw.get("claimed_final_review_decision") or raw.get("final_review_decision") or ""),
            claimed_real_root_admission_digest=str(raw.get("claimed_real_root_admission_digest") or raw.get("real_root_admission_digest") or ""),
            claimed_real_root_admission_decision=str(raw.get("claimed_real_root_admission_decision") or raw.get("real_root_admission_decision") or ""),
            claimed_sandbox_commit_digest=str(raw.get("claimed_sandbox_commit_digest") or raw.get("sandbox_commit_digest") or ""),
            claimed_sandbox_commit_decision=str(raw.get("claimed_sandbox_commit_decision") or raw.get("sandbox_commit_decision") or ""),
            claimed_sandbox_receipt_manifest_digest=str(raw.get("claimed_sandbox_receipt_manifest_digest") or raw.get("sandbox_receipt_manifest_digest") or ""),
            claimed_sandbox_rollback_manifest_digest=str(raw.get("claimed_sandbox_rollback_manifest_digest") or raw.get("sandbox_rollback_manifest_digest") or ""),
            operator_scope_keys=_as_tuple(raw.get("operator_scope_keys")), sandbox_artifact_plan=_as_mapping(raw.get("sandbox_artifact_plan")),
            live_receipt_schema_metadata=_as_mapping(raw.get("live_receipt_schema_metadata")), live_rollback_schema_metadata=_as_mapping(raw.get("live_rollback_schema_metadata")),
            post_commit_verification_plan=_as_mapping(raw.get("post_commit_verification_plan")), abort_panic_stop_condition_metadata=_as_mapping(raw.get("abort_panic_stop_condition_metadata") or raw.get("abort_panic_stop_condition_plan")),
            operator_runtime_confirmation_metadata=_as_mapping(raw.get("operator_runtime_confirmation_metadata")), real_adapter_implementation_metadata=_as_mapping(raw.get("real_adapter_implementation_metadata") or raw.get("future_real_adapter_implementation_metadata")),
            readiness_claims=_as_mapping(raw.get("readiness_claims") or raw.get("claims")), metadata=_as_mapping(raw.get("metadata")),
        )
    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class LiveAdapterReadinessRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    readiness_decision: LiveAdapterReadinessDecision
    final_review_decision: str
    final_review_digest: str
    final_review_record_digest: str
    real_root_admission_decision: str
    real_root_admission_digest: str
    sandbox_commit_decision: str
    sandbox_commit_digest: str
    sandbox_receipt_manifest_digest: str
    sandbox_rollback_manifest_digest: str
    operator_scope_keys: tuple[str, ...]
    final_review_scope_keys: tuple[str, ...]
    real_root_admission_scope_keys: tuple[str, ...]
    sandbox_scope_keys: tuple[str, ...]
    sandbox_artifact_plan: Mapping[str, Any]
    hypothetical_live_receipt_envelope: Mapping[str, Any]
    hypothetical_rollback_envelope: Mapping[str, Any]
    abort_panic_stop_condition_envelope: Mapping[str, Any]
    post_commit_verification_envelope: Mapping[str, Any]
    operator_runtime_confirmation_metadata: Mapping[str, Any]
    real_adapter_implementation_metadata: Mapping[str, Any]
    safe_next_actions: tuple[str, ...]
    adapter_readiness_future_runtime_gate_record: Mapping[str, Any]
    adapter_readiness_future_gate_only: bool = True
    adapter_readiness_is_runtime_execution_permission: bool = False
    adapter_readiness_has_executed_live_commit: bool = False
    final_review_is_execution_permission: bool = False
    final_review_is_real_commit: bool = False
    sandbox_commit_is_real_commit: bool = False
    sandbox_receipt_is_live_receipt: bool = False
    sandbox_rollback_is_applied_rollback: bool = False
    real_root_admission_is_memory_root_access: bool = False
    real_memory_root_access_performed: bool = False
    live_memory_write_claimed: bool = False
    live_memory_delete_claimed: bool = False
    live_memory_purge_claimed: bool = False
    live_index_mutation_claimed: bool = False
    prompt_assembly_claimed: bool = False
    live_context_retrieval_claimed: bool = False
    action_execution_claimed: bool = False
    external_disclosure_claimed: bool = False
    authority_claimed: bool = False
    consent_claimed: bool = False
    policy_claimed: bool = False
    truth_claimed: bool = False
    digest: str = ""
    def to_dict(self) -> dict[str, Any]: return asdict(self)
    def with_digest(self) -> "LiveAdapterReadinessRecord":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class LiveAdapterReadinessPacket:
    schema_version: str
    records: tuple[LiveAdapterReadinessRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""
    live_adapter_readiness_is_not_memory_write: bool = True
    live_adapter_readiness_is_not_memory_deletion: bool = True
    live_adapter_readiness_is_not_memory_purge: bool = True
    live_adapter_readiness_is_not_index_mutation: bool = True
    live_adapter_readiness_is_not_capsule_persistence: bool = True
    live_adapter_readiness_is_not_tomb_completion: bool = True
    live_adapter_readiness_is_not_prompt_assembly: bool = True
    live_adapter_readiness_is_not_live_context_retrieval: bool = True
    live_adapter_readiness_is_not_action_execution: bool = True
    live_adapter_readiness_is_not_external_disclosure: bool = True
    live_adapter_readiness_is_not_live_commit_execution: bool = True
    live_adapter_readiness_is_not_truth: bool = True
    live_adapter_readiness_is_not_policy: bool = True
    live_adapter_readiness_is_not_authority: bool = True
    live_adapter_readiness_is_not_consent: bool = True
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
    remote_service_enabled: bool = False
    adapter_runtime_execution_enabled: bool = False
    future_explicit_runtime_execution_gate_required: bool = True
    future_operator_runtime_confirmation_required: bool = True
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self); data["records"] = [r.to_dict() for r in self.records]; return data
    def with_digest(self) -> "LiveAdapterReadinessPacket":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class LiveAdapterReadinessReport:
    status: LiveAdapterReadinessStatus
    findings: tuple[LiveAdapterReadinessFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""
    def to_dict(self) -> dict[str, Any]: return {"status": self.status, "findings": [f.to_dict() for f in self.findings], "summary_counts": dict(sorted(self.summary_counts.items())), "digest": self.digest}


@dataclass(frozen=True)
class LiveAdapterReadinessResult:
    status: LiveAdapterReadinessStatus
    packet: LiveAdapterReadinessPacket | None
    report: LiveAdapterReadinessReport
    digest: str
    def to_dict(self) -> dict[str, Any]: return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> LiveAdapterReadinessPolicy: return LiveAdapterReadinessPolicy()


def validate_policy(policy: LiveAdapterReadinessPolicy | Mapping[str, Any] | None = None) -> dict[str, Any]:
    raw = asdict(policy) if isinstance(policy, LiveAdapterReadinessPolicy) else dict(policy or asdict(build_default_policy()))
    findings: list[dict[str, str]] = []
    if raw.get("default_posture") != "deny": findings.append({"severity": "error", "code": "default_posture_not_deny", "message": "adapter readiness must default deny"})
    for key, expected in INVARIANTS.items():
        if raw.get(key, expected) != expected: findings.append({"severity": "error", "code": f"invariant_{key}_changed", "message": f"{key} must remain {expected}"})
    status = "invalid" if findings else "valid"
    return {"status": status, "findings": findings, "policy": raw, "digest": _digest({"status": status, "findings": findings, "policy": raw})}


def _policy_from_payload(payload: Mapping[str, Any], policy: LiveAdapterReadinessPolicy | None) -> LiveAdapterReadinessPolicy:
    if policy is not None: return policy
    raw = _as_mapping(payload.get("policy"))
    if raw:
        allowed = set(LiveAdapterReadinessPolicy.__dataclass_fields__)
        return LiveAdapterReadinessPolicy(**{str(k): v for k, v in raw.items() if str(k) in allowed})
    return build_default_policy()


def _candidate_payloads(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = payload.get("live_adapter_readiness_candidates", payload.get("live_adapter_readiness_candidate", payload.get("candidates", ())))
    if isinstance(raw, Mapping): return (_as_mapping(raw),)
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)): return tuple(_as_mapping(item) for item in raw)
    return ()


def _blocked(code: str, findings: Sequence[LiveAdapterReadinessFinding] | None = None) -> LiveAdapterReadinessResult:
    finding_list = tuple(findings or (LiveAdapterReadinessFinding("error", code, code.replace("_", " ")),))
    report = LiveAdapterReadinessReport("live_adapter_readiness_blocked", finding_list, {"candidate_count": 0, "error_count": sum(1 for f in finding_list if f.severity == "error")})
    report = replace(report, digest=_digest(report.to_dict()))
    return LiveAdapterReadinessResult("live_adapter_readiness_blocked", None, report, _digest({"packet": None, "report": report.to_dict()}))


def _claims_blocker(candidate: LiveAdapterReadinessCandidate, policy: LiveAdapterReadinessPolicy) -> str | None:
    claims, metadata = candidate.readiness_claims, candidate.metadata
    all_data = {"claims": claims, "metadata": metadata, "sandbox_artifact_plan": candidate.sandbox_artifact_plan, "live_receipt_schema_metadata": candidate.live_receipt_schema_metadata, "live_rollback_schema_metadata": candidate.live_rollback_schema_metadata, "post_commit_verification_plan": candidate.post_commit_verification_plan, "abort_panic_stop_condition_metadata": candidate.abort_panic_stop_condition_metadata, "operator_runtime_confirmation_metadata": candidate.operator_runtime_confirmation_metadata, "real_adapter_implementation_metadata": candidate.real_adapter_implementation_metadata}
    if policy.block_raw_payload_leakage and _has_raw_payload(all_data): return "raw_payload_leak"
    if policy.block_real_memory_root_access_claims and (_flag(claims, "real_memory_root_access", "touches_real_memory_root", "opens_real_memory_path") or metadata.get("real_memory_root_access_claimed") is True): return "real_memory_root_access_claim"
    for keys, code in [(("live_write", "writes_live_memory", "real_memory_write"), "live_write_claim"), (("live_delete", "deletes_live_memory"), "live_delete_claim"), (("live_purge", "purges_live_memory"), "live_purge_claim"), (("index_mutation", "mutates_index", "mutates_live_index"), "index_mutation_claim")]:
        if policy.block_live_mutation_claims and (_flag(claims, *keys) or metadata.get(code.replace("_claim", "_claimed")) is True): return code
    for keys, code in [(("capsule_persistence", "persists_capsule", "persists_summary"), "capsule_persistence_claim"), (("tomb_completion", "completes_tomb"), "tomb_completion_claim"), (("protection_application", "applies_protection"), "protection_application_claim"), (("merge_application", "applies_merge"), "merge_application_claim")]:
        if policy.block_live_mutation_claims and (_flag(claims, *keys) or metadata.get(code.replace("_claim", "_claimed")) is True): return code
    if policy.block_readiness_execution_claims and (_flag(claims, "readiness_has_executed_live_commit", "adapter_readiness_is_runtime_execution_permission", "permission_to_execute_live_commit_now", "run_adapter_now") or metadata.get("adapter_readiness_has_executed_live_commit") is True or metadata.get("adapter_readiness_is_runtime_execution_permission") is True): return "adapter_readiness_execution_claim"
    if policy.block_final_review_conversion_claims and (_flag(claims, "final_review_is_execution_permission", "final_review_is_real_commit") or metadata.get("final_review_is_execution_permission") is True): return "final_review_conversion_claim"
    if policy.block_sandbox_conversion_claims and (_flag(claims, "sandbox_commit_is_real_commit", "sandbox_receipt_is_live_receipt", "sandbox_rollback_is_applied_rollback") or metadata.get("sandbox_commit_is_real_commit") is True or metadata.get("sandbox_receipt_is_live_receipt") is True or metadata.get("sandbox_rollback_is_applied_rollback") is True): return "sandbox_conversion_claim"
    if policy.block_real_root_admission_conversion_claims and (_flag(claims, "real_root_admission_is_memory_root_access") or metadata.get("real_root_admission_is_memory_root_access") is True): return "real_root_admission_conversion_claim"
    if policy.block_prompt_materialization and (_flag(claims, "prompt_materialization", "assembles_prompt") or metadata.get("prompt_materialization_claimed") is True): return "prompt_materialization"
    if policy.block_live_context_retrieval and (_flag(claims, "live_context_retrieval", "retrieves_live_context") or metadata.get("live_context_retrieval_claimed") is True): return "live_context_retrieval"
    if policy.block_action_execution and (_flag(claims, "action_execution", "executes_action") or metadata.get("action_execution_claimed") is True): return "action_execution"
    if policy.block_external_disclosure and (_flag(claims, "external_disclosure", "discloses_externally") or metadata.get("external_disclosure_claimed") is True): return "external_disclosure"
    if policy.block_authority_smuggling and (_flag(claims, "authority", "grants_authority") or metadata.get("authority_claimed") is True): return "authority_smuggling"
    if policy.block_consent_smuggling and (_flag(claims, "consent", "infers_consent") or metadata.get("consent_claimed") is True): return "consent_smuggling"
    if policy.block_policy_smuggling and (_flag(claims, "policy", "creates_policy") or metadata.get("policy_claimed") is True): return "policy_smuggling"
    if policy.block_truth_smuggling and (_flag(claims, "truth", "infers_truth") or metadata.get("truth_claimed") is True): return "truth_smuggling"
    return None


def _decision_for(candidate: LiveAdapterReadinessCandidate, final_decision: str, warning: bool) -> LiveAdapterReadinessDecision:
    if candidate.candidate_type == "noop_live_adapter_readiness_candidate" or final_decision == "final_live_commit_review_noop": return "live_adapter_readiness_noop"
    if final_decision == "final_live_commit_review_deferred_for_operator_review" or candidate.candidate_type == "operator_review_live_adapter_readiness_candidate": return "live_adapter_readiness_deferred_for_operator_review"
    if final_decision == "final_live_commit_review_rejected": return "live_adapter_readiness_rejected"
    if warning: return "live_adapter_readiness_ready_with_warnings"
    return "live_adapter_readiness_ready_for_later_runtime_gate"


def _safe_actions(decision: str) -> tuple[str, ...]:
    base = ["no_action_allowed", "inspect_live_adapter_readiness_packet", "inspect_final_live_memory_commit_review_packet", "sustain_default_deny"]
    if decision in {"live_adapter_readiness_ready_for_later_runtime_gate", "live_adapter_readiness_ready_with_warnings"}: base.extend(["prepare_future_explicit_runtime_execution_gate_later", "prepare_future_operator_runtime_confirmation_later"])
    if decision == "live_adapter_readiness_deferred_for_operator_review": base.append("operator_review_required")
    return tuple(dict.fromkeys(base))


def evaluate_real_live_memory_commit_adapter_readiness_envelope(payload: Mapping[str, Any], policy: LiveAdapterReadinessPolicy | None = None) -> LiveAdapterReadinessResult:
    try:
        active_policy = _policy_from_payload(payload, policy)
        final_packet = _as_mapping(payload.get("final_live_memory_commit_review_packet") or payload.get("final_live_commit_review_packet"))
        if not final_packet: return _blocked("missing_final_review_packet")
        final_records_raw = final_packet.get("records")
        if not isinstance(final_records_raw, Sequence) or isinstance(final_records_raw, (str, bytes, bytearray)) or not final_records_raw:
            return _blocked("invalid_final_review_packet")
        final_record = _as_mapping(final_records_raw[0])
        final_digest = str(final_packet.get("digest") or "")
        final_decision = str(final_record.get("review_decision") or final_record.get("final_review_decision") or "")
        if active_policy.require_ready_final_review and final_decision not in READY_FINAL_REVIEW_DECISIONS:
            return _blocked("final_review_not_ready")
        candidates = _candidate_payloads(payload)
        if not candidates: return _blocked("missing_live_adapter_readiness_candidate")
        findings: list[LiveAdapterReadinessFinding] = []
        records: list[LiveAdapterReadinessRecord] = []
        for raw_candidate in candidates:
            candidate = LiveAdapterReadinessCandidate.from_mapping(raw_candidate)
            if not candidate.candidate_id or candidate.candidate_type not in LIVE_ADAPTER_READINESS_CANDIDATE_TYPES:
                return _blocked("invalid_live_adapter_readiness_candidate")
            claim_blocker = _claims_blocker(candidate, active_policy)
            if claim_blocker:
                return _blocked(claim_blocker, [LiveAdapterReadinessFinding("error", claim_blocker, claim_blocker.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            non_noop = candidate.candidate_type != "noop_live_adapter_readiness_candidate"
            if active_policy.require_matching_final_review_digest and candidate.claimed_final_review_digest != final_digest:
                return _blocked("final_review_digest_mismatch", [LiveAdapterReadinessFinding("error", "final_review_digest_mismatch", "candidate final review digest does not match supplied final review packet", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_final_review_decision and candidate.claimed_final_review_decision != final_decision:
                return _blocked("final_review_decision_mismatch", [LiveAdapterReadinessFinding("error", "final_review_decision_mismatch", "candidate final review decision does not match supplied final review record", candidate.candidate_id, candidate.record_id)])
            real_digest = str(final_record.get("real_root_admission_digest") or "")
            real_decision = str(final_record.get("real_root_admission_decision") or "")
            sandbox_digest = str(final_record.get("sandbox_commit_digest") or "")
            sandbox_decision = str(final_record.get("sandbox_commit_decision") or "")
            if active_policy.require_matching_real_root_admission_digest and candidate.claimed_real_root_admission_digest != real_digest: return _blocked("real_root_admission_digest_mismatch")
            if active_policy.require_matching_real_root_admission_decision and candidate.claimed_real_root_admission_decision != real_decision: return _blocked("real_root_admission_decision_mismatch")
            if active_policy.require_matching_sandbox_commit_digest and candidate.claimed_sandbox_commit_digest != sandbox_digest: return _blocked("sandbox_commit_digest_mismatch")
            if active_policy.require_matching_sandbox_commit_decision and candidate.claimed_sandbox_commit_decision != sandbox_decision: return _blocked("sandbox_commit_decision_mismatch")
            if non_noop:
                required = [
                    (candidate.claimed_sandbox_receipt_manifest_digest, "missing_sandbox_receipt_manifest_digest"),
                    (candidate.claimed_sandbox_rollback_manifest_digest, "missing_sandbox_rollback_manifest_digest"),
                    (candidate.sandbox_artifact_plan, "missing_sandbox_artifact_plan"),
                    (candidate.live_receipt_schema_metadata, "missing_live_receipt_schema_metadata"),
                    (candidate.live_rollback_schema_metadata, "missing_live_rollback_schema_metadata"),
                    (candidate.post_commit_verification_plan, "missing_post_commit_verification_plan"),
                    (candidate.abort_panic_stop_condition_metadata, "missing_abort_panic_stop_condition_metadata"),
                    (candidate.operator_runtime_confirmation_metadata, "missing_operator_runtime_confirmation_metadata"),
                    (candidate.real_adapter_implementation_metadata, "missing_real_adapter_implementation_metadata"),
                ]
                for value, code in required:
                    if not value: return _blocked(code, [LiveAdapterReadinessFinding("error", code, code.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            final_scope = _as_tuple(final_record.get("operator_scope_keys"))
            real_scope = _as_tuple(final_record.get("real_root_admission_scope_keys"))
            sandbox_scope = _as_tuple(final_record.get("sandbox_scope_keys"))
            if active_policy.require_scope_alignment:
                scope_sets = [set(scope) for scope in (candidate.operator_scope_keys, final_scope, real_scope, sandbox_scope) if scope]
                aligned = not scope_sets or all(scope == scope_sets[0] for scope in scope_sets)
                if not aligned:
                    if active_policy.allow_mixed_scope_diagnostic_packet and candidate.candidate_type == "mixed_live_adapter_readiness_candidate" and candidate.metadata.get("diagnostic_warning") is True:
                        findings.append(LiveAdapterReadinessFinding("warning", "scope_mismatch_diagnostic", "scope mismatch allowed for diagnostic packet", candidate.candidate_id, candidate.record_id))
                    else:
                        return _blocked("scope_mismatch")
            warning = bool(candidate.metadata.get("warning_only") or candidate.metadata.get("diagnostic_warning")) or final_decision.endswith("with_warnings") or any(f.severity == "warning" and f.candidate_id == candidate.candidate_id for f in findings)
            if warning: findings.append(LiveAdapterReadinessFinding("warning", "live_adapter_readiness_warning", "candidate is warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
            decision = _decision_for(candidate, final_decision, warning)
            receipt = {"schema": dict(candidate.live_receipt_schema_metadata), "hypothetical_only": True, "live_receipt_emitted": False, "live_commit_performed": False}
            rollback = {"schema": dict(candidate.live_rollback_schema_metadata), "hypothetical_only": True, "rollback_applied": False}
            abort = {"metadata": dict(candidate.abort_panic_stop_condition_metadata), "panic_stop_required": bool(candidate.abort_panic_stop_condition_metadata), "hypothetical_only": True}
            post = {"plan": dict(candidate.post_commit_verification_plan), "post_commit_verification_performed": False, "hypothetical_only": True}
            future_record = {"candidate_id": candidate.candidate_id, "eligible_for_future_explicit_runtime_execution_gate": decision in {"live_adapter_readiness_ready_for_later_runtime_gate", "live_adapter_readiness_ready_with_warnings"}, "decision": decision, "real_live_commit_performed": False, "real_memory_root_access_performed": False, "adapter_runtime_execution_enabled": False, "future_explicit_runtime_execution_gate_required": True, "future_operator_runtime_confirmation_required": True, "operator_review_cannot_override_hard_blockers": True}
            records.append(LiveAdapterReadinessRecord(candidate.candidate_id, candidate.record_id, candidate.candidate_type, decision, final_decision, final_digest, str(final_record.get("digest") or ""), real_decision, real_digest, sandbox_decision, sandbox_digest, candidate.claimed_sandbox_receipt_manifest_digest, candidate.claimed_sandbox_rollback_manifest_digest, candidate.operator_scope_keys, final_scope, real_scope, sandbox_scope, dict(candidate.sandbox_artifact_plan), receipt, rollback, abort, post, dict(candidate.operator_runtime_confirmation_metadata), dict(candidate.real_adapter_implementation_metadata), _safe_actions(decision), future_record).with_digest())
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for f in findings if f.severity == "warning")}
        for record in records:
            counts[record.readiness_decision] = counts.get(record.readiness_decision, 0) + 1; counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {record.readiness_decision for record in records}
        if counts["warning_count"] or "live_adapter_readiness_ready_with_warnings" in decisions: status: LiveAdapterReadinessStatus = "live_adapter_readiness_ready_with_warnings"
        elif decisions <= {"live_adapter_readiness_noop"}: status = "live_adapter_readiness_noop"
        elif decisions <= {"live_adapter_readiness_deferred_for_operator_review"}: status = "live_adapter_readiness_deferred_for_operator_review"
        elif decisions <= {"live_adapter_readiness_rejected"}: status = "live_adapter_readiness_rejected"
        else: status = "live_adapter_readiness_ready"
        packet = LiveAdapterReadinessPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = LiveAdapterReadinessReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return LiveAdapterReadinessResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("failed", [LiveAdapterReadinessFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: LiveAdapterReadinessPolicy | None = None) -> LiveAdapterReadinessResult:
    return evaluate_real_live_memory_commit_adapter_readiness_envelope(payload, policy)


__all__ = [
    "FORBIDDEN_NEXT_STEPS", "INVARIANTS", "LIVE_ADAPTER_READINESS_CANDIDATE_TYPES", "READY_FINAL_REVIEW_DECISIONS", "SAFE_NEXT_ACTIONS",
    "LiveAdapterReadinessCandidate", "LiveAdapterReadinessFinding", "LiveAdapterReadinessPacket", "LiveAdapterReadinessPolicy", "LiveAdapterReadinessRecord", "LiveAdapterReadinessReport", "LiveAdapterReadinessResult",
    "build_default_policy", "validate_policy", "evaluate_real_live_memory_commit_adapter_readiness_envelope", "evaluate_packet",
]
