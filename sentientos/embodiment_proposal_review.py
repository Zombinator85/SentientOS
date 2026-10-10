from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos.ledger_api import append_audit_record
from sentientos.embodiment_proposals import DEFAULT_PROPOSAL_LOG, embodied_proposal_ref, list_recent_embodied_proposals
from sentientos.windows_handle_custody import read_explicit_file
from sentientos.world_state_board import record_digest

SCHEMA_VERSION = "embodiment.proposal.review_receipt.v2"
DEFAULT_REVIEW_RECEIPT_LOG = Path("logs/embodiment_proposal_reviews.jsonl")
MAX_REVIEW_RECEIPT_LOG_BYTES = 16_777_216
MAX_REVIEW_RECEIPTS_PER_PROJECTION = 32
MAX_REVIEW_MATERIAL_BYTES = 32_768

ALLOWED_REVIEW_OUTCOMES = {
    "pending_review",
    "reviewed_deferred",
    "reviewed_rejected",
    "reviewed_needs_more_context",
    "reviewed_approved_for_next_stage",
}
ALLOWED_REVIEWER_KINDS = {"operator", "system_policy", "diagnostic", "test_fixture"}


def classify_embodied_proposal_review_outcome(review_outcome: str) -> str:
    outcome = str(review_outcome or "").strip().lower()
    if outcome not in ALLOWED_REVIEW_OUTCOMES:
        raise ValueError(f"unsupported review_outcome: {review_outcome}")
    return outcome


def embodied_proposal_review_receipt_ref(record: Mapping[str, Any]) -> str:
    return f"proposal_review:{record['review_receipt_id']}"


def _review_receipt_id(material: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
    return f"eprr_{digest}"


def _review_material_digest(material: Mapping[str, Any]) -> str:
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _bounded_review_refs(value: Any) -> bool:
    return (isinstance(value, list) and len(value) <= 32
            and all(isinstance(item, str) and 0 < len(item) <= 512 for item in value))


def build_embodied_proposal_review_receipt(*, proposal_record: Mapping[str, Any], review_outcome: str, reviewer_kind: str,
                                           reviewer_ref: str | None = None, reviewer_label: str | None = None,
                                           review_rationale: str | None = None, source_event_refs: Sequence[str] | None = None,
                                           risk_flags: Mapping[str, Any] | None = None, correlation_id: str | None = None,
                                           created_at: float | None = None) -> dict[str, Any]:
    outcome = classify_embodied_proposal_review_outcome(review_outcome)
    reviewer_kind_normalized = str(reviewer_kind or "").strip().lower()
    if reviewer_kind_normalized not in ALLOWED_REVIEWER_KINDS:
        raise ValueError(f"unsupported reviewer_kind: {reviewer_kind}")

    proposal_ref = embodied_proposal_ref(proposal_record)
    proposal_digest = proposal_record.get("proposal_digest")
    if proposal_digest is not None and (not isinstance(proposal_digest, str)
            or not proposal_digest.startswith("sha256:") or len(proposal_digest) != 71
            or any(character not in "0123456789abcdef" for character in proposal_digest[7:])):
        raise ValueError("proposal_digest_invalid")
    event_refs = list(source_event_refs if source_event_refs is not None else proposal_record.get("source_event_refs", []))
    if not _bounded_review_refs(event_refs):
        raise ValueError("proposal_review_event_refs_invalid")
    material = {
        "proposal_id": proposal_record.get("proposal_id"),
        "proposal_ref": proposal_ref,
        "review_outcome": outcome,
        "reviewer_kind": reviewer_kind_normalized,
        "reviewer_ref": reviewer_ref,
        "reviewer_label": reviewer_label,
        "review_rationale": review_rationale,
        "correlation_id": correlation_id if correlation_id is not None else proposal_record.get("correlation_id"),
        "source_event_refs": event_refs,
    }
    execution_contexts = proposal_record.get("source_execution_contexts", ())
    if execution_contexts:
        if (not isinstance(execution_contexts, (list, tuple)) or len(execution_contexts) > 3
                or any(not isinstance(item, Mapping) or len(json.dumps(dict(item), sort_keys=True,
                    separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > 8192
                    for item in execution_contexts)):
            raise ValueError("proposal_execution_context_bounds_invalid")
        material["source_execution_contexts"] = [dict(item) for item in execution_contexts]
    if proposal_digest is not None:
        material["proposal_digest"] = proposal_digest
    if len(json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > MAX_REVIEW_MATERIAL_BYTES:
        raise ValueError("proposal_review_material_oversized")
    return {
        "schema_version": SCHEMA_VERSION,
        "review_receipt_id": _review_receipt_id(material),
        "review_material": material,
        "review_material_digest": _review_material_digest(material),
        "proposal_id": proposal_record.get("proposal_id"),
        "proposal_digest": proposal_digest,
        "proposal_binding_posture": "digest_bound" if proposal_digest is not None else "legacy_id_only",
        "proposal_ref": proposal_ref,
        "proposal_kind": str(proposal_record.get("proposal_kind") or "unknown"),
        "review_outcome": outcome,
        "reviewer_kind": reviewer_kind_normalized,
        "reviewer_ref": reviewer_ref,
        "reviewer_label": reviewer_label,
        "reviewer_identity_posture": "declared_unverified",
        "review_rationale": review_rationale or "review_recorded",
        "source_proposal_ref": proposal_ref,
        "source_ingress_receipt_ref": proposal_record.get("ingress_receipt_ref"),
        "source_event_refs": list(source_event_refs if source_event_refs is not None else proposal_record.get("source_event_refs", [])),
        "source_execution_contexts": material.get("source_execution_contexts", []),
        "correlation_id": correlation_id if correlation_id is not None else proposal_record.get("correlation_id"),
        "risk_flags": dict(risk_flags or proposal_record.get("risk_flags") or {}),
        "privacy_retention_posture": proposal_record.get("privacy_retention_posture", "review"),
        "consent_posture": proposal_record.get("consent_posture", "not_asserted"),
        "created_at": float(created_at if created_at is not None else time.time()),
        "non_authoritative": True,
        "decision_power": "none",
        "does_not_write_memory": True,
        "does_not_trigger_feedback": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
        "approval_is_not_execution": True,
    }


def _verified_review_material(record: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Return canonical review identity material and its binding posture."""
    material = record.get("review_material")
    required = {"proposal_id", "proposal_ref", "review_outcome", "reviewer_kind", "reviewer_ref",
        "reviewer_label", "review_rationale", "correlation_id", "source_event_refs"}
    if record.get("schema_version") != SCHEMA_VERSION:
        return None, "invalid"
    if material is None:
        # Historical v2 receipts stored only their deterministic ID. Rebuild
        # the original ID material; do not import unbound execution contexts.
        legacy = {key: record.get(key) for key in required}
        for field in ("proposal_digest",):
            if record.get(field) is not None:
                legacy[field] = record[field]
        candidates = [legacy]
        if legacy.get("review_rationale") == "review_recorded":
            alternate = dict(legacy)
            alternate["review_rationale"] = None
            candidates.append(alternate)
        material = next((item for item in candidates
                         if record.get("review_receipt_id") == _review_receipt_id(item)), None)
        if material is None:
            return None, "invalid"
        posture = "legacy_id_reconstructed"
    elif not isinstance(material, Mapping):
        return None, "invalid"
    else:
        material = dict(material)
        if frozenset(material) not in {frozenset(required), frozenset(required | {"proposal_digest"}),
                frozenset(required | {"source_execution_contexts"}),
                frozenset(required | {"proposal_digest", "source_execution_contexts"})}:
            return None, "invalid"
        posture = "material_digest_bound"
        try:
            encoded_size = len(json.dumps(material, sort_keys=True, separators=(",", ":"),
                                          ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError):
            return None, "invalid"
        if (encoded_size > MAX_REVIEW_MATERIAL_BYTES
                or record.get("review_receipt_id") != _review_receipt_id(material)
                or record.get("review_material_digest") != _review_material_digest(material)):
            return None, "invalid"
    if (record.get("review_receipt_id") != _review_receipt_id(material)
            or record.get("proposal_id") != material.get("proposal_id")
            or record.get("proposal_ref") != material.get("proposal_ref")
            or record.get("review_outcome") != material.get("review_outcome")
            or record.get("reviewer_kind") != material.get("reviewer_kind")
            or record.get("reviewer_ref") != material.get("reviewer_ref")
            or record.get("reviewer_label") != material.get("reviewer_label")
            or record.get("review_rationale") != (material.get("review_rationale") or "review_recorded")
            or record.get("correlation_id") != material.get("correlation_id")
            or record.get("source_event_refs") != material.get("source_event_refs")
            or record.get("proposal_digest") != material.get("proposal_digest")
            or record.get("source_execution_contexts", []) != material.get("source_execution_contexts", [])
            or not _bounded_review_refs(material.get("source_event_refs"))):
        return None, "invalid"
    contexts = material.get("source_execution_contexts", [])
    if (not isinstance(contexts, list) or len(contexts) > 3
            or any(not isinstance(item, Mapping) or len(json.dumps(dict(item), sort_keys=True,
                separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > 8192 for item in contexts)):
        return None, "invalid"
    try:
        classify_embodied_proposal_review_outcome(str(material.get("review_outcome", "")))
    except ValueError:
        return None, "invalid"
    return material, posture


def verify_embodied_proposal_review_receipt(record: Mapping[str, Any]) -> bool:
    """Verify receipt identity; reviewer identity itself remains unverified."""
    material, _ = _verified_review_material(record)
    return material is not None


def review_receipt_world_state_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt one exact review assertion as historical context, never authority."""
    material, binding_posture = _verified_review_material(record)
    if material is None:
        raise ValueError("review_receipt_identity_invalid")
    receipt_id = str(record["review_receipt_id"])
    semantic = {
        "source_kind": "embodiment", "source_id": f"proposal-review:{receipt_id}",
        "schema_version": SCHEMA_VERSION, "subject_id": str(record["proposal_id"]),
        "subject_kind": "embodied_strategy_proposal_review", "stage": "review",
        "disposition": str(record["review_outcome"]),
        "evidence_strength": ("digest_bound_review_assertion_unverified_reviewer"
            if binding_posture == "material_digest_bound" else "legacy_id_bound_review_assertion_unverified_reviewer"),
        "staleness": "unknown", "effect_claimed": False, "effect_proven": False,
        "payload": {"review_receipt_id": receipt_id,
            "review_material_digest": record.get("review_material_digest"),
            "review_binding_posture": binding_posture,
            "proposal_id": record["proposal_id"], "proposal_digest": record.get("proposal_digest"),
            "review_outcome": record["review_outcome"], "reviewer_kind": record["reviewer_kind"],
            "reviewer_identity_posture": "declared_unverified",
            "source_event_refs": list(record.get("source_event_refs", ())),
            "source_execution_contexts": list(material.get("source_execution_contexts", ())),
            "event_time_posture": "review_time_not_authenticated",
            "observer_issuer_posture": "unverified_caller_assertion",
            "current_truth": False, "authority": False, "effect_proven": False},
    }
    semantic["digest"] = record_digest(semantic)
    return semantic


def load_selected_review_world_state_records(*, path: Path,
        review_receipt_ids: Sequence[str]) -> list[dict[str, Any]]:
    """Read only explicitly selected, digest-bound review assertions.

    The local reviewer remains unverified and the projection carries no event
    time, authority, effect, or freshness claim.
    """
    identities = tuple(review_receipt_ids)
    if (len(identities) > MAX_REVIEW_RECEIPTS_PER_PROJECTION
            or len(identities) != len(set(identities))
            or any(not isinstance(item, str) or len(item) != 29 or not item.startswith("eprr_")
                or any(character not in "0123456789abcdef" for character in item[5:])
                for item in identities)):
        raise ValueError("review_receipt_selection_invalid")
    if not identities:
        return []
    raw = read_explicit_file(path, max_bytes=MAX_REVIEW_RECEIPT_LOG_BYTES)
    selected = set(identities)
    found: dict[str, dict[str, Any]] = {}
    lines = raw.splitlines()
    if len(lines) > 65_536:
        raise ValueError("review_receipt_log_line_limit_exceeded")
    for line in lines:
        if not line:
            continue
        if len(line) > 65_536:
            raise ValueError("review_receipt_log_record_oversized")
        try:
            row = json.loads(line.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("review_receipt_log_corrupt") from exc
        if not isinstance(row, dict):
            raise ValueError("review_receipt_log_shape_invalid")
        receipt_id = row.get("review_receipt_id")
        if receipt_id not in selected:
            continue
        if not verify_embodied_proposal_review_receipt(row):
            raise ValueError("review_receipt_binding_invalid")
        prior = found.get(receipt_id)
        if prior is not None and prior != row:
            raise ValueError("review_receipt_identity_conflict")
        found[receipt_id] = row
    if set(found) != selected:
        raise FileNotFoundError("selected_review_receipt_missing")
    return [review_receipt_world_state_record(found[item]) for item in identities]


def append_embodied_proposal_review_receipt(record: Mapping[str, Any], *, path: Path = DEFAULT_REVIEW_RECEIPT_LOG) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    return append_audit_record(path, record)


def list_recent_embodied_proposal_review_receipts(*, path: Path = DEFAULT_REVIEW_RECEIPT_LOG, limit: int = 50) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[-max(1, limit):]


def resolve_embodied_proposal_review_state(*, proposals: Sequence[Mapping[str, Any]], review_receipts: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    latest: dict[tuple[str, str | None], tuple[float, str, str]] = {}
    for row in review_receipts:
        pid = str(row.get("proposal_id") or "")
        if not pid:
            continue
        supplied_digest = row.get("proposal_digest")
        key = (pid, supplied_digest if isinstance(supplied_digest, str) else None)
        ts = float(row.get("created_at") or 0.0)
        rid = str(row.get("review_receipt_id") or "")
        outcome = classify_embodied_proposal_review_outcome(str(row.get("review_outcome") or "pending_review"))
        current = latest.get(key)
        if current is None or (ts, rid) >= (current[0], current[1]):
            latest[key] = (ts, rid, outcome)

    resolved: dict[str, str] = {}
    for proposal in proposals:
        pid = str(proposal.get("proposal_id") or "")
        if not pid:
            continue
        proposed_digest = proposal.get("proposal_digest")
        key = (pid, proposed_digest if isinstance(proposed_digest, str) else None)
        outcome = latest.get(key, (0.0, "", "pending_review"))[2]
        mapped = {
            "pending_review": "pending_review",
            "reviewed_deferred": "deferred",
            "reviewed_rejected": "rejected",
            "reviewed_needs_more_context": "needs_more_context",
            "reviewed_approved_for_next_stage": "approved_for_next_stage",
        }[outcome]
        resolved[pid] = mapped
    return resolved


def summarize_embodied_proposal_review_status(*, proposals: Sequence[Mapping[str, Any]], review_receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    states = resolve_embodied_proposal_review_state(proposals=proposals, review_receipts=review_receipts)
    counts = {"pending_review": 0, "approved_for_next_stage": 0, "rejected": 0, "deferred": 0, "needs_more_context": 0}
    for state in states.values():
        counts[state] = counts.get(state, 0) + 1
    high_risk_pending = 0
    by_id = {str(p.get("proposal_id") or ""): p for p in proposals}
    for pid, state in states.items():
        if state != "pending_review":
            continue
        row = by_id.get(pid, {})
        flags = row.get("risk_flags") if isinstance(row.get("risk_flags"), Mapping) else {}
        if flags.get("biometric_sensitive") or flags.get("emotion_sensitive"):
            high_risk_pending += 1

    if not proposals or counts["pending_review"] == 0:
        posture = "no_pending_review_activity"
    elif counts["pending_review"] > 0 and counts["approved_for_next_stage"] == 0 and counts["rejected"] == 0 and counts["deferred"] == 0 and counts["needs_more_context"] == 0:
        posture = "pending_review_items"
    elif counts["pending_review"] == 0 and counts["approved_for_next_stage"] > 0:
        posture = "reviewed_items_waiting_next_stage"
    elif high_risk_pending > 0:
        posture = "high_risk_review_pending"
    else:
        posture = "mixed_review_state"

    return {
        "review_counts_by_outcome": counts,
        "pending_without_review_count": counts["pending_review"],
        "approved_for_next_stage_count": counts["approved_for_next_stage"],
        "rejected_count": counts["rejected"],
        "deferred_count": counts["deferred"],
        "needs_more_context_count": counts["needs_more_context"],
        "review_posture": posture,
    }


__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_REVIEW_RECEIPT_LOG",
    "ALLOWED_REVIEW_OUTCOMES",
    "build_embodied_proposal_review_receipt",
    "verify_embodied_proposal_review_receipt",
    "review_receipt_world_state_record",
    "load_selected_review_world_state_records",
    "append_embodied_proposal_review_receipt",
    "list_recent_embodied_proposal_review_receipts",
    "embodied_proposal_review_receipt_ref",
    "classify_embodied_proposal_review_outcome",
    "resolve_embodied_proposal_review_state",
    "summarize_embodied_proposal_review_status",
    "DEFAULT_PROPOSAL_LOG",
    "list_recent_embodied_proposals",
]
