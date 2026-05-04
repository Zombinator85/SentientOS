from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from typing import Any, Mapping, Sequence

from .claim_ledger import claim_receipt_ref
from .stance_preflight import build_stance_preflight_record, validate_planned_claim_against_stance
from .stance_receipts import detect_no_new_evidence_reversal

SCHEMA_VERSION = "phase59.research_response_gate.v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def research_response_gate_ref(record: Mapping[str, Any]) -> str:
    return f"research_response_gate:{record['response_gate_id']}"


def build_planned_research_response_record(*, conversation_scope_id: str, turn_id: str, topic_id: str, response_mode: str = "research", planned_claim_receipts: Sequence[Mapping[str, Any]] | None = None, evidence_ids_used: Sequence[str] | None = None, stance_transition_intents: Sequence[str] | None = None, intended_user_visible_claim_summary: str = "", caveats: Sequence[str] | None = None, created_at: str | None = None) -> dict[str, Any]:
    claims = [dict(c) for c in (planned_claim_receipts or [])]
    claim_ids = [str(c.get("claim_id") or "") for c in claims if c.get("claim_id")]
    material = f"{conversation_scope_id}|{turn_id}|{topic_id}|{response_mode}|{sorted(claim_ids)}|{sorted(evidence_ids_used or [])}"
    return {
        "schema_version": SCHEMA_VERSION,
        "planned_response_id": "prr_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
        "conversation_scope_id": conversation_scope_id,
        "turn_id": turn_id,
        "topic_id": topic_id,
        "response_mode": response_mode if response_mode in {"research", "diagnostic", "conversational", "correction", "unknown"} else "unknown",
        "planned_claim_ids": claim_ids,
        "planned_claim_refs": [claim_receipt_ref(c) for c in claims if c.get("claim_id")],
        "evidence_ids_used": list(evidence_ids_used or []),
        "stance_transition_intents": list(stance_transition_intents or []),
        "intended_user_visible_claim_summary": intended_user_visible_claim_summary,
        "caveats": list(caveats or []),
        "created_at": created_at or _now_iso(),
        "non_authoritative": True,
        "decision_power": "none",
        "planned_response_is_not_emission": True,
        "planned_response_is_not_memory": True,
        "does_not_write_memory": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
        "does_not_trigger_feedback": True,
    }


def classify_research_response_gate_outcome(*, blocking_reasons: Sequence[str], warning_reasons: Sequence[str]) -> str:
    if blocking_reasons:
        joined = " ".join(blocking_reasons)
        if "no_new_evidence_reversal" in joined:
            return "response_gate_blocked_no_new_evidence_reversal"
        if "unsupported_dilution" in joined:
            return "response_gate_blocked_unsupported_dilution"
        if "unsupported_source_undermining" in joined:
            return "response_gate_blocked_unsupported_source_undermining"
        if "quote_fidelity_failure" in joined:
            return "response_gate_blocked_quote_fidelity_failure"
        if "missing_evidence" in joined:
            return "response_gate_blocked_missing_evidence"
        return "response_gate_unknown"
    if warning_reasons:
        if any("needs_review" in reason for reason in warning_reasons):
            return "response_gate_needs_review"
        return "response_gate_allowed_with_caveat"
    return "response_gate_allowed"


def validate_planned_response_against_truth(*, planned_response: Mapping[str, Any], planned_claim_receipts: Sequence[Mapping[str, Any]], prior_claims: Sequence[Mapping[str, Any]], evidence_receipts: Sequence[Mapping[str, Any]], stance_receipts: Sequence[Mapping[str, Any]], contradiction_receipts: Sequence[Mapping[str, Any]], log_fed_summary: Mapping[str, Any] | None = None, created_at: str | None = None) -> dict[str, Any]:
    planned_response = deepcopy(dict(planned_response))
    planned_claims = [dict(c) for c in planned_claim_receipts]
    prior = [dict(c) for c in prior_claims]
    evidence = [dict(e) for e in evidence_receipts]
    stances = [dict(s) for s in stance_receipts]
    contradictions = [dict(c) for c in contradiction_receipts]

    topic_id = str(planned_response.get("topic_id") or "")
    evidence_ids = {str(r.get("evidence_id") or "") for r in evidence if r.get("evidence_id")}
    blocking: list[str] = []
    warnings: list[str] = []
    generated: list[dict[str, Any]] = []
    stance_preflight_ids: list[str] = []

    has_prior_topic = any(str(c.get("topic_id") or "") == topic_id for c in prior)
    has_active_stance = any(str(s.get("topic_id") or "") == topic_id for s in stances)
    if has_prior_topic and not has_active_stance:
        warnings.append("needs_review:active_stance_missing_with_prior_claims")

    if log_fed_summary and topic_id and str(log_fed_summary.get("status") or "") == "degraded":
        if log_fed_summary.get("truth_records_load_errors"):
            warnings.append("needs_review:log_fed_diagnostic_load_errors")

    active_by_topic = [c for c in prior if str(c.get("topic_id") or "") == topic_id]

    for idx, claim in enumerate(planned_claims):
        transition_type = (planned_response.get("stance_transition_intents") or ["hold_revision"] * len(planned_claims))[idx] if planned_claims else "hold_revision"
        check = validate_planned_claim_against_stance(planned_claim=claim, prior_claims=active_by_topic, stance_receipts=stances, transition_type=transition_type)
        record = build_stance_preflight_record(planned_claim=claim, prior_claims=active_by_topic, stance_receipts=stances, transition_type=transition_type)
        stance_preflight_ids.append(str(record.get("stance_preflight_id") or ""))

        status = str(claim.get("epistemic_status") or "unknown")
        kind = str(claim.get("claim_kind") or "unknown")
        claim_evidence = [str(eid) for eid in claim.get("evidence_ids", []) if eid]

        if status == "unknown":
            warnings.append("needs_review:unknown_epistemic_status")
        if transition_type == "hold_revision":
            warnings.append("needs_review:ambiguous_transition_intent")
        if transition_type == "policy_block_but_preserve" and status not in {"directly_supported", "supported_with_caveat"}:
            warnings.append("needs_review:policy_block_without_preserve_receipt")
            blocking.append("policy_block_must_not_become_factual_reversal")

        if kind in {"source_backed_claim", "source_backed_implication"} and status not in {"underconstrained", "unknown"}:
            if not claim_evidence or not set(claim_evidence).issubset(evidence_ids):
                blocking.append("missing_evidence:source_backed_claim_requires_evidence")
        if status in {"underconstrained", "unknown", "plausible_but_unverified"}:
            warnings.append("caveat:provisional_or_underconstrained_claim_present")

        contradiction_type = check.get("contradiction_type")
        active_claim = active_by_topic[-1] if active_by_topic else None
        if contradiction_type is None and active_claim is not None:
            derived = detect_no_new_evidence_reversal(previous_claim=active_claim, new_claim=claim, transition_type=transition_type, new_evidence_ids=list(set(claim_evidence) - set(active_claim.get("evidence_ids", []))))
            contradiction_type = (derived or {}).get("contradiction_type")
        if contradiction_type:
            blocking.append(str(contradiction_type))
            generated.append({"contradiction_type": contradiction_type, "topic_id": topic_id, "new_claim_id": claim.get("claim_id")})

    for row in contradictions:
        if str(row.get("topic_id") or "") != topic_id:
            continue
        ctype = str(row.get("contradiction_type") or "")
        sev = str(row.get("severity") or "")
        if sev == "blocking":
            blocking.append(ctype)

    blocking = sorted(set(blocking))
    warnings = sorted(set(warnings))
    outcome = classify_research_response_gate_outcome(blocking_reasons=blocking, warning_reasons=warnings)

    material = f"{planned_response.get('planned_response_id')}|{topic_id}|{outcome}|{blocking}|{warnings}"
    return {
        "schema_version": SCHEMA_VERSION,
        "response_gate_id": "rrg_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
        "planned_response_id": planned_response.get("planned_response_id", ""),
        "conversation_scope_id": planned_response.get("conversation_scope_id", ""),
        "turn_id": planned_response.get("turn_id", ""),
        "topic_id": topic_id,
        "response_mode": planned_response.get("response_mode", "unknown"),
        "planned_claim_ids": list(planned_response.get("planned_claim_ids") or []),
        "active_claim_ids_checked": [c.get("claim_id") for c in active_by_topic if c.get("claim_id")],
        "evidence_ids_checked": sorted(evidence_ids),
        "contradiction_ids_checked": [c.get("contradiction_id") for c in contradictions if c.get("contradiction_id")],
        "stance_preflight_ids": [x for x in stance_preflight_ids if x],
        "gate_outcome": outcome,
        "blocking_reasons": blocking,
        "warning_reasons": warnings,
        "generated_contradiction_receipts": generated,
        "planned_response_adjustment_guidance": "Preserve stance linkage and add/retain evidence or explicit caveats before any future response emission.",
        "created_at": created_at or _now_iso(),
        "non_authoritative": True,
        "decision_power": "none",
        "response_gate_is_not_response_generation": True,
        "response_gate_is_not_memory_write": True,
        "does_not_write_memory": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
        "does_not_trigger_feedback": True,
    }


def summarize_research_response_gate_results(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(r.get("gate_outcome") or "response_gate_unknown") for r in records)
    topics = sorted({str(r.get("topic_id") or "") for r in records if str(r.get("gate_outcome") or "").startswith("response_gate_blocked")})
    blocked = sum(v for k, v in counts.items() if k.startswith("response_gate_blocked"))
    warnings = sum(len(list(r.get("warning_reasons") or [])) for r in records)
    needs_review = counts.get("response_gate_needs_review", 0)
    allowed = counts.get("response_gate_allowed", 0)

    if not records:
        posture = "no_response_gates_recorded"
    elif blocked and needs_review:
        posture = "mixed_response_gate_state"
    elif blocked:
        posture = "response_gates_blocked"
    elif needs_review:
        posture = "response_gates_need_review"
    elif counts.get("response_gate_allowed_with_caveat", 0):
        posture = "response_gates_with_warnings"
    else:
        posture = "response_gates_clear"

    return {
        "response_gate_count": len(records),
        "counts_by_outcome": dict(sorted(counts.items())),
        "blocked_count": blocked,
        "warning_count": warnings,
        "needs_review_count": needs_review,
        "allowed_count": allowed,
        "topics_with_blocking_gate": topics,
        "response_gate_posture": posture,
    }
