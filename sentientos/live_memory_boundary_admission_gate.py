"""Deterministic metadata-only live memory boundary admission gate.

The gate evaluates explicit JSON metadata from the distillation contract, receipt
 gate, tomb verifier, and governed writer adapter. It is review-only: it never
writes live memory, deletes memory, mutates indexes, persists capsules,
assembles prompts, executes actions, invokes remote services, discloses
externally, creates policy, grants authority, infers consent, or asserts truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal, Mapping, Sequence

LiveMemoryBoundaryAdmissionStatus = Literal[
    "live_memory_boundary_admission_ready",
    "live_memory_boundary_admission_ready_with_warnings",
    "live_memory_boundary_admission_deferred_for_operator_review",
    "live_memory_boundary_admission_blocked_missing_distillation_packet",
    "live_memory_boundary_admission_blocked_invalid_distillation_packet",
    "live_memory_boundary_admission_blocked_missing_receipt_gate_packet",
    "live_memory_boundary_admission_blocked_invalid_receipt_gate_packet",
    "live_memory_boundary_admission_blocked_missing_tomb_verifier_packet",
    "live_memory_boundary_admission_blocked_invalid_tomb_verifier_packet",
    "live_memory_boundary_admission_blocked_missing_writer_packet",
    "live_memory_boundary_admission_blocked_invalid_writer_packet",
    "live_memory_boundary_admission_blocked_missing_admission_candidate",
    "live_memory_boundary_admission_blocked_invalid_admission_candidate",
    "live_memory_boundary_admission_blocked_digest_mismatch",
    "live_memory_boundary_admission_blocked_decision_mismatch",
    "live_memory_boundary_admission_blocked_writer_not_ready",
    "live_memory_boundary_admission_blocked_tomb_not_verified",
    "live_memory_boundary_admission_blocked_live_write_claim",
    "live_memory_boundary_admission_blocked_live_delete_claim",
    "live_memory_boundary_admission_blocked_index_mutation_claim",
    "live_memory_boundary_admission_blocked_prompt_materialization",
    "live_memory_boundary_admission_blocked_action_execution",
    "live_memory_boundary_admission_blocked_external_disclosure",
    "live_memory_boundary_admission_blocked_authority_smuggling",
    "live_memory_boundary_admission_blocked_raw_payload_leak",
    "live_memory_boundary_admission_blocked_scope_mismatch",
    "live_memory_boundary_admission_invalid",
    "live_memory_boundary_admission_failed",
]

AdmissionDecision = Literal[
    "boundary_review_candidate_ready",
    "boundary_review_candidate_ready_with_warnings",
    "boundary_review_deferred_for_operator_review",
    "boundary_review_blocked",
    "boundary_review_rejected",
    "boundary_review_noop",
]

ADMISSION_CANDIDATE_TYPES = frozenset(
    {
        "ai_capsule_boundary_candidate",
        "human_summary_boundary_candidate",
        "dual_capsule_boundary_candidate",
        "protect_receipt_boundary_candidate",
        "merge_receipt_boundary_candidate",
        "tomb_receipt_boundary_candidate",
        "tomb_deferred_boundary_candidate",
        "operator_review_boundary_candidate",
        "noop_boundary_candidate",
        "mixed_boundary_candidate",
    }
)
TOMB_CANDIDATE_TYPES = frozenset({"tomb_receipt_boundary_candidate", "tomb_deferred_boundary_candidate"})
READY_WRITER_DECISIONS = frozenset({"writer_preview_ready", "writer_artifact_ready", "writer_artifact_ready_with_warnings"})
NON_BLOCKING_WRITER_DECISIONS = READY_WRITER_DECISIONS | frozenset({"writer_deferred_for_operator_review", "writer_rejected", "writer_noop"})
READY_TOMB_OUTCOMES = frozenset({"tomb_receipt_verified", "tomb_receipt_verified_with_warnings", "tomb_receipt_deferred_for_operator_review", "tomb_receipt_rejected", "tomb_receipt_noop"})
SAFE_NEXT_ACTIONS = (
    "no_action_allowed",
    "inspect_boundary_admission_packet",
    "operator_review_required",
    "prepare_live_memory_review_packet_later",
    "prepare_memory_commit_plan_later",
    "prepare_tomb_review_packet_later",
    "prepare_capsule_review_packet_later",
    "rerun_with_matching_digest",
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
    "call_append_memory",
    "call_purge_memory",
    "call_apply_forgetting_curve",
    "call_curate_memory",
    "call_summarize_memory",
    "assemble_prompt_now",
    "retrieve_live_context",
    "execute_action_ingress",
    "infer_truth_from_admission",
    "infer_authority_from_admission",
    "infer_consent_from_admission",
    "convert_admission_to_policy",
    "convert_admission_to_action",
    "bypass_distillation_contract",
    "bypass_receipt_gate",
    "bypass_tomb_verifier",
    "bypass_governed_writer_adapter",
    "bypass_operator_review",
    "enable_external_disclosure",
)
INVARIANTS: dict[str, bool] = {
    "admission_is_not_memory_write": True,
    "admission_is_not_memory_deletion": True,
    "admission_is_not_index_mutation": True,
    "admission_is_not_capsule_persistence": True,
    "admission_is_not_prompt_assembly": True,
    "admission_is_not_truth": True,
    "admission_is_not_policy": True,
    "admission_is_not_authority": True,
    "admission_is_not_consent": True,
    "admission_does_not_execute_action": True,
    "admission_does_not_disclose_externally": True,
    "live_memory_write_enabled": False,
    "live_memory_deletion_enabled": False,
    "live_index_mutation_enabled": False,
    "capsule_persistence_enabled": False,
    "prompt_materialization_enabled": False,
    "external_disclosure_enabled": False,
    "remote_service_enabled": False,
    "default_deny_live_boundary": True,
    "future_review_required": True,
}
_RAW_KEYS = frozenset({"raw_payload", "raw_private_payload", "private_payload", "raw_transcript", "transcript", "provider_prompt", "secret", "api_key", "password", "token", "encoded_media", "media_payload", "base64", "image", "audio", "video", "screenshot", "thumbnail"})
_MEDIA_RE = re.compile(r"(?:data:(?:image|audio|video)/|base64|[A-Za-z0-9+/]{120,}={0,2})")
_AUTHORITY_RE = re.compile(r"\b(authority|authorize|grant permission|policy now|consent granted|infer consent|infer authority|infer truth|convert.*policy|approved to act|override blocker|bypass)\b", re.I)
_PROMPT_RE = re.compile(r"\b(assemble prompt|prompt materialization|provider prompt|system prompt|retrieve live context)\b", re.I)
_ACTION_RE = re.compile(r"\b(execute action|action ingress|call_append_memory|call_purge_memory|mutate_vector_index|write_live_memory|delete_live_memory|delete memory|purge_live_memory|apply_forgetting_curve|curate_memory|summarize_memory)\b", re.I)
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
class LiveMemoryBoundaryAdmissionPolicy:
    schema_version: str = "live-memory-boundary-admission-gate.v1"
    default_boundary_posture: str = "deny"
    allow_boundary_review_candidates: bool = True
    allow_warning_candidates: bool = True
    allow_operator_review_candidates: bool = True
    allow_noop_candidates: bool = True
    allow_mixed_scope_diagnostic_packet: bool = False
    require_matching_source_digest: bool = True
    require_receipt_gate_admissible: bool = True
    require_writer_ready: bool = True
    require_tomb_verifier_for_tomb_candidates: bool = True
    require_scope_alignment: bool = True
    block_live_write_claims: bool = True
    block_live_delete_claims: bool = True
    block_index_mutation_claims: bool = True
    block_capsule_persistence_claims: bool = True
    block_hard_override_attempts: bool = True


@dataclass(frozen=True)
class LiveMemoryBoundaryAdmissionCandidate:
    candidate_id: str
    candidate_type: str
    record_id: str
    source_digest: str
    claimed_distillation_decision: str
    claimed_receipt_gate_decision: str
    claimed_writer_decision: str
    claimed_tomb_verifier_outcome: str | None = None
    source_scope_keys: tuple[str, ...] = ()
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
    def from_mapping(cls, payload: Mapping[str, Any]) -> "LiveMemoryBoundaryAdmissionCandidate":
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, Mapping):
            metadata = {}
        return cls(
            candidate_id=str(payload["candidate_id"]),
            candidate_type=str(payload["candidate_type"]),
            record_id=str(payload["record_id"]),
            source_digest=str(payload["source_digest"]),
            claimed_distillation_decision=str(payload["claimed_distillation_decision"]),
            claimed_receipt_gate_decision=str(payload["claimed_receipt_gate_decision"]),
            claimed_writer_decision=str(payload["claimed_writer_decision"]),
            claimed_tomb_verifier_outcome=str(payload["claimed_tomb_verifier_outcome"]) if payload.get("claimed_tomb_verifier_outcome") is not None else None,
            source_scope_keys=_as_tuple(payload.get("source_scope_keys")),
            requested_next_actions=_as_tuple(payload.get("requested_next_actions")),
            metadata=dict(metadata),
            hard_override_requested=bool(payload.get("hard_override_requested") or payload.get("override_hard_blocker")),
            prompt_materialization_requested=bool(payload.get("prompt_materialization_requested")),
            action_execution_requested=bool(payload.get("action_execution_requested")),
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
class LiveMemoryBoundaryAdmissionInput:
    distillation_packet: Mapping[str, Any]
    receipt_gate_packet: Mapping[str, Any]
    writer_packet: Mapping[str, Any]
    admission_candidates: tuple[LiveMemoryBoundaryAdmissionCandidate, ...]
    tomb_verifier_packet: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class LiveMemoryBoundaryAdmissionFinding:
    severity: str
    code: str
    message: str
    candidate_id: str | None = None
    record_id: str | None = None


@dataclass(frozen=True)
class LiveMemoryBoundaryAdmissionRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    admission_decision: str
    distillation_decision: str
    receipt_gate_decision: str
    writer_decision: str
    tomb_verifier_outcome: str | None = None
    safe_next_actions: tuple[str, ...] = ()
    digest: str = ""

    def with_digest(self) -> "LiveMemoryBoundaryAdmissionRecord":
        data = asdict(self)
        data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class LiveMemoryBoundaryAdmissionPacket:
    schema_version: str
    records: tuple[LiveMemoryBoundaryAdmissionRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        out = {"schema_version": self.schema_version, "records": [asdict(r) for r in self.records], "forbidden_next_steps": list(self.forbidden_next_steps), **INVARIANTS}
        out["digest"] = self.digest
        return out

    def with_digest(self) -> "LiveMemoryBoundaryAdmissionPacket":
        data = self.to_dict()
        data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class LiveMemoryBoundaryAdmissionReport:
    status: LiveMemoryBoundaryAdmissionStatus
    findings: tuple[LiveMemoryBoundaryAdmissionFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [asdict(f) for f in self.findings], "summary_counts": dict(self.summary_counts), "digest": self.digest}


@dataclass(frozen=True)
class LiveMemoryBoundaryAdmissionResult:
    status: LiveMemoryBoundaryAdmissionStatus
    packet: LiveMemoryBoundaryAdmissionPacket | None
    report: LiveMemoryBoundaryAdmissionReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> LiveMemoryBoundaryAdmissionPolicy:
    return LiveMemoryBoundaryAdmissionPolicy()


def validate_policy(policy: LiveMemoryBoundaryAdmissionPolicy) -> dict[str, Any]:
    findings: list[str] = []
    if policy.default_boundary_posture != "deny":
        findings.append("default_boundary_posture must be deny")
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
    raw = payload.get("admission_candidates") or payload.get("admission_candidate") or payload.get("candidate")
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


def _blocked(status: LiveMemoryBoundaryAdmissionStatus, findings: Sequence[LiveMemoryBoundaryAdmissionFinding]) -> LiveMemoryBoundaryAdmissionResult:
    counts = {"candidate_count": 0, "warning_count": sum(1 for f in findings if f.severity == "warning"), "error_count": sum(1 for f in findings if f.severity == "error")}
    report = LiveMemoryBoundaryAdmissionReport(status, tuple(findings), counts)
    report = replace(report, digest=_digest(report.to_dict()))
    return LiveMemoryBoundaryAdmissionResult(status, None, report, _digest({"packet": None, "report": report.to_dict()}))


def _status_for_blocker(blocker: str) -> LiveMemoryBoundaryAdmissionStatus:
    mapping: dict[str, LiveMemoryBoundaryAdmissionStatus] = {
        "digest_mismatch": "live_memory_boundary_admission_blocked_digest_mismatch",
        "decision_mismatch": "live_memory_boundary_admission_blocked_decision_mismatch",
        "writer_not_ready": "live_memory_boundary_admission_blocked_writer_not_ready",
        "tomb_not_verified": "live_memory_boundary_admission_blocked_tomb_not_verified",
        "live_write_claim": "live_memory_boundary_admission_blocked_live_write_claim",
        "live_delete_claim": "live_memory_boundary_admission_blocked_live_delete_claim",
        "index_mutation_claim": "live_memory_boundary_admission_blocked_index_mutation_claim",
        "prompt_materialization": "live_memory_boundary_admission_blocked_prompt_materialization",
        "action_execution": "live_memory_boundary_admission_blocked_action_execution",
        "external_disclosure": "live_memory_boundary_admission_blocked_external_disclosure",
        "authority_smuggling": "live_memory_boundary_admission_blocked_authority_smuggling",
        "raw_payload_leak": "live_memory_boundary_admission_blocked_raw_payload_leak",
        "scope_mismatch": "live_memory_boundary_admission_blocked_scope_mismatch",
    }
    return mapping.get(blocker, "live_memory_boundary_admission_blocked_invalid_admission_candidate")


def _candidate_blocker(candidate: LiveMemoryBoundaryAdmissionCandidate, dist: Mapping[str, Any], gate: Mapping[str, Any], writer: Mapping[str, Any], tomb: Mapping[str, Any] | None, payload: Mapping[str, Any], policy: LiveMemoryBoundaryAdmissionPolicy) -> str | None:
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
        return "live_write_claim"
    if policy.require_scope_alignment and not policy.allow_mixed_scope_diagnostic_packet:
        scopes = [_as_tuple(dist.get("source_scope_keys")), _as_tuple(gate.get("source_scope_keys")), _as_tuple(writer.get("source_scope_keys")), candidate.source_scope_keys]
        if tomb is not None:
            scopes.append(_as_tuple(tomb.get("source_scope_keys")))
        non_empty = {scope for scope in scopes if scope}
        if len(non_empty) > 1:
            return "scope_mismatch"
    if policy.require_matching_source_digest:
        expected = {str(dist.get("source_digest") or ""), str(gate.get("source_digest") or ""), str(writer.get("source_digest") or "")}
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
    if policy.require_writer_ready and writer_decision not in NON_BLOCKING_WRITER_DECISIONS:
        return "writer_not_ready"
    if candidate.candidate_type in TOMB_CANDIDATE_TYPES:
        if tomb is None:
            return "tomb_not_verified"
        tomb_outcome = str(tomb.get("verification_outcome") or tomb.get("tomb_verifier_outcome") or "")
        if candidate.claimed_tomb_verifier_outcome != tomb_outcome:
            return "decision_mismatch"
        if tomb_outcome not in READY_TOMB_OUTCOMES:
            return "tomb_not_verified"
    return None


def _decision_for(candidate: LiveMemoryBoundaryAdmissionCandidate, writer_decision: str, warning: bool) -> AdmissionDecision:
    if candidate.candidate_type == "noop_boundary_candidate" or writer_decision == "writer_noop":
        return "boundary_review_noop"
    if writer_decision == "writer_rejected":
        return "boundary_review_rejected"
    if candidate.candidate_type in {"operator_review_boundary_candidate", "tomb_deferred_boundary_candidate"} or writer_decision == "writer_deferred_for_operator_review":
        return "boundary_review_deferred_for_operator_review"
    if warning or writer_decision == "writer_artifact_ready_with_warnings":
        return "boundary_review_candidate_ready_with_warnings"
    return "boundary_review_candidate_ready"


def _safe_actions_for(decision: str, candidate_type: str) -> tuple[str, ...]:
    actions = ["no_action_allowed", "inspect_boundary_admission_packet", "sustain_default_deny", "defer_to_memory_runtime_boundary", "defer_to_self_improvement_ingress"]
    if decision == "boundary_review_deferred_for_operator_review":
        actions.append("operator_review_required")
    if decision in {"boundary_review_candidate_ready", "boundary_review_candidate_ready_with_warnings"}:
        actions.extend(["prepare_live_memory_review_packet_later", "prepare_memory_commit_plan_later"])
    if candidate_type in TOMB_CANDIDATE_TYPES:
        actions.append("prepare_tomb_review_packet_later")
    elif "capsule" in candidate_type:
        actions.append("prepare_capsule_review_packet_later")
    return tuple(dict.fromkeys(actions))


def _policy_from_payload(payload: Mapping[str, Any], policy: LiveMemoryBoundaryAdmissionPolicy | None) -> LiveMemoryBoundaryAdmissionPolicy:
    if policy is not None:
        return policy
    raw = payload.get("policy")
    if isinstance(raw, Mapping):
        allowed = set(LiveMemoryBoundaryAdmissionPolicy.__dataclass_fields__)
        return LiveMemoryBoundaryAdmissionPolicy(**{str(k): v for k, v in raw.items() if str(k) in allowed})
    return build_default_policy()


def evaluate_live_memory_boundary_admission_gate(payload: Mapping[str, Any], policy: LiveMemoryBoundaryAdmissionPolicy | None = None) -> LiveMemoryBoundaryAdmissionResult:
    try:
        active_policy = _policy_from_payload(payload, policy)
        validation = validate_policy(active_policy)
        if not validation["ok"]:
            return _blocked("live_memory_boundary_admission_invalid", [LiveMemoryBoundaryAdmissionFinding("error", "invalid_policy", "; ".join(validation["findings"]))])
        if _contains_forbidden_payload(payload):
            return _blocked("live_memory_boundary_admission_blocked_raw_payload_leak", [LiveMemoryBoundaryAdmissionFinding("error", "raw_payload_leak", "input contains raw/private/media/secret/provider-prompt payload markers")])
        dist_packet = _packet(payload, "distillation_packet")
        if dist_packet is None:
            return _blocked("live_memory_boundary_admission_blocked_missing_distillation_packet", [LiveMemoryBoundaryAdmissionFinding("error", "missing_distillation_packet", "distillation packet is required")])
        dist_records = _records(dist_packet, ("distillation_decision", "source_digest"))
        if dist_records is None:
            return _blocked("live_memory_boundary_admission_blocked_invalid_distillation_packet", [LiveMemoryBoundaryAdmissionFinding("error", "invalid_distillation_packet", "distillation packet records are invalid")])
        gate_packet = _packet(payload, "receipt_gate_packet")
        if gate_packet is None:
            return _blocked("live_memory_boundary_admission_blocked_missing_receipt_gate_packet", [LiveMemoryBoundaryAdmissionFinding("error", "missing_receipt_gate_packet", "receipt gate packet is required")])
        gate_records = _records(gate_packet, ("source_digest",))
        if gate_records is None or any(not (r.get("gate_decision") or r.get("receipt_gate_decision")) for r in gate_records.values()):
            return _blocked("live_memory_boundary_admission_blocked_invalid_receipt_gate_packet", [LiveMemoryBoundaryAdmissionFinding("error", "invalid_receipt_gate_packet", "receipt gate packet records are invalid")])
        writer_packet = _packet(payload, "writer_packet", ("governed_writer_packet",))
        if writer_packet is None:
            return _blocked("live_memory_boundary_admission_blocked_missing_writer_packet", [LiveMemoryBoundaryAdmissionFinding("error", "missing_writer_packet", "governed writer packet is required")])
        writer_records = _records(writer_packet, ("writer_decision", "source_digest"))
        if writer_records is None:
            return _blocked("live_memory_boundary_admission_blocked_invalid_writer_packet", [LiveMemoryBoundaryAdmissionFinding("error", "invalid_writer_packet", "writer packet records are invalid")])
        raw_candidates = _candidate_payloads(payload)
        if raw_candidates is None or not raw_candidates:
            return _blocked("live_memory_boundary_admission_blocked_missing_admission_candidate", [LiveMemoryBoundaryAdmissionFinding("error", "missing_admission_candidate", "admission candidate is required")])
        candidates: list[LiveMemoryBoundaryAdmissionCandidate] = []
        needs_tomb = False
        for raw in raw_candidates:
            if not isinstance(raw, Mapping):
                return _blocked("live_memory_boundary_admission_blocked_invalid_admission_candidate", [LiveMemoryBoundaryAdmissionFinding("error", "invalid_admission_candidate", "candidate must be a mapping")])
            try:
                candidate = LiveMemoryBoundaryAdmissionCandidate.from_mapping(raw)
            except (KeyError, TypeError, ValueError) as exc:
                return _blocked("live_memory_boundary_admission_blocked_invalid_admission_candidate", [LiveMemoryBoundaryAdmissionFinding("error", "invalid_admission_candidate", str(exc))])
            if candidate.candidate_type not in ADMISSION_CANDIDATE_TYPES:
                return _blocked("live_memory_boundary_admission_blocked_invalid_admission_candidate", [LiveMemoryBoundaryAdmissionFinding("error", "invalid_admission_candidate", "unknown candidate type", candidate.candidate_id, candidate.record_id)])
            needs_tomb = needs_tomb or candidate.candidate_type in TOMB_CANDIDATE_TYPES
            candidates.append(candidate)
        tomb_records: dict[str, Mapping[str, Any]] = {}
        tomb_packet = _packet(payload, "tomb_verifier_packet")
        if needs_tomb and active_policy.require_tomb_verifier_for_tomb_candidates:
            if tomb_packet is None:
                return _blocked("live_memory_boundary_admission_blocked_missing_tomb_verifier_packet", [LiveMemoryBoundaryAdmissionFinding("error", "missing_tomb_verifier_packet", "tomb verifier packet is required for tomb candidates")])
            parsed_tomb = _records(tomb_packet, ("source_digest",))
            if parsed_tomb is None or any(not (r.get("verification_outcome") or r.get("tomb_verifier_outcome")) for r in parsed_tomb.values()):
                return _blocked("live_memory_boundary_admission_blocked_invalid_tomb_verifier_packet", [LiveMemoryBoundaryAdmissionFinding("error", "invalid_tomb_verifier_packet", "tomb verifier packet records are invalid")])
            tomb_records = parsed_tomb
        findings: list[LiveMemoryBoundaryAdmissionFinding] = []
        scope_sets = {_as_tuple(r.get("source_scope_keys")) for packet_records in (dist_records, gate_records, writer_records, tomb_records) for r in packet_records.values() if _as_tuple(r.get("source_scope_keys"))}
        mixed_scope_warning = False
        if len(scope_sets) > 1:
            if active_policy.allow_mixed_scope_diagnostic_packet:
                findings.append(LiveMemoryBoundaryAdmissionFinding("warning", "mixed_scope_diagnostic_packet", "packet contains multiple source scopes"))
                mixed_scope_warning = True
            elif active_policy.require_scope_alignment:
                findings.append(LiveMemoryBoundaryAdmissionFinding("error", "scope_mismatch", "packet contains multiple source scopes"))
                return _blocked("live_memory_boundary_admission_blocked_scope_mismatch", findings)
        records: list[LiveMemoryBoundaryAdmissionRecord] = []
        for candidate in candidates:
            dist = dist_records.get(candidate.record_id)
            gate = gate_records.get(candidate.record_id)
            writer = writer_records.get(candidate.record_id)
            tomb = tomb_records.get(candidate.record_id) if tomb_records else None
            if dist is None or gate is None or writer is None:
                return _blocked("live_memory_boundary_admission_blocked_invalid_admission_candidate", [LiveMemoryBoundaryAdmissionFinding("error", "invalid_admission_candidate", "candidate references unknown upstream evidence", candidate.candidate_id, candidate.record_id)])
            blocker = _candidate_blocker(candidate, dist, gate, writer, tomb, payload, active_policy)
            if blocker:
                findings.append(LiveMemoryBoundaryAdmissionFinding("error", blocker, f"admission candidate blocked: {blocker}", candidate.candidate_id, candidate.record_id))
                return _blocked(_status_for_blocker(blocker), findings)
            warning = mixed_scope_warning or bool(candidate.metadata.get("warning_only") or candidate.metadata.get("diagnostic_warning")) or str(writer.get("writer_decision") or "") == "writer_artifact_ready_with_warnings"
            if warning:
                findings.append(LiveMemoryBoundaryAdmissionFinding("warning", "admission_warning", "candidate is warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
            decision = _decision_for(candidate, str(writer.get("writer_decision") or ""), warning)
            record = LiveMemoryBoundaryAdmissionRecord(
                candidate_id=candidate.candidate_id,
                record_id=candidate.record_id,
                candidate_type=candidate.candidate_type,
                admission_decision=decision,
                distillation_decision=str(dist.get("distillation_decision") or ""),
                receipt_gate_decision=str(gate.get("gate_decision") or gate.get("receipt_gate_decision") or ""),
                writer_decision=str(writer.get("writer_decision") or ""),
                tomb_verifier_outcome=str(tomb.get("verification_outcome") or tomb.get("tomb_verifier_outcome") or "") if tomb is not None else None,
                safe_next_actions=_safe_actions_for(decision, candidate.candidate_type),
            ).with_digest()
            records.append(record)
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for f in findings if f.severity == "warning")}
        for rec in records:
            counts[rec.admission_decision] = counts.get(rec.admission_decision, 0) + 1
            counts[rec.candidate_type] = counts.get(rec.candidate_type, 0) + 1
        decisions = {rec.admission_decision for rec in records}
        if counts["warning_count"]:
            status: LiveMemoryBoundaryAdmissionStatus = "live_memory_boundary_admission_ready_with_warnings"
        elif decisions <= {"boundary_review_deferred_for_operator_review"}:
            status = "live_memory_boundary_admission_deferred_for_operator_review"
        elif decisions <= {"boundary_review_noop"}:
            status = "live_memory_boundary_admission_ready"
        elif "boundary_review_rejected" in decisions and len(decisions) == 1:
            status = "live_memory_boundary_admission_deferred_for_operator_review"
        else:
            status = "live_memory_boundary_admission_ready"
        packet = LiveMemoryBoundaryAdmissionPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = LiveMemoryBoundaryAdmissionReport(status, tuple(findings), dict(sorted(counts.items())), "")
        report = replace(report, digest=_digest(report.to_dict()))
        return LiveMemoryBoundaryAdmissionResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("live_memory_boundary_admission_failed", [LiveMemoryBoundaryAdmissionFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: LiveMemoryBoundaryAdmissionPolicy | None = None) -> LiveMemoryBoundaryAdmissionResult:
    return evaluate_live_memory_boundary_admission_gate(payload, policy)


__all__ = [
    "ADMISSION_CANDIDATE_TYPES",
    "FORBIDDEN_NEXT_STEPS",
    "SAFE_NEXT_ACTIONS",
    "LiveMemoryBoundaryAdmissionPolicy",
    "LiveMemoryBoundaryAdmissionInput",
    "LiveMemoryBoundaryAdmissionCandidate",
    "LiveMemoryBoundaryAdmissionFinding",
    "LiveMemoryBoundaryAdmissionRecord",
    "LiveMemoryBoundaryAdmissionPacket",
    "LiveMemoryBoundaryAdmissionReport",
    "LiveMemoryBoundaryAdmissionResult",
    "build_default_policy",
    "validate_policy",
    "evaluate_live_memory_boundary_admission_gate",
    "evaluate_packet",
]
