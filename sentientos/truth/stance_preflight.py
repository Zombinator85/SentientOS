from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Mapping, Sequence

from .stance_receipts import detect_no_new_evidence_reversal, validate_stance_transition

SCHEMA_VERSION = "phase58.stance_preflight.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_stance_preflight_outcome(*, transition_allowed: bool, contradiction_type: str | None, transition_type: str, new_evidence_ids: Sequence[str], has_prior_claims: bool, active_claim_missing: bool, planned_epistemic_status: str) -> str:
    if planned_epistemic_status == "unknown":
        return "stance_preflight_needs_review"
    if active_claim_missing and has_prior_claims:
        return "stance_preflight_needs_review"
    if not transition_allowed:
        return "stance_preflight_needs_review"
    ctype = str(contradiction_type or "")
    if ctype == "no_new_evidence_reversal":
        return "stance_preflight_blocked_no_new_evidence_reversal"
    if ctype == "unsupported_dilution":
        return "stance_preflight_blocked_unsupported_dilution"
    if ctype == "unsupported_source_undermining":
        return "stance_preflight_blocked_unsupported_source_undermining"
    if ctype == "quote_fidelity_failure":
        return "stance_preflight_blocked_quote_fidelity_failure"
    if transition_type in {"preserve"}:
        return "stance_preflight_allowed_preserve"
    if transition_type in {"narrow"}:
        return "stance_preflight_allowed_narrow"
    if transition_type in {"qualify"}:
        return "stance_preflight_allowed_qualify"
    if transition_type in {"supersede_with_new_evidence", "weaken_with_new_evidence", "retract_due_to_error"} and list(new_evidence_ids):
        return "stance_preflight_allowed_with_new_evidence"
    if transition_type == "policy_block_but_preserve":
        return "stance_preflight_needs_review"
    return "stance_preflight_unknown"


def validate_planned_claim_against_stance(*, planned_claim: Mapping[str, Any], prior_claims: Sequence[Mapping[str, Any]], stance_receipts: Sequence[Mapping[str, Any]], contradiction_receipts: Sequence[Mapping[str, Any]] | None = None, transition_type: str = "hold_revision", rationale: str = "", has_new_source_quality_finding: bool = False) -> dict[str, Any]:
    claims = list(prior_claims)
    active_claim_id = str(stance_receipts[-1].get("active_claim_id") or "") if stance_receipts else ""
    active_claim = next((c for c in reversed(claims) if str(c.get("claim_id") or "") == active_claim_id), claims[-1] if claims else {})
    new_ids = sorted(set(planned_claim.get("evidence_ids") or []) - set(active_claim.get("evidence_ids") or []))
    transition_allowed, transition_reason = validate_stance_transition(transition_type=transition_type, new_evidence_ids=new_ids, contradictory=False, rationale=rationale, has_new_source_quality_finding=has_new_source_quality_finding)
    contradiction = detect_no_new_evidence_reversal(previous_claim=active_claim, new_claim=dict(planned_claim), transition_type=transition_type, new_evidence_ids=new_ids, has_new_source_quality_finding=has_new_source_quality_finding) if active_claim else None
    if not new_ids and set(active_claim.get("evidence_ids") or []) - set(planned_claim.get("evidence_ids") or []):
        contradiction = contradiction or {"contradiction_type": "unsupported_dilution", "severity": "blocking", "adjudication": "block_revision"}
    if str(planned_claim.get("quote_hash") or "") == "mismatch":
        contradiction = {"contradiction_type": "quote_fidelity_failure", "severity": "blocking", "adjudication": "block_revision"}
    outcome = classify_stance_preflight_outcome(
        transition_allowed=transition_allowed,
        contradiction_type=(contradiction or {}).get("contradiction_type"),
        transition_type=transition_type,
        new_evidence_ids=new_ids,
        has_prior_claims=bool(claims),
        active_claim_missing=not bool(active_claim),
        planned_epistemic_status=str(planned_claim.get("epistemic_status") or "unknown"),
    )
    return {"transition_allowed": transition_allowed, "transition_reason": transition_reason, "contradiction_receipt": contradiction, "preflight_outcome": outcome, "active_claim": dict(active_claim), "active_claim_id": str(active_claim.get("claim_id") or ""), "new_evidence_ids": new_ids}


def build_stance_preflight_record(*, planned_claim: Mapping[str, Any], prior_claims: Sequence[Mapping[str, Any]], stance_receipts: Sequence[Mapping[str, Any]], contradiction_receipts: Sequence[Mapping[str, Any]] | None = None, transition_type: str = "hold_revision", rationale: str = "", has_new_source_quality_finding: bool = False, created_at: str | None = None) -> dict[str, Any]:
    v = validate_planned_claim_against_stance(planned_claim=planned_claim, prior_claims=prior_claims, stance_receipts=stance_receipts, contradiction_receipts=contradiction_receipts, transition_type=transition_type, rationale=rationale, has_new_source_quality_finding=has_new_source_quality_finding)
    active = v["active_claim"]
    material = f"{planned_claim.get('topic_id')}|{planned_claim.get('claim_id')}|{v['active_claim_id']}|{transition_type}|{v['preflight_outcome']}"
    return {
        "schema_version": SCHEMA_VERSION,
        "stance_preflight_id": "spf_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
        "topic_id": planned_claim.get("topic_id"),
        "planned_claim_id": planned_claim.get("claim_id"),
        "active_claim_id": v["active_claim_id"] or None,
        "planned_epistemic_status": planned_claim.get("epistemic_status", "unknown"),
        "active_epistemic_status": active.get("epistemic_status", "unknown") if active else "unknown",
        "planned_evidence_ids": list(planned_claim.get("evidence_ids") or []),
        "active_evidence_ids": list(active.get("evidence_ids") or []),
        "new_evidence_ids": list(v["new_evidence_ids"]),
        "transition_type": transition_type,
        "preflight_outcome": v["preflight_outcome"],
        "contradiction_receipt": v["contradiction_receipt"],
        "rationale": rationale,
        "evidence": {"transition_reason": v["transition_reason"]},
        "created_at": created_at or _utc_now(),
        "non_authoritative": True,
        "decision_power": "none",
        "preflight_is_not_response_generation": True,
        "preflight_is_not_memory_write": True,
        "does_not_write_memory": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
        "does_not_trigger_feedback": True,
    }


def summarize_stance_preflight_results(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in records:
        key = str(row.get("preflight_outcome") or "stance_preflight_unknown")
        counts[key] = counts.get(key, 0) + 1
    return {"preflight_count": len(records), "counts_by_outcome": dict(sorted(counts.items()))}


def stance_preflight_ref(receipt: Mapping[str, Any]) -> str:
    return f"stance_preflight:{receipt['stance_preflight_id']}"
