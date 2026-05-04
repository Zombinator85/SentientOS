from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

from sentientos.ledger_api import append_audit_record
from sentientos.attestation import read_jsonl

SCHEMA_VERSION = "phase56.evidence.v1"
DEFAULT_EVIDENCE_LEDGER = Path("logs/truth/evidence_ledger.jsonl")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_evidence_locator(locator: str | dict[str, Any] | None) -> str:
    if locator is None:
        return ""
    if isinstance(locator, dict):
        return "|".join(f"{k}={locator[k]}" for k in sorted(locator))
    return str(locator).strip()


def hash_evidence_span(quote_text: str | None) -> str:
    return hashlib.sha256(str(quote_text or "").encode("utf-8")).hexdigest()


def build_evidence_receipt(*, source_type: str, source_id: str, locator: str | dict[str, Any] | None = None, quote_text: str = "", retrieval_query_id: str | None = None, observed_at: str | None = None, created_at: str | None = None, source_trust_tier: str = "unknown", source_quality_notes: str = "") -> dict[str, Any]:
    normalized_locator = normalize_evidence_locator(locator)
    quote_hash = hash_evidence_span(quote_text)
    evidence_basis = "|".join([source_type, source_id, normalized_locator, quote_hash, retrieval_query_id or ""])
    evidence_id = hashlib.sha256(evidence_basis.encode("utf-8")).hexdigest()[:24]
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": evidence_id,
        "source_type": source_type if source_type else "unknown",
        "source_id": source_id,
        "locator": normalized_locator,
        "quote_text": quote_text,
        "quote_hash": quote_hash,
        "retrieval_query_id": retrieval_query_id,
        "observed_at": observed_at or _utc_now(),
        "created_at": created_at or _utc_now(),
        "source_trust_tier": source_trust_tier,
        "source_quality_notes": source_quality_notes,
        "non_authoritative": True,
        "decision_power": "none",
        "does_not_write_memory": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
    }


def evidence_receipt_ref(receipt: dict[str, Any]) -> str:
    return f"evidence:{receipt['evidence_id']}"


def append_evidence_receipt(receipt: dict[str, Any], *, path: Path = DEFAULT_EVIDENCE_LEDGER) -> dict[str, Any]:
    return append_audit_record(path, dict(receipt))


def list_recent_evidence_receipts(*, path: Path = DEFAULT_EVIDENCE_LEDGER, limit: int = 50) -> list[dict[str, Any]]:
    rows = [row for row in read_jsonl(path) if isinstance(row, dict)]
    return rows[-max(0, limit) :]
