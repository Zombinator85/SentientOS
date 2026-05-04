from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "phase57.evidence_diagnostic.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def evidence_stability_diagnostic_ref(record: Mapping[str, Any]) -> str:
    return f"evidence_diagnostic:{record['diagnostic_id']}"


def count_claims_by_epistemic_status(claim_receipts: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in claim_receipts:
        status = str(row.get("epistemic_status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _count_claims_by_kind(claim_receipts: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in claim_receipts:
        kind = str(row.get("claim_kind") or "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items()))


def count_contradictions_by_type(contradiction_receipts: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in contradiction_receipts:
        ctype = str(row.get("contradiction_type") or "unknown")
        counts[ctype] = counts.get(ctype, 0) + 1
    return dict(sorted(counts.items()))


def summarize_claim_evidence_state(*, claim_receipts: Sequence[Mapping[str, Any]], evidence_receipts: Sequence[Mapping[str, Any]], stance_receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    active_stance = stance_receipts[-1] if stance_receipts else {}
    active_claim_id = str(active_stance.get("active_claim_id") or (claim_receipts[-1].get("claim_id") if claim_receipts else ""))
    active_claim = next((c for c in claim_receipts if str(c.get("claim_id") or "") == active_claim_id), claim_receipts[-1] if claim_receipts else {})
    return {
        "claim_count_total": len(claim_receipts),
        "evidence_count_total": len(evidence_receipts),
        "stance_receipt_count": len(stance_receipts),
        "active_claim_id": active_claim_id or None,
        "active_epistemic_status": str(active_claim.get("epistemic_status") or "unknown") if active_claim else "unknown",
        "active_evidence_ids": list(active_claim.get("evidence_ids") or []),
        "counts_by_epistemic_status": count_claims_by_epistemic_status(claim_receipts),
        "counts_by_claim_kind": _count_claims_by_kind(claim_receipts),
    }


def summarize_stance_contradictions(*, contradiction_receipts: Sequence[Mapping[str, Any]], stance_receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    blocking = [c for c in contradiction_receipts if str(c.get("severity") or "") == "blocking" or str(c.get("adjudication") or "") in {"block_revision", "require_new_evidence"}]
    warning = [c for c in contradiction_receipts if str(c.get("severity") or "") == "warning"]
    tcounts = count_contradictions_by_type(contradiction_receipts)
    policy_preserve = sum(1 for s in stance_receipts if str(s.get("transition_type") or "") == "policy_block_but_preserve")
    return {
        "contradiction_count_total": len(contradiction_receipts),
        "counts_by_contradiction_type": tcounts,
        "blocking_contradiction_count": len(blocking),
        "warning_contradiction_count": len(warning),
        "no_new_evidence_reversal_count": tcounts.get("no_new_evidence_reversal", 0),
        "unsupported_dilution_count": tcounts.get("unsupported_dilution", 0),
        "unsupported_source_undermining_count": tcounts.get("unsupported_source_undermining", 0),
        "policy_block_preserved_count": policy_preserve,
        "open_review_required_count": len(warning) + tcounts.get("quote_fidelity_failure", 0),
    }


def classify_evidence_stability_posture(*, claim_count_total: int, active_epistemic_status: str, blocking_contradiction_count: int, warning_contradiction_count: int, no_new_evidence_reversal_count: int, unsupported_source_undermining_count: int) -> str:
    if claim_count_total == 0:
        return "no_claims_recorded"
    if no_new_evidence_reversal_count > 0:
        return "blocked_due_to_no_new_evidence_reversal"
    if unsupported_source_undermining_count > 0:
        return "blocked_due_to_unsupported_source_undermining"
    if blocking_contradiction_count > 0:
        return "mixed_or_contested_stance"
    if active_epistemic_status in {"underconstrained", "plausible_but_unverified", "unknown", "blocked"}:
        return "provisional_or_underconstrained_stance"
    if warning_contradiction_count > 0:
        return "review_required_due_to_warnings"
    if active_epistemic_status in {"directly_supported", "provisional_supported", "strongly_inferred"}:
        return "stable_supported_stance"
    return "mixed_or_contested_stance"


def build_evidence_stability_diagnostic(*, claim_receipts: Sequence[Mapping[str, Any]], evidence_receipts: Sequence[Mapping[str, Any]], stance_receipts: Sequence[Mapping[str, Any]], contradiction_receipts: Sequence[Mapping[str, Any]], topic_id: str | None = None, generated_at: str | None = None) -> dict[str, Any]:
    claims = list(claim_receipts)
    evidence = list(evidence_receipts)
    stances = list(stance_receipts)
    contradictions = list(contradiction_receipts)
    claim_summary = summarize_claim_evidence_state(claim_receipts=claims, evidence_receipts=evidence, stance_receipts=stances)
    contradiction_summary = summarize_stance_contradictions(contradiction_receipts=contradictions, stance_receipts=stances)
    posture = classify_evidence_stability_posture(
        claim_count_total=claim_summary["claim_count_total"],
        active_epistemic_status=claim_summary["active_epistemic_status"],
        blocking_contradiction_count=contradiction_summary["blocking_contradiction_count"],
        warning_contradiction_count=contradiction_summary["warning_contradiction_count"],
        no_new_evidence_reversal_count=contradiction_summary["no_new_evidence_reversal_count"],
        unsupported_source_undermining_count=contradiction_summary["unsupported_source_undermining_count"],
    )
    material = f"{topic_id or 'none'}|{claim_summary['active_claim_id'] or 'none'}|{claim_summary['claim_count_total']}|{contradiction_summary['contradiction_count_total']}"
    return {
        "schema_version": SCHEMA_VERSION,
        "diagnostic_id": "esd_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
        "generated_at": generated_at or _utc_now(),
        "topic_id": topic_id,
        **claim_summary,
        **contradiction_summary,
        "evidence_stability_posture": posture,
        "user_visible_note": "Diagnostic-only epistemic stability summary. No memory or work routing effects.",
        "non_authoritative": True,
        "decision_power": "none",
        "diagnostic_is_not_memory": True,
        "does_not_write_memory": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
    }
