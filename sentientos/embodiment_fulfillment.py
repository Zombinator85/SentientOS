from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos.embodiment_governance_bridge import embodied_governance_bridge_candidate_ref
from sentientos.ledger_api import append_audit_record
from sentientos.world_state_board import record_digest
from sentientos.windows_handle_custody import read_explicit_file

CANDIDATE_SCHEMA_VERSION = "embodiment.fulfillment_candidate.v1"
LEGACY_RECEIPT_SCHEMA_VERSION = "embodiment.fulfillment_receipt.v1"
RECEIPT_SCHEMA_VERSION = "embodiment.fulfillment_receipt.v2"
DEFAULT_FULFILLMENT_RECEIPT_LOG = Path("logs/embodiment_fulfillment_receipts.jsonl")
MAX_FULFILLMENT_LOG_BYTES = 16_777_216
MAX_FULFILLMENT_RECEIPTS_PER_PROJECTION = 32
MAX_FULFILLMENT_RECEIPT_BYTES = 32_768

_FULFILLMENT_KIND_BY_BRIDGE_KIND = {
    "memory_governance_review_candidate": "memory_fulfillment_candidate",
    "feedback_action_governance_review_candidate": "feedback_action_fulfillment_candidate",
    "screen_retention_governance_review_candidate": "screen_retention_fulfillment_candidate",
    "vision_retention_governance_review_candidate": "vision_retention_fulfillment_candidate",
    "multimodal_retention_governance_review_candidate": "multimodal_retention_fulfillment_candidate",
    "operator_attention_governance_review_candidate": "operator_attention_fulfillment_candidate",
}

ALLOWED_FULFILLMENT_OUTCOMES = {
    "pending_fulfillment_review",
    "fulfillment_declined",
    "fulfillment_expired",
    "fulfillment_superseded",
    "fulfillment_failed_validation",
    "fulfilled_external_manual",
    "fulfilled_by_governed_path",
}


def embodied_fulfillment_candidate_ref(record: Mapping[str, Any]) -> str:
    return f"fulfillment_candidate:{record['fulfillment_candidate_id']}"


def embodied_fulfillment_receipt_ref(record: Mapping[str, Any]) -> str:
    return f"fulfillment_receipt:{record['fulfillment_receipt_id']}"


def classify_embodied_fulfillment_candidate_kind(bridge_candidate_kind: str) -> str:
    return _FULFILLMENT_KIND_BY_BRIDGE_KIND.get(str(bridge_candidate_kind or ""), "unsupported_fulfillment_candidate")


def classify_embodied_fulfillment_outcome(outcome: str) -> str:
    normalized = str(outcome or "pending_fulfillment_review")
    if normalized in ALLOWED_FULFILLMENT_OUTCOMES:
        return normalized
    return "fulfillment_failed_validation"


def _resolve_fulfillment_posture(bridge_candidate: Mapping[str, Any], kind: str) -> str:
    if not bridge_candidate:
        return "blocked_missing_governance_bridge"
    if kind == "unsupported_fulfillment_candidate":
        return "blocked_unsupported_kind"
    bridge_posture = str(bridge_candidate.get("bridge_posture") or "")
    if bridge_posture != "eligible_for_governance_review":
        return "blocked_bridge_not_eligible"
    privacy = str(bridge_candidate.get("privacy_retention_posture") or "")
    consent = str(bridge_candidate.get("consent_posture") or "")
    if privacy in {"restricted", "sensitive"} and consent in {"", "unknown", "not_asserted", "required"}:
        return "blocked_privacy_or_consent_required"
    return "eligible_for_fulfillment_review"


def build_embodied_fulfillment_candidate(*, governance_bridge_candidate: Mapping[str, Any], created_at: float | None = None) -> dict[str, Any]:
    kind = classify_embodied_fulfillment_candidate_kind(str(governance_bridge_candidate.get("governance_bridge_candidate_kind") or ""))
    posture = _resolve_fulfillment_posture(governance_bridge_candidate, kind)
    material = {
        "governance_bridge_candidate_id": governance_bridge_candidate.get("governance_bridge_candidate_id"),
        "fulfillment_candidate_kind": kind,
        "fulfillment_posture": posture,
    }
    candidate_id = "efc_" + hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
    return {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "fulfillment_candidate_id": candidate_id,
        "fulfillment_candidate_kind": kind,
        "source_governance_bridge_candidate_id": governance_bridge_candidate.get("governance_bridge_candidate_id"),
        "source_governance_bridge_candidate_ref": embodied_governance_bridge_candidate_ref(governance_bridge_candidate),
        "source_handoff_candidate_ref": governance_bridge_candidate.get("source_handoff_candidate_ref"),
        "source_proposal_id": governance_bridge_candidate.get("source_proposal_id"),
        "source_review_receipt_id": governance_bridge_candidate.get("source_review_receipt_id"),
        "source_ingress_receipt_ref": governance_bridge_candidate.get("source_ingress_receipt_ref"),
        "source_event_refs": list(governance_bridge_candidate.get("source_event_refs") or []),
        "correlation_id": governance_bridge_candidate.get("correlation_id"),
        "source_module": governance_bridge_candidate.get("source_module"),
        "proposal_kind": governance_bridge_candidate.get("proposal_kind"),
        "fulfillment_posture": posture,
        "risk_flags": dict(governance_bridge_candidate.get("risk_flags") or {}),
        "privacy_retention_posture": governance_bridge_candidate.get("privacy_retention_posture", "review"),
        "consent_posture": governance_bridge_candidate.get("consent_posture", "not_asserted"),
        "candidate_payload_summary": dict(governance_bridge_candidate.get("candidate_payload_summary") or {}),
        "rationale": list(governance_bridge_candidate.get("rationale") or []),
        "created_at": float(created_at if created_at is not None else time.time()),
        "non_authoritative": True,
        "decision_power": "none",
        "does_not_write_memory": True,
        "does_not_trigger_feedback": True,
        "does_not_commit_retention": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
        "bridge_is_not_admission": True,
        "fulfillment_candidate_is_not_effect": True,
    }


def resolve_embodied_fulfillment_candidates(*, governance_bridge_candidates: Sequence[Mapping[str, Any]], created_at: float | None = None) -> dict[str, Any]:
    candidates = []
    by_kind: dict[str, int] = {}
    by_posture: dict[str, int] = {}
    for bridge in governance_bridge_candidates:
        row = build_embodied_fulfillment_candidate(governance_bridge_candidate=bridge, created_at=created_at)
        by_posture[row["fulfillment_posture"]] = by_posture.get(row["fulfillment_posture"], 0) + 1
        if row["fulfillment_posture"] == "eligible_for_fulfillment_review":
            by_kind[row["fulfillment_candidate_kind"]] = by_kind.get(row["fulfillment_candidate_kind"], 0) + 1
            candidates.append(row)
    return {
        "fulfillment_candidates": candidates,
        "fulfillment_counts_by_kind": dict(sorted(by_kind.items())),
        "blocked_fulfillment_counts_by_reason": dict(sorted((k, v) for k, v in by_posture.items() if k != "eligible_for_fulfillment_review")),
        "counts_by_fulfillment_posture": dict(sorted(by_posture.items())),
    }


def build_embodied_fulfillment_receipt(*, fulfillment_candidate: Mapping[str, Any], fulfillment_outcome: str, fulfiller_kind: str, created_at: float | None = None, fulfiller_ref: str | None = None, fulfiller_label: str | None = None, fulfillment_rationale: str | None = None) -> dict[str, Any]:
    outcome = classify_embodied_fulfillment_outcome(fulfillment_outcome)
    body = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "source_fulfillment_candidate_id": fulfillment_candidate.get("fulfillment_candidate_id"),
        "source_fulfillment_candidate_ref": embodied_fulfillment_candidate_ref(fulfillment_candidate),
        "source_governance_bridge_candidate_ref": fulfillment_candidate.get("source_governance_bridge_candidate_ref"),
        "source_handoff_candidate_ref": fulfillment_candidate.get("source_handoff_candidate_ref"),
        "source_proposal_id": fulfillment_candidate.get("source_proposal_id"),
        "source_review_receipt_id": fulfillment_candidate.get("source_review_receipt_id"),
        "fulfillment_candidate_kind": fulfillment_candidate.get("fulfillment_candidate_kind"),
        "fulfillment_outcome": outcome,
        "fulfiller_kind": str(fulfiller_kind or "diagnostic"),
        "fulfiller_ref": fulfiller_ref,
        "fulfiller_label": fulfiller_label,
        "fulfillment_rationale": fulfillment_rationale,
        "source_event_refs": list(fulfillment_candidate.get("source_event_refs") or []),
        "correlation_id": fulfillment_candidate.get("correlation_id"),
        "risk_flags": dict(fulfillment_candidate.get("risk_flags") or {}),
        "privacy_retention_posture": fulfillment_candidate.get("privacy_retention_posture", "review"),
        "consent_posture": fulfillment_candidate.get("consent_posture", "not_asserted"),
        "created_at": float(created_at if created_at is not None else time.time()),
        "non_authoritative": True,
        "decision_power": "none",
        "fulfillment_receipt_is_not_effect": True,
        "receipt_does_not_prove_side_effect": True,
        "does_not_write_memory": True,
        "does_not_trigger_feedback": True,
        "does_not_commit_retention": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
    }
    if (not isinstance(body["source_fulfillment_candidate_id"], str)
            or not body["source_fulfillment_candidate_id"]
            or not isinstance(body["fulfillment_outcome"], str)
            or not isinstance(body["fulfiller_kind"], str)
            or not math.isfinite(float(body["created_at"]))
            or len(json.dumps(body, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False).encode("utf-8")) > MAX_FULFILLMENT_RECEIPT_BYTES):
        raise ValueError("fulfillment_receipt_material_invalid")
    receipt_id = "efr_" + hashlib.sha256(json.dumps(body, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
    sealed = {**body, "fulfillment_receipt_id": receipt_id}
    sealed["fulfillment_receipt_digest"] = "sha256:" + hashlib.sha256(json.dumps(
        sealed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    if len(json.dumps(sealed, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False).encode("utf-8")) + 1 > MAX_FULFILLMENT_RECEIPT_BYTES:
        raise ValueError("fulfillment_receipt_material_invalid")
    return sealed


def verify_embodied_fulfillment_receipt(record: Mapping[str, Any]) -> bool:
    if (not isinstance(record, Mapping) or record.get("schema_version") != RECEIPT_SCHEMA_VERSION
            or record.get("fulfillment_outcome") not in ALLOWED_FULFILLMENT_OUTCOMES
            or record.get("fulfillment_receipt_is_not_effect") is not True
            or record.get("receipt_does_not_prove_side_effect") is not True
            or any(record.get(key) is not True for key in ("non_authoritative", "does_not_write_memory",
                "does_not_trigger_feedback", "does_not_commit_retention", "does_not_admit_work",
                "does_not_execute_or_route_work"))):
        return False
    try:
        value = dict(record)
        claimed_digest = value.pop("fulfillment_receipt_digest")
        receipt_id = value.pop("fulfillment_receipt_id")
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False).encode("utf-8")
        if (len(json.dumps(dict(record), sort_keys=True, separators=(",", ":"),
                ensure_ascii=False).encode("utf-8")) + 1 > MAX_FULFILLMENT_RECEIPT_BYTES
                or not isinstance(record.get("source_fulfillment_candidate_id"), str)
                or not record["source_fulfillment_candidate_id"]
                or not isinstance(record.get("created_at"), (int, float))
                or not math.isfinite(float(record["created_at"]))
                or not isinstance(record.get("fulfiller_kind"), str)
                or not record["fulfiller_kind"]):
            return False
        expected_id = "efr_" + hashlib.sha256(encoded).hexdigest()[:24]
        expected_digest = "sha256:" + hashlib.sha256(json.dumps(
            {**value, "fulfillment_receipt_id": receipt_id}, sort_keys=True,
            separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        return (receipt_id == expected_id and claimed_digest == expected_digest
            and (record.get("source_fulfillment_candidate_ref") ==
                 "fulfillment_candidate:" + record["source_fulfillment_candidate_id"]))
    except (KeyError, TypeError, ValueError):
        return False


def fulfillment_receipt_world_state_record(record: Mapping[str, Any]) -> dict[str, Any]:
    if not verify_embodied_fulfillment_receipt(record):
        raise ValueError("fulfillment_receipt_binding_invalid")
    receipt_id = str(record["fulfillment_receipt_id"])
    semantic = {"source_kind": "embodiment", "source_id": f"fulfillment-receipt:{receipt_id}",
        "schema_version": RECEIPT_SCHEMA_VERSION, "subject_id": str(record.get("source_proposal_id")
            or record["source_fulfillment_candidate_id"]),
        "subject_kind": "embodied_proposal_fulfillment_receipt", "stage": "observation",
        "disposition": str(record["fulfillment_outcome"]), "evidence_strength": "digest_bound_fulfillment_claim",
        "staleness": "unknown", "effect_claimed": False, "effect_proven": False,
        "payload": {**dict(record), "event_time_posture": "receipt_creation_not_effect_time",
            "observer_issuer_posture": "fulfiller_claim_unverified",
            "actual_effect_observed": False, "authority": False, "effect_proven": False}}
    semantic["digest"] = record_digest(semantic)
    return semantic


def load_selected_fulfillment_world_state_records(*, path: Path,
        fulfillment_receipt_ids: Sequence[str]) -> list[dict[str, Any]]:
    identities = tuple(fulfillment_receipt_ids)
    if (len(identities) > MAX_FULFILLMENT_RECEIPTS_PER_PROJECTION
            or len(identities) != len(set(identities))
            or any(not isinstance(item, str) or len(item) != 28 or not item.startswith("efr_")
                or any(character not in "0123456789abcdef" for character in item[4:])
                for item in identities)):
        raise ValueError("fulfillment_receipt_selection_invalid")
    if not identities:
        return []
    raw = read_explicit_file(path, max_bytes=MAX_FULFILLMENT_LOG_BYTES)
    if len(raw.splitlines()) > 65_536:
        raise ValueError("fulfillment_receipt_log_line_limit_exceeded")
    selected, found = set(identities), {}
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b"\n") or len(line) > MAX_FULFILLMENT_RECEIPT_BYTES:
            raise ValueError("fulfillment_receipt_log_row_invalid")
        try:
            row = json.loads(line.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("fulfillment_receipt_log_corrupt") from exc
        if not isinstance(row, dict) or json.dumps(row, sort_keys=True,
                separators=(",", ":")).encode("utf-8") + b"\n" != line:
            raise ValueError("fulfillment_receipt_log_noncanonical")
        receipt_id = row.get("fulfillment_receipt_id")
        if receipt_id not in selected:
            continue
        if not verify_embodied_fulfillment_receipt(row):
            raise ValueError("fulfillment_receipt_binding_invalid")
        prior = found.get(receipt_id)
        if prior is not None and prior != row:
            raise ValueError("fulfillment_receipt_identity_conflict")
        found[receipt_id] = row
    if set(found) != selected:
        raise FileNotFoundError("selected_fulfillment_receipt_missing")
    return [fulfillment_receipt_world_state_record(found[item]) for item in identities]


def append_embodied_fulfillment_receipt(*, path: Path = DEFAULT_FULFILLMENT_RECEIPT_LOG, receipt: Mapping[str, Any]) -> dict[str, Any]:
    return dict(append_audit_record(path, dict(receipt)))


def list_recent_embodied_fulfillment_receipts(*, path: Path = DEFAULT_FULFILLMENT_RECEIPT_LOG, limit: int = 200) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            rows.append(record)
    return rows[-max(1, int(limit)):]


def resolve_embodied_fulfillment_state(*, fulfillment_candidate: Mapping[str, Any], fulfillment_receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    candidate_id = str(fulfillment_candidate.get("fulfillment_candidate_id") or "")
    matched = [r for r in fulfillment_receipts if str(r.get("source_fulfillment_candidate_id") or "") == candidate_id]
    if not matched:
        return {"fulfillment_outcome": "pending_fulfillment_review", "latest_fulfillment_receipt_ref": None}
    latest = max(matched, key=lambda row: (float(row.get("created_at") or 0.0), str(row.get("fulfillment_receipt_id") or "")))
    return {
        "fulfillment_outcome": classify_embodied_fulfillment_outcome(str(latest.get("fulfillment_outcome") or "pending_fulfillment_review")),
        "latest_fulfillment_receipt_ref": embodied_fulfillment_receipt_ref(latest),
    }


def summarize_embodied_fulfillment_status(*, fulfillment_candidates: Sequence[Mapping[str, Any]], fulfillment_receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts_by_kind: dict[str, int] = {}
    counts_by_outcome: dict[str, int] = {}
    pending = 0
    fulfilled = 0
    high_risk_pending = 0
    for c in fulfillment_candidates:
        kind = str(c.get("fulfillment_candidate_kind") or "unknown")
        counts_by_kind[kind] = counts_by_kind.get(kind, 0) + 1
        state = resolve_embodied_fulfillment_state(fulfillment_candidate=c, fulfillment_receipts=fulfillment_receipts)
        out = state["fulfillment_outcome"]
        counts_by_outcome[out] = counts_by_outcome.get(out, 0) + 1
        if out == "pending_fulfillment_review":
            pending += 1
            if kind in {"memory_fulfillment_candidate", "feedback_action_fulfillment_candidate", "vision_retention_fulfillment_candidate", "screen_retention_fulfillment_candidate", "multimodal_retention_fulfillment_candidate"}:
                high_risk_pending += 1
        if out in {"fulfilled_external_manual", "fulfilled_by_governed_path"}:
            fulfilled += 1

    if not fulfillment_candidates:
        posture = "no_fulfillment_candidates"
    else:
        labels = ["fulfillment_candidates_available"]
        if pending > 0:
            labels.append("pending_fulfillment_review")
        if fulfilled > 0:
            labels.append("fulfilled_receipts_present")
        if high_risk_pending > 0:
            labels.append("high_risk_fulfillment_review_available")
        if len(counts_by_outcome) > 1:
            labels.append("mixed_fulfillment_state")
        if len(labels) == 1:
            posture = labels[0]
        elif len(labels) > 1:
            posture = "mixed_fulfillment_state" if "mixed_fulfillment_state" in labels else labels[-1]
    return {
        "fulfillment_candidate_count": len(fulfillment_candidates),
        "fulfillment_counts_by_kind": dict(sorted(counts_by_kind.items())),
        "fulfillment_counts_by_outcome": dict(sorted(counts_by_outcome.items())),
        "pending_fulfillment_review_count": pending,
        "fulfilled_receipt_count": fulfilled,
        "high_risk_fulfillment_pending_count": high_risk_pending,
        "fulfillment_posture": posture,
    }


__all__ = [k for k in globals().keys() if k.startswith(("CANDIDATE_", "RECEIPT_", "DEFAULT_", "MAX_FULFILLMENT_", "build_", "verify_", "fulfillment_receipt_", "load_selected_", "resolve_", "embodied_", "classify_", "append_", "list_", "summarize_", "ALLOWED_"))]
