"""Deterministic metadata-only selective memory distillation contract.

This module evaluates caller-supplied JSON metadata records only. It never reads
live memory, writes memory, deletes memory, assembles prompts, invokes remote
services, executes actions, or grants authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal, Mapping, Sequence

DistillationStatus = Literal[
    "selective_memory_distillation_ready",
    "selective_memory_distillation_ready_with_warnings",
    "selective_memory_distillation_blocked_missing_records",
    "selective_memory_distillation_blocked_invalid_record",
    "selective_memory_distillation_blocked_raw_media_payload",
    "selective_memory_distillation_blocked_unbounded_affective_context",
    "selective_memory_distillation_blocked_missing_provenance",
    "selective_memory_distillation_blocked_authority_smuggling",
    "selective_memory_distillation_blocked_prompt_materialization",
    "selective_memory_distillation_blocked_runtime_memory_mutation",
    "selective_memory_distillation_blocked_external_authority",
    "selective_memory_distillation_blocked_scope_mismatch",
    "selective_memory_distillation_blocked_tomb_without_receipt_intent",
    "selective_memory_distillation_invalid",
    "selective_memory_distillation_failed",
]

SOURCE_RECORD_KINDS = frozenset({
    "raw_memory_fragment",
    "observation_summary",
    "curiosity_reflection",
    "action_reflection",
    "context_hygiene_candidate",
    "affective_overlay",
    "embodiment_proposal",
    "embodiment_governance_bridge",
    "embodiment_action_ingress_validation",
    "codex_task_report",
    "proof_bundle_summary",
    "audit_summary",
    "operator_note",
    "unknown_record_kind",
})
DISTILLATION_DECISIONS = frozenset({
    "retain_raw_temporarily",
    "distill_to_ai_capsule",
    "distill_to_human_summary",
    "distill_to_dual_capsule",
    "merge_into_existing_capsule",
    "protect_from_forgetting",
    "defer_for_operator_review",
    "tomb_after_distillation",
    "tomb_without_retention",
    "reject_record",
    "no_distillation_needed",
})
AI_CAPSULE_TYPES = frozenset({
    "ai_symbolic_state",
    "ai_boundary_state",
    "ai_affective_state",
    "ai_embodiment_state",
    "ai_authority_state",
    "ai_proof_state",
    "ai_memory_digest",
    "ai_task_handoff_state",
    "ai_operator_load_state",
    "ai_future_work_state",
    "ai_tomb_marker",
    "ai_mixed_capsule",
})
SAFE_NEXT_ACTIONS = frozenset({
    "no_action_allowed",
    "inspect_distillation_packet",
    "operator_review_required",
    "write_distilled_capsule_later",
    "write_tomb_receipt_later",
    "protect_memory_later",
    "rerun_with_provenance",
    "rerun_with_bounded_affective_context",
    "rerun_with_scope_alignment",
    "defer_to_context_hygiene_selector",
    "defer_to_memory_manager_runtime",
    "defer_to_self_improvement_ingress",
})
FORBIDDEN_NEXT_STEPS = (
    "delete_memory_now",
    "purge_memory_now",
    "write_memory_now",
    "mutate_raw_fragment",
    "mutate_vector_index",
    "mutate_distilled_memory",
    "call_append_memory",
    "call_purge_memory",
    "call_apply_forgetting_curve",
    "call_curate_memory",
    "call_summarize_memory",
    "assemble_prompt_now",
    "retrieve_live_context",
    "call_llm_provider",
    "call_network_api",
    "call_github_api",
    "execute_action_ingress",
    "infer_truth_from_retention",
    "infer_consent_from_affect",
    "infer_authority_from_memory",
    "convert_capsule_to_policy",
    "convert_distillation_to_action",
    "bypass_context_hygiene",
    "bypass_memory_tomb",
    "bypass_operator_review",
    "enable_external_disclosure",
)

_RAW_MEDIA_KEYS = frozenset({"image", "images", "audio", "video", "screenshot", "thumbnail", "media_payload", "base64", "bytes", "raw_media"})
_RAW_PAYLOAD_MARKERS = ("raw_transcript", "provider_prompt", "secret", "api_key", "password", "token")
_MEDIA_RE = re.compile(r"(?:data:(?:image|audio|video)/|base64|[A-Za-z0-9+/]{120,}={0,2})")
_AUTHORITY_RE = re.compile(r"\b(authorize|grant permission|policy now|execute|admit work|consent granted|approved to act)\b", re.I)
_PROMPT_RE = re.compile(r"\b(assemble prompt|prompt materialization|provider prompt|system prompt)\b", re.I)
_RUNTIME_MEMORY_RE = re.compile(r"\b(append_memory|purge_memory|apply_forgetting_curve|curate_memory|summarize_memory|delete memory|write memory|mutate vector)\b", re.I)
_EXTERNAL_RE = re.compile(r"\b(call network|github api|provider api|remote service|external disclosure|send to api|webhook)\b", re.I)
_ACTION_RE = re.compile(r"\b(execute action ingress|perform action|host actuation|run actuator)\b", re.I)


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
class SelectiveMemoryDistillationPolicy:
    schema_version: str = "selective-memory-distillation-contract.v1"
    allow_empty_diagnostic_packet: bool = False
    allow_unknown_record_kind: bool = False
    missing_provenance_mode: Literal["block", "warn"] = "warn"
    raw_transcript_mode: Literal["block", "warn"] = "block"
    scope_mismatch_mode: Literal["block", "warn"] = "block"
    allow_mixed_scope_diagnostic_packet: bool = False
    require_bounded_affective_context: bool = True
    require_tomb_intent_for_tomb_decision: bool = True
    ai_capsule_symbol_limit: int = 16
    human_summary_max_chars: int = 480
    raw_retention_max_age_hint_days: int = 14
    protect_importance_threshold: float = 0.75
    distill_importance_threshold: float = 0.35
    tomb_importance_threshold: float = 0.2
    novelty_distill_threshold: float = 0.4


@dataclass(frozen=True)
class SelectiveMemoryAffectiveSummary:
    bounded: bool = True
    descriptors: tuple[str, ...] = ()
    authorizes_action: bool = False
    implies_consent: bool = False

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "SelectiveMemoryAffectiveSummary | None":
        if not payload:
            return None
        return cls(
            bounded=bool(payload.get("bounded", True)),
            descriptors=_as_tuple(payload.get("descriptors") or payload.get("affects")),
            authorizes_action=bool(payload.get("authorizes_action", False)),
            implies_consent=bool(payload.get("implies_consent", False)),
        )


@dataclass(frozen=True)
class SelectiveMemoryEmbodimentSummary:
    bounded: bool = True
    descriptors: tuple[str, ...] = ()
    admits_work: bool = False
    executes_action: bool = False

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "SelectiveMemoryEmbodimentSummary | None":
        if not payload:
            return None
        return cls(
            bounded=bool(payload.get("bounded", True)),
            descriptors=_as_tuple(payload.get("descriptors") or payload.get("references")),
            admits_work=bool(payload.get("admits_work", False)),
            executes_action=bool(payload.get("executes_action", False)),
        )


@dataclass(frozen=True)
class SelectiveMemoryAuthoritySummary:
    descriptors: tuple[str, ...] = ()
    converts_to_policy: bool = False
    grants_permission: bool = False
    external_authority_requested: bool = False

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "SelectiveMemoryAuthoritySummary | None":
        if not payload:
            return None
        return cls(
            descriptors=_as_tuple(payload.get("descriptors") or payload.get("proof_refs")),
            converts_to_policy=bool(payload.get("converts_to_policy", False)),
            grants_permission=bool(payload.get("grants_permission", False)),
            external_authority_requested=bool(payload.get("external_authority_requested", False)),
        )


@dataclass(frozen=True)
class SelectiveMemoryAICapsule:
    capsule_type: str
    symbols: tuple[str, ...]
    source_digests: tuple[str, ...]
    expires_at: str | None = None
    human_expandable: bool = True
    digest: str = ""

    def with_digest(self) -> "SelectiveMemoryAICapsule":
        payload = asdict(replace(self, digest=""))
        return replace(self, digest=_digest(payload))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectiveMemoryTombIntent:
    tomb_intent_id: str
    reason: str
    source_digests: tuple[str, ...]
    requires_later_receipt: bool = True
    deletion_performed: bool = False
    digest: str = ""

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None, source_digest: str) -> "SelectiveMemoryTombIntent | None":
        if not payload:
            return None
        return cls(
            tomb_intent_id=str(payload.get("tomb_intent_id") or payload.get("intent_id") or ""),
            reason=str(payload.get("reason") or "metadata-only tomb intent"),
            source_digests=tuple(sorted(set(_as_tuple(payload.get("source_digests")) or (source_digest,)))),
            requires_later_receipt=bool(payload.get("requires_later_receipt", True)),
            deletion_performed=bool(payload.get("deletion_performed", False)),
        ).with_digest()

    def with_digest(self) -> "SelectiveMemoryTombIntent":
        return replace(self, digest=_digest(asdict(replace(self, digest=""))))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectiveMemorySourceRecord:
    record_id: str
    source_record_kind: str
    source_digest: str
    source_summary: str
    source_record_id: str | None = None
    source_timestamp: str | None = None
    source_tags: tuple[str, ...] = ()
    source_scope_keys: tuple[str, ...] = ()
    source_provenance_refs: tuple[str, ...] = ()
    affective_summary: SelectiveMemoryAffectiveSummary | None = None
    embodiment_summary: SelectiveMemoryEmbodimentSummary | None = None
    authority_summary: SelectiveMemoryAuthoritySummary | None = None
    proof_summary: Mapping[str, Any] | None = None
    risk_flags: tuple[str, ...] = ()
    privacy_posture: str = "metadata_only"
    retention_pressure: str = "normal"
    salience_score: float = 0.0
    novelty_score: float | None = None
    importance_score: float | None = None
    access_count: int | None = None
    last_accessed: str | None = None
    distillation_decision: str = "no_distillation_needed"
    ai_capsule: SelectiveMemoryAICapsule | None = None
    human_summary: str | None = None
    tomb_intent: SelectiveMemoryTombIntent | None = None
    safe_next_action: str = "inspect_distillation_packet"

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "SelectiveMemorySourceRecord":
        if not isinstance(payload, Mapping):
            raise ValueError("record_not_mapping")
        record_id = str(payload.get("record_id") or "")
        kind = str(payload.get("source_record_kind") or "")
        source_summary = str(payload.get("source_summary") or "")
        source_digest = str(payload.get("source_digest") or "") or _digest({"record_id": record_id, "kind": kind, "summary": source_summary})
        capsule_payload = payload.get("ai_capsule")
        capsule = None
        if isinstance(capsule_payload, Mapping):
            capsule = SelectiveMemoryAICapsule(
                capsule_type=str(capsule_payload.get("capsule_type") or "ai_memory_digest"),
                symbols=_as_tuple(capsule_payload.get("symbols")),
                source_digests=_as_tuple(capsule_payload.get("source_digests")) or (source_digest,),
                expires_at=str(capsule_payload["expires_at"]) if capsule_payload.get("expires_at") is not None else None,
                human_expandable=bool(capsule_payload.get("human_expandable", True)),
            ).with_digest()
        tomb_intent = SelectiveMemoryTombIntent.from_mapping(payload.get("tomb_intent") if isinstance(payload.get("tomb_intent"), Mapping) else None, source_digest)
        return cls(
            record_id=record_id,
            source_record_id=str(payload["source_record_id"]) if payload.get("source_record_id") is not None else None,
            source_record_kind=kind,
            source_digest=source_digest,
            source_timestamp=str(payload["source_timestamp"]) if payload.get("source_timestamp") is not None else None,
            source_tags=_as_tuple(payload.get("source_tags")),
            source_summary=source_summary,
            source_scope_keys=_as_tuple(payload.get("source_scope_keys")),
            source_provenance_refs=_as_tuple(payload.get("source_provenance_refs")),
            affective_summary=SelectiveMemoryAffectiveSummary.from_mapping(payload.get("affective_summary") if isinstance(payload.get("affective_summary"), Mapping) else None),
            embodiment_summary=SelectiveMemoryEmbodimentSummary.from_mapping(payload.get("embodiment_summary") if isinstance(payload.get("embodiment_summary"), Mapping) else None),
            authority_summary=SelectiveMemoryAuthoritySummary.from_mapping(payload.get("authority_summary") if isinstance(payload.get("authority_summary"), Mapping) else None),
            proof_summary=payload.get("proof_summary") if isinstance(payload.get("proof_summary"), Mapping) else None,
            risk_flags=_as_tuple(payload.get("risk_flags")),
            privacy_posture=str(payload.get("privacy_posture") or "metadata_only"),
            retention_pressure=str(payload.get("retention_pressure") or "normal"),
            salience_score=float(payload.get("salience_score") or 0.0),
            novelty_score=float(payload["novelty_score"]) if payload.get("novelty_score") is not None else None,
            importance_score=float(payload["importance_score"]) if payload.get("importance_score") is not None else None,
            access_count=int(payload["access_count"]) if payload.get("access_count") is not None else None,
            last_accessed=str(payload["last_accessed"]) if payload.get("last_accessed") is not None else None,
            distillation_decision=str(payload.get("distillation_decision") or "no_distillation_needed"),
            ai_capsule=capsule,
            human_summary=str(payload["human_summary"]) if payload.get("human_summary") is not None else None,
            tomb_intent=tomb_intent,
            safe_next_action=str(payload.get("safe_next_action") or "inspect_distillation_packet"),
        )


@dataclass(frozen=True)
class SelectiveMemoryDistillationFinding:
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    record_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectiveMemoryDistillationRecord:
    record_id: str
    source_record_id: str | None
    source_record_kind: str
    source_digest: str
    source_timestamp: str | None
    source_tags: tuple[str, ...]
    source_summary: str
    source_scope_keys: tuple[str, ...]
    source_provenance_refs: tuple[str, ...]
    risk_flags: tuple[str, ...]
    privacy_posture: str
    retention_pressure: str
    salience_score: float
    novelty_score: float | None
    importance_score: float | None
    access_count: int | None
    last_accessed: str | None
    distillation_decision: str
    ai_capsule: SelectiveMemoryAICapsule | None
    human_summary: str | None
    tomb_intent: SelectiveMemoryTombIntent | None
    safe_next_action: str
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    retention_is_not_truth: bool = True
    distillation_is_not_memory_write: bool = True
    distillation_is_not_prompt_assembly: bool = True
    capsule_is_not_policy: bool = True
    capsule_is_not_authority: bool = True
    deletion_recommendation_is_not_deletion: bool = True
    external_disclosure_enabled: bool = False
    runtime_memory_mutation_enabled: bool = False
    prompt_materialization_enabled: bool = False
    remote_service_enabled: bool = False
    digest: str = ""

    def with_digest(self) -> "SelectiveMemoryDistillationRecord":
        return replace(self, digest=_digest(asdict(replace(self, digest=""))))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectiveMemoryDistillationPacket:
    schema_version: str
    records: tuple[SelectiveMemoryDistillationRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    retention_is_not_truth: bool = True
    distillation_is_not_memory_write: bool = True
    distillation_is_not_prompt_assembly: bool = True
    capsule_is_not_policy: bool = True
    capsule_is_not_authority: bool = True
    deletion_recommendation_is_not_deletion: bool = True
    external_disclosure_enabled: bool = False
    runtime_memory_mutation_enabled: bool = False
    prompt_materialization_enabled: bool = False
    remote_service_enabled: bool = False
    digest: str = ""

    def with_digest(self) -> "SelectiveMemoryDistillationPacket":
        return replace(self, digest=_digest(asdict(replace(self, digest=""))))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectiveMemoryDistillationReport:
    status: DistillationStatus
    findings: tuple[SelectiveMemoryDistillationFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [f.to_dict() for f in self.findings], "summary_counts": dict(self.summary_counts), "digest": self.digest}


@dataclass(frozen=True)
class SelectiveMemoryDistillationResult:
    status: DistillationStatus
    packet: SelectiveMemoryDistillationPacket | None
    report: SelectiveMemoryDistillationReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> SelectiveMemoryDistillationPolicy:
    return SelectiveMemoryDistillationPolicy()


def validate_policy(policy: SelectiveMemoryDistillationPolicy) -> dict[str, Any]:
    findings: list[str] = []
    if not policy.schema_version:
        findings.append("missing_schema_version")
    if policy.missing_provenance_mode not in {"block", "warn"}:
        findings.append("invalid_missing_provenance_mode")
    if policy.raw_transcript_mode not in {"block", "warn"}:
        findings.append("invalid_raw_transcript_mode")
    if policy.scope_mismatch_mode not in {"block", "warn"}:
        findings.append("invalid_scope_mismatch_mode")
    if policy.ai_capsule_symbol_limit <= 0:
        findings.append("invalid_ai_capsule_symbol_limit")
    if policy.human_summary_max_chars <= 0:
        findings.append("invalid_human_summary_max_chars")
    return {"ok": not findings, "findings": findings, "digest": _digest(asdict(policy))}


def _blocked(status: DistillationStatus, findings: list[SelectiveMemoryDistillationFinding]) -> SelectiveMemoryDistillationResult:
    report = SelectiveMemoryDistillationReport(status, tuple(findings), {"record_count": 0, "blocked_count": 1}, "")
    report = replace(report, digest=_digest(report.to_dict()))
    return SelectiveMemoryDistillationResult(status, None, report, _digest(report.to_dict()))


def _contains_raw_media(payload: Mapping[str, Any]) -> bool:
    lowered_keys = {str(k).lower() for k in payload.keys()}
    if lowered_keys & _RAW_MEDIA_KEYS:
        return True
    text = _text(payload)
    return bool(_MEDIA_RE.search(text))


def _contains_raw_transcript(payload: Mapping[str, Any]) -> bool:
    if "raw_transcript" in {str(k).lower() for k in payload.keys()}:
        return True
    return "raw transcript:" in _text(payload).lower()


def _unsafe_capsule(capsule: SelectiveMemoryAICapsule | None) -> bool:
    if capsule is None:
        return False
    text = _text(capsule.to_dict()).lower()
    return any(marker in text for marker in _RAW_PAYLOAD_MARKERS) or bool(_MEDIA_RE.search(text))


def _make_symbols(record: SelectiveMemorySourceRecord, policy: SelectiveMemoryDistillationPolicy) -> tuple[str, ...]:
    symbols = [
        f"need:selective_memory_distillation.{record.distillation_decision}",
        "boundary:no_runtime_memory_mutation,no_prompt_assembly,no_external_disclosure",
        "retention:not_truth,not_policy,not_authority",
        "next:inspect_distillation_packet",
    ]
    if record.source_scope_keys:
        symbols.append("scope:" + "+".join(sorted(record.source_scope_keys))[:96])
    if record.affective_summary and record.affective_summary.descriptors:
        symbols.append("affect:" + "+".join(sorted(record.affective_summary.descriptors))[:96])
    if record.embodiment_summary and record.embodiment_summary.descriptors:
        symbols.append("embodiment:" + "+".join(sorted(record.embodiment_summary.descriptors))[:96])
    if record.authority_summary and record.authority_summary.descriptors:
        symbols.append("authority:descriptive_only")
    if record.proof_summary:
        symbols.append("proof:metadata_only")
    symbols.append(f"source:{record.source_record_kind}")
    return tuple(symbols[: policy.ai_capsule_symbol_limit])


def _capsule_type_for(record: SelectiveMemorySourceRecord) -> str:
    if record.ai_capsule and record.ai_capsule.capsule_type in AI_CAPSULE_TYPES:
        return record.ai_capsule.capsule_type
    if record.source_record_kind == "affective_overlay":
        return "ai_affective_state"
    if record.source_record_kind.startswith("embodiment"):
        return "ai_embodiment_state"
    if record.source_record_kind in {"proof_bundle_summary", "audit_summary"}:
        return "ai_proof_state"
    if record.distillation_decision in {"tomb_after_distillation", "tomb_without_retention"}:
        return "ai_tomb_marker"
    if record.source_record_kind == "codex_task_report":
        return "ai_task_handoff_state"
    if record.distillation_decision == "distill_to_dual_capsule":
        return "ai_mixed_capsule"
    return "ai_memory_digest"


def _record_from_source(record: SelectiveMemorySourceRecord, policy: SelectiveMemoryDistillationPolicy) -> SelectiveMemoryDistillationRecord:
    capsule = record.ai_capsule
    if record.distillation_decision in {"distill_to_ai_capsule", "distill_to_dual_capsule"} and capsule is None:
        capsule = SelectiveMemoryAICapsule(
            capsule_type=_capsule_type_for(record),
            symbols=_make_symbols(record, policy),
            source_digests=(record.source_digest,),
        ).with_digest()
    human_summary = record.human_summary
    if record.distillation_decision in {"distill_to_human_summary", "distill_to_dual_capsule", "tomb_after_distillation"} and human_summary is None:
        human_summary = record.source_summary[: policy.human_summary_max_chars]
    out = SelectiveMemoryDistillationRecord(
        record_id=record.record_id,
        source_record_id=record.source_record_id,
        source_record_kind=record.source_record_kind,
        source_digest=record.source_digest,
        source_timestamp=record.source_timestamp,
        source_tags=record.source_tags,
        source_summary=record.source_summary[: policy.human_summary_max_chars],
        source_scope_keys=record.source_scope_keys,
        source_provenance_refs=record.source_provenance_refs,
        risk_flags=record.risk_flags,
        privacy_posture=record.privacy_posture,
        retention_pressure=record.retention_pressure,
        salience_score=record.salience_score,
        novelty_score=record.novelty_score,
        importance_score=record.importance_score,
        access_count=record.access_count,
        last_accessed=record.last_accessed,
        distillation_decision=record.distillation_decision,
        ai_capsule=capsule,
        human_summary=human_summary[: policy.human_summary_max_chars] if human_summary else None,
        tomb_intent=record.tomb_intent,
        safe_next_action=record.safe_next_action,
    )
    return out.with_digest()


def evaluate_selective_memory_distillation_contract(payload: Mapping[str, Any], policy: SelectiveMemoryDistillationPolicy | None = None) -> SelectiveMemoryDistillationResult:
    policy = policy or build_default_policy()
    findings: list[SelectiveMemoryDistillationFinding] = []
    records_payload = payload.get("records", payload.get("source_records", []))
    if not isinstance(records_payload, Sequence) or isinstance(records_payload, (str, bytes, bytearray)):
        findings.append(SelectiveMemoryDistillationFinding("error", "records_not_list", "records must be a list"))
        return _blocked("selective_memory_distillation_blocked_invalid_record", findings)
    if not records_payload and not policy.allow_empty_diagnostic_packet:
        findings.append(SelectiveMemoryDistillationFinding("error", "missing_records", "missing source records"))
        return _blocked("selective_memory_distillation_blocked_missing_records", findings)

    source_records: list[SelectiveMemorySourceRecord] = []
    for raw in records_payload:
        if not isinstance(raw, Mapping):
            findings.append(SelectiveMemoryDistillationFinding("error", "invalid_record", "record must be a mapping"))
            return _blocked("selective_memory_distillation_blocked_invalid_record", findings)
        try:
            record = SelectiveMemorySourceRecord.from_mapping(raw)
        except (TypeError, ValueError) as exc:
            findings.append(SelectiveMemoryDistillationFinding("error", "invalid_record", str(exc)))
            return _blocked("selective_memory_distillation_blocked_invalid_record", findings)
        rid = record.record_id or None
        if not record.record_id or not record.source_summary or not record.source_record_kind:
            findings.append(SelectiveMemoryDistillationFinding("error", "invalid_record", "record_id, source_record_kind, and source_summary are required", rid))
            return _blocked("selective_memory_distillation_blocked_invalid_record", findings)
        if record.source_record_kind not in SOURCE_RECORD_KINDS or (record.source_record_kind == "unknown_record_kind" and not policy.allow_unknown_record_kind):
            severity: Literal["error", "warning"] = "warning" if policy.allow_unknown_record_kind else "error"
            findings.append(SelectiveMemoryDistillationFinding(severity, "unknown_record_kind", "unknown source record kind", rid))
            if severity == "error":
                return _blocked("selective_memory_distillation_blocked_invalid_record", findings)
        if record.distillation_decision not in DISTILLATION_DECISIONS:
            findings.append(SelectiveMemoryDistillationFinding("error", "invalid_decision", "unknown distillation decision", rid))
            return _blocked("selective_memory_distillation_blocked_invalid_record", findings)
        if record.safe_next_action not in SAFE_NEXT_ACTIONS:
            findings.append(SelectiveMemoryDistillationFinding("error", "invalid_safe_next_action", "unknown safe next action", rid))
            return _blocked("selective_memory_distillation_blocked_invalid_record", findings)
        if _contains_raw_media(raw):
            findings.append(SelectiveMemoryDistillationFinding("error", "raw_media_payload", "raw media or encoded media payload is forbidden", rid))
            return _blocked("selective_memory_distillation_blocked_raw_media_payload", findings)
        if _contains_raw_transcript(raw):
            severity = "warning" if policy.raw_transcript_mode == "warn" else "error"
            findings.append(SelectiveMemoryDistillationFinding(severity, "raw_transcript_payload", "raw transcripts are not distillation metadata", rid))
            if severity == "error":
                return _blocked("selective_memory_distillation_blocked_raw_media_payload", findings)
        if not record.source_provenance_refs:
            severity = "warning" if policy.missing_provenance_mode == "warn" else "error"
            findings.append(SelectiveMemoryDistillationFinding(severity, "missing_provenance", "record lacks provenance references", rid))
            if severity == "error":
                return _blocked("selective_memory_distillation_blocked_missing_provenance", findings)
        if record.affective_summary:
            if policy.require_bounded_affective_context and not record.affective_summary.bounded:
                findings.append(SelectiveMemoryDistillationFinding("error", "unbounded_affective_context", "affective context must be bounded", rid))
                return _blocked("selective_memory_distillation_blocked_unbounded_affective_context", findings)
            if record.affective_summary.authorizes_action or record.affective_summary.implies_consent:
                findings.append(SelectiveMemoryDistillationFinding("error", "affective_authority_smuggling", "affect cannot authorize action or imply consent", rid))
                return _blocked("selective_memory_distillation_blocked_authority_smuggling", findings)
        if record.embodiment_summary and (record.embodiment_summary.admits_work or record.embodiment_summary.executes_action):
            findings.append(SelectiveMemoryDistillationFinding("error", "embodiment_action_smuggling", "embodiment context cannot admit work or execute action", rid))
            return _blocked("selective_memory_distillation_blocked_authority_smuggling", findings)
        if record.authority_summary and (record.authority_summary.converts_to_policy or record.authority_summary.grants_permission):
            findings.append(SelectiveMemoryDistillationFinding("error", "authority_smuggling", "authority/proof metadata cannot become policy or permission", rid))
            return _blocked("selective_memory_distillation_blocked_authority_smuggling", findings)
        text = _text(raw)
        if _PROMPT_RE.search(text):
            findings.append(SelectiveMemoryDistillationFinding("error", "prompt_materialization", "prompt materialization is forbidden", rid))
            return _blocked("selective_memory_distillation_blocked_prompt_materialization", findings)
        if _RUNTIME_MEMORY_RE.search(text):
            findings.append(SelectiveMemoryDistillationFinding("error", "runtime_memory_mutation", "runtime memory mutation requests are forbidden", rid))
            return _blocked("selective_memory_distillation_blocked_runtime_memory_mutation", findings)
        if _EXTERNAL_RE.search(text) or (record.authority_summary and record.authority_summary.external_authority_requested):
            findings.append(SelectiveMemoryDistillationFinding("error", "external_authority", "remote services and external disclosure are forbidden", rid))
            return _blocked("selective_memory_distillation_blocked_external_authority", findings)
        if _ACTION_RE.search(text):
            findings.append(SelectiveMemoryDistillationFinding("error", "action_execution", "action execution is forbidden", rid))
            return _blocked("selective_memory_distillation_blocked_external_authority", findings)
        if record.distillation_decision in {"tomb_after_distillation", "tomb_without_retention"}:
            if policy.require_tomb_intent_for_tomb_decision and record.tomb_intent is None:
                findings.append(SelectiveMemoryDistillationFinding("error", "tomb_without_receipt_intent", "tomb decisions require tomb intent metadata", rid))
                return _blocked("selective_memory_distillation_blocked_tomb_without_receipt_intent", findings)
            if record.tomb_intent and (not record.tomb_intent.requires_later_receipt or record.tomb_intent.deletion_performed):
                findings.append(SelectiveMemoryDistillationFinding("error", "tomb_intent_claims_deletion", "tomb intent is not deletion and requires a later receipt", rid))
                return _blocked("selective_memory_distillation_blocked_tomb_without_receipt_intent", findings)
        if _unsafe_capsule(record.ai_capsule):
            findings.append(SelectiveMemoryDistillationFinding("error", "unsafe_ai_capsule_payload", "AI capsule contains forbidden raw payload material", rid))
            return _blocked("selective_memory_distillation_blocked_raw_media_payload", findings)
        source_records.append(record)

    scope_sets = {record.source_scope_keys for record in source_records if record.source_scope_keys}
    if len(scope_sets) > 1:
        severity = "warning" if (policy.scope_mismatch_mode == "warn" and policy.allow_mixed_scope_diagnostic_packet) else "error"
        findings.append(SelectiveMemoryDistillationFinding(severity, "scope_mismatch", "records contain multiple scope key sets"))
        if severity == "error":
            return _blocked("selective_memory_distillation_blocked_scope_mismatch", findings)

    records = tuple(_record_from_source(record, policy) for record in source_records)
    counts: dict[str, int] = {"record_count": len(records), "warning_count": sum(1 for f in findings if f.severity == "warning")}
    for distillation_record in records:
        counts[distillation_record.distillation_decision] = counts.get(distillation_record.distillation_decision, 0) + 1
    packet = SelectiveMemoryDistillationPacket(policy.schema_version, records).with_digest()
    status: DistillationStatus = "selective_memory_distillation_ready_with_warnings" if any(f.severity == "warning" for f in findings) else "selective_memory_distillation_ready"
    report = SelectiveMemoryDistillationReport(status, tuple(findings), dict(sorted(counts.items())), "")
    report = replace(report, digest=_digest(report.to_dict()))
    return SelectiveMemoryDistillationResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))


def evaluate_packet(payload: Mapping[str, Any], policy: SelectiveMemoryDistillationPolicy | None = None) -> SelectiveMemoryDistillationResult:
    return evaluate_selective_memory_distillation_contract(payload, policy)
