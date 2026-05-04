from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "phase57.truth_memory_ingress_guard.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def truth_memory_ingress_guard_ref(record: Mapping[str, Any]) -> str:
    return f"truth_memory_ingress_guard:{record['truth_memory_ingress_guard_id']}"


def classify_truth_memory_ingress_outcome(*, claim: Mapping[str, Any], contradictions: Sequence[Mapping[str, Any]], active_stance: Mapping[str, Any] | None) -> tuple[str, list[str]]:
    rationale: list[str] = []
    status = str(claim.get("epistemic_status") or "unknown")
    kind = str(claim.get("claim_kind") or "unknown")
    evidence_ids = list(claim.get("evidence_ids") or [])
    evidence_refs = list(claim.get("evidence_refs") or [])

    if kind in {"source_backed_claim", "source_backed_implication"} and not (evidence_ids or evidence_refs):
        return "truth_memory_ingress_blocked_missing_evidence", ["source-backed claim requires evidence linkage"]
    if status in {"underconstrained", "plausible_but_unverified", "unknown", "blocked"}:
        return "truth_memory_ingress_blocked_underconstrained", [f"epistemic status {status} not eligible for active memory"]
    if status in {"retracted_due_to_error", "superseded_by_new_evidence", "contradicted_by_new_evidence"}:
        return "truth_memory_ingress_blocked_retracted_or_superseded", [f"status {status} is non-active truth"]

    c_types = {str(c.get("contradiction_type") or "") for c in contradictions}
    if "no_new_evidence_reversal" in c_types:
        return "truth_memory_ingress_blocked_no_new_evidence_reversal", ["blocking no-new-evidence reversal present"]
    if "unsupported_dilution" in c_types:
        return "truth_memory_ingress_blocked_unsupported_dilution", ["unsupported dilution present"]
    if "unsupported_source_undermining" in c_types:
        return "truth_memory_ingress_blocked_unsupported_source_undermining", ["unsupported source undermining present"]
    if "quote_fidelity_failure" in c_types:
        return "truth_memory_ingress_blocked_quote_fidelity_failure", ["quote fidelity failure present"]

    has_blocking = any(str(c.get("severity") or "") == "blocking" or str(c.get("adjudication") or "") in {"block_revision", "require_new_evidence"} for c in contradictions)
    if has_blocking:
        return "truth_memory_ingress_needs_review", ["blocking contradiction adjudication present"]

    if active_stance:
        transition = str(active_stance.get("transition_type") or "")
        active_claim_id = str(active_stance.get("active_claim_id") or "")
        claim_id = str(claim.get("claim_id") or "")
        prev_claim_id = str(active_stance.get("previous_claim_id") or "")
        if active_claim_id != claim_id and not (transition == "policy_block_but_preserve" and prev_claim_id == claim_id):
            return "truth_memory_ingress_needs_review", ["active stance does not match claim"]
        if transition == "policy_block_but_preserve" and prev_claim_id == claim_id:
            rationale.append("policy block preserves prior supported claim")

    if status in {"directly_supported", "provisional_supported", "strongly_inferred"}:
        rationale.append("supported status with required evidence and no blocking contradiction")
        return "truth_memory_ingress_validated_for_future_memory", rationale

    return "truth_memory_ingress_blocked_unknown_status", [f"unhandled epistemic status {status}"]


def build_truth_memory_ingress_guard_record(*, claim_receipt: Mapping[str, Any], evidence_receipts: Sequence[Mapping[str, Any]], stance_receipts: Sequence[Mapping[str, Any]], contradiction_receipts: Sequence[Mapping[str, Any]], created_at: str | None = None) -> dict[str, Any]:
    claim_id = str(claim_receipt.get("claim_id") or "")
    linked_contradictions = [c for c in contradiction_receipts if claim_id in {str(c.get("old_claim_id") or ""), str(c.get("new_claim_id") or "")}]
    blocking_ids = [str(c.get("contradiction_id") or "") for c in linked_contradictions if str(c.get("severity") or "") == "blocking" or str(c.get("adjudication") or "") in {"block_revision", "require_new_evidence"}]
    active_stance = stance_receipts[-1] if stance_receipts else None
    outcome, rationale = classify_truth_memory_ingress_outcome(claim=claim_receipt, contradictions=linked_contradictions, active_stance=active_stance)
    material = f"{claim_id}|{outcome}|{','.join(sorted(blocking_ids))}"
    return {
        "schema_version": SCHEMA_VERSION,
        "truth_memory_ingress_guard_id": "tmg_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
        "claim_id": claim_id,
        "claim_ref": f"claim:{claim_id}",
        "topic_id": claim_receipt.get("topic_id"),
        "epistemic_status": claim_receipt.get("epistemic_status", "unknown"),
        "claim_kind": claim_receipt.get("claim_kind", "unknown"),
        "evidence_ids": list(claim_receipt.get("evidence_ids") or []),
        "active_stance_lock_id": None if not active_stance else active_stance.get("stance_lock_id"),
        "contradiction_ids": [str(c.get("contradiction_id") or "") for c in linked_contradictions],
        "blocking_contradiction_ids": blocking_ids,
        "validation_outcome": outcome,
        "evidence_complete": bool((claim_receipt.get("evidence_ids") or []) or (claim_receipt.get("evidence_refs") or [])),
        "active_stance_matches_claim": True if not active_stance else (str(active_stance.get("active_claim_id") or "") == claim_id or (str(active_stance.get("transition_type") or "") == "policy_block_but_preserve" and str(active_stance.get("previous_claim_id") or "") == claim_id)),
        "contradiction_free": not linked_contradictions,
        "rationale": rationale,
        "created_at": created_at or _utc_now(),
        "non_authoritative": True,
        "decision_power": "none",
        "guard_is_not_memory_write": True,
        "validation_is_not_memory_write": True,
        "does_not_write_memory": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
        "does_not_trigger_feedback": True,
    }


def validate_claim_for_memory_ingress(**kwargs: Any) -> dict[str, Any]:
    return build_truth_memory_ingress_guard_record(**kwargs)


def resolve_truth_memory_ingress_guards(*, claim_receipts: Sequence[Mapping[str, Any]], evidence_receipts: Sequence[Mapping[str, Any]], stance_receipts: Sequence[Mapping[str, Any]], contradiction_receipts: Sequence[Mapping[str, Any]], created_at: str | None = None) -> dict[str, Any]:
    rows = [
        validate_claim_for_memory_ingress(
            claim_receipt=claim,
            evidence_receipts=evidence_receipts,
            stance_receipts=stance_receipts,
            contradiction_receipts=contradiction_receipts,
            created_at=created_at,
        )
        for claim in claim_receipts
    ]
    return {
        "truth_memory_ingress_guard_records": rows,
        "truth_memory_ingress_guard_summary": summarize_truth_memory_ingress_guard_status(truth_memory_ingress_guard_records=rows),
    }


def summarize_truth_memory_ingress_guard_status(*, truth_memory_ingress_guard_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_outcome: dict[str, int] = {}
    for row in truth_memory_ingress_guard_records:
        outcome = str(row.get("validation_outcome") or "truth_memory_ingress_blocked_unknown_status")
        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
    return {
        "truth_memory_ingress_guard_count": len(truth_memory_ingress_guard_records),
        "truth_memory_ingress_guard_counts_by_outcome": dict(sorted(by_outcome.items())),
        "validated_for_future_memory_count": by_outcome.get("truth_memory_ingress_validated_for_future_memory", 0),
        "blocked_count": sum(v for k, v in by_outcome.items() if k.startswith("truth_memory_ingress_blocked")),
    }
