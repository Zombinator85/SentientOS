"""Deterministic metadata-only selective memory tomb receipt verifier.

The verifier evaluates caller-supplied JSON metadata only. It does not write
memory, delete memory, complete tombs, persist capsules, assemble prompts,
execute actions, invoke remote services, disclose externally, or grant
authority. It only checks whether tomb receipt claims are consistent with prior
selective memory distillation and receipt-gate metadata.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal, Mapping, Sequence

TombReceiptVerifierStatus = Literal[
    "selective_memory_tomb_receipt_verifier_ready",
    "selective_memory_tomb_receipt_verifier_ready_with_warnings",
    "selective_memory_tomb_receipt_verifier_blocked_missing_distillation_packet",
    "selective_memory_tomb_receipt_verifier_blocked_invalid_distillation_packet",
    "selective_memory_tomb_receipt_verifier_blocked_missing_receipt_gate_packet",
    "selective_memory_tomb_receipt_verifier_blocked_invalid_receipt_gate_packet",
    "selective_memory_tomb_receipt_verifier_blocked_missing_tomb_claim",
    "selective_memory_tomb_receipt_verifier_blocked_invalid_tomb_claim",
    "selective_memory_tomb_receipt_verifier_blocked_digest_mismatch",
    "selective_memory_tomb_receipt_verifier_blocked_decision_mismatch",
    "selective_memory_tomb_receipt_verifier_blocked_gate_not_admissible",
    "selective_memory_tomb_receipt_verifier_blocked_missing_tomb_intent",
    "selective_memory_tomb_receipt_verifier_blocked_tomb_intent_mismatch",
    "selective_memory_tomb_receipt_verifier_blocked_applied_state_overclaim",
    "selective_memory_tomb_receipt_verifier_blocked_claims_memory_mutation",
    "selective_memory_tomb_receipt_verifier_blocked_claims_unverified_deletion",
    "selective_memory_tomb_receipt_verifier_blocked_capsule_persistence_claim",
    "selective_memory_tomb_receipt_verifier_blocked_raw_payload_leak",
    "selective_memory_tomb_receipt_verifier_blocked_authority_smuggling",
    "selective_memory_tomb_receipt_verifier_blocked_prompt_materialization",
    "selective_memory_tomb_receipt_verifier_blocked_external_disclosure",
    "selective_memory_tomb_receipt_verifier_blocked_scope_mismatch",
    "selective_memory_tomb_receipt_verifier_invalid",
    "selective_memory_tomb_receipt_verifier_failed",
]

TombReceiptVerificationOutcome = Literal[
    "tomb_receipt_verified",
    "tomb_receipt_verified_with_warnings",
    "tomb_receipt_deferred_for_operator_review",
    "tomb_receipt_rejected",
    "tomb_receipt_blocked",
    "tomb_receipt_noop",
]

TOMB_CLAIM_TYPES = frozenset({
    "tomb_intent_observed_receipt",
    "tomb_after_distillation_observed_receipt",
    "tomb_without_retention_observed_receipt",
    "tomb_deferred_for_writer_receipt",
    "tomb_blocked_receipt",
    "tomb_rejected_receipt",
    "tomb_noop_receipt",
    "tomb_mixed_receipt",
})

SAFE_NEXT_ACTIONS = (
    "no_action_allowed",
    "inspect_tomb_receipt_verification",
    "operator_review_required",
    "prepare_governed_memory_writer_later",
    "prepare_tomb_receipt_archive_later",
    "rerun_with_matching_digest",
    "rerun_with_matching_tomb_intent",
    "rerun_with_admissible_receipt_gate",
    "rerun_with_scope_alignment",
    "sustain_tomb_deferral",
    "defer_to_memory_runtime_boundary",
    "defer_to_self_improvement_ingress",
)

FORBIDDEN_NEXT_STEPS = (
    "delete_memory_now",
    "purge_memory_now",
    "write_memory_now",
    "mutate_raw_fragment",
    "mutate_vector_index",
    "mutate_distilled_memory",
    "claim_deletion_performed_by_verifier",
    "claim_tomb_completed_by_verifier",
    "claim_capsule_persisted_by_verifier",
    "claim_protection_applied_by_verifier",
    "claim_merge_applied_by_verifier",
    "call_append_memory",
    "call_purge_memory",
    "call_apply_forgetting_curve",
    "call_curate_memory",
    "call_summarize_memory",
    "assemble_prompt_now",
    "retrieve_live_context",
    "execute_action_ingress",
    "infer_truth_from_tomb_receipt",
    "infer_authority_from_tomb_receipt",
    "infer_consent_from_tomb_receipt",
    "convert_tomb_receipt_to_policy",
    "convert_tomb_verification_to_action",
    "bypass_distillation_contract",
    "bypass_receipt_gate",
    "bypass_memory_tomb",
    "bypass_operator_review",
    "enable_external_disclosure",
)

_NON_AUTHORITY_INVARIANTS: dict[str, bool] = {
    "tomb_verifier_is_not_memory_write": True,
    "tomb_verifier_is_not_deletion": True,
    "tomb_verifier_is_not_tomb_completion": True,
    "tomb_verifier_is_not_capsule_persistence": True,
    "tomb_verifier_is_not_prompt_assembly": True,
    "tomb_verifier_is_not_policy": True,
    "tomb_verifier_is_not_authority": True,
    "tomb_verifier_does_not_execute_action": True,
    "tomb_verifier_does_not_disclose_externally": True,
    "runtime_memory_mutation_enabled": False,
    "deletion_performed_by_verifier": False,
    "tomb_completed_by_verifier": False,
    "capsule_persistence_enabled": False,
    "prompt_materialization_enabled": False,
    "external_disclosure_enabled": False,
    "remote_service_enabled": False,
}

_RAW_KEYS = frozenset({"raw_payload", "raw_private_payload", "raw_transcript", "transcript", "provider_prompt", "secret", "api_key", "password", "token", "private_payload"})
_MEDIA_KEYS = frozenset({"image", "images", "audio", "video", "screenshot", "thumbnail", "media_payload", "encoded_media", "base64", "bytes", "raw_media"})
_MEDIA_RE = re.compile(r"(?:data:(?:image|audio|video)/|base64|[A-Za-z0-9+/]{120,}={0,2})")
_AUTHORITY_RE = re.compile(r"\b(authority|authorize|grant permission|policy now|consent granted|infer consent|infer authority|infer truth|convert.*policy|approved to act|override blocker|bypass)\b", re.I)
_PROMPT_RE = re.compile(r"\b(assemble prompt|prompt materialization|provider prompt|system prompt|retrieve live context)\b", re.I)
_RUNTIME_RE = re.compile(r"\b(write memory|delete memory|purge memory|append_memory|purge_memory|apply_forgetting_curve|curate_memory|summarize_memory|mutate vector|mutate index|memory mutation)\b", re.I)
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
class SelectiveMemoryTombReceiptVerifierPolicy:
    schema_version: str = "selective-memory-tomb-receipt-verifier.v1"
    allow_mixed_scope_diagnostic_packet: bool = False
    allow_diagnostic_blocked_verification: bool = False
    allow_observed_deletion_diagnostic_warning: bool = False
    allow_noop_receipts: bool = True
    allow_operator_review_receipts: bool = True
    require_matching_source_digest: bool = True
    require_matching_tomb_intent: bool = True
    require_admissible_receipt_gate: bool = True
    require_scope_alignment: bool = True
    block_applied_state_overclaims: bool = True
    block_capsule_persistence_claims: bool = True
    block_hard_override_attempts: bool = True


@dataclass(frozen=True)
class SelectiveMemoryTombReceiptClaim:
    claim_id: str
    tomb_claim_type: str
    record_id: str
    claimed_distillation_decision: str
    source_digest: str
    source_scope_keys: tuple[str, ...] = ()
    claimed_packet_digest: str | None = None
    claimed_gate_decision_digest: str | None = None
    receipt_gate_decision_id: str | None = None
    tomb_intent_id: str | None = None
    tomb_intent_digest: str | None = None
    tomb_intent_source_digest: str | None = None
    receipt_metadata: Mapping[str, Any] = field(default_factory=dict)
    requested_next_actions: tuple[str, ...] = ()
    external_observed_deletion: bool = False
    deletion_performed_by_verifier: bool = False
    tomb_completed_by_verifier: bool = False
    memory_written_by_verifier: bool = False
    capsule_persisted_by_verifier: bool = False
    protection_applied_by_verifier: bool = False
    merge_applied_by_verifier: bool = False
    applied_state_claimed: bool = False
    hard_override_requested: bool = False
    memory_mutation_requested: bool = False
    prompt_materialization_requested: bool = False
    external_disclosure_requested: bool = False
    action_execution_requested: bool = False
    policy_creation_claimed: bool = False
    authority_grant_claimed: bool = False
    consent_inference_claimed: bool = False
    truth_inference_claimed: bool = False

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "SelectiveMemoryTombReceiptClaim":
        claim_id = str(payload.get("claim_id") or payload.get("tomb_claim_id") or "")
        claim_type = str(payload.get("tomb_claim_type") or payload.get("claim_type") or "")
        record_id = str(payload.get("record_id") or payload.get("distillation_record_id") or "")
        decision = str(payload.get("claimed_distillation_decision") or payload.get("distillation_decision") or "")
        source_digest = str(payload.get("source_digest") or payload.get("claimed_source_digest") or "")
        if not claim_id or not claim_type or not record_id or not decision or not source_digest:
            raise ValueError("claim_id_type_record_decision_source_digest_required")
        metadata = payload.get("receipt_metadata") or payload.get("metadata") or {}
        return cls(
            claim_id=claim_id,
            tomb_claim_type=claim_type,
            record_id=record_id,
            claimed_distillation_decision=decision,
            source_digest=source_digest,
            source_scope_keys=_as_tuple(payload.get("source_scope_keys")),
            claimed_packet_digest=str(payload["claimed_packet_digest"]) if payload.get("claimed_packet_digest") is not None else None,
            claimed_gate_decision_digest=str(payload["claimed_gate_decision_digest"]) if payload.get("claimed_gate_decision_digest") is not None else None,
            receipt_gate_decision_id=str(payload["receipt_gate_decision_id"]) if payload.get("receipt_gate_decision_id") is not None else None,
            tomb_intent_id=str(payload["tomb_intent_id"]) if payload.get("tomb_intent_id") is not None else None,
            tomb_intent_digest=str(payload["tomb_intent_digest"]) if payload.get("tomb_intent_digest") is not None else None,
            tomb_intent_source_digest=str(payload["tomb_intent_source_digest"]) if payload.get("tomb_intent_source_digest") is not None else None,
            receipt_metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
            requested_next_actions=_as_tuple(payload.get("requested_next_actions")),
            external_observed_deletion=bool(payload.get("external_observed_deletion") or payload.get("observed_deletion")),
            deletion_performed_by_verifier=bool(payload.get("deletion_performed_by_verifier") or payload.get("claim_deletion_performed_by_verifier")),
            tomb_completed_by_verifier=bool(payload.get("tomb_completed_by_verifier") or payload.get("claim_tomb_completed_by_verifier")),
            memory_written_by_verifier=bool(payload.get("memory_written_by_verifier") or payload.get("write_memory_now")),
            capsule_persisted_by_verifier=bool(payload.get("capsule_persisted_by_verifier") or payload.get("claim_capsule_persisted_by_verifier")),
            protection_applied_by_verifier=bool(payload.get("protection_applied_by_verifier")),
            merge_applied_by_verifier=bool(payload.get("merge_applied_by_verifier")),
            applied_state_claimed=bool(payload.get("applied_state_claimed") or payload.get("claim_applied")),
            hard_override_requested=bool(payload.get("hard_override_requested") or payload.get("override_hard_blocker")),
            memory_mutation_requested=bool(payload.get("memory_mutation_requested") or payload.get("runtime_memory_mutation_requested")),
            prompt_materialization_requested=bool(payload.get("prompt_materialization_requested")),
            external_disclosure_requested=bool(payload.get("external_disclosure_requested")),
            action_execution_requested=bool(payload.get("action_execution_requested")),
            policy_creation_claimed=bool(payload.get("policy_creation_claimed") or payload.get("converts_to_policy")),
            authority_grant_claimed=bool(payload.get("authority_grant_claimed") or payload.get("grants_authority")),
            consent_inference_claimed=bool(payload.get("consent_inference_claimed") or payload.get("infers_consent")),
            truth_inference_claimed=bool(payload.get("truth_inference_claimed") or payload.get("infers_truth")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectiveMemoryTombReceiptVerifierInput:
    distillation_packet: Mapping[str, Any]
    receipt_gate_packet: Mapping[str, Any]
    tomb_claims: tuple[SelectiveMemoryTombReceiptClaim, ...]


@dataclass(frozen=True)
class SelectiveMemoryTombReceiptFinding:
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    claim_id: str | None = None
    record_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectiveMemoryTombReceiptVerificationRecord:
    claim_id: str
    record_id: str
    tomb_claim_type: str
    claimed_distillation_decision: str
    receipt_gate_decision: str
    verification_outcome: TombReceiptVerificationOutcome
    safe_next_actions: tuple[str, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    tomb_verifier_is_not_memory_write: bool = True
    tomb_verifier_is_not_deletion: bool = True
    tomb_verifier_is_not_tomb_completion: bool = True
    tomb_verifier_is_not_capsule_persistence: bool = True
    tomb_verifier_is_not_prompt_assembly: bool = True
    tomb_verifier_is_not_policy: bool = True
    tomb_verifier_is_not_authority: bool = True
    tomb_verifier_does_not_execute_action: bool = True
    tomb_verifier_does_not_disclose_externally: bool = True
    runtime_memory_mutation_enabled: bool = False
    deletion_performed_by_verifier: bool = False
    tomb_completed_by_verifier: bool = False
    capsule_persistence_enabled: bool = False
    prompt_materialization_enabled: bool = False
    external_disclosure_enabled: bool = False
    remote_service_enabled: bool = False
    digest: str = ""

    def with_digest(self) -> "SelectiveMemoryTombReceiptVerificationRecord":
        return replace(self, digest=_digest(asdict(replace(self, digest=""))))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectiveMemoryTombReceiptVerificationPacket:
    schema_version: str
    records: tuple[SelectiveMemoryTombReceiptVerificationRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    tomb_verifier_is_not_memory_write: bool = True
    tomb_verifier_is_not_deletion: bool = True
    tomb_verifier_is_not_tomb_completion: bool = True
    tomb_verifier_is_not_capsule_persistence: bool = True
    tomb_verifier_is_not_prompt_assembly: bool = True
    tomb_verifier_is_not_policy: bool = True
    tomb_verifier_is_not_authority: bool = True
    tomb_verifier_does_not_execute_action: bool = True
    tomb_verifier_does_not_disclose_externally: bool = True
    runtime_memory_mutation_enabled: bool = False
    deletion_performed_by_verifier: bool = False
    tomb_completed_by_verifier: bool = False
    capsule_persistence_enabled: bool = False
    prompt_materialization_enabled: bool = False
    external_disclosure_enabled: bool = False
    remote_service_enabled: bool = False
    digest: str = ""

    def with_digest(self) -> "SelectiveMemoryTombReceiptVerificationPacket":
        return replace(self, digest=_digest(asdict(replace(self, digest=""))))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectiveMemoryTombReceiptVerificationReport:
    status: TombReceiptVerifierStatus
    findings: tuple[SelectiveMemoryTombReceiptFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [f.to_dict() for f in self.findings], "summary_counts": dict(self.summary_counts), "digest": self.digest}


@dataclass(frozen=True)
class SelectiveMemoryTombReceiptVerificationResult:
    status: TombReceiptVerifierStatus
    packet: SelectiveMemoryTombReceiptVerificationPacket | None
    report: SelectiveMemoryTombReceiptVerificationReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> SelectiveMemoryTombReceiptVerifierPolicy:
    return SelectiveMemoryTombReceiptVerifierPolicy()


def validate_policy(policy: SelectiveMemoryTombReceiptVerifierPolicy) -> dict[str, Any]:
    findings: list[str] = []
    if not policy.schema_version:
        findings.append("missing_schema_version")
    if policy.allow_mixed_scope_diagnostic_packet and not policy.require_scope_alignment:
        findings.append("mixed_scope_diagnostic_without_scope_checks")
    return {"ok": not findings, "findings": findings, "digest": _digest(asdict(policy))}


def _blocked(status: TombReceiptVerifierStatus, findings: list[SelectiveMemoryTombReceiptFinding]) -> SelectiveMemoryTombReceiptVerificationResult:
    report = SelectiveMemoryTombReceiptVerificationReport(status, tuple(findings), {"claim_count": 0, "blocked_count": 1}, "")
    report = replace(report, digest=_digest(report.to_dict()))
    return SelectiveMemoryTombReceiptVerificationResult(status, None, report, _digest(report.to_dict()))


def _packet_from_payload(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    packet = payload.get("distillation_packet") or payload.get("packet")
    return packet if isinstance(packet, Mapping) else None


def _gate_packet_from_payload(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    packet = payload.get("receipt_gate_packet") or payload.get("gate_packet")
    return packet if isinstance(packet, Mapping) else None


def _claims_from_payload(payload: Mapping[str, Any]) -> Any:
    if "tomb_claims" in payload:
        return payload.get("tomb_claims")
    if "tomb_claim" in payload:
        return [payload.get("tomb_claim")]
    if "claim" in payload:
        return [payload.get("claim")]
    return None


def _record_index(packet: Mapping[str, Any]) -> dict[str, Mapping[str, Any]] | None:
    records = packet.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)) or not records:
        return None
    out: dict[str, Mapping[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, Mapping):
            return None
        rid = str(raw.get("record_id") or "")
        if not rid or not raw.get("distillation_decision") or not raw.get("source_digest"):
            return None
        out[rid] = raw
    return out


def _gate_index(packet: Mapping[str, Any]) -> dict[str, Mapping[str, Any]] | None:
    decisions = packet.get("decisions")
    if not isinstance(decisions, Sequence) or isinstance(decisions, (str, bytes, bytearray)) or not decisions:
        return None
    out: dict[str, Mapping[str, Any]] = {}
    for raw in decisions:
        if not isinstance(raw, Mapping):
            return None
        rid = str(raw.get("record_id") or "")
        if not rid or not raw.get("gate_decision"):
            return None
        out[rid] = raw
    return out


def _contains_forbidden_payload(value: Any, markers: frozenset[str]) -> bool:
    if isinstance(value, Mapping) and {str(k).lower() for k in value.keys()} & markers:
        return True
    text = _text(value).lower()
    return any(marker in text for marker in markers)


def _contains_media(value: Any) -> bool:
    if isinstance(value, Mapping) and {str(k).lower() for k in value.keys()} & _MEDIA_KEYS:
        return True
    text = _text(value).lower()
    return "contains_encoded_media" in text or "raw_media_payload_declared" in text or bool(_MEDIA_RE.search(_text(value)))


def _decision_allowed(claim_type: str, decision: str) -> bool:
    allowed = {
        "tomb_intent_observed_receipt": {"tomb_after_distillation", "tomb_without_retention"},
        "tomb_after_distillation_observed_receipt": {"tomb_after_distillation"},
        "tomb_without_retention_observed_receipt": {"tomb_without_retention"},
        "tomb_deferred_for_writer_receipt": {"defer_for_operator_review", "tomb_after_distillation", "tomb_without_retention"},
        "tomb_blocked_receipt": {"tomb_after_distillation", "tomb_without_retention", "reject_record", "defer_for_operator_review"},
        "tomb_rejected_receipt": {"reject_record"},
        "tomb_noop_receipt": {"no_distillation_needed"},
        "tomb_mixed_receipt": {"tomb_after_distillation", "tomb_without_retention", "reject_record", "defer_for_operator_review", "no_distillation_needed"},
    }
    return decision in allowed.get(claim_type, set())


def _outcome_for(claim: SelectiveMemoryTombReceiptClaim, gate_decision: str, warnings: bool) -> TombReceiptVerificationOutcome:
    if claim.tomb_claim_type == "tomb_noop_receipt" or gate_decision == "receipt_candidate_noop":
        return "tomb_receipt_noop"
    if claim.tomb_claim_type == "tomb_rejected_receipt" or gate_decision == "receipt_candidate_rejected":
        return "tomb_receipt_rejected"
    if claim.tomb_claim_type == "tomb_deferred_for_writer_receipt" or gate_decision == "receipt_candidate_deferred_for_operator_review":
        return "tomb_receipt_deferred_for_operator_review"
    if claim.tomb_claim_type == "tomb_blocked_receipt" or gate_decision == "receipt_candidate_blocked":
        return "tomb_receipt_verified_with_warnings" if warnings else "tomb_receipt_blocked"
    return "tomb_receipt_verified_with_warnings" if warnings else "tomb_receipt_verified"


def _safe_actions_for(outcome: str, warnings: bool) -> tuple[str, ...]:
    actions = ["inspect_tomb_receipt_verification"]
    if outcome == "tomb_receipt_deferred_for_operator_review" or warnings:
        actions.append("operator_review_required")
        actions.append("sustain_tomb_deferral")
    if outcome in {"tomb_receipt_verified", "tomb_receipt_verified_with_warnings"}:
        actions.append("prepare_tomb_receipt_archive_later")
    if outcome == "tomb_receipt_blocked":
        actions.append("operator_review_required")
    actions.extend(["defer_to_memory_runtime_boundary", "defer_to_self_improvement_ingress", "no_action_allowed"])
    return tuple(dict.fromkeys(actions))


def _status_for(code: str) -> TombReceiptVerifierStatus:
    return {
        "digest_mismatch": "selective_memory_tomb_receipt_verifier_blocked_digest_mismatch",
        "decision_mismatch": "selective_memory_tomb_receipt_verifier_blocked_decision_mismatch",
        "gate_not_admissible": "selective_memory_tomb_receipt_verifier_blocked_gate_not_admissible",
        "missing_tomb_intent": "selective_memory_tomb_receipt_verifier_blocked_missing_tomb_intent",
        "tomb_intent_mismatch": "selective_memory_tomb_receipt_verifier_blocked_tomb_intent_mismatch",
        "applied_state_overclaim": "selective_memory_tomb_receipt_verifier_blocked_applied_state_overclaim",
        "claims_memory_mutation": "selective_memory_tomb_receipt_verifier_blocked_claims_memory_mutation",
        "claims_unverified_deletion": "selective_memory_tomb_receipt_verifier_blocked_claims_unverified_deletion",
        "capsule_persistence_claim": "selective_memory_tomb_receipt_verifier_blocked_capsule_persistence_claim",
        "raw_payload_leak": "selective_memory_tomb_receipt_verifier_blocked_raw_payload_leak",
        "authority_smuggling": "selective_memory_tomb_receipt_verifier_blocked_authority_smuggling",
        "prompt_materialization": "selective_memory_tomb_receipt_verifier_blocked_prompt_materialization",
        "external_disclosure": "selective_memory_tomb_receipt_verifier_blocked_external_disclosure",
        "scope_mismatch": "selective_memory_tomb_receipt_verifier_blocked_scope_mismatch",
    }.get(code, "selective_memory_tomb_receipt_verifier_blocked_invalid_tomb_claim")  # type: ignore[return-value]


def _claim_blockers(claim: SelectiveMemoryTombReceiptClaim, record: Mapping[str, Any], gate: Mapping[str, Any], dist_packet: Mapping[str, Any], policy: SelectiveMemoryTombReceiptVerifierPolicy) -> tuple[list[str], bool]:
    blockers: list[str] = []
    warning = False
    text = _text(claim.to_dict())
    if claim.tomb_claim_type not in TOMB_CLAIM_TYPES:
        blockers.append("invalid_tomb_claim")
    if policy.block_hard_override_attempts and claim.hard_override_requested:
        blockers.append("authority_smuggling")
    if claim.authority_grant_claimed or claim.consent_inference_claimed or claim.policy_creation_claimed or claim.truth_inference_claimed or _AUTHORITY_RE.search(text):
        blockers.append("authority_smuggling")
    if claim.prompt_materialization_requested or _PROMPT_RE.search(text):
        blockers.append("prompt_materialization")
    if claim.memory_mutation_requested or claim.action_execution_requested or claim.memory_written_by_verifier or _ACTION_RE.search(text) or _RUNTIME_RE.search(text):
        blockers.append("claims_memory_mutation")
    if claim.external_disclosure_requested or _EXTERNAL_RE.search(text):
        blockers.append("external_disclosure")
    if _contains_forbidden_payload(claim.to_dict(), _RAW_KEYS) or _contains_media(claim.to_dict()) or "raw transcript:" in text.lower():
        blockers.append("raw_payload_leak")
    if policy.block_capsule_persistence_claims and (claim.capsule_persisted_by_verifier or claim.protection_applied_by_verifier or claim.merge_applied_by_verifier):
        blockers.append("capsule_persistence_claim")
    if policy.block_applied_state_overclaims and (claim.applied_state_claimed or claim.deletion_performed_by_verifier or claim.tomb_completed_by_verifier):
        blockers.append("applied_state_overclaim")
    if claim.external_observed_deletion:
        if policy.allow_observed_deletion_diagnostic_warning:
            warning = True
        else:
            blockers.append("claims_unverified_deletion")
    packet_digest = str(dist_packet.get("digest") or "")
    if policy.require_matching_source_digest:
        record_digests = {str(record.get("source_digest") or ""), str(record.get("digest") or ""), packet_digest, str(gate.get("digest") or "")}
        if claim.source_digest not in record_digests:
            blockers.append("digest_mismatch")
        if claim.claimed_packet_digest and packet_digest and claim.claimed_packet_digest != packet_digest:
            blockers.append("digest_mismatch")
        if claim.claimed_gate_decision_digest and str(gate.get("digest") or "") and claim.claimed_gate_decision_digest != str(gate.get("digest") or ""):
            blockers.append("digest_mismatch")
    actual_decision = str(record.get("distillation_decision") or "")
    if claim.claimed_distillation_decision != actual_decision or not _decision_allowed(claim.tomb_claim_type, actual_decision):
        blockers.append("decision_mismatch")
    gate_decision = str(gate.get("gate_decision") or "")
    admissible = {"receipt_candidate_admissible", "receipt_candidate_admissible_with_warnings", "receipt_candidate_deferred_for_operator_review", "receipt_candidate_rejected", "receipt_candidate_noop"}
    if claim.tomb_claim_type == "tomb_blocked_receipt" and policy.allow_diagnostic_blocked_verification:
        warning = True
    elif policy.require_admissible_receipt_gate and gate_decision not in admissible:
        blockers.append("gate_not_admissible")
    tomb_types = {"tomb_intent_observed_receipt", "tomb_after_distillation_observed_receipt", "tomb_without_retention_observed_receipt"}
    if policy.require_matching_tomb_intent and claim.tomb_claim_type in tomb_types:
        tomb_intent = record.get("tomb_intent") if isinstance(record.get("tomb_intent"), Mapping) else None
        if not tomb_intent or not claim.tomb_intent_id or not claim.tomb_intent_digest:
            blockers.append("missing_tomb_intent")
        elif claim.tomb_intent_id != str(tomb_intent.get("tomb_intent_id") or tomb_intent.get("intent_id") or "") or claim.tomb_intent_digest != str(tomb_intent.get("digest") or ""):
            blockers.append("tomb_intent_mismatch")
        elif claim.tomb_intent_source_digest and claim.tomb_intent_source_digest != str(tomb_intent.get("source_digest") or record.get("source_digest") or ""):
            blockers.append("tomb_intent_mismatch")
    record_scope = _as_tuple(record.get("source_scope_keys"))
    gate_scope = _as_tuple(gate.get("source_scope_keys"))
    if policy.require_scope_alignment:
        if (claim.source_scope_keys and record_scope and claim.source_scope_keys != record_scope) or (gate_scope and record_scope and gate_scope != record_scope):
            blockers.append("scope_mismatch")
    return blockers, warning or gate_decision == "receipt_candidate_admissible_with_warnings" or bool(claim.receipt_metadata.get("diagnostic_warning") or claim.receipt_metadata.get("warning_only"))


def evaluate_selective_memory_tomb_receipt_verifier(payload: Mapping[str, Any], policy: SelectiveMemoryTombReceiptVerifierPolicy | None = None) -> SelectiveMemoryTombReceiptVerificationResult:
    if policy is None and isinstance(payload.get("policy"), Mapping):
        allowed = set(SelectiveMemoryTombReceiptVerifierPolicy.__dataclass_fields__)
        policy = SelectiveMemoryTombReceiptVerifierPolicy(**{str(k): v for k, v in dict(payload.get("policy", {})).items() if str(k) in allowed})
    policy = policy or build_default_policy()
    try:
        dist_packet = _packet_from_payload(payload)
        if dist_packet is None:
            return _blocked("selective_memory_tomb_receipt_verifier_blocked_missing_distillation_packet", [SelectiveMemoryTombReceiptFinding("error", "missing_distillation_packet", "distillation packet is required")])
        records = _record_index(dist_packet)
        if records is None:
            return _blocked("selective_memory_tomb_receipt_verifier_blocked_invalid_distillation_packet", [SelectiveMemoryTombReceiptFinding("error", "invalid_distillation_packet", "distillation packet records are invalid")])
        gate_packet = _gate_packet_from_payload(payload)
        if gate_packet is None:
            return _blocked("selective_memory_tomb_receipt_verifier_blocked_missing_receipt_gate_packet", [SelectiveMemoryTombReceiptFinding("error", "missing_receipt_gate_packet", "receipt gate packet is required")])
        gates = _gate_index(gate_packet)
        if gates is None:
            return _blocked("selective_memory_tomb_receipt_verifier_blocked_invalid_receipt_gate_packet", [SelectiveMemoryTombReceiptFinding("error", "invalid_receipt_gate_packet", "receipt gate decisions are invalid")])
        raw_claims = _claims_from_payload(payload)
        if raw_claims is None:
            return _blocked("selective_memory_tomb_receipt_verifier_blocked_missing_tomb_claim", [SelectiveMemoryTombReceiptFinding("error", "missing_tomb_claim", "tomb claim is required")])
        if not isinstance(raw_claims, Sequence) or isinstance(raw_claims, (str, bytes, bytearray)) or not raw_claims:
            return _blocked("selective_memory_tomb_receipt_verifier_blocked_invalid_tomb_claim", [SelectiveMemoryTombReceiptFinding("error", "invalid_tomb_claim", "tomb claims must be a non-empty list")])
        claims: list[SelectiveMemoryTombReceiptClaim] = []
        for raw in raw_claims:
            if not isinstance(raw, Mapping):
                return _blocked("selective_memory_tomb_receipt_verifier_blocked_invalid_tomb_claim", [SelectiveMemoryTombReceiptFinding("error", "invalid_tomb_claim", "tomb claim must be a mapping")])
            try:
                claims.append(SelectiveMemoryTombReceiptClaim.from_mapping(raw))
            except (TypeError, ValueError) as exc:
                return _blocked("selective_memory_tomb_receipt_verifier_blocked_invalid_tomb_claim", [SelectiveMemoryTombReceiptFinding("error", "invalid_tomb_claim", str(exc))])
        findings: list[SelectiveMemoryTombReceiptFinding] = []
        packet_scope_sets = {_as_tuple(record.get("source_scope_keys")) for record in records.values() if _as_tuple(record.get("source_scope_keys"))}
        mixed_scope_warning = False
        if len(packet_scope_sets) > 1:
            if policy.allow_mixed_scope_diagnostic_packet:
                findings.append(SelectiveMemoryTombReceiptFinding("warning", "mixed_scope_diagnostic_packet", "packet contains multiple source scopes"))
                mixed_scope_warning = True
            elif policy.require_scope_alignment:
                findings.append(SelectiveMemoryTombReceiptFinding("error", "scope_mismatch", "packet contains multiple source scopes"))
                return _blocked("selective_memory_tomb_receipt_verifier_blocked_scope_mismatch", findings)
        verification_records: list[SelectiveMemoryTombReceiptVerificationRecord] = []
        for claim in claims:
            record = records.get(claim.record_id)
            gate = gates.get(claim.record_id)
            if record is None or gate is None:
                return _blocked("selective_memory_tomb_receipt_verifier_blocked_invalid_tomb_claim", [SelectiveMemoryTombReceiptFinding("error", "invalid_tomb_claim", "claim references unknown prior evidence", claim.claim_id, claim.record_id)])
            blockers, warning = _claim_blockers(claim, record, gate, dist_packet, policy)
            if blockers:
                code = blockers[0]
                findings.append(SelectiveMemoryTombReceiptFinding("error", code, f"tomb receipt claim blocked: {code}", claim.claim_id, claim.record_id))
                return _blocked(_status_for(code), findings)
            warnings = warning or mixed_scope_warning
            if warnings:
                findings.append(SelectiveMemoryTombReceiptFinding("warning", "tomb_receipt_verification_warning", "claim verified only as warning/diagnostic metadata", claim.claim_id, claim.record_id))
            gate_decision = str(gate.get("gate_decision") or "")
            outcome = _outcome_for(claim, gate_decision, warnings)
            verification_records.append(
                SelectiveMemoryTombReceiptVerificationRecord(
                    claim_id=claim.claim_id,
                    record_id=claim.record_id,
                    tomb_claim_type=claim.tomb_claim_type,
                    claimed_distillation_decision=claim.claimed_distillation_decision,
                    receipt_gate_decision=gate_decision,
                    verification_outcome=outcome,
                    safe_next_actions=_safe_actions_for(outcome, warnings),
                ).with_digest()
            )
        counts: dict[str, int] = {"claim_count": len(verification_records), "warning_count": sum(1 for f in findings if f.severity == "warning")}
        for rec in verification_records:
            counts[rec.verification_outcome] = counts.get(rec.verification_outcome, 0) + 1
            counts[rec.tomb_claim_type] = counts.get(rec.tomb_claim_type, 0) + 1
        status: TombReceiptVerifierStatus = "selective_memory_tomb_receipt_verifier_ready_with_warnings" if counts["warning_count"] else "selective_memory_tomb_receipt_verifier_ready"
        out_packet = SelectiveMemoryTombReceiptVerificationPacket(policy.schema_version, tuple(verification_records)).with_digest()
        report = SelectiveMemoryTombReceiptVerificationReport(status, tuple(findings), dict(sorted(counts.items())), "")
        report = replace(report, digest=_digest(report.to_dict()))
        return SelectiveMemoryTombReceiptVerificationResult(status, out_packet, report, _digest({"packet": out_packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:  # defensive metadata validation boundary; no side effects are attempted
        return _blocked("selective_memory_tomb_receipt_verifier_failed", [SelectiveMemoryTombReceiptFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: SelectiveMemoryTombReceiptVerifierPolicy | None = None) -> SelectiveMemoryTombReceiptVerificationResult:
    return evaluate_selective_memory_tomb_receipt_verifier(payload, policy)


__all__ = [
    "FORBIDDEN_NEXT_STEPS",
    "SAFE_NEXT_ACTIONS",
    "TOMB_CLAIM_TYPES",
    "SelectiveMemoryTombReceiptVerifierPolicy",
    "SelectiveMemoryTombReceiptVerifierInput",
    "SelectiveMemoryTombReceiptClaim",
    "SelectiveMemoryTombReceiptFinding",
    "SelectiveMemoryTombReceiptVerificationRecord",
    "SelectiveMemoryTombReceiptVerificationPacket",
    "SelectiveMemoryTombReceiptVerificationReport",
    "SelectiveMemoryTombReceiptVerificationResult",
    "build_default_policy",
    "validate_policy",
    "evaluate_selective_memory_tomb_receipt_verifier",
    "evaluate_packet",
]
