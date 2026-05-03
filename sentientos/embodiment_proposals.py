from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos.ledger_api import append_audit_record

SCHEMA_VERSION = "embodiment.proposal.v1"
DEFAULT_PROPOSAL_LOG = Path("logs/embodiment_proposals.jsonl")


def classify_embodied_proposal_kind(*, blocked_effect_type: str, source_module: str, ingress_receipt: Mapping[str, Any] | None = None) -> str:
    effect = blocked_effect_type.strip().lower()
    if effect == "memory_write":
        return "memory_ingress_candidate"
    if effect == "feedback_action":
        return "feedback_action_candidate"
    if effect == "retention:screen_ocr":
        return "screen_retention_candidate"
    if effect == "retention:vision_emotion":
        return "vision_retention_candidate"
    if effect.startswith("retention:multimodal"):
        return "multimodal_retention_candidate"
    if effect == "operator_attention":
        return "operator_attention_candidate"
    candidate = ingress_receipt.get("operator_attention_candidate") if isinstance(ingress_receipt, Mapping) else None
    if candidate:
        return "operator_attention_candidate"
    if "screen" in source_module:
        return "screen_retention_candidate"
    if "vision" in source_module:
        return "vision_retention_candidate"
    if "multimodal" in source_module:
        return "multimodal_retention_candidate"
    return "operator_attention_candidate"


def embodied_proposal_ref(record: Mapping[str, Any]) -> str:
    return f"proposal:{record['proposal_id']}"


def _proposal_id(material: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
    return f"ep_{digest}"


def build_embodied_proposal_record(*, source_module: str, gate_mode: str, blocked_effect_type: str, ingress_receipt: Mapping[str, Any] | None = None,
                                   source_event_refs: Sequence[str] | None = None, source_snapshot_ref: str | None = None,
                                   correlation_id: str | None = None, risk_flags: Mapping[str, Any] | None = None,
                                   candidate_payload_summary: Mapping[str, Any] | None = None, rationale: Sequence[str] | None = None,
                                   proposal_kind: str | None = None, privacy_retention_posture: str | None = None,
                                   consent_posture: str | None = None, created_at: float | None = None) -> dict[str, Any]:
    receipt = dict(ingress_receipt or {})
    event_refs = list(source_event_refs if source_event_refs is not None else receipt.get("source_event_refs", []))
    snapshot_ref = source_snapshot_ref if source_snapshot_ref is not None else receipt.get("source_snapshot_ref")
    corr = correlation_id if correlation_id is not None else receipt.get("correlation_id")
    material = {
        "source_module": source_module,
        "gate_mode": gate_mode,
        "blocked_effect_type": blocked_effect_type,
        "ingress_receipt_ref": receipt.get("ingress_id"),
        "source_snapshot_ref": snapshot_ref,
        "source_event_refs": event_refs,
        "correlation_id": corr,
        "candidate_payload_summary": dict(candidate_payload_summary or {}),
    }
    kind = proposal_kind or classify_embodied_proposal_kind(blocked_effect_type=blocked_effect_type, source_module=source_module, ingress_receipt=receipt)
    return {
        "schema_version": SCHEMA_VERSION,
        "proposal_id": _proposal_id(material),
        "proposal_kind": kind,
        "source_module": source_module,
        "gate_mode": gate_mode,
        "blocked_effect_type": blocked_effect_type,
        "ingress_receipt_ref": receipt.get("ingress_id"),
        "source_event_refs": event_refs,
        "source_snapshot_ref": snapshot_ref,
        "correlation_id": corr,
        "privacy_retention_posture": privacy_retention_posture or receipt.get("privacy_retention_posture", "review"),
        "consent_posture": consent_posture or receipt.get("consent_posture", "not_asserted"),
        "risk_flags": dict(risk_flags or receipt.get("risk_flags", {})),
        "candidate_payload_summary": dict(candidate_payload_summary or {}),
        "rationale": list(rationale or receipt.get("rationale", ["blocked_effect:proposal_only"])),
        "created_at": float(created_at if created_at is not None else time.time()),
        "review_status": "pending_review",
        "non_authoritative": True,
        "decision_power": "none",
        "does_not_write_memory": True,
        "does_not_trigger_feedback": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
    }


def append_embodied_proposal(record: Mapping[str, Any], *, path: Path = DEFAULT_PROPOSAL_LOG) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    return append_audit_record(path, record)


def record_blocked_embodiment_effect(*, source_module: str, gate_mode: str, blocked_effect_type: str, ingress_receipt: Mapping[str, Any] | None = None,
                                    candidate_payload_summary: Mapping[str, Any] | None = None, rationale: Sequence[str] | None = None,
                                    append_proposal: Any = None) -> dict[str, Any]:
    record = build_embodied_proposal_record(
        source_module=source_module,
        gate_mode=gate_mode,
        blocked_effect_type=blocked_effect_type,
        ingress_receipt=ingress_receipt,
        candidate_payload_summary=candidate_payload_summary,
        rationale=rationale,
    )
    writer = append_proposal or append_embodied_proposal
    writer(record)
    return record


def list_recent_embodied_proposals(*, path: Path = DEFAULT_PROPOSAL_LOG, limit: int = 20) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[-max(1, limit):]


__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_PROPOSAL_LOG",
    "build_embodied_proposal_record",
    "append_embodied_proposal",
    "record_blocked_embodiment_effect",
    "embodied_proposal_ref",
    "list_recent_embodied_proposals",
    "classify_embodied_proposal_kind",
]
