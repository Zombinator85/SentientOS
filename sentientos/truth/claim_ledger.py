from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

from sentientos.attestation import read_jsonl
from sentientos.ledger_api import append_audit_record
from sentientos.truth.epistemic_status import normalize_epistemic_status

SCHEMA_VERSION = "phase56.claim.v1"
DEFAULT_CLAIM_LEDGER = Path("logs/truth/claim_ledger.jsonl")
CLAIM_KINDS = {
    "direct_extraction", "source_backed_claim", "source_backed_implication", "model_inference", "user_claim", "policy_override", "uncertainty_statement", "correction", "unknown",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_claim_scope(value: str | None) -> str:
    return str(value or "global").strip() or "global"


def classify_claim_kind(value: str | None) -> str:
    v = str(value or "unknown").strip().lower()
    return v if v in CLAIM_KINDS else "unknown"


def link_claim_to_evidence(evidence_ids: list[str] | None = None, evidence_refs: list[str] | None = None) -> dict[str, list[str]]:
    return {"evidence_ids": list(evidence_ids or []), "evidence_refs": list(evidence_refs or [])}


def build_claim_receipt(*, conversation_scope_id: str, turn_id: str, topic_id: str, claim_text: str, claim_kind: str = "unknown", epistemic_status: str = "unknown", confidence_band: str = "unknown", evidence_ids: list[str] | None = None, evidence_refs: list[str] | None = None, source_quality_summary: str = "", caveats: list[str] | None = None, what_would_change_the_claim: str = "", supersedes_claim_id: str | None = None, created_at: str | None = None) -> dict[str, Any]:
    kind = classify_claim_kind(claim_kind)
    status = normalize_epistemic_status(epistemic_status)
    links = link_claim_to_evidence(evidence_ids, evidence_refs)
    if kind in {"source_backed_claim", "source_backed_implication"} and not (links["evidence_ids"] or links["evidence_refs"]):
        if status not in {"underconstrained", "unknown"}:
            raise ValueError("source-backed claims require evidence unless underconstrained or unknown")
    normalized_claim = " ".join(claim_text.strip().lower().split())
    claim_id = hashlib.sha256("|".join([normalize_claim_scope(conversation_scope_id), str(turn_id), topic_id, normalized_claim, kind, status]).encode("utf-8")).hexdigest()[:24]
    return {
        "schema_version": SCHEMA_VERSION,
        "claim_id": claim_id,
        "conversation_scope_id": normalize_claim_scope(conversation_scope_id),
        "turn_id": str(turn_id),
        "topic_id": topic_id,
        "claim_text": claim_text,
        "normalized_claim": normalized_claim,
        "claim_kind": kind,
        "epistemic_status": status,
        "confidence_band": confidence_band if confidence_band in {"low", "medium", "high", "unknown"} else "unknown",
        "evidence_ids": links["evidence_ids"],
        "evidence_refs": links["evidence_refs"],
        "source_quality_summary": source_quality_summary,
        "caveats": list(caveats or []),
        "what_would_change_the_claim": what_would_change_the_claim,
        "supersedes_claim_id": supersedes_claim_id,
        "created_at": created_at or _utc_now(),
        "non_authoritative": True,
        "decision_power": "none",
        "claim_is_not_memory": True,
        "does_not_write_memory": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
    }


def claim_receipt_ref(receipt: dict[str, Any]) -> str:
    return f"claim:{receipt['claim_id']}"


def append_claim_receipt(receipt: dict[str, Any], *, path: Path = DEFAULT_CLAIM_LEDGER) -> dict[str, Any]:
    return append_audit_record(path, dict(receipt))


def list_recent_claim_receipts(*, path: Path = DEFAULT_CLAIM_LEDGER, limit: int = 50) -> list[dict[str, Any]]:
    rows = [row for row in read_jsonl(path) if isinstance(row, dict)]
    return rows[-max(0, limit) :]
