from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

TRANSITIONS_WITHOUT_NEW_EVIDENCE = {"initial_stance", "preserve", "narrow", "qualify", "policy_block_but_preserve", "hold_revision"}
TRANSITIONS_REQUIRE_NEW_EVIDENCE = {"weaken_with_new_evidence", "supersede_with_new_evidence"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_stance_transition(value: str | None) -> str:
    normalized = str(value or "hold_revision").strip().lower()
    allowed = TRANSITIONS_WITHOUT_NEW_EVIDENCE | TRANSITIONS_REQUIRE_NEW_EVIDENCE | {"strengthen", "retract_due_to_error"}
    return normalized if normalized in allowed else "hold_revision"


def validate_stance_transition(*, transition_type: str, new_evidence_ids: list[str] | None = None, contradictory: bool = False, rationale: str = "", has_new_source_quality_finding: bool = False) -> tuple[bool, str]:
    t = classify_stance_transition(transition_type)
    new_evidence = list(new_evidence_ids or [])
    if t in TRANSITIONS_REQUIRE_NEW_EVIDENCE and not new_evidence:
        return False, "new evidence required"
    if t == "qualify" and contradictory:
        return False, "qualify transition cannot contradict prior claim without new evidence"
    if t == "retract_due_to_error" and not rationale.strip():
        return False, "retraction requires explicit rationale"
    if t == "policy_block_but_preserve" and not has_new_source_quality_finding:
        return True, "policy block allowed; prior source-backed stance preserved"
    return True, "transition allowed"


def build_stance_receipt(*, topic_id: str, active_claim_id: str, previous_claim_id: str | None = None, transition_type: str = "hold_revision", evidence_ids: list[str] | None = None, new_evidence_ids: list[str] | None = None, contradictory: bool = False, rationale: str = "") -> dict[str, Any]:
    allowed, reason = validate_stance_transition(transition_type=transition_type, new_evidence_ids=new_evidence_ids, contradictory=contradictory, rationale=rationale)
    material = "|".join([topic_id, str(previous_claim_id or ""), active_claim_id, classify_stance_transition(transition_type), ",".join(sorted(evidence_ids or [])), ",".join(sorted(new_evidence_ids or []))])
    return {
        "schema_version": "phase56.stance.v1",
        "stance_lock_id": hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
        "topic_id": topic_id,
        "active_claim_id": active_claim_id,
        "previous_claim_id": previous_claim_id,
        "transition_type": classify_stance_transition(transition_type),
        "evidence_ids": list(evidence_ids or []),
        "new_evidence_ids": list(new_evidence_ids or []),
        "allowed": allowed,
        "reason": reason,
        "created_at": _utc_now(),
        "non_authoritative": True,
        "decision_power": "none",
        "stance_is_not_memory": True,
        "does_not_write_memory": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
    }


def build_contradiction_receipt(*, topic_id: str, old_claim_id: str, new_claim_id: str, contradiction_type: str, evidence_ids_compared: list[str] | None = None, new_evidence_ids: list[str] | None = None, severity: str = "warning", adjudication: str = "warn") -> dict[str, Any]:
    material = "|".join([topic_id, old_claim_id, new_claim_id, contradiction_type, ",".join(sorted(evidence_ids_compared or [])), ",".join(sorted(new_evidence_ids or []))])
    return {
        "schema_version": "phase56.contradiction.v1",
        "contradiction_id": hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
        "topic_id": topic_id,
        "old_claim_id": old_claim_id,
        "new_claim_id": new_claim_id,
        "evidence_ids_compared": list(evidence_ids_compared or []),
        "new_evidence_ids": list(new_evidence_ids or []),
        "contradiction_type": contradiction_type,
        "severity": severity,
        "adjudication": adjudication,
        "detected_at": _utc_now(),
        "created_at": _utc_now(),
        "non_authoritative": True,
        "decision_power": "none",
        "contradiction_is_not_memory": True,
        "does_not_write_memory": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
    }


def detect_no_new_evidence_reversal(*, previous_claim: dict[str, Any], new_claim: dict[str, Any], transition_type: str, new_evidence_ids: list[str] | None = None, has_new_source_quality_finding: bool = False) -> dict[str, Any] | None:
    if previous_claim.get("topic_id") != new_claim.get("topic_id"):
        return None
    if previous_claim.get("epistemic_status") not in {"directly_supported", "provisional_supported", "strongly_inferred"}:
        return None
    new_ids = list(new_evidence_ids or [])
    t = classify_stance_transition(transition_type)
    if t in {"weaken_with_new_evidence", "supersede_with_new_evidence"} and not new_ids:
        return build_contradiction_receipt(topic_id=str(new_claim.get("topic_id") or "unknown"), old_claim_id=str(previous_claim.get("claim_id") or "unknown"), new_claim_id=str(new_claim.get("claim_id") or "unknown"), contradiction_type="no_new_evidence_reversal", evidence_ids_compared=list(previous_claim.get("evidence_ids") or []), new_evidence_ids=new_ids, severity="blocking", adjudication="require_new_evidence")
    if t == "qualify" and new_claim.get("epistemic_status") in {"plausible_but_unverified", "underconstrained"} and not new_ids:
        return build_contradiction_receipt(topic_id=str(new_claim.get("topic_id") or "unknown"), old_claim_id=str(previous_claim.get("claim_id") or "unknown"), new_claim_id=str(new_claim.get("claim_id") or "unknown"), contradiction_type="unsupported_dilution", evidence_ids_compared=list(previous_claim.get("evidence_ids") or []), new_evidence_ids=new_ids, severity="blocking", adjudication="block_revision")
    if t == "policy_block_but_preserve" and not has_new_source_quality_finding and new_claim.get("source_quality_summary") == "undermined":
        return build_contradiction_receipt(topic_id=str(new_claim.get("topic_id") or "unknown"), old_claim_id=str(previous_claim.get("claim_id") or "unknown"), new_claim_id=str(new_claim.get("claim_id") or "unknown"), contradiction_type="unsupported_source_undermining", evidence_ids_compared=list(previous_claim.get("evidence_ids") or []), new_evidence_ids=new_ids, severity="blocking", adjudication="hold_revision_require_explanation")
    return None


def resolve_active_stance(previous_claim: dict[str, Any], new_claim: dict[str, Any], transition_type: str) -> str:
    return str(previous_claim.get("claim_id")) if classify_stance_transition(transition_type) == "policy_block_but_preserve" else str(new_claim.get("claim_id"))


def summarize_stance_lock_status(stance_receipt: dict[str, Any], contradiction_receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"allowed": bool(stance_receipt.get("allowed")), "transition_type": stance_receipt.get("transition_type"), "active_claim_id": stance_receipt.get("active_claim_id"), "contradiction": contradiction_receipt}


def stance_receipt_ref(receipt: dict[str, Any]) -> str:
    return f"stance:{receipt['stance_lock_id']}"


def contradiction_receipt_ref(receipt: dict[str, Any]) -> str:
    return f"contradiction:{receipt['contradiction_id']}"
