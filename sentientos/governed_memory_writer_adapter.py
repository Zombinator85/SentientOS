"""Deterministic governed local memory writer adapter.

This module evaluates metadata-only writer candidates produced after selective
memory distillation, receipt-gating, and tomb receipt verification. Evaluation is
pure: it never writes live memory, mutates indexes, assembles prompts, executes
actions, invokes remote services, or discloses externally. The isolated
``write_artifact`` helper writes deterministic JSON only to explicit safe local
artifact paths after the same policy checks pass.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

GovernedMemoryWriterStatus = Literal[
    "governed_memory_writer_ready",
    "governed_memory_writer_ready_with_warnings",
    "governed_memory_writer_dry_run_ready",
    "governed_memory_writer_blocked_missing_distillation_packet",
    "governed_memory_writer_blocked_invalid_distillation_packet",
    "governed_memory_writer_blocked_missing_receipt_gate_packet",
    "governed_memory_writer_blocked_invalid_receipt_gate_packet",
    "governed_memory_writer_blocked_missing_tomb_verifier_packet",
    "governed_memory_writer_blocked_invalid_tomb_verifier_packet",
    "governed_memory_writer_blocked_missing_writer_candidate",
    "governed_memory_writer_blocked_invalid_writer_candidate",
    "governed_memory_writer_blocked_digest_mismatch",
    "governed_memory_writer_blocked_decision_mismatch",
    "governed_memory_writer_blocked_receipt_gate_not_admissible",
    "governed_memory_writer_blocked_tomb_verifier_not_ready",
    "governed_memory_writer_blocked_live_memory_path",
    "governed_memory_writer_blocked_missing_output_path",
    "governed_memory_writer_blocked_unsafe_output_path",
    "governed_memory_writer_blocked_raw_payload_leak",
    "governed_memory_writer_blocked_authority_smuggling",
    "governed_memory_writer_blocked_prompt_materialization",
    "governed_memory_writer_blocked_action_execution",
    "governed_memory_writer_blocked_external_disclosure",
    "governed_memory_writer_blocked_scope_mismatch",
    "governed_memory_writer_invalid",
    "governed_memory_writer_failed",
]

WriterDecision = Literal[
    "writer_preview_ready",
    "writer_artifact_ready",
    "writer_artifact_ready_with_warnings",
    "writer_deferred_for_operator_review",
    "writer_blocked",
    "writer_rejected",
    "writer_noop",
]

WRITER_CANDIDATE_TYPES = frozenset(
    {
        "ai_capsule_artifact_candidate",
        "human_summary_artifact_candidate",
        "dual_capsule_artifact_candidate",
        "protect_receipt_artifact_candidate",
        "merge_receipt_artifact_candidate",
        "tomb_receipt_archive_candidate",
        "tomb_deferred_archive_candidate",
        "operator_review_archive_candidate",
        "no_op_artifact_candidate",
        "mixed_writer_artifact_candidate",
    }
)
WRITER_MODES = frozenset({"dry_run_preview", "explicit_artifact_write", "explicit_artifact_validate_only"})
TOMB_CANDIDATE_TYPES = frozenset({"tomb_receipt_archive_candidate", "tomb_deferred_archive_candidate"})
DELETION_ADJACENT_TYPES = TOMB_CANDIDATE_TYPES

SAFE_NEXT_ACTIONS = (
    "no_action_allowed",
    "inspect_writer_packet",
    "operator_review_required",
    "run_dry_preview",
    "write_explicit_artifact_later",
    "archive_tomb_receipt_later",
    "archive_capsule_receipt_later",
    "archive_protect_receipt_later",
    "archive_merge_receipt_later",
    "rerun_with_matching_digest",
    "rerun_with_admissible_receipt_gate",
    "rerun_with_ready_tomb_verifier",
    "rerun_with_safe_output_path",
    "rerun_with_scope_alignment",
    "defer_to_memory_runtime_boundary",
    "defer_to_self_improvement_ingress",
)

FORBIDDEN_NEXT_STEPS = (
    "write_live_memory_now",
    "delete_memory_now",
    "purge_memory_now",
    "mutate_raw_fragment",
    "mutate_vector_index",
    "mutate_distilled_memory",
    "silently_write_memory",
    "silently_delete_memory",
    "claim_unverified_deletion",
    "claim_unverified_capsule_persistence",
    "claim_policy_created",
    "claim_authority_granted",
    "call_append_memory",
    "call_purge_memory",
    "call_apply_forgetting_curve",
    "call_curate_memory",
    "call_summarize_memory",
    "assemble_prompt_now",
    "retrieve_live_context",
    "execute_action_ingress",
    "infer_truth_from_writer",
    "infer_authority_from_writer",
    "infer_consent_from_writer",
    "convert_writer_receipt_to_policy",
    "convert_writer_to_action",
    "bypass_distillation_contract",
    "bypass_receipt_gate",
    "bypass_tomb_verifier",
    "bypass_memory_tomb",
    "bypass_operator_review",
    "enable_external_disclosure",
)

_INVARIANTS: dict[str, bool] = {
    "writer_is_not_truth": True,
    "writer_is_not_policy": True,
    "writer_is_not_authority": True,
    "writer_is_not_consent": True,
    "writer_does_not_execute_action": True,
    "writer_does_not_assemble_prompt": True,
    "writer_does_not_disclose_externally": True,
    "live_memory_write_enabled": False,
    "live_memory_deletion_enabled": False,
    "live_index_mutation_enabled": False,
    "prompt_materialization_enabled": False,
    "external_disclosure_enabled": False,
    "remote_service_enabled": False,
    "dry_run_by_default": True,
    "explicit_output_path_required": True,
}
_RAW_KEYS = frozenset({"raw_payload", "raw_private_payload", "raw_transcript", "transcript", "provider_prompt", "secret", "api_key", "password", "token", "private_payload"})
_MEDIA_KEYS = frozenset({"image", "images", "audio", "video", "screenshot", "thumbnail", "media_payload", "encoded_media", "base64", "bytes", "raw_media"})
_MEDIA_RE = re.compile(r"(?:data:(?:image|audio|video)/|base64|[A-Za-z0-9+/]{120,}={0,2})")
_AUTHORITY_RE = re.compile(r"\b(authority|authorize|grant permission|policy now|consent granted|infer consent|infer authority|infer truth|convert.*policy|approved to act|override blocker|bypass)\b", re.I)
_PROMPT_RE = re.compile(r"\b(assemble prompt|prompt materialization|provider prompt|system prompt|retrieve live context)\b", re.I)
_ACTION_RE = re.compile(r"\b(execute action|action ingress|call_append_memory|call_purge_memory|mutate_vector_index|write_live_memory|delete_memory|purge_memory|apply_forgetting_curve|curate_memory|summarize_memory)\b", re.I)
_EXTERNAL_RE = re.compile(r"\b(external disclosure|send externally|remote service|network egress|provider invocation|upload)\b", re.I)
_LIVE_MEMORY_RE = re.compile(r"(^|/|\\)(memory|memories|vector_index|distilled_memory|live_memory)(/|\\|$)", re.I)
_SPECIAL_PREFIXES = ("/dev", "/proc", "/sys", "/run", "/etc", "/var", "/root", "/home")


def _json_data(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json_data(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    try:
        return _json_data(value)
    except TypeError:
        return str(value)


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(str(v) for v in value)
    return (str(value),)


@dataclass(frozen=True)
class GovernedMemoryWriterPolicy:
    schema_version: str = "governed-memory-writer-adapter.v1"
    default_mode: str = "dry_run_preview"
    allow_explicit_artifact_write: bool = True
    allow_live_memory_paths: bool = False
    allow_mixed_scope_diagnostic_packet: bool = False
    allow_warning_artifacts: bool = True
    allow_operator_review_archives: bool = True
    allow_noop_artifacts: bool = True
    require_matching_source_digest: bool = True
    require_receipt_gate_admissible: bool = True
    require_tomb_verifier_for_tomb_archives: bool = True
    require_explicit_output_path_for_write: bool = True
    require_safe_output_root: bool = True
    block_path_escape: bool = True
    block_live_index_mutation: bool = True
    block_hard_override_attempts: bool = True
    require_scope_alignment: bool = True


@dataclass(frozen=True)
class GovernedMemoryWriterCandidate:
    candidate_id: str
    candidate_type: str
    record_id: str
    source_digest: str
    claimed_distillation_decision: str
    claimed_receipt_gate_decision: str
    writer_mode: str = "dry_run_preview"
    output_path: str | None = None
    artifact_timestamp: str = "1970-01-01T00:00:00Z"
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

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], policy: GovernedMemoryWriterPolicy) -> "GovernedMemoryWriterCandidate":
        candidate_type = str(payload.get("candidate_type") or "")
        writer_mode = str(payload.get("writer_mode") or payload.get("mode") or policy.default_mode)
        metadata = payload.get("metadata") or payload.get("artifact_metadata") or {}
        if not isinstance(metadata, Mapping):
            metadata = {}
        return cls(
            candidate_id=str(payload["candidate_id"]),
            candidate_type=candidate_type,
            record_id=str(payload["record_id"]),
            source_digest=str(payload["source_digest"]),
            claimed_distillation_decision=str(payload["claimed_distillation_decision"]),
            claimed_receipt_gate_decision=str(payload["claimed_receipt_gate_decision"]),
            writer_mode=writer_mode,
            output_path=str(payload["output_path"]) if payload.get("output_path") is not None else None,
            artifact_timestamp=str(payload.get("artifact_timestamp") or payload.get("timestamp") or "1970-01-01T00:00:00Z"),
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
            live_memory_deletion_requested=bool(payload.get("live_memory_deletion_requested") or payload.get("delete_memory_now")),
            live_index_mutation_requested=bool(payload.get("live_index_mutation_requested") or payload.get("mutate_vector_index")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GovernedMemoryWriterInput:
    distillation_packet: Mapping[str, Any]
    receipt_gate_packet: Mapping[str, Any]
    writer_candidates: tuple[GovernedMemoryWriterCandidate, ...]
    tomb_verifier_packet: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class GovernedMemoryWriterFinding:
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    candidate_id: str | None = None
    record_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GovernedMemoryWriterPreview:
    candidate_id: str
    record_id: str
    candidate_type: str
    writer_mode: str
    preview_digest: str
    artifact_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GovernedMemoryWriterArtifactReceipt:
    artifact_path: str
    artifact_digest: str
    input_digest: str
    writer_mode: str
    candidate_id: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GovernedMemoryWriterRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    writer_mode: str
    writer_decision: WriterDecision
    distillation_decision: str
    receipt_gate_decision: str
    tomb_verifier_outcome: str | None
    artifact_path: str | None
    safe_next_actions: tuple[str, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    writer_is_not_truth: bool = True
    writer_is_not_policy: bool = True
    writer_is_not_authority: bool = True
    writer_is_not_consent: bool = True
    writer_does_not_execute_action: bool = True
    writer_does_not_assemble_prompt: bool = True
    writer_does_not_disclose_externally: bool = True
    live_memory_write_enabled: bool = False
    live_memory_deletion_enabled: bool = False
    live_index_mutation_enabled: bool = False
    prompt_materialization_enabled: bool = False
    external_disclosure_enabled: bool = False
    remote_service_enabled: bool = False
    dry_run_by_default: bool = True
    explicit_output_path_required: bool = True
    digest: str = ""

    def with_digest(self) -> "GovernedMemoryWriterRecord":
        return replace(self, digest=_digest(asdict(replace(self, digest=""))))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GovernedMemoryWriterPacket:
    schema_version: str
    records: tuple[GovernedMemoryWriterRecord, ...]
    previews: tuple[GovernedMemoryWriterPreview, ...]
    artifact_receipts: tuple[GovernedMemoryWriterArtifactReceipt, ...] = ()
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    writer_is_not_truth: bool = True
    writer_is_not_policy: bool = True
    writer_is_not_authority: bool = True
    writer_is_not_consent: bool = True
    writer_does_not_execute_action: bool = True
    writer_does_not_assemble_prompt: bool = True
    writer_does_not_disclose_externally: bool = True
    live_memory_write_enabled: bool = False
    live_memory_deletion_enabled: bool = False
    live_index_mutation_enabled: bool = False
    prompt_materialization_enabled: bool = False
    external_disclosure_enabled: bool = False
    remote_service_enabled: bool = False
    dry_run_by_default: bool = True
    explicit_output_path_required: bool = True
    digest: str = ""

    def with_digest(self) -> "GovernedMemoryWriterPacket":
        return replace(self, digest=_digest(asdict(replace(self, digest=""))))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GovernedMemoryWriterReport:
    status: GovernedMemoryWriterStatus
    findings: tuple[GovernedMemoryWriterFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [f.to_dict() for f in self.findings], "summary_counts": dict(self.summary_counts), "digest": self.digest}


@dataclass(frozen=True)
class GovernedMemoryWriterResult:
    status: GovernedMemoryWriterStatus
    packet: GovernedMemoryWriterPacket | None
    report: GovernedMemoryWriterReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> GovernedMemoryWriterPolicy:
    return GovernedMemoryWriterPolicy()


def validate_policy(policy: GovernedMemoryWriterPolicy) -> dict[str, Any]:
    findings: list[str] = []
    if not policy.schema_version:
        findings.append("missing_schema_version")
    if policy.default_mode not in WRITER_MODES:
        findings.append("invalid_default_mode")
    if policy.allow_mixed_scope_diagnostic_packet and not policy.require_scope_alignment:
        findings.append("mixed_scope_diagnostic_without_scope_checks")
    return {"ok": not findings, "findings": findings, "digest": _digest(asdict(policy))}


def _blocked(status: GovernedMemoryWriterStatus, findings: list[GovernedMemoryWriterFinding]) -> GovernedMemoryWriterResult:
    report = GovernedMemoryWriterReport(status, tuple(findings), {"candidate_count": 0, "blocked_count": 1}, "")
    report = replace(report, digest=_digest(report.to_dict()))
    return GovernedMemoryWriterResult(status, None, report, _digest(report.to_dict()))


def _dist_packet(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    packet = payload.get("distillation_packet") or payload.get("packet")
    return packet if isinstance(packet, Mapping) else None


def _gate_packet(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    packet = payload.get("receipt_gate_packet") or payload.get("gate_packet")
    return packet if isinstance(packet, Mapping) else None


def _tomb_packet(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    packet = payload.get("tomb_verifier_packet") or payload.get("tomb_packet")
    return packet if isinstance(packet, Mapping) else None


def _candidate_payloads(payload: Mapping[str, Any]) -> Any:
    if "writer_candidates" in payload:
        return payload.get("writer_candidates")
    if "writer_candidate" in payload:
        return [payload.get("writer_candidate")]
    if "candidate" in payload:
        return [payload.get("candidate")]
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


def _tomb_index(packet: Mapping[str, Any]) -> dict[str, Mapping[str, Any]] | None:
    records = packet.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)) or not records:
        return None
    out: dict[str, Mapping[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, Mapping):
            return None
        rid = str(raw.get("record_id") or "")
        if not rid or not raw.get("verification_outcome"):
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
    text = _text(value)
    return "contains_encoded_media" in text.lower() or "raw_media_payload_declared" in text.lower() or bool(_MEDIA_RE.search(text))


def _path_status(path: str | None, output_root: str | None, mode: str, policy: GovernedMemoryWriterPolicy) -> GovernedMemoryWriterStatus | None:
    if mode == "explicit_artifact_write" and policy.require_explicit_output_path_for_write and not path:
        return "governed_memory_writer_blocked_missing_output_path"
    if not path:
        return None
    normalized = path.replace("\\", "/")
    if not policy.allow_live_memory_paths and _LIVE_MEMORY_RE.search(normalized):
        return "governed_memory_writer_blocked_live_memory_path"
    p = Path(path)
    if p.is_absolute() and normalized.startswith(_SPECIAL_PREFIXES):
        return "governed_memory_writer_blocked_unsafe_output_path"
    parts = p.parts
    if policy.block_path_escape and (".." in parts or normalized.startswith("~") or normalized in {".", ""}):
        return "governed_memory_writer_blocked_unsafe_output_path"
    if policy.require_safe_output_root:
        if not output_root:
            return "governed_memory_writer_blocked_unsafe_output_path"
        root = Path(output_root).resolve()
        target = (root / p).resolve() if not p.is_absolute() else p.resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return "governed_memory_writer_blocked_unsafe_output_path"
    return None


def _status_for_blocker(code: str) -> GovernedMemoryWriterStatus:
    return {
        "digest_mismatch": "governed_memory_writer_blocked_digest_mismatch",
        "decision_mismatch": "governed_memory_writer_blocked_decision_mismatch",
        "receipt_gate_not_admissible": "governed_memory_writer_blocked_receipt_gate_not_admissible",
        "tomb_verifier_not_ready": "governed_memory_writer_blocked_tomb_verifier_not_ready",
        "live_memory_path": "governed_memory_writer_blocked_live_memory_path",
        "missing_output_path": "governed_memory_writer_blocked_missing_output_path",
        "unsafe_output_path": "governed_memory_writer_blocked_unsafe_output_path",
        "raw_payload_leak": "governed_memory_writer_blocked_raw_payload_leak",
        "authority_smuggling": "governed_memory_writer_blocked_authority_smuggling",
        "prompt_materialization": "governed_memory_writer_blocked_prompt_materialization",
        "action_execution": "governed_memory_writer_blocked_action_execution",
        "external_disclosure": "governed_memory_writer_blocked_external_disclosure",
        "scope_mismatch": "governed_memory_writer_blocked_scope_mismatch",
    }.get(code, "governed_memory_writer_blocked_invalid_writer_candidate")  # type: ignore[return-value]


def _gate_allowed(candidate_type: str, gate_decision: str, policy: GovernedMemoryWriterPolicy) -> bool:
    if not policy.require_receipt_gate_admissible:
        return True
    if candidate_type == "no_op_artifact_candidate":
        return gate_decision == "receipt_candidate_noop" and policy.allow_noop_artifacts
    if candidate_type in {"operator_review_archive_candidate", "tomb_deferred_archive_candidate"}:
        return gate_decision == "receipt_candidate_deferred_for_operator_review" and policy.allow_operator_review_archives
    if candidate_type == "mixed_writer_artifact_candidate":
        return gate_decision in {"receipt_candidate_admissible", "receipt_candidate_admissible_with_warnings"}
    return gate_decision in {"receipt_candidate_admissible", "receipt_candidate_admissible_with_warnings"}


def _tomb_allowed(candidate_type: str, outcome: str | None) -> bool:
    if candidate_type not in TOMB_CANDIDATE_TYPES:
        return True
    if candidate_type == "tomb_deferred_archive_candidate":
        return outcome == "tomb_receipt_deferred_for_operator_review"
    return outcome in {"tomb_receipt_verified", "tomb_receipt_verified_with_warnings"}


def _decision_for(candidate: GovernedMemoryWriterCandidate, gate_decision: str, tomb_outcome: str | None, warnings: bool) -> WriterDecision:
    if candidate.candidate_type == "no_op_artifact_candidate" or gate_decision == "receipt_candidate_noop" or tomb_outcome == "tomb_receipt_noop":
        return "writer_noop"
    if gate_decision == "receipt_candidate_rejected" or tomb_outcome == "tomb_receipt_rejected":
        return "writer_rejected"
    if gate_decision == "receipt_candidate_deferred_for_operator_review" or tomb_outcome == "tomb_receipt_deferred_for_operator_review" or candidate.candidate_type == "operator_review_archive_candidate":
        return "writer_deferred_for_operator_review"
    if candidate.writer_mode == "dry_run_preview":
        return "writer_preview_ready"
    return "writer_artifact_ready_with_warnings" if warnings else "writer_artifact_ready"


def _safe_actions_for(decision: WriterDecision, candidate_type: str, mode: str) -> tuple[str, ...]:
    actions = ["inspect_writer_packet", "defer_to_memory_runtime_boundary", "defer_to_self_improvement_ingress"]
    if decision == "writer_preview_ready":
        actions.append("write_explicit_artifact_later")
    elif decision == "writer_deferred_for_operator_review":
        actions.append("operator_review_required")
    elif decision == "writer_noop":
        actions.append("no_action_allowed")
    if mode == "dry_run_preview":
        actions.append("run_dry_preview")
    if candidate_type in {"ai_capsule_artifact_candidate", "human_summary_artifact_candidate", "dual_capsule_artifact_candidate"}:
        actions.append("archive_capsule_receipt_later")
    if candidate_type == "protect_receipt_artifact_candidate":
        actions.append("archive_protect_receipt_later")
    if candidate_type == "merge_receipt_artifact_candidate":
        actions.append("archive_merge_receipt_later")
    if candidate_type in TOMB_CANDIDATE_TYPES:
        actions.append("archive_tomb_receipt_later")
    return tuple(dict.fromkeys(actions))


def _candidate_blocker(
    candidate: GovernedMemoryWriterCandidate,
    record: Mapping[str, Any],
    gate: Mapping[str, Any],
    tomb: Mapping[str, Any] | None,
    payload: Mapping[str, Any],
    policy: GovernedMemoryWriterPolicy,
) -> str | None:
    candidate_blob = candidate.to_dict()
    all_blob = {"candidate": candidate_blob, "metadata": candidate.metadata}
    if _contains_forbidden_payload(all_blob, _RAW_KEYS) or _contains_media(all_blob):
        return "raw_payload_leak"
    text = _text(all_blob)
    if candidate.prompt_materialization_requested or _PROMPT_RE.search(text):
        return "prompt_materialization"
    if candidate.action_execution_requested or candidate.live_memory_write_requested or candidate.live_memory_deletion_requested or candidate.live_index_mutation_requested or _ACTION_RE.search(text):
        return "action_execution"
    if candidate.external_disclosure_requested or _EXTERNAL_RE.search(text):
        return "external_disclosure"
    if candidate.authority_grant_claimed or candidate.policy_creation_claimed or candidate.consent_inference_claimed or candidate.truth_inference_claimed or candidate.hard_override_requested or _AUTHORITY_RE.search(text):
        return "authority_smuggling"
    if policy.require_matching_source_digest:
        digests = [str(record.get("source_digest") or ""), str(gate.get("source_digest") or record.get("source_digest") or "")]
        if tomb is not None:
            digests.append(str(tomb.get("source_digest") or record.get("source_digest") or ""))
        if any(d and d != candidate.source_digest for d in digests):
            return "digest_mismatch"
    dist_decision = str(record.get("distillation_decision") or "")
    gate_decision = str(gate.get("gate_decision") or "")
    if dist_decision != candidate.claimed_distillation_decision or gate_decision != candidate.claimed_receipt_gate_decision:
        return "decision_mismatch"
    if not _gate_allowed(candidate.candidate_type, gate_decision, policy):
        return "receipt_gate_not_admissible"
    tomb_outcome = str(tomb.get("verification_outcome") or "") if tomb else None
    if not _tomb_allowed(candidate.candidate_type, tomb_outcome):
        return "tomb_verifier_not_ready"
    record_scope = _as_tuple(record.get("source_scope_keys"))
    gate_scope = _as_tuple(gate.get("source_scope_keys"))
    tomb_scope = _as_tuple(tomb.get("source_scope_keys")) if tomb else ()
    if policy.require_scope_alignment:
        if (candidate.source_scope_keys and record_scope and candidate.source_scope_keys != record_scope) or (gate_scope and record_scope and gate_scope != record_scope) or (tomb_scope and record_scope and tomb_scope != record_scope):
            return "scope_mismatch"
    path_status = _path_status(candidate.output_path or str(payload.get("artifact_path") or ""), str(payload.get("output_root") or ""), candidate.writer_mode, policy)
    if path_status is not None:
        return "missing_output_path" if path_status.endswith("missing_output_path") else "live_memory_path" if path_status.endswith("live_memory_path") else "unsafe_output_path"
    return None


def _artifact_payload(candidate: GovernedMemoryWriterCandidate, record: GovernedMemoryWriterRecord, input_digest: str) -> dict[str, Any]:
    return {
        "schema_version": "governed-memory-writer-artifact.v1",
        "candidate_id": candidate.candidate_id,
        "record_id": candidate.record_id,
        "candidate_type": candidate.candidate_type,
        "writer_mode": candidate.writer_mode,
        "writer_decision": record.writer_decision,
        "input_digest": input_digest,
        "artifact_timestamp": candidate.artifact_timestamp,
        "metadata": dict(sorted(candidate.metadata.items())),
        "forbidden_next_steps": list(FORBIDDEN_NEXT_STEPS),
        **_INVARIANTS,
    }


def evaluate_governed_memory_writer_adapter(payload: Mapping[str, Any], policy: GovernedMemoryWriterPolicy | None = None) -> GovernedMemoryWriterResult:
    if policy is None and isinstance(payload.get("policy"), Mapping):
        allowed = set(GovernedMemoryWriterPolicy.__dataclass_fields__)
        policy = GovernedMemoryWriterPolicy(**{str(k): v for k, v in dict(payload.get("policy", {})).items() if str(k) in allowed})
    policy = policy or build_default_policy()
    try:
        dist = _dist_packet(payload)
        if dist is None:
            return _blocked("governed_memory_writer_blocked_missing_distillation_packet", [GovernedMemoryWriterFinding("error", "missing_distillation_packet", "distillation packet is required")])
        records = _record_index(dist)
        if records is None:
            return _blocked("governed_memory_writer_blocked_invalid_distillation_packet", [GovernedMemoryWriterFinding("error", "invalid_distillation_packet", "distillation packet records are invalid")])
        gate_packet = _gate_packet(payload)
        if gate_packet is None:
            return _blocked("governed_memory_writer_blocked_missing_receipt_gate_packet", [GovernedMemoryWriterFinding("error", "missing_receipt_gate_packet", "receipt gate packet is required")])
        gates = _gate_index(gate_packet)
        if gates is None:
            return _blocked("governed_memory_writer_blocked_invalid_receipt_gate_packet", [GovernedMemoryWriterFinding("error", "invalid_receipt_gate_packet", "receipt gate packet decisions are invalid")])
        raw_candidates = _candidate_payloads(payload)
        if raw_candidates is None:
            return _blocked("governed_memory_writer_blocked_missing_writer_candidate", [GovernedMemoryWriterFinding("error", "missing_writer_candidate", "writer candidate is required")])
        if not isinstance(raw_candidates, Sequence) or isinstance(raw_candidates, (str, bytes, bytearray)) or not raw_candidates:
            return _blocked("governed_memory_writer_blocked_invalid_writer_candidate", [GovernedMemoryWriterFinding("error", "invalid_writer_candidate", "writer candidates must be a non-empty list")])
        candidates: list[GovernedMemoryWriterCandidate] = []
        needs_tomb = False
        for raw in raw_candidates:
            if not isinstance(raw, Mapping):
                return _blocked("governed_memory_writer_blocked_invalid_writer_candidate", [GovernedMemoryWriterFinding("error", "invalid_writer_candidate", "writer candidate must be a mapping")])
            try:
                candidate = GovernedMemoryWriterCandidate.from_mapping(raw, policy)
            except (KeyError, TypeError, ValueError) as exc:
                return _blocked("governed_memory_writer_blocked_invalid_writer_candidate", [GovernedMemoryWriterFinding("error", "invalid_writer_candidate", str(exc))])
            if candidate.candidate_type not in WRITER_CANDIDATE_TYPES or candidate.writer_mode not in WRITER_MODES:
                return _blocked("governed_memory_writer_blocked_invalid_writer_candidate", [GovernedMemoryWriterFinding("error", "invalid_writer_candidate", "unknown candidate type or writer mode", candidate.candidate_id, candidate.record_id)])
            needs_tomb = needs_tomb or candidate.candidate_type in DELETION_ADJACENT_TYPES
            candidates.append(candidate)
        tomb_records: dict[str, Mapping[str, Any]] = {}
        tomb_packet = _tomb_packet(payload)
        if needs_tomb and policy.require_tomb_verifier_for_tomb_archives:
            if tomb_packet is None:
                return _blocked("governed_memory_writer_blocked_missing_tomb_verifier_packet", [GovernedMemoryWriterFinding("error", "missing_tomb_verifier_packet", "tomb verifier packet is required for tomb archive candidates")])
            parsed_tomb = _tomb_index(tomb_packet)
            if parsed_tomb is None:
                return _blocked("governed_memory_writer_blocked_invalid_tomb_verifier_packet", [GovernedMemoryWriterFinding("error", "invalid_tomb_verifier_packet", "tomb verifier packet records are invalid")])
            tomb_records = parsed_tomb
        findings: list[GovernedMemoryWriterFinding] = []
        packet_scope_sets = {_as_tuple(record.get("source_scope_keys")) for record in records.values() if _as_tuple(record.get("source_scope_keys"))}
        mixed_scope_warning = False
        if len(packet_scope_sets) > 1:
            if policy.allow_mixed_scope_diagnostic_packet:
                findings.append(GovernedMemoryWriterFinding("warning", "mixed_scope_diagnostic_packet", "packet contains multiple source scopes"))
                mixed_scope_warning = True
            elif policy.require_scope_alignment:
                findings.append(GovernedMemoryWriterFinding("error", "scope_mismatch", "packet contains multiple source scopes"))
                return _blocked("governed_memory_writer_blocked_scope_mismatch", findings)
        out_records: list[GovernedMemoryWriterRecord] = []
        previews: list[GovernedMemoryWriterPreview] = []
        input_digest = _digest({k: v for k, v in payload.items() if k not in {"output", "summary"}})
        for candidate in candidates:
            record = records.get(candidate.record_id)
            gate = gates.get(candidate.record_id)
            tomb = tomb_records.get(candidate.record_id) if tomb_records else None
            if record is None or gate is None:
                return _blocked("governed_memory_writer_blocked_invalid_writer_candidate", [GovernedMemoryWriterFinding("error", "invalid_writer_candidate", "candidate references unknown prior evidence", candidate.candidate_id, candidate.record_id)])
            blocker = _candidate_blocker(candidate, record, gate, tomb, payload, policy)
            if blocker:
                findings.append(GovernedMemoryWriterFinding("error", blocker, f"writer candidate blocked: {blocker}", candidate.candidate_id, candidate.record_id))
                return _blocked(_status_for_blocker(blocker), findings)
            warnings = mixed_scope_warning or str(gate.get("gate_decision") or "") == "receipt_candidate_admissible_with_warnings" or (tomb is not None and str(tomb.get("verification_outcome") or "").endswith("with_warnings")) or bool(candidate.metadata.get("diagnostic_warning") or candidate.metadata.get("warning_only"))
            if warnings:
                findings.append(GovernedMemoryWriterFinding("warning", "writer_artifact_warning", "writer output is warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
            gate_decision = str(gate.get("gate_decision") or "")
            tomb_outcome = str(tomb.get("verification_outcome") or "") if tomb is not None else None
            decision = _decision_for(candidate, gate_decision, tomb_outcome, warnings)
            out_record = GovernedMemoryWriterRecord(
                candidate_id=candidate.candidate_id,
                record_id=candidate.record_id,
                candidate_type=candidate.candidate_type,
                writer_mode=candidate.writer_mode,
                writer_decision=decision,
                distillation_decision=str(record.get("distillation_decision") or ""),
                receipt_gate_decision=gate_decision,
                tomb_verifier_outcome=tomb_outcome,
                artifact_path=candidate.output_path,
                safe_next_actions=_safe_actions_for(decision, candidate.candidate_type, candidate.writer_mode),
            ).with_digest()
            out_records.append(out_record)
            previews.append(GovernedMemoryWriterPreview(candidate.candidate_id, candidate.record_id, candidate.candidate_type, candidate.writer_mode, _digest(_artifact_payload(candidate, out_record, input_digest)), candidate.output_path))
        counts: dict[str, int] = {"candidate_count": len(out_records), "warning_count": sum(1 for f in findings if f.severity == "warning")}
        for rec in out_records:
            counts[rec.writer_decision] = counts.get(rec.writer_decision, 0) + 1
            counts[rec.candidate_type] = counts.get(rec.candidate_type, 0) + 1
        if all(rec.writer_mode == "dry_run_preview" for rec in out_records):
            status: GovernedMemoryWriterStatus = "governed_memory_writer_dry_run_ready"
        elif counts["warning_count"]:
            status = "governed_memory_writer_ready_with_warnings"
        else:
            status = "governed_memory_writer_ready"
        packet = GovernedMemoryWriterPacket(policy.schema_version, tuple(out_records), tuple(previews)).with_digest()
        report = GovernedMemoryWriterReport(status, tuple(findings), dict(sorted(counts.items())), "")
        report = replace(report, digest=_digest(report.to_dict()))
        return GovernedMemoryWriterResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("governed_memory_writer_failed", [GovernedMemoryWriterFinding("error", "failed", str(exc))])


def _resolve_artifact_target(output_root: str, artifact_path: str, policy: GovernedMemoryWriterPolicy) -> Path:
    status = _path_status(artifact_path, output_root, "explicit_artifact_write", policy)
    if status is not None:
        raise ValueError(status)
    root = Path(output_root).resolve()
    target = Path(artifact_path)
    return (root / target).resolve() if not target.is_absolute() else target.resolve()


def write_artifact(payload: Mapping[str, Any], output_root: str, artifact_path: str, policy: GovernedMemoryWriterPolicy | None = None, *, dry_run: bool = False) -> GovernedMemoryWriterResult:
    effective_policy = policy
    merged = dict(payload)
    raw_candidates = _candidate_payloads(merged)
    if isinstance(raw_candidates, Sequence) and not isinstance(raw_candidates, (str, bytes, bytearray)) and raw_candidates:
        first = dict(raw_candidates[0]) if isinstance(raw_candidates[0], Mapping) else {}
        first["writer_mode"] = "dry_run_preview" if dry_run else "explicit_artifact_write"
        first["output_path"] = artifact_path
        merged["writer_candidates"] = [first, *list(raw_candidates[1:])]
    merged["output_root"] = output_root
    result = evaluate_governed_memory_writer_adapter(merged, effective_policy)
    if result.packet is None or result.status.startswith("governed_memory_writer_blocked") or result.status.endswith(("invalid", "failed")) or dry_run:
        return result
    candidate = GovernedMemoryWriterCandidate.from_mapping(dict(merged["writer_candidates"][0]), policy or build_default_policy())
    target = _resolve_artifact_target(output_root, artifact_path, policy or build_default_policy())
    target.parent.mkdir(parents=True, exist_ok=True)
    record = result.packet.records[0]
    artifact = _artifact_payload(candidate, record, result.digest)
    artifact_text = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    target.write_text(artifact_text, encoding="utf-8")
    receipt = GovernedMemoryWriterArtifactReceipt(str(target), _digest(artifact), result.digest, candidate.writer_mode, candidate.candidate_id, candidate.artifact_timestamp)
    packet = replace(result.packet, artifact_receipts=(receipt,)).with_digest()
    report = replace(result.report, digest=_digest(result.report.to_dict()))
    return GovernedMemoryWriterResult(result.status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))


def evaluate_packet(payload: Mapping[str, Any], policy: GovernedMemoryWriterPolicy | None = None) -> GovernedMemoryWriterResult:
    return evaluate_governed_memory_writer_adapter(payload, policy)


__all__ = [
    "FORBIDDEN_NEXT_STEPS",
    "SAFE_NEXT_ACTIONS",
    "WRITER_CANDIDATE_TYPES",
    "WRITER_MODES",
    "GovernedMemoryWriterPolicy",
    "GovernedMemoryWriterInput",
    "GovernedMemoryWriterCandidate",
    "GovernedMemoryWriterFinding",
    "GovernedMemoryWriterPreview",
    "GovernedMemoryWriterArtifactReceipt",
    "GovernedMemoryWriterRecord",
    "GovernedMemoryWriterPacket",
    "GovernedMemoryWriterReport",
    "GovernedMemoryWriterResult",
    "build_default_policy",
    "validate_policy",
    "evaluate_governed_memory_writer_adapter",
    "evaluate_packet",
    "write_artifact",
]
