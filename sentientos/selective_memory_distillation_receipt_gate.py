"""Deterministic metadata-only receipt gate for selective memory distillation.

The gate evaluates caller-supplied JSON metadata only. It never writes memory,
deletes memory, completes tombs, persists capsules, assembles prompts, executes
actions, invokes remote services, discloses externally, or grants authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal, Mapping, Sequence

ReceiptGateStatus = Literal[
    "selective_memory_receipt_gate_ready",
    "selective_memory_receipt_gate_ready_with_warnings",
    "selective_memory_receipt_gate_blocked_missing_distillation_packet",
    "selective_memory_receipt_gate_blocked_invalid_distillation_packet",
    "selective_memory_receipt_gate_blocked_missing_receipt_candidate",
    "selective_memory_receipt_gate_blocked_invalid_receipt_candidate",
    "selective_memory_receipt_gate_blocked_decision_mismatch",
    "selective_memory_receipt_gate_blocked_digest_mismatch",
    "selective_memory_receipt_gate_blocked_tomb_intent_missing",
    "selective_memory_receipt_gate_blocked_tomb_receipt_claimed",
    "selective_memory_receipt_gate_blocked_capsule_payload_unsafe",
    "selective_memory_receipt_gate_blocked_raw_payload_leak",
    "selective_memory_receipt_gate_blocked_authority_smuggling",
    "selective_memory_receipt_gate_blocked_prompt_materialization",
    "selective_memory_receipt_gate_blocked_runtime_memory_mutation",
    "selective_memory_receipt_gate_blocked_external_disclosure",
    "selective_memory_receipt_gate_blocked_scope_mismatch",
    "selective_memory_receipt_gate_invalid",
    "selective_memory_receipt_gate_failed",
]

ReceiptGateDecision = Literal[
    "receipt_candidate_admissible",
    "receipt_candidate_admissible_with_warnings",
    "receipt_candidate_deferred_for_operator_review",
    "receipt_candidate_blocked",
    "receipt_candidate_rejected",
    "receipt_candidate_noop",
]

RECEIPT_CANDIDATE_TYPES = frozenset({
    "ai_capsule_write_receipt_candidate",
    "human_summary_write_receipt_candidate",
    "dual_capsule_write_receipt_candidate",
    "tomb_intent_receipt_candidate",
    "tomb_after_distillation_receipt_candidate",
    "protect_memory_receipt_candidate",
    "merge_capsule_receipt_candidate",
    "operator_review_receipt_candidate",
    "defer_receipt_candidate",
    "reject_record_receipt_candidate",
    "no_op_receipt_candidate",
})

SAFE_NEXT_ACTIONS = (
    "no_action_allowed",
    "inspect_receipt_gate_packet",
    "operator_review_required",
    "prepare_capsule_writer_later",
    "prepare_tomb_receipt_writer_later",
    "prepare_protect_receipt_later",
    "prepare_merge_receipt_later",
    "rerun_with_matching_digest",
    "rerun_with_tomb_intent",
    "rerun_with_safe_capsule",
    "rerun_with_scope_alignment",
    "defer_to_memory_runtime_boundary",
    "defer_to_self_improvement_ingress",
)

FORBIDDEN_NEXT_STEPS = (
    "write_memory_now",
    "delete_memory_now",
    "purge_memory_now",
    "mutate_raw_fragment",
    "mutate_vector_index",
    "mutate_distilled_memory",
    "claim_tomb_completed",
    "claim_capsule_written",
    "claim_protection_applied",
    "claim_merge_applied",
    "call_append_memory",
    "call_purge_memory",
    "call_apply_forgetting_curve",
    "call_curate_memory",
    "call_summarize_memory",
    "assemble_prompt_now",
    "retrieve_live_context",
    "execute_action_ingress",
    "infer_truth_from_receipt",
    "infer_authority_from_receipt",
    "infer_consent_from_receipt",
    "convert_receipt_to_policy",
    "convert_receipt_gate_to_action",
    "bypass_distillation_contract",
    "bypass_memory_tomb",
    "bypass_operator_review",
    "enable_external_disclosure",
)

_NON_AUTHORITY_INVARIANTS: dict[str, bool] = {
    "receipt_gate_is_not_memory_write": True,
    "receipt_gate_is_not_deletion": True,
    "receipt_gate_is_not_tomb_completion": True,
    "receipt_gate_is_not_prompt_assembly": True,
    "receipt_gate_is_not_policy": True,
    "receipt_gate_is_not_authority": True,
    "receipt_gate_does_not_execute_action": True,
    "receipt_gate_does_not_disclose_externally": True,
    "runtime_memory_mutation_enabled": False,
    "prompt_materialization_enabled": False,
    "external_disclosure_enabled": False,
    "remote_service_enabled": False,
}

_RAW_KEYS = frozenset({"raw_payload", "raw_private_payload", "raw_transcript", "provider_prompt", "secret", "api_key", "password", "token"})
_MEDIA_KEYS = frozenset({"image", "images", "audio", "video", "screenshot", "thumbnail", "media_payload", "encoded_media", "base64", "bytes", "raw_media"})
_MEDIA_RE = re.compile(r"(?:data:(?:image|audio|video)/|base64|[A-Za-z0-9+/]{120,}={0,2})")
_AUTHORITY_RE = re.compile(r"\b(authority|authorize|grant permission|policy now|consent granted|infer consent|infer authority|convert.*policy|approved to act|override blocker)\b", re.I)
_PROMPT_RE = re.compile(r"\b(assemble prompt|prompt materialization|provider prompt|system prompt|retrieve live context)\b", re.I)
_RUNTIME_RE = re.compile(r"\b(write memory|delete memory|purge memory|append_memory|purge_memory|apply_forgetting_curve|curate_memory|summarize_memory|mutate vector|mutate index|capsule written|protection applied|merge applied)\b", re.I)
_EXTERNAL_RE = re.compile(r"\b(external disclosure|remote service|send to api|webhook|provider api|network api|github api)\b", re.I)
_ACTION_RE = re.compile(r"\b(execute action|action ingress|host actuation|run actuator)\b", re.I)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return tuple(str(item) for item in value)
    return (str(value),)


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return _canonical_json(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return " ".join(_text(item) for item in value)
    return str(value)


@dataclass(frozen=True)
class SelectiveMemoryDistillationReceiptGatePolicy:
    schema_version: str = "selective-memory-distillation-receipt-gate.v1"
    allow_mixed_scope_diagnostic_packet: bool = False
    allow_warning_receipts: bool = True
    allow_operator_review_receipts: bool = True
    allow_noop_receipts: bool = True
    require_matching_source_digest: bool = True
    require_tomb_intent_for_tomb_receipts: bool = True
    require_capsule_safety_scan: bool = True
    require_scope_alignment: bool = True
    block_applied_state_claims: bool = True
    block_hard_override_attempts: bool = True


@dataclass(frozen=True)
class SelectiveMemoryDistillationReceiptCandidate:
    candidate_id: str
    receipt_candidate_type: str
    record_id: str
    claimed_distillation_decision: str
    source_digest: str
    source_scope_keys: tuple[str, ...] = ()
    claimed_packet_digest: str | None = None
    requested_next_actions: tuple[str, ...] = ()
    tomb_intent_id: str | None = None
    tomb_intent_digest: str | None = None
    capsule_metadata: Mapping[str, Any] = field(default_factory=dict)
    receipt_metadata: Mapping[str, Any] = field(default_factory=dict)
    future_intent_only: bool = True
    applied_state_claimed: bool = False
    deletion_performed: bool = False
    hard_override_requested: bool = False
    memory_mutation_requested: bool = False
    prompt_materialization_requested: bool = False
    external_disclosure_requested: bool = False
    action_execution_requested: bool = False
    policy_creation_claimed: bool = False
    authority_grant_claimed: bool = False
    consent_inference_claimed: bool = False

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "SelectiveMemoryDistillationReceiptCandidate":
        if not isinstance(payload, Mapping):
            raise ValueError("candidate_not_mapping")
        candidate_id = str(payload.get("candidate_id") or payload.get("receipt_candidate_id") or "")
        candidate_type = str(payload.get("receipt_candidate_type") or payload.get("candidate_type") or "")
        record_id = str(payload.get("record_id") or payload.get("distillation_record_id") or "")
        decision = str(payload.get("claimed_distillation_decision") or payload.get("distillation_decision") or "")
        source_digest = str(payload.get("source_digest") or payload.get("claimed_source_digest") or "")
        if not candidate_id or not candidate_type or not record_id or not decision or not source_digest:
            raise ValueError("candidate_id_type_record_decision_source_digest_required")
        return cls(
            candidate_id=candidate_id,
            receipt_candidate_type=candidate_type,
            record_id=record_id,
            claimed_distillation_decision=decision,
            source_digest=source_digest,
            source_scope_keys=_as_tuple(payload.get("source_scope_keys")),
            claimed_packet_digest=str(payload["claimed_packet_digest"]) if payload.get("claimed_packet_digest") is not None else None,
            requested_next_actions=_as_tuple(payload.get("requested_next_actions")),
            tomb_intent_id=str(payload["tomb_intent_id"]) if payload.get("tomb_intent_id") is not None else None,
            tomb_intent_digest=str(payload["tomb_intent_digest"]) if payload.get("tomb_intent_digest") is not None else None,
            capsule_metadata=dict(payload.get("capsule_metadata") or {}) if isinstance(payload.get("capsule_metadata") or {}, Mapping) else {},
            receipt_metadata=dict(payload.get("receipt_metadata") or payload.get("metadata") or {}) if isinstance(payload.get("receipt_metadata") or payload.get("metadata") or {}, Mapping) else {},
            future_intent_only=bool(payload.get("future_intent_only", True)),
            applied_state_claimed=bool(payload.get("applied_state_claimed", False) or payload.get("claim_applied", False)),
            deletion_performed=bool(payload.get("deletion_performed", False) or payload.get("tomb_completed", False) or payload.get("claim_tomb_completed", False)),
            hard_override_requested=bool(payload.get("hard_override_requested", False) or payload.get("override_hard_blocker", False)),
            memory_mutation_requested=bool(payload.get("memory_mutation_requested", False) or payload.get("runtime_memory_mutation_requested", False)),
            prompt_materialization_requested=bool(payload.get("prompt_materialization_requested", False)),
            external_disclosure_requested=bool(payload.get("external_disclosure_requested", False)),
            action_execution_requested=bool(payload.get("action_execution_requested", False)),
            policy_creation_claimed=bool(payload.get("policy_creation_claimed", False) or payload.get("converts_to_policy", False)),
            authority_grant_claimed=bool(payload.get("authority_grant_claimed", False) or payload.get("grants_authority", False)),
            consent_inference_claimed=bool(payload.get("consent_inference_claimed", False) or payload.get("infers_consent", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectiveMemoryDistillationReceiptGateInput:
    distillation_packet: Mapping[str, Any]
    receipt_candidates: tuple[SelectiveMemoryDistillationReceiptCandidate, ...]


@dataclass(frozen=True)
class SelectiveMemoryDistillationReceiptFinding:
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    candidate_id: str | None = None
    record_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectiveMemoryDistillationReceiptDecision:
    candidate_id: str
    record_id: str
    receipt_candidate_type: str
    claimed_distillation_decision: str
    gate_decision: ReceiptGateDecision
    safe_next_actions: tuple[str, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    receipt_gate_is_not_memory_write: bool = True
    receipt_gate_is_not_deletion: bool = True
    receipt_gate_is_not_tomb_completion: bool = True
    receipt_gate_is_not_prompt_assembly: bool = True
    receipt_gate_is_not_policy: bool = True
    receipt_gate_is_not_authority: bool = True
    receipt_gate_does_not_execute_action: bool = True
    receipt_gate_does_not_disclose_externally: bool = True
    runtime_memory_mutation_enabled: bool = False
    prompt_materialization_enabled: bool = False
    external_disclosure_enabled: bool = False
    remote_service_enabled: bool = False
    digest: str = ""

    def with_digest(self) -> "SelectiveMemoryDistillationReceiptDecision":
        return replace(self, digest=_digest(asdict(replace(self, digest=""))))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectiveMemoryDistillationReceiptGatePacket:
    schema_version: str
    decisions: tuple[SelectiveMemoryDistillationReceiptDecision, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    receipt_gate_is_not_memory_write: bool = True
    receipt_gate_is_not_deletion: bool = True
    receipt_gate_is_not_tomb_completion: bool = True
    receipt_gate_is_not_prompt_assembly: bool = True
    receipt_gate_is_not_policy: bool = True
    receipt_gate_is_not_authority: bool = True
    receipt_gate_does_not_execute_action: bool = True
    receipt_gate_does_not_disclose_externally: bool = True
    runtime_memory_mutation_enabled: bool = False
    prompt_materialization_enabled: bool = False
    external_disclosure_enabled: bool = False
    remote_service_enabled: bool = False
    digest: str = ""

    def with_digest(self) -> "SelectiveMemoryDistillationReceiptGatePacket":
        return replace(self, digest=_digest(asdict(replace(self, digest=""))))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectiveMemoryDistillationReceiptGateReport:
    status: ReceiptGateStatus
    findings: tuple[SelectiveMemoryDistillationReceiptFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [f.to_dict() for f in self.findings], "summary_counts": dict(self.summary_counts), "digest": self.digest}


@dataclass(frozen=True)
class SelectiveMemoryDistillationReceiptGateResult:
    status: ReceiptGateStatus
    packet: SelectiveMemoryDistillationReceiptGatePacket | None
    report: SelectiveMemoryDistillationReceiptGateReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> SelectiveMemoryDistillationReceiptGatePolicy:
    return SelectiveMemoryDistillationReceiptGatePolicy()


def validate_policy(policy: SelectiveMemoryDistillationReceiptGatePolicy) -> dict[str, Any]:
    findings: list[str] = []
    if not policy.schema_version:
        findings.append("missing_schema_version")
    if not policy.allow_warning_receipts and policy.allow_mixed_scope_diagnostic_packet:
        findings.append("mixed_scope_diagnostic_requires_warning_receipts")
    return {"ok": not findings, "findings": findings, "digest": _digest(asdict(policy))}


def _blocked(status: ReceiptGateStatus, findings: list[SelectiveMemoryDistillationReceiptFinding]) -> SelectiveMemoryDistillationReceiptGateResult:
    report = SelectiveMemoryDistillationReceiptGateReport(status, tuple(findings), {"candidate_count": 0, "blocked_count": 1}, "")
    report = replace(report, digest=_digest(report.to_dict()))
    return SelectiveMemoryDistillationReceiptGateResult(status, None, report, _digest(report.to_dict()))


def _status_for_block_code(code: str) -> ReceiptGateStatus:
    return {
        "decision_mismatch": "selective_memory_receipt_gate_blocked_decision_mismatch",
        "digest_mismatch": "selective_memory_receipt_gate_blocked_digest_mismatch",
        "tomb_intent_missing": "selective_memory_receipt_gate_blocked_tomb_intent_missing",
        "tomb_receipt_claimed": "selective_memory_receipt_gate_blocked_tomb_receipt_claimed",
        "capsule_payload_unsafe": "selective_memory_receipt_gate_blocked_capsule_payload_unsafe",
        "raw_payload_leak": "selective_memory_receipt_gate_blocked_raw_payload_leak",
        "authority_smuggling": "selective_memory_receipt_gate_blocked_authority_smuggling",
        "prompt_materialization": "selective_memory_receipt_gate_blocked_prompt_materialization",
        "runtime_memory_mutation": "selective_memory_receipt_gate_blocked_runtime_memory_mutation",
        "external_disclosure": "selective_memory_receipt_gate_blocked_external_disclosure",
        "scope_mismatch": "selective_memory_receipt_gate_blocked_scope_mismatch",
    }.get(code, "selective_memory_receipt_gate_blocked_invalid_receipt_candidate")  # type: ignore[return-value]


def _packet_from_payload(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    packet = payload.get("distillation_packet", payload.get("packet"))
    return packet if isinstance(packet, Mapping) else None


def _candidates_from_payload(payload: Mapping[str, Any]) -> Any:
    if "receipt_candidates" in payload:
        return payload.get("receipt_candidates")
    if "receipt_candidate" in payload:
        return [payload.get("receipt_candidate")]
    if "candidate" in payload:
        return [payload.get("candidate")]
    return None


def _record_index(packet: Mapping[str, Any]) -> dict[str, Mapping[str, Any]] | None:
    records = packet.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        return None
    out: dict[str, Mapping[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, Mapping):
            return None
        record_id = str(raw.get("record_id") or "")
        if not record_id or not raw.get("distillation_decision") or not raw.get("source_digest"):
            return None
        out[record_id] = raw
    if not out:
        return None
    return out


def _contains_forbidden_payload(value: Any, markers: frozenset[str]) -> bool:
    if isinstance(value, Mapping):
        lowered = {str(k).lower() for k in value.keys()}
        if lowered & markers:
            return True
    text = _text(value).lower()
    return any(marker in text for marker in markers)


def _contains_media(value: Any) -> bool:
    if isinstance(value, Mapping) and {str(k).lower() for k in value.keys()} & _MEDIA_KEYS:
        return True
    text = _text(value).lower()
    if "contains_encoded_media" in text or "raw_media_payload_declared" in text:
        return True
    return bool(_MEDIA_RE.search(_text(value)))


def _raw_payload_leak(candidate: SelectiveMemoryDistillationReceiptCandidate) -> bool:
    return _contains_forbidden_payload(candidate.to_dict(), _RAW_KEYS) or "raw transcript:" in _text(candidate.to_dict()).lower()


def _unsafe_capsule(candidate: SelectiveMemoryDistillationReceiptCandidate) -> bool:
    if candidate.receipt_candidate_type not in {"ai_capsule_write_receipt_candidate", "dual_capsule_write_receipt_candidate"}:
        return False
    return _contains_media(candidate.capsule_metadata) or _raw_payload_leak(candidate)


def _decision_allowed(candidate_type: str, decision: str) -> bool:
    allowed = {
        "ai_capsule_write_receipt_candidate": {"distill_to_ai_capsule"},
        "human_summary_write_receipt_candidate": {"distill_to_human_summary"},
        "dual_capsule_write_receipt_candidate": {"distill_to_dual_capsule"},
        "tomb_intent_receipt_candidate": {"tomb_without_retention", "tomb_after_distillation"},
        "tomb_after_distillation_receipt_candidate": {"tomb_after_distillation"},
        "protect_memory_receipt_candidate": {"protect_from_forgetting"},
        "merge_capsule_receipt_candidate": {"merge_into_existing_capsule"},
        "operator_review_receipt_candidate": {"defer_for_operator_review"},
        "defer_receipt_candidate": {"defer_for_operator_review"},
        "reject_record_receipt_candidate": {"reject_record"},
        "no_op_receipt_candidate": {"no_distillation_needed", "reject_record"},
    }
    return decision in allowed.get(candidate_type, set())


def _safe_actions_for(candidate: SelectiveMemoryDistillationReceiptCandidate, warnings: bool) -> tuple[str, ...]:
    actions = ["inspect_receipt_gate_packet"]
    if warnings:
        actions.append("operator_review_required")
    if candidate.receipt_candidate_type in {"ai_capsule_write_receipt_candidate", "human_summary_write_receipt_candidate", "dual_capsule_write_receipt_candidate"}:
        actions.append("prepare_capsule_writer_later")
    elif candidate.receipt_candidate_type in {"tomb_intent_receipt_candidate", "tomb_after_distillation_receipt_candidate"}:
        actions.append("prepare_tomb_receipt_writer_later")
    elif candidate.receipt_candidate_type == "protect_memory_receipt_candidate":
        actions.append("prepare_protect_receipt_later")
    elif candidate.receipt_candidate_type == "merge_capsule_receipt_candidate":
        actions.append("prepare_merge_receipt_later")
    elif candidate.receipt_candidate_type in {"operator_review_receipt_candidate", "defer_receipt_candidate"}:
        actions.append("operator_review_required")
    else:
        actions.append("no_action_allowed")
    actions.append("defer_to_memory_runtime_boundary")
    return tuple(dict.fromkeys(actions))


def _gate_decision_for(candidate: SelectiveMemoryDistillationReceiptCandidate, warnings: bool) -> ReceiptGateDecision:
    if candidate.receipt_candidate_type == "no_op_receipt_candidate":
        return "receipt_candidate_noop"
    if candidate.receipt_candidate_type == "reject_record_receipt_candidate":
        return "receipt_candidate_rejected"
    if candidate.receipt_candidate_type in {"operator_review_receipt_candidate", "defer_receipt_candidate"}:
        return "receipt_candidate_deferred_for_operator_review"
    return "receipt_candidate_admissible_with_warnings" if warnings else "receipt_candidate_admissible"


def _candidate_blockers(
    candidate: SelectiveMemoryDistillationReceiptCandidate,
    record: Mapping[str, Any],
    packet: Mapping[str, Any],
    policy: SelectiveMemoryDistillationReceiptGatePolicy,
) -> list[str]:
    blockers: list[str] = []
    if candidate.receipt_candidate_type not in RECEIPT_CANDIDATE_TYPES:
        blockers.append("invalid_receipt_candidate_type")
    text = _text(candidate.to_dict())
    if candidate.hard_override_requested and policy.block_hard_override_attempts:
        blockers.append("authority_smuggling")
    if candidate.authority_grant_claimed or candidate.consent_inference_claimed or candidate.policy_creation_claimed or _AUTHORITY_RE.search(text):
        blockers.append("authority_smuggling")
    if candidate.prompt_materialization_requested or _PROMPT_RE.search(text):
        blockers.append("prompt_materialization")
    if candidate.memory_mutation_requested or candidate.action_execution_requested or _ACTION_RE.search(text) or _RUNTIME_RE.search(text):
        blockers.append("runtime_memory_mutation")
    if candidate.external_disclosure_requested or _EXTERNAL_RE.search(text):
        blockers.append("external_disclosure")
    if _raw_payload_leak(candidate):
        blockers.append("raw_payload_leak")
    if policy.require_capsule_safety_scan and _unsafe_capsule(candidate):
        blockers.append("capsule_payload_unsafe")
    if policy.block_applied_state_claims and (candidate.applied_state_claimed or not candidate.future_intent_only):
        blockers.append("runtime_memory_mutation")
    if candidate.deletion_performed:
        blockers.append("tomb_receipt_claimed")
    if policy.require_matching_source_digest:
        packet_digest = str(packet.get("digest") or "")
        record_digests = {str(record.get("source_digest") or ""), str(record.get("digest") or ""), packet_digest}
        if candidate.source_digest not in record_digests:
            blockers.append("digest_mismatch")
        if candidate.claimed_packet_digest and packet_digest and candidate.claimed_packet_digest != packet_digest:
            blockers.append("digest_mismatch")
    actual_decision = str(record.get("distillation_decision") or "")
    if candidate.claimed_distillation_decision != actual_decision or not _decision_allowed(candidate.receipt_candidate_type, actual_decision):
        blockers.append("decision_mismatch")
    tomb_types = {"tomb_intent_receipt_candidate", "tomb_after_distillation_receipt_candidate"}
    if candidate.receipt_candidate_type in tomb_types and policy.require_tomb_intent_for_tomb_receipts:
        tomb_intent = record.get("tomb_intent") if isinstance(record.get("tomb_intent"), Mapping) else None
        if not tomb_intent or not candidate.tomb_intent_id:
            blockers.append("tomb_intent_missing")
        elif candidate.tomb_intent_id != str(tomb_intent.get("tomb_intent_id") or tomb_intent.get("intent_id") or ""):
            blockers.append("tomb_intent_missing")
    if candidate.receipt_candidate_type in {"protect_memory_receipt_candidate", "merge_capsule_receipt_candidate"} and candidate.applied_state_claimed:
        blockers.append("runtime_memory_mutation")
    if candidate.receipt_candidate_type in {"operator_review_receipt_candidate", "defer_receipt_candidate"} and not policy.allow_operator_review_receipts:
        blockers.append("authority_smuggling")
    if candidate.receipt_candidate_type == "no_op_receipt_candidate" and not policy.allow_noop_receipts:
        blockers.append("decision_mismatch")
    if policy.require_scope_alignment:
        record_scope = _as_tuple(record.get("source_scope_keys"))
        if candidate.source_scope_keys and record_scope and tuple(candidate.source_scope_keys) != tuple(record_scope):
            blockers.append("scope_mismatch")
    return list(dict.fromkeys(blockers))


def evaluate_selective_memory_distillation_receipt_gate(
    payload: Mapping[str, Any],
    policy: SelectiveMemoryDistillationReceiptGatePolicy | None = None,
) -> SelectiveMemoryDistillationReceiptGateResult:
    if policy is None and isinstance(payload.get("policy"), Mapping):
        allowed = set(SelectiveMemoryDistillationReceiptGatePolicy.__dataclass_fields__)
        policy = SelectiveMemoryDistillationReceiptGatePolicy(**{k: v for k, v in payload["policy"].items() if k in allowed})
    policy = policy or build_default_policy()
    packet = _packet_from_payload(payload)
    if packet is None:
        finding = SelectiveMemoryDistillationReceiptFinding("error", "missing_distillation_packet", "missing distillation packet")
        return _blocked("selective_memory_receipt_gate_blocked_missing_distillation_packet", [finding])
    records = _record_index(packet)
    if records is None:
        finding = SelectiveMemoryDistillationReceiptFinding("error", "invalid_distillation_packet", "distillation packet records are invalid")
        return _blocked("selective_memory_receipt_gate_blocked_invalid_distillation_packet", [finding])
    raw_candidates = _candidates_from_payload(payload)
    if raw_candidates is None:
        finding = SelectiveMemoryDistillationReceiptFinding("error", "missing_receipt_candidate", "missing receipt candidate")
        return _blocked("selective_memory_receipt_gate_blocked_missing_receipt_candidate", [finding])
    if not isinstance(raw_candidates, Sequence) or isinstance(raw_candidates, (str, bytes, bytearray)) or not raw_candidates:
        finding = SelectiveMemoryDistillationReceiptFinding("error", "invalid_receipt_candidate", "receipt candidates must be a non-empty list")
        return _blocked("selective_memory_receipt_gate_blocked_invalid_receipt_candidate", [finding])

    findings: list[SelectiveMemoryDistillationReceiptFinding] = []
    candidates: list[SelectiveMemoryDistillationReceiptCandidate] = []
    for raw in raw_candidates:
        if not isinstance(raw, Mapping):
            finding = SelectiveMemoryDistillationReceiptFinding("error", "invalid_receipt_candidate", "receipt candidate must be a mapping")
            return _blocked("selective_memory_receipt_gate_blocked_invalid_receipt_candidate", [finding])
        try:
            candidate = SelectiveMemoryDistillationReceiptCandidate.from_mapping(raw)
        except (TypeError, ValueError) as exc:
            finding = SelectiveMemoryDistillationReceiptFinding("error", "invalid_receipt_candidate", str(exc))
            return _blocked("selective_memory_receipt_gate_blocked_invalid_receipt_candidate", [finding])
        candidates.append(candidate)

    packet_scope_sets = {_as_tuple(record.get("source_scope_keys")) for record in records.values() if _as_tuple(record.get("source_scope_keys"))}
    mixed_scope_warning = False
    if len(packet_scope_sets) > 1:
        if policy.allow_mixed_scope_diagnostic_packet and policy.allow_warning_receipts:
            findings.append(SelectiveMemoryDistillationReceiptFinding("warning", "mixed_scope_diagnostic_packet", "packet contains multiple source scopes"))
            mixed_scope_warning = True
        elif policy.require_scope_alignment:
            findings.append(SelectiveMemoryDistillationReceiptFinding("error", "scope_mismatch", "packet contains multiple source scopes"))
            return _blocked("selective_memory_receipt_gate_blocked_scope_mismatch", findings)

    decisions: list[SelectiveMemoryDistillationReceiptDecision] = []
    for candidate in candidates:
        record = records.get(candidate.record_id)
        if record is None:
            finding = SelectiveMemoryDistillationReceiptFinding("error", "invalid_receipt_candidate", "candidate references an unknown distillation record", candidate.candidate_id, candidate.record_id)
            return _blocked("selective_memory_receipt_gate_blocked_invalid_receipt_candidate", [finding])
        blockers = _candidate_blockers(candidate, record, packet, policy)
        if blockers:
            code = blockers[0]
            findings.append(SelectiveMemoryDistillationReceiptFinding("error", code, f"receipt candidate blocked: {code}", candidate.candidate_id, candidate.record_id))
            return _blocked(_status_for_block_code(code), findings)
        warnings = mixed_scope_warning or bool(candidate.receipt_metadata.get("warning_only") or candidate.receipt_metadata.get("diagnostic_warning"))
        if warnings and not policy.allow_warning_receipts:
            finding = SelectiveMemoryDistillationReceiptFinding("error", "warning_receipts_disabled", "warning receipts are disabled", candidate.candidate_id, candidate.record_id)
            return _blocked("selective_memory_receipt_gate_blocked_invalid_receipt_candidate", [finding])
        if warnings:
            findings.append(SelectiveMemoryDistillationReceiptFinding("warning", "receipt_candidate_warning", "candidate is admissible only as warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
        decisions.append(
            SelectiveMemoryDistillationReceiptDecision(
                candidate_id=candidate.candidate_id,
                record_id=candidate.record_id,
                receipt_candidate_type=candidate.receipt_candidate_type,
                claimed_distillation_decision=candidate.claimed_distillation_decision,
                gate_decision=_gate_decision_for(candidate, warnings),
                safe_next_actions=_safe_actions_for(candidate, warnings),
            ).with_digest()
        )

    counts: dict[str, int] = {"candidate_count": len(decisions), "warning_count": sum(1 for finding in findings if finding.severity == "warning")}
    for decision in decisions:
        counts[decision.gate_decision] = counts.get(decision.gate_decision, 0) + 1
        counts[decision.receipt_candidate_type] = counts.get(decision.receipt_candidate_type, 0) + 1
    status: ReceiptGateStatus = "selective_memory_receipt_gate_ready_with_warnings" if counts["warning_count"] else "selective_memory_receipt_gate_ready"
    out_packet = SelectiveMemoryDistillationReceiptGatePacket(policy.schema_version, tuple(decisions)).with_digest()
    report = SelectiveMemoryDistillationReceiptGateReport(status, tuple(findings), dict(sorted(counts.items())), "")
    report = replace(report, digest=_digest(report.to_dict()))
    return SelectiveMemoryDistillationReceiptGateResult(status, out_packet, report, _digest({"packet": out_packet.to_dict(), "report": report.to_dict()}))


def evaluate_packet(payload: Mapping[str, Any], policy: SelectiveMemoryDistillationReceiptGatePolicy | None = None) -> SelectiveMemoryDistillationReceiptGateResult:
    return evaluate_selective_memory_distillation_receipt_gate(payload, policy)


__all__ = [
    "FORBIDDEN_NEXT_STEPS",
    "SAFE_NEXT_ACTIONS",
    "RECEIPT_CANDIDATE_TYPES",
    "SelectiveMemoryDistillationReceiptGatePolicy",
    "SelectiveMemoryDistillationReceiptGateInput",
    "SelectiveMemoryDistillationReceiptCandidate",
    "SelectiveMemoryDistillationReceiptFinding",
    "SelectiveMemoryDistillationReceiptDecision",
    "SelectiveMemoryDistillationReceiptGatePacket",
    "SelectiveMemoryDistillationReceiptGateReport",
    "SelectiveMemoryDistillationReceiptGateResult",
    "build_default_policy",
    "validate_policy",
    "evaluate_selective_memory_distillation_receipt_gate",
    "evaluate_packet",
]
